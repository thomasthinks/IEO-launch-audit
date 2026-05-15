# Check 10 — External backlinks

## Why this matters

Backlinks remain a top-tier ranking signal for traditional search and a
growing signal for LLM-driven citation (Perplexity, ChatGPT Search,
Claude Search). The 2026 incremental: AI search systems triangulate
entity authority via crawl-graph density, so referring-domain count
matters even when individual link equity is low.

This check uses **free, no-auth sources only** per the project's
no-paid-API ruling. The free-tier surface is genuinely limited compared
to Ahrefs / Moz / Majestic, so this check is **observational, not
gating** — its job is to surface a trend line, not block the launch
flip on a backlink count.

**Cited sources:** Wayback CDX API documentation
(https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server);
Common Crawl index API
(https://commoncrawl.org/the-data/get-started/); Open PageRank API
(https://www.domcop.com/openpagerank/).

## What's checked

### 10.1 — Wayback Machine archived snapshots

Queries the Internet Archive CDX API for snapshots of `*.<DOMAIN>/*`.
A proxy signal for "URLs the wider web has noticed enough to archive".

| Assertion | Pass | Info |
|---|---|---|
| Wayback has ≥1 archived snapshot for the domain | yes | no |

INFO (not FAIL) when zero — pre-flip and just-post-flip sites
legitimately have zero snapshots.

### 10.2 — Referring/archive domains (combined)

Aggregates the unique host set across Wayback + Common Crawl results.

**Important caveat:** the free Wayback + Common Crawl endpoints return
archived/crawled URLs **OF** the audited domain, not pages that link
**TO** the audited domain. True "who links to me" enumeration requires
either a paid backlink index (Ahrefs / Moz / Majestic) or an offline
parse of Common Crawl's WAT/WET corpus (terabytes; out of scope here).

So this finding is a proxy: "how many distinct surfaces of my own
domain have been crawled/archived by the public web?" — useful as a
visibility-trend indicator, not a true backlink count.

| Assertion | Pass | Info |
|---|---|---|
| ≥5 unique referring/archive domains | yes | < 5 |
| 0 results | — | INFO (pre-flip expected) |

### 10.3 — Open PageRank score (optional)

Queries the Open PageRank API for the domain's rank score. Requires a
free API key in the `OPR_API_KEY` env var.

| Assertion | Pass | Skip |
|---|---|---|
| `OPR_API_KEY` env var set | run | NOT_APPLICABLE |
| API returns a non-zero `page_rank_decimal` | yes | INFO |

## How to fix

Most "fixes" here are operator-side and slow (months, not weeks):

### Fix 10.1 — Get archived

Wayback Machine crawls organically once the domain is reachable and
linked-from-anywhere. To accelerate:

1. Submit the apex via the "Save Page Now" form at
   https://web.archive.org/save.
2. Post the apex on at least one public surface that Wayback indexes
   (GitHub README, personal blog, public Mastodon).

**Auto-fix safety: manual** (requires public posting + Wayback submission).

### Fix 10.2 — Earn referring domains

Standard SEO-side levers: guest posts, podcast appearances, public
talks with linked slides, open-source project READMEs, conference
proceedings, news mentions, podcast show notes.

For an editorial / writing-led site specifically, the highest-yield
moves in 2026 are:

- Cross-post canonical-tagged versions on Substack / Medium / Mirror
  (these have high TF-IDF authority and pass referrer signal)
- Get cited in Wikipedia footnotes (highest-trust referring domain
  available)
- Get included in a curated "best writing on X" list

**Auto-fix safety: manual** (operator-side content / outreach work).

### Fix 10.3 — Improve domain rank

Open PageRank moves slowly. The score is downstream of 10.2; can't be
fixed directly. The check is reported as observational telemetry.

**Auto-fix safety: manual** (downstream of referring-domain growth).

## Failure ratings

- **INFO:** zero results from any source (pre-flip expected; not a launch blocker).
- **PASS:** ≥1 Wayback snapshot or ≥5 referring domains.
- **MANUAL_VERIFY:** network or API failure; re-run after recovery.
- **NOT_APPLICABLE:** Open PageRank skipped due to missing `OPR_API_KEY`.

This check **does not emit FAIL**. Backlinks are an emergent property
of the wider web noticing the site; they're not something the operator
can directly write code to produce, so gating launch on them would be
miscalibrated.

## Cited research

- [Wayback CDX API](https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md)
- [Common Crawl index server](https://github.com/ikreymer/cdx-index-client)
- [Open PageRank API docs](https://www.domcop.com/openpagerank/documentation)
- [Backlink signals 2026](https://ahrefs.com/blog/seo-statistics/) (general industry context, no API consumed)

## Implementation notes

The script `scripts/check-backlinks.py`:

1. Reads `canonical_origin` from `.launch-readiness.yml`, strips the
   protocol to get the bare host.
2. If the host is local (`localhost`, `127.*`, `192.168.*`, `10.*`),
   emits a pre-flip INFO sentinel and skips the Common Crawl call
   (public indexes won't return anything for a private origin).
3. Queries Wayback CDX (`http://web.archive.org/cdx/search/cdx`) with
   `matchType=domain&limit=100&output=json`. Network errors degrade to
   MANUAL_VERIFY.
4. Queries Common Crawl: first hits `collinfo.json` to get the latest
   index id, then queries `https://index.commoncrawl.org/<index-id>-index`.
   Failures here are silenced (the index is genuinely flaky); the
   error is appended to the 10.2 note instead of producing its own
   finding.
5. If `OPR_API_KEY` is set in the env, queries Open PageRank with the
   `API-OPR` header. Otherwise emits NOT_APPLICABLE.
6. Aggregates the unique host set across Wayback + Common Crawl rows
   for the 10.2 finding.
7. Caps each source at 100 entries to avoid pagination explosion.

All HTTP uses `urllib.request` from the stdlib — no `requests`
dependency.
