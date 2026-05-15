#!/usr/bin/env python3
"""crux-trend.py — append CrUX field-metric snapshots to a trend CSV.

v1.2 monitoring helper. Each audit run that has PSI/CrUX configured (check 4)
emits a `4.crux.summary` INFO finding + six `4.crux.<scope>_<metric>` graded
findings. This helper extracts the p75 + category for each (scope, metric)
pair from the JSON report and appends one row to a long-running CSV so the
operator can see CrUX direction over weeks/months without re-running PSI
calls.

Stdlib-only. Repo-portable. Runs in seconds.

Usage:
    python3 .../scripts/crux-trend.py [--report PATH] [--out PATH] [--summary]

Defaults:
    --report   .launch-readiness-report.json in $PWD
    --out      .launch-readiness-crux-trend.csv in $PWD
    --summary  Print a tail-N + direction-arrow trend summary after appending.
               Implied when the CSV already has ≥2 rows; flag forces it on
               first-run too (when there's nothing to compare yet).

Tradeoffs:
    The audit emits a snapshot per run; this helper materialises the
    time series. Trend interpretation belongs to the operator — the
    helper reports raw direction, not "your site got worse." See
    web.dev/vitals for category thresholds (LCP 2500ms / CLS 0.1 /
    INP 200ms at p75 separate FAST from AVERAGE).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# CrUX finding IDs the helper extracts. Order is the CSV column order.
CRUX_KEYS = [
    ("page", "lcp"),
    ("page", "cls"),
    ("page", "inp"),
    ("origin", "lcp"),
    ("origin", "cls"),
    ("origin", "inp"),
]

CSV_HEADER = (
    ["timestamp_utc", "report_path"]
    + [f"{scope}_{metric}_{field}"
       for (scope, metric) in CRUX_KEYS
       for field in ("p75", "category")]
)

# Higher = worse. Used to decide direction (improve/regress) when the
# category changes between adjacent rows.
CATEGORY_ORDER = {"FAST": 0, "AVERAGE": 1, "SLOW": 2}

# Direction arrows. The category dimension uses absolute direction
# (improve vs regress); the p75 dimension uses ↘/↗ for "down by N%"
# and "up by N%" respectively. INP/LCP improving = p75 going DOWN
# (faster); CLS improving = p75 going DOWN (less shift); for all three
# metrics, lower p75 = better.
ARROW_DOWN, ARROW_UP, ARROW_FLAT = "↘", "↗", "→"


def extract_crux_row(report: list[dict], report_path: Path) -> dict:
    """Pull the per-(scope, metric) p75 + category out of a report JSON.

    Tolerates missing scopes / metrics — when a key isn't found, both
    fields are written as "" so the CSV row is still well-formed.
    """
    # Findings are nested per check; check 4 carries the 4.crux.* family.
    findings_by_id: dict[str, dict] = {}
    for check in report:
        if check.get("check", "").startswith("04-") or check.get("check") == "04-performance":
            for f in check.get("findings", []) or []:
                fid = f.get("id", "")
                if fid.startswith("4.crux."):
                    findings_by_id[fid] = f
    row = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "report_path": str(report_path),
    }
    for (scope, metric) in CRUX_KEYS:
        fid = f"4.crux.{scope}_{metric}"
        f = findings_by_id.get(fid)
        if not f:
            row[f"{scope}_{metric}_p75"] = ""
            row[f"{scope}_{metric}_category"] = ""
            continue
        cur = f.get("current") or {}
        # `current` may be a dict ({"category": ..., "percentile": ...})
        # or a string fallback for NOT_APPLICABLE. Tolerate both.
        if isinstance(cur, dict):
            row[f"{scope}_{metric}_p75"] = cur.get("percentile") if cur.get("percentile") is not None else ""
            row[f"{scope}_{metric}_category"] = cur.get("category") or ""
        else:
            row[f"{scope}_{metric}_p75"] = ""
            row[f"{scope}_{metric}_category"] = ""
    return row


def append_row(csv_path: Path, row: dict) -> bool:
    """Append a row to the trend CSV, creating the file with header if
    it doesn't exist. Returns True if the file was newly created."""
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return new_file


def _direction(prior: str, current: str) -> str:
    """Compare two p75 values (numeric strings) and return an arrow.
    Empty values → flat. Numeric drift < 5% → flat, else up/down arrows."""
    try:
        p, c = float(prior), float(current)
    except (TypeError, ValueError):
        return ARROW_FLAT
    if p == 0:
        return ARROW_FLAT
    delta = (c - p) / p
    if abs(delta) < 0.05:  # <5% noise floor
        return ARROW_FLAT
    return ARROW_DOWN if delta < 0 else ARROW_UP  # lower p75 = better; ↘ means improve


def _category_marker(prior: str, current: str) -> str:
    """FAST/AVERAGE/SLOW → improve/regress/unchanged marker."""
    pi, ci = CATEGORY_ORDER.get(prior, -1), CATEGORY_ORDER.get(current, -1)
    if pi < 0 or ci < 0:
        return ""
    if ci < pi:
        return "(improve)"
    if ci > pi:
        return "(regress)"
    return ""


def emit_summary(csv_path: Path, tail_n: int = 5) -> None:
    """Print a tail-N table of the trend CSV plus a direction row.

    Direction row compares the latest row against the prior row using
    p75 delta and category change. If only one row exists, the
    direction row is "(baseline)"."""
    if not csv_path.exists():
        print(f"crux-trend: no trend CSV at {csv_path}; nothing to summarise.", file=sys.stderr)
        return
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("crux-trend: trend CSV is empty.", file=sys.stderr)
        return

    print(f"\n# CrUX trend — {csv_path.name}  (last {min(tail_n, len(rows))} of {len(rows)} runs)\n")
    tail = rows[-tail_n:]
    cols = [(s, m, f"{s}_{m}") for (s, m) in CRUX_KEYS]
    header = ["timestamp_utc"] + [f"{s}_{m}_p75/cat" for (s, m, _k) in cols]
    print("  " + " | ".join(header))
    print("  " + " | ".join("-" * len(h) for h in header))
    for r in tail:
        cells = [r.get("timestamp_utc", "?")[:19]]
        for (_s, _m, key) in cols:
            p75 = r.get(f"{key}_p75", "") or "-"
            cat = r.get(f"{key}_category", "") or "-"
            cells.append(f"{p75}/{cat}")
        print("  " + " | ".join(cells))
    print()

    # Direction row: compare last vs previous row when ≥2 rows present.
    if len(rows) >= 2:
        prior, current = rows[-2], rows[-1]
        print("## Direction (latest vs prior)")
        for (scope, metric) in CRUX_KEYS:
            key = f"{scope}_{metric}"
            arrow = _direction(prior.get(f"{key}_p75", ""), current.get(f"{key}_p75", ""))
            marker = _category_marker(
                prior.get(f"{key}_category", ""),
                current.get(f"{key}_category", ""),
            )
            label = f"  {scope:<6} {metric.upper():<3}"
            print(f"{label}  {arrow}  {marker}")
        print(
            "\nLegend: ↘ p75 dropped ≥5% (improving), ↗ rose ≥5% (regressing), "
            "→ within ±5% noise. (improve)/(regress) flag category changes "
            "across FAST/AVERAGE/SLOW thresholds."
        )
    else:
        print("## Direction\n  (baseline — only one row; trend visible after the next run.)")
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Append/summarise CrUX field-metric trends from an audit report.")
    p.add_argument("--report", default=".launch-readiness-report.json",
                   help="Path to audit report JSON (default: .launch-readiness-report.json in $PWD)")
    p.add_argument("--out", default=".launch-readiness-crux-trend.csv",
                   help="Path to trend CSV (default: .launch-readiness-crux-trend.csv in $PWD)")
    p.add_argument("--summary", action="store_true",
                   help="Always emit summary (default: only when CSV has ≥2 rows)")
    p.add_argument("--summary-only", action="store_true",
                   help="Don't read or append the report; just emit the summary from the existing CSV.")
    args = p.parse_args(argv)

    csv_path = Path(args.out)

    if args.summary_only:
        emit_summary(csv_path)
        return 0

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"crux-trend: report not found: {report_path}", file=sys.stderr)
        return 2
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"crux-trend: report JSON malformed: {e}", file=sys.stderr)
        return 2
    if not isinstance(report, list):
        print(f"crux-trend: report should be a JSON array of checks; got {type(report).__name__}", file=sys.stderr)
        return 2

    row = extract_crux_row(report, report_path)
    new_file = append_row(csv_path, row)

    if new_file:
        print(f"crux-trend: created {csv_path} (1 row).", file=sys.stderr)
    else:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            n = sum(1 for _ in csv.reader(fh)) - 1  # minus header
        print(f"crux-trend: appended to {csv_path} ({n} rows total).", file=sys.stderr)

    # Skip summary on first-ever run unless explicitly requested.
    if args.summary or not new_file:
        emit_summary(csv_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
