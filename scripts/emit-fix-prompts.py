#!/usr/bin/env python3
"""
Emit copy-paste LLM remediation prompts from an audit report (ADR 0004).

Reads `.launch-readiness-report.json` (the array of CheckResult objects
audit.sh assembles) and writes `.launch-readiness-fixes.md`: one
ready-to-paste prompt per actionable finding (severity WARN or FAIL with
a fix_action), ordered FAIL-first. Presentation only — no new detection
logic; the prompt text is the finding's own fix_action + context.

Usage:
    python3 scripts/emit-fix-prompts.py --repo <consumer-repo-root>
    python3 scripts/emit-fix-prompts.py --report <path.json> --out <path.md>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ACTIONABLE = ("FAIL", "WARN")


def build_prompt(check: str, finding: dict) -> str:
    lines = [
        f"Fix the following {finding['severity']} finding from an "
        f"IEO-launch-audit run (check {check}, finding {finding['id']}):",
        "",
        f"Finding: {finding['title']}",
    ]
    if finding.get("current") is not None:
        lines.append(f"Current state: {json.dumps(finding['current'], default=str)}")
    if finding.get("expected") is not None:
        lines.append(f"Expected: {json.dumps(finding['expected'], default=str)}")
    lines.append(f"Fix: {finding['fix_action']}")
    if finding.get("fix_template"):
        lines.append(f"Template to start from (in the IEO-launch-audit skill repo): {finding['fix_template']}")
    if finding.get("notes"):
        lines.append(f"Context: {finding['notes']}")
    lines += [
        "",
        "Make the minimal change that resolves the finding. Do not touch "
        "unrelated files. After changing, state which files you edited and why.",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="IEO-launch-audit: findings -> remediation prompts")
    p.add_argument("--repo", help="Consumer repo root (report + output default here)")
    p.add_argument("--report", help="Report JSON path (default: <repo>/.launch-readiness-report.json)")
    p.add_argument("--out", help="Output MD path (default: <repo>/.launch-readiness-fixes.md)")
    args = p.parse_args()

    if not args.repo and not args.report:
        p.error("need --repo or --report")
    repo = Path(args.repo) if args.repo else Path.cwd()
    report_path = Path(args.report) if args.report else repo / ".launch-readiness-report.json"
    out_path = Path(args.out) if args.out else repo / ".launch-readiness-fixes.md"

    if not report_path.exists():
        print(f"No report at {report_path} — run audit.sh first.", file=sys.stderr)
        return 1
    try:
        checks = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Report is not valid JSON ({e}) — re-run audit.sh.", file=sys.stderr)
        return 1

    items: list[tuple[str, dict]] = []
    for c in checks:
        for f in c.get("findings", []):
            if f.get("severity") in ACTIONABLE and f.get("fix_action"):
                items.append((c.get("check", "?"), f))
    items.sort(key=lambda cf: (cf[1]["severity"] != "FAIL", cf[0], cf[1]["id"]))

    out = [
        "# Remediation prompts",
        "",
        f"Generated from `{report_path.name}`. One copy-paste prompt per "
        "actionable finding (FAIL first). Paste a block into Claude Code / "
        "Cursor in the consumer repo; each prompt is self-contained.",
        "",
    ]
    if not items:
        out.append("_No actionable WARN/FAIL findings with a fix_action — nothing to remediate._")
    for check, f in items:
        out += [
            f"## {f['severity']} · {f['id']}",
            "",
            "```text",
            build_prompt(check, f),
            "```",
            "",
        ]
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} prompt(s) to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
