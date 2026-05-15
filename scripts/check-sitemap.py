#!/usr/bin/env python3
"""
Check 07 — Sitemap accuracy.

Parses sitemap.xml, verifies presence + structural validity, samples
lastmod claims against source file mtimes (when source files can be
located via slug → file mapping).
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact,
    find_frontmatter_for_slug, load_config, load_frontmatter, time_check,
)


# Default frontmatter patterns when sitemap_lastmod_mode == "editorial"
# and the config doesn't override `slug_to_frontmatter_map`. Repo-portable
# defaults; ordered most-specific-first.
DEFAULT_EDITORIAL_PATTERNS = [
    "docs/editorial/drafts/*{slug}*.md",
    "writing-drafts/*{slug}*.md",
    "content/**/*{slug}*.md",
    "posts/**/*{slug}*.md",
]
DEFAULT_EDITORIAL_DATE_KEYS = [
    "dateModified",
    "originalPublicationDate",
    "publishedDate",
]


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse_sitemap(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    urls = []
    for u in root.findall(f"{SITEMAP_NS}url"):
        loc = u.find(f"{SITEMAP_NS}loc")
        lastmod = u.find(f"{SITEMAP_NS}lastmod")
        urls.append({
            "loc": loc.text if loc is not None else None,
            "lastmod": lastmod.text if lastmod is not None else None,
        })
    return urls


def find_source_file(repo: Path, slug: str) -> Path | None:
    """Try common source-content locations to locate a file that produces this slug."""
    candidates = [
        f"docs/editorial/drafts/*{slug}*.md",
        f"content/**/{slug}*.md",
        f"content/**/{slug}.md",
        f"src/content/**/{slug}*.md",
        f"posts/**/{slug}*.md",
        f"client/src/content/writing/*{slug}*.tsx",
        f"writing-drafts/*{slug}*.md",
    ]
    for pat in candidates:
        matches = list(repo.glob(pat))
        if matches:
            return matches[0]
    return None


def parse_iso_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        # Force timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="07-sitemap-accuracy")

    sm_path = find_artifact(repo, config, "sitemap_xml", [
        "dist/public/sitemap.xml", "public/sitemap.xml", "out/sitemap.xml",
        "_site/sitemap.xml", "build/sitemap.xml", "static/sitemap.xml",
    ])

    if not sm_path:
        result.findings.append(Finding(
            id="7.1.missing", severity="FAIL",
            title="sitemap.xml not found",
            fix_safety="manual",
            fix_action="Build the site to emit sitemap.xml; or set artifacts.sitemap_xml in config.",
        ))
        return result

    try:
        urls = parse_sitemap(sm_path)
    except ET.ParseError as e:
        result.findings.append(Finding(
            id="7.1.malformed", severity="FAIL",
            title="sitemap.xml malformed",
            current=str(e), fix_safety="manual",
        ))
        return result

    result.findings.append(Finding(
        id="7.1.parses", severity="PASS",
        title=f"sitemap.xml parses cleanly; {len(urls)} URLs",
    ))

    # 7.2 — lastmod accuracy (sample of 20)
    #
    # Two modes:
    #   * file_mtime (default, v0.4): compare sitemap <lastmod> against
    #     source file mtime. Correct for sites where the build pipeline
    #     preserves mtimes from authoring.
    #   * editorial: compare against editorial date keys (dateModified /
    #     originalPublicationDate / publishedDate) read from a
    #     frontmatter source file located via configured glob patterns.
    #     Correct for backdated catalogues where every source file
    #     shares a build-step mtime but the editorially-correct lastmod
    #     lives in the piece's frontmatter.
    lastmod_mode = config.get("sitemap_lastmod_mode", "file_mtime")
    editorial_cfg = config.get("slug_to_frontmatter_map") or {}
    if isinstance(editorial_cfg, dict):
        patterns: list[str] = []
        if editorial_cfg.get("pattern"):
            patterns.append(editorial_cfg["pattern"])
        if editorial_cfg.get("fallback_pattern"):
            patterns.append(editorial_cfg["fallback_pattern"])
        date_keys = editorial_cfg.get("date_keys") or DEFAULT_EDITORIAL_DATE_KEYS
    else:
        patterns = []
        date_keys = DEFAULT_EDITORIAL_DATE_KEYS
    if not patterns:
        patterns = DEFAULT_EDITORIAL_PATTERNS

    sample = urls[:20]
    matched = mtime_mismatches = all_identical = unverifiable = 0
    lastmod_values = []
    for u in sample:
        if not u["loc"] or not u["lastmod"]:
            continue
        lastmod_values.append(u["lastmod"][:10])
        # Slug = last path segment of loc
        slug = u["loc"].rstrip("/").rsplit("/", 1)[-1]
        sitemap_dt = parse_iso_date(u["lastmod"])
        if not sitemap_dt:
            unverifiable += 1
            continue

        if lastmod_mode == "editorial":
            fm_path = find_frontmatter_for_slug(repo, slug, patterns)
            if not fm_path:
                unverifiable += 1
                continue
            fm = load_frontmatter(fm_path)
            if not fm:
                unverifiable += 1
                continue
            editorial_dt = None
            for key in date_keys:
                raw = fm.get(key)
                if raw:
                    editorial_dt = parse_iso_date(str(raw))
                    if editorial_dt:
                        break
            if not editorial_dt:
                unverifiable += 1
                continue
            diff_days = abs((sitemap_dt - editorial_dt).days)
        else:
            src = find_source_file(repo, slug)
            if not src:
                unverifiable += 1
                continue
            src_mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc)
            diff_days = abs((sitemap_dt - src_mtime).days)

        if diff_days <= 1:
            matched += 1
        else:
            mtime_mismatches += 1

    truth_label = "editorial frontmatter" if lastmod_mode == "editorial" else "source mtime"

    # All-identical-lastmod check
    if lastmod_values and len(set(lastmod_values)) == 1:
        result.findings.append(Finding(
            id="7.2.all_identical", severity="FAIL",
            title="All sampled lastmod values are identical (suggests build-timestamp not per-piece date)",
            current=lastmod_values[0],
            fix_safety="manual",
            fix_action=(
                "Update sitemap emitter to derive lastmod from per-piece source "
                f"({truth_label}), not build time. Google discounts sitemaps "
                "with all-identical lastmod."
            ),
        ))
    elif unverifiable >= len(sample) - 2:
        miss_label = (
            "frontmatter source file or date key"
            if lastmod_mode == "editorial"
            else "source files"
        )
        result.findings.append(Finding(
            id="7.2.unverifiable", severity="MANUAL_VERIFY",
            title=f"Cannot map sitemap URLs to {miss_label} (slug -> source lookup failed)",
            fix_safety="manual",
            fix_action=(
                f"Verify manually that sitemap lastmod matches {truth_label}. "
                "If mode=editorial, check slug_to_frontmatter_map.pattern + date_keys."
            ),
        ))
    elif mtime_mismatches > matched:
        result.findings.append(Finding(
            id="7.2.mismatches", severity="WARN",
            title=(
                f"sitemap lastmod mismatch vs {truth_label} on "
                f"{mtime_mismatches}/{matched + mtime_mismatches} sampled URLs"
            ),
            fix_safety="manual",
        ))
    else:
        result.findings.append(Finding(
            id="7.2.accuracy", severity="PASS",
            title=(
                f"sitemap lastmod accurate vs {truth_label} on "
                f"{matched}/{matched + mtime_mismatches} verifiable sampled URLs"
            ),
        ))

    # 7.3 — Static pages present
    #
    # Compare path-normalised forms so the home URL matches whether the
    # sitemap emits it as `<APEX>`, `<APEX>/`, or just `/` and however the
    # config carries it. Strip trailing slashes from both sides; treat the
    # bare apex (empty-path) as equivalent to `/`.
    canonical = config.get("canonical_origin", "")
    apex = canonical.rstrip("/")
    static_pages_seen = {(u["loc"] or "").rstrip("/") for u in urls if u["loc"]}
    expected_static = ["/", "/writing", "/about", "/contact"]
    missing_static = []
    if canonical:
        for sp in expected_static:
            # For the root ("/"), the normalised target is the bare apex.
            target = apex if sp == "/" else apex + sp
            if target not in static_pages_seen:
                missing_static.append(sp)
        if missing_static:
            result.findings.append(Finding(
                id="7.3.static_pages", severity="WARN",
                title=f"Static pages missing from sitemap: {missing_static}",
                fix_safety="manual",
                fix_action="Add static pages (home, /writing, /about, /contact) to sitemap emitter.",
            ))
        else:
            result.findings.append(Finding(
                id="7.3.static_pages", severity="PASS",
                title="Common static pages present in sitemap",
            ))

    result.summary = (
        f"Sitemap: {len(urls)} URLs, lastmod-accuracy (mode={lastmod_mode}) sample "
        f"{matched}/{matched + mtime_mismatches} OK, {unverifiable} unverifiable."
    )
    result.config_used = {
        "sitemap_lastmod_mode": lastmod_mode,
        "editorial_patterns": patterns if lastmod_mode == "editorial" else None,
        "editorial_date_keys": date_keys if lastmod_mode == "editorial" else None,
    }
    return result


if __name__ == "__main__":
    parser = base_argparser("07-sitemap-accuracy")
    args = parser.parse_args()
    emit(run(args))
