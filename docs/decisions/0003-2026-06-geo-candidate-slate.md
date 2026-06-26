# ADR 0003 — June 2026 GEO / IEO candidate slate

**Status:** Accepted as implementation slate (2026-06-26; code changes
pending)
**Context:** June 2026 research pass across academic GEO papers and
first-party crawler documentation
**Decision:** Promote four candidates into the implementation backlog,
defer two watchlist items, and explicitly reject one tempting but
non-auditable surface.

## Context

The skill already covers the May 2026 GEO baseline: schema-text parity,
AI-bot directives, first-30% content front-loading, freshness discipline,
multi-UA live-apex probing, imagery provenance, and visible multimodal
markup. A June 2026 research pass checked whether new methodology-
disclosed evidence had emerged that justifies adding or reshaping checks.

The strongest new evidence is not another platform-specific ranking
formula. It is a convergence around three themes:

1. **Citation selection and citation absorption are different outcomes.**
   A page can be cited weakly without shaping the answer, or shape an
   answer more deeply when it supplies definitions, comparisons, factual
   support, numerical evidence, code/examples, or procedural steps.
2. **Single-query optimization is fragile.** Multiple 2026 GEO papers
   warn that optimizing a document around one query can create downside
   risk for adjacent intents. Robustness across likely query facets is
   a better audit target than narrow prompt matching.
3. **Crawler access semantics keep moving.** First-party docs now draw
   sharper boundaries between search inclusion, user-triggered fetches,
   training, Gemini grounding, and cache validation behavior.

This ADR translates those findings into implementation recommendations.
Per ADR 0001, claims are constrained to source-supported mechanisms and
avoid invented lift percentages or closed-source ranking weights.

## Sources reviewed

### Methodology-disclosed research

- [From Citation Selection to Citation Absorption](https://arxiv.org/abs/2604.25707)
  (April 2026). Public `geo-citation-lab` dataset; 602 controlled prompts,
  ChatGPT / Google AI Overview-Gemini / Perplexity, 21K+ citations, 18K+
  fetched pages, 72 features. Key usable finding: high-influence pages
  tend to be longer, more structured, semantically aligned, and richer
  in extractable evidence such as definitions, numerical facts,
  comparisons, and procedural steps. Q&A formatting alone is not enough.
- [How Generative AI Disrupts Search](https://arxiv.org/abs/2604.27790)
  (SIGIR 2026). Public benchmark of 11,500 user queries comparing Google
  Search, AI Overviews, and Gemini. Key usable finding: source overlap
  across traditional and generative Google surfaces is low, and websites
  blocking Google's AI crawler are less likely to be retrieved by AIOs.
- [IF-GEO](https://arxiv.org/abs/2601.13938)
  (January 2026). Multi-query GEO framework. Key usable finding:
  document optimization must account for heterogeneous query intents and
  downside risk, not just mean visibility gain.
- [FeatGEO](https://arxiv.org/abs/2604.19113)
  (April 2026). Feature-level optimization over structural, content, and
  linguistic properties. Key usable finding: document-level content
  properties matter more than isolated lexical edits.
- [MAGEO](https://arxiv.org/abs/2604.19516)
  (ACL Findings 2026). Multi-agent reusable strategy learning. Key usable
  finding: engine-specific preference modeling and strategy reuse matter,
  but this is stronger as research framing than as a stdlib audit check.

### First-party platform documentation

- [OpenAI crawler documentation](https://developers.openai.com/api/docs/bots)
  distinguishes `OAI-SearchBot`, `GPTBot`, and `ChatGPT-User`. It states
  that `OAI-SearchBot` is the Search control surface, while `GPTBot` is
  for training and `ChatGPT-User` is user-triggered.
- [OpenAI searchbot IP ranges](https://openai.com/searchbot.json) provide
  machine-readable published IP prefixes for `OAI-SearchBot`.
- [Google crawler overview](https://developers.google.com/crawling/docs/crawlers-fetchers/overview-google-crawlers)
  documents crawler cache behavior, including `ETag`,
  `If-None-Match`, `Last-Modified`, and `If-Modified-Since`.
- [Google common crawlers](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers)
  documents `Googlebot`, `GoogleOther`, and `Google-Extended`. It states
  that `Google-Extended` is a standalone token for Gemini training and
  grounding controls, and does not affect Google Search inclusion or
  ranking.

## Decision

### Candidate A — evidence-container density

**Promote to implementation.**

Add a new check 9 finding:

```text
9.11.evidence_container_density
```

The finding should score sampled pieces for extractable evidence
containers:

- definition markers (`is`, `means`, `refers to`, glossary-like phrasing)
- comparison sections or tables
- numerical / statistical facts with named context
- procedural / how-to steps
- code snippets or worked examples where relevant
- list and heading structure sufficient to expose those units

Severity:

- `PASS` when a healthy share of sampled pieces expose at least two
  evidence-container types.
- `INFO` for mixed coverage.
- `WARN` only when coverage is sparse across the corpus.

Rationale:

Check 9 already inventories citations, quotations, first-party data,
Q&A subheads, and front-loading. The new evidence from the
citation-absorption paper shifts the framing from "appears in citation
strip" to "supplies answer-shaping units." This is a better GEO target
than adding more Q&A wrappers.

Implementation constraints:

- Stdlib-only regex / HTML-text extraction, matching existing
  `scripts/check-content-tactics.py` style.
- Advisory only; no precise lift claims.
- Finding text must explicitly say these are observational features,
  not guaranteed causal levers.

### Candidate B — query-facet coverage / downside-risk advisory

**Promote to implementation as advisory.**

Add a new check 9 finding:

```text
9.12.query_facet_coverage
```

For sampled pieces, infer whether the page covers multiple likely query
facets when the topic calls for it:

- definition / "what is"
- comparison / alternatives
- procedure / "how to"
- evidence / statistics
- examples / cases
- limitations / caveats

The audit should not generate or test live prompts. It should only
surface structural coverage gaps in content that is already intended to
serve broad informational demand.

Severity:

- `INFO` by default.
- `WARN` only for long-form pillar pages that are structurally narrow
  despite broad titles or hub-page placement.

Rationale:

IF-GEO's useful takeaway for this skill is not its LLM editing pipeline;
it is the downside-risk warning. A static audit can cheaply flag pages
that appear overfit to one intent, while avoiding stochastic live
query measurement.

Implementation constraints:

- Do not auto-rewrite content.
- Do not claim that each page needs every facet.
- Treat product pages, short announcements, changelogs, and narrow
  essays as likely exempt unless configured otherwise.

### Candidate C — Google crawler semantics refresh

**Promote to implementation.**

Update check 3 documentation, templates, and `check-ai-bots.py` finding
text to clarify the current role split:

- `Googlebot`: Search, Discover, Google Images/Video/News, and Search
  features that depend on the Google Search index.
- `GoogleOther`: generic Google product and R&D crawler; no specific
  product guarantee.
- `Google-Extended`: publisher control token for Gemini Apps / Vertex
  Gemini training and grounding, not a separate HTTP crawler and not a
  Google Search ranking or inclusion control.

Rationale:

The current docs describe `Google-Extended` primarily as a training
opt-out flag. Google's current first-party docs make the grounding
control explicit. This matters for IEO/GEO operator advice: blocking
`Google-Extended` is not the same thing as blocking Google Search, but
it may affect Gemini grounding use.

Implementation constraints:

- Keep policy neutral: explicit `Allow` or `Disallow` both count as a
  valid training/grounding policy when the operator has chosen it.
- Do not imply that allowing `Google-Extended` improves Google Search
  ranking.
- Preserve graceful degrade when `robots.txt` is absent or malformed.

### Candidate D — live HTTP cache validators

**Promote to implementation.**

Add a live-apex phase or check-1 live subfinding:

```text
11.M.cache_validators
```

Probe a small sample of live HTML URLs and report:

- `ETag` presence
- `Last-Modified` presence
- parseability of `Last-Modified`
- whether all sampled pages share an obviously uniform build timestamp
- optional comparison between live `Last-Modified` and sitemap
  `lastmod`, with wide tolerance and `INFO` / `MANUAL_VERIFY` framing

Severity:

- `PASS` when validators are present and plausible.
- `INFO` when one validator exists but not both.
- `WARN` when sampled HTML pages expose no cache validators or all
  pages share a suspicious build-time timestamp.
- `MANUAL_VERIFY` on network errors or non-200 pages.

Rationale:

Google's crawler docs now explicitly discuss `ETag` and
`Last-Modified` behavior. The skill already audits sitemap freshness;
live cache validators are the adjacent post-launch surface that helps
crawlers understand recrawl state.

Implementation constraints:

- Put this behind check 11 if it requires live network access.
- Keep sample size small.
- Do not fail a site solely for missing `ETag`; many static hosts rely
  on `Last-Modified` and immutable asset hashes.

## Watchlist

### Watchlist A — published crawler IP freshness

OpenAI publishes JSON IP ranges for `OAI-SearchBot`, `GPTBot`,
`ChatGPT-User`, and `OAI-AdsBot`. A future optional check could fetch
the configured list and report whether local WAF allowlists are stale.

Do not implement yet because:

- The skill does not currently introspect arbitrary WAF allowlists
  beyond the Cloudflare Bytespider probe.
- Simulating source IP is not possible from the audit runner.
- Fetching vendor IP JSONs adds network dependency for a narrow benefit.

Revisit if consumers start maintaining explicit AI-bot IP allowlists.

### Watchlist B — Web Bot Auth / agent authentication

Google's crawler docs now link to experimental Web Bot Auth. This may
become relevant for distinguishing authorized agents from spoofed user
agents.

Do not implement yet because:

- The surface is experimental.
- No clear static-site audit assertion exists today.
- Adoption and hosting support are not yet visible enough to justify
  check complexity.

Revisit when first-party docs stabilize and one or more major hosts
ship deployable support.

## Explicit non-recommendation

### Do not add a live AI-search citation tracker

Do not add a default or opt-in check that queries ChatGPT, Gemini,
Perplexity, or AI Overviews to see whether a site is cited.

Reasoning:

- ADR 0002 already classifies LLM citation tracking as low signal for a
  single-shot audit because outputs are stochastic and require repeated
  query sampling.
- Search surfaces are proprietary, unstable, and often unavailable
  through free, documented APIs.
- The April 2026 SIGIR paper supports the strategic point that
  traditional and generative source sets diverge, but it does not make
  one-off citation probing reliable enough for this skill.

Keep this as operator-side measurement, not audit-time gating.

## Implementation order

1. **Check 3 semantics refresh** — documentation and finding-text only;
   lowest risk.
2. **Check 9 evidence-container density** — extends existing content
   tactics with the strongest new research signal.
3. **Check 9 query-facet coverage** — advisory, slightly more heuristic;
   ship after evidence-container density so findings do not overlap.
4. **Check 11 cache validators** — live-network behavior; needs careful
   graceful-degrade and sampling.

## Consequences

Positive:

- The skill moves from generic "GEO content tactics" toward the more
  precise selection-vs-absorption distinction.
- The implementation stays inside existing check boundaries: check 3
  for crawler policy, check 9 for content-side structure, check 11 for
  live-apex behavior.
- The candidates are auditable with stdlib parsing and small live probes.

Negative:

- Check 9 becomes broader and will need careful finding text to avoid
  turning into prose-quality grading.
- Query-facet coverage risks false positives on intentionally narrow
  essays; exemptions and INFO-first severity are required.
- Cache-validator behavior varies by host, so WARN language must avoid
  implying a hard Google requirement.

## What would change this decision

- A first-party AI-search API ships with stable citation reporting and
  repeatable query sampling; then revisit the "no live AI citation
  tracker" decision.
- Google or OpenAI changes crawler-control documentation materially;
  update check 3 semantics again rather than freezing this ADR's wording.
- Consumer dogfooding shows evidence-container or query-facet findings
  are noisy; demote thresholds to INFO or make them opt-in.
- Web Bot Auth leaves experimental status and static hosts expose a
  portable configuration surface; promote the watchlist item.

## Related

- [ADR 0001](0001-claim-verification.md) — claim-verification and
  steelman discipline for new candidates.
- [ADR 0002](0002-self-improving-skill.md) — why live LLM citation
  tracking is not a load-bearing audit signal.
- [Check 03](../../checks/03-ai-bot-directives.md) — crawler policy.
- [Check 09](../../checks/09-content-tactics.md) — content-side GEO
  tactics.
- [Check 11](../../checks/11-live-apex.md) — live-apex audit.
