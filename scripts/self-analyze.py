#!/usr/bin/env python3
"""
Self-analyze pass — IEO-launch-audit v1.5, Phase A of ADR 0002.

Runs after the main audit completes. Reads `.ieo-audit-state.yml` from
repo root (or detects absence = first pass), compares current-pass
findings against prior-pass findings, categorizes deltas (new, resolved,
persistent, regressed, long-running), and appends an "Operator action
since last pass" section to the audit report. Writes a new state file
at the end so the next pass has fresh context.

Per ADR 0002 Decision 1: audit-diff persistence is the primary
measurement signal — this script operationalizes it.

Per Decision 2: state file lives in consumer repo, committed by the
operator. When absent, this script emits a "first pass" advisory and
writes a fresh state file for future commits.

Per Decision 3: this is advisory output. Never auto-mutates the audit
results, the audit-report findings, or the skill itself.

Read-only when state file is absent. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import (
    State, StateFinding, load_state, write_state, build_state_from_results,
)


PROBLEM_SEVERITIES = ("WARN", "FAIL")


def _is_problem(severity: str) -> bool:
    return severity in PROBLEM_SEVERITIES


def categorize_findings(
    current_results: list[dict],
    prior: State | None,
) -> dict:
    """Categorize current findings against prior state.

    Returns dict with keys:
    - new:        list[str]            problem-severity findings in current pass; absent in prior
    - resolved:   list[str]            problem-severity in prior; absent OR PASS-ish in current
    - persistent: list[str]            problem-severity in both passes
    - regressed:  list[str]            problem-severity in current; PASS-ish in prior
    - long_open:  list[tuple[str,int]] persistent findings open ≥3 passes (id, pass_count)
    """
    current_map: dict[str, str] = {}  # id -> severity
    for check_result in current_results:
        if not isinstance(check_result, dict):
            continue
        for f in check_result.get("findings", []) or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            if not fid:
                continue
            current_map[str(fid)] = str(f.get("severity", ""))

    prior_severity_map: dict[str, str] = {}
    prior_pass_counts: dict[str, int] = {}
    if prior is not None:
        for f in prior.findings:
            prior_severity_map[f.id] = f.severity
            prior_pass_counts[f.id] = f.pass_count

    new: list[str] = []
    resolved: list[str] = []
    persistent: list[str] = []
    regressed: list[str] = []
    long_open: list[tuple[str, int]] = []

    for fid, sev in current_map.items():
        if fid not in prior_severity_map:
            if _is_problem(sev):
                new.append(fid)
            continue
        prior_sev = prior_severity_map[fid]
        if _is_problem(prior_sev) and not _is_problem(sev):
            resolved.append(fid)
        elif _is_problem(sev) and not _is_problem(prior_sev):
            regressed.append(fid)
        elif _is_problem(sev) and _is_problem(prior_sev):
            persistent.append(fid)
            count_now = prior_pass_counts.get(fid, 0) + 1
            if count_now >= 3:
                long_open.append((fid, count_now))

    # Findings that DROPPED OUT entirely (in prior, absent in current).
    # Typically "fixed + no longer flagged at all" — count as resolved when
    # the prior severity was a problem.
    for fid, prior_sev in prior_severity_map.items():
        if fid not in current_map and _is_problem(prior_sev):
            resolved.append(fid)

    return {
        "new": new,
        "resolved": resolved,
        "persistent": persistent,
        "regressed": regressed,
        "long_open": long_open,
    }


def emit_report_section(
    categories: dict,
    prior: State | None,
    current_state: State,
) -> str:
    """Generate the markdown section to append to the audit report."""
    lines: list[str] = []
    lines.append("")
    lines.append("## Operator action since last pass")
    lines.append("")

    if prior is None:
        lines.append("**First pass — no prior state file found.**")
        lines.append("")
        lines.append(
            f"This run wrote `.ieo-audit-state.yml` to the repo root with "
            f"{len(current_state.findings)} finding records. Commit this "
            f"file to enable cross-pass operator-action tracking on the "
            f"next audit run."
        )
        lines.append("")
        lines.append(
            "_Per ADR 0002, the state file is the primary measurement "
            "substrate for the skill's self-improving architecture. The "
            "next pass will categorize each finding as: new / resolved / "
            "persistent / regressed / long-running._"
        )
        lines.append("")
        return "\n".join(lines)

    new = categories["new"]
    resolved = categories["resolved"]
    persistent = categories["persistent"]
    regressed = categories["regressed"]
    long_open = categories["long_open"]

    lines.append(f"Last pass: `{prior.last_pass_date or 'unknown'}` "
                 f"(skill `{prior.skill_version or 'unknown'}`).")
    lines.append("")
    lines.append("| Category | Count | Meaning |")
    lines.append("|---|---|---|")
    lines.append(f"| **Resolved** | {len(resolved)} | findings that became PASS or dropped out since last pass |")
    lines.append(f"| **Regressed** | {len(regressed)} | findings that became WARN/FAIL after being PASS last pass |")
    lines.append(f"| **Persistent** | {len(persistent)} | findings still WARN/FAIL in both passes |")
    lines.append(f"| **New** | {len(new)} | WARN/FAIL findings present this pass but not last |")
    lines.append("")

    if resolved:
        lines.append("### Resolved (operator action observed)")
        lines.append("")
        for fid in sorted(set(resolved))[:15]:
            lines.append(f"- `{fid}`")
        if len(set(resolved)) > 15:
            lines.append(f"- … and {len(set(resolved)) - 15} more.")
        lines.append("")

    if regressed:
        lines.append("### Regressed (was PASS, now WARN/FAIL)")
        lines.append("")
        for fid in sorted(regressed)[:15]:
            lines.append(f"- `{fid}`")
        if len(regressed) > 15:
            lines.append(f"- … and {len(regressed) - 15} more.")
        lines.append("")
        lines.append(
            "Regressions warrant investigation: a finding flipped from "
            "PASS to WARN/FAIL since the last pass. Common causes: a "
            "content edit reintroduced a flagged pattern, a config "
            "change weakened a previously-enforced rule, or a build-"
            "pipeline change stripped metadata."
        )
        lines.append("")

    if long_open:
        lines.append("### Long-running problems (≥3 passes open)")
        lines.append("")
        for fid, count in sorted(long_open, key=lambda x: (-x[1], x[0]))[:15]:
            lines.append(f"- `{fid}` (open {count} passes)")
        if len(long_open) > 15:
            lines.append(f"- … and {len(long_open) - 15} more.")
        lines.append("")
        lines.append(
            "Long-open findings either represent intentional acceptance "
            "or genuinely-stuck work. Consider documenting acceptance in "
            "`.launch-readiness.yml` to suppress them, OR addressing the "
            "underlying issue."
        )
        lines.append("")

    if new:
        lines.append("### New findings this pass")
        lines.append("")
        for fid in sorted(new)[:15]:
            lines.append(f"- `{fid}`")
        if len(new) > 15:
            lines.append(f"- … and {len(new) - 15} more.")
        lines.append("")

    if not (resolved or regressed or long_open or new):
        lines.append("No category-shifts since last pass. Audit posture stable.")
        lines.append("")

    return "\n".join(lines)


def run(args) -> int:
    repo = Path(args.repo)
    report_json_path = Path(args.report_json)
    report_md_path = Path(args.report_md)
    skill_version = args.skill_version

    if not report_json_path.exists():
        print(
            f"self-analyze: audit JSON report not found at {report_json_path}; "
            f"skipping self-analyze pass.",
            file=sys.stderr,
        )
        return 0

    try:
        results = json.loads(report_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"self-analyze: could not read {report_json_path}: {e}", file=sys.stderr)
        return 0

    if not isinstance(results, list):
        # Audit report shape changed; degrade rather than crash.
        results = []

    prior = load_state(repo)
    categories = categorize_findings(results, prior)
    new_state = build_state_from_results(skill_version, results, prior)

    try:
        write_state(repo, new_state)
    except OSError as e:
        print(f"self-analyze: could not write state file: {e}", file=sys.stderr)
        # Continue — report section still useful even if state write failed.

    section = emit_report_section(categories, prior, new_state)

    if report_md_path.exists():
        try:
            with report_md_path.open("a", encoding="utf-8") as f:
                f.write(section)
        except OSError as e:
            print(f"self-analyze: could not append to {report_md_path}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="IEO-launch-audit Phase A self-analyze (ADR 0002)",
    )
    parser.add_argument("--repo", required=True, help="Repo root path")
    parser.add_argument("--report-json", required=True, help="Path to audit JSON report")
    parser.add_argument("--report-md", required=True, help="Path to audit MD report")
    parser.add_argument("--skill-version", required=True, help="Current skill version")
    args = parser.parse_args()
    sys.exit(run(args))
