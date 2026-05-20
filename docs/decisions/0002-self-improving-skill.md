# ADR 0002 — Self-improving skill architecture (state, self-analyze, auto-research)

**Status:** Accepted (v1.4.2, 2026-05-20)
**Context:** v1.4 + the v1.5 research pass surfaced the architectural gap
**Decision:** Skill evolves from pure-function audit to lightly-stateful audit with periodic self-analysis. Auto-mutation explicitly NOT in scope.

## Context

The skill v1.0 → v1.4 architecture is **pure-function**: run audit → emit findings → exit. No memory, no learning, no measurement of whether emitted findings helped consumers. The audit-diff substrate added in v1.2 (`audit_diff.py` + `.launch-readiness-report.prev.json` auto-rotation) was a half-step toward statefulness — it can compare run N vs run N−1 within a single working directory but does not persist findings across consumer-side reinstalls, version bumps, or out-of-band repo migrations.

This produces three structural gaps:

1. **No measurement of operator action.** If the skill flags "fix figcaption" in run N, did the operator fix it before run N+1? The audit-diff captures this transiently, but the skill never learns that "figcaption-sparse findings are typically actioned within 30 days" or "consumer X has had finding Y open for 4 passes." Every run starts blind.
2. **No signal on whether findings move outcomes.** Even when an operator acts on a finding, the skill never sees whether that action correlated with any measurable effect (indexing-state delta, citation-state delta, traffic delta). The skill recommends; it never learns from recommendations that worked vs didn't.
3. **No mechanism for the skill to evolve from real consumer experience.** New checks ship via human-driven research passes (v1.1 → v1.5). The skill never tells the maintainer "this check fires 80% of the time across 4 consumers; the threshold may be miscalibrated" or "no consumer has actioned this finding in 6 months; consider deprecation."

The v1.4 research pass + v1.5 candidate slate were the forcing function: without measurement-side scaffolding, future check candidates ship blind and stay shipped regardless of whether they help. The four load-bearing decisions in this ADR define the architecture that closes the gap.

## Four load-bearing decisions

### Decision 1: Primary measurement signal is audit-diff persistence across passes

Realistically usable signals ranked by signal-to-noise:

| Signal | What it measures | S/N | Status in skill |
|---|---|---|---|
| **Audit-diff persistence across passes** | Operator action rate (WARN → PASS?) | **HIGH** | Partial — `audit_diff.py` + `.prev.json` snapshot exist; needs cross-pass state persistence |
| GSC index snapshot delta | Indexed URL count change | MEDIUM | yes (check 12) |
| Bing Webmaster API delta | Impressions/clicks for sitemap URLs | MEDIUM | yes (check 12) |
| Wayback CDX content-digest delta | Confirms content actually changed (not just metadata) | MEDIUM (companion-only) | yes (check 7.5 substrate) |
| LLM citation tracker JSON drop | "Were we cited" — stochastic, needs n≥5 sampling | LOW | no |

**Decision: audit-diff persistence is the primary measurement signal. GSC/Bing deltas are companion signals reported at confidence-tier "medium" at best. LLM citation tracking is too noisy to be load-bearing.**

Reasoning: audit-diff has the cleanest attribution chain. Skill emitted finding X in pass N. Audit-diff in pass N+1 shows finding X became PASS. Operator acted on X. No seasonality confound, no algo-update noise, no engine-policy-event interference. The causal chain at the *action layer* is clean even though the causal chain at the *outcome layer* is messy.

GSC/Bing deltas have attribution noise (algo updates, seasonality, other operator changes, content-side edits the skill didn't recommend) that the skill cannot disambiguate. They should be reported but never claim causation. Confidence-tier framing is mandatory in any output that surfaces these signals.

LLM citation tracking (Profound, Otterly, Brave probe, GSC AI-mode impressions) is too noisy to be load-bearing for a single-shot audit. Per the v1.4 measurement-variance advisory in check 11, LLM citation outputs are stochastic; n≥5 sampling per query with stratified prompt variants is required for any defensible measurement. This is outside the skill's audit-time scope; surface it as advisory only.

**What would change this decision:** if audit-diff turns out to measure compliance theater (operators "fix" findings cosmetically without addressing the underlying issue — e.g., adding empty `alt=""` to satisfy alt-text density without descriptive content). Then audit-diff measures the wrong thing. Mitigation: pair with substantive-edit detection (Wayback CDX content-digest or git-diff size signals) where possible to distinguish cosmetic from substantive fixes.

### Decision 2: State location is consumer repo, committed, version-controlled

Three options considered:

- **(a) Consumer repo** (e.g., `.ieo-audit-state.yml` at repo root, committed by the operator). Survives skill updates and reinstalls. Visible to operator. Diffable in code review.
- (b) Skill-side artifact (`~/.claude/skills/IEO-launch-audit/state/<repo-hash>/...`). Doesn't survive skill reinstall; not portable across operator machines; not visible to operator unless they go looking.
- (c) No state file — infer state from git history every pass. Slow; brittle to commit-message hygiene; loses everything the skill knows that git doesn't.

**Decision: (a) primary + (c) as fallback when state file is absent.** The skill writes the state file at end of each audit pass; the operator commits it (or doesn't); subsequent audits read it. When absent, the skill mines `git log` for commits matching flagged-finding fix patterns and bootstraps inferred state.

Reasoning: state belongs in the consumer repo because it's *about* that repo. It needs to survive skill version bumps (skill ships as `.claude/skills/IEO-launch-audit` — reinstall wipes skill-side state). It needs to be inspectable + diffable by the operator (otherwise the skill knows things the operator can't see, which is opaque). It needs to be portable across operator machines (multi-developer audit teams).

(b) loses on portability + reinstall-survival. (c) loses on reliability — commit-message conventions vary, fix-commit patterns are not standardized, and the skill would re-mine the same history every pass for no benefit. Combining (a) primary + (c) fallback gives both reliability when state exists and graceful-degrade when it doesn't.

**What would change this decision:** if state files become large enough that committing them is friction (e.g., >100KB binary). Then split: hot state in repo, archive in skill-side artifact. For now, expected state size is <10KB per audit pass (findings list + operator-action history) and grows logarithmically. The state file is human-readable YAML; operators can `git diff` it.

### Decision 3: Auto-learn output is advisory-only — never auto-mutating

Spectrum of auto-learn behaviors considered:

- **(a) Read-only advisory.** Auto-learn emits a `auto-learn-report.md` for the maintainer to review. Never auto-modifies skill code, configs, or thresholds.
- (b) Threshold adjustment. Auto-learn writes config-side changes (e.g., adjusts `multimodal_figcaption_pass` from 0.7 to 0.6 based on cross-repo action rate). Bounded mutation; reversible.
- (c) Check promotion / demotion. Auto-learn promotes opt-in checks to default, OR drops underperforming checks from the default set.
- (d) Self-rewriting checks. Auto-learn edits check scripts (e.g., adjusts the regex in `check-multimodal-markup.py` based on false-positive rate).

**Decision: (a) only, at least through v1.7.** Advisory-only output. The auto-learn pass emits a `auto-learn-report.md` artifact; the maintainer reviews and decides whether to mutate the skill via normal git PR review.

Reasoning: the failure mode of (b)-(d) is **drift toward consumer-bias**. Skill loosens thresholds because consumers don't act on findings; the conclusion becomes "check too strict" when reality might be "operators haven't gotten around to fixing it yet" or "operators don't understand the finding's importance." Auto-mutation needs a way to distinguish "evidence the recommendation is wrong" from "evidence the operator is busy or confused." The skill doesn't have that distinguishing signal yet, and the cost of mis-calibration (looser thresholds → real findings missed) compounds.

Advisory-only preserves the discipline pattern established by ADR 0001: skill surfaces evidence; maintainer decides what mutates. Same pattern as the verification-subagent reflex (subagents surface; maintainer ratifies). Same pattern as the steelman amendment (steelman finds evidence; verification attacks; maintainer decides what survives).

**What would change this decision:** after 3-6 months of (a) running, if the recommendations are obvious and uncontroversial ("threshold X should be 0.6 not 0.7; this has been recommended in 4 consecutive monthly auto-learn reports across 3 consumer repos"), promote to (b) with narrow scope. Don't start at (b)-(d); earn the trust via (a) first.

### Decision 4: Auto-research scheduled monthly, opens PR, never auto-merges

Frequency considered: weekly (too noisy — GEO landscape doesn't move weekly; signal/noise of weekly cadence is poor), monthly (right cadence — aligned with industry research-cycle pace), quarterly (too slow given field's evolution rate).

Mechanism: a `scripts/research/auto-pass.sh` orchestrator lives in the skill repo. A scheduled remote agent (Claude Code `/schedule` pointing at the IEO-launch-audit repo) runs it monthly. Output: opens a PR with `references/research-YYYY-MM.md` updates + a candidate-slate markdown for the next version + an `auto-learn-report.md` summarizing cross-repo state findings (if multi-repo state is available).

**Decision: monthly cadence, PR-opening, maintainer reviews + decides — never auto-merge.**

Reasoning: same advisory-only discipline. The auto-research surfaces findings under the ADR 0001 two-reflex discipline (steelman + verification). Maintainer ratifies. Cost: ~$50-90/month in Claude credits per the budget established in ADR 0001's amended Consequences section.

**What would change this decision:** if the monthly cadence surfaces zero novel candidates for 3+ months running, drop to quarterly. If 2+ novel candidates per month surface consistently, hold cadence or consider bi-monthly. Run length is the calibration signal; this is testable.

## Phased rollout

Don't ship all this at once. Phase A is real release-shape work for v1.5; B-D are forward-looking.

- **Phase A (v1.5):** **State-file substrate + self-analyze.** Skill writes `.ieo-audit-state.yml` to consumer repo at end of audit. Self-analyze reads it; audit-diff persistence becomes the primary measurement. New audit-report section: "Operator action since last pass." Git-log fallback when state file absent. Config gate (`state_tracking: true`, default true).
- **Phase B (v1.5.x or v1.6):** **GSC / Bing delta integration in self-analyze.** Check 12 already has API surfaces; add cross-pass persistence + confidence-tier reporting in self-analyze output. Pair with Wayback CDX substantive-edit confirmation to distinguish cosmetic vs substantive fixes.
- **Phase C (v1.6):** **Auto-research routine.** `scripts/research/auto-pass.sh` + scheduled remote agent + PR-opening pipeline. Monthly cadence under ADR 0001 two-reflex discipline.
- **Phase D (v1.7+):** **Cross-repo auto-learn.** Aggregate state across multiple consumer repos (maintainer's fleet OR an opted-in public-consumer cohort) and emit `auto-learn-report.md`. Privacy gate: opt-in only; never collect without explicit consumer-side configuration.

Per-phase scope keeps each release small enough to ship cleanly + rollback if it regresses. Phase A alone is a meaningful release.

## Consequences

**Positive:**

- Skill closes the gap between "we recommended X" and "we observed X became PASS." Measurement-side scaffolding makes future evidence-driven check tuning possible.
- The auto-research routine (Phase C) industrializes the research discipline ADR 0001 ratifies. Manual research passes become the exception, not the rule.
- Per-repo state makes per-consumer adaptation easier without skill-side mutation. Operators can document why they suppress a finding ("we know about X, intentionally accepting risk") and the skill respects it without losing the context across reinstalls.
- The maintainer can detect skill-side calibration drift (e.g., "check 14 has 80% WARN rate across all consumers" → threshold likely miscalibrated) and act on it via normal PR review.

**Negative:**

- **Skill is no longer pure-function.** State-file shape, migration, missing-file degradation, corrupted-file handling all become test surface. The "stdlib-only + graceful-degrade" rule from CLAUDE.md extends to every state-aware feature.
- **Consumer onboarding gains a step** ("first run produces state file; commit it"). Soft-required with clear messaging when absent; not gating but visible in audit output.
- **Cost.** Monthly auto-research at ~$50-90 = ~$600-1080/year ongoing operational cost. Worth it for an actively-used skill; over-budget if skill goes dormant. Mitigate by pausing auto-research scheduling when no new candidates surface for 3+ months.
- **Causation is unsolvable.** The skill will report correlations between findings-acted-on and outcome-deltas; consumers must read these as correlation only. Confidence-tier framing is mandatory in any output that surfaces GSC/Bing deltas as correlated with audit findings.

## What would change this decision

- **A consumer surfaces a load-bearing use-case that the current pure-function shape blocks.** E.g., "I need the skill to remember why I suppressed finding X last month" — that's already happening implicitly via consumer-side comments; this ADR makes it explicit.
- **Auto-learn proves unsafe.** If after 6 months of advisory-only output the recommendations are routinely wrong (recommend tightening thresholds that should loosen, or vice versa), demote to "no auto-learn; manual research only."
- **State-file bloat becomes friction.** Split state into repo-side hot + skill-side archive per Decision 2's fallback option.
- **Auto-research cadence underperforms.** Drop monthly to quarterly per Decision 4's testable trigger.
- **Anthropic or a successor platform ships a primary-source-verification or audit-state-tracking primitive** that supersedes this architecture. Unlikely soon but tracked.

## Related

- [ADR 0001](0001-claim-verification.md) — claim-verification reflex + steelman amendment (v1.4.1). The research discipline this architecture industrializes.
- v1.5 candidate slate (CHANGELOG entry forthcoming) — the new checks that need the state-file substrate to measure their effect post-launch.
- v1.2 `audit_diff.py` + `.prev.json` rotation — the existing audit-diff substrate that Phase A builds on.
- ROADMAP § "v1.5+ candidates" — NLWeb / Bing AI Performance API deferrals; both could be re-evaluated once the state-file substrate exists to measure their post-ship impact.
