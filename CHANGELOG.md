# IEO-launch-audit — Changelog

All notable changes to this skill. Follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + SemVer.

## [1.6.0] — 2026-05-20

Phase C of ADR 0002 ships. The skill now has a routine for monthly
auto-research: a Claude Code session invoked via `/schedule` reads
`scripts/research/PROTOCOL.md`, dispatches the two-reflex discipline
(discovery → steelman → verification) per ADR 0001, consolidates
findings, and opens a PR for maintainer review. **Activation is
operator-side** — the routine is ready; configure `/schedule` when
ready to start the monthly cadence.

### Added

- **`scripts/research/PROTOCOL.md`** — execution guide for a Claude
  Code session running the auto-research pass. ~250 lines covering:
  - **Preconditions** (clone + cwd, Agent tool surface, gh CLI).
  - **Branch setup** (`auto-research/YYYY-MM` from main).
  - **Discovery wave** — 5-7 parallel subagents across the 8 corpora
    mandated by ADR 0001 (academic primary, first-party platform,
    conference talks, practitioner LinkedIn, newsletters, subreddits,
    GitHub awesome-lists + YouTube). 60-100 tool uses each.
  - **Steelman wave** — 3-5 parallel subagents finding verbatim
    evidence FOR top hypotheses. Opposite incentive structure to
    verification.
  - **Verification wave** — 3-5 parallel subagents attacking findings.
    PROMOTE / DEMOTE / KILL disposition; target distribution
    4-7 / 1-3 / 0-2.
  - **Consolidation** → `references/research-YYYY-MM.md`.
  - **Ship** via `auto-pass.sh ship YYYY-MM`.
  - **Error handling** — `.last-pass-error.md` marker; PR opens with
    `[FAILED]` prefix when errors occur.
  - **Idempotency + skip conditions** — one PR per month max; skip
    when prior PR open OR error marker exists OR <14 days remain.
  - **Calibration triggers** for the maintainer — testable signals
    that flip cadence to quarterly OR tighten subagent budgets OR
    add a meta-verification pass.

- **`scripts/research/auto-pass.sh`** — git + gh ship mechanics
  (~120 LoC stdlib bash). Two subcommands:
  - `init [YYYY-MM]`: verifies no prior PR open, sets up
    `auto-research/YYYY-MM` branch from `origin/main`.
  - `ship YYYY-MM`: stages research artifacts, commits with
    conventional-commits prefix, pushes branch, opens PR via `gh`
    with a maintainer-review-required body. Degrades gracefully when
    `gh` is absent (commits + pushes + writes manual-PR-creation note).

- **`scripts/research/README.md`** — usage doc + scheduled-cadence
  configuration example for Claude Code `/schedule`.

### Architecture invariants preserved

Per ADR 0001 + ADR 0002, the routine **never**:

- Merges PRs (maintainer reviews + decides every candidate).
- Mutates skill checks directly (only writes research artifacts +
  opens a PR).
- Mutates consumer state files (per-repo `.ieo-audit-state.yml` is
  consumer-side; out of auto-research scope).
- Updates maintainer memory automatically (memory updates are
  PR-suggested via PR body, not auto-applied).

### What this enables

With Phase A + B + C all shipped, the skill's self-improving loop is
complete in its minimum-viable form:

1. **Consumer-side measurement** (Phase A): `.ieo-audit-state.yml`
   tracks operator action across passes.
2. **Outcome correlation** (Phase B): indexing-state delta from
   check 12 paired with operator action, medium-confidence framing.
3. **Maintainer-side knowledge refresh** (Phase C): monthly
   auto-research PR surfaces new candidates under the two-reflex
   discipline; maintainer ratifies.

**Phase D (cross-repo auto-learn)** remains deferred to v1.7+ — needs
multi-repo state aggregation + opt-in privacy gating.

### Changed

- **`SKILL.md`** version bumped 1.5.2 → 1.6.0 (minor — new feature
  surface).
- **`README.md`** Status line updated.

### Migration notes for v1.5.x consumers

No breaking changes. No new config required for consumer-side audit
runs. Phase C ships only the maintainer-side research-routine scripts;
consumer-side audit behavior is unchanged.

To activate the monthly cadence:

```
/schedule monthly-on-1st 09:00 "Run the IEO-launch-audit auto-research pass per scripts/research/PROTOCOL.md against github.com/thomasthinks/IEO-launch-audit"
```

When activated, expect:
- 1 PR per month (auto-opened, maintainer-reviewed).
- ~$50-90/month operational cost in Claude credits.
- ~60-100min wall-clock per pass (parallel subagent dispatch).
- Calibration after 3 passes: if zero novel candidates surface 3x
  consecutive, drop to quarterly per ADR 0002 Decision 4's testable
  trigger.

## [1.5.2] — 2026-05-20

Phase B of ADR 0002 ships. The skill now pairs its primary measurement
signal (audit-diff persistence — Phase A) with a companion signal
(indexing-state delta from check 12). Strict confidence-tier framing
preserved: attribution noise is unresolvable so the skill reports
correlation, never causation.

### Added

- **Phase B GSC/Bing delta integration in `scripts/self-analyze.py`.**
  When self-analyze runs, it now ALSO:
  1. Reads the auto-rotated prev report JSON
     (`.launch-readiness-report.prev.json`, established in v1.2's
     `audit_diff.py` substrate).
  2. Extracts numeric metric values from check 12 findings'
     `current` field. Five metric IDs supported:
     - `bing.crawl_errors_7d` (from `12.bing.crawl_errors.current.crawl_errors_7d`)
     - `bing.crawled_pages_7d` (from `12.bing.crawl_errors` or `12.bing.crawl_stats`)
     - `gsc.indexed` (from `12.gsc.indexed_vs_sitemap.current.indexed`)
     - `gsc.sitemap` (from `12.gsc.indexed_vs_sitemap.current.sitemap`)
  3. Computes deltas (absolute + percentage) when the same metric is
     present in both current and prev.
  4. Emits an **"Indexing-state context (Phase B, medium confidence)"**
     subsection in the audit report immediately after the "Operator
     action since last pass" section.

  **Confidence-tier framing (mandatory in section body):**
  > Companion signals only. Per ADR 0002 Decision 1, audit-diff
  > persistence is the primary measurement; the deltas below are
  > reported at confidence-tier MEDIUM at best. Attribution noise is
  > unresolvable — indexing-state shifts could be operator action,
  > Google/Bing algorithm updates, seasonality, or other operator
  > changes the skill didn't recommend. Do not claim causation; read
  > as correlation only.

  When resolved-findings count >0, the section also notes that any
  positive delta is "directionally consistent with operator action
  but cannot be causally attributed." When 0 resolved findings, the
  section notes deltas are independent of skill recommendations.

  Implementation: ~120 LoC added to `self-analyze.py`. Stdlib only.
  Zero new network calls. Degrades silently when prev report or check
  12 findings absent.

### Changed

- **`scripts/self-analyze.py`** Phase B section appended automatically
  to the audit report when prerequisites are met. No config gate yet
  — section emits only when prev + current both have check 12 metrics,
  so first-pass + non-check-12 consumers see nothing new (graceful
  degrade).

- **`SKILL.md`** version bumped 1.5.1 → 1.5.2.

- **`README.md`** Status line updated.

### Phase A + Phase B interaction (cumulative effect)

A consumer running v1.5.2 against a repo with state file + check 12
configured + a prev report will now see, in order, at the end of
their audit report:

1. **Per-check finding sections** (unchanged from v1.x default).
2. **"Operator action since last pass"** — Phase A categorization
   (resolved / regressed / persistent / new / long-running).
3. **"Indexing-state context (Phase B, medium confidence)"** — Phase B
   metric deltas table + confidence-tier framing + resolved-count
   context paragraph.

The two phases pair as designed: Phase A measures the action layer
(did the operator fix?); Phase B measures the outcome layer (did
indexed-count move?). Both are surfaced; neither is conflated.

### What's NOT in Phase B (deferred to Phase C / v1.6+)

- **Long-term trend persistence.** Phase B uses only the immediate prev
  pass (auto-rotated `.prev.json`); no multi-pass metric history is
  retained. If long-term trend is needed, a future schema migration
  (state_version 1 → 2) can add a `metrics` field to `.ieo-audit-state.yml`.
- **Substantive-edit confirmation pairing.** Phase B does not yet pair
  resolved findings with Wayback CDX content-digest delta to confirm
  the operator actually changed visible content (vs cosmetic
  dateModified-style flips). Logically natural for Phase B+ but
  separate work.
- **Cross-engine LLM citation deltas.** Profound / Otterly / SE Ranking
  JSON drops not yet ingested by self-analyze; consumer would need a
  state-side schema for tracking. Deferred to Phase D (cross-repo
  auto-learn) or later.
- **Auto-research routine.** Phase C — separate forthcoming work.

### Migration notes for v1.5.1 consumers

No breaking changes. No new files. No new config gates. Existing audit
output unchanged on first run; Phase B subsection appears on subsequent
runs when prev report + check 12 metrics are both present.

Smoke-tested end-to-end: prev pass with check 12 metrics (GSC 180/250
indexed, Bing 1430 crawled) → current pass after operator fixed
schema_text_parity (GSC 220/250, Bing 1610) → Phase B report shows
+40 indexed (+22.2%), +180 crawled (+12.6%), correctly labeled as
medium-confidence companion signal.

## [1.5.1] — 2026-05-20

The v1.4.1 deep research pass closes out. Five firm candidates that
survived steelman + verification ship atop Phase A. Each finding-text
preserves the verification-mandated caveats (engine-coverage, Phase-4
scope, ChatGPT-only boundary, EU-skew where applicable).

### Added

- **Check 9.10 — first-30% positional check.** New sub-check in
  `scripts/check-content-tactics.py`. For each content piece with
  body ≥60 words, extract the first 30% of body text and detect:
  (a) declarative copula pattern (X is Y / X means Y / X refers to Y /
  X involves Y / X denotes Y / X describes Y); (b) ≥2 distinct multi-
  word title-cased phrases as a named-entity proxy. A piece is
  "front-loaded" when both fire. Severity gradient: PASS ≥60%, INFO
  30-60%, WARN <30% of pieces.

  **Evidence:** Kevin Indig "The science of how AI pays attention"
  (Growth Memo Feb 2026) — 18,012 verified citations from 1.2M ChatGPT
  responses, 44.2% in first 30% of text, entity density 20.6% in cited
  text vs 5-8% baseline, p<0.0001. all-MiniLM-L6-v2 embeddings at
  cosine 0.55. Methodology fully disclosed; verified primary. Mechanistic
  prior: Liu et al. "Lost in the Middle" (TACL 2024, peer-reviewed) —
  LLMs preferentially attend to beginning + end of context.

  **Mandatory caveats in finding text:** ChatGPT-only boundary (Indig's
  data is single-engine); Liu et al. measures in-context retrieval,
  not web-citation, so use as mechanism not direct replication; entity
  density heuristic uses title-cased phrase proxy, not full NER.

- **Check 11.L — multi-UA live-apex crawler probe (opt-in).** New
  phase in `scripts/check-live-apex.py`. Gated on `multi_ua_probe: true`
  in `.launch-readiness.yml` (default off). When opted-in: 1 baseline
  browser-UA fetch of apex + 6 AI-bot UA fetches (GPTBot, OAI-SearchBot,
  ClaudeBot, Claude-SearchBot, PerplexityBot, Google-Extended). Compares
  response status + body size. Emits:
  - `11.L.multi_ua_clean` (PASS) — all AI bots get 200 + comparable body
  - `11.L.ai_bot_blocked` (WARN) — ≥1 bot gets 403/429/503
  - `11.L.ai_bot_shrunk` (INFO) — ≥1 bot gets <70% baseline body (likely
    WAF challenge / interstitial)
  - `11.L.multi_ua_skip` (MANUAL_VERIFY) — baseline fetch failed

  **Evidence:** Aleyda Solis on Humans of Martech Ep 202 (Jan 2026) —
  "I realized my hosting company was blocking AI bots… I only found
  it because I dug deep into the validation." Cloudflare default-block
  (July 2025, opt-in-at-signup mechanism per Cloudflare press release;
  416B AI-bot requests blocked at edge July → Dec 2025). HUMAN Security
  per-crawler spoof ratios (1:5 ChatGPT-User → 1:88 Perplexity-User)
  validate UA+IP cross-check as the detection method.

  **Mandatory framing fix from verification:** Cloudflare mechanism is
  opt-in-at-signup, not silent auto-block on every zone. BuiltWith
  robots.txt-block adoption numbers (5.6M GPTBot, 5.8M ClaudeBot) are
  source-side detectable and adjacent context, not core evidence.

### Changed

- **Check 2.4.schema_text_parity finding text strengthened** in
  `scripts/check-schema.py`. Fix-action now cites three independent
  methodology-disclosed studies converging on JSON-LD invisibility
  during direct retrieval: (a) SearchVIU 2025 5/5-systems experiment;
  (b) Ahrefs 1,885-page DiD (Mar 2026) — AIO −4.6%, AI Mode +2.4%,
  ChatGPT +2.2%; (c) OtterlyAI Mar 2026 self-attribution ("6 of 7
  platforms can't access schema markup when directly queried").
  Phase-4-only scope caveat added: this covers direct-retrieval
  pathways; indexing + training pathways are unmeasured and schema
  may still help there.

- **Check 7.5.substantive_delta finding text strengthened** in
  `scripts/check-sitemap.py`. Fix-action now cites arXiv:2509.11353
  ACM SIGIR-AP 2025 peer-reviewed evidence: rank shifts of up to 95
  positions, pairwise-preference reversals up to 25% on average across
  7 LLMs with synthetic date injection, p<0.05. Pairs with Ahrefs
  16.975M-citation field study (Jul 2025) showing ChatGPT cites
  content 393-458 days newer than organic results, and Bing's May 2026
  first-party grounding statement: *"In grounding, a stale fact
  produces a misleading response."* Scope caveat on arXiv evidence
  preserved (LLM-as-reranker on TREC passages, NOT production-citation
  telemetry).

- **`checks/12-search-console.md` — new section "Cross-engine citation
  portfolio (don't aggregate)".** Documents the three converging
  methodology-disclosed studies on narrow cross-engine overlap (Indig
  Consensus Gap 91.07% single-engine on 3.7M citations EU-weighted;
  SISTRIX Jaccard 0.17 between AIO + AI Mode on 1.55M snapshots × 17
  weeks × 6 countries; arXiv:2510.11560 4,606-query peer-publishable).
  Plus the Nature Communications 2025 finding that <10 distinct URLs
  cover 80% of LLM responses per query — strategic implication for
  entity-hub (check 5) + backlink (check 10) emphasis.

  **Mandatory caveats in doc:** Indig is EU-weighted (Spain + UK +
  Nordics) so US-market magnitude generalization unproven; no public
  study covers ChatGPT + Claude + Gemini + Perplexity + AIO + AI Mode +
  Copilot simultaneously, so any "AI engines do X" claim should be
  checked against engine-coverage of its evidence source.

- **`scripts/check-live-apex.py`** module docstring updated to
  reflect 12 phases (A-J default; K + L opt-in).

- **`templates/.launch-readiness.yml.example`** gains `multi_ua_probe`
  opt-in configuration block.

- **`SKILL.md`** version bumped 1.5.0 → 1.5.1.

- **`README.md`** Status line updated.

### Phase A interaction (v1.5.0 + v1.5.1 together)

State-file substrate from v1.5.0 now has 5 new finding-types to track
across passes:

- `2.4.schema_text_parity` (existing, finding text strengthened)
- `7.5.substantive_delta` (existing, finding text strengthened)
- `9.10.front_loading` (**new**)
- `11.L.ai_bot_blocked` / `11.L.ai_bot_shrunk` / `11.L.multi_ua_clean` (**new**)

Cross-pass behavior in self-analyze: consumers will see operator-action
rate on these new findings on subsequent passes. For example, if a
consumer fixes their figcaption density (drops from `14.figcaption_sparse`
WARN to `14.figcaption_dense` PASS) AND simultaneously front-loads their
content (drops from `9.10.front_loading` WARN to PASS), the next pass
will surface both as "Resolved" in the operator-action section. This is
the measurement layer ADR 0002 ratified.

### Verification provenance (audit trail)

v1.5.1 candidates traveled through the full ADR 0001 two-reflex
discipline:

- **Discovery:** 7 parallel subagents across 8 corpora (academic
  primary, first-party platform docs, conference talks, practitioner
  LinkedIn long-form, newsletter back-issues, practitioner subreddits,
  GitHub awesome-lists + YouTube transcripts). ~7 min wall-clock.
- **Steelman:** 4 parallel subagents finding verbatim primary evidence
  for the top 7 hypotheses. ~5 min wall-clock.
- **Verification:** 4 parallel subagents attacking each steelman finding,
  re-fetching source URLs, applying folklore patterns 1-4.

Verification killed 5 findings, demoted 12, promoted 16. Three number-
drift errors caught at steelman→verification handoff. One hypothesis
(programmatic-GEO posture check / H8) killed entirely on inverse
evidence (format-templating studies show templated content is cited
MORE not less; NationalToday case coincides with Google manual action
not templating per se).

### Migration notes for v1.5.0 consumers

No breaking changes. Existing audit-output finding semantics unchanged.
New findings (`9.10.front_loading`, `11.L.*`) appear in audit output
on first v1.5.1 run.

Check 11.L requires `multi_ua_probe: true` opt-in. When unset (default):
no new network calls; phase L is silently skipped.

Check 9.10 runs automatically when content directory + ≥60-word pieces
exist. No new config required.

## [1.5.0] — 2026-05-20

Phase A of ADR 0002 ships. The skill is no longer pure-function:
`.ieo-audit-state.yml` lives in the consumer repo at root, written by
the audit at end of each pass, read at start of the next pass, and used
to categorize how findings shifted between passes. This is the
measurement substrate that future v1.5.x candidates (the slate from
v1.4.1's deep research) need to surface their effect on consumers.

The v1.4 candidate slate (schema-text parity strengthening, cross-engine
portfolio in check 12, first-30% positional check, freshness substantive-
edit detection, multi-UA live-apex probe) does NOT ship in v1.5.0 — it
ships in v1.5.1 once Phase A has settled. Rationale: the state-file
substrate is load-bearing for measuring whether new checks actually help;
shipping checks without state means no signal for whether they helped.

### Added

- **`scripts/_state.py`** — state-file substrate module (~260 LoC stdlib).
  - `StateFinding` + `State` dataclasses capturing finding identity +
    severity + first-seen / last-seen / pass-count.
  - `load_state(repo)` — reads `.ieo-audit-state.yml` from repo root.
    Tolerant of state-version mismatch (newer state from future skill
    version → treats as absent rather than corrupting).
  - `write_state(repo, state)` — atomic write (tmp file + rename) to
    repo root.
  - `build_state_from_results(skill_version, results, prior)` — merges
    current-pass results with prior state, preserving `first_seen` and
    incrementing `pass_count` where findings persist.
  - **Stdlib-only YAML fallback.** Emitter + parser handle the
    state-file shape when PyYAML is not importable. Round-trip tested.

- **`scripts/self-analyze.py`** — self-analyze pass orchestrator (~210
  LoC stdlib). Runs after the main audit. Reads `.ieo-audit-state.yml`,
  compares current-pass findings against prior:
  - **Resolved** — was WARN/FAIL, now PASS or dropped out
  - **Regressed** — was PASS, now WARN/FAIL
  - **Persistent** — WARN/FAIL in both passes
  - **New** — WARN/FAIL in current pass, absent in prior
  - **Long-running** — persistent findings open ≥3 passes
  Appends an "Operator action since last pass" section to the audit
  report (`.launch-readiness-report.md`). Writes a fresh state file
  at end. First-pass behavior (state file absent): emits advisory
  + writes initial state file for consumer to commit.

- **`docs/decisions/0002-self-improving-skill.md`** (ratified in v1.4.2;
  Phase A operationalizes Decision 1 — audit-diff persistence as
  primary measurement signal — and Decision 2 — state in consumer
  repo, committed by operator).

### Changed

- **`scripts/audit.sh`** — registers self-analyze invocation after the
  main audit loop. Self-analyze runs unconditionally (no config gate
  yet — opt-out via removing the block; gate to be added if a real
  need surfaces). Errors degrade gracefully (self-analyze never blocks
  the audit).

- **`SKILL.md`** — version bumped to 1.5.0.

- **`README.md`** — Status line updated; mentions state file behavior.

### First-pass behavior for v1.4.x consumers upgrading to v1.5.0

When a v1.4.x consumer first runs v1.5.0:

1. Audit runs as usual; emits the usual MD + JSON reports.
2. Self-analyze runs at end. Detects no prior state file.
3. Writes `.ieo-audit-state.yml` to repo root with current findings.
4. Appends "First pass — no prior state file found" section to the
   audit report. Advises the operator to commit the state file.

Operator commits the state file. Next pass produces the full
"Operator action since last pass" section.

### Migration notes for v1.4.x consumers

No breaking changes to audit-output finding semantics. One new file at
first invocation: `.ieo-audit-state.yml` at repo root. **Soft-required
commit**; not gating but visible in audit output as advisory.

If you want to disable state tracking entirely, remove the self-analyze
invocation block from `scripts/audit.sh` (the skill is symlinked from
`~/.claude/skills/IEO-launch-audit/` so the edit is local to your install).
A proper `state_tracking: false` config gate may land in v1.5.x if a
real need surfaces; for now, the default-on behavior is what the ADR
ratified.

### Phase A budget impact

Audit-budget impact is negligible — `self-analyze.py` adds ~50-200ms
per pass for typical finding counts (10-100 findings). No new network
calls. Stdlib only. Phase A does NOT add to the "~5 minutes for checks
1-10 fast pass" budget.

State file size grows logarithmically with audit history. Expected
<10KB per audit pass after stabilization (state captures one record
per unique finding-id across audit history; PASS findings are also
retained to track resolution events).

### Known gaps in Phase A (deferred to Phase B / v1.5.x+)

- **GSC / Bing delta integration in self-analyze.** Check 12 already
  has API surfaces; pairing them with state-file persistence to track
  indexing-state delta correlated with finding-resolution is Phase B.
- **Wayback CDX substantive-edit confirmation.** Pair self-analyze's
  "resolved" findings with content-digest evidence that the underlying
  content actually changed (not just metadata).
- **Operator-action tracking via commit-message mining.** Currently
  the skill infers operator action from finding-severity delta only.
  Future work: detect commits matching fix patterns to attribute the
  action.
- **`auto-learn-report.md` cross-repo aggregation.** Phase D.

## [1.4.2] — 2026-05-20

ADR-only patch. v1.4.1's deep research pass (under the new two-reflex
discipline) closed with 5 firm + 2 conditional v1.5 candidates surviving
steelman + verification. Discovery surfaced an architectural gap orthogonal
to the candidate slate: the skill has no way to measure whether emitted
findings move outcomes, no per-repo memory, no mechanism to evolve from
real consumer experience. v1.4.2 ratifies the architecture that closes
that gap.

### Added

- **`docs/decisions/0002-self-improving-skill.md` — ADR 0002.** Ratifies
  four load-bearing decisions:
  1. **Primary measurement signal: audit-diff persistence across passes.**
     GSC/Bing deltas are companion signals reported at confidence-tier
     "medium" at best (attribution noise unresolvable). LLM citation
     tracking is too noisy to be load-bearing.
  2. **State location: consumer repo, committed, version-controlled.**
     `.ieo-audit-state.yml` at repo root. Operator commits; subsequent
     audits read. Git-log fallback when absent.
  3. **Auto-learn output: advisory-only, never auto-mutating.** Skill
     emits `auto-learn-report.md`; maintainer reviews and decides whether
     to mutate via normal PR review. Reasoning: drift toward consumer-bias
     is the failure mode of auto-mutation. Same discipline pattern as
     ADR 0001's verification-subagent reflex.
  4. **Auto-research scheduled monthly, opens PR, never auto-merges.**
     `scripts/research/auto-pass.sh` + scheduled remote agent. Runs under
     ADR 0001's two-reflex discipline. ~$50-90/month operational cost.

  **Phased rollout:**
  - **Phase A (v1.5):** state-file substrate + self-analyze pass +
    audit-report integration + git-log fallback. Substantial release.
  - **Phase B (v1.5.x or v1.6):** GSC/Bing delta integration in
    self-analyze.
  - **Phase C (v1.6):** auto-research routine + scheduled remote agent.
  - **Phase D (v1.7+):** cross-repo auto-learn (opt-in only).

### Why this lands as a patch, not a release with code

Doc-only architectural ratification. The ADR captures decisions the
maintainer has explicitly agreed to but the implementation is substantial
enough to warrant its own release (v1.5). Shipping the ADR separately as
v1.4.2 keeps the contract immutable while Phase A code lands; reviewers
of the v1.5 PR have a clear reference document.

### Why v1.5 instead of v1.4.3 for Phase A

Phase A is a load-bearing architectural shift (pure-function → lightly-
stateful) that bundles with the v1.5 candidate slate from the deep
research pass. Bundling makes the package coherent: new checks land
alongside the per-repo memory that lets future passes measure their
effect. Shipping checks without state means no signal for whether they
helped; shipping state without checks means nothing to measure.

### Migration notes for v1.4.1 consumers

No code changes; no audit-output changes; no breaking changes. The
amendment affects future architecture, not current behavior.

When v1.5 ships (with Phase A code), v1.4.x consumers will see one new
file at first invocation: `.ieo-audit-state.yml` at repo root. Soft-
required commit; not gating but visible in audit output.

## [1.4.1] — 2026-05-20

ADR-only patch. The v1.4 GEO/pGEO research pass surfaced a structural
shortcoming in ADR 0001: the verification reflex is defensive — it
catches folklore but doesn't push toward finding the strongest available
evidence for surviving candidates. The v1.4 candidate slate emerged
from a thin corpus (Google web search + vendor blogs + arXiv);
verification dutifully killed three candidates but never asked "what's
the strongest evidence FOR the survivors I haven't found yet?"

This patch amends ADR 0001 with a paired "steelman reflex" — a
generative discipline that runs alongside verification. The two compose
into a per-candidate two-pass pipeline: steelman finds verbatim
evidence; verification attacks it; only candidates that survive both
promote to the candidate slate.

### Changed

- **`docs/decisions/0001-claim-verification.md`** — new section
  "The steelman reflex (added v1.4.1)" capturing:
  - **Definition.** Opposite incentive structure to verification —
    steelman is incentivized to find evidence; verification is
    incentivized to attack it.
  - **What a steelman subagent does.** Takes a hypothesis; searches
    expanded corpora; returns **verbatim quotes with source URLs**
    (not paraphrases); tags source tier explicitly per finding;
    exhausts corpora before reporting.
  - **Expanded corpora — mandatory for major-pass steelman.** Eight
    corpora in priority order: (1) academic / methodology-disclosed
    primary research (arXiv sanity, Semantic Scholar, ACM DL, Papers
    with Code, conference proceedings); (2) first-party platform
    docs (developers.google.com, platform.claude.com, help.openai.com,
    perplexity.ai/hub, learn.microsoft.com, blogs.bing.com,
    brave.com/blog); (3) conference talk catalogs (BrightonSEO, SMX,
    Pubcon, MozCon); (4) practitioner LinkedIn long-form (Indig, King,
    Solís, Ray, Haynes, Shepard, Gabe, Critchlow, Kohn); (5) newsletter
    back-issues (SEOFOMO, Growth Memo, Indie SEO, Search Engine
    Roundtable); (6) practitioner subreddits (r/SEO, r/bigseo,
    r/TechSEO); (7) YouTube speaker-series transcripts; (8) GitHub
    awesome-lists + GEO-tooling repo discussions.
  - **Budget expectation per pass.** Major-version pass: 5-7 discovery
    subagents (60-100 tool uses each) + 3-5 steelman subagents (40-60
    tool uses each) + 3-5 verification subagents attacking each
    steelman finding. ~2-3h subagent runtime + ~30min consolidation.
    Patch-level: 1-2 of each, ~30-60min. The v1.4-style "thin pass"
    (2 discovery + 2 verification, ~30 tool uses each) is **no longer
    sufficient** for major-version candidate slates.
  - **Pipeline composition.** Steelman → verification, sequential.
    Both required for any candidate that ships.
  - **Failure mode + mandatory mitigation.** Steelman risks
    regenerating folklore (incentivized to find evidence). Mitigations:
    verbatim quotes only, source-tier tagging, verification re-fetches
    source URL to confirm quote exists and means what steelman claimed.

- **Consequences section** updated to reflect the budget shift (4-6
  subagents → 11-17 subagents per major pass) and to add the new
  failure mode (steelman without verification = folklore generator).

### Why this lands as a patch, not a release with new checks

Doc-only architectural amendment. No new checks; no audit-output
changes; no run-time behavior changes. The amendment affects how
future research passes are conducted, not how the current skill runs.

The next major release (v1.5) will be the first candidate slate produced
under the two-reflex discipline; this patch defines the discipline so
the v1.5 research pass can execute against an established contract.

### Migration notes for v1.4.0 consumers

No code changes; no audit-output changes; no breaking changes.

## [1.4.0] — 2026-05-20

The "fold in all surviving v1.4 candidates" release. A two-pass GEO/pGEO
recursive-research arc (two parallel discovery subagents + two parallel
verification subagents) surfaced six candidates; verification killed
three (NLWeb portability, Bing AI Performance API status, Claude
`web_search` source-preference). The three that survived plus four
framing-patch candidates ship in v1.4. The v1.3.2 dogfooding patch
(check 9 preamble + ADR pattern 4) — surfaced by the same research
pass — shipped as a separate hotfix; v1.4 builds on it.

### Added

- **Check 14 — multimodal markup (figcaption + alt-text + HTML tables).**
  New opt-in check. Walks sampled rendered HTML pages, restricts to
  `<main>` / `<article>` scope when present (falls back to full document
  with a caveat note), counts `<img>` tags in content scope, `<img>` tags
  with non-empty `alt=`, `<figure>`/`<figcaption>` pairs, and `<table>`
  tags (excluding nav/header/footer regions). Aggregates ratios across
  the sample and emits graded findings (`14.figcaption_dense` PASS at
  ≥70%, `14.figcaption_sparse` WARN at <30% when ≥3 imgs, similar for
  alt-text at 90%/70%, plus tables presence INFO). Gated on
  `multimodal_markup_check: true` in `.launch-readiness.yml`; emits one
  `14.skipped` INFO when unset. Stdlib only (`re` for HTML parsing, no
  PIL/BeautifulSoup/lxml). ~280 lines. Audit-budget impact: ~10-30s for
  the default 10-page sample.

  **Evidence base:**
  - [SearchVIU 2025](https://www.searchviu.com/en/schema-markup-and-ai-in-2025-what-chatgpt-claude-perplexity-gemini-really-see/)
    methodology-disclosed test: 5 LLM systems extracted only visible
    HTML at retrieval time; hidden JSON-LD / Microdata / RDFa ignored.
  - [Williams-Cook "Duck Test" Feb 2026](https://www.youtube.com/watch?v=-nTqaG3GKLk):
    fabricated address in JSON-LD only, no visible text — ChatGPT +
    Perplexity returned the fake address verbatim. LLMs scrape raw
    JSON-LD as text, not as structured data; visible HTML wins as
    load-bearing context.
  - [Aleyda Solís AI-search optimization checklist](https://www.aleydasolis.com/en/ai-search/ai-search-optimization-checklist/)
    (practitioner-tier): figcaption + HTML tables specifically called
    out as multimodal-markup recommendations.

  **Source-tier honesty (per ADR 0001):** practitioner-consensus +
  indirect-methodology alignment. The two methodology-disclosed studies
  measure the upstream principle ("visible HTML wins"), not figcaption
  / table deltas directly. WARN is the strongest severity emitted —
  never FAIL — because no LLM engine has published "we deprecate
  citation eligibility for images without figcaption" (cf. check 13,
  which DOES escalate to FAIL when `merchant_feed: true` because
  Google Merchant Center publishes a concrete demotion policy).

- **Check 11 — post-launch measurement-variance advisory (doc patch).**
  Added a framing note in the check 11 preamble: when consumers track
  LLM citations via Profound / Otterly / BrightEdge / 5W / Brave / etc.
  post-launch, single-shot measurements are unreliable because LLM
  outputs are stochastic. Recommends **n≥5 per query** with stratified
  prompt variants (persona, length, framing) and Jaccard / Rank-Biased
  Overlap / bootstrap-resampled confidence intervals over point
  estimates. Sources: [arXiv:2604.07585 "Don't Measure
  Once"](https://arxiv.org/abs/2604.07585) +
  [arXiv:2603.08924 "Quantifying Uncertainty in AI
  Visibility"](https://arxiv.org/abs/2603.08924). Methodology-side
  scaffolding; the skill doesn't measure citations itself, just flags
  the stochasticity so consumers don't misinterpret any tracking-tool's
  single-shot output.

- **Check 9 — citation-absorption framing (doc patch).** Added a
  framing note distinguishing retrieval ≠ citation ≠ answer influence.
  [arXiv:2604.25707 "From Citation Selection to Citation
  Absorption"](https://arxiv.org/abs/2604.25707) formalizes the
  distinction; AirOps 548K-page measurement found 85% of pages
  retrieved by ChatGPT are never cited; Kevin Indig measured 61.7%
  ghost-citation rate (link in citation strip without brand name in
  answer text) across 1.2M responses. Implication for consumer advice:
  optimizing for citation count is coarser than optimizing for
  absorption (content that actually shapes the LLM's answer text);
  the latter is what drives reader traffic.

- **Check 2 — Google "AI features" schema tension surface (doc patch).**
  Added a 2026-05 update note acknowledging Google's
  [AI optimization
  guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
  first-party statement: *"Structured data isn't required for generative
  AI search, and there's no special schema.org markup you need to add."*
  Schema remains load-bearing for rich-result eligibility, entity graph
  disambiguation, and non-Google engine parsing (Bing Copilot, ChatGPT
  Search, Claude Search, Perplexity). For Google AI features
  specifically, visible HTML (check 14) is the load-bearing surface.
  Cross-ref test added: schema-graph PASS + check-14 WARN → strategic
  priority for Google AI features is fixing check 14, not deepening
  the schema graph.

- **Checks 5 + 10 — cited-source concentration framing (doc patches).**
  Added cross-reference framing to checks 5 (Wikidata) and 10
  (Backlinks): Nature Communications 2025 measured citation
  concentration in LLM responses — fewer than 10 distinct URLs cover
  80% of responses per query. Entity-hub presence (check 5) and
  authoritative-domain backlinks (check 10) matter disproportionately
  because once a site enters the top-cited set for a topic, it locks
  in. The framing distinguishes the discrete hub-presence threshold
  from traditional SEO's continuous link-equity gradient.

### Changed

- **`audit.sh`** registers check 14 (`multimodal-markup` script). Default
  `--checks` block unchanged (1-10); opt in with `--checks 1-14` or
  `--checks 14`.
- **`templates/.launch-readiness.yml.example`** gains a check-14 config
  block: `multimodal_markup_check` gate + tunable thresholds
  (`multimodal_figcaption_pass`/`_warn`, `multimodal_alt_text_pass`/`_warn`,
  `multimodal_sample_size`).
- **`SKILL.md`** description bumped from 13 to 14 categories;
  multimodal markup added to the parenthetical list; post-launch
  use line extended with check 14.
- **`README.md`** Status block updated.
- **`ROADMAP.md`** gains a new `## v1.4 shipped (2026-05-20)` section
  at the top documenting the six items above. The longer-trail
  candidates section is renamed `## v1.5+ candidates` and gains two
  new "held under specific testable triggers" entries: **NLWeb /
  `schemamap` endpoint detection** (held pending portable static-file
  spec + LLM-engine-parsing confirmation) and **Bing AI Performance
  dashboard API integration** (held pending Microsoft exposing
  AI-Performance data via the Bing Webmaster API; currently UI-only).
  Plus the v1.4-deferred LLM-probe for check 9 Query Fan-Out moves
  here.

### Rejected (verification killed)

Documenting these so future research passes don't re-propose without
new evidence:

- **NLWeb `/ask` endpoint detection / `schemamap` validation.** NLWeb is
  dynamic-only (requires per-request natural-language processing) —
  rules out pure SSGs (Hugo, Eleventy, Astro static export). Yoast 27.1's
  `schemamap` is WordPress-`/wp-json/`-bound and Yoast itself calls it
  "proposed." No LLM engine has confirmed parsing either endpoint for
  citation eligibility. Held to v1.5+ pending portable-spec + engine-
  parsing-confirmation gates.
- **Bing AI Performance dashboard API extension.** Microsoft confirmed
  verbatim on learn.microsoft.com Q&A: "no API right now." UI-only;
  stdlib-Python can't scrape an authenticated SPA dashboard. Held to
  v1.5+ pending API exposure.
- **Claude `web_search` "originals over aggregators" preference.** No
  verbatim Anthropic source. The `web_search_20260209` docs only
  mention caller-supplied `allowed_domains` / `blocked_domains` —
  customer-side filtering, not Anthropic-side preference. The
  practitioner-inferred framing fails ADR 0001 pattern 4 (vendor-
  published weight percentages for closed-source ranking).
- **"pGEO" defined check.** The term is not stably defined in 2026
  discourse; closest usage is "programmatic GEO" (a content strategy,
  not an audit category). Existing duplicate-metadata / sitemap-accuracy
  / internal-link checks catch the failure modes.
- **AGENTS.md detection.** Wrong surface — AGENTS.md is for AI coding
  agents (Claude Code, Cursor, Aider), not LLM citation engines. Out
  of scope.

### Migration notes for v1.3.x consumers

No breaking changes. `audit.sh --checks 1-10` default fast-pass
behavior is unchanged. To opt into check 14:

```yaml
# .launch-readiness.yml
multimodal_markup_check: true
```

Then run `audit.sh --checks 1-14` or `audit.sh --checks 14`. Tunable
thresholds are documented in `templates/.launch-readiness.yml.example`
under the "Check 14" block.

The check-9 / check-11 / check-2 / check-5 / check-10 framing patches
are documentation-only; no audit-output changes for existing findings.
Reports will show the corrected framing on the next run when consumers
read the check docs alongside their report.

### Known doc drift (not in v1.4 scope)

`SKILL.md` § "What it covers" still lists "Eleven audit categories"
with bullets 1-11; checks 12, 13, 14 are not listed in that section
(the description block above it lists all 14 correctly). Not fixed in
v1.4 because the drift predates v1.4 and the fix is larger than the
v1.4 surface. Will reconcile in a follow-up doc-only pass.

## [1.3.2] — 2026-05-20

Dogfooding patch. v1.3 shipped ADR 0001 ("claim-verification reflex") to
catch folklore-emission patterns in third-party SEO discourse — and then
shipped a check that violates the ADR. A recursive 2026-GEO-pattern
research pass (run during v1.4 candidate evaluation) caught the self-
violation: `checks/09-content-tactics.md` preamble quoted Aggarwal et al.
(KDD 2024) as point estimates (`+30%`, `+35%`, `+37%`) — bound-smoothed
from the paper's published 30-40% / 15-30% ranges, with the per-rank-
bucket caveat omitted (rank-1 deltas in the paper are actually
*negative* for these tactics; rank-5 deltas exceed +100%, paper Table 2).
Two additional numbers (`Q&A blocks +40%` and `First-party data +30-40%`,
attributed to Profound) had no traceable per-tactic methodology. A fourth
(`Semantic completeness 340% inclusion rate vs shallow pages`) had no
source citation at all (verified by grep).

This patch fixes the self-violation and adds ADR 0001 pattern 4
("vendor-published weight percentages for closed-source ranking
algorithms"), verified-by-absence across Anthropic / OpenAI / Perplexity /
Google's canonical docs (none publishes source-selection weights).

### Fixed

- **`checks/09-content-tactics.md` preamble** rewritten to quote
  Aggarwal et al.'s actual published ranges (**30-40%** on Position-
  Adjusted Word Count, **15-30%** on Subjective Impression — paper §4)
  and to surface the rank-bucket caveat from Table 2: Cite Sources is
  **−30.3% at rank-1** → **+115.1% at rank-5**; Quotation Addition
  **−22.9% → +99.7%**; Statistics Addition **−20.6% → +97.9%**. **GEO
  tactics disproportionately help low-ranked sources and may hurt
  already-rank-1 sources** — a strategic implication the prior framing
  omitted. Methodology context added (10K-query GEO-bench, 5 random
  seeds, Perplexity.ai real-world validation, GPT-3.5 G-Eval for
  Subjective Impression).
- **Removed unverified Profound per-tactic percentages** (`Q&A blocks
  +40%`, `First-party data +30-40%`). Profound publishes citation-
  pattern observations and aggregate readouts; their published material
  does not include per-tactic delta methodology. The tactics themselves
  remain in the check's recommendation list as practitioner-consensus
  advice (sections 9.5, 9.6); only the false-precision percentages are
  dropped from the preamble.
- **Removed `Semantic completeness ≥8.5/10: 340% inclusion rate vs
  shallow pages`** — no source citation in the file (verified by grep
  across `checks/`, `references/`, `scripts/`).
- **Tightened the "cited sources" attribution** at the preamble foot:
  methodology-disclosed sources (Aggarwal et al.) separated from
  pattern-observation sources (Profound, ALM Corp, SEJ, SEL) so future
  edits don't conflate the two tiers.

### Added

- **ADR 0001 pattern 4 — "Vendor-published weight percentages for
  closed-source ranking algorithms."** Verified-by-absence (May 2026):
  direct fetches of [Anthropic's `web_search` tool
  docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
  [OpenAI's ChatGPT Search
  help](https://help.openai.com/en/articles/9237897-chatgpt-search),
  [Perplexity's publisher program](https://www.perplexity.ai/hub),
  and [Google's AI optimization
  guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
  confirm that none of the four publishes source-selection weights. Any
  "Claude weights entity 30%" / "ChatGPT weights authority 40%" /
  "Perplexity weighs recency 20%" claims circulating in vendor blogs are
  fabricated. The engines explicitly do not publish this information —
  that is policy, not oversight, and unlikely to change.
- **ADR 0001 context item 4** documents this v1.3.2 dogfooding pass as
  the originating evidence for pattern 4. The ADR's status line is
  amended (not superseded) — pattern 4 was identified via the same
  verification-subagent dispatch the ADR ratifies.

### Migration notes for v1.3.1 consumers

No breaking changes. No invocation changes. Existing audit outputs are
unchanged in finding-count / finding-shape; only the *preamble framing*
of check 09 is rewritten. Consumer-side audit reports will show the
corrected narrative on the next run.

If a consumer's editorial team has been citing the prior check-9
percentages in their own briefs / dashboards, those briefs should be
updated. The corrected framing is "30-40% range, but rank-1 deltas can
be negative" — not "+30 / +35 / +37%."

## [1.3.1] — 2026-05-20

Rule-correctness patch. The offline curated-rules catalog
(`references/schema-org-rules.json`) had `mainEntity` typed as `object`,
which fires `2.9.value_types` FAIL against any well-formed `FAQPage`
(canonical shape: array of `Question` objects). Relaxed to
`object-or-array`. Surfaced by a consumer audit run against an FAQ-emitting
site (rule 2.9 firing FAIL on 5 nodes that were structurally correct).

### Fixed

- **`references/schema-org-rules.json` — `mainEntity` value-type
  loosened from `"object"` to `"object-or-array"`.** Google's documented
  `FAQPage` JSON-LD example uses `mainEntity: [Question, Question, ...]`
  (see [developers.google.com/search/docs/appearance/structured-data/faqpage](https://developers.google.com/search/docs/appearance/structured-data/faqpage)).
  Schema.org itself does not constrain `mainEntity` cardinality — the
  range is just `Thing` ([schema.org/mainEntity](https://schema.org/mainEntity))
  — so the prior `object`-only rule was stricter than the spec. Rules file
  `version` field bumped `2026-05d` → `2026-05e` to make the catalog drift
  detectable.

### Tradeoff (intentional, low-risk)

The relaxation is global — `ProfilePage.mainEntity` (canonically a single
`Person`) and `CollectionPage.mainEntity` (canonically a single `ItemList`)
will no longer trip `2.9.value_types` if accidentally emitted as arrays.
Accepted because:

- The dedicated CollectionPage shape check (`scripts/check-schema.py:907-908`)
  independently enforces `dict + @type == ItemList`, so CollectionPage's
  strict-singular convention is still validated — just by the dedicated rule
  rather than the generic value-type rule.
- `type_required_props` still flags `mainEntity` *absence* on ProfilePage /
  CollectionPage. Only the value-shape changes.
- The strictly-correct alternative is per-parent-type overrides (`FAQPage`
  → array-of-`Question`; `ProfilePage` → single `Person`;
  `CollectionPage` → single `ItemList`). More code + more rules to maintain.
  Deferred to a future patch only if a real consumer regression surfaces.

### Migration notes for v1.3.0 consumers

No breaking changes. No invocation changes. Consumers re-running the audit
should see `2.9.value_types` PASS on previously-failing `FAQPage` nodes.
Other `mainEntity` users (ProfilePage, CollectionPage, WebPage, ItemPage)
unaffected when emitting the canonical single-object shape.

## [1.3.0] — 2026-05-15

The Phase-2-verified candidate slate ships. Seven new findings across six existing checks + one new check (check 13). Driven by the recursive-research arc that ran across v1.2.1: five discovery + six verification subagents validated each candidate against primary sources before promotion. Local-validated against `thomasjankowski-site`; the schema-parity finding surfaces a real WARN (71% of JSON-LD string fields not in DOM, 22 unique missing strings).

### Added

- **Check 13 — Imagery provenance (C2PA / IPTC `digitalSourceType`).** New opt-in check. Walks sampled rendered HTML pages, extracts `og:image` / `twitter:image` targets, resolves to local filesystem path (falls back to remote Range-fetch), scans XMP for IPTC `digitalSourceType` (`trainedAlgorithmicMedia` / `compositeSynthetic`) + C2PA manifest markers. Gated on `ai_generated_imagery: true` — skips silently when unset. WARN when AI imagery declared but provenance absent; escalates to FAIL when `merchant_feed: true` (Google Merchant Center demotes non-compliant AI product images). **Scope distinction from declined EU AI Act scope:** this is indexing-side enforcement (Google Merchant Center), not regulatory compliance. Stdlib-only XMP parsing; no PIL / ExifRead. ~250 lines.

- **Check 2.4.about_mentions_usage** (advisory). Counts `about` and `mentions` arrays on sampled articles. Flags pages with `mentions` but no `about` (entity-linking inverted); flags `about` array > 3 entries (over-broad); flags zero `about` site-wide (entity-linking signal missing). INFO-tier — no Google primary confirms ranking weight; schema.org definition + practitioner consensus only. ~70 lines.

- **Check 2.4.graph_consolidation** (advisory). Counts inline JSON-LD blocks per rendered page. Flags fragmented sites (>1 block per page) or sites without `@graph` wrappers as INFO. NLWeb-readiness signal (Microsoft NLWeb + Yoast 27.1 March 2026 aggregator); not yet a measured citation penalty. ~50 lines.

- **Check 2.4.schema_text_parity.** Walks JSON-LD string fields (`name`, `headline`, `description`, `alternativeHeadline`, `abstract`, `articleBody`, `creditText`, `caption`) and verifies the first 5 words appear in the rendered DOM. Backstopped by Google's [General Structured Data Guidelines](https://developers.google.com/search/docs/appearance/structured-data/sd-policies): *"Don't mark up content that is not visible to readers of the page."* Verified empirically by SearchVIU 2025 + Williams-Cook "Duck Test" early 2026 — LLM fetchers tokenize JSON-LD as raw text; schema-only content is functionally invisible. Severity scales WARN/INFO with miss percentage. Caught a real WARN on the canonical consumer (71% miss rate).

- **Check 5.5.entity_hub_coverage.** Extends check 5 (Wikidata) — enumerates Person.sameAs coverage against a 13-hub top-tier list (Wikipedia, Wikidata, LinkedIn, YouTube channel, GitHub, Crunchbase, ORCID, Reddit, Google Business Profile, Mastodon, Bluesky, X/Twitter, LinkedIn company). Default list anchored on 5W "AI Platform Citation Source Index 2026" + SE Ranking 1.3M-citation study showing Google AI-Mode self-cites google.com properties (GBP/YouTube) 17.42%. INFO-tier; configurable via `entity_hubs:` list override.

- **Check 7.4.engine_freshness** + **7.5.substantive_delta.** Per-engine freshness bands (Perplexity 30d, ChatGPT 90d, AIO 180d; Claude omitted — insufficient independent measurement) keyed on `target_engines:` config. Reports % of sitemap URLs under each engine's band as INFO. The 13-week global cliff candidate (Amsive folklore) is replaced by per-engine bands. Substantive-delta detection (opt-in via `freshness_delta_check: true`) uses Wayback CDX content-digest API + `difflib.SequenceMatcher` text-diff on mismatch — <10% delta = cosmetic-only dateModified flip. WARN per Mueller on record + December 2025 core update enforcement. Stdlib-only; ~10s-2min audit-budget impact when enabled.

- **Check 9.fanout.heuristic** + **9.fanout.advisory.** Structural retrievability proxy for Query Fan-Out: ≥3 question-shaped H2/H3 headings, ≥3 distinct named entities in headings, FAQPage/HowTo schema OR `<dl>`/`<details>` answer blocks, avg paragraph length 40-150 words (chunkable LLM-friendly band). Honest about the limitation: cannot enumerate actual fan-out queries without an LLM probe. The advisory points consumers at Locomotive Agency / QueryBurst / Otterly for true fan-out audits. Optional opt-in LLM probe deferred to v1.4 (mirrors v0.5 curation-scaffold pattern).

- **`docs/decisions/0001-claim-verification.md` ADR.** Documents the three folklore-emission patterns surfaced across the two research passes (precise-percentage-no-methodology; submit-to-product-that-doesn't-exist; single-source-boundaries-smoothed-to-precision) and ratifies the verification-subagent reflex as the standing pattern for new check candidates.

### Changed

- **`audit.sh`** registers check 13. Default `--checks` block unchanged (1-10); opt in with `--checks 1-13` or `--checks 13`.

- **`scripts/check-schema.py`** 2.8 per-page HTML sampling loop refactored: now finds ALL inline JSON-LD blocks (was: first only) and parses each. Per-page malformed semantics improved from "first-block-malformed" to "any-block-malformed" — more correct.

- **`templates/.launch-readiness.yml.example`** gains six new config sections: check 13 (`ai_generated_imagery`, `merchant_feed`), check 7 (`target_engines`, `freshness_delta_check`, `freshness_delta_sample_size`), check 5 (`entity_hubs:` list override), check 2 (`news_publisher_us_english`).

- **`SKILL.md` description + check count** bumped from 12 to 13 categories.

- **`README.md`** Status block + capability table updated for 13 checks.

- **`ROADMAP.md`** § "v1.3 candidates" cleared (all shipped); the longer-trail v1.3+ section (GSC live-API, CrUX longer-trend) is the next holding area. The v1.4 candidate registry expands implicitly with the deferred LLM-probe for check 9.

### Local-validation results (against `thomasjankowski-site`)

Smoke-tested against TJ's live build artifacts. Real-signal results:

- **`2.4.schema_text_parity`: WARN** — 71% of JSON-LD string fields (66/93 across 22 unique strings) not present in rendered DOM. Specifically Person `description` and `hasOccupation.name` are schema-only. Confirms the v1.3 candidate is the highest-value check landed this release.
- **`2.4.graph_consolidation`: INFO** — 9/10 sampled pages have >1 inline JSON-LD block. TJ emits both a consolidated `schema-graph.json` AND per-page inline JSON-LD; check catches the per-page fragmentation pattern.
- **`2.4.about_mentions_usage`: PASS** — 10/10 sampled articles have disciplined `about` (1-3 entities). TJ adopted the entity-linking pattern.
- **`5.5.entity_hub_coverage`: INFO** — 5/12 top-tier hubs present. Missing: Wikipedia, YouTube channel, Reddit, ORCID, GBP, Mastodon, Bluesky.
- **`7.4.engine_freshness`: INFO** — median content age 9 days; 100% of URLs under all per-engine bands. TJ uses `sitemap_lastmod_mode: file_mtime`, so dates cluster around build.
- **`9.fanout.heuristic`: INFO** — 0/249 pieces hit ≥3 of 4 retrievability signals. Editorial-by-design (TJ writes long-form essays, not Q&A). The advisory is the meaningful surface here, not the heuristic.
- **`13.skipped`: INFO** — `ai_generated_imagery` not set (TJ's `--TJ x AI` hero figcaption pattern is content-side, not metadata-side).

### Migration notes for v1.2.1 consumers

No breaking changes. v1.2.1 invocations work unchanged.

To opt into check 13 (imagery provenance):
```yaml
# .launch-readiness.yml
ai_generated_imagery: true
merchant_feed: true   # optional; raises severity for missing provenance
```

To opt into substantive-delta detection (check 7.5):
```yaml
freshness_delta_check: true
freshness_delta_sample_size: 5   # default
```

To customize per-engine freshness bands (check 7.4):
```yaml
target_engines: [chatgpt, perplexity, aio]   # default
```

To customize the entity-hub list (check 5.5):
```yaml
entity_hubs:
  - { name: "Wikipedia",       match: "wikipedia.org/wiki/" }
  - { name: "ResearchGate",    match: "researchgate.net/profile/" }
  # ... etc.
```

To preserve prior Speakable WARN behaviour (US-news-English publishers):
```yaml
news_publisher_us_english: true
```

### v1.4+ holding area

- Opt-in LLM probe for check 9 Query Fan-Out (mirrors v0.5 curation-scaffold pattern; driver creates batches, subagent dispatches to Claude/Gemini for fan-out generation + coverage scoring; gated behind explicit config).
- GSC live-API integration (still v1.3+; auth-complexity unresolved — RSA-SHA256 JWT signing).
- CrUX longer-trend analysis (ASCII charts; built on v1.2's CSV substrate).

## [1.2.1] — 2026-05-15

Small patch on top of v1.2. v1.2.1 is the result of a second recursive research pass: five parallel discovery subagents surveyed 2026 SEO/IEO/GEO shifts; six parallel verification subagents validated the highest-leverage candidates. **Three patterns SUPERSEDE prior framing** (llms.txt severity, FAQPage stance, Speakable default), five additive updates land alongside. Local-validated against `thomasjankowski-site` (the canonical consumer); the schema-parity finding fired on 5/5 sampled pages, confirming the v1.3 candidate will surface real signal.

### Changed (supersedes prior framing)

- **`check 3.5` (llms.txt) severity downgraded WARN → INFO.** 2026 disconfirmation: SE Ranking's ~300K-domain study (Nov 2025) found zero statistically-significant correlation between `llms.txt` presence and AI citation rate. AEO Engine's 90-day study found 0.1% of AI-bot requests target `llms.txt`. No major LLM provider (OpenAI / Anthropic / Google / Meta / Mistral) commits to reading it in production as of Q1 2026. Primary value remaining: developer-tool context (Cursor / Claude Code / Codex), and `AGENTS.md` now serves that role explicitly. The finding's prior "WARN if missing" framing implied a citation-eligibility cost that no longer holds; the audit emits INFO and notes that the signal is cheap-but-not-load-bearing.

- **`checks/02-schema-graph.md` FAQPage / HowTo dual-stance.** Google retired FAQ rich results May 2026 + removed FAQ from Rich Results Test June 2026 (HowTo deprecated earlier, 2023). But the schema types remain LOAD-BEARING for IEO/GEO — ChatGPT Search, Perplexity, AI Overviews still parse FAQPage for Q&A extraction. The check 02 doc now splits "deprecated for SERP-display" (Google's stance) from "still load-bearing for AI-engine citation" (IEO best practice). Audit does not flag emitted FAQPage as deprecated; both stances coexist explicitly.

- **`check 2.4.speakable` severity gate.** Speakable is officially **beta** at Google and only consumed by Google Assistant for US-English news. Confirmed in 2026: NOT used by AI Overviews / AI Mode for summarization. The array-vs-single-selector finding now demotes WARN → INFO outside US-news-English context. New config key `news_publisher_us_english: true` (default `false`) preserves prior WARN behaviour when consumer explicitly declares the role. The Speakable passage-length band finding (added v1.1) remains INFO regardless.

### Added

- **3 new AI-bot user-agents in check 03.** Citation-class: `Google-Agent` (user-triggered fetcher for Gemini Agent + AI Mode, added to Google's official crawler list 2026-03-20; PPC.land + SEJ documented), `Meta-ExternalFetcher` (user-prompted Meta AI fetches, complements `Meta-ExternalAgent`; ai-robots-txt project). Training-class: `cohere-training-data-crawler` (Cohere's training-class UA; ai-robots-txt project).

- **Known-undocumented-crawler INFO finding (`3.5b.undocumented_crawlers`).** Flags xAI Grok + DeepSeek as crawlers that publish no documented user-agent and cannot be UA-blocked. Cite Cloudflare on Grok stealth-crawling. Recommendation: configure WAF-tier defenses (JA4 fingerprinting, Vercel BotID, Cloudflare bot management); the audit can't reach these via robots.txt by design.

- **`_rich_result_retired_2026_01` block in `references/schema-org-rules.json`.** Documents the 7 schema types Google retired rich-result UI for in January 2026 (`Course`, `ClaimReview`, `EstimatedSalary`, `LearningVideo`, `SpecialAnnouncement`, `VehicleListing`, `PracticeProblem`). Types remain VALID schema.org vocabulary — still parsed for entity understanding + AI engine extraction. Audit treats detection as INFO advisory, not WARN. Schema.org rules version stamp bumped 2026-05c → 2026-05d; `schema_org_version` bumped 27.0 → 30.0 to reflect the March 2026 schema.org release.

- **`_faqpage_howto_2026_05` block in `references/schema-org-rules.json`.** Documents the SERP-display deprecation vs IEO-extraction-value split. Cited from `checks/02-schema-graph.md` § 2.4.faqpage_howto_framing.

- **`_deprecated_types` block** documents `GraphicNovel` deprecation (schema.org v29.4, Dec 2025) → `SequentialArt`.

- **LoAF (Long Animation Frames) recommendation** in `_emit_crux_finding` when INP is failing. web-vitals v4 + LoAF (Chrome 123+, production 2026) report the long-task chain causing the slow INP interaction — diagnosis path beyond raw INP measurement. Notes text only; no new finding or check.

- **`README.md` § "What this skill is NOT" — AGENTS.md disambiguation.** Clarifies that `AGENTS.md` (Linux Foundation Agentic AI Foundation, 60k+ open-source projects as of 2025-2026) is a repo-context file for coding agents (Cursor, Claude Code, Codex, Gemini CLI, Devin), NOT a crawler-policy file like `llms.txt`. The two operate at different protocol layers with different audiences. Skill does not audit `AGENTS.md` presence.

### Local-validation results (against `thomasjankowski-site` canonical consumer)

Validated four v1.3 candidates against TJ's live build artifacts:

- **Schema↔visible-text parity:** **5/5 sampled pages have JSON-LD strings absent from rendered DOM.** Specifically Person `description` "Operator across AI, travel, and healthcare. Always a builder" + `hasOccupation.name` "Operator / Builder" appear in schema but not in any page's visible text. This is exactly the failure mode the v1.3 check would catch. **Promote candidate.**
- **Entity-hub `sameAs` coverage:** TJ's Person `sameAs` carries 5/10 top-tier hubs (Wikidata, LinkedIn, GitHub, Crunchbase, X/Twitter). Missing: Wikipedia, YouTube, Reddit, ORCID, Mastodon. INFO-level finding would surface; operator decides priority. **Promote candidate as INFO check.**
- **@graph consolidation:** TJ already consolidates (742 nodes, 742 distinct `@id`s, 2148 internal cross-references). Check would PASS on TJ. False-positive risk for fragmented sites: low. **Promote as INFO.**
- **Median content age:** TJ median 9 days, p75 9 days, 100% under per-engine bands. TJ is a non-stress-test for the cliff check (uses `sitemap_lastmod_mode: file_mtime`, so dates cluster around build). The substantive-delta detection (Wayback CDX + text-diff, Phase-2-verified) is the more valuable companion finding for this consumer profile. **Promote with Wayback-CDX path as primary mechanism.**

### v1.3 ROADMAP (Phase-2-verified slate)

Seven candidates promoted from Phase-2 verification (see ROADMAP.md for detail):

1. Schema↔visible-text parity (PASS; Google policy backstop).
2. @graph consolidation INFO (NUANCED; advisory-tier).
3. `about` vs `mentions` usage INFO (NUANCED; advisory-tier).
4. Per-engine freshness bands + substantive-delta detection (PASS, Mueller-on-record).
5. Entity-hub `sameAs` coverage probe (covers top-15 concentration + Google self-citation).
6. Query Fan-Out heuristic proxy + INFO advisory (NUANCED; structural retrievability check).
7. C2PA / IPTC `digitalSourceType` for AI imagery, gated on operator declaration (SHIP NARROW).

### Declined / dropped (after verification)

- "Information Gain operationalized at scale March 2026 / +22% lift" — press-release-tier folklore; no Google first-party. Existing check 9 (Princeton GEO tactics) is the de-facto IG proxy.
- Unlinked brand mentions citation lift — marketing-blog tier, off-site only.
- 40% sentiment suppression — single vendor source with incentive; no honest source-side proxy.
- 13-week global recency cliff (specifically) — traces to one source (Amsive); per-engine bands more defensible.

### Process learning

Across two research passes now (`seo_learnings.md` verification + this one), three folklore-emission patterns surfaced repeatedly. Cataloging here so future passes catch them earlier:

1. **Press-release-tier "X% lift in core update Y"** — Information Gain "+22%", "134-167 word Princeton thesis", "+34% structured-attribution-verb lift". Pattern: a specific percentage with no disclosed methodology, syndicated across vendor blogs that each cite each other.
2. **"Submit to X" products that don't exist** — Brave Webmaster Tools (debunked v1.1).
3. **Single-source "boundaries" smoothed into precise numbers** — 13-week cliff (Amsive only), 134-167 word range (Lattice Ocean only). Precise numbers in marketing posts that don't agree across sources.

The verification-subagent reflex catches these. Worth a `docs/decisions/0001-claim-verification.md` ADR in v1.3.

### Migration notes for v1.2.0 consumers

No breaking changes. v1.2 invocations work unchanged.

To preserve prior Speakable WARN behaviour (US-news-English publishers):
```yaml
# .launch-readiness.yml
news_publisher_us_english: true
```

Sources for the changed-framing items:
- llms.txt disconfirmation: [SE Ranking 300K-domain analysis](https://seranking.com/blog/llms-txt/); [AEO Engine zero-usage study](https://aeoengine.ai/blog/llms-txt-zero-usage-ai-bots-ignore); [aeo.press State of llms.txt 2026](https://www.aeo.press/ai/the-state-of-llms-txt-in-2026)
- FAQPage / HowTo: [Google FAQPage developer docs](https://developers.google.com/search/docs/appearance/structured-data/faqpage); [SearchEngineLand on FAQ rich-results retirement](https://searchengineland.com/google-to-no-longer-support-faq-rich-results-476957)
- Speakable: [Google Speakable docs](https://developers.google.com/search/docs/appearance/structured-data/speakable) (beta + US English news only)
- Google-Agent UA: [PPC.land coverage](https://ppc.land/google-agent-joins-the-crawler-list-as-ai-browsing-gets-an-official-identity/); [SEJ](https://www.searchenginejournal.com/why-new-google-agent-may-be-a-pivot-related-to-openclaw-trend/570764/)
- Grok stealth-crawling: [Cloudflare blog on Perplexity + general stealth pattern](https://blog.cloudflare.com/perplexity-is-using-stealth-undeclared-crawlers-to-evade-website-no-crawl-directives/)
- LoAF: [Chrome for Developers — LoAF has shipped](https://developer.chrome.com/blog/loaf-has-shipped)

## [1.2.0] — 2026-05-15

Monitoring + indexing-state release. v1.0 + v1.1 established the audit
surface; v1.2 adds the post-launch layer that catches drift over time
(CrUX trend), per-piece content-vs-schema consistency (wordCount), the
search-engine indexing-state cross-verification (Bing API + GSC
snapshot), and an opinionated recipe for /loop / /schedule / cron /
GitHub Actions wrapping. The skill now has three complementary layers:
checks 1-10 source-side, check 11 live-apex behavior, check 12 indexing
state.

### Added

- **Check 12 — Search Console cross-verification** (`scripts/check-search-console.py` + `checks/12-search-console.md`). New opt-in check answering the question SUBMITTED ≠ INDEXED. Two paths, either or both:

  - **Bing Webmaster API**: opt-in via `bing_webmaster_api_key` (env / inline / SOPS) + `bing_webmaster_site_url` (or fallback to `canonical_origin`). The audit fetches `GetUrlSubmissionQuota` + `GetCrawlStats` and emits:
    - `12.bing.quota` PASS — key + site verification both valid.
    - `12.bing.crawl_errors` WARN/PASS — 7d aggregate crawl-error count.
    - `12.bing.blocked_pages` INFO — robots.txt-blocked count (advisory).
    - `12.bing.indexed_vs_sitemap` WARN/INFO/PASS — `indexed / sitemap_url_count` ratio (WARN <50%, INFO 50-80%, PASS ≥80%).
    - `12.bing.api_error` / `12.bing.no_site` MV — config / API failures.

    Site must be verified in Bing Webmaster Tools UI before API calls succeed. Free tier handles 1-2 GETs per audit run comfortably.

  - **GSC snapshot reader**: opt-in via `gsc_index_snapshot_path` pointing at a JSON file the operator exports from GSC's Index Coverage report. Expected schema: `{exported_at, indexed_urls[], excluded_urls[{url, reason}]}`. Emits:
    - `12.gsc.indexed_vs_sitemap` WARN/INFO/PASS — same ratio thresholds as Bing.
    - `12.gsc.excluded_reasons` INFO — top-5 GSC exclusion reasons + counts; surfaces the "Crawled - currently not indexed" / "Soft 404" / etc. taxonomy.
    - `12.gsc.snapshot_missing` / `12.gsc.snapshot_malformed` / `12.gsc.snapshot_shape` MV — file / shape failures.

    Why no OAuth: GSC requires RSA-SHA256 JWT (service account) or 3-legged OAuth; both need non-stdlib crypto. The snapshot path keeps the skill stdlib-only at the cost of operator-side staleness (re-export periodically). Live GSC API integration is on v1.3+ ROADMAP.

  - When neither path configured, emits a single `12.skipped` INFO and runs in <1s. Opt-in like check 11; default `--checks` block is still 1-10, pass `--checks 1-12` or `--checks 12` explicitly.

- **Per-piece wordCount frontmatter validation (check 2.4.word_count_drift)**. Extends the v0.4 per-page HTML sampling: for each sampled article, the audit now resolves the Article node's declared `wordCount`, extracts the rendered body word count from `<article>` / `<main>` / `<p>` fallback (stripping `<script>` / `<style>` / `<nav>` / `<aside>` / `<header>` / `<footer>` / `<figure>` first), and compares. Drift >10% emits a WARN with the declared / actual / percentage. Pages with `<100` rendered words are skipped (noise floor). Catches the silent drift class external auditors can't see (they only have the rendered HTML, internally consistent against itself but divergent from the schema-graph claim).

- **`scripts/crux-trend.py`**. New skill-side helper. Reads `.launch-readiness-report.json`, extracts the `4.crux.<scope>_<metric>` finding family (p75 + category for page / origin × LCP / CLS / INP), appends one row per audit run to `.launch-readiness-crux-trend.csv` at the consumer repo root. Supports `--summary` (always print direction summary) / `--summary-only` (skip the append, just print). Direction arrows: `↘` p75 dropped ≥5% (improving), `↗` rose ≥5% (regressing), `→` within ±5% noise. Category changes across FAST/AVERAGE/SLOW thresholds flagged as `(improve)` / `(regress)`. Stdlib-only.

- **`templates/scheduled-audit.md`**. Opinionated recipe for post-launch recurring audits. Documents four wrapper patterns: `/loop`, `/schedule`, system crontab, GitHub Actions. Covers cadence-by-use-case (weekly default; daily for newly-launched or daily-publish sites; monthly for established), what scheduled audits catch (external link rot, CDN trailing-slash drift, sitemap/link-graph drift, CrUX regression, etc.), what they don't catch (content-quality regression, voice drift), and a "stability before scheduling" pre-flight checklist. Template-only; skill ships no cron wiring (consumer-side infrastructure).

### Changed

- **`audit.sh`** registers check 12 alongside the existing 11. Default `--checks` block unchanged (still 1-10); check 12 is opt-in like check 11.

- **`templates/.launch-readiness.yml.example`** gains a new "Check 12" section block: `bing_webmaster_api_key` / `bing_webmaster_secret_path` / `bing_webmaster_site_url` / `gsc_index_snapshot_path`.

- **`SKILL.md` description + check count** bumped from 11 to 12 categories.

- **`README.md`** Status block + capability table updated for 12 checks. The pre-launch / post-launch framing now reads as "three complementary layers" rather than "pre-flip + post-flip pair."

- **`ROADMAP.md`** § "v1.2 candidates" cleared (all shipped); GSC live-API integration moved to v1.3+ holding area with the auth-complexity caveat documented.

### Audit-state shift (consumer-repo `thomasjankowski-site` example, post-v1.2)

No fresh consumer-side audit run in this release notes block — v1.2 ships infrastructure that's silent until configured. Expected behavior on the canonical consumer:

- 2.4.word_count_drift fires once per audit run, with PASS/WARN depending on whether the schema emitter computes `wordCount` from compiled MDX output (matching rendered body) or from raw markdown source (typically inflates the count by 5-15%).
- crux-trend.py starts collecting rows on the next audit run; first useful direction summary appears after the second run.
- Check 12 stays silent (no `bing_webmaster_api_key` configured on the canonical consumer pre-Bing-verification).

### Migration notes for v1.1 consumers

No breaking changes. v1.1 invocations work unchanged.

To opt into check 12 (Bing path):
1. Verify your site in Bing Webmaster Tools UI (DNS TXT / meta tag / XML).
2. Settings → API Access → Generate key.
3. Drop the key in env `BING_WEBMASTER_API_KEY` OR `.launch-readiness.yml` (`bing_webmaster_api_key: ...`) OR SOPS (`bing_webmaster_secret_path`).
4. Run with `--checks 1-12` (or `--checks 12` alone).

To opt into check 12 (GSC snapshot path):
1. Export GSC Index Coverage report (Indexing → Pages → Export → JSON).
2. Save to a stable path in the repo or build-output dir.
3. Set `gsc_index_snapshot_path: <relative-path>` in `.launch-readiness.yml`.
4. Re-export periodically (audit reports `exported_at` so freshness is visible).
5. Run with `--checks 1-12`.

To start the CrUX trend CSV:
```bash
bash audit.sh --checks 1-12 --report-only
python3 .claude/skills/IEO-launch-audit/scripts/crux-trend.py
```

The first run creates the CSV with one row; the second and subsequent runs append + emit a direction summary.

### Deferred to v1.3+

- **GSC live-API integration** (service-account JWT or 3-legged OAuth). Auth complexity is the open question — RSA-SHA256 signing needs `cryptography` (non-stdlib) or shelling out to `openssl`. The v1.2 snapshot-reader path is the workaround. v1.3 will pick a path explicitly.

## [1.1.0] — 2026-05-15

Post-v1.0 verification pass: a `seo_learnings.md` artifact carried over from the parent repo's extraction was put through a four-subagent verification sweep. Three claims survived with revisions and are shipped here; two fabricated/misattributed claims were declined (EU AI Act Article 50 disclosure check declined entirely as out-of-scope regulatory-compliance auditing, recorded in ROADMAP.md). The release also folds in the two leftover ROADMAP-side v1.1 candidates (CiTO @context optionality, narrow Article subtypes, `audit-diff --verbose-pass` passthrough). No breaking changes; all additions are opt-in or default-on with the same severity ceiling as prior advisory checks.

### Added

- **Brave Search indexability probe (check 11 phase K).** Opt-in single-call probe to `api.search.brave.com/res/v1/web/search` for a brand-entity query (default: bare apex host; configurable via `brave_probe_query`). Findings:
  - `11.K.brave_probe` PASS — apex appeared in top-10 (reports the rank).
  - INFO — apex absent (host-only match recognized separately).
  - MV — API unreachable / rate-limited / non-JSON.
  - INFO — phase skipped (no `brave_api_key` configured).

  Anthropic's Claude.ai web search routes through Brave Search (Anthropic subprocessor list, March 2025; Profound May 2025 measurement: 86.7% citation-URL overlap, p<0.0001). Brave visibility is the practical Claude-citation eligibility lever. **The skill explicitly does NOT recommend "submitting to Brave Webmaster Tools" — that product does not exist** (confirmed by Brave staff in community threads); Brave indexes via the Web Discovery Project (opt-in browser-side telemetry). Findings are advisory only (PASS/INFO/MV); never FAIL — search-engine visibility is emergent and noisy. Free-tier quota at api.search.brave.com is 1 req/sec, 2k req/month; the audit issues exactly one request per run. Config: `brave_api_key` (inline), `brave_secret_path` (SOPS-encrypted with `BRAVE_API_KEY`), or env `BRAVE_API_KEY`.

- **Exact-match anchor ratio (check 8.5, 8.6).** Two new findings extend check 8's anchor-text-quality audit:
  - `8.5.exact_match` — site-wide ratio of inline anchors whose text exactly matches their target page's title. PASS <5%, INFO 5-10%, WARN ≥10%.
  - `8.6.anchor_concentration` — per-target-URL anchor-phrase concentration. For each target with ≥10 inbound anchors (signal floor), WARN if any single anchor phrase exceeds 10% of inbound coverage.

  Mechanism documented in the 2024 Google API leak: `phraseAnchorSpamFraq` measures spammy-anchor fraction per phrase; `anchorMismatchDemotion` penalizes anchor-text-to-target-topic mismatch. Findings cite the leak as mechanism and label the cutoffs as practitioner-consensus (Ahrefs N=384k median 3.7 exact-match anchors on top-ranking pages; Sterling Sky August 2025 spam-update case study), not as Google-stated numbers.

- **Speakable passage-length sanity check (check 2.4.speakable_passage_length).** When per-page JSON-LD sampling resolves a Speakable `cssSelector` to a DOM node, the audit counts the passage's words and flags resolutions outside the 100-300 word band as INFO. Empirical basis: xSeek 1M-query AI Overviews dataset (Zyppy/Rampton 2024) — 62% of AIO outputs in 100-300 words; modal band 150-200 at 20.3%. Frame as observability (single-source empirical), not gating. Stdlib selector grammar supports `[attr]`, `[attr="value"]`, `#id`, `.class`, `tagname`; compound selectors fall through to MV.

- **CiTO typed-citation coverage (check 2.4.cito_coverage, v0.7 + v1.1).** New finding audits the fraction of `citation[]` entries that carry a CiTO-style typed-relation marker (`[groundedBy]` / `[extendedBy]` / `[substantiatedBy]` / `[contradictedBy]` / `[discussedIn]`) in their `description` field. PASS ≥80%, WARN <80%. New config key `cito_enabled` (default `true`) gates the check; consumers who prefer vanilla schema.org citation arrays without typed-relation richness set `cito_enabled: false` to suppress.

- **Narrow Article subtypes in offline rules (check 2.9).** `references/schema-org-rules.json` expanded from 6 covered Article subtypes (Article, NewsArticle, BlogPosting, ScholarlyArticle, TechArticle, Report) to **15** — adds `AdvertiserContentArticle`, `OpinionNewsArticle`, `SatiricalArticle`, `BackgroundNewsArticle`, `AnalysisNewsArticle`, `AskPublicNewsArticle`, `ReportageNewsArticle`, `ReviewNewsArticle`, `SocialMediaPosting`, `DiscussionForumPosting`. All inherit Article's required-prop set, so the maintenance cost is a single shared rule template. Sites emitting any of these subtypes no longer fall through to the 2.10 web-validator fallback. The `ARTICLE_SUBTYPES` (check-schema.py) and `ARTICLE_TYPES` (check-live-apex.py phase B) lists are also expanded to match.

- **`--verbose-pass` passthrough on `audit.sh`.** The `audit_diff.py` script has supported `--verbose-pass` (expand collapsed PASS rows in the diff) since v1.0, but the `audit.sh` orchestrator didn't expose the flag. Mechanical wiring. Use as `bash audit.sh --diff --verbose-pass`.

### Changed

- **`audit.sh` startup version banner** sourced from `SKILL.md` frontmatter (`grep '^  version:'`). Was hardcoded `v0.4.0` — fully stale. The report-header version (`SKILL.md` line 159 of audit.sh) was already sourced from SKILL.md as of v0.9; this aligns the stdout banner with that.

- **`templates/.launch-readiness.yml.example`** gains four new documented config blocks:
  - Check 11 — title/description length thresholds (`title_length_min/max`, `description_length_min/max`) — carried-over v1.0 doc gap; the code accepted these as of v1.0 but they weren't shown in the example template.
  - Check 11 — Brave Search indexability probe (`brave_api_key`, `brave_secret_path`, `brave_probe_query`).
  - Check 02 — `cito_enabled` toggle.

- **`checks/02-schema-graph.md`** § 2.4 enumerates all 15 Article subtypes and adds two table rows for CiTO typed-citation coverage + Speakable passage-length band.

- **`checks/08-internal-link-quality.md`** adds § 8.5 (exact-match anchor ratio) + § 8.6 (per-target anchor-phrase concentration) with mechanism and threshold rationale.

- **`checks/11-live-apex.md`** adds § 11.K (Brave indexability probe) and a new row in the "What this catches vs internal" table.

### Audit-state shift (consumer-repo `thomasjankowski-site` example, post-v1.1)

No fresh consumer-side audit run in this release notes block — v1.1 was a documentation + verified-claims pass driven by the seo_learnings verification sweep, not a re-audit against a live consumer. The new findings will surface on the next consumer run:

- 8.5 / 8.6 will fire against any consumer with ≥10 inbound anchors to a target URL; sites that converged on hand-curated named-concept anchors during v0.7 typed-citation work should land cleanly in the PASS / INFO band.
- 2.4.speakable_passage_length will fire on any consumer emitting Speakable selectors; first runs surface the passage-length distribution, then operator decides whether to reshape.
- 2.4.cito_coverage will fire on any consumer emitting `citation[]`; the v0.7 typed-citation pass left thomasjankowski-site with [groundedBy]/[extendedBy]/[substantiatedBy]/[contradictedBy]/[discussedIn] markers, so this should land PASS.
- 11.K stays silent until `brave_api_key` is configured. The opt-in nature is intentional — the skill must remain useful with zero API keys.

### Declined (recorded in ROADMAP.md § Out-of-scope)

- **EU AI Act Article 50 disclosure check.** Verified PASS as a regulatory fact (enforceable 2026-08-02; Article 50.2 imposes machine-readable marking on providers, Article 50.4 imposes visible disclosure on deployers publishing AI content on matters of public interest, editorial-control exemption covers most human-edited sites). Declined as a check because compliance auditing is a different audit class from SEO/IEO/GEO; enforcement priority is providers + large platforms, not individual blogs; the check would mostly false-positive against EU-scope consumers who qualify for the editorial-control exemption.
- **134-167 word "Princeton GEO study" thesis target.** Attribution is fabricated; the Princeton paper measures content tactics, not passage length. The Speakable passage-length band (above) uses the xSeek 1M-query AIO empirical instead, framed honestly.
- **"+34% structured-attribution-verb citation lift."** Number likely conflated with an unrelated Stacker earned-media-distribution study. Princeton's `Authoritative Voice` tactic was +8%, not +34%. No check added on this basis.
- **"Submit to Brave Webmaster Tools."** Product does not exist (confirmed by Brave staff). Replaced with the Brave indexability probe (above).

### Migration notes for v1.0 consumers

No breaking changes. v1.0 invocations work unchanged.

To opt into the Brave probe:
1. Get a free-tier Brave Search API key at `api.search.brave.com` (Pro / Free / Pro AI tier; the audit's 1 req/run sits comfortably in the free tier's 2k/month quota).
2. Drop in env (`BRAVE_API_KEY=...`) OR `.launch-readiness.yml` (`brave_api_key: ...`) OR SOPS path (`brave_secret_path: secrets/brave.enc.yaml`).
3. Optionally override the default query (bare apex host) via `brave_probe_query: "Brand Name"`.

To opt out of CiTO typed-citation coverage:
```yaml
# .launch-readiness.yml
cito_enabled: false
```

To extract the `--verbose-pass` diff:
```bash
bash audit.sh --diff --verbose-pass
```

## [1.0.0] — 2026-05-15

**Production-ready.** v0.7 → v1.0 was a single-session arc post-F-1 apex flip (thomasjankowski.com going live earlier the same day) that exercised the skill against a real live origin for the first time. Three releases (v0.8 → v0.9 → v1.0) each landed with a real corpus running it; every false positive caught + fixed, every coverage gap closed.

This release polishes the documentation surface, adds CrUX field-metrics parsing to check 4 (extending v0.9's PSI integration), rewrites `audit_diff.py` with cleaner output + regress/improve trend tracking, adds `find-redirect-source.py` as a 11.H follow-up helper, and adds configurable editorial-threshold keys for check 11's title/description length phases.

### Added

- **CrUX field-metrics parsing in check 4.** Extends v0.9 PSI integration. When PSI returns `loadingExperience` (page-level) or `originLoaderExperience` (origin-level), the check emits 6 graded findings (`4.crux.page_lcp/cls/inp` + `4.crux.origin_lcp/cls/inp`) + a `4.crux.summary` INFO with the full distribution + percentile data. Uses CrUX's FAST/AVERAGE/SLOW category directly (PASS/WARN/FAIL) rather than re-thresholding p75 percentiles; trusts Google's bucketing to track web.dev/vitals thresholds without drift. When neither scope has data (new site; <28 days of traffic), consolidates to a single `4.crux.no_data` INFO. Optional kill-switch: `pagespeed_include_crux: false` (rarely useful; CrUX rides in the existing PSI response at zero extra API cost).

- **`scripts/find-redirect-source.py`.** New skill-side helper. Reads `.launch-readiness-report.json`, extracts the 11.H redirect-chain pairs from each finding's `notes`, greps the consumer repo for the non-canonical href shapes, and reports grouped by file with line numbers. Stdlib-only. Default file-types: tsx/jsx/ts/js/html/md/mdx/astro/vue/svelte/py; default excludes `node_modules`, `.git`, `dist`, build dirs. Use after check 11 surfaces redirect-chain WARNs to find the source files emitting non-canonical hrefs.

- **Editorial-threshold config keys for check 11.G.** `.launch-readiness.yml` now accepts `title_length_min` / `title_length_max` (defaults 30/65) and `description_length_min` / `description_length_max` (defaults 70/160). Consumers with editorial-intentional deviations (operator-class long-form descriptors, brand-voice short titles) can relax the ranges without losing the rest of phase G's hygiene checks.

### Changed

- **`audit_diff.py` rewritten.** Headline leads with FAIL/WARN trend (the load-bearing severities), then resolved/new/changed counts. Findings grouped BY CHECK (matching operator mental model when triaging "what changed in check N"), not by severity globally. PASS rows collapsed to one-liner per check by default; `--verbose-pass` expands them. New **Content changes** section catches when same (check, id) keeps its severity but text drifts. Severity changes flagged with `regress` / `improve` / `shift` markers; sorted worse-first. Fixed a `fmt_delta` U+2212 formatting bug from v0.9.

- **`README.md`** fully refreshed. Status block bumped 0.4.0 → 1.0.0. Eleven-category table including check 11. Per-row notes reflect v0.6 web-validator fallback, v0.7 typed citations, v0.8 Cloudflare WAF probe, v0.9 PSI+CrUX, v1.0 audit-diff polish. Added "Output" subsection documenting the audit_diff.py flow + `--verbose-pass`. Added "Not a paid-API consumer" stance — load-bearing for the no-paid-API ruling.

- **`SKILL.md`** rewritten for the v1.0 capability set. Eleven-category content list (was ten); all per-check descriptions mention v0.6-v0.9 additions where relevant. Configuration yaml block documents `cloudflare_*`, `pagespeed_*`, `indexnow_key` keys. Stale "9 checks ran" example bumped.

- **`.launch-readiness.yml.example`** reorganized into clearly-labeled sections by purpose (identity/origin, artifacts, then per-check blocks). Added v0.8 `cloudflare_zone_id` + `cloudflare_secret_path` block. Added v0.9 `pagespeed_*` block. Added v1.0 title/description length thresholds. Reframed header preamble to document the env-var/inline/SOPS resolution order once instead of repeating per-key.

- **Check 11.J finding (meta-description duplicates)** now sets `fix_safety: "manual"` explicitly + populates `fix_template` with affected-page list + per-page-type starter-copy guidance (home / about / writing-piece / pillar). Copy stays manual; the template speeds the operator to the right call sites.

### Fixed

- **`checks/01-technical-seo.md`** referenced `check-headers.sh` which doesn't exist; corrected to `check-headers.py`.

### Audit-state shift (consumer-repo `thomasjankowski-site` example, post-v1.0)

`bash audit.sh --checks 1-11`: 0 FAIL / **7 WARN** / 64 PASS / 13 INFO / 1 MV / 1 NA.

- Checks 1-10: 0 FAIL / **3 WARN** — 7.2 (lastmod editorial-date), 8.1 (single-word named entities), 8.3 (short-piece link density). All pre-existing accepted-as-current.
- Check 11: 0 FAIL / **4 WARN** — 11.G title length distribution (editorial), 11.G desc length distribution (editorial), 11.H redirect-chain residue (real F-2 trailing-slash residue; `find-redirect-source.py` now surfaces sources), 11.J meta-description duplicate on `/` + `/about` (real bug; needs unique desc on /about).

Audit-state arc across the v0.7 → v1.0 cycle:

| Version | FAIL | WARN | New checks | Key signal |
|---|---|---|---|---|
| v0.7 | 0 | 8 | — | initial baseline (post-F-2) |
| v0.8 | 0 | 6 (-2) | +1 (check 11 opt-in) | 7.3 home-URL false positive fixed; 3.4 CF WAF probe |
| v0.9 | 0 | 8 (+2 from check 11; 6.2 cleared) | — | PSI + CrUX + IndexNow hook + Schema rules + SF-parity G/H/I/J |
| v1.0 | 0 | 7 (-1) | — | 2.9 ProfilePage `name` fix; editorial-threshold config; helper script |

Each release caught more real issues + fewer false positives. v1.0 declares "production-ready": the false-positive surface is empty, every remaining WARN is real editorial signal.

### Promotion to global skill

This release is the candidate for promotion from project-scoped (`.claude/skills/`) to globally-installed (`~/.claude/skills/`) so future repos can consume directly. Migration is mechanical (copy the directory); no per-site state. The single load-bearing portability concern (`.launch-readiness.yml` in consumer repo) is documented in the template.

### Migration notes for v0.9 consumers

No breaking changes. v0.9 invocations work unchanged.

To opt into CrUX:
- No additional config; ride in the existing PSI response. Requires `pagespeed_api_key`.
- New sites: expect `4.crux.no_data` INFO until ~28 days post-launch.

To find redirect-chain source files surfaced by check 11.H:
```
python3 .claude/skills/IEO-launch-audit/scripts/find-redirect-source.py
```

To relax check 11.G thresholds for editorial-intentional deviations:
```yaml
# .launch-readiness.yml
title_length_min: 15
title_length_max: 80
description_length_min: 40
description_length_max: 220
```

## [0.9.0] — 2026-05-15

PSI / Lighthouse CWV integration, IndexNow publish-hook pattern, Schema.org rules expansion (8 new types), and Screaming-Frog-parity additions to check 11. Closes audit WARN 6.2 corpus-wide when the publish-hook lands in the consumer repo. The skill now produces real Core Web Vitals data (Lighthouse via PSI) when configured, replacing the prior offline-only check 4.

### Added

- **PSI / Lighthouse CWV integration in check 4** (`scripts/check-performance.py`). Optional via `pagespeed_api_key` in `.launch-readiness.yml` OR `pagespeed_secret_path` pointing at a SOPS-encrypted YAML with `PAGESPEED_API_KEY`. When configured, samples home + N URLs (default 3, configurable via `pagespeed_sample_urls`) and emits 5 findings: `4.psi.scores` (the 4 Lighthouse category scores), `4.psi.lcp`, `4.psi.cls`, `4.psi.tbt` (lab proxy for INP), and `4.psi.detail` (INFO with per-URL breakdown). Strategy is mobile-default; can do `desktop` or `both` via `pagespeed_strategy`. Graceful-degrades on 429 (`4.psi.rate_limited` WARN) and other API errors. Offline checks (hero attrs, viewport, preconnect hints, image-format coverage) preserved as the fallback path when no key is configured. ~30s per PSI call; default config (4 calls mobile) is ~2-3 min per audit; `both` strategies doubles.

- **IndexNow publish-hook pattern + consumer-side script** (`scripts/publish_to_indexnow.py` in consumer repo, not the skill). The skill historically WARNed on 6.2 ("No IndexNow reference in publish pipeline") when the keyfile shipped but no publish-time URL push existed. Pattern now codified: a stdlib-only `scripts/publish_to_indexnow.py` posts URL lists to `api.indexnow.org/indexnow` (multi-engine fanout to Bing, Yandex, Seznam) on every new-URL deploy. The check now scans `scripts/` + `docs/runbooks/` + `Makefile` + `.github/workflows/` for `api.indexnow.org` references to verify the consumer repo has wired the hook. Live ping for thomasjankowski-site's live-001 returned HTTP 202; check 6.2 now PASSes.

- **Schema.org rules expansion** (`references/schema-org-rules.json`). 8 new `type_required_props` entries: `Organization`, `WebPage`, `BreadcrumbList`, `ListItem` (strengthened to require `name`), `CollectionPage` (strengthened to require `name`, `url`, `mainEntity`), `ProfilePage` (strengthened similarly), `DefinedTerm` (strengthened to require `sameAs`), `Occupation`. Check 2.9 now catches required-prop misses across the expanded type set. Surfaced 1 real load-bearing finding on thomasjankowski-site corpus: `ProfilePage@https://thomasjankowski.com/about#profilepage missing ['name']` — schema-emitter authoring gap previously invisible to the audit.

- **Screaming-Frog-parity phases in check 11** (`scripts/check-live-apex.py`). 4 new phases (G/H/I/J) extend the live-apex sweep:
  - **G — Title + heading hygiene**: title tag length (WARN if < 30 or > 65 chars), title presence (FAIL if missing), H1 presence + uniqueness, meta-description length (WARN if < 70 or > 160 chars).
  - **H — Redirect-chain hygiene**: follow each sampled internal link's redirect chain; WARN if any single-hop redirect, FAIL if > 1 hop. Catches the F-2 trailing-slash drift class.
  - **I — Orphan-page detection**: sitemap URLs not linked-from-anywhere (INFO; mostly sampling artifact at default n=20), internal-link targets not in sitemap (WARN; canonical-form mismatch).
  - **J — Meta-description duplicate detection**: sample 20 pieces, flag any descriptions shared across pages.
  Surfaced 4 real WARNs on thomasjankowski-site live apex: title-length distribution (14/20 outside range; editorial call), desc-length distribution (18/20 outside range; editorial call), 3/5 sampled internal links trigger single redirects (real F-2-residue trailing-slash fix candidates), `/` and `/about` share the same meta description (real bug). No extra apex fetches added beyond bumping piece-sample 12 → 18 so 20 pages enter the cache; G + J consume the existing cache; H reuses the same 5 sampled link pieces.

- **Range syntax in `audit.sh --checks` flag**. Was comma-only (`1,2,7`); now accepts ranges (`1-11`) and mixed (`1,3-5,11`). Range expansion runs before the per-check loop. Default unchanged (1-10; check 11 stays opt-in).

### Fixed

- **Hardcoded skill version in `audit.sh` report header.** Was `0.4.0` (stale); now sourced from `SKILL.md` frontmatter so bumps stay in one place.

### Changed

- **`.launch-readiness.yml` consumer-repo config schema** gains 4 optional keys:
  - `pagespeed_api_key` / `pagespeed_secret_path` (PSI check)
  - `pagespeed_sample_urls` (default 3; URL budget control)
  - `pagespeed_strategy` (`mobile` / `desktop` / `both`; default mobile)
  All optional; consumers without PSI keys preserve the offline-only behavior.

- **`scripts/check-indexnow.py` signal-shape** (6.2): broadened from a fixed-candidate filename list to a substring scan for `api.indexnow.org` across `scripts/`, `docs/runbooks/`, `Makefile`, `.github/workflows/`. Filename-agnostic so the convention is portable.

### Audit-state shift (consumer-repo `thomasjankowski-site` example, post-v0.9)

Pre-v0.9 (v0.8 + CF probe + 11 opt-in): 0 FAIL / 4 WARN / 46 PASS on checks 1-10. Now: **0 FAIL / 4 WARN / 46 PASS on checks 1-10**, but WARN composition changed:
- 6.2 (IndexNow hook) cleared ✓
- 2.9 (Schema.org type-required) emerged from the rules expansion as a real ProfilePage authoring gap ⚠️

Check 11 (opt-in, full SF-parity): 17 PASS / 4 WARN / 0 FAIL — the 4 new WARNs are real editorial follow-up signal (title-length, desc-length, trailing-slash redirects, meta-desc duplicate on home + about).

### Migration notes for v0.8 consumers

No breaking changes. v0.8 invocations work unchanged. To opt into PSI:
1. Create a PageSpeed Insights API key at Google Cloud Console (PageSpeed Insights API → enable → create key)
2. Drop in env (`PAGESPEED_API_KEY=...`) OR `.launch-readiness.yml` (`pagespeed_api_key: ...`) OR SOPS path (`pagespeed_secret_path: secrets/pagespeed.enc.yaml`)
3. Run audit; check 4 emits CWV findings in ~2-3 min

To clear 6.2 in the consumer repo:
1. Drop `scripts/publish_to_indexnow.py` in the consumer repo (the reference implementation in thomasjankowski-site is portable; ~120 lines stdlib Python)
2. Document the publish-time invocation in the consumer's runbook
3. Re-run audit

## [0.8.0] — 2026-05-15

Post-launch hardening pass. F-1 apex flip (thomasjankowski.com going live on Cloudflare Pages 2026-05-15) + the F-2 fix-cycle exercised v0.7 against a real live origin for the first time. Three known false positives + one coverage gap surfaced; this release fixes all four and adds a new opt-in check 11 (live-apex behavior) that catches the class of issues source-side checks structurally cannot.

### Added

- **Check 11 — Live-apex behavior** (`scripts/check-live-apex.py` + `checks/11-live-apex.md`). Opt-in post-launch check; not in the default 1-10 run. Hits a configurable live apex (via `--apex URL` CLI flag, falling back to `live_probe_origin` or `canonical_origin` in `.launch-readiness.yml`) and runs six phases: sitemap discovery, sitemap-wide reachability sweep (HEAD every URL), per-page JSON-LD audit on home + about + 12 sampled pieces (parse cleanliness, type-required-shape, baseline graph presence), per-page meta audit (title / description / canonical / og:image / noindex), inline-link sampling (5 pieces, all internal hrefs resolve), security-header consistency across home + a piece + about, discovery-artifact presence (`/robots.txt`, `/llms.txt`, `/sitemap.xml`, `/image-sitemap.xml`, IndexNow keyfile). Catches the F-2 class of bugs: CDN trailing-slash 308 chains, per-page meta drift between source and rendered HTML, slug-rename orphans on inline links, host-config glob mismatches (security headers applied to subset of routes), discovery artifacts present in `dist/` but 404 at the apex due to host rewrite rules. Run via `bash audit.sh --checks 11 --report-only` or standalone `python3 check-live-apex.py --apex URL`. Stdlib-only Python; browser-shaped User-Agent (CF + other CDNs block default Python UA); portable to any repo.

- **Optional Cloudflare WAF probe for check 3.4.** When `.launch-readiness.yml` carries `cloudflare_zone_id` and a CF API token is reachable (env `CLOUDFLARE_API_TOKEN` first, then SOPS-decrypt of `cloudflare_secret_path`), check 3.4 hits the zone's `http_request_firewall_custom` ruleset and verifies a Bytespider-blocking rule exists (action=block + expression contains `bytespider`). When verified, downgrades the WARN to PASS. When configured-but-API-errors, emits a diagnostic WARN ("CF WAF probe failed"). When unconfigured, prior behavior is unchanged. The CF WAF probe is the canonical evidence-of-edge-block; robots.txt-only signal is no longer the ceiling for 3.4 PASS.

- **Article subtype handling in check 2.4 + `references/schema-org-rules.json`.** Now accepts Article + the 6 broad subtypes (NewsArticle, BlogPosting, ScholarlyArticle, TechArticle, Report) via Schema.org type-hierarchy. Required-prop rules expanded to cover the 4 added subtypes; check 2.9 (offline type-validation) recognizes them. The 2.4 finding's `current` field reports the subtype distribution (e.g., `ScholarlyArticle=141, Article=108`) so consumers can see what was emitted.

### Fixed

- **Check 7.3 (static-pages-in-sitemap) false positive on home URL.** Comparator stripped trailing slashes from sitemap `<loc>` entries but re-built the home-URL target as `<APEX>/`, producing a guaranteed miss. The home URL now matches whether the sitemap emits it as `<APEX>`, `<APEX>/`, or `/`. Caught during F-2 audit on the live thomasjankowski.com sitemap.

- **`apply_typed_citations.py` whitespace + idempotence (carried from v0.7 tail).** Confirmed idempotent on re-runs against an already-curated TSX (quote-count guard catches double-wrap). No content change; documenting the existing behavior in this release-notes block.

### Changed

- **`scripts/audit.sh`** registry expanded from 10 to 11 checks. Default `--checks` argument still runs 1-10 only; check 11 is opt-in so the network-hitting probe doesn't fire on every run. Pass `--checks 1-11` or `--checks 11` to include.

- **`.launch-readiness.yml` consumer-repo config schema** gains two optional keys: `cloudflare_zone_id` (zone UUID for the WAF probe in check 3.4), `cloudflare_secret_path` (path to a SOPS-encrypted YAML with `CLOUDFLARE_API_TOKEN`). Both optional; consumers without Cloudflare in front of their origin can ignore.

- **SKILL.md description rewritten** to surface "pre-launch + post-launch" framing now that check 11 makes the skill useful past the apex flip.

### Migration notes for v0.7 consumers

No breaking changes. v0.7 invocations work unchanged. To opt into check 11:
1. Add `live_probe_origin: https://<apex>` (or `canonical_origin`) to `.launch-readiness.yml`
2. Run via `bash audit.sh --checks 11 --report-only` for the live-apex sweep alone, or `--checks 1-11` for the full set

To opt into the CF WAF probe in 3.4:
1. Add `cloudflare_zone_id: <zone-uuid>` to `.launch-readiness.yml`
2. Make `CLOUDFLARE_API_TOKEN` reachable (env var OR SOPS path via `cloudflare_secret_path: secrets/cf-api.enc.yaml`)

### Audit-state shift (consumer-repo `thomasjankowski-site` example)

Pre-v0.8 (v0.7 + F-2 fixes against live apex): 0 FAIL / 6 WARN / 46 PASS / 1 MV / 11 INFO / 1 NA.

Post-v0.8: 0 FAIL / **4 WARN** / 46 PASS / 1 MV / 12 INFO / 1 NA. WARNs 3.4 (Bytespider WAF) + 7.3 (home URL in sitemap) cleared. Remaining 4 WARNs all pre-existing accepted-as-current (6.2 IndexNow hook → F-3 publish-time trigger, 7.2 lastmod editorial-date mismatch, 8.1 single-word anchors → named entities, 8.3 link density → 3 short pieces).

## [0.7.0] — 2026-05-14

### Added

- **Two-pass curation pattern.** Pass 1 (10 parallel subagents)
  reads each batch's 25 piece bodies + full corpus link table +
  section-anchors index, identifies named operator-class concepts
  with originator slug + originator section. Pass 2 (10 parallel
  subagents) reads each batch + the full concept catalogue, emits
  typed citations against catalogued originators. Solves the
  cross-batch concept-resolution problem v0.6 hit. Driver scripts:
  `scripts/build_v07_pass1_batches.py` + `build_v07_pass2_batches.py`.
- **Section-anchor pattern.** Tracked
  `<repo>/docs/editorial/section-anchors.json` (or equivalent) maps
  each piece's h2/h3 to slugified IDs. Citations target specific
  sections via `<a href="/writing/<slug>/#<section>">` path-fragment
  form (replaces v0.6's hash-form which couldn't carry section
  anchors). Section IDs are stability levers: re-run the anchor
  script + diff the JSON to surface moved anchors. This skill ships
  the pattern as documentation; the consumer repo emits its own
  artifact via `scripts/add_section_anchors.py`.
- **Typed-citation schema emission.** Skill consumers can pivot
  their schema emitter from `mentions[]` (loose relatedness graph)
  to `citation[]` (Schema.org CreativeWork with section-anchored
  @id, concept name, typed relation in description: `[groundedBy]`
  / `[extendedBy]` / `[substantiatedBy]` / `[contradictedBy]` /
  `[discussedIn]`). Schema.org-valid; no cito: namespace dependency.
  Reference implementation in the consumer repo's
  `scripts/emit_schema_graph.py`.

### Changed

- **Check 8 (internal-link-quality) bug fixes.**
  - Double-glob bug: the prior `list(*.tsx) + list(**/*.tsx)`
    double-counted in flat content layouts. Replaced with
    `set(rglob(...))`. 8.1.single_word + 8.3.density counts now
    accurate.
  - 8.4.graph_density: now reads `citation[]` OR `mentions[]` from
    the schema graph (v0.7 emitters may choose either signal;
    crawlers parse both). Replaces the prior `mentions[]`-only
    check. Title surfaces which signal predominates.

### Removed

- v0.6's CURATED_LINK_GRAPH-only pattern in the reference emitter
  (the consumer repo's `scripts/emit_schema_graph.py`) -- mentions[]
  is dropped in favor of citation[]. Skill consumers who want to
  keep mentions[] can still do so; the audit checks accept either.

### Out of scope (deferred to v0.8+)

- Post-flip live external audit parity (Screaming Frog, Lighthouse
  CrUX integration).
- Cron-style scheduled re-curation routines (the v0.5 scaffold +
  v0.7 two-pass pattern support /loop and /schedule; the actual
  cron wiring is consumer-side).
- Offline-rules expansion to Organization / WebPage / BreadcrumbList
  ListItem shape (the 2.10 web-validator fallback's
  `_web_validator.should_be_covered_offline` field lists these as
  promotion candidates).
- Richer relation typology (CiTO under extended @context) for sites
  that want scholarly-grade citation typing.
- GSC + Bing Webmaster API integration (post-flip verification gate).

---

## [0.6.0] — 2026-05-14

### Added
- **Check 10 — external backlinks** (item 1). New
  `scripts/check-backlinks.py` + `checks/10-backlinks.md`. Free-tier
  sources, **no paid API**: Wayback CDX always; Common Crawl index
  best-effort; Open PageRank opt-in via `OPR_API_KEY` env. Findings
  `10.0.local_origin` / `10.1.wayback_snapshots` /
  `10.2.referring_domains` / `10.3.opr_rank`. No FAIL severity —
  backlinks are emergent, not gating. Local-origin sentinel emits
  INFO when canonical_origin points at localhost/RFC1918 (pre-flip
  posture). `audit.sh` registers check 10 in default `CHECKS=1..10`.
- **2.10.web_validator fallback** in `check-schema.py` (item 3). For
  nodes whose `@type` isn't in the v0.5 offline curated rules,
  optionally POST to free public `validator.schema.org` endpoint
  (XSSI-stripped JSON response; up to 25 uncovered nodes per request
  to bound rate-limit exposure). Default off
  (`web_validator_fallback: false` in config) to avoid network calls
  on every audit run; opt-in for repos emitting non-Article schema
  (Recipe / Product / etc.). Graceful degradation to MANUAL_VERIFY on
  timeout / HTML response / non-JSON. Reference metadata in
  `references/schema-org-rules.json` `_web_validator` block.
- **First full inline-link curation run** (item 2). 10 parallel Claude
  Code general-purpose subagents dispatched against the v0.5 scaffold;
  produced 361 topically-curated edges across 201 source pieces (out
  of 247 batched). Distribution: ~50/50 confidence 4-vs-5; per-piece
  cap 3 respected; 0 self-links. Application:
  `scripts/apply_curated_links.py` (new) wraps verbatim anchor matches
  in piece TSX bodies with the hash-form `<a href="#/writing/<slug>">`
  (matches the 2 hand-coded reciprocal links that survived the
  2026-05-13 TFIDF revert); 74 visible links applied across 56 pieces
  (rest are paraphrased anchors that still feed `mentions[]`).
  `docs/editorial/curated-link-graph.json` tracked as the canonical
  edge source; `scripts/emit_schema_graph.py` reads it to repopulate
  Article `mentions[]` (replaces the TFIDF noun-chunk edges
  dropped 2026-05-14). 201 articles carry 361 mentions[] edges, avg
  1.8 per piece.

### Out of scope (deferred to v0.7+)
- Post-flip live external audit parity (Screaming Frog, Lighthouse
  CrUX).
- Cron-style scheduled re-curation routines (the scaffold supports
  /loop and /schedule patterns; the actual cron entry is consumer-
  side wiring, not skill code).
- GSC + Bing Webmaster API integration (post-flip verification gate).
- Offline-rules expansion to Organization / WebPage / etc. (the
  v0.6 web-validator fallback's `_web_validator.should_be_covered_
  offline` field lists candidates for promotion).

---

## [0.5.0] — 2026-05-14

### Added
- **`live_probe_origin` config knob** (item 1). Separates "URL that
  ends up in JSON-LD / sitemap / Wikidata reconciliation"
  (`canonical_origin`) from "URL the audit can actually curl right
  now" (`live_probe_origin`, defaults to canonical_origin). Eliminates
  the false-positive cascade where pointing canonical_origin at
  localhost (so live header probes work pre-flip) broke URL-prefix
  matching in checks 5.2 and 7.3. Touches `_lib.py`, `check-headers.py`,
  `check-performance.py`. v0.4 behavior preserved when live_probe_origin
  is unset.
- **`sitemap_lastmod_mode: editorial`** (item 2). New mode for check
  7.2: read frontmatter `dateModified` / `originalPublicationDate` via
  a configurable `slug_to_frontmatter_map` instead of comparing
  source-file mtime. Eliminates false-positive WARN on backdated
  catalogues where every TSX shares build-mtime but editorial dates
  from frontmatter are the correct lastmod signal. New helpers
  `load_frontmatter()` + `find_frontmatter_for_slug()` in `_lib.py`
  (with PyYAML fallback regex-parser). v0.4 `file_mtime` default
  preserved.
- **Offline Schema.org type-validation** (item 3). New curated rules at
  `references/schema-org-rules.json` covering the 13 types this skill
  audits (Article, Person, WebSite, BreadcrumbList, CollectionPage,
  ProfilePage, ImageObject, ItemList, ListItem, DefinedTerm,
  SpeakableSpecification, Occupation, ScholarlyArticle) plus 29
  property-to-type-token mappings + 6 deprecated-property entries.
  Three new findings in `check-schema.py`: `2.9.types_required` /
  `2.9.value_types` / `2.9.deprecated`. Catches what Rich Results Test
  catches that v0.4's structural-shape check missed — surfaced and
  fixed a real `wordCount: null` violation in the live consumer repo's
  emitter during the v0.5 integration test. **No paid API**; offline
  rules JSON only. Web-validator fallback deferred to v0.6.
- **Configurable per-piece JSON-LD sample size** (item 6). New config
  key `jsonld_sample_size` (int N or `"all"`; default 10). `check-
  schema.py` 2.8 sampling honors the override. Malformed values
  (negative, zero, bool, etc.) silently fall back to the default
  rather than crashing the audit.
- **Incremental diff between runs** (item 5). New
  `scripts/audit_diff.py` (stdlib-only). `audit.sh` now auto-rotates
  the previous report to `.launch-readiness-report.prev.json` at the
  start of each run; the new `--diff` flag invokes the diff tool
  post-audit, emitting `.launch-readiness-diff.md`. Match-by-`(check,
  id)` tuple. Surfaces NEW / RESOLVED / severity-changed findings plus
  a delta table. Baseline mode when no prior report exists.
- **Inline-link curation scaffold** (item 7). New
  `scripts/curate_inline_links.py` driver + `templates/curate-inline-
  links-prompt.md`. Driver batches the corpus into self-contained
  per-batch markdown task files + a manifest; **no LLM SDK imports**
  (pure stdlib). Prompt template encodes load-bearing constraints
  (max-3-links, topical-entity-anchors-only, skip-if-no-high-
  confidence, 1-5 confidence rubric, ship-only-≥4, JSON output
  schema). SKILL.md documents three invocation patterns: parallel
  one-shot via Agent dispatch, recurring via `/loop`, scheduled via
  `/schedule`. v0.5 ships scaffold only; first full curation run
  is post-flip work.

### Changed
- **Wikidata 5.3 finding now enumerates missing properties** (item 4).
  Title previously read "Wikidata Q<N> missing 2 of 8 properties" with
  no enumeration. Now: "missing 2 of 8 properties: ['P101 (field of
  work)', 'P39 (position held)']". Both the `title` and the
  machine-readable `current` field carry the list, and `fix_action`
  names the exact properties the operator needs to add at the Wikidata
  entity URL.

### Companion content-side change (in consumer repo, NOT a skill change)
- **`mentions[]` stripped from `Article` schema nodes** in the consumer
  repo's `scripts/emit_schema_graph.py`. The array was populated from
  `link-graph.json`'s POS-tagged noun-chunk extraction — the same
  mechanical signal that drove the reverted TFIDF inline-link
  injection. Visible-anchor vs. invisible-@id-ref doesn't change the
  anti-pattern. Returns when LLM-curation replaces it via v0.5 item 7
  scaffold (full curation post-flip).

### Out of scope (deferred to v0.6+)
- Free-tier backlinks integration (Ahrefs / Moz / Web Archive).
- Full inline-link curation run (the v0.5 scaffold is the prep).
- Web-validator fallback for Schema.org type-tree gaps the offline
  curated rules don't cover.

---

## [0.4.0] — 2026-05-14

### Added

- **Per-piece JSON-LD validation sampling** (`check-schema.py`).
  Now also samples up to 10 rendered HTML pages from `dist/public/writing/`
  (or equivalent), extracts the inline `<script type="application/ld+json">`,
  and validates structurally. Catches per-piece emission drift the
  consolidated `schema-graph.json` doesn't surface.
- **AI-content fingerprint detection** (`check-content-tactics.py`).
  Three new sub-checks: sentence-length variance across corpus (uniform
  variance is an AI signal; human essay prose stddev typically 8-15);
  transition-word density (moreover/furthermore/additionally/consequently
  at >8/1000w is fingerprint-grade); em-dash density (target ≤2/500w).

### Known limitations (v0.4.0 carry-over)

- Schema.org Validator API integration deferred to v0.5 (network rate
  limits; would need request throttling).
- LLM-assisted link curation (subagent dispatch) deferred to v0.5+ —
  better executed at the orchestrating-conversation layer than from
  within the skill.
- Free-tier backlinks API integration deferred indefinitely (each
  provider requires per-repo auth keys; out of scope for a portable
  skill).
- Multi-repo threshold tuning ongoing (can't test against repos that
  don't exist on the local machine).

## [0.3.0] — 2026-05-14

### Added

- **`--apply-safe-fixes` auto-application loop** (`scripts/apply_fixes.py`).
  Reads `.launch-readiness-report.json` from a prior audit, identifies
  findings tagged `fix_safety: "safe"` with a registered fix recipe,
  applies the fix idempotently. Conservative scope: file-create /
  template-drop operations only (robots.txt, llms.txt, llms-full.txt,
  vercel.json headers block, IndexNow key file). Source-modification
  fixes (schema emitter changes, sitemap mtime sourcing) remain `manual`
  because source layout varies per repo. Includes `--dry-run` flag.
- **Audit orchestrator wires `--apply-safe-fixes` flag** to `apply_fixes.py`
  and re-runs audit afterward to verify fixes landed.
- **Lighthouse CLI integration** (`check-performance.py`). If `lhci` or
  `lighthouse` is on PATH AND `canonical_origin` is set in config, runs
  a real audit and parses LCP / CLS / INP findings with PASS/WARN/FAIL
  thresholds. Falls back to MANUAL_VERIFY otherwise.

### Known limitations (v0.3.0 carry-over)

- Schema.org Validator API call deferred to v0.5.

## [0.2.0] — 2026-05-14

### Added

- Per-check execution scripts for all 9 checks (`scripts/check-*.py`)
  - `check-headers.py` — static config audit + live curl probe (when canonical_origin set) for HTTP security headers; indexability check (Disallow/noindex/X-Robots-Tag); 404 status verification; hero image attribute audit; viewport meta validation
  - `check-schema.py` — JSON-LD validation + structural completeness (WebSite root, absolute @ids, Person properties, Article properties, Speakable selector arrays, CollectionPage→ItemList nesting, ProfilePage hasPart, ImageObject count)
  - `check-ai-bots.py` — robots.txt parsing, 14 citation-class + 5 training-class bot coverage diff, Bytespider posture, llms.txt + llms-full.txt presence
  - `check-performance.py` — stack-aware delegation recommendation (vercel:performance-optimizer for Vercel/Next.js), Lighthouse CLI detection, static input checks (preload hints, image formats)
  - `check-wikidata.py` — fetches Q-ID via Wikidata API, verifies P856 reciprocity, inventories 8 required properties
  - `check-indexnow.py` — key file presence (UUID-style `<key>.txt` self-matching), publish-hook grep
  - `check-sitemap.py` — XML parse, URL count, lastmod-vs-mtime sampling, all-identical detection, static page coverage
  - `check-link-quality.py` — inline `<a href>` analysis (anchor-text quality, single-word ratio, density per 500w, named-concept match), JSON-LD mentions[] density
  - `check-content-tactics.py` — per-piece scoring on 8 tactics (thesis-block, inline citations, quotations, first-party data, Q&A subheads, author byline, first-person voice, no-year-in-title), corpus-level GREEN/YELLOW/RED rating
- Shared helper module `scripts/_lib.py` (Finding / CheckResult dataclasses, arg parsing, config loading, severity ranking)
- `templates/llms-full.txt` template
- `templates/.launch-readiness.yml.example` — full config template with documented options
- Orchestrator script-name mapping fix (`audit.sh` now correctly routes check N → check-<topic>.py)

### Known limitations (v0.2.0)

- `--apply-safe-fixes` flag is still parsed but not wired to fix application logic. Each check identifies safe-fix candidates via `fix_safety: "safe"` finding metadata, but auto-application is deferred to v0.3.0.
- Schema validation in `check-schema.py` is structural (presence of properties); semantic validation (Schema.org Validator API call) is deferred. The check correctly identifies the most-likely audit-flagged structural issues.
- `check-performance.py` does not directly invoke Lighthouse; surfaces availability + delegation recommendation. Direct Lighthouse run requires `--apply-safe-fixes` and a separate runner.
- `check-content-tactics.py` uses heuristic regex for tactic detection (e.g., "et al." for inline citation). False positives + false negatives expected at the 5-10% level. Surfaces corpus-level GREEN/YELLOW/RED rating which is robust to per-piece noise.
- No multi-repo testing yet; threshold tuning may need adjustment after exercising the skill against 2-3 different stack/repo shapes (planned for v0.3.0).

### Threshold defaults

- `check-link-quality.py`:
  - Single-word anchor ratio: WARN ≥10%, FAIL ≥30%
  - Link density per 500w: WARN >2
- `check-content-tactics.py`:
  - Tactic coverage per piece: PASS ≥70%, WARN ≥40%, INFO <40%
  - Overall rating: GREEN ≥60% / YELLOW 35-60% / RED <35%
- `check-sitemap.py`:
  - lastmod accuracy tolerance: 1 day vs source mtime
  - All-identical detection: FAIL
- `check-wikidata.py`:
  - 8 required properties; WARN if 1-4 missing, FAIL if 5+ missing
  - P856 missing: always FAIL (load-bearing)

## [0.1.0] — 2026-05-14

### Added

- Initial skill scaffold under `.claude/skills/IEO-launch-audit/`
- `SKILL.md` orchestration with 9 audit categories + invocation patterns
- `README.md` human-facing skill documentation
- 9 check definitions (`checks/01-technical-seo.md` through
  `checks/09-content-tactics.md`)
- Templates: `templates/robots.txt`, `templates/llms.txt`,
  `templates/vercel-headers.json.example`
- Orchestrator script: `scripts/audit.sh`
- Research synthesis: `references/research-2026-05.md` (cited across the
  check definitions)

### Derived from

The 8-subagent parallel research pass on 2026-05-13. Source-of-truth
research summary at `references/research-2026-05.md`. Underlying primary
sources cited within each check file.
