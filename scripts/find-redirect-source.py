#!/usr/bin/env python3
"""
Helper for check 11.H — find the source of non-canonical (redirect-
triggering) internal hrefs in the codebase.

Reads `.launch-readiness-report.json` from a prior audit run, extracts
the URLs that triggered single-hop redirects in phase 11.H, derives the
non-canonical href shapes (typically trailing-slash drift), and greps
the consumer repo for files that emit those hrefs. Results are grouped
by file with line numbers.

Stdlib-only, portable, no thomasjankowski-side hardcodes. The 11.H
finding's `notes` field carries the redirect pairs in the form
"<from> -> <to>"; this script parses those pairs and searches for the
<from> URL's path component in the repo.

Usage:
  python3 find-redirect-source.py --repo PATH [--report PATH] \\
      [--include GLOB ...] [--exclude GLOB ...]

Exit codes: 0 on success (any results), 1 if no 11.H finding present,
2 on input error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path


DEFAULT_INCLUDE_SUFFIXES = (
    ".tsx", ".jsx", ".ts", ".js",
    ".html", ".htm",
    ".md", ".mdx",
    ".astro", ".vue", ".svelte",
    ".py",
)
# Skip generated / vendor / build dirs by default. Caller can override.
DEFAULT_EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "out", "_site",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".cache", "__pycache__",
    "coverage",
}


def parse_h_finding(report: list) -> list[tuple[str, str]] | None:
    """Pull (from_url, to_url) pairs out of the 11.H finding notes.

    Returns None if no 11.H finding exists in the report.
    Returns [] if the finding exists but lists no redirects (PASS state).
    """
    for check in report:
        if check.get("check") != "11-live-apex":
            continue
        for finding in check.get("findings", []):
            if finding.get("id") != "11.H.redirect_chain":
                continue
            sev = finding.get("severity")
            if sev == "PASS":
                return []
            notes = finding.get("notes") or ""
            pairs: list[tuple[str, str]] = []
            for segment in notes.split(";"):
                segment = segment.strip()
                if not segment:
                    continue
                # Two emitted shapes:
                #   WARN: "<url> -> <terminal>"
                #   FAIL: "<url> (N hops -> <terminal>)"
                m_warn = re.match(r"^(\S+)\s+->\s+(\S+)$", segment)
                m_fail = re.match(r"^(\S+)\s+\(\d+\s+hops\s+->\s+(\S+)\)$", segment)
                m = m_warn or m_fail
                if m:
                    pairs.append((m.group(1), m.group(2)))
            return pairs
    return None


def url_to_search_paths(from_url: str, to_url: str) -> list[str]:
    """Return the search needles for a redirect pair.

    For trailing-slash drift (`/writing` -> `/writing/`), the source-side
    href is the from_url path. We grep for the non-canonical path
    embedded in an href context. Returned needles avoid being too
    narrow (so we catch both `href="/writing"` and `href='/writing'`
    and `to="/writing"` router patterns).
    """
    src_path = urllib.parse.urlparse(from_url).path or "/"
    # Strip a single trailing slash on the from-side ONLY if the to-side
    # adds one (the canonical from-shape we want to find).
    src_norm = src_path.rstrip("/") or "/"
    needles = [src_norm]
    return needles


def should_scan(path: Path, includes: list[str], excludes: list[str]) -> bool:
    """Return True if `path` should be scanned given include/exclude
    globs. Excludes win over includes."""
    rel = str(path)
    for ex in excludes:
        if Path(rel).match(ex):
            return False
    if includes:
        for inc in includes:
            if Path(rel).match(inc):
                return True
        return False
    return True


def iter_repo_files(
    repo: Path,
    includes: list[str],
    excludes: list[str],
    exclude_dirs: set[str],
) -> list[Path]:
    out: list[Path] = []
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        # Skip if any path part is in exclude_dirs.
        if any(part in exclude_dirs for part in p.parts):
            continue
        if p.suffix.lower() not in DEFAULT_INCLUDE_SUFFIXES:
            continue
        if not should_scan(p.relative_to(repo), includes, excludes):
            continue
        out.append(p)
    return out


# Match the needle inside an href / to / link= style attribute. We
# require a quote (" or ') before the needle and either a quote, `#`,
# or `?` after (so `/writing` matches `href="/writing"` but NOT
# `href="/writing/"` or `href="/writing-foo"`).
def build_pattern(needle: str) -> re.Pattern:
    # Escape regex metas in the needle.
    esc = re.escape(needle)
    return re.compile(
        r"""(['"])""" + esc + r"""(?=['"#?])""",
    )


def search_file(path: Path, patterns: dict[str, re.Pattern]) -> dict[str, list[tuple[int, str]]]:
    """Return {needle: [(line_no, line_text), ...]}."""
    hits: dict[str, list[tuple[int, str]]] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for i, line in enumerate(text.splitlines(), start=1):
        for needle, pat in patterns.items():
            if pat.search(line):
                hits.setdefault(needle, []).append((i, line.rstrip()))
    return hits


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="Consumer repo to search.")
    p.add_argument(
        "--report",
        default=None,
        help="Path to .launch-readiness-report.json (default: <repo>/.launch-readiness-report.json).",
    )
    p.add_argument(
        "--include",
        action="append",
        default=[],
        help="Glob pattern (relative to repo) to include. Repeatable.",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob pattern (relative to repo) to exclude. Repeatable.",
    )
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    report_path = Path(args.report) if args.report else repo / ".launch-readiness-report.json"
    if not report_path.exists():
        print(f"ERROR: report not found at {report_path}", file=sys.stderr)
        return 2

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed report JSON: {e}", file=sys.stderr)
        return 2

    pairs = parse_h_finding(report)
    if pairs is None:
        print(
            "No 11.H.redirect_chain finding present in the report.\n"
            "Re-run audit with check 11 enabled (--checks 11 or include "
            "in --checks list).",
            file=sys.stderr,
        )
        return 1
    if not pairs:
        print("11.H is PASS — no redirect-triggering hrefs to find.")
        return 0

    # Build a needle map: needle -> list[(from_url, to_url)] for reporting.
    needle_to_pairs: dict[str, list[tuple[str, str]]] = {}
    for from_url, to_url in pairs:
        for needle in url_to_search_paths(from_url, to_url):
            needle_to_pairs.setdefault(needle, []).append((from_url, to_url))

    patterns = {n: build_pattern(n) for n in needle_to_pairs}

    print(f"Searching {repo} for {len(patterns)} non-canonical href shape(s):")
    for needle, prs in needle_to_pairs.items():
        sample_to = prs[0][1]
        print(f"  '{needle}' (canonical: {urllib.parse.urlparse(sample_to).path})")
    print()

    files = iter_repo_files(repo, args.include, args.exclude, DEFAULT_EXCLUDE_DIRS)

    # Group results by file -> needle -> line hits.
    results: dict[Path, dict[str, list[tuple[int, str]]]] = {}
    for f in files:
        hits = search_file(f, patterns)
        if hits:
            results[f] = hits

    if not results:
        print("No matches found. The redirect source may be in a route/link "
              "registry not covered by the default file-type set; pass "
              "--include to extend coverage.")
        return 0

    total_hits = 0
    for f in sorted(results):
        rel = f.relative_to(repo)
        print(f"{rel}")
        for needle in sorted(results[f]):
            print(f"  needle: '{needle}'")
            for ln, txt in results[f][needle]:
                # Truncate very long lines for readability.
                snip = txt if len(txt) <= 140 else txt[:137] + "..."
                print(f"    {ln}: {snip}")
                total_hits += 1
        print()

    print(f"Summary: {total_hits} match(es) across {len(results)} file(s). "
          f"Fix by appending the trailing slash (or aligning to the canonical "
          f"shape the CDN serves).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
