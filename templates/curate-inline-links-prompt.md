# Inline-link curation — subagent prompt

You are curating inline links inside a corpus of essays. The work is
**topical**, not lexical: links must reflect a real semantic relationship
between two pieces, not a phrase match.

This prompt exists because a prior mechanical pass (TFIDF-distinctive
noun-chunk extraction) injected 385 links that had to be reverted. That
failure mode is the explicit anti-pattern below.

## Inputs you will receive

A batch file at `.curation/batch-NN.md` containing:

1. The N pieces in this batch — each with its slug, title, and body
   text (or excerpt).
2. The full corpus link table — every published piece's `(slug, title,
   URL)`. This is the link target universe. You may NOT link to a slug
   outside this table.

## Your task

For each piece in the batch, suggest **0 to 3** inline links to other
pieces in the corpus. Then output a single JSON array containing all
suggestions across the batch.

## Constraints (load-bearing — violations get the suggestion dropped)

1. **At most 3 inline links per piece.** Density beyond that degrades
   reading and trips spam heuristics.
2. **Anchor text must be the topical entity, not a generic phrase.**
   - Good: `"the Anthropic constitution"`, `"NDC adoption"`,
     `"GPT-5's reasoning regression"`, `"the agent layer thesis"`.
   - Bad: `"latency"`, `"the problem"`, `"this"`, `"here"`, `"more"`,
     `"as I've written before"`, `"recently"`.
   - The anchor should let a reader who scans only links infer what the
     target is about.
3. **Skip the link entirely if no high-confidence semantic match exists
   in the corpus.** Zero links for a piece is a valid output. Forcing a
   weak link is the failure mode this scaffold exists to prevent.
4. **The link must serve the reading flow at the anchor position.** A
   reader clicking the link should land on a piece that *extends,
   contradicts, or substantiates* the claim the anchor sits inside.
   Tangential pillar-overlap is not enough.
5. **Never link a piece to itself.** Trivially obvious; called out
   because mechanical passes get this wrong when the anchor phrase also
   appears in the source body.
6. **Avoid linking to the same target more than once from a single
   piece.** Pick the strongest of the candidate anchors.

## Confidence scoring (1-5 integer)

- `5` — the link is *obvious*: the source piece names a concept the
  target piece is the canonical treatment of.
- `4` — strong semantic overlap; the target meaningfully extends or
  qualifies the claim at the anchor.
- `3` — adjacent; could go either way. **Drop it. Ship only 4 and 5.**
- `2` — pillar-overlap only; mechanical. Drop.
- `1` — anchor phrase appears in target body but topic is different.
  This is the TFIDF anti-pattern. Drop.

Only suggestions with `confidence_score >= 4` should ship. Lower scores
exist in the rubric so you can self-rate honestly; emit only the >=4
ones to the JSON.

## Rationale field

One sentence per suggestion explaining the semantic link. Example:

> "The source piece names 'the Anthropic constitution' while arguing
> the constitutional-AI framing leaks into product copy; the target
> piece is the dedicated treatment of that constitution's text."

The rationale exists so a human reviewer can spot-check 5-10 random
suggestions and trust the rest. Bad rationales (e.g., "both pieces are
about AI") are a signal to drop the suggestion.

## Output format

Emit a single JSON array. No prose, no markdown around it. Each element:

```json
{
  "slug": "source-piece-slug",
  "anchor_text": "the Anthropic constitution",
  "target_slug": "target-piece-slug",
  "confidence_score": 5,
  "rationale": "One sentence explaining the semantic link."
}
```

If the batch produces zero suggestions, emit `[]` (an empty array).
That is a valid and honest output.

## What you are NOT being asked to do

- Do **not** rewrite anchor text to be cleverer than the source body's
  natural phrasing. Use words that already appear, or near-paraphrases.
- Do **not** suggest new link targets outside the corpus link table.
- Do **not** rank pieces, suggest edits, or comment on the writing.
  Link curation only.
- Do **not** emit suggestions for end-of-piece "related reading" blocks.
  That's a separate curation pass. Inline only.

## Self-check before emitting

For each candidate suggestion, ask:
- Would a human editor agree this anchor → target serves the reader?
- Is the anchor a topical entity, not a generic phrase?
- Is the confidence honestly >= 4?

If any answer is no, drop the suggestion.
