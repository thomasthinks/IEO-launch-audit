# Check 04 — Core Web Vitals (LCP / INP / CLS)

## Why this matters

Core Web Vitals are a confirmed Google ranking factor (Page Experience
update, 2021; INP replaced FID March 2024). In 2026, PageSpeed Insights
weights INP heavily; static sites with hydration-heavy JS frameworks
commonly fail INP even when LCP is green. Lighthouse is the canonical
local validator; CrUX (Chrome User Experience Report) is the field-data
truth source once a site has real traffic.

This check delegates to `vercel:performance-optimizer` skill if available
(Vercel/Next.js stack). When `pagespeed_api_key` is configured it calls
PageSpeed Insights v5 for real Lighthouse data. Otherwise falls back to a
local Lighthouse CLI run, or to MANUAL_VERIFY with PSI instructions.

**Cited sources:** web.dev/articles/vitals (current); Google Search
Central — Page Experience; PageSpeed Insights documentation.

## PageSpeed Insights integration (opt-in)

When config + token are both present, the check fires PSI calls for
`canonical_origin/` (home) + N randomly sampled piece URLs from the live
sitemap. Both Lighthouse category scores and CWV-class audits are parsed.

### Config keys (`.launch-readiness.yml`)

| Key | Type | Default | Purpose |
|---|---|---|---|
| `pagespeed_api_key` | string | unset | PSI v5 API key (inline; convenient for one-offs, not recommended for committed configs) |
| `pagespeed_secret_path` | string | unset | Path to SOPS-encrypted YAML with `PAGESPEED_API_KEY:` line. Mirrors `cloudflare_secret_path`. |
| `pagespeed_sample_urls` | int | 3 | How many piece URLs to sample beyond home. Cost-controlling. |
| `pagespeed_strategy` | string | mobile | `mobile`, `desktop`, or `both`. `both` doubles cost. |
| `pagespeed_include_crux` | bool | true | Parse CrUX field data from the same PSI responses. No extra API cost; flip off only to suppress CrUX findings when running pre-traffic and the `NOT_APPLICABLE` noise gets annoying. |

Token-resolution priority: `PAGESPEED_API_KEY` env var, then inline
`pagespeed_api_key`, then SOPS-decrypted `pagespeed_secret_path`. None of
the three reachable means PSI is skipped; existing offline + lighthouse
CLI behaviour is preserved.

### Cost shape

PSI is slow (~25-40s per URL per strategy on the server-side; PSI runs
Lighthouse on Google infrastructure and round-trips lab data). A default
audit (home + 3 sampled pieces, mobile-only) takes ~2-3 minutes. `both`
strategy doubles that to ~4-6 minutes. PSI's free quota is 25,000
requests/day per key; default audit consumes 4 requests per run.

On HTTP 429 (quota exhausted), the audit degrades to WARN with diagnostic
and does not block the rest of the run. Other API errors degrade the same
way. PSI quota resets daily at Pacific midnight.

### Emitted findings

| ID | Severity model |
|---|---|
| `4.psi.detail` | INFO — full per-URL category + CWV distribution |
| `4.psi.scores` | PASS if all category scores >=0.9; WARN if any in 0.7-0.9; FAIL if any <0.7 |
| `4.psi.lcp` | PASS if LCP <=2.5s; WARN if <=4s; FAIL otherwise |
| `4.psi.cls` | PASS if CLS <=0.1; WARN if <=0.25; FAIL otherwise |
| `4.psi.tbt` | PASS if TBT <=200ms; WARN if <=600ms; FAIL otherwise (lab proxy for INP) |
| `4.psi.rate_limited` | WARN — all PSI calls hit 429 (quota exhausted) |
| `4.psi.all_failed` | WARN — all PSI calls failed for non-429 reasons |
| `4.psi.partial_errors` | INFO — some calls failed while others succeeded |
| `4.crux.page_lcp` | PASS if CrUX page-level LCP category=FAST; WARN if AVERAGE; FAIL if SLOW; NOT_APPLICABLE if not yet populated |
| `4.crux.page_cls` | PASS/WARN/FAIL/NOT_APPLICABLE per CrUX page-level CLS category |
| `4.crux.page_inp` | PASS/WARN/FAIL/NOT_APPLICABLE per CrUX page-level INP category (replaced FID, March 2024) |
| `4.crux.origin_lcp` | PASS/WARN/FAIL/NOT_APPLICABLE per CrUX origin-level LCP category |
| `4.crux.origin_cls` | PASS/WARN/FAIL/NOT_APPLICABLE per CrUX origin-level CLS category |
| `4.crux.origin_inp` | PASS/WARN/FAIL/NOT_APPLICABLE per CrUX origin-level INP category |
| `4.crux.summary` | INFO — full per-row CrUX distribution + percentile data for human review |
| `4.crux.no_data` | INFO — single line when neither page- nor origin-level CrUX has data (e.g. site too new) |

CrUX field-data INP is the actual ranking signal; PSI's lab TBT is the
best lab proxy available without real-user traffic.

### Lab vs field — what the two data sources tell you

PSI returns two distinct flavors of CWV data in the same response:

- **Lab data** (Lighthouse — surfaces under `4.psi.*`): synthetic Chrome
  on a controlled connection (mobile slow-4G profile by default). Always
  available, deterministic, no traffic required. Use pre-launch to catch
  regressions before they ship.
- **Field data** (CrUX — surfaces under `4.crux.*`): real-user Chrome
  installs aggregated over the trailing 28 days, bucketed at the 75th
  percentile. Needs ~28 days of traffic to populate. This is the canonical
  Core Web Vitals signal Google Search Console uses for ranking.

CrUX is split into two scopes in the PSI response:

- `loadingExperience` — **page-level**: per-URL aggregate. Sparse; most
  individual pages don't have enough Chrome users to clear CrUX's
  per-URL traffic threshold.
- `originLoaderExperience` — **origin-level**: the entire origin
  aggregated together. Much more often populated; 24M+ origins covered
  by CrUX as of 2026.

The integration parses both blocks from the same PSI response (no extra
API calls), grades each metric on its CrUX category bucket
(FAST / AVERAGE / SLOW maps to PASS / WARN / FAIL), and degrades to
`NOT_APPLICABLE` per-metric when CrUX hasn't populated. When both scopes
are entirely empty (pre-traffic site), a single `4.crux.no_data` INFO
finding fires instead of 6 NOT_APPLICABLE noise lines.

## What's checked

### 4.1 — LCP (Largest Contentful Paint)

Target: ≤ 2.5s at 75th percentile.

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| LCP ≤ 2.5s | yes | 2.5-4.0s | >4.0s |
| LCP element identified (usually hero `<img>`) | yes | — | unidentifiable |

### 4.2 — INP (Interaction to Next Paint)

Target: ≤ 200ms at 75th percentile. Replaced FID March 2024.

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| INP ≤ 200ms | yes | 200-500ms | >500ms |

### 4.3 — CLS (Cumulative Layout Shift)

Target: ≤ 0.1.

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| CLS ≤ 0.1 | yes | 0.1-0.25 | >0.25 |

### 4.4 — Image optimization

| Assertion | Pass | Warn |
|---|---|---|
| Hero images served as AVIF or WebP | yes | only JPG/PNG |
| Modern format negotiation via `<picture>` source or Accept header | yes | no |
| Images compressed (no oversized unoptimized) | yes | files >200KB unoptimized |

### 4.5 — Font loading

| Assertion | Pass | Warn |
|---|---|---|
| Fonts preloaded via `<link rel="preconnect">` | yes | no |
| `font-display: swap` set (no FOIT) | yes | no |
| Self-hosted or CDN with explicit caching | yes | third-party with no cache control |

## How to fix

### Fix 4.1 — Improve LCP

The single biggest win: ensure the hero `<img>` is the LCP element AND
has `fetchpriority="high"` + `loading="eager"`. Preload it:

```html
<link rel="preload" as="image" href="/hero.avif" type="image/avif" fetchpriority="high">
```

If hero is below-the-fold (rare on essay sites), the LCP element is
probably the main heading or first paragraph text. Ensure web fonts are
swap-friendly.

If using `vercel:performance-optimizer` skill, invoke it for stack-specific
LCP audit + recommendations.

**Auto-fix safety: safe** (template-driven preload addition).

### Fix 4.2 — Improve INP

INP measures every interaction's latency, not just first. Hydration-heavy
frameworks (Next.js with heavy client components, Astro with large
islands) commonly fail INP.

Quick wins:
- Move non-critical JS to `defer` or `async`
- Reduce client-side React tree size (lazy-load below-fold components)
- Audit for synchronous heavy work in event handlers
- Use `requestIdleCallback` for non-critical work

For Vercel/Next.js: invoke `vercel:performance-optimizer` for stack-aware
INP audit.

**Auto-fix safety: manual** (requires code refactoring).

### Fix 4.3 — Eliminate CLS

Hero `<img>` must have explicit `width` + `height` attributes (or use
CSS aspect-ratio). Fonts must be loaded with size-adjust to prevent
FOIT/FOUT layout shifts.

```css
@font-face {
  font-family: 'CustomFont';
  src: url('/font.woff2') format('woff2');
  font-display: swap;
  size-adjust: 100%; /* Match fallback metrics */
}
```

**Auto-fix safety: safe** (mechanical attribute addition); **manual**
(font metric matching).

### Fix 4.4 — Image format negotiation

Convert source PNGs/JPGs to AVIF + WebP at build time. For static sites,
ship multiple formats:

```html
<picture>
  <source srcset="/hero.avif" type="image/avif">
  <source srcset="/hero.webp" type="image/webp">
  <img src="/hero.jpg" alt="..." width="1920" height="1080">
</picture>
```

For Next.js: use `<Image>` component which handles this automatically.

**Auto-fix safety: manual** (pipeline change; requires build-side image
processing).

## Failure ratings

- **FAIL:** LCP >4s, INP >500ms, CLS >0.25.
- **WARN:** LCP 2.5-4s, INP 200-500ms, CLS 0.1-0.25, no image
  format negotiation, no font preload.
- **PASS:** all metrics in green range.

## Cited research

- [web.dev — Core Web Vitals (2026)](https://web.dev/articles/vitals)
- [INP becomes Core Web Vital (March 2024)](https://web.dev/blog/inp-cwv-march-12)
- [PageSpeed Insights documentation](https://developers.google.com/speed/docs/insights/v5/about)
- [Lighthouse Performance audits](https://developer.chrome.com/docs/lighthouse/performance/)
- [CrUX (Chrome User Experience Report)](https://developer.chrome.com/docs/crux)

## Implementation notes

This check is the most stack-dependent. Four execution paths, tried in
order:

1. **Vercel/Next.js detected**: invoke `vercel:performance-optimizer`
   skill with a query like "audit Core Web Vitals on this repo." That
   skill has stack-specific knowledge for INP/LCP optimization in
   Next.js (server components, edge runtime, image optimization).

2. **PageSpeed Insights API configured**: when `pagespeed_api_key` is
   reachable (env / inline / SOPS) AND a live origin is set, the check
   calls PSI v5 for home + N sampled pieces and parses category scores +
   CWV audits from `lighthouseResult.categories` and
   `lighthouseResult.audits`. The same responses are also mined for CrUX
   field data (`loadingExperience` page-level + `originLoaderExperience`
   origin-level) and surfaced under `4.crux.*` findings. No extra API
   calls; CrUX rides in the existing PSI response. See "PageSpeed
   Insights integration" + "Lab vs field" above.

3. **Local Lighthouse CLI available**: run `lhci autorun --config=.lighthouserc.json`
   against a local prod build. Results parsed for LCP/INP/CLS. Skipped
   when path 2 already produced field data.

4. **None of the above**: fall back to recommending the operator run
   PageSpeed Insights on the deployed origin manually. Report as
   MANUAL_VERIFY with the URL to run.

The check reports degraded gracefully when no field data exists (pre-flip
sites have no real-user traffic). In that case, it reports lab data from
Lighthouse + flags for post-flip CrUX recheck.
