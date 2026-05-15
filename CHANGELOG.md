# IEO-launch-audit — Changelog

All notable changes to this skill. Follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + SemVer.

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
