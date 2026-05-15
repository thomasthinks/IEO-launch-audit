#!/usr/bin/env python3
"""
Check 06 — IndexNow setup.

Looks for a UUID-style <key>.txt file at the public root and greps the
publish pipeline for the IndexNow API endpoint.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


KEY_PATTERN = re.compile(r"^[a-f0-9]{32}$|^[a-zA-Z0-9-]{16,128}$")
PUBLIC_ROOTS = ["dist/public", "public", "out", "_site", "build", "static"]


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="06-indexnow")

    # 6.1 — Key file presence
    key_found = None
    for root in PUBLIC_ROOTS:
        d = repo / root
        if not d.exists():
            continue
        for p in d.iterdir():
            if p.is_file() and p.suffix == ".txt" and KEY_PATTERN.match(p.stem):
                # Verify file contents match filename
                content = p.read_text(encoding="utf-8").strip()
                if content == p.stem:
                    key_found = p
                    break
        if key_found:
            break

    if key_found:
        result.findings.append(Finding(
            id="6.1.keyfile", severity="PASS",
            title=f"IndexNow key file found: {key_found.relative_to(repo)}",
            current=key_found.stem,
        ))
    else:
        result.findings.append(Finding(
            id="6.1.keyfile", severity="WARN",
            title="No IndexNow key file (<32-char>.txt with self-matching content) found in public roots",
            fix_safety="safe",
            fix_action="Generate a key: `KEY=$(uuidgen | tr 'A-Z' 'a-z' | tr -d '-')`; "
                       "write to dist/public/$KEY.txt with $KEY as contents.",
        ))

    # 6.2 — Publish-hook grep.
    #
    # Signal: the substring "api.indexnow.org" (or "indexnow.org/indexnow")
    # in any file under scripts/ or docs/runbooks/, or in Makefile or
    # .github/workflows/. Filename-agnostic on purpose -- consumer repos
    # name the publish script whatever they want; what matters is that a
    # callable that POSTs to IndexNow exists AND a runbook references it.
    publish_surfaces = [
        repo / "scripts",
        repo / "docs" / "runbooks",
        repo / "Makefile",
        repo / ".github" / "workflows",
    ]
    needle = "api.indexnow.org"
    found_in: list[str] = []
    for p in publish_surfaces:
        if not p.exists():
            continue
        if p.is_dir():
            for f in p.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix not in {".py", ".sh", ".ts", ".js", ".md", ".yml", ".yaml", ""}:
                    continue
                try:
                    if needle in f.read_text(encoding="utf-8", errors="ignore").lower():
                        found_in.append(str(f.relative_to(repo)))
                except Exception:
                    continue
        else:
            try:
                if needle in p.read_text(encoding="utf-8", errors="ignore").lower():
                    found_in.append(str(p.relative_to(repo)))
            except Exception:
                continue

    if found_in:
        result.findings.append(Finding(
            id="6.2.hook", severity="PASS",
            title=f"IndexNow publish reference found: {found_in}",
        ))
    else:
        result.findings.append(Finding(
            id="6.2.hook", severity="WARN",
            title="No IndexNow reference in publish pipeline",
            fix_safety="manual",
            fix_action="Wire a POST to https://api.indexnow.org/indexnow on publish "
                       "(see checks/06-indexnow.md § Fix 6.2).",
        ))

    result.summary = (
        f"IndexNow: key file {'present' if key_found else 'missing'}; "
        f"publish hook {'present' if found_in else 'missing'}."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("06-indexnow")
    args = parser.parse_args()
    emit(run(args))
