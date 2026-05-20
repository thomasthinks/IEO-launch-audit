#!/usr/bin/env python3
"""
inspect-state.py — operator UX for the IEO-launch-audit state file (v1.6.1).

Reads `.ieo-audit-state.yml` from a repo root and presents a human-
readable summary of audit-history state: counts by severity, longest-
open findings, recently-resolved (if a prior pass's state is available
via git), and optional filter by finding-id.

Stdlib only. Read-only — never modifies state.

Usage:
  python3 scripts/inspect-state.py [--repo PATH] [--id PATTERN]
                                   [--long-open N] [--limit N] [--json]

Examples:
  python3 scripts/inspect-state.py
  python3 scripts/inspect-state.py --long-open 5
  python3 scripts/inspect-state.py --id '14\\.'
  python3 scripts/inspect-state.py --json | jq '.findings[] | select(.pass_count >= 3)'
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import State, StateFinding, load_state


PROBLEM_SEVERITIES = {"WARN", "FAIL"}


def _format_age(timestamp: str) -> str:
    """Render a relative-age string for an ISO timestamp. Tolerant of
    malformed input."""
    if not timestamp:
        return "unknown"
    try:
        from datetime import datetime, timezone
        ts = timestamp.rstrip("Z")
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        days = int(delta.total_seconds() / 86400)
        if days <= 0:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}h ago" if hours > 0 else "now"
        if days == 1:
            return "1 day ago"
        if days < 14:
            return f"{days} days ago"
        if days < 60:
            weeks = days // 7
            return f"{weeks} weeks ago"
        if days < 730:
            months = days // 30
            return f"{months} months ago"
        years = days // 365
        return f"{years} years ago"
    except (ValueError, TypeError):
        return timestamp


def summarize(state: State) -> dict:
    by_severity: dict[str, int] = {}
    for f in state.findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
    problem_findings = [f for f in state.findings if f.severity in PROBLEM_SEVERITIES]
    long_open = sorted(
        problem_findings,
        key=lambda f: (-f.pass_count, f.first_seen),
    )
    return {
        "skill_version": state.skill_version,
        "last_pass_date": state.last_pass_date,
        "last_pass_age": _format_age(state.last_pass_date),
        "total_findings": len(state.findings),
        "by_severity": by_severity,
        "problem_count": len(problem_findings),
        "long_open": long_open,
    }


def emit_text_summary(summary: dict, state: State, filter_re: re.Pattern | None,
                      long_open_n: int, limit: int) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("IEO-launch-audit — state file summary")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Skill version (last pass): {summary['skill_version'] or 'unknown'}")
    lines.append(f"Last pass date:            {summary['last_pass_date'] or 'unknown'} "
                 f"({summary['last_pass_age']})")
    lines.append(f"Total findings tracked:    {summary['total_findings']}")
    lines.append("")

    lines.append("Findings by severity:")
    severity_order = ["FAIL", "WARN", "MANUAL_VERIFY", "INFO", "PASS", "NOT_APPLICABLE"]
    bs = summary["by_severity"]
    for sev in severity_order:
        if sev in bs:
            marker = "⚠ " if sev in PROBLEM_SEVERITIES else "  "
            lines.append(f"  {marker}{sev:<16} {bs[sev]}")
    # Catch unknown severities not in canonical order.
    for sev, n in bs.items():
        if sev not in severity_order:
            lines.append(f"    {sev:<16} {n}")
    lines.append("")

    if summary["problem_count"] > 0:
        lines.append(f"Top {min(long_open_n, len(summary['long_open']))} longest-open "
                     f"WARN/FAIL findings (by pass_count desc):")
        lines.append("")
        for f in summary["long_open"][:long_open_n]:
            lines.append(
                f"  [{f.severity:<5}] {f.id}"
            )
            lines.append(
                f"          {f.title[:90]}"
                + ("..." if len(f.title) > 90 else "")
            )
            lines.append(
                f"          open {f.pass_count} pass{'es' if f.pass_count != 1 else ''}; "
                f"first seen {_format_age(f.first_seen)}, last seen {_format_age(f.last_seen)}"
            )
            lines.append("")
    else:
        lines.append("No WARN/FAIL findings currently tracked. Audit posture clean.")
        lines.append("")

    if filter_re is not None:
        filtered = [f for f in state.findings if filter_re.search(f.id)]
        lines.append(f"Findings matching pattern (showing {min(len(filtered), limit)}):")
        lines.append("")
        for f in filtered[:limit]:
            lines.append(
                f"  [{f.severity:<5}] {f.id} (pass_count={f.pass_count})"
            )
            lines.append(f"          {f.title[:90]}")
            lines.append(f"          first {_format_age(f.first_seen)} / last {_format_age(f.last_seen)}")
            lines.append("")
        if len(filtered) > limit:
            lines.append(f"  ... and {len(filtered) - limit} more match. Pass --limit to widen.")
            lines.append("")

    lines.append("=" * 60)
    lines.append("State file is consumer-side; commit `.ieo-audit-state.yml` to track")
    lines.append("audit history across passes. See ADR 0002 for the contract.")
    lines.append("=" * 60)
    return "\n".join(lines)


def emit_json(state: State) -> str:
    out: dict[str, Any] = {
        "state_version": state.state_version,
        "skill_version": state.skill_version,
        "last_pass_date": state.last_pass_date,
        "findings": [
            {
                "id": f.id,
                "severity": f.severity,
                "title": f.title,
                "first_seen": f.first_seen,
                "last_seen": f.last_seen,
                "pass_count": f.pass_count,
            }
            for f in state.findings
        ],
    }
    return json.dumps(out, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect IEO-launch-audit state file. Reads "
            "`.ieo-audit-state.yml` from --repo and prints a human-"
            "readable summary."
        ),
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repo root containing `.ieo-audit-state.yml` (default: current dir).",
    )
    parser.add_argument(
        "--id",
        metavar="REGEX",
        default=None,
        help=(
            "Filter findings by id regex (e.g. '14\\.' to show all check-14 findings). "
            "Case-sensitive."
        ),
    )
    parser.add_argument(
        "--long-open",
        type=int,
        default=10,
        metavar="N",
        help="Number of longest-open WARN/FAIL findings to show (default: 10).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Max findings to print under --id filter (default: 20).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw state as JSON instead of human-readable summary.",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    state = load_state(repo)
    if state is None:
        print(
            f"No state file found at {repo}/.ieo-audit-state.yml. "
            f"Run an audit pass first; it will write the state file on completion.",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(emit_json(state))
        return 0

    filter_re = None
    if args.id:
        try:
            filter_re = re.compile(args.id)
        except re.error as e:
            print(f"Invalid --id regex: {e}", file=sys.stderr)
            return 2

    summary = summarize(state)
    print(emit_text_summary(summary, state, filter_re, args.long_open, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
