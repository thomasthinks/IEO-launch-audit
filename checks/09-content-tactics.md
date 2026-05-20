# Check 09 — Content tactics (GEO posture, advisory)

## Why this matters

Princeton/Georgia Tech (Aggarwal et al., KDD 2024) measured 9 content
tactics for GEO effect on LLM visibility, using a 10K-query benchmark
(ELI5 + GPT-4-synthesized queries across 9 source domains), 5 random
seeds per condition, real-world validation against Perplexity.ai, and
Subjective Impression scored via GPT-3.5 G-Eval. Headline findings
(paper §4, verbatim):

- **Cite Sources, Quotation Addition, Statistics Addition** — top-
  performing bucket. **+30 to +40%** on Position-Adjusted Word Count;
  **+15 to +30%** on Subjective Impression (ranges averaged across
  rank buckets).
- **Fluency Optimization, Easy-to-Understand** — also **+15 to +30%**
  visibility on the same metrics.
- **Authoritative Tone** — no significant improvement.
- **Keyword Stuffing** — little to no improvement.

**Rank-bucket caveat (paper Table 2, load-bearing).** The Position-
Adjusted Word Count deltas swing dramatically by rank bucket: Cite
Sources is **−30.3% at rank-1** (already-cited sources can *lose*
visibility adding more citations) and **+115.1% at rank-5**. Same
pattern: Quotation Addition (−22.9% → +99.7%), Statistics Addition
(−20.6% → +97.9%). **GEO tactics help low-ranked sources
disproportionately and may hurt already-rank-1 sources.** This matters
for consumer advice: a piece that's already heavily cited for its
topic may not want to add more citation/quotation density — the
intervention can be net-negative.

Practitioner consensus across SEJ / Search Engine Land / Aleyda Solís /
Lily Ray / Profound is directionally aligned with Aggarwal: pieces
practicing these tactics get cited more than pieces that don't. Treat
as direction-of-bias, not as predicted lift magnitudes for a specific
page. Avoid quoting precise per-tactic percentages from vendor
readouts — most vendor "X% lift from Y tactic" claims do not trace
to a methodology document (see `docs/decisions/0001-claim-verification.md`).

This check is **advisory**. Auto-fixing prose is out of scope (250 pieces
× ~2K words is not auto-paraphraseable without voice degradation). It
inventories what each piece does / doesn't do and surfaces a remediation
recommendation list.

**Cited sources (methodology-disclosed):** Aggarwal et al. (KDD 2024).
**Cited sources (pattern-observation, no per-tactic methodology):**
Profound's 2026 citation-pattern readouts; ALM Corp 325K-prompt LinkedIn
study; SEJ "Role of E-E-A-T in AI narratives"; Search Engine Land
"Content strategy in 2026."

**Citation absorption ≠ citation retrieval ≠ answer influence (framing
clarification).** A piece appearing in an LLM's cited-sources list does
not mean it *influenced* the answer. The
["From Citation Selection to Citation Absorption"
paper](https://arxiv.org/abs/2604.25707) (2026) distinguishes pages that
get retrieved-and-quoted vs pages that get retrieved-and-discarded
(absorbed without influence). AirOps's 548K-page measurement found
**85% of pages retrieved by ChatGPT are never cited**, and even cited
pages may be "ghost citations" (link present in citation strip without
the brand name in the answer text — Kevin Indig measured 61.7% ghost-
citation rate in a 1.2M-response sample). The implication for consumer
advice: optimizing for citation count is a coarser signal than
optimizing for *absorption* (content that actually shapes the LLM's
answer text). The latter is what drives reader traffic; the former is
just a footnote presence.

## What's checked

For each piece (or for a stratified sample if catalog is large):

### 9.1 — Thesis-first structure

| Assertion | Pass | Warn |
|---|---|---|
| First paragraph contains a load-bearing claim (the thesis) | yes | thesis later in piece |
| `data-thesis-block` (or equivalent Speakable selector) marks the thesis | yes | no |
| Thesis can be quoted as a standalone sentence (no orphan pronouns) | yes | requires context |

### 9.2 — Author byline presence

| Assertion | Pass | Warn |
|---|---|---|
| Author name visible in-page (not just in schema) | yes | no |
| Author byline includes credentials / role | yes | name only |
| Author byline links to external profile (LinkedIn) | yes | no |

### 9.3 — Citation density

| Assertion | Pass | Warn |
|---|---|---|
| ≥1 inline named citation (Author + Outlet + Year) per ~750 words | yes | <1 |
| Citations point to PRIMARY sources (SEC filings, JAMA papers, FDA
  guidance), not secondary summaries | yes | secondary chain |

### 9.4 — Quotation presence

| Assertion | Pass | Warn |
|---|---|---|
| ≥1 direct quotation from a named expert or primary document | yes | no |
| Quotations use proper attribution (Person — Outlet, Year) | yes | unattributed |

### 9.5 — First-party data

| Assertion | Pass | Warn |
|---|---|---|
| Piece includes ≥1 first-party data point (named amount, dated event,
  proprietary number) | yes | secondary-only |
| First-party data is bound to specifics (which company, when, what
  amount) | yes | generic claim |

### 9.6 — Q&A subheads (where natural)

| Assertion | Pass | Warn |
|---|---|---|
| Section headers are question-shaped where the content answers a
  question | yes | declarative-only |

### 9.7 — Stable named concepts

Operates across the corpus (not per-piece).

| Assertion | Pass | Warn |
|---|---|---|
| Named concept used in piece A is named identically in pieces B-Z (no
  drift) | yes | drift detected |
| Concept naming follows ADR/style-guide (where one exists) | yes | inconsistent |

### 9.8 — Date discipline

| Assertion | Pass | Fail |
|---|---|---|
| `datePublished` is immutable (no retroactive changes) | yes | drift |
| `dateModified` bumps only on substantive edits (not cosmetic) | yes | bumped without changes |
| No year-stamps in titles for atemporal essays | yes | year in title |

### 9.9 — AI-content fingerprint avoidance

| Assertion | Pass | Warn |
|---|---|---|
| No structural-tic fingerprints (e.g., bold-numbered lists at >25% cadence) | yes | tic detected |
| Em-dash density within ADR-defined cap | yes | over cap |
| Sentence-length and transition-word variance is human-like | yes | uniform |

## How to fix

These are content-level changes; no auto-fixable category. The script
emits a per-piece recommendation list:

### Fix 9.1 — Move thesis to first paragraph

Per piece flagged: rewrite the first paragraph to lead with the load-
bearing claim. Add `data-thesis-block` attribute. Speakable
SpeakableSpecification.cssSelector should include `[data-thesis-block]`.

### Fix 9.2 — Embed author byline

Add a small byline component to each piece's render. Template:

```tsx
<div className="author-byline">
  <span className="name">Thomas Jankowski</span>
  <span className="role">Five-time CEO, applied AI in travel + healthcare</span>
  <a href="https://www.linkedin.com/in/thomasjankowski" rel="me">LinkedIn</a>
</div>
```

Place at piece foot (after the prose, before the Read-next block).

### Fix 9.3 / 9.4 / 9.5 — Citation, quotation, first-party data

These are per-piece editorial work. The check identifies pieces below
target density; the operator decides whether to backfill citations or
accept gaps.

For new pieces being drafted: bake in citation + quotation + first-party
data during drafting, not retroactively.

### Fix 9.6 — Q&A subheads

Where a section naturally answers a question, reshape the header. Quick
example: "The agent layer is here" → "What changed when the agent
layer landed?" Not all sections benefit; don't force.

### Fix 9.7 — Named-concept consistency

Audit-only across the corpus. The check produces a "concept drift" list
(same concept named differently across pieces). Operator decides whether
to canonicalize naming.

### Fix 9.8 — Date discipline

Code-side: emitter should set `datePublished` immutably (from
frontmatter, never from build time). `dateModified` bumps only when
prose actually changes (content-hash check at build time).

### Fix 9.9 — Structural-tic remediation

Per-piece structural-tic detection. The fix is per-tic; see
`docs/editorial/audits/2026-05-13-voice-drift-exceptions.md` for the
remediation pattern used in the May 2026 audit of this repo.

## Failure ratings

This check is **advisory only**. It emits a per-piece score (0-9 of the
above assertions passing) but does NOT block the audit's overall
pass/fail.

The overall audit emits a "Content Tactics Coverage" summary:
- ≥80% of pieces score 7+/9 → GREEN
- 50-80% → YELLOW
- <50% → RED

RED is a recommendation, not a launch block.

## Cited research

- [GEO: Generative Engine Optimization (Aggarwal et al., arXiv)](https://arxiv.org/abs/2311.09735)
- [Search Engine Land — GEO framework introduced](https://searchengineland.com/generative-engine-optimization-framework-introduced-research-paper-435855)
- [ConvertMate GEO Benchmark Study 2026](https://www.convertmate.io/research/geo-benchmark-2026)
- [Profound — AI Platform Citation Patterns](https://www.tryprofound.com/blog/ai-platform-citation-patterns)
- [Search Engine Journal — Role of E-E-A-T in AI narratives](https://www.searchenginejournal.com/role-of-eeat-in-ai-narratives-building-brand-authority/541927/)
- [Qwairy — Content Freshness & AI Citations Guide 2026](https://www.qwairy.co/blog/content-freshness-ai-citations-guide)
- [ALM Corp — LinkedIn #2 Most Cited Source (325K-prompt study)](https://almcorp.com/blog/linkedin-ai-search-citations-2026/)
- [Search Engine Land — Content strategy in 2026](https://searchengineland.com/guide/content-strategy-in-2026)

## Implementation notes

`scripts/check-content-tactics.py`:
1. Walks every piece body
2. Runs the 9 sub-checks per piece via regex / structural heuristics
3. Emits per-piece scorecards + corpus-level summary

This check is the most expensive (parses prose); supports `--sample N`
to score a random sample instead of full corpus.
