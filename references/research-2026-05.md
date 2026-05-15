# Research synthesis — 2026-05-13

Source-of-truth research summary that informed the v0.1.0 check
definitions. Captured here so the skill remains cite-able + the
provenance survives future best-practice shifts.

## Provenance

Four parallel research subagents dispatched 2026-05-13:

1. **SEO best practices for internal linking** — Google PageRank,
   anchor text, topical relevance, automated vs LLM-curated linking
   tooling.
2. **GEO and LLM citation behavior** — Perplexity / ChatGPT / Claude /
   Gemini citation pipelines, JSON-LD mentions[] impact, llms.txt
   adoption.
3. **UX patterns for editorial sites** — Stratechery, Paul Graham,
   Astral Codex Ten, gwern.net, NYT/New Yorker. Hover cards, sidenotes,
   end-of-piece recirculation.
4. **AI-bot directives + entity graph** — robots.txt user-agents,
   llms.txt status, Wikidata Q-IDs, sameAs reciprocity, IndexNow.

Plus an earlier four-subagent pass on 2026-05-13 covering:

5. **Technical SEO pre-launch checklist** — what external auditors
   flag.
6. **Schema.org graph completeness for editorial sites** — what types
   beyond Article should be emitted.
7. **GEO content-level tactics** — what moves LLM citation rates.
8. **llms.txt + AI bots + Wikidata 2026** — current adoption status.

## Convergent findings across all eight passes

### Inline linking

Mechanical TFIDF-distinctive-phrase auto-injection is **obsolete** as
of 2025-2026 tooling. The current floor is LLM-curated + human-approved
(Link Whisper, Linksy, AI Link Genius, Linkbot — pivoted between 2024
and 2026). Pure phrase-matching no longer passes external SEO audits
because topical-cluster discipline replaced it.

Single-word generic anchors (e.g., "latency") linking across pillar
boundaries is a documented anti-pattern that dilutes the cluster signal
LLMs and Google use to determine topical authority. The fix is sparse,
hand-curated, named-concept anchors (Stratechery/PG model) or LLM-curated
inline proposals with operator ratification.

### LLM citation pipeline

Perplexity (Sonar / pplx-embed-context-v1, Feb 2025-2026), ChatGPT
search, Claude.ai web, Bing Copilot all use **chunk-and-embed** retrieval
at query time, NOT link-graph traversal. Internal `<a href>` is not a
documented ranking input for any of them. JSON-LD `mentions[]` /
`sameAs` / clean entity graph is the structured-data signal these
systems actually read — confirmed publicly by Microsoft (March 2025) and
Google Search Central (April 2025).

The Princeton/Georgia Tech paper (Aggarwal et al., KDD 2024) measured
9 content tactics; internal linking was not a measured variable. The
content-side levers that DID move LLM visibility: Cite Sources (+30%),
Quotations (+35%), Statistics (+37%). 2026 follow-ups added Q&A
formatting (+40%) and first-party data (+30-40%).

### Editorial UX

Top essay sites (Stratechery, Paul Graham, Astral Codex Ten, gwern.net)
use **sparse** inline linking limited to named concepts that load-bear
on the current claim. Density target well under 1 internal link per 500
words. gwern.net is the most engineered case: hover-card previews on
every internal link, sidenotes instead of footnotes on wide viewports,
bidirectional backlinks per page. LessWrong and Substack ship hover-card
previews natively as of 2025.

NYT / New Yorker / Wired feature long-form: 3 hand-picked "Read next"
cards at the foot, not algorithmic. Operator-curated, per piece.

Cognitive-load research (DeStefano & LeFevre 2007; Springer Educ Psych
Review 2021): more inline links = higher extraneous load; links to
semantically distant targets degrade comprehension more than links to
closely related ones. Restricted access + visible link types + hierarchy
is the design principle, exactly what hover-card previews and end-of-
piece curated blocks provide and what TFIDF auto-injection violates.

### Schema.org structural gaps

The 2026 best-practice graph for an editorial author site:

- `WebSite` root at `/#website` with `publisher` → Person `@id`
- Absolute @id URLs (`https://example.com/#person` not `#person`)
- Per-page `WebPage` wrapper
- Person: `hasOccupation`, `mainEntityOfPage`, `image` (→ ImageObject)
- Article: `about` (→ DefinedTerm with sameAs to Wikipedia/Wikidata),
  `articleSection`, `publisher`, `copyrightHolder`, `copyrightYear`
- `ImageObject` for every hero image
- `CollectionPage.mainEntity` → `ItemList` with `numberOfItems` +
  `ListItem[]`
- ProfilePage `hasPart` referencing every authored Article @id
- Speakable selectors as array of multiple shallow selectors

The December 2024 study found no statistically significant correlation
between schema *coverage* and LLM citation *frequency*. The consensus
across Microsoft (March 2025) and Google (April 2025) confirmations is
that schema increases citation *accuracy* — when cited, cited correctly
— which is what an editorial site optimizing for entity-graph
disambiguation wants.

### AI-bot directives 2026

The "three-bot" pattern: training-class (`GPTBot`, `ClaudeBot`,
`Google-Extended`, `CCBot`, `Applebot-Extended`), citation-class
(`OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, `Bingbot`,
`Applebot`, `DuckAssistBot`, `MistralAI-User`, `GoogleOther`,
`Google-NotebookLM`, `Amazonbot`, `Meta-ExternalAgent`), and user-fetch
(`ChatGPT-User`, `Claude-User`, `Perplexity-User`).

Bytespider (ByteDance/TikTok) ignores robots.txt; edge/WAF block
required for actual enforcement.

`llms.txt` is read aspirationally — near-zero direct LLM crawler
consumption — but feeds developer-side agents (Cursor, Aider, Cline,
MCP servers). Cheap to ship; signals editorial intent. Anthropic /
Vercel / LangGraph ship `llms.txt` + `llms-full.txt` pair.

`ai.txt` and `agent.txt` are not adopted standards as of 2026.
`AGENTS.md` (Linux Foundation Agentic AI Foundation) is repo-side, not
site-side.

### Wikidata + entity graph

Wikidata is the canonical entity hub for Google KG, Apple Spotlight,
Bing, and increasingly Anthropic / OpenAI / Perplexity disambiguation.
Best-practice wiring:
- Person `sameAs` → full Wikidata URL (not bare Q-ID)
- **Wikidata P856 (official website) → apex domain** — single
  highest-leverage entity-graph edge
- Properties to populate on Q-ID: P31, P735, P734, P101, P39, P106,
  P21, P27
- Reciprocity: LinkedIn / GitHub / Crunchbase "Website" field points
  at apex (operator-side; not enforced here)

Knowledge Panel eligibility in 2026 is gated on triangulated entity
claims, not on Wikipedia article presence.

## Convergent recommendation summary

These eight findings converge on a coherent posture for 2026 editorial-
site launch:

1. **Strip mechanical TFIDF auto-injection.** Replace with hand-
   curated or LLM-curated sparse inline linking + end-of-piece
   recirculation.
2. **Expand schema graph completeness.** WebSite root, absolute @ids,
   ImageObject, ItemList nesting, ProfilePage hasPart.
3. **Address all citation-class AI bots explicitly + make training-class
   policy visible.** Edge-block Bytespider.
4. **Set Wikidata P856.** Single highest-leverage entity-graph move.
5. **Set HSTS + CSP + Permissions-Policy + nosniff + Referrer-Policy
   headers.**
6. **Hero `<img>` gets fetchpriority + width/height + eager loading**
   for LCP+CLS.
7. **Sitemap lastmod must reflect real mtimes** — Google verifies in
   2026.
8. **IndexNow key + publish hook** for Bing/Yandex/Naver coverage.

## Sources

### Pass 1 (SEO internal linking)

- Search Engine Journal — Google's Internal Anchor Text (Jun 2020)
- Yoast — Related posts in WordPress (Aug 2020)
- Semrush — Internal Links Ultimate Guide
- Search Engine Land — Internal linking for SEO
- Ahrefs — Internal Links for SEO Guide
- Ahrefs — Topic Clusters in 10 Minutes
- Search Engine Roundtable — No Internal Linking Over-Optimization Penalty
- SearchAtlas — 9 Automated Internal Linking Tools (2025)
- Techoclock — Best AI Internal Linking Tools (2026)
- TopicalMap.ai — Internal Linking for Topic Clusters (2026)

### Pass 2 (LLM citation pipeline)

- Aggarwal et al., GEO paper, arXiv 2311.09735, KDD 2024
- Perplexity, pplx-embed announcement (Feb 2025)
- Growth Marshal — 2025 Perplexity Playbook
- ZipTie — How Perplexity AI Answers Work
- Search Engine Land — Technical SEO blueprint for GEO (2025)
- Search Engine Land — How schema markup fits into AI search
- Belmore Digital — Does Schema Markup Help LLMs (May 2026)
- Lily Ray — Your GEO Strategy Might Be Destroying Your SEO
- Evil Martians — 6 techniques that work, 8 that don't
- TryProfound — AI Platform Citation Patterns
- Yext — AI Visibility in 2025

### Pass 3 (Editorial UX patterns)

- Cognitive load in hypertext reading (DeStefano & LeFevre, ScienceDirect)
- Understanding Cognitive Load in Digital and Online Learning (Springer)
- Design Of This Website — gwern.net
- Sidenotes In Web Design — gwern.net
- Paul Graham — Essays
- Astral Codex Ten
- LessWrong — Support for Footnotes (hover previews)
- How the New York Times A/B tests their headlines
- Designing Pillar Pages for Maximum SEO Impact — Siteimprove

### Pass 4 (AI bots + Wikidata)

- LLMs.txt: Why AI Crawlers Ignore It (audit)
- llms.txt Explained (May 2026)
- The AI User-Agent Landscape in 2026
- ai-robots-txt project
- Anthropic three-bot framework
- OpenAI crawlers overview
- Wikidata for SEO (2026)
- How to Get a Knowledge Panel (2026)
- Wikidata P856 property talk
- IndexNow guide 2026
- IndexNow vs Sitemap 2026

### Pass 5 (technical SEO checklist) + 6 (schema completeness) + 7 (content tactics) + 8 (status update)

All cited inline in `checks/NN-*.md`.
