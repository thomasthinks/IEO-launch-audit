#!/usr/bin/env python3
"""
Check 04 — Core Web Vitals (LCP / INP / CLS).

Strategy:
1. If Vercel/Next.js stack detected AND `vercel:performance-optimizer` skill
   available, surface a delegation recommendation (the orchestrating
   conversation invokes the skill).
2. If `pagespeed_api_key` (or `pagespeed_secret_path`) is configured AND a
   live origin is reachable, call PageSpeed Insights v5 for home + N
   sampled pieces and parse Lighthouse category scores + Core Web Vitals.
3. Else, if `lhci` or `lighthouse` CLI available, run a local lab audit.
4. Else, report MANUAL_VERIFY with PageSpeed Insights instructions.

Static-input recommendations (preload hints, fetchpriority on hero, font
loading) are checked regardless of runtime audit availability.

PSI cost shape:
  ~25-40s per URL per strategy. With default sample of 3 pieces + home =
  4 URLs, mobile-only run is ~2-3 minutes; "both" strategy doubles that.
  PSI quota is 25k req/day per key.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_TIMEOUT = 90  # seconds; PSI can take 30-60s per URL
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _resolve_psi_key(repo: Path, config: dict) -> str | None:
    """Find a PageSpeed Insights API key, in priority order:

    1. PAGESPEED_API_KEY env var (explicit, no decryption needed).
    2. `pagespeed_api_key` literal in config (not recommended for committed
       configs; convenient for one-off runs).
    3. SOPS-decrypted secrets file at `pagespeed_secret_path` in config.
       Requires `sops` on PATH. Mirrors the cf-api SOPS pattern (check 3.4).

    Returns None if no key is reachable. Caller treats None as "PSI not
    configured" and skips the API path.
    """
    tok = os.environ.get("PAGESPEED_API_KEY")
    if tok:
        return tok.strip()
    inline = config.get("pagespeed_api_key")
    if inline and isinstance(inline, str) and inline.strip():
        return inline.strip()
    secret_rel = config.get("pagespeed_secret_path")
    if not secret_rel:
        return None
    secret_path = repo / secret_rel
    if not secret_path.exists():
        return None
    try:
        out = subprocess.run(
            ["sops", "-d", str(secret_path)],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        m = re.match(r"^\s*PAGESPEED_API_KEY\s*:\s*(.+?)\s*$", line)
        if m:
            val = m.group(1).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            return val
    return None


def _sample_urls(origin: str, sample_n: int) -> list[str]:
    """Fetch the live sitemap and randomly sample N piece URLs.

    Returns [] on any fetch/parse failure — caller falls back to home-only.
    Deterministic per-run via random.seed(42), consistent with check 11.
    """
    if not origin or sample_n <= 0:
        return []
    sitemap_url = origin.rstrip("/") + "/sitemap.xml"
    try:
        req = urllib.request.Request(sitemap_url, headers={"User-Agent": "IEO-launch-audit"})
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200:
                return []
            body = r.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(body.decode(errors="replace"))
    except ET.ParseError:
        return []
    urls: list[str] = []
    for u in root.findall("s:url", SITEMAP_NS):
        loc = u.find("s:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    # Prefer piece URLs (richer content for CWV measurement) over index pages.
    piece_urls = [u for u in urls if "/writing/" in u and "/pillar/" not in u]
    pool = piece_urls if piece_urls else urls
    if not pool:
        return []
    random.seed(42)
    n = min(sample_n, len(pool))
    return random.sample(pool, n)


def _call_psi(url: str, strategy: str, api_key: str) -> tuple[str, dict | str]:
    """Call PageSpeed Insights v5.

    Returns:
      ("ok", parsed_json)        — successful response
      ("rate_limited", message)  — HTTP 429
      ("error", message)         — any other failure mode

    Stdlib-only; no `requests` / `googleapiclient`.
    """
    qs = urllib.parse.urlencode([
        ("url", url),
        ("strategy", strategy),
        ("category", "performance"),
        ("category", "accessibility"),
        ("category", "best-practices"),
        ("category", "seo"),
        ("key", api_key),
    ])
    full = f"{PSI_ENDPOINT}?{qs}"
    req = urllib.request.Request(full, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=PSI_TIMEOUT) as resp:
            return ("ok", json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return ("rate_limited", f"HTTP 429: {e.reason}")
        return ("error", f"HTTP {e.code}: {e.reason}")
    except (urllib.error.URLError, TimeoutError) as e:
        return ("error", f"{type(e).__name__}: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        return ("error", f"JSON parse: {e}")


def _parse_psi_result(data: dict) -> dict:
    """Extract category scores + CWV audits from a PSI response.

    Returns a flat dict with keys:
      perf, a11y, bp, seo                  — category scores 0..1 (or None)
      lcp_s, cls, tbt_ms, fcp_s, si_s, tti_s — CWV-class audit numericValues
                                             (or None if absent)
    """
    out: dict = {
        "perf": None, "a11y": None, "bp": None, "seo": None,
        "lcp_s": None, "cls": None, "tbt_ms": None,
        "fcp_s": None, "si_s": None, "tti_s": None,
    }
    lh = (data or {}).get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    out["perf"] = (cats.get("performance") or {}).get("score")
    out["a11y"] = (cats.get("accessibility") or {}).get("score")
    out["bp"] = (cats.get("best-practices") or {}).get("score")
    out["seo"] = (cats.get("seo") or {}).get("score")
    audits = lh.get("audits") or {}

    def _num(audit_id: str) -> float | None:
        a = audits.get(audit_id) or {}
        v = a.get("numericValue")
        return float(v) if v is not None else None

    lcp_ms = _num("largest-contentful-paint")
    out["lcp_s"] = lcp_ms / 1000.0 if lcp_ms is not None else None
    out["cls"] = _num("cumulative-layout-shift")
    out["tbt_ms"] = _num("total-blocking-time")
    fcp_ms = _num("first-contentful-paint")
    out["fcp_s"] = fcp_ms / 1000.0 if fcp_ms is not None else None
    si_ms = _num("speed-index")
    out["si_s"] = si_ms / 1000.0 if si_ms is not None else None
    tti_ms = _num("interactive")
    out["tti_s"] = tti_ms / 1000.0 if tti_ms is not None else None
    return out


# CrUX (Chrome User Experience Report) — real-user field data.
# Lab data (Lighthouse) is synthetic Chrome on a controlled connection.
# Field data is the canonical Core Web Vitals signal Google Search Console
# uses for ranking; needs ~28 days of real user traffic to populate.
#
# PSI puts CrUX in two optional blocks on every response:
#   loadingExperience       — page-level (sparse; most URLs lack traffic)
#   originLoaderExperience  — origin-level (much more often populated)
#
# Each block carries a `metrics` dict keyed by metric name with shape:
#   {"percentile": int, "distributions": [...], "category": "FAST"|"AVERAGE"|"SLOW"}
# plus an `overall_category` for the block.

# PSI CrUX metric key -> short label used in finding IDs and detail dicts.
_CRUX_METRIC_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "INTERACTION_TO_NEXT_PAINT": "inp",
    "FIRST_INPUT_DELAY_MS": "fid",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}


def _parse_crux_block(block: dict | None) -> dict | None:
    """Extract CrUX metrics from a `loadingExperience` or
    `originLoaderExperience` block. Returns None if block is absent or
    carries no metrics (a populated block always has a non-empty
    `metrics` dict)."""
    if not block or not isinstance(block, dict):
        return None
    metrics = block.get("metrics") or {}
    if not metrics:
        return None
    out: dict = {
        "overall_category": block.get("overall_category"),
        "initial_url": block.get("initial_url"),
        "metrics": {},
    }
    for psi_key, short in _CRUX_METRIC_KEYS.items():
        m = metrics.get(psi_key)
        if not m:
            continue
        out["metrics"][short] = {
            "percentile": m.get("percentile"),
            "category": m.get("category"),
            "distributions": m.get("distributions"),
        }
    return out if out["metrics"] else None


def _grade_crux_category(category: str | None) -> str:
    """Map CrUX category to a Finding severity.
    FAST -> PASS, AVERAGE -> WARN, SLOW -> FAIL, anything else -> NOT_APPLICABLE.
    CrUX categories already encode the 75th-percentile thresholds Google uses,
    so we trust the bucket directly rather than re-thresholding on percentiles."""
    if category == "FAST":
        return "PASS"
    if category == "AVERAGE":
        return "WARN"
    if category == "SLOW":
        return "FAIL"
    return "NOT_APPLICABLE"


def _grade_scores(per_url: list[dict]) -> tuple[str, list[str]]:
    """Aggregate severity across category scores from a list of parsed
    per-URL results. Returns (severity, problem_descriptions).

    PASS if all 4 scores >=0.9 across all URLs.
    WARN if any score in [0.7, 0.9).
    FAIL if any score <0.7.
    """
    worst = "PASS"
    problems: list[str] = []
    for p in per_url:
        for key, label in (("perf", "performance"), ("a11y", "accessibility"),
                           ("bp", "best-practices"), ("seo", "seo")):
            score = p.get(key)
            if score is None:
                continue
            if score < 0.7:
                worst = "FAIL"
                problems.append(f"{p['_url']} [{p['_strategy']}] {label}={score:.2f}")
            elif score < 0.9 and worst != "FAIL":
                worst = "WARN"
                problems.append(f"{p['_url']} [{p['_strategy']}] {label}={score:.2f}")
    return worst, problems


def _grade_metric(per_url: list[dict], key: str, pass_th: float, warn_th: float,
                  unit: str) -> tuple[str, list[str]]:
    """Generic CWV-metric aggregator. PASS if all <=pass_th, WARN if all
    <=warn_th, FAIL otherwise."""
    worst = "PASS"
    over: list[str] = []
    for p in per_url:
        v = p.get(key)
        if v is None:
            continue
        if v > warn_th:
            worst = "FAIL"
            over.append(f"{p['_url']} [{p['_strategy']}] {v:.3f}{unit}")
        elif v > pass_th and worst != "FAIL":
            worst = "WARN"
            over.append(f"{p['_url']} [{p['_strategy']}] {v:.3f}{unit}")
    return worst, over


_CRUX_NO_DATA_NOTE = (
    "CrUX needs ~28 days of real user traffic to populate; "
    "re-check after launch traffic accumulates."
)


def _emit_crux_finding(result: CheckResult, finding_id: str, scope: str,
                       metric_label: str, target_str: str,
                       block: dict | None, metric_short: str) -> None:
    """Emit one CrUX-derived finding.

    scope is "page" or "origin" — used only for human-readable titles.
    block is the parsed CrUX dict (or None if absent for this scope).
    metric_short is the key under block["metrics"] ("lcp", "cls", "inp", ...).
    """
    if not block:
        result.findings.append(Finding(
            id=finding_id, severity="NOT_APPLICABLE",
            title=f"CrUX {scope}-level {metric_label.upper()}: no field data yet",
            notes=_CRUX_NO_DATA_NOTE,
        ))
        return
    metric = (block.get("metrics") or {}).get(metric_short)
    if not metric:
        result.findings.append(Finding(
            id=finding_id, severity="NOT_APPLICABLE",
            title=f"CrUX {scope}-level {metric_label.upper()}: metric not reported in CrUX block",
            notes=f"CrUX block present but {metric_label.upper()} not populated; "
                  "common when traffic volume is below per-metric thresholds.",
        ))
        return
    category = metric.get("category")
    percentile = metric.get("percentile")
    sev = _grade_crux_category(category)
    title = (
        f"CrUX {scope}-level {metric_label.upper()}: category={category} "
        f"(p75={percentile})"
    )
    if sev == "NOT_APPLICABLE":
        result.findings.append(Finding(
            id=finding_id, severity=sev,
            title=f"CrUX {scope}-level {metric_label.upper()}: unrecognised category={category!r}",
            current={"category": category, "percentile": percentile},
        ))
        return
    finding = Finding(
        id=finding_id, severity=sev, title=title,
        current={"category": category, "percentile": percentile},
        expected=f"category=FAST (target {target_str})",
    )
    if sev != "PASS":
        finding.fix_safety = "manual"
        finding.notes = (
            f"CrUX field {metric_label.upper()} is the Google ranking signal; "
            "75th-percentile across real-user sessions in the last 28 days."
        )
    result.findings.append(finding)


def _emit_crux_findings(result: CheckResult,
                        home_page_crux: dict | None,
                        origin_crux: dict | None,
                        page_crux_rows: list[dict]) -> None:
    """Emit the full 4.crux.* finding family.

    If neither page-level nor origin-level CrUX is populated, emit a single
    `4.crux.no_data` INFO finding and skip the per-metric breakouts (would
    otherwise be 6 NOT_APPLICABLE findings carrying the same signal)."""
    if not home_page_crux and not origin_crux:
        result.findings.append(Finding(
            id="4.crux.no_data", severity="INFO",
            title="CrUX field data not yet available (page- and origin-level both empty)",
            notes=_CRUX_NO_DATA_NOTE,
        ))
        return

    # Per-metric findings. CrUX-defined p75 targets (web.dev/vitals): LCP
    # <=2.5s, CLS <=0.1, INP <=200ms. These match the lab thresholds but
    # apply to the 75th-percentile of real users, not synthetic Chrome.
    _emit_crux_finding(result, "4.crux.page_lcp", "page", "lcp",
                       "<=2500ms p75", home_page_crux, "lcp")
    _emit_crux_finding(result, "4.crux.page_cls", "page", "cls",
                       "<=0.1 p75", home_page_crux, "cls")
    _emit_crux_finding(result, "4.crux.page_inp", "page", "inp",
                       "<=200ms p75", home_page_crux, "inp")
    _emit_crux_finding(result, "4.crux.origin_lcp", "origin", "lcp",
                       "<=2500ms p75", origin_crux, "lcp")
    _emit_crux_finding(result, "4.crux.origin_cls", "origin", "cls",
                       "<=0.1 p75", origin_crux, "cls")
    _emit_crux_finding(result, "4.crux.origin_inp", "origin", "inp",
                       "<=200ms p75", origin_crux, "inp")

    # 4.crux.summary — INFO carrying the full distribution + percentile data
    # for human review. Includes every page-level row sampled (not just
    # home), so an operator can spot inconsistencies between pages.
    summary_payload: dict = {
        "page_level": [
            {
                "url": row.get("_url"),
                "strategy": row.get("_strategy"),
                "overall_category": row.get("overall_category"),
                "metrics": row.get("metrics"),
            }
            for row in page_crux_rows
        ],
        "origin_level": (
            {
                "initial_url": origin_crux.get("initial_url"),
                "overall_category": origin_crux.get("overall_category"),
                "metrics": origin_crux.get("metrics"),
            } if origin_crux else None
        ),
    }
    result.findings.append(Finding(
        id="4.crux.summary", severity="INFO",
        title=(
            f"CrUX field-data summary: "
            f"{len(page_crux_rows)} page-level row(s), "
            f"origin-level={'present' if origin_crux else 'absent'}"
        ),
        current=summary_payload,
        notes="Field data is the canonical Core Web Vitals signal Google "
              "Search Console uses for ranking; lab data (4.psi.*) is "
              "synthetic and pre-traffic.",
    ))


def _run_psi_phase(result: CheckResult, origin: str, api_key: str,
                   strategies: list[str], sample_n: int,
                   include_crux: bool = True) -> bool:
    """Run PSI calls + emit findings. Mutates `result` in place. Returns
    True iff at least one PSI call produced parseable lab data.

    CrUX field-data extraction (`include_crux=True`, default) parses
    `loadingExperience` (page-level) and `originLoaderExperience`
    (origin-level) from the same PSI responses — no extra API calls."""
    home = origin.rstrip("/") + "/"
    sampled = _sample_urls(origin, sample_n)
    targets = [home] + [u for u in sampled if u != home]

    per_url: list[dict] = []
    api_errors: list[str] = []
    rate_limited = False
    # CrUX: home-URL page-level (most stable target), all page-level rows
    # (for the summary), and origin-level (identical across responses, so
    # first one wins).
    home_page_crux: dict | None = None
    page_crux_rows: list[dict] = []
    origin_crux: dict | None = None
    for u in targets:
        for strat in strategies:
            status, payload = _call_psi(u, strat, api_key)
            if status == "rate_limited":
                rate_limited = True
                api_errors.append(f"{u} [{strat}]: {payload}")
                continue
            if status == "error":
                api_errors.append(f"{u} [{strat}]: {payload}")
                continue
            parsed = _parse_psi_result(payload)
            parsed["_url"] = u
            parsed["_strategy"] = strat
            per_url.append(parsed)
            if include_crux:
                page_block = _parse_crux_block(payload.get("loadingExperience"))
                if page_block:
                    page_block["_url"] = u
                    page_block["_strategy"] = strat
                    page_crux_rows.append(page_block)
                    if u == home and home_page_crux is None:
                        home_page_crux = page_block
                if origin_crux is None:
                    origin_crux = _parse_crux_block(payload.get("originLoaderExperience"))

    if rate_limited and not per_url:
        result.findings.append(Finding(
            id="4.psi.rate_limited", severity="WARN",
            title="PSI returned HTTP 429 for all calls; quota exhausted (resets daily Pacific midnight)",
            current=api_errors[:5],
            fix_safety="manual",
            fix_action="Wait for daily quota reset, or use a different API key. "
                       "PSI free tier: 25k req/day per key.",
        ))
        return False
    if not per_url:
        result.findings.append(Finding(
            id="4.psi.all_failed", severity="WARN",
            title=f"PSI calls failed for all {len(targets) * len(strategies)} attempts",
            current=api_errors[:5],
            fix_safety="manual",
            fix_action="Inspect error detail; verify PAGESPEED_API_KEY scope and network reachability.",
        ))
        return False

    # Per-URL info finding (machine-readable distribution).
    detail = []
    for p in per_url:
        detail.append({
            "url": p["_url"], "strategy": p["_strategy"],
            "perf": p["perf"], "a11y": p["a11y"],
            "bp": p["bp"], "seo": p["seo"],
            "lcp_s": p["lcp_s"], "cls": p["cls"],
            "tbt_ms": p["tbt_ms"], "fcp_s": p["fcp_s"],
            "si_s": p["si_s"], "tti_s": p["tti_s"],
        })
    result.findings.append(Finding(
        id="4.psi.detail", severity="INFO",
        title=f"PSI per-URL detail ({len(per_url)} measurements across "
              f"{len(targets)} URL(s), strategies={','.join(strategies)})",
        current=detail,
    ))

    # 4.psi.scores — aggregate Lighthouse category scores
    sev, problems = _grade_scores(per_url)
    if sev == "PASS":
        result.findings.append(Finding(
            id="4.psi.scores", severity="PASS",
            title=f"All Lighthouse category scores >=0.9 across {len(per_url)} measurement(s)",
        ))
    else:
        result.findings.append(Finding(
            id="4.psi.scores", severity=sev,
            title=f"{len(problems)} category-score(s) below 0.9 threshold",
            current=problems[:10],
            fix_safety="manual",
            fix_action="Open the PSI report for each flagged URL and address the lowest category.",
        ))

    # 4.psi.lcp — Largest Contentful Paint
    sev, problems = _grade_metric(per_url, "lcp_s", 2.5, 4.0, "s")
    if sev == "PASS":
        result.findings.append(Finding(
            id="4.psi.lcp", severity="PASS",
            title=f"LCP <=2.5s across {len(per_url)} measurement(s)",
        ))
    else:
        result.findings.append(Finding(
            id="4.psi.lcp", severity=sev,
            title=f"{len(problems)} measurement(s) over LCP target",
            current=problems[:10], expected="<=2.5s",
            fix_safety="manual",
        ))

    # 4.psi.cls — Cumulative Layout Shift
    sev, problems = _grade_metric(per_url, "cls", 0.1, 0.25, "")
    if sev == "PASS":
        result.findings.append(Finding(
            id="4.psi.cls", severity="PASS",
            title=f"CLS <=0.1 across {len(per_url)} measurement(s)",
        ))
    else:
        result.findings.append(Finding(
            id="4.psi.cls", severity=sev,
            title=f"{len(problems)} measurement(s) over CLS target",
            current=problems[:10], expected="<=0.1",
            fix_safety="manual",
        ))

    # 4.psi.tbt — Total Blocking Time (lab proxy for INP)
    sev, problems = _grade_metric(per_url, "tbt_ms", 200.0, 600.0, "ms")
    if sev == "PASS":
        result.findings.append(Finding(
            id="4.psi.tbt", severity="PASS",
            title=f"TBT <=200ms across {len(per_url)} measurement(s) (lab proxy for INP)",
        ))
    else:
        result.findings.append(Finding(
            id="4.psi.tbt", severity=sev,
            title=f"{len(problems)} measurement(s) over TBT target",
            current=problems[:10], expected="<=200ms",
            fix_safety="manual",
            notes="TBT is a Lighthouse-lab proxy for INP; CrUX field INP is the ranking signal.",
        ))

    # 4.crux.* — CrUX field data (real-user, last-28-day). Page-level uses
    # the home-URL response; origin-level is identical across responses.
    if include_crux:
        _emit_crux_findings(result, home_page_crux, origin_crux, page_crux_rows)

    # Surface partial-failure as INFO so consumers see the gap.
    if api_errors:
        result.findings.append(Finding(
            id="4.psi.partial_errors", severity="INFO",
            title=f"{len(api_errors)} PSI call(s) failed while others succeeded",
            current=api_errors[:5],
        ))
    return True


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    # Lighthouse runs against the URL the audit can actually reach right now;
    # live_probe_origin falls back to canonical_origin in load_config().
    live_probe_origin = config.get("live_probe_origin", "")
    result = CheckResult(check="04-performance")

    # 4.1 — Stack-based delegation recommendation
    if args.stack.startswith("vercel"):
        result.findings.append(Finding(
            id="4.0.delegate", severity="INFO",
            title="Vercel/Next.js stack — invoke vercel:performance-optimizer for stack-aware audit",
            fix_safety="manual",
            fix_action="Run `/vercel:performance-optimizer` in the conversation. "
                       "Covers LCP/INP/CLS, server components, edge runtime, image optimization.",
        ))

    # 4.2 — PageSpeed Insights (opt-in via config)
    psi_key = _resolve_psi_key(repo, config)
    psi_ran = False
    psi_produced_data = False
    if psi_key and live_probe_origin:
        strategy_cfg = (config.get("pagespeed_strategy") or "mobile").lower()
        if strategy_cfg == "both":
            strategies = ["mobile", "desktop"]
        elif strategy_cfg in ("mobile", "desktop"):
            strategies = [strategy_cfg]
        else:
            strategies = ["mobile"]
        try:
            sample_n = int(config.get("pagespeed_sample_urls", 3))
        except (TypeError, ValueError):
            sample_n = 3
        # Default ON: CrUX rides in the same PSI response — no extra cost.
        include_crux = bool(config.get("pagespeed_include_crux", True))
        psi_produced_data = _run_psi_phase(
            result, live_probe_origin, psi_key, strategies, sample_n,
            include_crux=include_crux,
        )
        psi_ran = True

    # 4.2 — Lighthouse CLI integration (legacy local-lab path; only when PSI
    # didn't already produce field data)
    lhci = shutil.which("lhci") or shutil.which("lighthouse")
    if not psi_ran:
        if lhci and live_probe_origin:
            # Actually run lighthouse and parse results
            try:
                cmd = [lhci, live_probe_origin, "--output=json", "--quiet", "--chrome-flags=--headless"]
                if "lhci" in lhci:
                    # lhci-ci wrapper takes different args
                    cmd = [lhci, "autorun", "--config", "/dev/null"]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode != 0:
                    raise RuntimeError(f"lighthouse exited {r.returncode}")
                # Parse output (lighthouse emits JSON to stdout when --output=json)
                lh_data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
                if lh_data:
                    audits = lh_data.get("audits", {})
                    lcp = audits.get("largest-contentful-paint", {}).get("numericValue", None)
                    cls = audits.get("cumulative-layout-shift", {}).get("numericValue", None)
                    inp = audits.get("interaction-to-next-paint", {}).get("numericValue", None) \
                        or audits.get("interactive", {}).get("numericValue", None)

                    if lcp is not None:
                        lcp_s = lcp / 1000
                        sev = "PASS" if lcp_s <= 2.5 else ("WARN" if lcp_s <= 4.0 else "FAIL")
                        result.findings.append(Finding(
                            id="4.lcp", severity=sev,
                            title=f"LCP {lcp_s:.2f}s (target <=2.5s)",
                            current=f"{lcp_s:.2f}s", expected="<=2.5s",
                            fix_safety="manual",
                        ))
                    if cls is not None:
                        sev = "PASS" if cls <= 0.1 else ("WARN" if cls <= 0.25 else "FAIL")
                        result.findings.append(Finding(
                            id="4.cls", severity=sev,
                            title=f"CLS {cls:.3f} (target <=0.1)",
                            current=f"{cls:.3f}", expected="<=0.1",
                            fix_safety="manual",
                        ))
                    if inp is not None:
                        sev = "PASS" if inp <= 200 else ("WARN" if inp <= 500 else "FAIL")
                        result.findings.append(Finding(
                            id="4.inp", severity=sev,
                            title=f"INP/TTI {inp:.0f}ms (target <=200ms)",
                            current=f"{inp:.0f}ms", expected="<=200ms",
                            fix_safety="manual",
                        ))
                else:
                    result.findings.append(Finding(
                        id="4.1.lighthouse.parse_error", severity="MANUAL_VERIFY",
                        title="Lighthouse ran but output not parseable as JSON",
                    ))
            except Exception as e:
                result.findings.append(Finding(
                    id="4.1.lighthouse.run_error", severity="MANUAL_VERIFY",
                    title=f"Lighthouse run failed: {e}",
                    fix_action=f"Run manually: {lhci} {live_probe_origin} --output=json --quiet",
                ))
        elif not live_probe_origin:
            result.findings.append(Finding(
                id="4.1.lighthouse.no_origin", severity="MANUAL_VERIFY",
                title="No live_probe_origin / canonical_origin in config — cannot run Lighthouse against live URL",
                fix_safety="manual",
                fix_action="Set canonical_origin (or live_probe_origin during pre-flip dev) in .launch-readiness.yml, then re-run.",
            ))
        else:
            result.findings.append(Finding(
                id="4.1.lighthouse.not_installed", severity="MANUAL_VERIFY",
                title="Lighthouse CLI not installed (and no pagespeed_api_key configured)",
                fix_safety="manual",
                fix_action="Either: install Lighthouse (`npm install -g @lhci/cli`), "
                           "or set pagespeed_api_key / pagespeed_secret_path in .launch-readiness.yml.",
            ))

    # 4.3 — Static input checks (apply regardless of runtime audit availability)
    # Hero image preload hint in index.html
    for idx_path in [repo / "client/index.html", repo / "public/index.html",
                      repo / "src/index.html", repo / "index.html"]:
        if idx_path.exists():
            html = idx_path.read_text(encoding="utf-8")
            if 'rel="preload"' in html and "as=\"image\"" in html:
                result.findings.append(Finding(
                    id="4.3.hero_preload", severity="PASS",
                    title="Hero image preload hint present in index.html",
                ))
            else:
                result.findings.append(Finding(
                    id="4.3.hero_preload", severity="INFO",
                    title="No <link rel='preload' as='image'> in index.html",
                    fix_safety="safe",
                    fix_action="Add preload hint for hero image to improve LCP.",
                    notes="Hero attrs are checked in check 01 (technical SEO).",
                ))
            break

    # Font loading
    for idx_path in [repo / "client/index.html", repo / "public/index.html", repo / "index.html"]:
        if idx_path.exists():
            html = idx_path.read_text(encoding="utf-8")
            if "rel=\"preconnect\"" in html or "rel=\"dns-prefetch\"" in html:
                result.findings.append(Finding(
                    id="4.3.font_preconnect", severity="PASS",
                    title="Font preconnect/dns-prefetch hints present",
                ))
            else:
                result.findings.append(Finding(
                    id="4.3.font_preconnect", severity="INFO",
                    title="No font preconnect/dns-prefetch hints",
                    fix_safety="safe",
                    fix_action="Add <link rel='preconnect' href='https://fonts.googleapis.com'> if using web fonts.",
                ))
            break

    # 4.4 — Image format optimization (AVIF/WebP presence)
    avif_count = len(list(repo.glob("**/*.avif")))
    webp_count = len(list(repo.glob("**/*.webp")))
    jpg_count = len(list((repo / "client/src/assets").rglob("*.jpg"))) if (repo / "client/src/assets").exists() else 0
    png_count = len(list((repo / "client/src/assets").rglob("*.png"))) if (repo / "client/src/assets").exists() else 0
    if avif_count + webp_count > 0:
        result.findings.append(Finding(
            id="4.4.image_formats", severity="PASS",
            title=f"Modern image formats present: {avif_count} AVIF, {webp_count} WebP",
            current={"avif": avif_count, "webp": webp_count, "jpg": jpg_count, "png": png_count},
        ))
    elif jpg_count + png_count > 5:
        result.findings.append(Finding(
            id="4.4.image_formats", severity="WARN",
            title=f"No AVIF/WebP found; {jpg_count} JPG + {png_count} PNG in assets",
            fix_safety="manual",
            fix_action="Convert assets to AVIF or WebP at build time for LCP improvement.",
        ))

    if psi_produced_data:
        result.summary = (
            "PSI data collected; CWV findings reflect real Lighthouse runs. "
            "Static input checks also done."
        )
    elif psi_ran:
        result.summary = (
            "PSI configured but all calls failed (see 4.psi.* findings). "
            "Static input checks done."
        )
    else:
        result.summary = (
            "Performance audit is mostly runtime-dependent; static input checks done. "
            "Live LCP/INP/CLS verification requires lighthouse + canonical_origin, "
            "or set pagespeed_api_key in .launch-readiness.yml."
        )
    return result


if __name__ == "__main__":
    parser = base_argparser("04-performance")
    args = parser.parse_args()
    emit(run(args))
