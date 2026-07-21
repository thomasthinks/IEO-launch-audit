# HANDOFF — IEO-launch-audit

Session-state file (canonical per global convention). Durable narrative +
resume point. Update before clearing context.

## State as of 2026-07-21

- **Version:** v1.8.0. Last substantive commit `5deac12` (2026-06-26)
  implemented the full ADR 0003 June 2026 GEO candidate slate (check 3
  crawler-semantics refresh, check 9 evidence-container density +
  query-facet coverage, check 11 cache validators).
- 2026-07-21: housekeeping — added `.gitignore` (`__pycache__/`, `*.pyc`),
  untracked the stale compiled caches, pushed.

## July 2026 research pass (2026-07-21)

Four parallel sonnet research subagents swept deltas since 2026-06-26
(academic, first-party platform docs, GEO-startup data studies, mainstream
SEO). Findings synthesized into a candidate slate — **not yet ratified as
an ADR, nothing implemented.** Summary of the slate:

### Build candidates (strong evidence)

1. **Cloudflare `Content-Signal: use=` param** (first-party, 2026-07-01;
   blog.cloudflare.com/content-independence-day-ai-options/). New 4th
   param (`use=immediate|reference|full`) auto-injected into CF-managed
   robots.txt; new Search/Agent/Training bot taxonomy; stricter defaults
   land **2026-09-15**. → regex subfinding in check 3 robots parsing.
   While there: refresh OpenAI doc links (platform.openai.com/docs/bots
   → developers.openai.com/api/docs/bots, old 301s).
2. **llms.txt severity recalibration** — Google Search Central now
   explicitly does not use/endorse llms.txt (June 2026 doc note); ppc.land
   2026-07-02: 97% of llms.txt files get zero AI-crawler fetches; only
   IDE agents (Cursor/Claude Code/Copilot) read it. Check 3 findings
   3.5/3.6 currently WARN on missing llms.txt — downgrade to INFO and
   reframe as "agent-context nicety, not a citation lever."
3. **Sitemap lastmod binary-trust refresh** — Gary Illyes 2026-07-16:
   unreliable lastmods → Google distrusts the *entire column*; better to
   remove lastmod than ship inaccurate ones. Check 7 already FAILs
   all-identical lastmod; add the "consider removing lastmod entirely"
   fix path + cite the new guidance.

### Epistemics recalibration (from academic pass)

4. **Critical survey** (Martinez, arXiv 2607.14035, 2026-07-15; 45
   studies): GEO gains are stage-local; naive GEO rewrites cut top-20
   retrieval ~9% / post-rerank top-10 ~16%; run-to-run citation Jaccard
   0.34–0.42 (single-run measurement unstable — **validates ADR 0003's
   rejection of a live citation tracker**). The famous "+40% GEO lift"
   traced to one narrow metric/config. Plus SIGIR '26 252k-trial study
   (2605.25517): relevance + retrieved-context position dominate; content
   tactics second-order. Plus Ahrefs matched-control study (1,885 pages
   vs 4,000 controls): JSON-LD addition → no significant AI-citation
   uplift. → Soften check 2 "schema types remain load-bearing for
   AI-engine citation" line; add anti-over-optimization caveat to check 9
   finding text; check 2's existing hedge is otherwise well-positioned.

### Advisory candidates (moderate evidence — industry synthesis)

5. **Q&A direct-answer band**: H2 ending in "?" + immediately-following
   40–80-word answer paragraph (Ahrefs/Previsible July 2026 synthesis;
   AIO citations from top-10 organic fell 76%→38% over 8 months).
   check-content-tactics.py already checks 40–150-word answer blocks —
   this is a pairing/threshold refinement, not a new check.
6. **Dated-currency language** ("as of Q3 2026") regex freshness marker.
7. **URL path-depth distribution** — AI Mode concentrates 69–76% of
   citations on 2–3-segment-deep docs URLs (Aleyda Solis 2026-07-16,
   15 SaaS brands). INFO-only histogram candidate; single-analyst
   synthesis, weakest of the slate — maybe watchlist.

### Watchlist updates

- Web Bot Auth: registry draft `draft-meunier-webbotauth-registry-03`
  (2026-06-26) still individual-draft, no fixed .well-known path — ADR
  0003 watchlist stance stands.
- GSC "Search generative AI" opt-out toggle + AI performance reports:
  limited rollout, API surface unverified — check 12 candidate later.
- GSC **FAQ rich-result API fields removed August 2026** — confirm check
  12 graceful-degrades (likely unaffected; it pulls search analytics).
- RFC 9309 repext draft (Illyes) expires 2026-10-20 — watch.

### Confirmed no-change

schema.org still v30.0 (2026-03-19); CWV thresholds unchanged — the
"LCP tightened to 2.0s" claim circulating is NOT corroborated by web.dev,
treat as misinformation; Bing/IndexNow unchanged; Anthropic/Perplexity/
Meta/Apple/Amazon crawler policies unchanged; Wikidata no delta.

## July 2026 research pass — wave 2 (community/tooling channels, 2026-07-21)

Five more subagents (HN via Algolia API, Reddit via safereddit/redlib curl
route — reddit.com itself is triple-blocked from this box, Product
Hunt+GitHub, LinkedIn/newsletters, data-API providers). Adds to the slate:

### New build candidates from wave 2

- **Prompt-injection / negative-citation-signal check** (new category):
  hidden text, invisible Unicode, embedded LLM instructions, aria-hidden
  abuse, micro-font text; plus negative signals (CTA overload, boilerplate
  ratio). Source: `Auriti-Labs/geo-optimizer-skill` (608★, MIT, Python —
  nearest open-source peer, worth reading end-to-end). Stdlib regex/DOM.
- **`agents.md` + MCP server-card detection** — cheap INFO findings
  (from `houtini-ai/seo-audit`, 2026-07-20).
- **Adopt `ai.robots.txt` `robots.json`** (github.com/ai-robots-txt,
  v1.47, MIT) as periodically-refreshed multi-vendor bot registry to
  augment the hardcoded UA list in `scripts/check-ai-bots.py:100`.
- **FCrDNS bot-impostor verification** — check 11 candidate (PTR →
  forward-resolve round-trip; works for Googlebot/Bingbot/Applebot/
  PerplexityBot; GPTBot/ClaudeBot are IP-range-verified instead).
- **LLM-remediation-prompt output format** — emit each finding as a
  copy-paste fix prompt for Claude Code/Cursor (presentation only; two
  independent tools shipped this).
- **Passage-level self-containment** advisory for check 9 ("Query
  Fan-Out" practitioner consensus: retrieval is passage-level; each
  H2/H3 block should state claim + support standalone).
- **Token-efficiency / boilerplate-ratio** scoring — INFO candidate.

### llms.txt downgrade now quadruple-sourced

Google non-endorsement + Ahrefs 137k (97% zero-fetch; "zero requests for
llms.txt files that don't exist" — bots never probe) + 80k-blog operator
(zero bot fetches) + SE Ranking 300k XGBoost (removing llms.txt as
feature IMPROVED citation-prediction accuracy — it's noise). Adoption
~9-10% (Tranco crawl + SE Ranking converge). WARN→INFO is now the
best-evidenced single change in the slate.

### Caution flag on the Q&A-band candidate

Secondhand Reddit recap of Google Search Central Live Milan (Jun 2026)
claims Google advised AGAINST formatting content into "bite-sized chunks"
for LLMs — direct tension with the H2-question+40-80-word-answer
candidate. Unverified (tweet-aggregation). **Verify via Search Engine
Roundtable coverage before shipping that advisory.**

### ADR 0002/0003 premise update (reword, don't reverse)

DataForSEO shipped `ai_optimization/llm_mentions` API 2026-06-01
(~$0.10/query, per-domain citation filter, ChatGPT/Claude/Gemini/
Perplexity/Google AI; historical backfill to 2025-08). Bright Data
~$0.0015/query. So "no stable documented API exists" is now false — but
the stochasticity objection stands (run-to-run citation Jaccard
0.34-0.42) and practitioner sentiment agrees (130-upvote r/SEO thread:
GEO visibility tools are "invented prompt baskets"). Reword ADR premise
to cost/methodology grounds; live tracker stays out of default. Possible
future opt-in.

### Useful calibration base rates (for report framing, not checks)

GPTBot blocked by ~41% of bot-blocking-tracked sites, ClaudeBot ~36%,
PerplexityBot ~7% (sitestatsdb 126k); 16.8% of Tranco-500k block LLM
crawlers; ~9% llms.txt adoption; YC S26 batch: 50% any schema, ~9% AI-bot
blocking, 1-in-11 sites are empty shells to non-JS crawlers.

### Wave-2 watchlist adds

- `Accept: text/markdown` content negotiation (acceptmarkdown.com) —
  single-source, emerging; possible check-11 probe later.
- Semantic Manifest spec (`semantic-manifest.jsonl`) — v0.1, 2★, watch.
- Dark Visitors rebranded → knownagents.com (no repo links to fix —
  grepped clean).
- Kevin Indig agent study: pricing/features/security pages crawlable-text
  vs JS-gated as static precondition (B2B/SaaS-leaning; INFO candidate).
- Petrovic COE (2,249 experiments): format edits beat E-E-A-T/credential
  signals >2:1 — supports existing evidence-container emphasis; no new
  check.
- Prior art to differentiate from in README (optional):
  `MerqryLabs/ai-crawler-visibility` (narrow subset of this skill).

## Resume point

**v1.9.0 shipped 2026-07-21** — TJ ratified the combined slate; ADR 0004
written and implemented the same day. What landed: Content-Signal
parsing (3.7), AGENTS.md detection (3.8), registry diff vs vendored
ai.robots.txt snapshot (3.9), prompt-injection detection (9.13),
negative-citation signals (9.14), dated-currency (9.15),
`emit-fix-prompts.py` output mode, llms.txt/lastmod/schema-claim text
recalibrations, and the ADR 0002/0003 citation-tracker premise update
(decision upheld on stochasticity grounds). The Milan "don't chunk"
claim was verified against the primary source (SER 2026-06-19): it's a
caveat against *forcing* chunking, not against Q&A structure — folded
into 9.fanout notes rather than blocking anything.

Deferred with documented triggers (see ADR 0004 watchlist /
non-recommendations): FCrDNS bot verification (no inbound-IP access),
token-efficiency scoring (needs built-page HTML — check-14 candidate),
MCP-card detection, `Accept: text/markdown` probe, Web Bot Auth, GSC
AI-toggle field for check 12. Note on record: GSC FAQ rich-result API
fields disappear August 2026 (check 12 unaffected — pulls search
analytics only).

Next natural steps, none urgent: dogfood v1.9.0 against
thomasjankowski-site (canonical consumer) to shake out 9.13/9.14 false
positives; consider tagging the next research pass for ~September 2026
(post the 2026-09-15 Cloudflare default change). Full subagent reports
live only in the session transcript — this file + ADR 0004 are the
durable record.

Open loose end: `.claude/CLAUDE.md` and `.portfolio-config.yml` sit
untracked at repo root (pre-existing, not authored this session; left
out of the public push deliberately). TJ to decide: commit, gitignore,
or leave.
