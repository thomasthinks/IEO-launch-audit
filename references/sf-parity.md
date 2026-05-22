# Screaming Frog SEO Spider parity — coverage map vs IEO-launch-audit skill

**Purpose:** Map every default check Screaming Frog SEO Spider performs (~300+ across 16 categories) against this skill's 14 checks. Identifies (a) what SF catches that IEO doesn't, (b) what IEO catches that SF doesn't, (c) where the two overlap.

**Why this exists:** Operators running the IEO-launch-audit skill before flipping a site live often follow up with a paid SF crawl as a sanity check. Knowing what SF will flag that IEO already covers, and what gaps remain, lets them decide whether to: (i) treat SF as redundant, (ii) close specific IEO gaps before the SF run, or (iii) keep SF as a supplemental check for surfaces IEO intentionally doesn't address.

**Scope:** SF inventory captured from screamingfrog.co.uk/seo-spider/issues/ (2026-05). IEO check inventory at `checks/01-*` through `checks/14-*` of this skill (v0.4.0+ skill state as of 2026-05-22).

**Not in scope:** SF custom extractions, configurable filters, JavaScript rendering modes, integrations (GSC/GA/PageSpeed/AHrefs/Majestic/Moz), bulk-export views. Those are user-configured surfaces, not default checks.

---

## SF inventory: 16 default check categories

| Category | ~Checks | What SF flags |
|---|---|---|
| Response Codes | 15 | 4XX, 5XX, redirect loops, redirect chains, blocked-by-robots, blocked resources, meta/JS/HTTP refresh redirects |
| Security | 12 | HTTP URLs, mixed content, insecure forms, missing HSTS/CSP/X-Content-Type-Options/X-Frames-Options/Referrer-Policy, bad content-type, unsafe cross-origin links, protocol-relative resources |
| URL | 11 | Multiple slashes, spaces, broken bookmarks, non-ASCII chars, uppercase, repetitive paths, search URLs, query params, GA tracking params, underscores, >115 chars |
| Page Titles | 9 | Missing, multiple, outside `<head>`, duplicate, over/under chars + pixels, title==H1 |
| Meta Description | 8 | Missing, multiple, outside `<head>`, duplicate, over/under chars + pixels |
| H1 | 6 | Missing, multiple, alt-text-as-H1, non-sequential, duplicate, over 70 chars |
| H2 | 5 | Missing, multiple, non-sequential, duplicate, over 70 chars |
| Content | 11 | Exact + near + semantic duplicates, spelling, grammar, soft 404, lorem ipsum, low relevance, low content, readability difficult / very difficult |
| Images | 7 | Missing alt text + attr, background images, over 100kb, alt >100 chars, incorrectly sized, missing size attrs |
| Canonicals | 10 | Multiple conflicting, non-indexable canonical, invalid attr, fragment URL, outside `<head>`, canonicalized, missing, unlinked, multiple, relative URLs |
| Pagination | 7 | URL not in anchor, non-200 pagination, unlinked pagination, multiple, loop, sequence error, non-indexable |
| Directives | 10 | Outside `<head>`, noimageindex, noindex, nofollow, none, unavailable_after, nosnippet, noodp, noydir, notranslate |
| Hreflang | 12 | Non-200, missing return links, inconsistent codes, non-canonical return links, noindex returns, incorrect codes, multiple entries, missing self-ref, missing x-default, etc. |
| JavaScript | 16 | Noindex/nofollow only in original HTML, canonical mismatch, AJAX hashbang, JS-rendered content/links/titles/descriptions/H1/canonical, JS errors |
| Links | 12 | Outlinks to localhost, uncrawlable internal outlinks, pages without internal outlinks, internal nofollow inlinks/outlinks, high external/internal outlinks, follow+nofollow mix, high crawl depth, missing/non-descriptive anchor text |
| AMP | 16 | Non-200, missing canonical, missing required tags, invalid HTML/AMP boilerplate/charset/viewport, disallowed HTML, other validation |
| Structured Data | 6 | Validation errors + warnings, rich result errors + warnings, parse errors, missing |
| Sitemaps | 6 | Over 50k URLs, over 50mb, URLs not in sitemap, orphan URLs, non-indexable in sitemap, URLs in multiple sitemaps |
| PageSpeed | 19 | LCP request discovery, render-blocking, network dep tree, cache lifetimes, layout shift, image delivery, forced reflow, legacy + duplicated + unused JS, unused + un-minified CSS, DOM size, font display, etc. |
| Mobile | 6 | Viewport not set, content sizing, illegible font, unsupported plugins, target size, mobile alt link |
| Accessibility | 50+ | WCAG 2.0/2.1/2.2 violations via axe-core: ARIA attrs/roles/names, alt text on images/SVG/objects/areas, lang attrs, frame titles, color contrast, focus order, keyboard nav, captions, autoplay, etc. |

**Total: ~245 distinct default checks across 21 categories** (Response Codes 15 + Security 12 + URL 11 + Titles 9 + Meta 8 + H1 6 + H2 5 + Content 11 + Images 7 + Canonicals 10 + Pagination 7 + Directives 10 + Hreflang 12 + JS 16 + Links 12 + AMP 16 + Structured 6 + Sitemaps 6 + PageSpeed 19 + Mobile 6 + Accessibility 50+).

---

## IEO-launch-audit inventory: 14 checks

| Check | Purpose (one-line) |
|---|---|
| 01 — Technical SEO baseline | noindex-from-staging, security headers (HSTS/CSP/Permissions-Policy), soft-404, sitemap lastmod truthfulness, robots.txt sanity |
| 02 — Schema.org graph | JSON-LD per-piece + consolidated graph; Article/Person/WebSite/CollectionPage/BreadcrumbList completeness; CiTO predicate emission; speakable; web-validator fallback |
| 03 — AI-bot directives | robots.txt + llms.txt + llms-full.txt for citation-class crawlers (PerplexityBot, OAI-SearchBot, Claude-SearchBot, etc.) + training-class crawlers |
| 04 — Core Web Vitals | LCP / INP / CLS via Lighthouse + CrUX; hydration-heavy SPA INP failures |
| 05 — Wikidata entity graph | Q-ID present, sameAs reciprocity (Person↔Wikidata), structured properties populated for Knowledge Panel eligibility |
| 06 — IndexNow | keyfile present + Bing/Yandex/Naver/Seznam submission protocol wired |
| 07 — Sitemap accuracy | lastmod truthfulness (matches real mtimes), URLs-in-sitemap == URLs-published, no orphans, valid xml |
| 08 — Internal-link quality | LLM-curated inline links with stable named-concept anchors; flags mechanical TFIDF/keyword-distinctive auto-injection as anti-pattern |
| 09 — Content tactics | GEO posture per Princeton/Georgia Tech KDD 2024 (9 measured tactics for LLM-visibility); advisory |
| 10 — Backlinks | Referring-domain inventory for AI-search triangulation |
| 11 — Live-apex audit | Live-origin behavior the source repo can't see (CDN trailing-slash canonicalization, redirect chains, real response codes) |
| 12 — Search Console cross-verification | Did Google actually accept what the site declared? (indexability state, coverage report, sitemap submission status) |
| 13 — Imagery provenance | C2PA + IPTC `digitalSourceType` for AI-generated images (Merchant-Center mandate, Adobe Content Credentials, etc.) |
| 14 — Multimodal markup | figcaption + alt-text + visible HTML tables (LLM extraction prefers visible HTML over hidden JSON-LD per SearchVIU 2025) |

---

## Parity table — SF category × IEO coverage

Legend:
- **FULL** — IEO covers ≥80% of the SF category's checks
- **PARTIAL** — IEO covers some but not all; specific gaps listed
- **GAP** — IEO does not currently address this SF category; recommendation given
- **N/A** — Out of scope for IEO's editorial-site posture (e.g., AMP, hreflang for single-locale sites)

### Response Codes — PARTIAL
- **Covered:** Check 11 (live-apex) checks live HTTP status for sample URLs; check 07 (sitemap) catches sitemap URLs returning 404 / 5XX.
- **Gap:** SF crawls every URL; IEO samples. No IEO equivalent of redirect-chain detection, JS-redirect detection, meta-refresh detection.
- **Recommendation:** ADD check 11.2 (full-sitemap response-code sweep). Cheap to add (single HEAD per URL, parallel-fetch). Catches the silent-404 case where a sitemap URL stops resolving post-deploy.

### Security — PARTIAL
- **Covered:** Check 01 covers HSTS, CSP, Permissions-Policy presence + value sanity. HTTP URL detection implicit in check 11.
- **Gap:** Mixed-content detection (HTTPS page loading HTTP resource), form-on-HTTP, missing X-Content-Type-Options, missing X-Frames-Options, missing Referrer-Policy, bad content-type headers, unsafe cross-origin links, protocol-relative resource detection.
- **Recommendation:** Expand check 01 to cover the missing header inventory. The CSP/HSTS subset is already there; the others are mechanical header-presence checks of the same shape. ~30-min addition.

### URL — GAP (mostly N/A for editorial sites)
- **N/A:** Editorial sites with hash-routing or static-build slug conventions don't typically emit search URLs, GA tracking params, repetitive paths. URL hygiene is a CMS concern, not editorial.
- **Worth adding:** URL >115 chars (LLM citation surfaces sometimes truncate at ~100 chars per Perplexity / Bing AI Mode observation); URLs containing spaces (build bug); uppercase URLs (Vercel/Cloudflare may serve 200 but Google canonicalises to lowercase, producing duplicate-content drift).
- **Recommendation:** ADD check 01.7 (URL hygiene) as a one-shot sweep over the sitemap URLs. Low value but ~15-min add.

### Page Titles — PARTIAL
- **Covered:** Check 02 (schema graph) validates `headline` per Article; mismatch with rendered `<title>` would be caught at check 14 (multimodal markup) if explicitly compared.
- **Gap:** Title length (chars + pixels), title duplicate-across-pages, title==H1, title outside `<head>`. SF catches all of these mechanically per URL.
- **Recommendation:** ADD check 14.4 (rendered-title sanity). Low effort. Catches the case where `<title>` and JSON-LD `headline` drift, which breaks AI-overview attribution.

### Meta Description — PARTIAL
- **Covered:** Check 02 validates JSON-LD `description` presence. Multimodal check 14 implicitly addresses visible-vs-hidden.
- **Gap:** Description length (chars + pixels), duplicate-across-pages, description outside `<head>`.
- **Recommendation:** Same as titles — fold into check 14 as rendered-meta sanity.

### H1 — PARTIAL
- **Covered:** Check 14 (multimodal) implicitly cares about heading structure for LLM extraction.
- **Gap:** H1 missing, multiple H1s per page, H1 length, H1 duplicate, alt-text-in-H1.
- **Recommendation:** ADD check 14.5 (heading-hierarchy sanity). H1 missing is a real LLM-extraction failure mode (the citation summary uses H1 as the article title).

### H2 — GAP
- **N/A for static-emit sites** where heading discipline is enforced at template level. But for hand-authored content (corpus pieces, drafts), H2 sequence is real.
- **Recommendation:** Optional. Lower priority than H1.

### Content — PARTIAL
- **Covered:** Check 02 catches soft-404 (page returns 200 with 404-like JSON-LD). Check 08 internal-link quality + check 09 content tactics overlap with content depth.
- **Gap:** Exact duplicate, near-duplicate, semantic-similar pages, lorem-ipsum placeholder, low-content pages, readability scoring, spelling + grammar errors.
- **Notable IEO advantage:** "Low relevance content" (SF's term) maps to check 09 GEO content-tactics. IEO is more current on the LLM-citation-relevance signal; SF is more general.
- **Recommendation:** ADD check 09.5 (content-depth sanity) — flag any published piece <300 words; flag any piece identical to another by hash. The semantic-duplicate detection is heavier work; defer until needed.

### Images — PARTIAL
- **Covered:** Check 13 imagery-provenance covers C2PA/IPTC for AI images. Check 02 validates JSON-LD ImageObject.
- **Gap:** Alt text presence/length sanity, image file-size over 100kb, missing width/height attrs, incorrectly-sized images (display vs source dimensions).
- **Recommendation:** ADD check 13.6 (image rendering sanity) — alt-text presence sweep + file-size cap warning + width/height presence. The C2PA/IPTC layer is the unique IEO value; the mechanical alt + size checks are commodity but worth covering.

### Canonicals — GAP
- **Mostly N/A** for hash-routed SPA + single-URL editorial pieces where canonical is mechanically emitted by the build. But for sites with query-string URLs, internal-search URLs, or pagination, canonical hygiene matters.
- **Recommendation:** ADD check 01.8 (canonical-tag sanity) — verifies every URL in sitemap has a canonical, the canonical resolves to itself (no canonical-chain), canonical is absolute (not relative), no fragment in canonical.

### Pagination — N/A
- Out of scope for the static-emit editorial-site posture this skill targets. Pagination is a CMS / listing-page concern.
- **Re-evaluate if:** consumer site uses paginated /writing/page/N/ structure.

### Directives — PARTIAL
- **Covered:** Check 01 verifies no accidental `noindex` from staging; check 03 covers robots.txt directives for AI bots.
- **Gap:** Per-page meta-robots inventory across the sitemap, noimageindex / nosnippet / unavailable_after / notranslate detection.
- **Recommendation:** Expand check 01 with per-sitemap-URL meta-robots inventory. Mostly a sanity check (catches a piece left in noindex by mistake).

### Hreflang — N/A
- Out of scope; this skill targets English-language single-locale editorial sites. Re-evaluate if consumer site is multi-locale.

### JavaScript — PARTIAL
- **Covered:** Check 14 (multimodal) addresses LLM extraction of rendered vs source HTML. Check 11 implicit checks-after-CDN.
- **Gap:** Detection of JS-only content (content present after render but absent in static HTML), JS-only canonical, JS-only meta, JS error console.
- **Notable:** For SSG sites where rendered = source, this category is mostly N/A. For SPA sites where rendering matters, the gaps are real.
- **Recommendation:** ADD check 14.6 (source-vs-rendered diff) — fetch static HTML + rendered HTML for a sample of URLs, compare key elements (title, meta, H1, JSON-LD). Catches the SPA-renders-but-bots-don't-execute-JS failure mode.

### Links — PARTIAL
- **Covered:** Check 08 (internal-link quality) addresses anchor-text + topical relevance for inline links.
- **Gap:** Outlinks-to-localhost (dev leak), pages-without-internal-outlinks (orphan from internal nav), non-descriptive anchor text inventory, high-crawl-depth pages.
- **Recommendation:** Expand check 08 with the orphan + crawl-depth inventory. Single graph-walk over the build's internal link map.

### AMP — N/A
- AMP is effectively deprecated as of 2026 (Google deprecated AMP-Story 2023; AMP-HTML retention scrolling back). Not worth covering.

### Structured Data — FULL
- **Strong overlap.** Check 02 covers the full SF structured-data surface (validation errors, rich-result warnings, parse errors, missing) PLUS additional IEO-specific signal: CiTO predicates, Wikidata sameAs, speakable selectors, web-validator fallback for uncovered types.
- **IEO advantage:** Check 02 audits the full graph at build time (offline + curated rules) rather than per-page at crawl time. Faster, more comprehensive, no rate-limit risk.

### Sitemaps — FULL
- **Strong overlap.** Check 07 (sitemap accuracy) covers lastmod truthfulness + URL inventory match + no orphans. SF's 50k-URL + 50mb cap are mechanical limits IEO doesn't currently enforce but should.
- **Recommendation:** ADD check 07.5 (sitemap size limits) — single-line check, catches the case where a corpus grows past 50k URLs and the sitemap silently becomes invalid.

### PageSpeed — PARTIAL
- **Covered:** Check 04 (Core Web Vitals) covers LCP, INP, CLS via Lighthouse + CrUX.
- **Gap:** SF runs the full PageSpeed Insights audit (render-blocking, unused CSS/JS, font-display, DOM size, etc.). Check 04 reports the headline metrics; SF surfaces the underlying causes.
- **Recommendation:** Check 04 already invokes Lighthouse; surface the Lighthouse `opportunities` section (which IS the PageSpeed cause list) as findings. ~15-min addition to expose what's already computed.

### Mobile — PARTIAL
- **Covered:** Check 04 (CWV) implicitly covers mobile via Lighthouse mobile preset.
- **Gap:** Viewport-tag presence per page, illegible font sanity, target-size (tap targets) inventory.
- **Recommendation:** Surface Lighthouse's mobile-specific findings (already computed) as standalone findings under check 04.

### Accessibility — GAP
- **Not currently covered.** axe-core's 50+ WCAG checks (ARIA, alt text, lang attrs, frame titles, color contrast, focus order, captions, autoplay) are entirely outside IEO's current scope.
- **Recommendation:** ADD check 15 — accessibility (axe-core wrapper). Heavy lift (50+ rules) but axe-core is the canonical engine and runs offline via Lighthouse. Lift: one new check file + Lighthouse `accessibility` category result extraction. Adds material value: WCAG compliance + IEO signal both improve from a11y improvements (semantic HTML is what LLMs extract).

---

## Beyond SF — IEO checks SF doesn't cover

These are the irreducible IEO-specific surfaces. SF will never flag these (different ontology, different optimization target):

| IEO check | What SF doesn't see |
|---|---|
| **03 AI-bot directives** | llms.txt + llms-full.txt + AI-bot allowlist in robots.txt are 2025-2026 IEO-specific; SF doesn't audit them |
| **05 Wikidata entity graph** | Q-ID presence, Person sameAs reciprocity, structured-property completeness for Knowledge Panel; SF is page-level, not entity-graph-level |
| **06 IndexNow** | IndexNow keyfile + protocol wiring; SF doesn't probe IndexNow endpoints |
| **08 Internal-link quality (LLM-curated)** | SF flags missing anchor text / non-descriptive anchors, but doesn't know about the LLM-curated-vs-mechanical-TFIDF distinction. IEO catches the *type* of internal-linking strategy. |
| **09 Content tactics (GEO posture)** | 9-tactic Princeton/Georgia Tech KDD 2024 measurement framework; SF doesn't model LLM-citation-likelihood as a metric |
| **12 Search Console cross-verification** | Did Google actually accept the sitemap? Did pages get indexed? SF crawls what the site SAYS; only GSC says what Google ACCEPTED |
| **13 Imagery provenance (C2PA / IPTC digitalSourceType)** | Merchant-Center AI-image labeling mandate; SF checks alt text + file size but doesn't parse C2PA manifests |
| **14 Multimodal markup (figcaption + visible HTML tables)** | SearchVIU 2025: LLM extraction prefers visible HTML over hidden JSON-LD. SF validates JSON-LD but doesn't model the LLM extraction-preference signal. |

**IEO's specialization:** AI-search / LLM-citation signal (10 of 14 checks). SF's specialization: traditional-search hygiene at scale (~200+ checks per crawl, fully automated). The two are complementary, not redundant.

---

## Recommended new IEO checks (gap-closures)

Ranked by effort + impact:

| New check | Effort | Impact | Surface |
|---|---|---|---|
| **04.b — Lighthouse `opportunities` surface** | XS (15min) | High | Exposes PageSpeed cause-list already computed; closes ~80% of SF's PageSpeed + Mobile gaps in one shot |
| **11.b — Full-sitemap response-code sweep** | XS (15min) | High | Catches silent-404 post-deploy across every published URL |
| **07.b — Sitemap size limits (50k + 50mb)** | XS (5min) | Low (only matters at scale) | Single-line check; cheap insurance |
| **14.b — Rendered title + meta + H1 sanity** | S (30min) | Medium | Catches `<title>` ↔ JSON-LD `headline` drift; H1 missing/multiple |
| **01.b — Expanded security header coverage** | S (30min) | Medium | X-Content-Type-Options + X-Frames-Options + Referrer-Policy + mixed-content detection |
| **08.b — Internal-link orphan + crawl-depth audit** | S (45min) | Medium | Single graph-walk over build's internal link map |
| **14.c — Source-vs-rendered HTML diff** | M (2h) | High (SPA) / Low (SSG) | Catches the SPA-renders-but-bots-don't-execute failure mode; less critical for static sites |
| **15 — Accessibility (axe-core via Lighthouse)** | M (1-2h) | High | Adds new check file + Lighthouse accessibility category extraction; ~50 a11y rules + semantic-HTML lift for LLM extraction |
| **09.b — Content-depth sanity (low-word + duplicate-hash)** | S (45min) | Medium | Flags <300-word pieces; flags identical body hashes; defer semantic-similarity to a v2 |

Total potential additions: 9 new sub-checks, ~6-8 hours engineering, catches ~80% of the SF-only gaps without external-tool dependency.

---

## Decision framework — when to run SF vs rely on IEO

**Run SF when:**
- Site has >1000 URLs (IEO samples; SF crawls full inventory)
- CMS with dynamic URLs / pagination / search results (URL hygiene matters)
- Multi-locale (hreflang matters)
- Accessibility compliance is a hard requirement (a11y in v0.4.0 is GAP)
- Need crawl-graph traversal for orphan / depth analysis at scale

**Rely on IEO when:**
- Static-emit editorial site (<1000 URLs, single locale, no pagination)
- AI-search / LLM-citation optimization is primary goal
- Need offline audit at build-time (no live origin yet)
- Need to track Wikidata + IndexNow + AI-bot directives + C2PA imagery provenance
- Want a single-tool audit before paid-tool spend

**Run both when:** Pre-launch readiness check for a new site, OR post-redesign / migration / re-platforming.

---

## Maintenance

Update this parity doc when:
- SF ships a new check category (their changelog: screamingfrog.co.uk/seo-spider/updates/)
- IEO ships a new check (bumps the 14-check baseline)
- A consumer-site audit surfaces an SF finding the parity doc says IEO should cover

**Version:** v0.1 (2026-05-22)
**Sources:**
- Screaming Frog default-check inventory: https://www.screamingfrog.co.uk/seo-spider/issues/
- IEO-launch-audit skill: this repo's `checks/01-*` through `checks/14-*`
- SearchVIU 2025 multimodal-markup study (referenced in check 14)
- Princeton/Georgia Tech Aggarwal et al. KDD 2024 (referenced in check 09)
