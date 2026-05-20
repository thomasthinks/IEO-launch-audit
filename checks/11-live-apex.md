# Check 11 — Live-apex audit

## Why this matters

Checks 1-10 audit the **source repo + built artifacts** (`dist/`, `public/`,
`out/`, config files). That catches authoring + emitter bugs, but it
cannot see what the live origin actually serves:

- CDN-side trailing-slash canonicalization (Cloudflare, Vercel, Fastly
  all do this differently). A sitemap whose entries 308-redirect on
  every fetch still works for users but signals "lying about
  canonicalization" to Googlebot.
- Per-page meta drift between source and rendered HTML (template
  variables that silently default to `undefined`, missing `og:image`
  on routes that the emitter forgot to cover, rogue `noindex` left over
  from staging).
- JSON-LD that parses-clean locally but renders broken at the CDN edge
  (e.g. HTML-escaped quotes inside the script block).
- Internal links pointing at slugs that were renamed before the
  matching `<a href>` was updated — only the live target reveals the
  404.
- Security headers that apply to `/` but not to subpath routes when
  the host config's `source` glob is wrong.
- Discovery artifacts (`/robots.txt`, `/llms.txt`, `/sitemap.xml`,
  `/image-sitemap.xml`, IndexNow keyfile) that exist in `dist/` but
  404 at the apex because the host's static-rewrite rules don't catch
  them.

External auditors (Screaming Frog, Sitebulb, Ahrefs Site Audit, GSC
URL Inspection) all hit the live origin. Check 11 surfaces the same
class of finding without needing a paid tool.

**Post-launch LLM-citation tracking — measurement-variance advisory.**
If the consumer is using Profound / Otterly / BrightEdge / 5W / Brave
or any LLM-citation-tracking tool after launch, single-shot measurements
are unreliable. LLM citation outputs are stochastic — the same query
issued multiple times produces different citation sets. Two arXiv
preprints in 2026 formalize this: "Don't Measure Once: Measuring
Visibility in AI Search" ([arXiv:2604.07585](https://arxiv.org/abs/2604.07585))
and "Quantifying Uncertainty in AI Visibility"
([arXiv:2603.08924](https://arxiv.org/abs/2603.08924)). Recommended
practice: sample **n≥5 per query** with **stratified prompt variants**
(persona, length, framing) and report Jaccard / Rank-Biased Overlap /
bootstrap-resampled confidence intervals rather than point estimates.
This is methodology-side scaffolding consumers should apply to any LLM-
citation-tracking workflow; the skill doesn't measure citations itself,
but flagging the stochasticity prevents misinterpretation of any tool's
single-shot output.

**Cited sources:** Google Search Central — *Crawling and indexing
overview*; sitemap.xml protocol (sitemaps.org) — `<lastmod>` and URL
shape requirements; Schema.org — Article hierarchy and required
properties.

## When to run this

Check 11 is the only check in the suite that **requires the production
origin to be live and reachable**. It is excluded from the default
audit run (`audit.sh` runs checks 1-10 by default; pass
`--checks 11` or `--checks 1,2,...,11` to include it).

Run it:

- Immediately after pointing DNS at a new origin (catches CDN-side
  rewrites + redirect shape drift).
- After any change to host config (`vercel.json` `headers`,
  `_headers`, Cloudflare Workers route).
- After any rename of a piece slug (catches internal-link drift).
- On a schedule post-launch (weekly/monthly) as a regression check.

## What's checked

### 11.0 — Sitemap discovery

| Assertion | Pass | Fail |
|---|---|---|
| `sitemap.xml` fetches from `<apex>/sitemap.xml` with HTTP 200 | yes | no / non-200 |
| `sitemap.xml` is valid XML | yes | malformed |
| `sitemap.xml` contains at least one `<url>` entry | yes | empty |

### 11.A — Reachability sweep

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Every sitemap URL returns 2xx on HEAD | yes | — | any non-2xx |
| Zero sitemap URLs return a 301/302/307/308 redirect | yes | any redirect | — |

Redirect drift is WARN not FAIL — a 308 chain works for users but
signals "this URL is not canonical" to crawlers. The fix is to align
sitemap entries with the CDN's preferred URL shape (slash or no-slash;
pick one).

### 11.B — JSON-LD audit (home + about + sampled pieces)

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Every sampled page's JSON-LD blocks parse cleanly | yes | — | parse error |
| Every sampled page carries at least one JSON-LD block | yes | — | none |
| Home page carries both `WebSite` and `Person` types | yes | partial | — |
| Every sampled piece carries an Article-class type | yes | — | missing |

**Article-class** includes Schema.org Article subtypes: `Article`,
`NewsArticle`, `BlogPosting`, `ScholarlyArticle`, `TechArticle`,
`Report`. Any one satisfies the baseline.

Sample size defaults to 12 pieces (plus home + about). Sample is
deterministic via `random.seed(42)` so re-runs compare cleanly.

### 11.C — Per-page meta audit

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Every sampled page has `<title>` | yes | — | missing |
| Every sampled page has `<meta name="description">` | yes | missing | — |
| Every sampled page has `<link rel="canonical">` | yes | missing | — |
| Canonical points at the apex host | yes | — | wrong host |
| Every sampled page has `<meta property="og:image">` | yes | missing | — |
| No sampled page carries `<meta name="robots" content="noindex">` | yes | — | noindex present |

A rogue `noindex` is FAIL because it silently de-indexes the page —
the most common cause of "we launched but Google won't pick us up."

### 11.D — Inline-link audit

| Assertion | Pass | Fail |
|---|---|---|
| Every internal `<a href>` on 5 sampled pieces returns 2xx/3xx on HEAD | yes | broken |

Catches slug renames that orphaned an inline link.

### 11.E — Security-header consistency

Checks 5 security headers (`Strict-Transport-Security`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
`Content-Security-Policy`) on 3 target pages (home, a sampled piece,
about).

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Every header present on every target | yes | — | missing somewhere |
| Each header has the same value on every target | yes | inconsistent | — |

Inconsistency typically means the host config's `source` glob only
catches a subset of routes (e.g. `/(.*)` works but `/` alone may not
match in some hosts).

### 11.F — Discovery artifacts

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| `/robots.txt` returns 200 | yes | — | non-200 |
| `/sitemap.xml` returns 200 | yes | — | non-200 |
| `/llms.txt` returns 200 | yes | non-200 | — |
| `/image-sitemap.xml` returns 200 | yes | non-200 | — |
| IndexNow keyfile (`/<key>.txt`) returns 200 if `indexnow_key` set | yes | non-200 | — |

`robots.txt` + `sitemap.xml` are FAIL-class (load-bearing for any
crawler); `llms.txt` + `image-sitemap.xml` are WARN-class (best
practice but not blocking).

### 11.G — Title + heading + meta-description hygiene

Screaming-Frog-parity: catches the SERP-snippet display issues that
external auditors flag on every site report. All assertions run
against the pages already fetched (home + about + 18 sampled pieces).

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| `<title>` length within 30-65 chars | yes | <30 or >65 | — |
| `<h1>` present on every page | yes | — | missing |
| Exactly one `<h1>` per page | yes | >1 | — |
| `<meta name="description">` length within 70-160 chars | yes | <70 or >160 | — |

Title length range (30-65) is Google's snippet-display range —
shorter wastes SERP real estate, longer truncates on mobile.
Description range (70-160) is the desktop-SERP truncation range.
Both are guidance, not hard rules; editorial deviations are
defensible if intentional.

### 11.H — Redirect-chain hygiene

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Each sampled internal link resolves in 0 hops | yes | exactly 1 hop | >1 hop |

Reuses the 5-piece link sample from phase D; collects up to 25
unique internal-link targets and follows the redirect chain manually
(`HEAD`, no auto-follow, capped at 5 hops). Single-hop redirects
(typically trailing-slash drift, `/writing` → `/writing/`) WARN;
chains of 2+ FAIL because they compound latency + dilute link signal.

### 11.I — Orphan-page + un-sitemapped-link detection

Reconciles two graphs without extra apex fetches:

1. **Sitemap set:** every URL `sitemap.xml` claims is canonical.
2. **Link set:** every internal `<a href>` observed across home +
   about + sampled-piece HTML in the existing page cache.

| Assertion | Pass | Warn | Info |
|---|---|---|---|
| Every sitemap URL appears as a target somewhere in the link-set | yes | — | apparent orphans |
| Every internal-link target appears in the sitemap | yes | un-sitemapped | — |

Apparent-orphans is **INFO not WARN**: with only 20 pages sampled,
most "orphans" are simply unsampled. Use as a directional signal
(verify a few by hand), not as a definitive orphan-test. The
un-sitemapped finding is WARN-class because it indicates pages
that exist + are linked but won't be discovered through canonical
crawl paths.

### 11.J — Meta-description duplicate detection

| Assertion | Pass | Warn |
|---|---|---|
| Every sampled page's meta description is unique | yes | duplicates present |

Compares all non-empty meta descriptions across the page cache
(20 pages by default). Whitespace-normalized so trivial render-time
diffs don't dodge the dedup check. Duplicates trigger Google's
"duplicate meta descriptions" warning in Search Console and waste
SERP differentiation.

### 11.K — Brave Search indexability probe (v1.1)

| Assertion | Pass | Info | Manual-verify |
|---|---|---|---|
| Apex URL appears in Brave Search top-10 for brand-entity query | rank #N | absent / host-only match | API unreachable / rate-limited |

Anthropic's Claude.ai web search routes through Brave Search (Anthropic
subprocessor list, March 2025; Profound May 2025 measurement: 86.7%
citation-URL overlap between Claude's cited sources and Brave's top-10,
p<0.0001). Brave visibility is the practical Claude-citation eligibility
lever.

**NOTE: Brave does not offer a Webmaster Tools / Search Console
product.** Site owners cannot directly submit URLs; Brave indexes via
its Web Discovery Project (opt-in browser-side telemetry from Brave
users). The lever is *Brave visibility*, not *Brave submission*.

Opt-in: requires `brave_api_key` (free tier: 1 req/sec, 2k req/month at
api.search.brave.com). When unconfigured, phase K emits a single INFO
and skips. Findings are advisory only (INFO/PASS/MV); never FAIL —
search-engine visibility is emergent and noisy.

## What this catches vs the internal audit (checks 1-10)

| Class of issue | Internal (1-10) | Live (11) |
|---|---|---|
| Source-side authoring bugs | yes | no |
| Emitter logic bugs (wrong sitemap, broken JSON-LD generation) | yes | yes |
| CDN-side trailing-slash redirects | no | yes |
| Per-page meta drift between source and rendered HTML | partial | yes |
| Host-config glob mismatches (header applied to subset of routes) | no | yes |
| Slug-rename orphans on inline links | no | yes |
| Rogue staging `noindex` left in rendered HTML | partial | yes |
| Discovery artifacts missing at apex but present in build | no | yes |
| Title / H1 / meta-description hygiene (length, presence, uniqueness) | partial | yes |
| Multi-hop redirect chains on inline links | no | yes |
| Apparent orphan pages (sitemap-vs-link-graph drift) | no | yes |
| Duplicate meta descriptions across pages | no | yes |
| Brave Search indexability (Claude-citation eligibility) | no | yes (opt-in) |

The two are complementary. Run 1-10 during development to catch
source-side issues fast; run 11 against the live origin to catch what
the CDN + host config silently change.

Phases G-J close the Screaming-Frog-parity gap: they surface the
same class of finding paid crawlers flag, against the live rendered
HTML, without leaving the suite.

## Usage

```bash
# Run check 11 standalone against any origin
python3 .claude/skills/IEO-launch-audit/scripts/check-live-apex.py \
  --apex https://example.com/

# Run via orchestrator (only check 11)
bash .claude/skills/IEO-launch-audit/scripts/audit.sh \
  --checks 11 --report-only

# Run with the rest of the suite
bash .claude/skills/IEO-launch-audit/scripts/audit.sh \
  --checks 1,2,3,4,5,6,7,8,9,10,11 --report-only
```

When invoked via the orchestrator the apex is resolved from
`live_probe_origin` (preferred) or `canonical_origin` in
`.launch-readiness.yml`. The standalone `--apex` flag overrides.

## Configuration

Read from `.launch-readiness.yml`:

| Key | Type | Default | Used for |
|---|---|---|---|
| `live_probe_origin` | string URL | — | Apex to audit (preferred) |
| `canonical_origin` | string URL | — | Apex fallback |
| `indexnow_key` | string | unset | If set, additionally probes `/<key>.txt` in phase F |

If neither origin key is set and `--apex` is not passed, the check
returns a single `NOT_APPLICABLE` finding and exits.

## Failure ratings

- **FAIL:** sitemap unreachable / malformed; sitemap URLs return non-2xx;
  JSON-LD parse errors; pages missing JSON-LD; piece missing
  Article-class type; pages missing `<title>` or `<h1>`; canonical
  pointing at wrong host; rogue `noindex`; broken internal links;
  internal link traverses >1 redirect hop; missing security headers;
  missing `/robots.txt` or `/sitemap.xml` at apex.
- **WARN:** sitemap URLs 308-redirect; missing meta description /
  canonical / og:image; title or meta-description outside SERP-display
  length range; multiple `<h1>` on one page; internal link triggers a
  single redirect hop; internal-link target absent from sitemap;
  meta-description duplicated across pages; security-header values
  inconsistent across pages; `/llms.txt` or `/image-sitemap.xml` not
  served at apex.
- **INFO:** sitemap URLs that aren't linked from the sampled corpus
  (apparent orphans; sample-bounded so mostly false-positive).
- **NOT_APPLICABLE:** no live origin configured.
- **PASS:** everything else.

## How to fix

### Fix 11.A — Sitemap trailing-slash drift

Pick one canonical URL shape (slash or no-slash) and ensure both:
1. The sitemap emitter emits that shape for every URL.
2. The host config doesn't 308-redirect that shape to the other.

For Vercel: set `trailingSlash: false` (or `true`) in `next.config.js`
or use the `cleanUrls` field in `vercel.json`. For Cloudflare Pages:
configure under "Settings → Builds & deployments → Routing."

**Auto-fix safety: manual** (touches host config + emitter logic).

### Fix 11.B — Per-piece JSON-LD missing

Verify the piece template emits a JSON-LD `<script>` block at render
time, not at build time only. Common bug: server-side template emits
JSON-LD but client-side hydration discards it. Render JSON-LD in the
static HTML, not via React/Vue.

**Auto-fix safety: manual** (touches render pipeline).

### Fix 11.C — Missing canonical / og:image on home + about

Static pages (home, about, contact) often slip through emitters that
only handle dynamic content routes. Add a default head template that
emits canonical + og:image for every route, with overrides per page.

**Auto-fix safety: manual** (touches template layer).

### Fix 11.E — Security-header inconsistency

Common cause: `vercel.json` `source` field uses `/` (matches only
home) instead of `/(.*)` (matches all routes). Fix:

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains; preload" }
      ]
    }
  ]
}
```

**Auto-fix safety: manual** (host config).

## Implementation notes

`scripts/check-live-apex.py`:

1. Resolves apex from `--apex` CLI flag, then `live_probe_origin`,
   then `canonical_origin`. Returns `NOT_APPLICABLE` if none set.
2. Uses a browser-shaped `User-Agent` header (CF + other CDNs block
   default Python UA).
3. `random.seed(42)` makes the piece sample deterministic across
   runs so the JSON report diffs cleanly.
4. Article-baseline check accepts `Article` + Schema.org subtypes
   (`NewsArticle`, `BlogPosting`, `ScholarlyArticle`, `TechArticle`,
   `Report`). False-positive otherwise.
5. Stdlib-only (no `requests`, no `httpx`, no `lxml`).
6. ~60-90s wall clock for a 250-URL sitemap on a typical CDN. The
   reachability sweep is the slowest phase.
7. Default piece sample is 18 (plus home + about → 20 pages). Phases
   B, C, G, J all reuse the same fetched HTML cache; phases D, H, I
   reuse the same 5-piece link sample. Adding a phase to the script
   should NOT add a fresh fetch budget — collect once, use across
   phases.
8. Phase H follows redirects manually via a `_NoRedirect` opener so
   hop count is observable; cap is `REDIRECT_MAX_HOPS = 5`.

## Cited research

- [Google Search Central — Sitemaps overview](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview)
- [Schema.org — Article hierarchy](https://schema.org/Article) (NewsArticle, BlogPosting, ScholarlyArticle subtypes)
- [Google Search Central — Robots meta](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)
- [MDN — Canonical link element](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/canonical)
