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
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_config
from _state import (
    State, StateFinding, load_state, write_state, build_state_from_results,
)


PROBLEM_SEVERITIES = ("WARN", "FAIL")


def _is_problem(severity: str) -> bool:
    return severity in PROBLEM_SEVERITIES


# Phase B (v1.5.2): metric extraction from check 12 (GSC + Bing) findings.
# These are COMPANION signals at confidence-tier "medium" at best per
# ADR 0002 Decision 1. The skill reports correlation between operator
# action (resolved findings) and indexing-state delta; it never claims
# causation. Attribution noise is unresolvable (algo updates, seasonality,
# other operator changes the skill didn't recommend).
#
# Extracted metrics, by finding ID:
# - 12.bing.crawl_errors.current.crawl_errors_7d   (Bing crawl errors)
# - 12.bing.crawl_errors.current.crawled_pages_7d  (Bing pages crawled)
# - 12.bing.crawl_stats.current.crawled_pages_7d   (alt path when 0 errors)
# - 12.bing.indexed_vs_sitemap.current.* (title fallback for indexed_count)
# - 12.gsc.indexed_vs_sitemap.current.indexed      (GSC indexed URLs)
# - 12.gsc.indexed_vs_sitemap.current.sitemap      (sitemap URL count)
_PHASE_B_METRIC_PATHS = [
    # (metric_id, finding_id, current_field, label)
    ("bing.crawl_errors_7d", "12.bing.crawl_errors", "crawl_errors_7d",
     "Bing crawl errors (last 7d)"),
    ("bing.crawled_pages_7d", "12.bing.crawl_errors", "crawled_pages_7d",
     "Bing pages crawled (last 7d)"),
    ("bing.crawled_pages_7d", "12.bing.crawl_stats", "crawled_pages_7d",
     "Bing pages crawled (last 7d)"),
    ("gsc.indexed", "12.gsc.indexed_vs_sitemap", "indexed",
     "GSC indexed URL count"),
    ("gsc.sitemap", "12.gsc.indexed_vs_sitemap", "sitemap",
     "Sitemap URL count (declared)"),
]


def extract_phase_b_metrics(results: list[dict]) -> dict[str, tuple[int, str]]:
    """Extract Phase B metric values from check 12 findings.

    Returns {metric_id: (value, label)}. Only includes metrics where the
    finding-id is present AND the current field contains a numeric value.
    """
    finding_map: dict[str, dict] = {}
    for check_result in results:
        if not isinstance(check_result, dict):
            continue
        for f in check_result.get("findings", []) or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            if not fid:
                continue
            finding_map[fid] = f

    metrics: dict[str, tuple[int, str]] = {}
    for metric_id, finding_id, field_name, label in _PHASE_B_METRIC_PATHS:
        if metric_id in metrics:
            continue  # already filled from an earlier finding_id in priority order
        f = finding_map.get(finding_id)
        if not f:
            continue
        current = f.get("current")
        if not isinstance(current, dict):
            continue
        val = current.get(field_name)
        try:
            metrics[metric_id] = (int(val), label)
        except (TypeError, ValueError):
            continue
    return metrics


def _format_delta(current: int, prior: int) -> str:
    delta = current - prior
    if prior == 0:
        if current == 0:
            return "no change"
        return f"+{delta} (was 0)"
    pct = delta * 100 / prior
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta} ({sign}{pct:.1f}%)"


def emit_phase_b_section(
    current_metrics: dict[str, tuple[int, str]],
    prior_results: list[dict] | None,
    resolved_count: int,
) -> str:
    """Phase B audit-report subsection: indexing-state delta with
    confidence-tier framing. Emits only when both current + prior metrics
    are available."""
    if not current_metrics or prior_results is None:
        return ""
    prior_metrics = extract_phase_b_metrics(prior_results)
    overlap = set(current_metrics.keys()) & set(prior_metrics.keys())
    if not overlap:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("### Indexing-state context (Phase B, medium confidence)")
    lines.append("")
    lines.append(
        "**Companion signals only.** Per ADR 0002 Decision 1, audit-diff "
        "persistence (above) is the primary measurement; the deltas below "
        "are reported at confidence-tier MEDIUM at best. Attribution noise "
        "is unresolvable — indexing-state shifts could be operator action, "
        "Google/Bing algorithm updates, seasonality, or other operator "
        "changes the skill didn't recommend. Do not claim causation; read "
        "as correlation only."
    )
    lines.append("")
    lines.append("| Metric | Prior pass | Current pass | Delta |")
    lines.append("|---|---|---|---|")
    for metric_id in sorted(overlap):
        cur_val, label = current_metrics[metric_id]
        prior_val, _ = prior_metrics[metric_id]
        lines.append(
            f"| {label} | {prior_val} | {cur_val} | {_format_delta(cur_val, prior_val)} |"
        )
    lines.append("")

    if resolved_count > 0:
        lines.append(
            f"_Context: {resolved_count} finding(s) marked resolved this pass. "
            "Any positive indexing-state delta is **directionally consistent** "
            "with operator action but cannot be causally attributed — "
            "confounders unresolved. Negative deltas similarly may or may not "
            "trace to skill recommendations._"
        )
    else:
        lines.append(
            "_No findings marked resolved this pass; indexing-state deltas "
            "are independent of skill recommendations and reflect ambient "
            "engine + content state._"
        )
    lines.append("")
    return "\n".join(lines)


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


# Phase B+ (v1.6.2): substantive-edit pairing via Wayback CDX.
#
# Distinguishes substantive content changes from cosmetic / emitter-side
# fixes. When self-analyze detects resolved findings AND the operator
# has opted in via `substantive_edit_pairing: true` config, this probe
# samples sitemap URLs + compares current HTML against the most-recent
# Wayback snapshot. <10% text delta = cosmetic; ≥10% = substantive.
#
# Gated on: substantive_edit_pairing config + canonical_origin set +
# resolved-findings count > 0. Network-bound (Wayback CDX + current
# HTML fetch); ~30s-2min budget. Stdlib only.
#
# Output: advisory subsection. When 0/N substantive but findings
# resolved, flag compliance-theater risk. When ≥1/N substantive,
# directional consistency note.
_SUBSTANTIVE_SAMPLE = 3
_SUBSTANTIVE_THRESHOLD = 0.10  # >=10% text delta = substantive
_SUBSTANTIVE_UA = "IEO-launch-audit/self-analyze (substantive-edit-pairing)"
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)


def _fetch_sitemap_urls(canonical_origin: str, limit: int = 30) -> list[str]:
    """Fetch sitemap.xml; return up to `limit` URLs."""
    sitemap_url = f"{canonical_origin.rstrip('/')}/sitemap.xml"
    try:
        req = urllib.request.Request(
            sitemap_url,
            headers={"User-Agent": _SUBSTANTIVE_UA},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return []
    return _LOC_RE.findall(text)[:limit]


def _strip_text(html: str) -> str:
    s = re.sub(r"<script\b.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _wayback_substantive_probe(url: str) -> tuple[str | None, float | None]:
    """Per-URL: fetch most-recent Wayback snapshot + current HTML +
    compute SequenceMatcher ratio on stripped text. Returns
    (status, delta) where status is one of 'substantive', 'cosmetic',
    'unverifiable', and delta is 1.0 - ratio (None when unverifiable).
    """
    cdx_url = (
        "https://web.archive.org/cdx/search/cdx?"
        + urllib.parse.urlencode({
            "url": url,
            "output": "json",
            "limit": "-1",
            "fl": "timestamp,digest",
        })
    )
    try:
        req = urllib.request.Request(cdx_url, headers={"User-Agent": _SUBSTANTIVE_UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, TimeoutError, OSError):
        return "unverifiable", None
    if not isinstance(rows, list) or len(rows) < 2:
        return "unverifiable", None
    prior_ts = rows[-1][0]
    wayback_url = f"https://web.archive.org/web/{prior_ts}id_/{url}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _SUBSTANTIVE_UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            current_html = r.read().decode("utf-8", errors="replace")
        req = urllib.request.Request(wayback_url, headers={"User-Agent": _SUBSTANTIVE_UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            prior_html = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError):
        return "unverifiable", None
    cur_text = _strip_text(current_html)
    prior_text = _strip_text(prior_html)
    if not cur_text or not prior_text:
        return "unverifiable", None
    ratio = SequenceMatcher(None, prior_text, cur_text).ratio()
    delta = 1.0 - ratio
    return ("substantive" if delta >= _SUBSTANTIVE_THRESHOLD else "cosmetic"), delta


def emit_substantive_edit_section(
    resolved_count: int,
    canonical_origin: str | None,
    enabled: bool,
) -> str:
    """Optional Phase B+ subsection. Only emits when enabled + resolved
    findings present + canonical_origin known + sitemap fetchable +
    samples yield at least one verifiable result."""
    if not enabled or resolved_count == 0 or not canonical_origin:
        return ""
    urls = _fetch_sitemap_urls(canonical_origin, limit=30)
    if not urls:
        return ""

    # Deterministic sample (same as check-sitemap.py 7.5 seed).
    import random as _random
    _random.seed(42)
    sample = _random.sample(urls, min(_SUBSTANTIVE_SAMPLE, len(urls)))

    results: list[tuple[str, str, float | None]] = []
    for u in sample:
        status, delta = _wayback_substantive_probe(u)
        results.append((u, status, delta))

    substantive = [r for r in results if r[1] == "substantive"]
    cosmetic = [r for r in results if r[1] == "cosmetic"]
    unverifiable = [r for r in results if r[1] == "unverifiable"]
    scored = len(substantive) + len(cosmetic)

    if scored == 0:
        # All unverifiable — emit nothing rather than spam the report.
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("### Substantive-edit pairing (Phase B+, advisory)")
    lines.append("")
    lines.append(
        f"Sampled {len(sample)} sitemap URLs from `{canonical_origin}`; compared "
        f"current rendered HTML against most-recent Wayback snapshot. Threshold: "
        f"≥10% text delta = substantive content change."
    )
    lines.append("")
    lines.append(
        f"- **Substantive content delta:** {len(substantive)}/{scored} sampled URLs"
    )
    lines.append(
        f"- **Cosmetic-only (or unchanged):** {len(cosmetic)}/{scored} sampled URLs"
    )
    if unverifiable:
        lines.append(
            f"- **Unverifiable:** {len(unverifiable)} URL(s) — Wayback CDX returned "
            "no prior snapshot OR current/prior fetch failed."
        )
    lines.append("")

    if len(substantive) == 0:
        # Compliance-theater advisory.
        lines.append(
            f"**Compliance-theater advisory:** {resolved_count} finding(s) marked "
            "resolved this pass, but **0/{0} sampled URLs show substantive content "
            "change** vs the most-recent Wayback snapshot. Resolved findings may "
            "reflect *emitter-side* fixes (e.g., dropping unmirrored JSON-LD strings, "
            "adjusting metadata) rather than *visible content* changes. Consider "
            "whether each resolution actually addresses the underlying issue — "
            "schema-text parity resolved by dropping schema is technically a "
            "resolution but doesn't help LLM citation behavior the way restoring "
            "visible content does.".format(scored)
        )
    elif len(substantive) >= 1 and resolved_count > 0:
        lines.append(
            f"**Directionally consistent with operator action:** "
            f"{len(substantive)}/{scored} sampled URLs show substantive content "
            "delta, paired with this pass's resolved findings. Correlation only — "
            "the audit cannot causally attribute content changes to specific "
            "resolved findings without further evidence (which sampled URLs "
            "correspond to which findings is not tracked)."
        )
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

    # Phase B (v1.5.2): indexing-state delta from check 12 (GSC + Bing).
    # Read the prev report JSON (auto-rotated by audit.sh per v1.2's
    # .prev.json substrate) and compute metric deltas. Companion signal
    # only; medium-confidence framing mandatory.
    prev_json_path = report_json_path.with_name(
        report_json_path.stem + ".prev.json"
    ) if not report_json_path.name.endswith(".prev.json") else None
    # Standard auto-rotation: .launch-readiness-report.json →
    # .launch-readiness-report.prev.json. Derive directly.
    if prev_json_path is None or not prev_json_path.exists():
        # Fallback: try the canonical sibling path.
        candidate = report_json_path.parent / ".launch-readiness-report.prev.json"
        if candidate.exists():
            prev_json_path = candidate
        else:
            prev_json_path = None

    prior_results: list[dict] | None = None
    if prev_json_path and prev_json_path.exists():
        try:
            prior_results = json.loads(prev_json_path.read_text(encoding="utf-8"))
            if not isinstance(prior_results, list):
                prior_results = None
        except (OSError, json.JSONDecodeError):
            prior_results = None

    current_metrics = extract_phase_b_metrics(results)
    resolved_count = len(categories.get("resolved", []))
    phase_b_section = emit_phase_b_section(
        current_metrics, prior_results, resolved_count,
    )

    # Phase B+ (v1.6.2): substantive-edit pairing via Wayback CDX.
    # Opt-in via `substantive_edit_pairing: true` config + requires
    # canonical_origin set. Adds ~30s-2min when enabled.
    config = load_config(args.config) if args.config else {}
    substantive_section = emit_substantive_edit_section(
        resolved_count=resolved_count,
        canonical_origin=config.get("canonical_origin"),
        enabled=config.get("substantive_edit_pairing") is True,
    )

    if report_md_path.exists():
        try:
            with report_md_path.open("a", encoding="utf-8") as f:
                f.write(section)
                if phase_b_section:
                    f.write(phase_b_section)
                if substantive_section:
                    f.write(substantive_section)
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
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to .launch-readiness.yml (default: <repo>/.launch-readiness.yml). "
            "Used for Phase B+ substantive-edit pairing config "
            "(`substantive_edit_pairing: true` + `canonical_origin`)."
        ),
    )
    args = parser.parse_args()
    if args.config is None:
        args.config = str(Path(args.repo) / ".launch-readiness.yml")
    sys.exit(run(args))
