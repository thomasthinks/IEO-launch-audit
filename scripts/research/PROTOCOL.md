# Auto-research protocol — IEO-launch-audit Phase C

**Purpose:** execution guide for a Claude Code session invoked monthly
via `/schedule` against this repo. Read this file, follow the protocol,
ship a PR. Reviewer (TJ) decides what merges.

**Authority:** [ADR 0001](../../docs/decisions/0001-claim-verification.md)
(claim-verification + steelman reflex) +
[ADR 0002](../../docs/decisions/0002-self-improving-skill.md)
(Decision 4: monthly cadence, opens PR, never auto-merges).

**Budget per pass:** ~2-3h subagent runtime + ~30min consolidation +
~$50-90 in Claude credits. See ADR 0001 § "Budget expectation per pass."

---

## 0. Preconditions

When invoked from `/schedule`, the calling session has:

- The IEO-launch-audit repo cloned + `cd`'d in.
- Claude Code's full tool surface (Agent, Bash, Edit, Read, Write).
- `gh` CLI authenticated (caller responsibility — protocol degrades to
  "commit + push to branch + emit manual-PR-creation note" if not).

If any precondition fails, write a `scripts/research/.last-pass-error.md`
with the failure mode + early return. Subsequent `/schedule` invocations
detect the marker + skip until cleared.

---

## 1. Pass identification + branch setup

```bash
PASS_YEAR_MONTH=$(date -u +%Y-%m)
BRANCH="auto-research/${PASS_YEAR_MONTH}"
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
git reset --hard origin/main
```

If `$BRANCH` already exists on remote, **abort** with a note in
`.last-pass-error.md` — a prior pass is still open as a PR; resolve
that first before running another pass.

---

## 2. Discovery wave — 5-7 parallel subagents

Dispatch **5-7 parallel Agent calls** (single message, multiple
`Agent` tool uses). Each subagent gets ~60-100 tool uses and one
corpus from the 8-corpus list in ADR 0001 § "Expanded corpora":

1. **Academic / methodology-disclosed primary research.** arXiv sanity,
   Semantic Scholar, ACM Digital Library, Papers with Code, conference
   proceedings (NeurIPS / ICML / EMNLP / SIGIR / KDD / WWW). Time
   window: last 12 months.
2. **First-party platform documentation.** developers.google.com,
   platform.claude.com, help.openai.com, perplexity.ai/hub,
   learn.microsoft.com, blogs.bing.com, brave.com/blog. Highest
   signal-to-noise for engine-behavior claims.
3. **Conference talk catalogs.** BrightonSEO (Apr + Sep), SMX
   (Munich / West / East / Advanced), Pubcon, MozCon, SEOFOMO Live.
4. **Practitioner long-form on LinkedIn.** Named practitioners:
   Kevin Indig, Mike King, Aleyda Solís, Lily Ray, Marie Haynes,
   Cyrus Shepard, Glenn Gabe, Will Critchlow, AJ Kohn. Higher signal
   than vendor blogs (reputation staked).
5. **Newsletter back-issues.** SEOFOMO (Solís), Growth Memo (Indig),
   Indie SEO, Search Engine Roundtable, Mostly Harmless (Gabe).
6. **Practitioner subreddits.** r/SEO, r/bigseo, r/TechSEO. Filter by
   karma + comment density + recency. Useful for counter-evidence to
   vendor consensus.
7. **GitHub awesome-lists + GEO-tooling repo discussions + YouTube
   speaker transcripts.** awesome-llm-seo, awesome-geo, awesome-
   llmstxt, BrightonSEO YouTube channel, named-practitioner channels.

**Per-subagent prompt template** (full text in
`scripts/research/discovery-prompt-template.md` — generate via
`auto-pass.sh prepare-prompts` if absent). Key elements:

- Tag every claim with **source tier** (primary / first-party /
  methodology-disclosed / practitioner / FOLKLORE).
- **Verbatim quotes only** for empirical claims; preserve bounds.
- **Audit-shape filter**: each hypothesis must include a one-sentence
  detection mechanism that maps to a static-site audit check.
- Output per hypothesis: id, source URL, verbatim quote, methodology,
  source tier, audit-shape mapping, existing-skill-coverage, confidence.

Time-box: 15-30 min wall-clock for the parallel dispatch.

---

## 3. Consolidate discovery into hypothesis slate

Read all 5-7 discovery reports. Pick the top 5-10 hypotheses for
steelman based on:

- **Multi-corpus convergence** (≥3 corpora confirm direction).
- **Audit-shape clarity** (detection mechanism sketchable in one sentence).
- **Novelty against current check set** (skim `SKILL.md` for
  existing coverage).

Write the consolidated slate to:

```
scripts/research/${PASS_YEAR_MONTH}-discovery-slate.md
```

Format: one section per hypothesis with multi-corpus citations. Lead
with strongest. Flag folklore at the end.

---

## 4. Steelman wave — 3-5 parallel subagents

For each top hypothesis (or hypothesis-pair), dispatch a steelman
subagent. Its task: **find the strongest available primary, first-
party, or methodology-disclosed evidence FOR the hypothesis**. Opposite
incentive structure to verification (incentivized to find evidence,
not attack it).

**Mandatory mechanics (ADR 0001 § Failure mode of steelman):**

- Verbatim quotes with source URLs only — never paraphrase empirical
  claims.
- Source-tier tagged explicitly per finding.
- Exhaust corpora before reporting — don't stop at first hit.

Write findings to:

```
scripts/research/${PASS_YEAR_MONTH}-steelman.md
```

Time-box: 15-25 min wall-clock.

---

## 5. Verification wave — 3-5 parallel subagents

For each steelman finding, dispatch a verification subagent. Its task:
**attack the finding**. Re-fetch source URLs, confirm verbatim quotes,
apply folklore patterns 1-4 (precise-%-no-methodology / submit-to-
nonexistent-product / single-source-boundary-smoothed / vendor-weight-%-
for-closed-source-ranking).

**Disposition per finding:**

- **PROMOTE** — quote confirmed, methodology disclosed, no folklore
  pattern triggered.
- **DEMOTE** — quote confirmed but claim narrower than steelman
  framed.
- **KILL** — quote not at URL, paraphrase-strengthening, folklore
  pattern triggered, or primary source contradicts framing.

Write to:

```
scripts/research/${PASS_YEAR_MONTH}-verification.md
```

Target distribution: 4-7 PROMOTE / 1-3 DEMOTE / 0-2 KILL per pass.
Outside band suggests calibration issue (rubber-stamping or
over-killing).

Time-box: 10-20 min wall-clock.

---

## 6. Final consolidation

Write the survivor slate to:

```
references/research-${PASS_YEAR_MONTH}.md
```

Sections:

1. **Pass summary** (release-cycle target, total subagent count,
   approximate cost).
2. **Promoted candidates** (ordered by evidence strength + audit-shape
   + budget cost).
3. **Demoted hypotheses** (real-but-narrower; logged for future passes
   to reconsider with new evidence).
4. **Killed hypotheses** (with verification reasoning; future passes
   should NOT re-propose without new evidence).
5. **New folklore patterns observed** (worth logging as ADR 0001
   pattern subtypes).
6. **Recommended v1.x candidate slate** (concrete: which checks ship,
   which extend, which framing-patches land).

Update `MEMORY.md`-style file in `~/.claude/projects/-home-thomas-projects-IEO-launch-audit/memory/`
WITH PERMISSION — auto-pass should NOT touch user memory without TJ
ratifying. Surface the proposed memory update in the PR description
instead.

---

## 7. Ship as PR

Run `scripts/research/auto-pass.sh ship` (operates the git/gh
sequence):

```bash
bash scripts/research/auto-pass.sh ship "$PASS_YEAR_MONTH"
```

The script:

1. Stages the new files (`references/research-${PASS_YEAR_MONTH}.md` +
   `scripts/research/${PASS_YEAR_MONTH}-*.md`).
2. Creates a commit with conventional-commits format
   (`research(auto): ${PASS_YEAR_MONTH} monthly research pass`).
3. Pushes the branch.
4. Opens a PR via `gh pr create` with a body that summarizes the
   PROMOTE / DEMOTE / KILL counts + the proposed candidate slate +
   the verification provenance.

**Never** `git merge` or `gh pr merge` from this protocol. ADR 0002
Decision 3 + 4: maintainer reviews + decides.

---

## 8. Error handling

If any step fails:

- Write `scripts/research/.last-pass-error.md` with the failure mode +
  timestamp + which step failed + recovery guidance.
- Commit the error file to the branch (so PR description surfaces it).
- Open the PR anyway with a `[FAILED]` prefix in title.

If `gh` is unavailable, fall back to committing + pushing the branch +
writing a manual-PR-creation note to `.last-pass-error.md`.

---

## 9. Idempotency + skip conditions

The protocol is **not** idempotent per-month — re-running for the same
`$PASS_YEAR_MONTH` will fail at branch creation. This is intentional:
each month produces exactly one PR.

Skip conditions:

- An existing `auto-research/${PASS_YEAR_MONTH}` branch on remote (prior
  pass is open as a PR).
- A `scripts/research/.last-pass-error.md` file in the current working
  tree (prior pass failed; TJ must clear).
- The current month has fewer than 14 days remaining (don't ship a pass
  the operator won't review before next cycle).

---

## 10. Calibration triggers for the maintainer

After 3 monthly passes, review:

- **Pass landed zero novel candidates 3x consecutive** → drop monthly
  cadence to quarterly per ADR 0002 Decision 4's testable trigger.
- **Pass cost exceeded $150 average 3x consecutive** → tighten subagent
  budgets (cap discovery at 5 instead of 7; cap steelman/verification
  at 3 instead of 5).
- **>30% of PROMOTE-tier candidates later prove wrong in v1.x audits**
  → tighten verification subagent prompts; consider triple-pass
  (discovery → steelman → verification → meta-verification).

These are the testable signals ADR 0002 declared.

---

## Quick reference

| Step | Action | Output | Time-box |
|---|---|---|---|
| 1 | Branch setup | `auto-research/YYYY-MM` | 30s |
| 2 | Discovery (5-7 subagents parallel) | per-corpus reports | 15-30min |
| 3 | Consolidate → slate | `YYYY-MM-discovery-slate.md` | 5-10min |
| 4 | Steelman (3-5 parallel) | `YYYY-MM-steelman.md` | 15-25min |
| 5 | Verification (3-5 parallel) | `YYYY-MM-verification.md` | 10-20min |
| 6 | Final consolidation | `references/research-YYYY-MM.md` | 10-15min |
| 7 | Ship PR | `gh pr create` | 1min |

Total: ~60-100min wall-clock; ~$50-90 in Claude credits.

---

## Authority + scope

This protocol industrializes the research discipline ratified in:

- ADR 0001 (claim-verification + steelman reflex, v1.4.1)
- ADR 0002 (self-improving skill architecture, v1.4.2)

The protocol does NOT:

- Mutate the skill's checks directly. Only writes research artifacts
  + opens a PR. Maintainer reviews + decides what merges.
- Mutate consumer-side state files (`.ieo-audit-state.yml`). Those are
  per-repo and out of auto-research scope.
- Touch maintainer memory (`~/.claude/projects/...`). Memory updates
  are PR-suggested, not auto-applied.
