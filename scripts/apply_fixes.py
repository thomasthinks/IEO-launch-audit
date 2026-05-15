#!/usr/bin/env python3
"""
Safe-fix auto-application loop.

Reads `.launch-readiness-report.json` from a prior audit run, identifies
findings tagged `fix_safety: "safe"` that have a recognized fix recipe,
and applies the fix.

Scope is conservative: ONLY file-create / template-drop operations are
auto-applied. Source-code modifications (schema emitter changes, sitemap
mtime sourcing, hero TSX attribute additions across N pieces) remain
`manual` because the source layout varies per repo.

Idempotent: each fix function checks for prior application and skips if
already applied.

Usage:
  python3 apply_fixes.py --repo PATH --config PATH [--dry-run]

Exits 0 on success, 1 on partial failure, 2 on input error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_config


SKILL_DIR = Path(__file__).resolve().parent.parent


def find_public_root(repo: Path) -> Path | None:
    """Locate the most likely public-asset root."""
    for candidate in ("dist/public", "public", "out", "_site", "build", "static"):
        p = repo / candidate
        if p.exists() and p.is_dir():
            return p
    return None


# ---------------------------------------------------------------------------
# Fix functions: each takes (repo, config, finding) -> (applied: bool, msg: str)
# ---------------------------------------------------------------------------


def fix_create_robots_txt(repo: Path, config: dict, finding: dict) -> tuple[bool, str]:
    public_root = find_public_root(repo)
    if not public_root:
        return False, "no public-root directory found"
    target = public_root / "robots.txt"
    if target.exists():
        return False, f"already exists at {target.relative_to(repo)}; not overwriting (manual review)"
    template = SKILL_DIR / "templates" / "robots.txt"
    content = template.read_text(encoding="utf-8")
    canonical = config.get("canonical_origin", "https://example.com")
    content = content.replace("<CANONICAL_ORIGIN>", canonical)
    content = content.replace("<DATE>", datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"))
    target.write_text(content, encoding="utf-8")
    return True, f"created {target.relative_to(repo)}"


def fix_create_llms_txt(repo: Path, config: dict, finding: dict) -> tuple[bool, str]:
    public_root = find_public_root(repo)
    if not public_root:
        return False, "no public-root directory found"
    target = public_root / "llms.txt"
    if target.exists():
        return False, f"already exists at {target.relative_to(repo)}; not overwriting"
    template = SKILL_DIR / "templates" / "llms.txt"
    content = template.read_text(encoding="utf-8")
    canonical = config.get("canonical_origin", "https://example.com")
    content = content.replace("<CANONICAL_ORIGIN>", canonical)
    content = content.replace("<SITE_NAME>", config.get("site_name", "Site"))
    target.write_text(content, encoding="utf-8")
    return True, f"created {target.relative_to(repo)} (template — fill pillar sections manually)"


def fix_create_llms_full_txt(repo: Path, config: dict, finding: dict) -> tuple[bool, str]:
    public_root = find_public_root(repo)
    if not public_root:
        return False, "no public-root directory found"
    target = public_root / "llms-full.txt"
    if target.exists():
        return False, f"already exists at {target.relative_to(repo)}; not overwriting"
    template = SKILL_DIR / "templates" / "llms-full.txt"
    content = template.read_text(encoding="utf-8")
    canonical = config.get("canonical_origin", "https://example.com")
    content = content.replace("<CANONICAL_ORIGIN>", canonical)
    content = content.replace("<SITE_NAME>", config.get("site_name", "Site"))
    target.write_text(content, encoding="utf-8")
    return True, f"created {target.relative_to(repo)} (template — populate anchor pieces manually)"


def fix_create_vercel_headers(repo: Path, config: dict, finding: dict) -> tuple[bool, str]:
    target = repo / "vercel.json"
    template = SKILL_DIR / "templates" / "vercel-headers.json.example"
    if target.exists():
        # Merge: load existing, add headers if absent
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, "existing vercel.json malformed; manual review required"
        template_cfg = json.loads(template.read_text(encoding="utf-8"))
        # Merge headers conservatively: only add if no rule with same source exists
        existing_headers = existing.get("headers", [])
        existing_sources = {h.get("source") for h in existing_headers}
        added = 0
        for new_rule in template_cfg.get("headers", []):
            if new_rule.get("source") not in existing_sources:
                existing_headers.append(new_rule)
                added += 1
        if added:
            existing["headers"] = existing_headers
            target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            return True, f"added {added} header rule(s) to existing vercel.json"
        return False, "vercel.json already has rules at the target sources"
    # No existing vercel.json — drop the template
    content = template.read_text(encoding="utf-8")
    target.write_text(content, encoding="utf-8")
    return True, f"created {target.relative_to(repo)} from template"


def fix_indexnow_keyfile(repo: Path, config: dict, finding: dict) -> tuple[bool, str]:
    """Generate a UUID-style key file at public root."""
    import uuid
    public_root = find_public_root(repo)
    if not public_root:
        return False, "no public-root directory found"
    # Check if any existing key file
    for p in public_root.iterdir():
        if p.is_file() and p.suffix == ".txt":
            stem = p.stem
            if re.match(r"^[a-f0-9]{32}$|^[a-zA-Z0-9-]{16,128}$", stem):
                content = p.read_text(encoding="utf-8").strip()
                if content == stem:
                    return False, f"IndexNow key already present at {p.name}"
    # Generate new key
    key = uuid.uuid4().hex
    target = public_root / f"{key}.txt"
    target.write_text(key, encoding="utf-8")
    return True, f"generated IndexNow key file {target.relative_to(repo)}; store {key!r} as INDEXNOW_KEY env var"


# Map finding-id PATTERN → fix function
SAFE_FIX_REGISTRY = [
    (re.compile(r"^1\.2\.robots\.missing$"), fix_create_robots_txt),
    (re.compile(r"^3\.1\.missing$"), fix_create_robots_txt),
    (re.compile(r"^3\.5\.llms_txt$"), fix_create_llms_txt),
    (re.compile(r"^3\.6\.llms_full_txt$"), fix_create_llms_full_txt),
    (re.compile(r"^1\.1\.(Strict-Transport-Security|X-Content-Type-Options|Content-Security-Policy|Referrer-Policy|Permissions-Policy)$"), fix_create_vercel_headers),
    (re.compile(r"^6\.1\.keyfile$"), fix_indexnow_keyfile),
]


def find_fix(finding_id: str):
    for pattern, fn in SAFE_FIX_REGISTRY:
        if pattern.match(finding_id):
            return fn
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--dry-run", action="store_true", help="Report what would be applied; do not modify files.")
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    config = load_config(args.config)
    report_path = repo / ".launch-readiness-report.json"
    if not report_path.exists():
        print(f"ERROR: {report_path} not found. Run audit.sh first.", file=sys.stderr)
        return 2

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed report JSON: {e}", file=sys.stderr)
        return 2

    applied = 0
    skipped = 0
    no_recipe = 0
    print(f"apply-safe-fixes: scanning {sum(len(check.get('findings', [])) for check in report)} findings...")

    for check in report:
        check_name = check.get("check", "?")
        for finding in check.get("findings", []):
            if finding.get("fix_safety") != "safe":
                continue
            if finding.get("severity") not in ("WARN", "FAIL"):
                continue
            fix_fn = find_fix(finding["id"])
            if not fix_fn:
                no_recipe += 1
                continue

            if args.dry_run:
                print(f"  [dry-run] {check_name} :: {finding['id']} — would apply {fix_fn.__name__}")
                continue

            try:
                ok, msg = fix_fn(repo, config, finding)
                if ok:
                    applied += 1
                    print(f"  ✓ {check_name} :: {finding['id']} — {msg}")
                else:
                    skipped += 1
                    print(f"  · {check_name} :: {finding['id']} — skipped: {msg}")
            except Exception as e:
                print(f"  ✗ {check_name} :: {finding['id']} — error: {e}", file=sys.stderr)

    print(f"\nSummary: {applied} applied, {skipped} skipped (already-present), "
          f"{no_recipe} no recipe (manual-only).")
    if args.dry_run:
        print("(dry-run; no files written)")
    return 0 if applied or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
