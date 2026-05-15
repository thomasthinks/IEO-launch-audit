#!/usr/bin/env python3
"""
Check 10 — External backlinks.

Queries free, no-auth public sources to report what's linking to the
audited domain. Per the project's no-paid-API ruling, free sources only:

  - Wayback CDX API (web.archive.org) — archived snapshots as a proxy
    signal for "URLs known to the wider web". Always queried.
  - Common Crawl CDX index — broad-web crawler index. Queried opportunistically;
    skipped on timeout because the index is huge and slow.
  - Open PageRank API — domain-rank score. Queried only when OPR_API_KEY
    env var is set; emits SKIP otherwise.

Pre-flip case (zero backlinks expected): emits INFO/PASS, not FAIL.
Network errors degrade to MANUAL_VERIFY findings; the audit does not crash.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


WAYBACK_LIMIT = 100
CC_LIMIT = 100
HTTP_TIMEOUT = 15  # seconds; per-request


def strip_protocol(origin: str) -> str:
    """Return bare host (no scheme, no path, no trailing slash) from a
    canonical_origin string. Falls back to the raw string if unparsable."""
    if not origin:
        return ""
    try:
        parsed = urllib.parse.urlparse(origin)
        host = parsed.netloc or parsed.path
        return host.strip("/").split("/")[0]
    except Exception:
        return origin.strip("/")


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = HTTP_TIMEOUT) -> tuple[int, bytes] | tuple[None, str]:
    """GET with stdlib only. Returns (status, body_bytes) on success or
    (None, error_msg) on failure."""
    hdrs = {"User-Agent": "IEO-launch-audit/0.6"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        return None, f"URLError: {e.reason}"
    except TimeoutError:
        return None, f"timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def query_wayback(domain: str) -> tuple[list[dict], str | None]:
    """Wayback CDX search. Returns (rows, error). Rows are dicts with
    at least 'original' (URL) and 'timestamp' keys."""
    url = (
        f"http://web.archive.org/cdx/search/cdx"
        f"?url=*.{urllib.parse.quote(domain)}/*"
        f"&matchType=domain&limit={WAYBACK_LIMIT}&output=json"
    )
    status, body = http_get(url)
    if status is None:
        return [], body  # type: ignore[return-value]
    if status != 200:
        return [], f"non-200 status: {status}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return [], f"JSON decode error: {e}"
    # CDX returns [[header], [row], [row], ...]
    if not data or not isinstance(data, list) or len(data) < 1:
        return [], None
    header, *rows = data
    return [dict(zip(header, row)) for row in rows], None


def query_common_crawl(domain: str) -> tuple[list[dict], str | None]:
    """Common Crawl index lookup. Picks the most recent index, queries
    once. Returns (rows, error). Skipped silently on timeout."""
    # List indexes first.
    status, body = http_get("https://index.commoncrawl.org/collinfo.json", timeout=10)
    if status is None:
        return [], body  # type: ignore[return-value]
    if status != 200:
        return [], f"collinfo non-200: {status}"
    try:
        collections = json.loads(body)
    except json.JSONDecodeError as e:
        return [], f"collinfo JSON error: {e}"
    if not collections:
        return [], "no Common Crawl collections returned"
    latest = collections[0]
    index_id = latest.get("id")
    if not index_id:
        return [], "no index id in collinfo"
    url = (
        f"http://index.commoncrawl.org/{index_id}-index"
        f"?url={urllib.parse.quote(domain)}/*"
        f"&limit={CC_LIMIT}&output=json"
    )
    status, body = http_get(url, timeout=20)
    if status is None:
        return [], body  # type: ignore[return-value]
    if status != 200:
        return [], f"index non-200: {status}"
    # CC returns one JSON object per line.
    rows: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows, None


def query_open_pagerank(domain: str, api_key: str) -> tuple[dict | None, str | None]:
    """Open PageRank API lookup. Returns (response_dict_for_domain, error)."""
    url = f"https://openpagerank.com/api/v1.0/getPageRank?domains[]={urllib.parse.quote(domain)}"
    status, body = http_get(url, headers={"API-OPR": api_key})
    if status is None:
        return None, body  # type: ignore[return-value]
    if status != 200:
        return None, f"non-200 status: {status}"
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return None, f"JSON decode error: {e}"
    response = data.get("response", [])
    if not response:
        return None, "empty response array"
    return response[0], None


def referring_domains_from_wayback(rows: list[dict]) -> set[str]:
    """Wayback CDX returns archived URLs *of the audited domain*, not
    referring pages. There's no free 'who links to me' from Wayback.
    Counts unique subdomains/hosts seen in 'original' as a proxy for
    distinct surfaces archived (still useful but not true referring
    domains)."""
    out: set[str] = set()
    for r in rows:
        original = r.get("original", "")
        if not original:
            continue
        try:
            host = urllib.parse.urlparse(original).netloc
            if host:
                out.add(host)
        except Exception:
            continue
    return out


def referring_domains_from_common_crawl(rows: list[dict]) -> set[str]:
    """Same caveat as Wayback — Common Crawl URL lookups return crawl
    records OF the audited domain. True referring-domain enumeration
    requires the offline WAT/WET corpus parse, which is out of scope."""
    out: set[str] = set()
    for r in rows:
        url = r.get("url", "")
        if not url:
            continue
        try:
            host = urllib.parse.urlparse(url).netloc
            if host:
                out.add(host)
        except Exception:
            continue
    return out


@time_check
def run(args) -> CheckResult:
    config = load_config(args.config)
    result = CheckResult(check="10-backlinks")

    canonical_origin = config.get("canonical_origin", "")
    domain = strip_protocol(canonical_origin)

    if not domain:
        result.findings.append(Finding(
            id="10.0.config", severity="MANUAL_VERIFY",
            title="canonical_origin not set — cannot query backlink sources",
            fix_safety="manual",
            fix_action="Set canonical_origin: https://<apex> in .launch-readiness.yml.",
        ))
        result.summary = "Backlinks: cannot run without canonical_origin."
        return result

    # Pre-flip sentinel: a localhost / private origin will return zero
    # from every public source. Flag once at INFO so the operator isn't
    # confused by empty results.
    is_local = any(domain.startswith(p) for p in ("localhost", "127.", "0.0.", "192.168.", "10."))
    if is_local:
        result.findings.append(Finding(
            id="10.0.local_origin", severity="INFO",
            title=f"canonical_origin is local ({domain}); public backlink sources will return 0",
            notes="Expected pre-flip. Re-run after apex DNS flip for real numbers.",
        ))

    # 10.1 — Wayback snapshots
    wayback_rows, wayback_err = query_wayback(domain)
    if wayback_err:
        result.findings.append(Finding(
            id="10.1.wayback_snapshots", severity="MANUAL_VERIFY",
            title=f"Wayback CDX query failed: {wayback_err}",
            fix_safety="manual",
            fix_action="Re-run after network recovers. The Wayback CDX endpoint is "
                       "occasionally rate-limited; transient failures are normal.",
        ))
    elif not wayback_rows:
        result.findings.append(Finding(
            id="10.1.wayback_snapshots", severity="INFO",
            title=f"Wayback: 0 snapshots archived for {domain}",
            current=0,
            notes="Pre-flip expected. Post-flip, Wayback typically picks up the apex within weeks.",
        ))
    else:
        result.findings.append(Finding(
            id="10.1.wayback_snapshots", severity="PASS",
            title=f"Wayback: {len(wayback_rows)} snapshots archived (capped at {WAYBACK_LIMIT})",
            current=len(wayback_rows),
        ))

    # Aggregate referring-domain set across sources.
    referring: set[str] = set()
    referring |= referring_domains_from_wayback(wayback_rows)

    # 10.2 contributing — Common Crawl (best-effort; skip silently on timeout)
    cc_rows: list[dict] = []
    cc_err: str | None = None
    if not is_local:
        cc_rows, cc_err = query_common_crawl(domain)
        if cc_err:
            # Don't add a top-level finding for CC failure — it's known-flaky.
            # Note it inline on the 10.2 finding below.
            pass
        else:
            referring |= referring_domains_from_common_crawl(cc_rows)

    # 10.2 — Referring domains (combined)
    sources_used = ["wayback"]
    if not is_local and not cc_err:
        sources_used.append("common-crawl")

    if not referring:
        base_note = ("Pre-flip expected. Backlink discovery is naturally lagging: "
                     "Wayback + Common Crawl indexes update on a multi-week cadence.")
        if cc_err:
            base_note += f" Common Crawl note: {cc_err}"
        result.findings.append(Finding(
            id="10.2.referring_domains", severity="INFO",
            title=f"0 referring domains found across sources: {sources_used}",
            current=0,
            notes=base_note,
        ))
    else:
        # Severity is INFO at low counts (early post-flip), WARN if still
        # tiny after months. Pre-flip we don't know which we're in; default
        # to INFO until the operator has time-series context.
        severity = "INFO" if len(referring) < 5 else "PASS"
        result.findings.append(Finding(
            id="10.2.referring_domains", severity=severity,
            title=f"{len(referring)} unique referring/archive domains across {sources_used}",
            current=sorted(referring)[:25],  # cap output
            notes=("Note: Wayback + Common Crawl free endpoints return archived/crawled "
                   "URLs OF the audited domain, used here as a proxy for surface visibility. "
                   "True 'who links to me' enumeration requires Ahrefs/Moz/Majestic (paid) "
                   "or a Common Crawl WAT/WET offline parse (out of scope)."),
        ))

    # 10.3 — Open PageRank (optional; gated on env)
    opr_key = os.environ.get("OPR_API_KEY", "").strip()
    if not opr_key:
        result.findings.append(Finding(
            id="10.3.opr_rank", severity="NOT_APPLICABLE",
            title="Open PageRank: skipped (OPR_API_KEY env var not set)",
            fix_safety="manual",
            fix_action="Get a free key at https://www.domcop.com/openpagerank/ and "
                       "export OPR_API_KEY=<key> before re-running this check.",
        ))
    else:
        opr_data, opr_err = query_open_pagerank(domain, opr_key)
        if opr_err:
            result.findings.append(Finding(
                id="10.3.opr_rank", severity="MANUAL_VERIFY",
                title=f"Open PageRank query failed: {opr_err}",
                fix_safety="manual",
            ))
        elif not opr_data:
            result.findings.append(Finding(
                id="10.3.opr_rank", severity="INFO",
                title=f"Open PageRank: no data for {domain}",
                current=None,
            ))
        else:
            rank = opr_data.get("page_rank_decimal") or opr_data.get("rank") or 0
            result.findings.append(Finding(
                id="10.3.opr_rank", severity="PASS" if rank else "INFO",
                title=f"Open PageRank for {domain}: {rank}",
                current=rank,
                notes=f"Raw response: {opr_data}",
            ))

    result.summary = (
        f"Backlinks ({domain}): "
        f"wayback={len(wayback_rows)}, "
        f"common-crawl={'skipped' if (is_local or cc_err) else len(cc_rows)}, "
        f"referring_domains={len(referring)}, "
        f"opr={'skip' if not opr_key else 'queried'}."
    )
    result.config_used = {
        "domain": domain,
        "wayback_limit": WAYBACK_LIMIT,
        "cc_limit": CC_LIMIT,
        "opr_enabled": bool(opr_key),
    }
    return result


if __name__ == "__main__":
    parser = base_argparser("10-backlinks")
    args = parser.parse_args()
    emit(run(args))
