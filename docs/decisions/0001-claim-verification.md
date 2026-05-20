# ADR 0001 — Claim-verification reflex for new check candidates

**Status:** Accepted (v1.3, 2026-05-15; pattern 4 added v1.3.2, 2026-05-20; steelman reflex added v1.4.1, 2026-05-20)
**Context:** Two research passes against 2026 SEO/IEO/GEO discourse
**Decision:** Every candidate sourced from third-party SEO discourse goes
through a verification-subagent pass before promotion into the skill's
default findings.

## Context

The skill audits a domain (SEO / IEO / GEO best practices) where folklore
travels faster than measurement. Marketing-blog ecosystems produce
specific-sounding numbers that get syndicated across vendor sites, each
citing the others, until a "consensus" exists that doesn't trace to any
methodology.

Across two research passes (May 2026), the same failure pattern repeated:

1. **A `seo_learnings.md` artifact** carried over from the parent repo's
   extraction contained the "Princeton GEO study, optimal passage length
   134-167 words" claim. Verification subagent established that the
   Princeton paper (Aggarwal et al., arXiv 2311.09735, KDD 2024) does NOT
   contain that claim — the paper measures content-modification tactics,
   not passage length. The 134-167 number traces to a single
   `latticeocean.com` post with no methodology, then propagated through
   `amicited.com`, `surferseo.com`, `sapt.ai`, `getpassionfruit.com`.
2. **The aaron-he-zhu/seo-geo-claude-skills repo survey** (Nov 2026,
   declined import) repeated similar patterns: "+34% citation lift from
   structured-attribution verbs" turned out to be misattributed (the
   number traces to a Stacker earned-media study measuring something
   different). "Submit to Brave Webmaster Tools as Claude-citation
   lever" — that product does not exist (Brave staff confirmation in
   community thread).
3. **The 2026-emergent-pattern recursive research** (May 2026)
   surfaced "Information Gain operationalized at scale in the March 2026
   core update with ~22% visibility lift." Verification subagent: no
   Google first-party confirmation; the "22%" traces to a press-release
   distribution ecosystem (wyomingnews / foresthillmessenger /
   financialcontent / openpr — all syndicating one underlying release
   promoting an SEO content service). The "13-week recency cliff" turned
   out to trace to one source (Amsive) smoothed across vendor blogs into
   "consensus."
4. **The v1.3.2 dogfooding pass** (May 2026) surfaced a self-violation:
   `checks/09-content-tactics.md` had quoted Aggarwal et al. (KDD 2024)
   as point estimates (`+30%`, `+35%`, `+37%`) — bound-smoothed from the
   paper's published 30-40% / 15-30% ranges, with the per-rank-bucket
   caveat omitted entirely (rank-1 deltas in the paper are actually
   *negative* for these tactics; rank-5 deltas exceed +100%). Two other
   numbers in the same file (`Q&A blocks +40%`, `First-party data
   +30-40%`, both attributed to Profound) had no traceable methodology
   source. A fourth (`Semantic completeness 340% inclusion rate`) had
   no source citation at all. Fixed in v1.3.2; the dogfooding pattern
   becomes pattern 4 below.

These are not one-offs. They are the **emission pattern of the SEO
content-marketing ecosystem in 2026** — and the skill is not immune to
emitting them when sourcing from that ecosystem.

## Four failure-pattern signatures

Calibrating institutional pattern-recognition so future research passes
catch these earlier:

### Pattern 1 — "X% lift in core update Y"

A specific percentage with no disclosed methodology, syndicated across
vendor blogs that each cite each other.

Examples seen:
- Information Gain "+22%"
- "134-167 word Princeton thesis-passage target"
- "+34% structured-attribution-verb lift"
- "+28% SSR-vs-CSR citation lift"

**Verification reflex:** dispatch a subagent to find the *single
underlying methodology*. If methodology can't be traced past 2 hops of
citation, the number is folklore. The mechanism may be real (Information
Gain is a real Google patent) but the quantitative claim is not.

### Pattern 2 — "Submit to X" products that don't exist

An actionable verb attached to a platform that hasn't actually shipped
that surface. Sounds prescriptive; isn't operational.

Examples seen:
- "Submit to Brave Webmaster Tools" — product doesn't exist; Brave
  indexes via Web Discovery Project (opt-in browser telemetry).
- (Watch for similar with future engines: "Submit to ChatGPT Webmaster"
  — also doesn't exist; OpenAI has no submission surface.)

**Verification reflex:** when a recommendation says "submit to [hub]",
verify the submission surface exists with a primary-source URL. If the
hub doesn't have a submission UI, the recommendation is wrong — the
real lever is *visibility on the hub*, not *submission to the hub*.

### Pattern 3 — Single-source "boundaries" smoothed into precise numbers

Precise numbers in marketing posts that don't agree across sources.

Examples seen:
- 13-week recency cliff (Amsive only; Profound says "3× decay after 3
  months", Seer says "65% past-year content")
- 134-167 word range (Lattice Ocean only; Am I Cited says 75-150;
  Kopp says 120-180; Sapt says 127-156)

**Verification reflex:** when a precise number cited as consensus turns
out to drift by 50%+ across sources all claiming the same study, **no
study exists**. The number was made up in one place; the rest is
copy-paste.

### Pattern 4 — Vendor-published weight percentages for closed-source ranking

Specific percentage claims about how a closed-source LLM ranking
algorithm weights factors, with no first-party source from the engine
vendor.

Examples seen:
- "Claude weights entity verification 30% / technical accuracy 25% / ..."
- "ChatGPT weights domain authority 40% / content 35% / trust 25%"
- "Perplexity weighs recency at 20% in core update X"

**Verified-by-absence (May 2026):** direct fetches of canonical docs
confirm that none of Anthropic ([web_search tool
docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)),
OpenAI ([ChatGPT Search
help](https://help.openai.com/en/articles/9237897-chatgpt-search)),
Perplexity ([publisher program](https://www.perplexity.ai/hub)), or
Google ([AI optimization
guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide))
publishes a source-selection algorithm or factor weights. Any such
percentage circulating in vendor blogs is fabricated. (The engines
explicitly do not publish this information — that is policy, not
oversight, and unlikely to change.)

**Verification reflex:** when a recommendation cites engine-specific
ranking weights, demand the first-party URL from the engine vendor. If
none exists, the percentage is folklore. Distinguish this from
mechanism-claims that ARE publishable ("Claude uses dynamic filtering"
is verifiable; "Claude weights aggregators 25% less" is not).

## The steelman reflex (added v1.4.1)

The verification reflex is structurally defensive — it catches folklore.
Run alone, it produces a bias toward candidates whose evidence is
weak-but-traceable over candidates whose evidence is strong-but-
undiscovered. The v1.4 research pass surfaced this failure mode: the
candidate slate emerged from a thin corpus (Google web search + vendor
blogs + arXiv), and the verification pass dutifully verified the few
claims that surfaced — without ever asking "what's the strongest
evidence FOR this pattern that I haven't found yet?"

The steelman reflex is the generative counterpart. For each candidate
hypothesis, dispatch a subagent whose explicit task is to find the
strongest available primary, first-party, or methodology-disclosed
evidence FOR the hypothesis. Opposite incentive structure to the
verification subagent: steelman is incentivized to find evidence;
verification is incentivized to attack it.

### What a steelman subagent does

1. Takes a hypothesis (one-sentence statement of the pattern under test).
2. Searches expanded corpora (see below) for evidence supporting it.
3. Returns **verbatim quotes with source URLs**, not paraphrases.
   Tags each finding with source tier (primary research / first-party
   platform / methodology-disclosed industry study / practitioner
   opinion).
4. Exhausts the corpus list before reporting. Doesn't stop at first
   hit — finds the strongest available evidence, which may not be the
   first surfaced.

### Expanded corpora (mandatory for major-pass steelman)

The v1.4 research over-relied on Google web search + vendor blogs.
Each major-pass steelman MUST sample beyond this. Corpora to mine,
in priority order:

1. **Academic / methodology-disclosed primary research.** arXiv sanity,
   Semantic Scholar, ACM Digital Library, Papers with Code, conference
   proceedings (NeurIPS, ICML, EMNLP, SIGIR, KDD, WWW).
2. **First-party platform documentation.** developers.google.com,
   platform.claude.com, help.openai.com, perplexity.ai/hub,
   learn.microsoft.com, blogs.bing.com, brave.com/blog. Highest
   signal-to-noise for engine-behavior claims; mine systematically.
3. **Conference talk catalogs.** BrightonSEO, SMX (Munich / West /
   East / Advanced), Pubcon, MozCon, SEOFOMO Live, SEO Discoveries.
4. **Practitioner long-form on LinkedIn.** Named practitioners with
   consistent 2026 GEO-side output: Kevin Indig, Mike King, Aleyda
   Solís, Lily Ray, Marie Haynes, Cyrus Shepard, Glenn Gabe, Will
   Critchlow, AJ Kohn. LinkedIn long-form is higher-signal than
   vendor blogs (practitioner reputation is staked).
5. **High-signal newsletter back-issues.** SEOFOMO, Growth Memo
   (Indig), Indie SEO, Search Engine Roundtable.
6. **Practitioner subreddits.** r/SEO, r/bigseo, r/TechSEO — filter
   by karma + comment density + recency.
7. **YouTube speaker-series transcripts.** Search Engine Land Live,
   SMX YouTube post-event uploads, BrightonSEO channel, named-
   practitioner channels.
8. **GitHub awesome-lists + GEO-tooling repo discussions.**
   awesome-llm-seo, awesome-geo, awesome-llmstxt, tooling-repo
   issues + discussions reveal what practitioners are actually testing.

A pass that hits only corpora 1+2 is fine for primary-source questions.
A pass that hits only 4+6 is suspect (practitioner opinion without
methodology anchoring). Mix tiers per pass.

### Budget expectation per pass

| Pass type | Discovery | Steelman | Verification | Runtime |
|---|---|---|---|---|
| **Major** (e.g., v1.4 → v1.5) | 5-7 parallel, 60-100 tool uses each | 3-5 on top hypotheses, 40-60 tool uses each | 3-5 attacking each steelman finding | ~2-3h subagent + ~30min consolidation |
| **Patch** (e.g., v1.4.1 → v1.4.2) | 1-2 lightweight | 1-2 on the specific question | 1-2 | ~30-60min total |

The v1.4-style thin pass (2 discovery + 2 verification, ~30 tool uses
each) is **no longer sufficient** for major-version candidate slates.
Patches may still use a thin pass when scoped to a single hypothesis.

### Pipeline composition

The two reflexes form a per-candidate two-pass pipeline:

```
candidate hypothesis
        │
        ▼
   steelman pass ──── verbatim evidence + source URLs + tier tags
        │
        ▼
   verification pass ── attacks each steelman finding per
        │              folklore patterns 1-4 + verbatim-quote check
        ▼
   survives both? → promote to candidate slate
                    else → reject; log reasoning in CHANGELOG / ADR
```

Steelman alone produces credulity. Verification alone produces
shallowness. Both are required for any candidate that ships.

### Failure mode of steelman + mandatory mitigation

The steelman subagent's incentive structure ("find evidence FOR X")
risks regenerating folklore — the subagent may surface vendor-blog
claims that sound supportive but trace back to no methodology, OR
paraphrase a finding into a stronger claim than the source actually
makes (cf. pattern 3, single-source boundaries smoothed into precise
numbers).

Mitigations are not optional:

- Steelman returns **verbatim quotes with source URLs**. No paraphrase
  of empirical claims.
- Source tier tagged explicitly per finding.
- Verification subagent **re-fetches** the source URL and confirms the
  verbatim quote exists at that URL and means what the steelman
  subagent claimed it means.

Verification is the load-bearing safety net for steelman. Steelman +
verification together = research discipline. Steelman alone =
folklore generator.

## The verification-subagent reflex

For each candidate sourced from third-party SEO discourse:

1. **Identify the primary source.** Trace each citation back to its
   originating measurement. Marketing-blog → vendor-blog → ... — keep
   going until you find a methodology disclosure or run out of hops.
2. **Distinguish mechanism from quantification.** "Information Gain is
   a real Google patent" is true. "Information Gain weighs 22% in the
   March 2026 core update" is folklore unless Google says so.
3. **Cross-check numbers across ≥2 independent measurements with
   disclosed methodology.** If only one methodology-disclosed source
   exists, treat the number as direction-of-bias, not magnitude.
4. **Verify products exist before recommending "submit to" them.**
5. **Watch for patterns 1-3.** Flag a finding as `LOW`-confidence when
   any pattern signature is present.

The verification-subagent dispatch is **already proven** as the
mechanism: the seo_learnings.md, aaron-he-zhu, and 2026-emergent
research passes were all run through verification before promotion.
This ADR ratifies the pattern as a default for future passes.

## Consequences

**Positive:**
- New checks promote with disclosed-evidence backing. The skill stays
  out of folklore.
- The two-reflex discipline (steelman + verification, added v1.4.1)
  closes the v1.4 failure mode where verification alone biased toward
  weak-but-traceable evidence at the expense of strong-but-undiscovered
  evidence.
- The skill maintains the editorial discipline distinguishing "Google
  said this" from "vendor blogs say Google would say this."

**Negative:**
- Each candidate has a two-pass tax before shipping. Major-pass budget
  expanded from v1.4's "thin pass" (~15-30 min, 4-6 subagents) to
  v1.5+'s major-pass budget (~2-3h, 11-17 subagents across discovery +
  steelman + verification). Worth the cost; named here so it's not
  surprising at execution time.
- The reflex doesn't catch first-order accuracy errors (a subagent can
  be wrong about whether a primary source exists). Cross-check
  load-bearing claims against the original document, not just the
  subagent's report.
- Steelman without verification = folklore generator. The two reflexes
  MUST run as a pair; running steelman alone is worse than running
  verification alone.

## What would change this decision

- Anthropic ships a primary-source-verification tool that's
  measurably more reliable than the verification-subagent pattern.
  (Unlikely soon; this is the current best-practice.)
- The SEO discourse ecosystem stops emitting folklore in the three
  patterns above. (Unlikely; the incentive structures favor folklore
  emission.)
- A specific candidate has SO MUCH primary-source backing across
  ≥3 independent measurements that a verification pass would be
  redundant. (Possible for established checks like CWV thresholds,
  W3C-confirmed schema types, or web.dev/vitals canonical metrics —
  these don't need re-verification each pass.)

## Related

- v1.1 CHANGELOG § "Declined" — seo_learnings.md verification + drops.
- v1.2.1 CHANGELOG § "Process learning" — three-pattern catalog.
- v1.2.1 README § "Authoring credit" — research-2026-05.md is the
  durable verified-evidence base; this ADR is the verification reflex.
- `verification-subagent.md` (future) — concrete prompt template for the
  reflex; currently embodied in conversational pattern across the
  research passes.
