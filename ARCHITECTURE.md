# ARCHITECTURE.md — IEO-launch-audit

Single-document map of the skill at v1.6.2. Intended audience:
maintainers, contributors, and any Claude Code agent dropped into this
repo without context. Living document; update on each architectural
shift.

For the *what to do* layer, see `CLAUDE.md`. For *audit findings + fix
recipes*, see `checks/*.md`. For *what changed when*, see
`CHANGELOG.md`. This document is the *why + how it fits together* layer.

---

## What the skill is

A Claude Code skill that audits a static / SSG website's
**SEO + IEO + GEO posture** before launch and verifies it post-launch.

- **SEO** — search-engine optimization (Google + Bing classical web
  search).
- **IEO** — index-eligibility optimization (does Google's index
  actually accept the site's URLs).
- **GEO** — generative engine optimization (does the site get cited
  by ChatGPT / Claude / Perplexity / Gemini / AI Overviews).

Runs as `audit.sh` against a consumer's source repo + built artifacts;
emits `.launch-readiness-report.md` + `.launch-readiness-report.json`
+ (v1.5.0+) writes/reads `.ieo-audit-state.yml` for cross-pass tracking.

Stdlib-Python only (no PyYAML / BeautifulSoup / lxml required for
core paths; PyYAML used opportunistically with stdlib fallback).

---

## The 14 audit checks

| # | Name | Default? | Lives in |
|---|---|---|---|
| 1 | Technical SEO | yes | `scripts/check-headers.py` |
| 2 | Schema.org graph | yes | `scripts/check-schema.py` |
| 3 | AI-bot directives | yes | `scripts/check-ai-bots.py` |
| 4 | Core Web Vitals | yes | `scripts/check-performance.py` |
| 5 | Wikidata entity graph | yes | `scripts/check-wikidata.py` |
| 6 | IndexNow | yes | `scripts/check-indexnow.py` |
| 7 | Sitemap accuracy (+ 7.5 substantive-delta opt-in) | yes | `scripts/check-sitemap.py` |
| 8 | Internal-link quality | yes | `scripts/check-link-quality.py` |
| 9 | Content tactics (+ 9.10 front-loading v1.5.1) | yes | `scripts/check-content-tactics.py` |
| 10 | External backlinks | yes | `scripts/check-backlinks.py` |
| 11 | Live-apex audit (12 phases A-L) | **opt-in** | `scripts/check-live-apex.py` |
| 12 | Search Console cross-verification (Bing + GSC) | **opt-in** | `scripts/check-search-console.py` |
| 13 | Imagery provenance (C2PA / IPTC) | **opt-in** | `scripts/check-imagery-provenance.py` |
| 14 | Multimodal markup | **opt-in** | `scripts/check-multimodal-markup.py` |

Default fast pass: `bash audit.sh --checks 1-10` (~5 min).
Full pass with opt-ins: `bash audit.sh --checks 1-14` (varies by
configured integrations).

Within check 11, phase K (Brave probe) and phase L (multi-UA crawler
probe, v1.5.1) are individually opt-in.

---

## The self-improving loop (ADR 0002)

v1.5.0+ ships the architecture for the skill to evolve from
*pure-function audit* to *lightly-stateful audit with periodic
self-analysis*. Decomposed into four phases:

### Phase A (v1.5.0) — state-file substrate

`.ieo-audit-state.yml` in consumer repo root. Tracks per-finding state
across audit passes:

```yaml
state_version: 1
skill_version: "1.6.2"
last_pass_date: "2026-05-20T20:00:00Z"
findings:
  - id: "2.4.schema_text_parity"
    severity: WARN
    title: "..."
    first_seen: "2026-04-15T10:00:00Z"
    last_seen: "2026-05-20T20:00:00Z"
    pass_count: 5      # how many consecutive passes this finding was present
```

Written at end of each audit (`scripts/_state.py`). Consumer commits
to git. Subsequent passes read + compare.

`scripts/self-analyze.py` runs after the main audit. Categorizes
current-pass findings against prior state:

- **Resolved** — was WARN/FAIL, now PASS or dropped out.
- **Regressed** — was PASS, now WARN/FAIL.
- **Persistent** — WARN/FAIL in both passes.
- **New** — WARN/FAIL in current, absent in prior.
- **Long-running** — persistent findings with `pass_count ≥ 3`.

Appends **"Operator action since last pass"** section to the audit
report. First-pass behavior: emits advisory + writes initial state.

### Phase B (v1.5.2) — GSC/Bing delta as companion signal

When check 12 (Search Console cross-verification) is configured AND
`.launch-readiness-report.prev.json` exists, self-analyze:

1. Extracts numeric metric values from check 12 findings'
   `current` field (Bing crawl-errors, crawled-pages, GSC indexed-count,
   sitemap-count).
2. Computes deltas vs the auto-rotated prev report.
3. Emits **"Indexing-state context (Phase B, medium confidence)"**
   subsection.

**Confidence-tier framing mandatory.** Per ADR 0002 Decision 1,
audit-diff persistence (Phase A) is the primary measurement signal
because attribution is clean at the action layer. GSC/Bing deltas
are *companion* signals at medium confidence — attribution noise is
unresolvable (algo updates, seasonality, other operator changes).

### Phase B+ (v1.6.2) — substantive-edit pairing

Opt-in via `substantive_edit_pairing: true` + `canonical_origin` set.
When self-analyze detects resolved findings, this probe:

1. Fetches sitemap.xml from canonical_origin.
2. Samples 3 URLs (deterministic seed).
3. For each: Wayback CDX content-digest fetch + current HTML fetch +
   `difflib.SequenceMatcher` ratio.
4. Classifies each URL as `substantive` (≥10% text delta), `cosmetic`
   (<10%), or `unverifiable`.

Emits **"Substantive-edit pairing (Phase B+, advisory)"** subsection
with two framings:

- **Compliance-theater advisory** when 0/N substantive but findings
  resolved — resolutions may reflect emitter-side fixes (e.g.,
  dropping unmirrored JSON-LD strings) rather than visible content
  changes.
- **Directional consistency** when ≥1/N substantive — paired with
  resolved findings, but correlation only.

Network-bound: ~30s-2min when enabled. Opt-in so the audit budget
stays predictable.

### Phase C (v1.6.0) — auto-research routine

Maintainer-side. `scripts/research/` ships:

- **`PROTOCOL.md`** — execution guide for a Claude Code session
  invoked monthly via `/schedule`. Discovery wave (5-7 parallel
  subagents across 8 corpora) → steelman wave (3-5 parallel) →
  verification wave (3-5 parallel attacking findings) →
  consolidation → ship as PR.
- **`auto-pass.sh`** — git + gh ship mechanics. `init` sets up
  branch; `ship` commits + pushes + opens PR via `gh`.
- **`README.md`** — usage doc + scheduled-cadence example.

**Activation is operator-side** — configure via Claude Code
`/schedule` when ready:

```
/schedule monthly-on-1st 09:00 "Run the IEO-launch-audit auto-research
pass per scripts/research/PROTOCOL.md against
github.com/thomasthinks/IEO-launch-audit"
```

When active: ~60-100min wall-clock per pass, ~$50-90/month in Claude
credits. Maintainer reviews every candidate; routine never auto-merges.
Calibration triggers per PROTOCOL.md § 10 (drop to quarterly if zero
candidates 3x consecutive, etc.).

### Phase D (deferred to v1.7+) — cross-repo auto-learn

Aggregate state across multiple consumer repos (maintainer fleet OR
opted-in public cohort) + emit `auto-learn-report.md` flagging
patterns ("threshold X under-actioned across 4 repos for 3 months —
consider loosening"). Needs opt-in privacy gating + multi-repo
schema design. Not in scope until consumer fleet is large enough to
justify the architecture.

---

## Operator UX

**`scripts/inspect-state.py`** (v1.6.1) — stdlib CLI for operators
to inspect `.ieo-audit-state.yml` between audit runs:

```bash
python3 scripts/inspect-state.py                  # summary
python3 scripts/inspect-state.py --long-open 5    # top 5 stuck findings
python3 scripts/inspect-state.py --id '14\.'      # all check-14 findings
python3 scripts/inspect-state.py --json | jq ...  # structured output
```

Read-only. Surfaces: severity counts, longest-open WARN/FAIL findings
(by `pass_count` desc), relative-age formatting ("3 months ago"),
optional regex filter.

---

## The research discipline (ADR 0001)

The skill's evidence base — what claims it surfaces in finding text,
fix-actions, and cited sources — has a published verification regime.
v1.4.1 amended it with a paired discipline.

### Two reflexes (paired, not alternating)

**Verification reflex** (defensive — catches folklore). Subagent
attacks each candidate claim:

- Pattern 1: precise % with no methodology.
- Pattern 2: "submit to X" for products that don't exist.
- Pattern 3: single-source boundaries smoothed into precise numbers.
- Pattern 4: vendor-published weight % for closed-source ranking
  algorithms.

**Steelman reflex** (generative — finds strongest available evidence).
Subagent dispatched with the explicit task of finding the strongest
primary, first-party, or methodology-disclosed evidence FOR a
hypothesis. Opposite incentive structure to verification.

**The two compose into a pipeline** per candidate:

```
candidate hypothesis
        │
        ▼
   steelman pass ──── verbatim evidence + source URLs + tier tags
        │
        ▼
   verification pass ── attacks each finding (folklore patterns 1-4
        │              + verbatim quote re-fetch)
        ▼
   survives both? → promote
                    else → reject; log reasoning
```

Steelman alone produces credulity. Verification alone produces
shallowness. Both required for any candidate that ships.

### 8 mandated corpora (major-pass steelman)

1. Academic / methodology-disclosed primary research (arXiv,
   Semantic Scholar, ACM, KDD/WWW/EMNLP/SIGIR proceedings).
2. First-party platform documentation (developers.google.com,
   platform.claude.com, help.openai.com, perplexity.ai/hub,
   learn.microsoft.com, blogs.bing.com, brave.com/blog).
3. Conference talk catalogs (BrightonSEO, SMX, Pubcon, MozCon,
   SEOFOMO Live).
4. Practitioner long-form on LinkedIn (Indig, King, Solís, Ray,
   Haynes, Shepard, Gabe, Critchlow, Kohn).
5. Newsletter back-issues (SEOFOMO, Growth Memo, Indie SEO, Search
   Engine Roundtable).
6. Practitioner subreddits (r/SEO, r/bigseo, r/TechSEO).
7. YouTube speaker-series transcripts.
8. GitHub awesome-lists + GEO-tooling repo discussions.

A pass that hits only 1+2 is fine for primary-source questions. A
pass that hits only 4+6 is suspect (practitioner opinion without
methodology). Mix tiers.

### Budget calibration

| Pass type | Discovery | Steelman | Verification | Cost |
|---|---|---|---|---|
| Major version (e.g., v1.4 → v1.5) | 5-7 parallel, 60-100 tool uses each | 3-5 on top hypotheses, 40-60 tool uses each | 3-5 attacking findings | ~$75-120 |
| Patch (e.g., v1.4.1 → v1.4.2) | 1-2 lightweight | 1-2 on specific question | 1-2 | ~$20-40 |
| Monthly auto-research (Phase C) | 5-7 | 3-5 | 3-5 | ~$50-90/month |

The v1.4-style "thin pass" (2 discovery + 2 verification) is
**retired** for major-version candidate slates per ADR 0001 v1.4.1.

### Verification disposition format

Per attacked finding: **PROMOTE / DEMOTE / KILL**.

- **PROMOTE** — verbatim quote confirmed, methodology disclosed, no
  folklore pattern triggered.
- **DEMOTE** — quote confirmed but claim narrower than steelman
  framed.
- **KILL** — quote not at URL, paraphrase-strengthening, folklore
  triggered, or primary source contradicts framing.

Target distribution: 4-7 PROMOTE / 1-3 DEMOTE / 0-2 KILL per pass.
Outside band suggests calibration issue (rubber-stamping or
over-killing).

---

## File map

```
.
├── ARCHITECTURE.md            ← this file
├── CHANGELOG.md               ← per-release detail (v1.3 → v1.6.x arc)
├── CLAUDE.md                  ← agent orientation for any Claude in this repo
├── README.md                  ← consumer-facing skill description
├── ROADMAP.md                 ← v1.x candidates + standing principles
├── SKILL.md                   ← skill manifest + retrieval aliases
│
├── checks/
│   ├── 01-technical-seo.md          ← per-check why/what/fix docs
│   ├── 02-schema-graph.md
│   ├── ... (one per check 1-14)
│   └── 14-multimodal-markup.md
│
├── docs/
│   └── decisions/
│       ├── 0001-claim-verification.md   ← ADR: research discipline
│       └── 0002-self-improving-skill.md ← ADR: self-improving architecture
│
├── references/
│   ├── research-2026-05.md      ← v1.3 deep-research evidence base
│   ├── schema-org-rules.json    ← curated Schema.org type+property rules
│   └── (future: research-YYYY-MM.md per monthly auto-research pass)
│
├── scripts/
│   ├── audit.sh                  ← top-level orchestrator
│   ├── _lib.py                   ← Finding/CheckResult dataclasses + helpers
│   ├── _state.py                 ← state-file substrate (v1.5.0+, Phase A)
│   ├── self-analyze.py           ← Phase A + B + B+ orchestrator
│   ├── inspect-state.py          ← operator UX CLI (v1.6.1)
│   ├── audit_diff.py             ← cross-pass diff (v1.2)
│   ├── apply_fixes.py            ← apply-safe-fixes path
│   ├── crux-trend.py             ← CWV trend tracking (v1.2)
│   ├── check-*.py                ← one per check (1-14)
│   │
│   └── research/                 ← Phase C auto-research (v1.6.0+)
│       ├── PROTOCOL.md           ← execution guide for /schedule sessions
│       ├── auto-pass.sh          ← git + gh ship mechanics
│       └── README.md             ← usage doc
│
└── templates/
    ├── .launch-readiness.yml.example   ← consumer config template
    └── vercel-headers.json.example
```

---

## Architecture invariants (preserved at every layer)

Per ADR 0001 + ADR 0002, the skill maintains these invariants:

1. **Audit-diff persistence is the primary measurement signal**
   (clean attribution at action layer).
2. **GSC/Bing delta is companion-only at medium confidence**
   (attribution noise unresolvable).
3. **State lives in consumer repo** (committed, version-controlled,
   survives skill reinstalls).
4. **Auto-learn is advisory-only** (skill never auto-mutates its own
   checks or thresholds).
5. **Auto-research opens PRs, never merges** (maintainer reviews +
   decides every candidate).
6. **Two-reflex discipline (steelman + verification)** for all
   research passes.
7. **8 mandated corpora** + budget calibration.
8. **Verbatim quotes for empirical claims** — never paraphrase
   "+X%" / "N-Y range" without preserving bounds.
9. **Source-tier tagging explicit** per finding (primary / first-
   party / methodology-disclosed / practitioner / FOLKLORE).
10. **Stdlib-Python by default**; optional integrations
    (PageSpeed Insights, Cloudflare WAF, OPR API) graceful-degrade
    when absent.

---

## What's deferred to v1.7+

Documented decisions to NOT ship yet, with the trigger that would
unblock them:

| Deferred item | Trigger to revisit |
|---|---|
| **Phase D cross-repo auto-learn** | Consumer fleet large enough to make multi-repo aggregation worth the privacy-gate complexity. |
| **NLWeb / `schemamap` endpoint detection** | (a) Portable static-file spec (W3C/IETF/WHATWG draft) AND (b) ≥1 LLM engine publicly confirms parsing the endpoint. |
| **Bing AI Performance dashboard API integration** | Microsoft exposes AI-Performance data via Bing Webmaster API (currently UI-only per their Q&A). |
| **LLM probe for check 9 Query Fan-Out** | Clean opt-in API surface design that doesn't bind the skill to a specific LLM provider. |
| **GSC live-API integration** | Consumer pushes for it OR Anthropic ships a primary-source-verification tool that supersedes the snapshot-reader path. |
| **State schema v1 → v2 with metric persistence** | Multi-pass trend analysis needed (Phase B currently uses only the immediate prev). |
| **Heading-count band check (v1.5 conditional)** | Independent replication of Indig's vertical-specific peaks (currently single-vendor, ChatGPT-only). |
| **Passage/chunk-level audit (v1.5 conditional check 15)** | Methodology-disclosed empirical study quantifying lift (currently practitioner-consensus only). |

---

## When this document is wrong

Living document. Update when:

- A new phase ships (Phase D, future).
- An ADR is amended or superseded.
- A check count changes.
- A deferred item moves to "shipped" or "rejected."
- A new architectural invariant is added (e.g., from a future ADR
  0003+).

The maintainer is the source of truth; this document trails the
release-state in CHANGELOG.md by at most one release.
