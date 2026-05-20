# IEO-launch-audit

A Claude Code skill that audits a static / SSG site's SEO / IEO / GEO
posture before launch and verifies it post-launch. Catches what external
auditors (Screaming Frog, Sitebulb, Ahrefs, Lighthouse, Schema Markup
Validator, Google Rich Results Test) will flag, plus the LLM-citation-side
gaps the SEO tool ecosystem still under-covers.

**Status:** 1.6.4 (14 checks + complete self-improving loop + operator UX + substantive-edit pairing + ARCHITECTURE.md + 404-cascade bugfix). v1.6.4 fixes a check-11 bug where a missing baseline page (e.g., `/about` on a product site) caused a cascade of 6+ false-positive "missing X" findings across phases B / C / G as the audit walked the 404 response body. Surfaced by real consumer feedback on a product-site audit (pdfops.dev). Phases now check HTTP status during baseline sampling; non-200 pages are excluded from content-extraction phases and consolidated into one `11.0.expected_pages_missing` MANUAL_VERIFY finding. v1.6.3 ships [ARCHITECTURE.md](ARCHITECTURE.md) — a durable single-document map of the v1.6.2 architecture. Intended audience: maintainers, contributors, and any Claude Code agent dropped into this repo without prior context. Doc-only patch closing the v1.3 → v1.6 architectural arc. v1.6.2 closes a named Phase B+ gap from the v1.5.2 CHANGELOG: when self-analyze detects resolved findings AND the operator opts in (`substantive_edit_pairing: true` + `canonical_origin` set), it probes 3 sitemap URLs via Wayback CDX, computes text-delta vs current rendered HTML, and emits a "Substantive-edit pairing" advisory subsection. **When 0/N sampled URLs show substantive content change but findings were resolved, flags compliance-theater risk** — resolved findings may reflect emitter-side fixes rather than visible content changes. Distinguishes "fixed the emitter to satisfy the audit" from "fixed the underlying issue." Network-bound, ~30s-2min when enabled. Stdlib only. v1.6.0 adds **Phase C of ADR 0002**: `scripts/research/` directory with PROTOCOL.md (execution guide for a Claude Code session invoked monthly via `/schedule`) + auto-pass.sh (git + gh ship mechanics) + README. Operationalizes ADR 0002 Decision 4: monthly cadence, opens PR, never auto-merges, ~$50-90/month operational cost. Maintainer reviews + decides every candidate. **Activation is operator-side** — configure via Claude Code `/schedule` when ready. v1.5.1 ships the 5 firm candidates from v1.4.1's deep GEO research pass (steelman + verification discipline), all landing atop the Phase A state-file substrate: (1) schema-text parity finding-text strengthened with Ahrefs 1,885-page DiD methodology + Phase-4 caveat (check 2.4); (2) cross-engine citation portfolio framing in check 12 doc (Indig Consensus Gap 3.7M / SISTRIX Jaccard 0.17 / arXiv:2510.11560); (3) new check 9.10 — first-30% positional check (declarative claim + entity density in first 30% of body, ChatGPT-only boundary preserved per Indig 18K-citation methodology); (4) freshness substantive-edit detection finding-text strengthened with arXiv:2509.11353 ACM SIGIR-AP 2025 peer-reviewed + Ahrefs 16.975M field study + Bing first-party "stale fact" quote (check 7.5); (5) new check 11.L — multi-UA live-apex probe catching CDN-layer AI-bot blocks invisible to source-side audits (opt-in via `multi_ua_probe: true`). v1.3 ships seven
new findings from the second-pass recursive research: schema↔visible-text
parity (Google policy backstop; SearchVIU + Duck Test 2026 verified),
@graph consolidation INFO (NLWeb-readiness; advisory), `about` vs
`mentions` usage INFO, entity-hub `sameAs` coverage probe (top-tier hub
list extending check 5 beyond Wikidata), per-engine freshness bands +
substantive-delta detection via Wayback CDX (Mueller-on-record;
December 2025 core update enforcement), Query Fan-Out heuristic
retrievability proxy (structural-only; honest about LLM-probe limitation),
and new opt-in **check 13** (AI-imagery provenance — IPTC `digitalSourceType`
+ C2PA; Google Merchant Center indexing-side, distinct from declined EU AI
Act scope). Also ships ADR 0001 documenting the claim-verification reflex.
See `CHANGELOG.md` for the full v0.5 → v1.3 roll-up.

Add `.launch-readiness-report.*` to your repo's `.gitignore` to keep
generated reports out of version control. The reports are local artifacts
that change on every run.

## What this skill does

Thirteen audit categories, each with cite-able rationale and concrete fixes:

| # | Category | Covers |
|---|---|---|
| 1 | Technical SEO | HTTP headers, canonical URLs, 404 status, mobile-first viewport, hero-image attrs, sitemap lastmod accuracy |
| 2 | Schema.org graph | JSON-LD validation + completeness (WebSite root, absolute @id URLs, ImageObject, ItemList nesting, Speakable selector array); opt-in web-validator fallback for long-tail @types |
| 3 | AI-bot directives | robots.txt + llms.txt + llms-full.txt. Citation-class + training-class user-agent coverage. Bytespider edge-block + optional Cloudflare WAF API verification |
| 4 | Core Web Vitals | LCP / INP / CLS targets. Opt-in PageSpeed Insights v5 with CrUX field-data parsing; delegates to vercel:performance-optimizer if available; Lighthouse CLI fallback |
| 5 | Wikidata entity graph | Person sameAs to Q-ID, P856 (official website) reciprocity. Operator-side checklist |
| 6 | IndexNow | Key file + publish-hook ping flow. Bing/Yandex/Naver coverage |
| 7 | Sitemap accuracy | lastmod matches real mtimes (file_mtime mode) or editorial dates from frontmatter (editorial mode for backdated catalogues). Sitemap submitted to GSC + Bing |
| 8 | Internal-link quality | Catches TFIDF-distinctive-phrase trap. Recommends LLM-curated or hand-curated inline + Read-next footer |
| 9 | Content tactics | GEO content-side levers (Princeton/Georgia Tech KDD 2024 + 2025-2026 follow-ups). Advisory; does not auto-fix prose |
| 10 | External backlinks | Free-tier Wayback CDX + Common Crawl + Open PageRank (with `OPR_API_KEY`). Observational, no FAIL severity |
| 11 | Live-apex audit | Sitemap reachability, rendered-HTML JSON-LD, per-page meta drift, inline-link 404 detection, security-header consistency, discovery-artifact reachability, Screaming-Frog-parity title/H1/meta hygiene, redirect-chain audit, sitemap-vs-link reconciliation, duplicate meta-description detection, Brave Search indexability probe (Claude-citation eligibility, v1.1). Opt-in (requires live origin) |
| 12 | Search Console cross-verification | Bing Webmaster API (GetUrlSubmissionQuota + GetCrawlStats; indexed-vs-sitemap delta, crawl errors, blocked pages). Google Search Console snapshot path (operator-exported JSON; indexed-vs-sitemap + excluded-reason taxonomy). v1.2, opt-in (network + operator-side export) |
| 13 | Imagery provenance (C2PA / IPTC) | Reads `og:image` / `twitter:image` XMP for IPTC `digitalSourceType` (`trainedAlgorithmicMedia` / `compositeSynthetic`) + C2PA manifest markers. WARN when AI imagery declared but provenance absent (FAIL when `merchant_feed: true` — Google Merchant Center demotes non-compliant). Stdlib XMP parsing; no PIL/ExifRead. v1.3, opt-in via `ai_generated_imagery: true` |

Checks 1-10 run against the source repo + built artifacts (`dist/`,
`public/`, `out/`). Checks 11 + 12 run against the live apex (check 11)
and the search-engine indexing layer (check 12) and catch the class of
finding paid crawlers and SaaS rank-trackers flag (CDN-side
canonicalization, host-config glob mismatches, slug-rename orphans,
indexed-vs-submitted deltas). The three layers are complementary.

## Why this skill exists

The 2026 SEO/GEO/IEO landscape is fragmented:

- **SEO tooling** (Ahrefs, Semrush, Screaming Frog, Sitebulb) covers the
  technical-SEO + content-quality space but misses LLM-side citation
  posture.
- **GEO tooling** (Profound, AirOps, TryProfound) tracks LLM citation rates
  but doesn't audit the structural inputs.
- **IEO best practices** (structured data, entity graph, Speakable) sit in
  Schema.org documentation + Google/Bing/Anthropic policy posts but no
  tool synthesizes them.

This skill bundles the synthesis into a single pre-flip + post-flip
audit that:
- Runs in ~5 minutes against any static/SSG repo (checks 1-10);
  ~2-3 minutes extra for check 11 against a live origin (more with PSI).
- Reports findings with cite-able rationale per finding.
- Optionally applies safe fixes (header config, llms.txt expansion,
  robots.txt user-agents, Speakable arrays, absolute @ids).
- Surfaces what requires operator decision (Wikidata edits, GSC
  verification, training-bot policy, host-config changes).
- Stays free + stdlib-only: no paid APIs, no `requests`/`httpx`
  dependency, no auth surface beyond optional opt-in API keys
  (`PAGESPEED_API_KEY`, `OPR_API_KEY`, `CLOUDFLARE_API_TOKEN`).

## Quick start

```bash
# Install (clone or copy to .claude/skills/ in your repo OR ~/.claude/skills/ globally)
cp -r path/to/IEO-launch-audit ./.claude/skills/

# Run via Claude Code (default: checks 1-10)
/IEO-launch-audit

# Include the live-apex check (requires the apex to be reachable)
bash .claude/skills/IEO-launch-audit/scripts/audit.sh \
  --checks 1,2,3,4,5,6,7,8,9,10,11 --report-only

# Diff against the previous run (auto-rotated)
bash .claude/skills/IEO-launch-audit/scripts/audit.sh --report-only --diff
```

## Tech-stack support

| Stack | Status | Notes |
|---|---|---|
| Vercel + Next.js | first-class | uses vercel:performance-optimizer for check 4, vercel.json templates for headers |
| Vercel + static | supported | header config via vercel.json |
| Netlify | supported | header config via _headers; uses Lighthouse for check 4 |
| Cloudflare Pages | supported | header config via Workers / _headers; uses Lighthouse for check 4; check 3.4 WAF probe available |
| GitHub Pages | partial | no header control; flagged WARN on check 1 |
| Astro / Hugo / Jekyll | supported | static output; same checks |
| Plain static HTML | supported | minimum viable surface; some checks skipped |

## Configuration

`<repo>/.launch-readiness.yml` overrides defaults. See
`templates/.launch-readiness.yml.example` for an annotated template
documenting every config key. SKILL.md "Configuration" section covers
the rationale for the load-bearing keys.

Notable opt-in surfaces:
- `pagespeed_api_key` / `pagespeed_secret_path` — PSI v5 + CrUX field data for check 4.
- `cloudflare_zone_id` / `cloudflare_secret_path` — Cloudflare WAF API probe for check 3.4 (Bytespider edge-block verification).
- `sitemap_lastmod_mode: editorial` + `slug_to_frontmatter_map` — editorial-date sitemap mode for backdated catalogues (check 7).
- `web_validator_fallback: true` — POST uncovered @types to validator.schema.org (check 2.10).
- `live_probe_origin` — separates "what URL shape to canonicalize on" (canonical_origin) from "what URL the audit curls right now" (live_probe_origin); useful pre-flip when the apex DNS doesn't resolve yet.
- `indexnow_key` — additionally probes `/<key>.txt` reachability in check 11 phase F.

## Output

Three artifacts at the repo root after each run:
- `.launch-readiness-report.md` — human-readable
- `.launch-readiness-report.json` — machine-readable (for CI gating)
- `.launch-readiness-report.prev.json` — previous run, auto-rotated;
  used by `audit_diff.py` to surface what moved between runs

All gitignored by default (the skill emits a `.gitignore` snippet on
first run).

`scripts/audit_diff.py --current X --prior Y` emits a markdown diff
grouped by check, separating new findings (regressions) from resolved
findings (wins), with severity-change and content-drift sections. Pass
`--verbose-pass` to expand collapsed PASS rows.

## Authoring philosophy

Each check answers four questions:

1. **Why does this matter?** Specific cited source(s). No vibes.
2. **What's checked?** A concrete assertion that produces PASS / WARN /
   FAIL. No subjective judgement.
3. **What's the fix?** A copy-pasteable code or config diff. No "consider
   adding."
4. **Is the fix safe to auto-apply?** Tagged `safe` or `manual`. Auto-fix
   never touches anything tagged `manual`.

Each check ages out as best practice shifts. Threshold changes are
versioned in `CHANGELOG.md`.

## What this skill is NOT

- Not a Lighthouse replacement. Lighthouse is more complete on technical
  SEO + accessibility + performance. This skill delegates to Lighthouse
  for check 4 (or PSI when configured) and complements it for the other
  10 checks.
- Not a content auditor. Check 9 (Content tactics) is advisory and lists
  structural recommendations; it doesn't grade prose quality.
- Not an ongoing-rank tracker. Use an SEO suite (Ahrefs, Semrush) for
  ongoing keyword/rank monitoring. This skill is pre-launch posture +
  recurring health-check, not continuous rank tracking.
- Not a generic "best-practices" linter. Each check derives from cited
  2025-2026 best-practice research. When best practice shifts, the check
  updates; this is opinionated by design.
- Not a paid-API consumer. Every network surface is free-tier or
  free-with-opt-in-key (PSI, Open PageRank, Cloudflare). Backlinks via
  Wayback + Common Crawl, not Ahrefs/Moz/Majestic.
- Not an `AGENTS.md` auditor. `AGENTS.md` (Linux Foundation Agentic AI
  Foundation) is a **repo-context file for coding agents** (Cursor,
  Claude Code, Codex, Gemini CLI, Devin, etc.) — not a crawler-policy
  surface like `llms.txt`. The two operate at different protocol layers
  with different audiences. This skill does not audit `AGENTS.md`
  presence or content; if you want repo-context guidance, write one,
  but don't expect it to affect AI-engine citation.

## License

(decision pending) — author has not chosen a license. Treat as
all-rights-reserved until a license is added.

## Authoring credit

Designed during the May 2026 pre-flip audit of
[`thomasjankowski-site`](https://github.com/thomasthinks/thomasjankowski-site).
The research underpinning the check thresholds derives from a four-agent
parallel research pass; see `references/research-2026-05.md`.

## Contributing

This is a single-author skill. If it becomes useful enough to publicize,
contributing guidelines + threshold-change RFC process will be documented
here. For now: open an issue (TBD where) or fork.
