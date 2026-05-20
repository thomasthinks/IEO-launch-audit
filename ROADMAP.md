# ROADMAP.md — IEO-launch-audit

What's beyond v1.0. Not a commitment; a holding area for candidates ranked by
"would this catch a class of finding the skill misses today, and is it
portable across consumers."

## v1.4 shipped (2026-05-20)

A two-pass GEO/pGEO recursive-research arc surfaced six candidates;
verification subagents (NLWeb portability, Bing AI Performance API
status, Claude `web_search` source-preference claims) killed three.
The three that survived ship in v1.4. Plus the v1.3.2 dogfooding patch
(check 9 preamble + ADR pattern 4) which was itself surfaced by the
same research pass.

- **Check 14 — multimodal markup (figcaption + alt-text + HTML tables).**
  Opt-in via `multimodal_markup_check: true`. Walks sampled HTML,
  audits figcaption density on content `<img>` tags + alt-text density
  + `<table>` presence. Backed by SearchVIU 2025 + Williams-Cook Duck
  Test (Feb 2026) for the "visible HTML wins" principle; Aleyda Solís
  AI-search checklist for the practitioner-tier figcaption + HTML-table
  recommendations. Default INFO/PASS; WARN only on unambiguously sparse
  pages with ≥3 content images. ~280 lines stdlib Python.

- **Check 11 — measurement-variance advisory (doc patch).** Surfaces
  the stochasticity of LLM citation outputs (arXiv:2604.07585 +
  arXiv:2603.08924) so consumers using Profound / Otterly /
  BrightEdge / 5W / Brave for post-launch citation tracking don't
  misinterpret single-shot measurements. Recommends n≥5 per query
  with stratified prompt variants.

- **Check 9 — citation-absorption framing (doc patch).** Distinguishes
  retrieval ≠ citation ≠ answer influence. arXiv:2604.25707 +
  AirOps 548K-page study (85% retrieved-never-cited) + Kevin Indig
  ghost-citation rate (61.7%). Surfaces that optimizing for citation
  count is coarser than optimizing for absorption.

- **Check 2 — Google "AI features" schema tension (doc patch).**
  Google's [AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
  states schema is not required for AI features specifically. Cross-
  refs to check 14 (visible HTML) as the load-bearing surface for
  Google AI surfaces. Schema remains load-bearing for rich-results +
  non-Google engines.

- **Checks 5 + 10 — cited-source concentration framing (doc patches).**
  Nature Communications 2025 measured citation concentration: n<10
  URLs cover 80% of LLM responses per query. Implies entity-hub
  presence (check 5) and authoritative backlink quality (check 10)
  matter disproportionately because once a site enters the top-cited
  set for a topic, it locks in. Cross-reference framing only; no new
  emitters.

## v1.3 shipped (2026-05-15)

All seven Phase-2-verified candidates landed in v1.3 — see
`CHANGELOG.md` § [1.3.0]. The slate below remains as historical
context for what was verified and what shipped where.

## v1.3 candidates (Phase-2-verified, shipped)

Seven candidates promoted from the May-2026 recursive-research pass (five
discovery + six verification subagents). Each survived both Phase-2 evidence
review and (where applicable) local validation against
`thomasjankowski-site`. Rank order: highest-confidence + highest-leverage
first.

### 1. Schema↔visible-text parity check

**Verdict: PASS.** Two independent controlled tests (SearchVIU 2025, Williams-Cook "Duck Test" early 2026) show LLM fetchers tokenize JSON-LD as raw text — content present only in schema (not in DOM) is functionally invisible. Google's own [General Structured Data Guidelines](https://developers.google.com/search/docs/appearance/structured-data/sd-policies) state: *"Don't mark up content that is not visible to readers of the page."*

**Local validation on `thomasjankowski-site` confirmed real signal:** 5/5 sampled pages have Person `description` + `hasOccupation.name` in schema only, not in DOM.

Audit shape: strip HTML → text, extract JSON-LD string-valued fields (`name`, `description`, `headline`, `articleBody`, `about.name`), flag any string >5 tokens absent from stripped text. Stdlib + `re`. ~30 lines.

Refresh cadence: semi-annual. Obsolescence trigger: any LLM vendor announcing semantic JSON-LD parsing in fetch pipeline (currently none have).

### 2. Per-engine freshness bands + substantive-delta detection

**Verdict: PASS** (substantive-delta) + **NUANCED → REFRAME** (the prior 13-week global cliff candidate is replaced).

The 13-week cliff figure traces to one source (Amsive) laundered across vendors — drop. Replace with per-engine bands keyed on `target_engines:` config: ~30d Perplexity, ~90d ChatGPT, ~6-12mo AI Overviews. Per-engine evidence: Profound, BrightEdge, ConvertMate, Ahrefs.

Substantive-delta detection: Mueller on record + December 2025 core update enforcement. Cosmetic `dateModified` flips no longer trigger freshness boost. Stdlib-feasible via Wayback CDX content-digest API (cheap; identical digests = bit-identical = cosmetic) + `difflib.SequenceMatcher` on visible-text diff only when digests differ. <10% delta = cosmetic.

Don't add portfolio-% thresholds (no primary research). Emit distribution as INFO; operator decides.

Refresh cadence: quarterly. Obsolescence trigger: AI engines move from real-time search-grounding to longer-cached indexes.

### 3. Entity-hub `sameAs` coverage probe

**Verdict: PARTIAL probe — covers both top-15 domain concentration and Google AI-Mode self-citation insights with one ~20-line extension.**

Extends existing `check 5` (Wikidata) and/or `check 2.3` (Person.sameAs). Enumerate top-tier entity hubs (Wikipedia, Wikidata, LinkedIn, YouTube channel, Reddit, GitHub, ORCID, Crunchbase, GBP). Flag missing hubs as INFO.

Source evidence: [5W AI Platform Citation Source Index 2026](https://www.prnewswire.com/news-releases/5w-releases-ai-platform-citation-source-index-2026-the-50-websites-that-now-decide-what-brands-are-visible-inside-chatgpt-claude-perplexity-gemini-and-google-ai-overviews-302759804.html); [SE Ranking 1.3M-citation study on Google AI-Mode self-citation 17.42%](https://seranking.com/blog/google-links-in-ai-mode-answers/).

**Local validation on TJ:** 5/10 hubs present (Wikidata, LinkedIn, GitHub, Crunchbase, X/Twitter). 5 missing (Wikipedia, YouTube, Reddit, ORCID, Mastodon). Surfaces actionable INFO findings.

Refresh cadence: quarterly (5W revises quarterly). Obsolescence trigger: a hub gets de-listed from citation share (cf Reddit's Sept 2025 ChatGPT-share collapse).

### 4. Query Fan-Out heuristic proxy + INFO advisory (hybrid)

**Verdict: NUANCED.** Mechanism is Google-confirmed (Search Central + I/O 2025 blog); the 68% non-top-10 figure is corroborated by Ahrefs Feb 2026 (37.9% top-10 = ~62% not). **But cannot be audited structurally without an LLM/SERP probe** — fan-outs are model-generated and stochastic.

Two-shape ship:

- **(a) Heuristic proxy (stdlib):** ≥3 question-shaped H2/H3s per page, entity diversity in headings, FAQ/HowTo schema presence, passage-length variety (40-150 word LLM-friendly chunks). Framed as "retrievability proxy," not "fan-out coverage."
- **(b) Operator INFO advisory:** one finding pointing at Locomotive / QueryBurst / Otterly for true fan-out audits. Honest about the gap.

Park (c) **opt-in LLM probe** for v1.4 — mirrors the v0.5 curation-scaffold pattern (driver creates batches; subagent dispatches).

Refresh cadence: 6 months. Obsolescence trigger: AI Mode pipeline change (Gemini-4, Deep Search expansion).

### 5. @graph consolidation INFO (forward-looking)

**Verdict: NUANCED.** Microsoft NLWeb is shipping (Yoast 27.1 March 2026 aggregator endpoint; Cloudflare AI Search integration; Tripadvisor / O'Reilly pioneer integrations). But "fragmented loses vs consolidated" is architectural inference — no controlled-test comparing fragmented vs consolidated @graph in current LLM citation rates exists.

Audit shape: count distinct `@graph` blocks per page; count `@id` cross-references between entities; flag fragmented (>1 block or zero cross-refs). INFO-tier only; "you're not blocked from the NLWeb path," not "fragmented sites are penalized today."

**Local validation on TJ:** 742 nodes, 742 distinct @ids, 2148 cross-references. TJ is already the consolidated pattern; check would PASS.

Refresh cadence: quarterly through 2026, then semi-annual. Obsolescence trigger: LLM vendor announces direct `/mcp` consumption OR Web Almanac reports @graph consolidation crossing some threshold.

### 6. `about` vs `mentions` usage INFO (advisory)

**Verdict: NUANCED.** Schema.org defines the semantic distinction (`about` = primary entities; `mentions` = secondary references), but **no Google primary doc differentiates ranking weight**. Mueller on record: Google "rarely learns anything unique from structured data."

Audit shape: count `about` array length per article (flag >3 or 0); count `mentions`; flag pages with `mentions` but no `about`. ~20 lines. INFO advisory only.

Refresh cadence: annual. Slowest-moving of the seven candidates. Obsolescence trigger: any Google rep / doc differentiating, OR measured citation-rate study comparing about-vs-mentions.

### 7. C2PA / IPTC `digitalSourceType` for AI-generated imagery (narrow ship)

**Verdict: SHIP NARROW.** Provenance metadata is **not** confirmed as organic-search ranking or AI-engine citation signal in 2026. BUT: [Google Merchant Center](https://support.google.com/merchants/answer/14743464) mandates `TrainedAlgorithmicMedia` for AI product images and demotes non-compliant listings. That's distribution-affecting, SEO-side (not regulatory).

Distinct from the declined-scope EU AI Act Article 50 check: this is indexing-side enforcement, not compliance. Reconciliation OK.

Audit shape: stdlib XMP parsing from JPEG/PNG/WebP `og:image` / `twitter:image` targets. ~50-150ms per image. Gated on operator declaration:

```yaml
# .launch-readiness.yml
ai_generated_imagery: true   # operator declares site uses gen-AI images
merchant_feed: true          # optional: site syndicates to Google Merchant
```

Skip silently when unset; default-off. WARN when AI-gen imagery declared but `digitalSourceType` absent.

Refresh cadence: quarterly (Merchant Center policy + IPTC adoption rates).

## v1.5+ candidates (longer-trail)

Each entry surfaced during research but did not survive steelman for
v1.4. Logged here as the "wait until X changes" list — held under
specific testable triggers, not generic "someday."

### NLWeb / `schemamap` endpoint detection

**Held — defer to v1.5+ pending two specific signals.** NLWeb (Microsoft,
2025) is a real protocol with reference impl + Cloudflare adoption.
But: the canonical `/ask` endpoint is **dynamic-only** — it requires
per-request natural-language processing against an index, which rules
out pure SSGs (Hugo, Eleventy, Astro static export) without a serverless
layer. Yoast 27.1's "schemamap" (March 2026) is the adjacent
consolidation pattern but is WordPress-bound at the URL level
(`/wp-json/yoast/v1/schema-aggregator/get-schema/...`) and Yoast itself
calls it "proposed," not standardized. **No LLM engine has publicly
confirmed parsing either endpoint for citation eligibility.**

What would unblock v1.5+ promotion:

1. A portable static-file variant of `schemamap` (e.g., a
   `.well-known/schemamap.json` IETF / W3C / WHATWG draft, or a Microsoft
   spec doc at `nlweb.ai/spec`).
2. At least one LLM engine (OpenAI, Perplexity, Anthropic, Google)
   publishing that it consumes the endpoint.

Until both: don't recommend the endpoint. Don't even emit an INFO
advisory — that's vendor-watch noise without engine-parsing evidence
and would violate ADR 0001 pattern 2 (recommending products / surfaces
not confirmed to be operational).

### Bing AI Performance dashboard API integration

**Held — defer until Microsoft exposes the data via API.** The Feb 2026
announcement of Bing Webmaster Tools "AI Performance" dashboard exposes
per-page Copilot citation counts + grounding queries — but **UI-only,
no API**. Microsoft confirmed verbatim on learn.microsoft.com Q&A: *"In
the Blog post, no API is mentioned so the answer is not right now."*
The skill is stdlib-Python; it cannot scrape an authenticated SPA
dashboard without a Selenium/Playwright dependency, which violates the
stdlib-only stance.

Unblock when `learn.microsoft.com/en-us/bingwebmaster/` adds an
AI-Performance endpoint. Check 12 already integrates the existing Bing
Webmaster API; adding the AI-Performance fetcher is then a small extension.

### LLM probe for check 9 Query Fan-Out (deferred from v1.3)

Opt-in LLM probe that mirrors the v0.5 curation-scaffold pattern:
driver creates batches, subagent dispatches an LLM to enumerate
probable fan-out queries for the consumer's content. Held — needs a
clean opt-in API surface that doesn't bind the skill to a specific LLM
provider. Plausible v1.5+ once the surface design is clear.

### GSC live-API integration (service-account JWT or 3-legged OAuth)

v1.2 shipped the GSC snapshot-reader path (operator exports Index Coverage
JSON; audit reads it). The trade is operator-side staleness — re-export
periodically. v1.3 would close that loop with live GSC API integration:
service-account credentials → JWT signed with RSA-SHA256 → OAuth token →
`searchconsole.googleapis.com/v1/sites/<site>/searchAnalytics/query` and
`v1/urlInspection/index:inspect`.

Auth complexity is the open question. RSA-SHA256 signing isn't in Python's
stdlib (`hashlib` has the hash, but no RSA private-key signing). Two paths:
- **Optional dependency on `cryptography`** — clean code, but breaks the
  stdlib-only stance.
- **Shell out to `openssl rsa`** — keeps stdlib-only at the cost of a new
  binary dependency (openssl is near-universal on Linux/Mac; less reliable
  on Windows but the rest of the skill assumes Unix-ish env).

Decision deferred to when a consumer pushes for it. Until then, the
snapshot-reader path (v1.2) is the working answer.

### Real-user CrUX dashboard / longer-trend analysis

v1.2 shipped `crux-trend.py` (append-per-run CSV + direction summary). The
next layer would be a "show me the last N runs as ASCII line charts" or
"alert when category regresses 2 runs in a row" feature. Tradeoff: this
drifts from "audit per build" toward "monitoring product," which is
arguably out-of-scope. Holding for now; v1.2's CSV is the substrate.

## Standing principles (gate for what gets in)

Pulled verbatim from `CLAUDE.md` § Standing principles — repeated here
because the roadmap reviews against them:

- **Standalone-runnable.** Every check is invokable on its own.
- **Audit-budget-aware.** New checks add minutes only when they catch a
  class of finding the existing checks can't.
- **Graceful degrade.** No hard-fail on absent config / API keys.
- **Portable / no consumer-specific assumptions.** No hardcoded paths,
  domain names, or `.launch-readiness.yml` schema assumptions beyond
  documented keys.

A candidate that violates any of the four needs a documented justification
in the version's CHANGELOG entry; otherwise it doesn't ship.

## Out-of-scope (declined)

- **Building a hosted dashboard.** The skill is a CLI / Claude-Code-skill
  artifact, not a SaaS surface. If someone wants a dashboard, they wrap
  the JSON output.
- **Crawl-the-whole-site mode.** Screaming Frog and Sitebulb do this well;
  the skill's edge is the synthesis layer (SEO + IEO + GEO best practices)
  + the consumer-repo-side checks (1-10) the crawlers can't see. Doubling
  the SF surface dilutes both edges.
- **Paid-API requirement.** PSI / CrUX / OPR are opt-in; the skill must
  ship a useful audit with zero API keys. Anything that makes a paid key
  required is declined on portability grounds.
- **Regulatory-compliance auditing (EU AI Act, CCPA, DSA, etc.).** Different
  audit class from SEO/IEO/GEO — compliance is lawyer territory, not
  crawler territory. EU AI Act Article 50 (the most-asked-about 2026
  surface) imposes machine-readable marking on AI *providers* (model labs)
  and visible disclosure on *deployers* publishing AI content on matters of
  public interest, with an editorial-control exemption that covers most
  human-edited sites. Enforcement priority is providers + large platforms,
  not individual essay/blog sites. Out of scope; consult counsel.
