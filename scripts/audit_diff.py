#!/usr/bin/env python3
"""audit_diff.py — incremental diff between two launch-readiness audit reports.

Reads two JSON reports (current + prior) and emits a markdown summary of
WHAT CHANGED between the runs:

- Severity-count deltas (headline + table)
- New findings (present in current, absent in prior) — grouped by check
- Resolved findings (present in prior, absent in current) — grouped by check
- Severity-changed findings (same id, different severity)
- Content-changed findings (same id + severity, but title/notes/current/
  expected text drifted)

Findings are matched across runs by the (check, id) tuple. Output is
optimised for triage: regressions surface first (FAIL/WARN news), then
wins (resolved), then drift (severity + content changes).

PASS findings are noisy in the "new" bucket on first-run-of-a-new-check
diffs (e.g. a freshly-added check 11 dumps 17 PASS rows). They're
collapsed to a single line per check by default; pass --verbose-pass to
see each id.

Stdlib only. Repo-portable.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# Severity ordering for display + delta-sign convention.
# "Higher" = worse; resolving WARN -> PASS is "improvement".
SEVERITY_ORDER = ["FAIL", "WARN", "MANUAL_VERIFY", "INFO", "PASS"]
SEVERITY_SHORT = {"MANUAL_VERIFY": "MV"}

# Fields whose value-drift counts as a "content change" when severity is
# unchanged. title is the human-readable headline; notes/current/expected
# carry the diagnostic payload.
CONTENT_FIELDS = ("title", "notes", "current", "expected")


def load_report(path: Path) -> list[dict]:
    """Load a JSON report. Returns the list of check objects."""
    with path.open() as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at top level of {path}, got {type(data).__name__}")
    return data


def extract_findings(report: list[dict]) -> dict[tuple[str, str], dict]:
    """Flatten a report to a {(check, finding_id): finding_with_check} map."""
    out: dict[tuple[str, str], dict] = {}
    for check in report:
        check_name = check.get("check", "unknown")
        for finding in check.get("findings", []) or []:
            fid = finding.get("id")
            if not fid:
                continue
            key = (check_name, fid)
            enriched = dict(finding)
            enriched["_check"] = check_name
            out[key] = enriched
    return out


def severity_counts(findings: dict[tuple[str, str], dict]) -> dict[str, int]:
    counts: dict[str, int] = {sev: 0 for sev in SEVERITY_ORDER}
    for f in findings.values():
        sev = f.get("severity", "UNKNOWN")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def fmt_delta(delta: int) -> str:
    """Sign-aware delta string using a proper U+2212 minus for negatives."""
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return f"−{abs(delta)}"  # U+2212 MINUS SIGN
    return "0"


def fmt_severity(sev: str) -> str:
    return SEVERITY_SHORT.get(sev, sev)


def _trend_phrase(label: str, prior_n: int, cur_n: int) -> str | None:
    """Format one severity-trend phrase, e.g. 'FAIL 0 (unchanged)' or 'WARN 6 -> 4 (-2)'.

    Returns None when the severity is zero on both sides (skip noise).
    """
    if prior_n == 0 and cur_n == 0:
        return None
    delta = cur_n - prior_n
    if delta == 0:
        return f"{label} {cur_n} (unchanged)"
    return f"{label} {prior_n} → {cur_n} ({fmt_delta(delta)})"


def group_by_check(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        check = item.get("_check", "unknown")
        grouped.setdefault(check, []).append(item)
    return grouped


def format_finding_line(f: dict, *, with_check: bool = False) -> str:
    fid = f.get("id", "?")
    sev = fmt_severity(f.get("severity", "?"))
    title = (f.get("title") or f.get("notes") or "").strip()
    prefix = f"[{f.get('_check', '?')}] " if with_check else ""
    if title:
        return f"- {prefix}{fid} {sev}: {title}"
    return f"- {prefix}{fid} {sev}"


def _content_diff(prior: dict, cur: dict) -> list[tuple[str, str, str]]:
    """Return (field, prior_value, cur_value) for each content-field that changed."""
    out: list[tuple[str, str, str]] = []
    for field in CONTENT_FIELDS:
        a, b = prior.get(field), cur.get(field)
        # Treat None and "" as equivalent absence.
        if (a or "") != (b or ""):
            out.append((field, str(a or ""), str(b or "")))
    return out


def _truncate(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def render_baseline(current_path: Path, current: dict[tuple[str, str], dict]) -> str:
    counts = severity_counts(current)
    total = sum(counts.values())
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Audit diff - {ts}",
        "",
        "## Headline",
        "",
        f"No prior report; this is the baseline. {total} findings recorded "
        f"({counts.get('FAIL', 0)} FAIL, {counts.get('WARN', 0)} WARN, "
        f"{counts.get('PASS', 0)} PASS).",
        "",
        f"Current: `{current_path}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_diff(
    current_path: Path,
    prior_path: Path,
    current: dict[tuple[str, str], dict],
    prior: dict[tuple[str, str], dict],
    *,
    verbose_pass: bool = False,
) -> str:
    cur_keys = set(current.keys())
    prior_keys = set(prior.keys())

    new_keys = cur_keys - prior_keys
    resolved_keys = prior_keys - cur_keys
    common_keys = cur_keys & prior_keys

    severity_changed: list[tuple[dict, dict]] = []
    content_changed: list[tuple[dict, dict]] = []
    for k in common_keys:
        old_sev = prior[k].get("severity")
        new_sev = current[k].get("severity")
        if old_sev != new_sev:
            severity_changed.append((prior[k], current[k]))
        else:
            diff = _content_diff(prior[k], current[k])
            if diff:
                content_changed.append((prior[k], current[k]))

    cur_counts = severity_counts(current)
    prior_counts = severity_counts(prior)
    deltas = {sev: cur_counts.get(sev, 0) - prior_counts.get(sev, 0) for sev in SEVERITY_ORDER}

    # Headline: lead with FAIL state, then WARN, then a movement summary.
    trend_bits = []
    for label in ("FAIL", "WARN"):
        phrase = _trend_phrase(label, prior_counts.get(label, 0), cur_counts.get(label, 0))
        if phrase:
            trend_bits.append(phrase)
    if not trend_bits:
        trend_bits.append("no FAIL/WARN on either side")
    trend = "; ".join(trend_bits)

    movement_bits = []
    if resolved_keys:
        movement_bits.append(f"{len(resolved_keys)} resolved")
    if new_keys:
        movement_bits.append(f"{len(new_keys)} new")
    if severity_changed:
        movement_bits.append(f"{len(severity_changed)} severity-changed")
    if content_changed:
        movement_bits.append(f"{len(content_changed)} content-changed")
    movement = ", ".join(movement_bits) if movement_bits else "no per-finding movement"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[str] = []
    out.append(f"# Audit diff - {ts}")
    out.append("")
    out.append("## Headline")
    out.append("")
    out.append(f"- {trend}.")
    out.append(f"- {movement}.")
    out.append("")
    out.append(f"- Current: `{current_path}`")
    out.append(f"- Prior:   `{prior_path}`")
    out.append("")

    # Severity counts table — skip rows that are zero on both sides.
    out.append("## Severity counts")
    out.append("")
    out.append("| Severity | Prior | Current | Delta |")
    out.append("|----------|------:|--------:|------:|")
    for sev in SEVERITY_ORDER:
        prior_n = prior_counts.get(sev, 0)
        cur_n = cur_counts.get(sev, 0)
        if prior_n == 0 and cur_n == 0:
            continue
        out.append(
            f"| {fmt_severity(sev):<8} | {prior_n:>5} | {cur_n:>7} | {fmt_delta(cur_n - prior_n):>5} |"
        )
    out.append("")

    # Resolved findings (wins) — grouped by check.
    out.append(f"## Resolved ({len(resolved_keys)})")
    out.append("")
    if resolved_keys:
        resolved = [prior[k] for k in sorted(resolved_keys)]
        for check, items in sorted(group_by_check(resolved).items()):
            out.append(f"### {check} ({len(items)})")
            out.append("")
            items.sort(key=lambda f: (SEVERITY_ORDER.index(f.get("severity", "PASS")) if f.get("severity") in SEVERITY_ORDER else 99, f.get("id", "")))
            for f in items:
                fid = f.get("id", "?")
                sev = fmt_severity(f.get("severity", "?"))
                title = (f.get("title") or "").strip()
                line = f"- {fid} {sev} → (gone)"
                if title:
                    line += f": {title}"
                out.append(line)
            out.append("")
    else:
        out.append("_None._")
        out.append("")

    # New findings — grouped by check, with severity ordering inside each.
    # PASS rows collapsed by default (noisy when a new check first lands).
    out.append(f"## New ({len(new_keys)})")
    out.append("")
    if new_keys:
        new_findings = [current[k] for k in sorted(new_keys)]
        for check, items in sorted(group_by_check(new_findings).items()):
            # Per-check severity tally for the section header.
            per_check_counts: dict[str, int] = {}
            for f in items:
                per_check_counts[f.get("severity", "?")] = per_check_counts.get(f.get("severity", "?"), 0) + 1
            tally = ", ".join(
                f"{n} {fmt_severity(sev)}"
                for sev in SEVERITY_ORDER
                if (n := per_check_counts.get(sev, 0))
            )
            out.append(f"### {check} - {tally}")
            out.append("")
            # Sort: worse severity first, then by id.
            items.sort(key=lambda f: (
                SEVERITY_ORDER.index(f.get("severity", "PASS"))
                if f.get("severity") in SEVERITY_ORDER else 99,
                f.get("id", ""),
            ))
            pass_rows: list[dict] = []
            for f in items:
                if f.get("severity") == "PASS" and not verbose_pass:
                    pass_rows.append(f)
                    continue
                out.append(format_finding_line(f))
            if pass_rows:
                # Collapse PASS rows to one summary line per check.
                ids = ", ".join(f.get("id", "?") for f in pass_rows[:6])
                more = f", +{len(pass_rows) - 6} more" if len(pass_rows) > 6 else ""
                out.append(f"- {len(pass_rows)} PASS (collapsed; --verbose-pass to expand): {ids}{more}")
            out.append("")
    else:
        out.append("_None._")
        out.append("")

    # Severity changes — flag direction with arrow.
    out.append(f"## Severity changes ({len(severity_changed)})")
    out.append("")
    if severity_changed:
        # Sort so worsening (worse-than-prior) lands first.
        def _worse_first(pair: tuple[dict, dict]) -> tuple[int, str, str]:
            p, c = pair
            old_idx = SEVERITY_ORDER.index(p.get("severity", "PASS")) if p.get("severity") in SEVERITY_ORDER else 99
            new_idx = SEVERITY_ORDER.index(c.get("severity", "PASS")) if c.get("severity") in SEVERITY_ORDER else 99
            # Worsening = new_idx < old_idx (smaller idx = worse).
            return (new_idx - old_idx, c.get("_check", ""), c.get("id", ""))

        severity_changed.sort(key=_worse_first)
        for prior_f, cur_f in severity_changed:
            check = cur_f.get("_check", "?")
            fid = cur_f.get("id", "?")
            old = fmt_severity(prior_f.get("severity", "?"))
            new = fmt_severity(cur_f.get("severity", "?"))
            old_idx = SEVERITY_ORDER.index(prior_f.get("severity", "PASS")) if prior_f.get("severity") in SEVERITY_ORDER else 99
            new_idx = SEVERITY_ORDER.index(cur_f.get("severity", "PASS")) if cur_f.get("severity") in SEVERITY_ORDER else 99
            marker = "regress" if new_idx < old_idx else "improve" if new_idx > old_idx else "shift"
            title = (cur_f.get("title") or "").strip()
            line = f"- [{check}] {fid} {old} → {new} ({marker})"
            if title:
                line += f": {title}"
            out.append(line)
        out.append("")
    else:
        out.append("_None._")
        out.append("")

    # Content changes — title/notes/current/expected drift at same severity.
    # Truncated; full payload remains in the per-run JSON.
    out.append(f"## Content changes ({len(content_changed)})")
    out.append("")
    if content_changed:
        content_changed.sort(key=lambda pair: (pair[1].get("_check", ""), pair[1].get("id", "")))
        for prior_f, cur_f in content_changed:
            check = cur_f.get("_check", "?")
            fid = cur_f.get("id", "?")
            sev = fmt_severity(cur_f.get("severity", "?"))
            out.append(f"- [{check}] {fid} {sev}")
            for field, old_val, new_val in _content_diff(prior_f, cur_f):
                out.append(f"  - {field}: `{_truncate(old_val)}` → `{_truncate(new_val)}`")
        out.append("")
    else:
        out.append("_None._")
        out.append("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diff two launch-readiness audit reports.")
    p.add_argument("--current", required=True, help="Path to current report JSON.")
    p.add_argument(
        "--prior",
        required=False,
        default=None,
        help="Path to prior report JSON. If missing or omitted, emits a baseline notice.",
    )
    p.add_argument(
        "--out",
        required=False,
        default=None,
        help="Write markdown output to this path (in addition to stdout).",
    )
    p.add_argument(
        "--verbose-pass",
        action="store_true",
        help="Expand new-PASS rows individually instead of collapsing to a single per-check line.",
    )
    args = p.parse_args(argv)

    current_path = Path(args.current)
    if not current_path.exists():
        print(f"error: current report not found: {current_path}", file=sys.stderr)
        return 2

    current = extract_findings(load_report(current_path))

    if not args.prior or not Path(args.prior).exists():
        md = render_baseline(current_path, current)
    else:
        prior_path = Path(args.prior)
        prior = extract_findings(load_report(prior_path))
        md = render_diff(current_path, prior_path, current, prior, verbose_pass=args.verbose_pass)

    sys.stdout.write(md)
    if args.out:
        Path(args.out).write_text(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
