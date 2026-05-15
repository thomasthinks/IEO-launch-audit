#!/usr/bin/env python3
"""
Check 12 — Search Console cross-verification (Bing Webmaster API + GSC snapshot).

v1.2 opt-in. Cross-verifies what the audit reports SUBMITTED (sitemap
contents, IndexNow keyfile) against what the search engines have actually
INDEXED. Catches the class of failure where the build emits a valid
sitemap, the audit reports clean, but Google/Bing have either silently
dropped pages or never accepted them.

Two paths, both opt-in (skill stays stdlib-only + zero-paid-API by default):

  - **Bing Webmaster API** (live, single GET). Requires `bing_webmaster_api_key`
    (or env BING_WEBMASTER_API_KEY) + `bing_webmaster_site_url`. Free tier;
    no quota issues for a per-audit single call. The site must be verified
    in Bing Webmaster Tools first.

  - **Google Search Console snapshot** (operator-side export). The audit
    reads a JSON file the operator exports from GSC's Index Coverage
    report. Avoids OAuth complexity in the skill itself; the trade is
    operator-side staleness (snapshot ages between exports).

When neither is configured, the check emits a single INFO and runs in
<1s. Opt-in to take a position on indexing coverage.
"""
from __future__ import annotations

import json
import os
import re
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


BING_API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"
BING_TIMEOUT_S = 20
UA = "IEO-launch-audit/1.2 (+search-console-check)"
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _resolve_secret(repo: Path, secret_rel: str | None, env_var: str) -> str | None:
    """Resolve an API key, in priority order: env var → SOPS path.
    Mirrors the pattern used by check 4 (PSI) and check 11 (Brave).
    Returns None when nothing is reachable."""
    tok = os.environ.get(env_var)
    if tok:
        return tok.strip()
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
        m = re.match(rf"^\s*{re.escape(env_var)}\s*:\s*(.+?)\s*$", line)
        if m:
            val = m.group(1).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            return val
    return None


def _resolve_sitemap_url_count(origin: str) -> int | None:
    """Fetch live sitemap.xml and return URL count. None on failure."""
    if not origin:
        return None
    sitemap_url = origin.rstrip("/") + "/sitemap.xml"
    try:
        req = urllib.request.Request(sitemap_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200:
                return None
            body = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    try:
        root = ET.fromstring(body.decode(errors="replace"))
    except ET.ParseError:
        return None
    return sum(1 for _ in root.findall("s:url", SITEMAP_NS))


def _call_bing(endpoint: str, params: dict) -> tuple[str, dict | str]:
    """Call a Bing Webmaster API endpoint. Returns ("ok", parsed_json) or
    ("error", message)."""
    url = f"{BING_API_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=BING_TIMEOUT_S) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        return ("error", f"HTTP {e.code} from Bing API ({endpoint})")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return ("error", f"Bing API unreachable: {e!r}"[:200])
    try:
        return ("ok", json.loads(raw.decode("utf-8", errors="replace")))
    except json.JSONDecodeError as e:
        return ("error", f"Bing API non-JSON response: {e!r}"[:200])


def _check_bing(result: CheckResult, repo: Path, config: dict, origin: str) -> bool:
    """Run the Bing-side findings. Returns True if Bing was configured and
    a call was attempted (regardless of success), False if unconfigured.
    Caller uses the return to decide whether to emit a 'Bing skipped' INFO."""
    key = (
        config.get("bing_webmaster_api_key")
        or _resolve_secret(repo, config.get("bing_webmaster_secret_path"), "BING_WEBMASTER_API_KEY")
    )
    if not key:
        return False
    site_url = config.get("bing_webmaster_site_url") or origin
    if not site_url:
        result.findings.append(Finding(
            id="12.bing.no_site", severity="MANUAL_VERIFY",
            title="Bing API key configured but no site URL resolvable (config + canonical_origin both empty)",
            fix_action="Set `bing_webmaster_site_url` in .launch-readiness.yml.",
        ))
        return True
    # 12.bing.quota — sanity check the key is valid + the site is verified
    # by fetching the URL-submission quota. Cheap; one call.
    status, payload = _call_bing("GetUrlSubmissionQuota", {"siteUrl": site_url, "apikey": key})
    if status != "ok":
        result.findings.append(Finding(
            id="12.bing.api_error", severity="MANUAL_VERIFY",
            title="Bing Webmaster API call failed; probe skipped this run",
            notes=str(payload)[:200],
            fix_action=(
                "Verify bing_webmaster_api_key is valid and bing_webmaster_site_url "
                "points at a Bing-verified site. The site must be verified in "
                "Bing Webmaster Tools (UI) before API calls succeed."
            ),
        ))
        return True
    daily_quota = ((payload or {}).get("d") or {}).get("DailyQuota")
    monthly_quota = ((payload or {}).get("d") or {}).get("MonthlyQuota")
    if daily_quota is not None and monthly_quota is not None:
        result.findings.append(Finding(
            id="12.bing.quota", severity="PASS",
            title=f"Bing API reachable; daily quota={daily_quota}, monthly={monthly_quota}",
            current={"daily_quota": daily_quota, "monthly_quota": monthly_quota},
            notes="Quota values come from Bing's per-key tier; presence confirms key + site verification both valid.",
        ))
    # 12.bing.crawl_stats — pull aggregate crawl stats. Two findings:
    # crawl-errors count + indexed-vs-sitemap delta.
    status, payload = _call_bing("GetCrawlStats", {"siteUrl": site_url, "apikey": key})
    if status != "ok":
        result.findings.append(Finding(
            id="12.bing.crawl_stats", severity="MANUAL_VERIFY",
            title="Bing GetCrawlStats failed; indexing cross-verification skipped",
            notes=str(payload)[:200],
        ))
        return True
    stats = (payload or {}).get("d") or []
    if not isinstance(stats, list) or not stats:
        result.findings.append(Finding(
            id="12.bing.crawl_stats", severity="INFO",
            title="Bing GetCrawlStats returned no rows (newly-verified site, or no crawl activity in window)",
            notes="Bing reports stats once it has crawled the site; expect data ~7-14 days after verification.",
        ))
        return True
    # GetCrawlStats returns an array of daily snapshots. Sum the last 7
    # days for crawl-errors; use the most recent row for index count.
    recent = stats[:7] if len(stats) >= 7 else stats
    total_crawled = sum(int(r.get("CrawledPages", 0) or 0) for r in recent)
    total_errors = sum(int(r.get("CrawlErrors", 0) or 0) for r in recent)
    total_blocked = sum(int(r.get("BlockedByRobotsTxtPages", 0) or 0) for r in recent)
    latest = stats[0] if stats else {}
    indexed_count = int(latest.get("InIndex", 0) or 0)

    if total_errors > 0:
        result.findings.append(Finding(
            id="12.bing.crawl_errors", severity="WARN",
            title=f"Bing reports {total_errors} crawl error(s) across the last {len(recent)} day(s)",
            current={"crawl_errors_7d": total_errors, "crawled_pages_7d": total_crawled},
            fix_action=(
                "Inspect Bing Webmaster Tools UI for the specific URLs flagged. "
                "Common causes: server 5xx on a subset of paths, slow response "
                "times triggering Bing timeout, or robots.txt regression."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="12.bing.crawl_errors", severity="PASS",
            title=f"Bing reports 0 crawl errors across the last {len(recent)} day(s)",
            current={"crawled_pages_7d": total_crawled},
        ))

    if total_blocked > 0:
        result.findings.append(Finding(
            id="12.bing.blocked_pages", severity="INFO",
            title=f"Bing reports {total_blocked} page(s) blocked by robots.txt over the window",
            notes=(
                "Expected when robots.txt explicitly disallows admin / draft / "
                "staging paths. Investigate only if you didn't expect any blocks."
            ),
        ))

    # 12.bing.indexed_vs_sitemap — cross-verify indexed count against
    # sitemap URL count.
    sitemap_n = _resolve_sitemap_url_count(origin)
    if sitemap_n is not None and indexed_count > 0:
        ratio = indexed_count / sitemap_n
        if ratio < 0.5:
            severity = "WARN"
        elif ratio < 0.8:
            severity = "INFO"
        else:
            severity = "PASS"
        result.findings.append(Finding(
            id="12.bing.indexed_vs_sitemap", severity=severity,
            title=(
                f"Bing indexed {indexed_count} URL(s); sitemap declares {sitemap_n} "
                f"({ratio * 100:.0f}%)"
            ),
            current={"indexed": indexed_count, "sitemap": sitemap_n, "ratio": round(ratio, 2)},
            expected="≥80% of sitemap URLs indexed (allowing for Bing's discovery lag)",
            fix_action=(
                "If <50%, the sitemap is being submitted but Bing isn't accepting "
                "the URLs. Verify Bing Webmaster Tools UI Index Explorer for "
                "specific exclusion reasons. Common causes: noindex on a subset, "
                "canonical pointing off-site, or thin-content classification."
            ) if severity != "PASS" else None,
        ))
    return True


def _check_gsc_snapshot(result: CheckResult, repo: Path, config: dict, origin: str) -> bool:
    """Run the GSC-side findings from an operator-exported snapshot file.

    Schema expected at gsc_index_snapshot_path (JSON object):
        {
          "exported_at": "2026-05-15T03:00:00Z",
          "indexed_urls": [<url>, ...],
          "excluded_urls": [{"url": ..., "reason": "...", ...}, ...]
        }

    The operator exports this from GSC's Index Coverage report (manual
    UI export). The skill ships no OAuth surface to avoid auth complexity
    + service-account JWT signing (would require non-stdlib crypto).
    """
    snap_rel = config.get("gsc_index_snapshot_path")
    if not snap_rel:
        return False
    snap_path = repo / snap_rel
    if not snap_path.exists():
        result.findings.append(Finding(
            id="12.gsc.snapshot_missing", severity="MANUAL_VERIFY",
            title=f"gsc_index_snapshot_path set but file not found: {snap_rel}",
            fix_action=(
                "Export the Index Coverage report from Google Search Console "
                "(UI: Indexing → Pages → Export) as JSON, save to this path."
            ),
        ))
        return True
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        result.findings.append(Finding(
            id="12.gsc.snapshot_malformed", severity="MANUAL_VERIFY",
            title=f"GSC snapshot at {snap_rel} is malformed",
            notes=str(e)[:200],
        ))
        return True
    indexed = snap.get("indexed_urls") or []
    excluded = snap.get("excluded_urls") or []
    exported_at = snap.get("exported_at") or "<unknown>"
    if not isinstance(indexed, list) or not isinstance(excluded, list):
        result.findings.append(Finding(
            id="12.gsc.snapshot_shape", severity="MANUAL_VERIFY",
            title="GSC snapshot fields indexed_urls / excluded_urls must both be arrays",
            current={"indexed_type": type(indexed).__name__, "excluded_type": type(excluded).__name__},
        ))
        return True

    # 12.gsc.indexed_vs_sitemap — cross-verify against live sitemap.
    sitemap_n = _resolve_sitemap_url_count(origin)
    if sitemap_n is not None and len(indexed) > 0:
        ratio = len(indexed) / sitemap_n
        severity = "PASS" if ratio >= 0.8 else ("INFO" if ratio >= 0.5 else "WARN")
        result.findings.append(Finding(
            id="12.gsc.indexed_vs_sitemap", severity=severity,
            title=(
                f"GSC snapshot reports {len(indexed)} indexed URL(s); sitemap "
                f"declares {sitemap_n} ({ratio * 100:.0f}%)"
            ),
            current={"indexed": len(indexed), "sitemap": sitemap_n, "exported_at": exported_at},
            expected="≥80% of sitemap URLs indexed (allowing for GSC discovery lag)",
            fix_action=(
                "If <50%, inspect the excluded_urls reasons. GSC's most common "
                "exclusion reasons: 'Crawled - currently not indexed' (quality), "
                "'Discovered - currently not indexed' (waiting on crawl budget), "
                "'Alternate page with proper canonical tag' (intentional)."
            ) if severity != "PASS" else None,
            notes=f"Snapshot exported_at: {exported_at}. Re-export when stale.",
        ))

    # 12.gsc.excluded_reasons — surface most common exclusion categories.
    if excluded:
        reason_counts: dict[str, int] = {}
        for entry in excluded:
            if isinstance(entry, dict):
                r = entry.get("reason") or entry.get("status") or "<unspecified>"
                reason_counts[r] = reason_counts.get(r, 0) + 1
        top = sorted(reason_counts.items(), key=lambda x: -x[1])[:5]
        result.findings.append(Finding(
            id="12.gsc.excluded_reasons", severity="INFO",
            title=f"GSC snapshot lists {len(excluded)} excluded URL(s); top reasons: {top}",
            current=dict(top),
            notes=(
                "Excluded ≠ broken. Many GSC exclusion reasons are intentional "
                "(canonical chains, redirect alternates). Investigate quality-"
                "related reasons ('Crawled - currently not indexed', 'Soft 404')."
            ),
        ))
    return True


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="12-search-console")

    origin = (
        config.get("canonical_origin")
        or config.get("live_probe_origin")
        or ""
    ).rstrip("/")
    if origin and not origin.startswith(("http://", "https://")):
        origin = "https://" + origin

    if not origin:
        result.findings.append(Finding(
            id="12.0.no_origin", severity="NOT_APPLICABLE",
            title="No canonical_origin configured; Search Console cross-verification needs a live origin",
            fix_action=(
                "Set canonical_origin in .launch-readiness.yml. Both Bing API and "
                "GSC snapshot paths need an origin to cross-verify against the "
                "live sitemap."
            ),
        ))
        return result

    bing_ran = _check_bing(result, repo, config, origin)
    gsc_ran = _check_gsc_snapshot(result, repo, config, origin)

    if not bing_ran and not gsc_ran:
        result.findings.append(Finding(
            id="12.skipped", severity="INFO",
            title="Search Console cross-verification skipped (no bing_webmaster_api_key + no gsc_index_snapshot_path)",
            notes=(
                "Opt-in to either path to take a position on indexing coverage:\n"
                "  - Bing: set bing_webmaster_api_key + verify the site in Bing "
                "Webmaster Tools UI. Free tier; one API call per audit run.\n"
                "  - GSC: export Index Coverage report from GSC UI to JSON, set "
                "gsc_index_snapshot_path. Operator-driven; avoids OAuth complexity."
            ),
        ))

    result.summary = (
        f"Bing: {'configured' if bing_ran else 'skipped'}; "
        f"GSC snapshot: {'configured' if gsc_ran else 'skipped'}"
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("12-search-console")
    args = parser.parse_args()
    emit(run(args))
