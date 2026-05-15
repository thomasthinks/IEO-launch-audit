# Check 12 — Search Console cross-verification

## Why this matters

The audit's source-side checks (1-10) verify what the site DECLARES
about its indexability surface (sitemap shape, robots.txt directives,
IndexNow keyfile, JSON-LD graph, canonical URLs). The live-apex check
(11) verifies the apex actually serves what was declared. Neither
catches the next layer: **did the search engines accept it?**

Submitted ≠ indexed. A clean sitemap can sit at Bing for weeks with 0
URLs accepted (Bing's quality classifier rejects the entire submission
because of a single low-quality page). GSC's "Crawled - currently not
indexed" exclusion silently drops content that the site believes is
canonical. This check is the operator's eye on that gap.

Both paths are opt-in. The skill stays stdlib-only + zero-paid-API by
default; this check costs ~1 second when unconfigured.

**Cited sources:** [Bing Webmaster API
docs](https://learn.microsoft.com/en-us/bingwebmaster/getting-access);
[GSC Index Coverage
report](https://support.google.com/webmasters/answer/7440203);
[Bing's index-rejection classifier — Fabrice Canel, SMX Munich 2025];
[GSC excluded-reasons taxonomy](https://support.google.com/webmasters/answer/7440203#excluded).

## What's checked

### 12.bing — Bing Webmaster API path

Opt-in via `bing_webmaster_api_key` (or env `BING_WEBMASTER_API_KEY`) +
`bing_webmaster_site_url` (or fallback to `canonical_origin`). The site
must be verified in Bing Webmaster Tools UI before API calls succeed.

| Finding | Pass | Info | Warn | MV |
|---|---|---|---|---|
| `12.bing.quota` — API key + site verification both valid | yes | — | — | — |
| `12.bing.crawl_errors` — 7d aggregate crawl-error count | 0 | — | >0 | — |
| `12.bing.blocked_pages` — pages blocked by robots.txt (informational) | — | always | — | — |
| `12.bing.indexed_vs_sitemap` — `indexed / sitemap_url_count` | ≥80% | 50-80% | <50% | — |
| `12.bing.api_error` — API call failed | — | — | — | any |

One `GetUrlSubmissionQuota` + one `GetCrawlStats` call per audit run.
Free tier handles this comfortably.

### 12.gsc — Google Search Console snapshot path

Opt-in via `gsc_index_snapshot_path` pointing at a JSON file the operator
exports manually from GSC's Index Coverage report.

Why no OAuth: GSC's API requires service-account JWT auth or 3-legged
OAuth. Both involve RSA-SHA256 signing that Python's stdlib doesn't
ship (would need `cryptography` or shelling out to `openssl`). The
snapshot-reader path keeps the skill stdlib-only at the cost of
operator-side staleness (re-export when stale).

**Snapshot schema:**

```json
{
  "exported_at": "2026-05-15T03:00:00Z",
  "indexed_urls": ["https://example.com/", "https://example.com/about", "..."],
  "excluded_urls": [
    {"url": "https://example.com/draft/", "reason": "Crawled - currently not indexed"},
    {"url": "https://example.com/redirect-old/", "reason": "Alternate page with proper canonical tag"}
  ]
}
```

| Finding | Pass | Info | Warn | MV |
|---|---|---|---|---|
| `12.gsc.indexed_vs_sitemap` — `indexed / sitemap_url_count` | ≥80% | 50-80% | <50% | — |
| `12.gsc.excluded_reasons` — top-5 exclusion reason counts | — | always | — | — |
| `12.gsc.snapshot_missing` — `gsc_index_snapshot_path` set but file absent | — | — | — | always |
| `12.gsc.snapshot_malformed` — JSON parse fail or wrong shape | — | — | — | always |

### 12.skipped — Both paths unconfigured

When neither Bing nor GSC is configured, a single INFO finding is
emitted. The check runs in <1s.

## How to fix

### Fix 12.bing — Get a Bing Webmaster API key

1. Go to [Bing Webmaster Tools](https://www.bing.com/webmasters/), sign in.
2. Add + verify your site (DNS TXT, meta tag, or XML upload method).
3. Settings → API Access → Generate key.
4. Drop the key in `BING_WEBMASTER_API_KEY` env var, OR
   `bing_webmaster_api_key` in `.launch-readiness.yml`, OR SOPS path
   via `bing_webmaster_secret_path`.

**Auto-fix safety: manual** (one-time operator setup).

### Fix 12.gsc — Export a GSC snapshot

1. In Google Search Console, select your property.
2. Indexing → Pages.
3. Click Export → JSON. (As of 2026-05, GSC exports CSV by default; switch
   format to JSON via the export dialog.)
4. Save the JSON to a stable path in the repo or build-output dir.
5. Set `gsc_index_snapshot_path: <relative-path>` in `.launch-readiness.yml`.
6. Re-export periodically; the audit reports `exported_at` so freshness
   is visible.

**Auto-fix safety: manual** (operator-driven export).

### Fix 12.bing.indexed_vs_sitemap (low ratio)

If Bing reports <50% of sitemap URLs indexed, the most likely causes:
- **Recent sitemap submission** — Bing typically takes 7-14 days to
  catch up. Re-run the audit weekly until ratio stabilises.
- **Subset of pages 5xx-ing during crawl** — check `12.bing.crawl_errors`
  count.
- **Quality classifier rejection** — Bing's classifier sometimes
  excludes pages that share too much template boilerplate (thin
  content, similar titles, near-duplicate descriptions). Check 11.J
  (meta-description duplicates) and check 1.canonical may surface
  the trigger.
- **Pages blocked by robots.txt** — check `12.bing.blocked_pages` to
  rule out an unintentional disallow.

**Auto-fix safety: manual** (case-specific).

### Fix 12.gsc.indexed_vs_sitemap (low ratio)

Most useful next step: read the `excluded_urls` array in the snapshot.
GSC's reason taxonomy is documented; the common reasons map to specific
actions:

| Reason | Action |
|---|---|
| "Crawled - currently not indexed" | Quality classifier. Strengthen content depth, internal-link density, or `about`/`mentions` schema. |
| "Discovered - currently not indexed" | Crawl-budget queue. Wait + submit via IndexNow / sitemap re-ping. |
| "Alternate page with proper canonical tag" | Intentional. No action needed unless the canonical is wrong. |
| "Duplicate without user-selected canonical" | Set explicit canonical. |
| "Soft 404" | Server returning 200 for empty / placeholder pages. Fix server-side. |
| "Blocked by robots.txt" | Intentional or regression — check robots.txt. |
| "Excluded by 'noindex' tag" | Intentional or staging leftover (see check 11.C.noindex). |

**Auto-fix safety: manual** (case-specific).

## Failure ratings

`12.bing.indexed_vs_sitemap` is the highest-severity finding in this
check (can WARN). Everything else is INFO/MV-class advisory. Search
Console cross-verification is observational rather than gating — a
brand-new site will inevitably show low indexed counts until Google /
Bing have crawled it.

## Cited research

- [Bing Webmaster API reference](https://learn.microsoft.com/en-us/bingwebmaster/getting-access)
- [GSC Index Coverage report](https://support.google.com/webmasters/answer/7440203)
- [Bing IndexNow integration](https://www.bing.com/indexnow)
- [GSC excluded-reasons taxonomy](https://support.google.com/webmasters/answer/7440203#excluded)

## Implementation notes

`scripts/check-search-console.py`:

1. Resolves `canonical_origin` from config (FAIL with NOT_APPLICABLE if
   absent — needs a live origin to cross-verify against).
2. Tries Bing API path: resolves key (env → inline → SOPS); fetches
   `GetUrlSubmissionQuota` + `GetCrawlStats`; emits 1-4 findings.
3. Tries GSC snapshot path: reads JSON file at
   `gsc_index_snapshot_path`; emits 2 findings.
4. If neither configured, emits one `12.skipped` INFO.

Stdlib only. ~300 lines. Bing API uses two GET requests (no auth except
the apikey query param). GSC path is filesystem read only.

The check runs in the default 1-10 block by default? **No** — opt-in
like check 11 (network-hitting, requires config). Pass `--checks 12` or
`--checks 1-12` explicitly.

GSC live API integration (service-account JWT or 3-legged OAuth) is on
the v1.3+ ROADMAP. The auth-complexity surface (RSA-SHA256 signing
without non-stdlib crypto) is the blocker; the snapshot path is the
v1.2 workaround.
