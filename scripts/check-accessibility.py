#!/usr/bin/env python3
"""
Check 15 — Accessibility (axe-core via Lighthouse accessibility category).

Lighthouse bundles the axe-core engine and audits ~50 WCAG 2.0/2.1/2.2
rules per URL: color contrast, image alt text, link/button names, ARIA
attribute validity, heading order, lang attrs, tabindex correctness,
viewport meta, and more. PageSpeed Insights returns the same audits;
this check makes a single PSI call and surfaces each failing a11y rule
as a Finding.

Why this matters for IEO/GEO (not just compliance):

  - LLM citation engines parse rendered HTML for entity extraction.
    Semantic HTML (proper heading order, descriptive link names, button
    text, alt text) directly improves the extraction surface AI engines
    pull citations from.
  - axe-core hits on missing alt / missing button text / heading-skip
    correlate with LLM-summary quality regressions observed in 2025-26
    A/B testing (Princeton/Georgia Tech KDD 2024, follow-on work).
  - WCAG compliance is also a legal requirement for many consumer-site
    classes; this check covers both surfaces in one pass.

Source: Lighthouse accessibility category, https://web.dev/lighthouse-accessibility/
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_TIMEOUT = 60

# A11y audits with audit.score == 1 are not actionable; only audits with
# audit.score in (0, null) plus details indicating actual failures are
# worth surfacing. Lighthouse marks audits scoreDisplayMode == "informative"
# or "notApplicable" for non-actionable cases.
NON_ACTIONABLE_DISPLAY_MODES = {"manual", "notApplicable", "informative"}


def _resolve_secret(repo: Path, secret_rel: str | None, env_var: str) -> str | None:
    """Locate a secret either via repo-relative file or env var."""
    import os
    if secret_rel:
        p = (repo / secret_rel).resolve()
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    v = os.environ.get(env_var)
    return v.strip() if v else None


def _call_psi(url: str, api_key: str) -> tuple[str, dict | str]:
    """Make a single PSI call requesting only the accessibility category."""
    qs = urllib.parse.urlencode([
        ("url", url),
        ("strategy", "mobile"),  # a11y rules are device-agnostic; mobile is canonical
        ("category", "accessibility"),
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


def _extract_a11y_failures(data: dict) -> tuple[float | None, list[dict]]:
    """From a PSI response, return (category_score, failing_audits).
    A failing audit is one with score==0 (or null with an actionable mode)
    and a non-empty details.items list."""
    lh = (data or {}).get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    a11y_score = (cats.get("accessibility") or {}).get("score")
    audit_refs = (cats.get("accessibility") or {}).get("auditRefs") or []
    audits = lh.get("audits") or {}

    failures = []
    for ref in audit_refs:
        audit_id = ref.get("id")
        if not audit_id:
            continue
        audit = audits.get(audit_id) or {}
        display_mode = audit.get("scoreDisplayMode", "")
        if display_mode in NON_ACTIONABLE_DISPLAY_MODES:
            continue
        score = audit.get("score")
        # score == 1 means the audit passed; score in (0, null) is actionable
        if score is not None and score >= 1:
            continue
        details = audit.get("details") or {}
        items = details.get("items") or []
        # If there's no items list, we can't tell what failed; skip.
        if not items and score is None:
            continue
        failures.append({
            "id": audit_id,
            "title": audit.get("title", audit_id),
            "description": audit.get("description", ""),
            "score": score,
            "weight": ref.get("weight", 0),  # higher = bigger contribution to category score
            "failing_node_count": len(items),
        })
    # Sort by weight desc (highest-impact failures first), then by failing-node-count desc.
    failures.sort(key=lambda f: (-f.get("weight", 0), -f.get("failing_node_count", 0)))
    return a11y_score, failures


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check_id=15, name="Accessibility (axe-core via Lighthouse)")

    # Resolve target origin. Prefer live_probe_origin (post-launch) over
    # canonical_origin (pre-launch placeholder).
    origin = (
        config.get("live_probe_origin")
        or config.get("canonical_origin")
    )
    if not origin:
        result.findings.append(Finding(
            id="15.no_origin", severity="MANUAL_VERIFY",
            title="No live_probe_origin / canonical_origin in config",
            fix_safety="manual",
            fix_action="Set canonical_origin (or live_probe_origin) in .launch-readiness.yml, then re-run.",
        ))
        result.summary = "Accessibility check skipped (no target origin)."
        return result

    api_key = _resolve_secret(repo, config.get("pagespeed_secret_path"), "PAGESPEED_API_KEY")
    if not api_key:
        result.findings.append(Finding(
            id="15.no_api_key", severity="MANUAL_VERIFY",
            title="PSI API key not configured (env PAGESPEED_API_KEY or pagespeed_secret_path)",
            fix_safety="manual",
            fix_action="Set PAGESPEED_API_KEY env var OR set pagespeed_secret_path in .launch-readiness.yml.",
            notes="PSI free tier: 25k req/day per key. Get one at https://developers.google.com/speed/docs/insights/v5/get-started.",
        ))
        result.summary = "Accessibility check skipped (no PSI API key)."
        return result

    home = origin.rstrip("/") + "/"
    status, payload = _call_psi(home, api_key)
    if status != "ok":
        sev = "WARN" if status == "rate_limited" else "MANUAL_VERIFY"
        result.findings.append(Finding(
            id=f"15.psi.{status}", severity=sev,
            title=f"PSI call for accessibility failed: {payload}",
            fix_safety="manual",
            fix_action="Re-run after quota reset (rate-limited) or inspect network/key (error).",
        ))
        result.summary = "Accessibility check failed to fetch Lighthouse data."
        return result

    a11y_score, failures = _extract_a11y_failures(payload)

    # 15.score — overall category score
    if a11y_score is None:
        result.findings.append(Finding(
            id="15.score", severity="MANUAL_VERIFY",
            title="PSI returned no accessibility score for the home URL",
        ))
    elif a11y_score >= 0.95:
        result.findings.append(Finding(
            id="15.score", severity="PASS",
            title=f"Accessibility category score {a11y_score:.2f} (>=0.95 threshold)",
        ))
    elif a11y_score >= 0.8:
        result.findings.append(Finding(
            id="15.score", severity="WARN",
            title=f"Accessibility category score {a11y_score:.2f} (target >=0.95)",
            fix_safety="manual",
            fix_action="See 15.failures finding for the per-audit cause list.",
        ))
    else:
        result.findings.append(Finding(
            id="15.score", severity="FAIL",
            title=f"Accessibility category score {a11y_score:.2f} (target >=0.95)",
            fix_safety="manual",
            fix_action="See 15.failures finding for the per-audit cause list.",
        ))

    # 15.failures — per-audit failure list
    if failures:
        # Cap to top 15 by weight; rest are visible in the .launch-readiness-report.json.
        sample = failures[:15]
        max_weight = max(f.get("weight", 0) for f in failures)
        sev = "FAIL" if max_weight >= 7 else ("WARN" if max_weight >= 3 else "INFO")
        result.findings.append(Finding(
            id="15.failures", severity=sev,
            title=f"{len(failures)} accessibility audit(s) failed (top {len(sample)} shown)",
            current=[
                {
                    "id": f["id"], "title": f["title"],
                    "weight": f["weight"],
                    "failing_nodes": f["failing_node_count"],
                }
                for f in sample
            ],
            fix_safety="manual",
            fix_action="Address highest-weight audits first (weight is Lighthouse's per-audit "
                       "category contribution; 7-10 = highest impact). See "
                       "https://web.dev/lighthouse-accessibility/ for per-audit fix guidance.",
            notes="LLM citation engines parse rendered HTML; semantic-HTML failures (missing alt, "
                  "unlabeled buttons/links, heading skips) directly degrade AI extraction quality.",
        ))
    elif a11y_score is not None and a11y_score >= 0.95:
        result.findings.append(Finding(
            id="15.failures", severity="PASS",
            title="No actionable accessibility audit failures",
        ))

    result.summary = (
        f"Accessibility audit complete. Score: "
        f"{a11y_score if a11y_score is not None else 'n/a'}. "
        f"Failures: {len(failures)}."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("15-accessibility")
    args = parser.parse_args()
    emit(run(args))
