---
name: IEO-launch-audit
description: Pre-launch + post-launch SEO / IEO / GEO audit for a static or SSG site. Audits 14 categories (technical SEO, Schema.org graph, AI-bot directives, Core Web Vitals, Wikidata entity graph, IndexNow, sitemap accuracy, internal-link quality, content tactics, external backlinks, live-apex behavior, Search Console cross-verification, imagery provenance, multimodal markup) and reports gaps with concrete fixes. Designed to catch what external audits (Screaming Frog, Sitebulb, Lighthouse, Schema Markup Validator, Google Rich Results Test, AI-citation trackers) will flag, before they flag it. Pre-launch use: run before pointing the apex domain at a build. Post-launch use: opt-in checks 11 (live-apex) + 12 (Bing API + GSC snapshot) + 13 (AI-imagery XMP) + 14 (multimodal markup) verify behavior + indexing-state + provenance + DOM-side semantic markup the source-side checks can't see. Use when launching a content site, when running readiness checks on someone else's site, or as a recurring health check post-launch.
metadata:
  priority: 7
  version: 1.4.0
  docs:
    - "https://developers.google.com/search/docs/fundamentals/seo-starter-guide"
    - "https://schema.org/Article"
    - "https://web.dev/articles/vitals"
    - "https://llmstxt.org/"
  pathPatterns:
    - 'robots.txt'
    - 'sitemap.xml'
    - 'llms.txt'
    - 'llms-full.txt'
    - '**/structured-data.{json,jsonld}'
    - 'schema-graph.json'
  bashPatterns:
    - '\bmake\s+(verify|audit|launch-readiness)\b'
retrieval:
  aliases:
    - launch audit
    - pre-launch audit
    - seo audit
    - geo audit
    - ieo audit
    - flip readiness
  intents:
    - audit pre-launch
    - check before going live
    - verify seo posture
    - run launch readiness
  entities:
    - SEO
    - GEO
    - IEO
    - Schema.org
    - Core Web Vitals
    - llms.txt
    - Wikidata
    - structured data
---

# IEO-launch-audit

Pre-launch posture audit for a static or SSG site. Catches the gaps external
auditors will flag (Screaming Frog, Sitebulb, Ahrefs Site Audit, Lighthouse,
Schema Markup Validator, Google Rich Results Test, Bing Webmaster URL
Inspection) before they do, plus the LLM-citation-side gaps that the SEO
tool ecosystem still under-covers in 2026.

The skill is opinionated: it's a checklist with cite-able rationale, not a
generic "best practices" linter. Each check names the source(s) it derives
from, the failure mode it catches, and the concrete fix.

## What it covers

Fourteen audit categories, each in `checks/NN-<name>.md`. Checks 1-10
operate on the source repo + built artifacts and run by default;
checks 11-14 are opt-in (live-apex behavior + indexing-state +
provenance + DOM-side semantic markup that the source-side checks
can't see).

1. **Technical SEO** — HTTP headers (HSTS/CSP/Referrer-Policy/Permissions-Policy), canonical URLs, 404 status correctness, mobile-first viewport, hero-image attributes (LCP+CLS), sitemap `lastmod` accuracy.
2. **Schema.org graph** — JSON-LD validation + completeness. `WebSite` root, absolute `@id` URLs, per-page `WebPage`, Person properties (`hasOccupation`, `mainEntityOfPage`), Article completeness (`about`, `articleSection`, `publisher`, `copyrightHolder`), `ImageObject` for heroes, `CollectionPage.mainEntity` → `ItemList`, ProfilePage `hasPart` linkage, Speakable selector array. Optional web-validator fallback (2.10) covers @types not in the offline catalogue.
3. **AI-bot directives** — `robots.txt` + `llms.txt` + `llms-full.txt`. Citation-class user-agents (`OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, `Perplexity-User`, `DuckAssistBot`, `MistralAI-User`, `Applebot`, `Meta-ExternalAgent`, `GoogleOther`, `Google-NotebookLM`). Training-class policy (`GPTBot`, `ClaudeBot`, `Google-Extended`, `CCBot`, `Applebot-Extended`). Bytespider edge-block recommendation; optional Cloudflare WAF API probe (3.4) verifies the block is actually live.
4. **Core Web Vitals** — LCP / INP / CLS targets. Delegates to `vercel:performance-optimizer` if available (Vercel/Next.js stack). Opt-in PageSpeed Insights v5 integration with CrUX field-data parsing when `pagespeed_api_key` is configured; falls back to direct Lighthouse CLI run otherwise.
5. **Wikidata entity graph** — Person `sameAs` to Wikidata Q-ID, reciprocity via Wikidata P856 (official website). Operator-side checklist; can't fully automate.
6. **IndexNow** — Key file at `/<key>.txt`, publish-hook ping flow. Covers Bing/Yandex/Naver (Google doesn't consume).
7. **Sitemap accuracy** — `<lastmod>` matches real file mtimes (Google now verifies, not blindly trusts). Sitemap submitted to GSC + Bing Webmaster. Supports `file_mtime` (default) and `editorial` (frontmatter-derived) lastmod modes for backdated catalogues.
8. **Internal-link quality** — Catches the TFIDF-distinctive-phrase trap (mechanical phrase-match ≠ topical relevance). Recommends LLM-curated inline + curated end-of-piece related-block.
9. **Content tactics (advisory)** — GEO content-side levers from Princeton/Georgia Tech (KDD 2024) + 2025-2026 follow-ups: thesis-first via Speakable, inline author byline, first-party data inline, named citations, direct quotation, Q&A subheads, stable named concepts. Per-piece audit is high-cost; surfaces structural recommendations rather than auto-fixing.
10. **External backlinks (observational)** — Free-tier query of Wayback CDX, Common Crawl index, and Open PageRank (when `OPR_API_KEY` is set) to report archived snapshots, unique referring/archive domains, and domain rank. Pre-flip INFO; no FAIL severity (backlinks are emergent, not gating).
11. **Live-apex audit (post-flip, opt-in)** — Phases 0/A-J. Sitemap reachability, JSON-LD rendered-HTML audit, per-page meta drift, inline-link 404 detection, security-header consistency across routes, discovery-artifact reachability, title/H1/meta-description hygiene (Screaming-Frog-parity), redirect-chain hygiene, sitemap-vs-link-graph reconciliation, duplicate meta-description detection. Optional Brave Search indexability probe (phase K) when `brave_api_key` is configured. Excluded from the default run; opt in with `--checks 11` or `--checks 1-11`.
12. **Search Console cross-verification (opt-in)** — Bing Webmaster API (impressions, clicks, crawl-stats, indexed-count) when `bing_webmaster_api_key` configured; Google Search Console index snapshot (operator-exported JSON) when `gsc_index_snapshot_path` configured. Cross-verifies indexed URL count against sitemap URL count to catch silent indexing drift. Opt in with `--checks 12` or `--checks 1-12`.
13. **Imagery provenance (C2PA / IPTC, opt-in)** — Walks sampled `og:image` / `twitter:image` targets, resolves to local file or remote Range-fetch, scans XMP for IPTC `digitalSourceType` (`trainedAlgorithmicMedia` / `compositeSynthetic`) + C2PA manifest markers. Gated on `ai_generated_imagery: true`. Escalates WARN→FAIL when `merchant_feed: true` (Google Merchant Center demotes / removes non-compliant AI product images). Stdlib XMP parsing; no PIL / ExifRead.
14. **Multimodal markup (opt-in)** — Walks sampled HTML, restricts to `<main>` / `<article>` scope when present, audits figcaption density on content images, alt-text density, and `<table>` presence (excludes nav/header/footer). Gated on `multimodal_markup_check: true`. Backs the SearchVIU 2025 + Williams-Cook Duck Test (Feb 2026) "visible HTML wins" principle and Aleyda Solís AI-search checklist's multimodal-markup recommendations. Default INFO/PASS; WARN only on unambiguously sparse pages with ≥3 content images.

## When to use

- Pre-flip on a content site (writing-led, essay-led, blog, knowledge base)
- Post-major-changes audit (after a redesign, after a content migration)
- Recurring health check (monthly/quarterly) on a live site
- Auditing someone else's site (consulting, advisory, due-diligence)

## When NOT to use

- Pure web-app / SaaS surfaces with minimal indexable content — most of the checks are content-site-specific
- Pre-MVP sites without real content — premature; come back when there are ≥20 indexable pages
- Native mobile apps with thin web surface — checks don't apply
- E-commerce-specific concerns — needs `Product`/`Offer`/`Review` schema audit which isn't covered here (out of scope)

## Mental model

```
audit.sh [--repo PATH] [--report-only|--apply-safe-fixes] [--checks 1,2,5]
   │
   ├── detect tech stack (Vercel/Next.js/Astro/Hugo/Jekyll/plain HTML)
   ├── locate emitted artifacts (sitemap.xml / robots.txt / llms.txt /
   │   schema-graph.json / per-page HTML)
   ├── for each check (1-10 by default; 11 opt-in via --checks):
   │     │
   │     ├── run the check
   │     ├── classify findings: PASS / WARN / FAIL
   │     ├── if --apply-safe-fixes and finding has a "safe-fix" tag:
   │     │     apply the fix (idempotent, traceable)
   │     └── else: report finding + recommended fix
   │
   └── emit summary report (markdown) + machine-readable JSON
```

## Invocation patterns

### Quick scan (report only, all checks)

```
/IEO-launch-audit
```

Equivalent: `bash .claude/skills/IEO-launch-audit/scripts/audit.sh
--report-only`.

### Targeted check

```
/IEO-launch-audit --checks 2,3
```

Runs only Schema.org graph + AI-bot directives. Useful for re-validating
after a fix.

### Apply safe fixes

```
/IEO-launch-audit --apply-safe-fixes
```

Auto-applies fixes tagged `safe`: header config templates, llms.txt
expansion, robots.txt user-agent additions, IndexNow key generation,
Speakable selector array expansion, absolute @id conversion. Does NOT
auto-apply schema graph overhaul, hero image attribute changes, or
internal-link decisions (these require operator judgment).

### Run against a different repo

```
/IEO-launch-audit --repo /path/to/other-repo
```

The skill is repo-agnostic. It detects the tech stack and routes
accordingly. Optional config at `<repo>/.launch-readiness.yml` overrides
defaults (e.g., custom artifact paths, skip-list, threshold overrides).

### Incremental diff between runs

```
bash .claude/skills/IEO-launch-audit/scripts/audit.sh --diff
```

After a fix-loop pass, run with `--diff` to see what improved or regressed
without eyeball-comparing two reports. Mechanism:

- Every run auto-rotates `.launch-readiness-report.json` to
  `.launch-readiness-report.prev.json` *before* the new run overwrites it.
  So the "prior" is always the immediately preceding run.
- `--diff` invokes `audit_diff.py` after the audit, which emits
  `.launch-readiness-diff.md` (and stdout) summarising:
  - Severity-count deltas (`FAIL: 5 → 0 (−5)`, `WARN: 18 → 6 (−12)`, etc.).
  - **New findings** (in current but not prior, matched by `(check, id)`).
  - **Resolved findings** (in prior but not current).
  - **Severity-changed findings** (same id, different severity, e.g. `WARN → PASS`).
- First-ever run has no prior; the diff emits a baseline notice instead
  of erroring.
- To compare against a saved snapshot rather than the auto-rotated prev,
  pass `--diff-path /path/to/snapshot.json`. Useful for "what changed
  since launch?" or "what changed since the last weekly checkpoint?"

Typical fix-loop workflow:

```
bash audit.sh --report-only          # baseline pass
# (apply fixes, manually or via --apply-safe-fixes)
bash audit.sh --report-only --diff   # see what moved
```

## Step-by-step (the agent's workflow when invoked)

### Step 1 — Detect tech stack

Inspect repo root for: `package.json` (Node), `vercel.json` (Vercel),
`next.config.js` / `next.config.mjs` (Next.js), `astro.config.mjs` (Astro),
`config.toml`/`hugo.toml` (Hugo), `_config.yml` (Jekyll), bare `index.html`
(static).

Branch decisions:
- **Vercel + Next.js**: use `vercel:performance-optimizer` for check 4
  (Core Web Vitals). Headers config goes in `vercel.json`. Edge-WAF rules
  use `vercel:vercel-firewall` patterns.
- **Non-Vercel**: fall back to Lighthouse CLI for check 4. Headers config
  goes in the relevant server config (nginx, CF Workers, Netlify
  `_headers`, etc.).
- **Static HTML only**: skip checks that depend on dynamic config; surface
  static-file-only recommendations.

### Step 2 — Locate emitted artifacts

For each path the audit needs, search the repo:
- `robots.txt` — usually at `public/robots.txt` or `dist/robots.txt`
- `sitemap.xml` — similar
- `llms.txt` / `llms-full.txt` — site root
- JSON-LD: check the rendered HTML head for `<script type="application/ld+json">`
- Schema-emitter script: `scripts/emit_schema*.py`, `lib/seo*.ts`, etc.

If artifacts are not found, the check reports `MISSING` rather than running
the check; the fix template is provided.

### Step 3 — Run each check sequentially

Each check is a self-contained markdown file at `checks/NN-<name>.md` with:
- **Why this matters** (one paragraph + cited sources)
- **What's checked** (specific assertions)
- **Pass / Warn / Fail criteria**
- **How to fix** (concrete steps with code/config templates)
- **Auto-fix safety** (tagged `safe` or `manual`)

The agent reads each check file, runs the assertions (via the relevant
script in `scripts/`), and records the result.

### Step 4 — Emit report

Two artifacts:
- `<repo>/.launch-readiness-report.md` — human-readable report
- `<repo>/.launch-readiness-report.json` — machine-readable for CI gating

Report structure:
```
## Summary
  10 checks ran. 4 PASS, 3 WARN, 2 FAIL.

## FAIL — must fix before flip
  [2] Schema.org graph: WebSite root entity missing. Fix: <link to checks/02-schema-graph.md § Fix>
  [5] Wikidata entity: P856 not set on Q139721032. Fix: <link to checks/05-wikidata-entity.md § Fix>

## WARN — should fix before flip
  ...

## PASS
  ...

## Next actions
  ...
```

### Step 5 — Apply safe fixes (optional)

If `--apply-safe-fixes` was passed, after reporting, the agent iterates
findings tagged `safe-fix-auto` and applies them. Each fix is idempotent
and produces a git-trackable change. The report is regenerated after
fixes.

## Configuration

Optional `<repo>/.launch-readiness.yml`:

```yaml
# Skip specific checks (by number)
skip_checks: [4]   # e.g. skip Core Web Vitals on a non-rendered repo

# Override default artifact paths
artifacts:
  robots_txt: dist/public/robots.txt
  sitemap_xml: dist/public/sitemap.xml
  llms_txt: dist/public/llms.txt
  schema_graph_json: dist/public/schema-graph.json

# Wikidata Q-ID (required for check 5)
wikidata_qid: Q139721032

# Apex domain — the real public origin that ends up in JSON-LD `url`
# fields, sitemap <loc> prefixes, Wikidata P856 reconciliation, and other
# URL-shape comparisons. Required for several checks.
canonical_origin: https://example.com

# Live-probe override: where the audit actually curls right now. Defaults
# to canonical_origin. Typical use: pre-flip dev work where the apex DNS
# doesn't resolve yet — point at a local server so live header probes,
# 404-status checks, and Lighthouse runs hit something real, while URL-
# shape checks (sitemap prefix match, P856 reconciliation) keep using
# canonical_origin.
live_probe_origin: http://localhost:5000

# Sitemap lastmod source-of-truth for check 07.
# - file_mtime (default; v0.4 behavior): compare against source file mtime.
#   Correct when the build pipeline preserves authoring mtimes.
# - editorial: compare against editorial date keys (dateModified /
#   originalPublicationDate / publishedDate) read from per-piece frontmatter.
#   Use for backdated catalogues where every source file shares a build-step
#   mtime but per-piece editorial dates are the truthful lastmod signal.
#   Requires slug_to_frontmatter_map.
sitemap_lastmod_mode: file_mtime

# Only used when sitemap_lastmod_mode: editorial.
# slug_to_frontmatter_map:
#   pattern: "docs/editorial/drafts/*{slug}*.md"     # {slug} substituted at runtime
#   fallback_pattern: "writing-drafts/*{slug}*.md"   # optional second glob
#   date_keys: ["dateModified", "originalPublicationDate", "publishedDate"]

# Citation-class bot allowlist for check 3
ai_bots_allow_citation: all  # or: specific list

# Training-class bot policy for check 3
ai_bots_allow_training: all  # or: deny_all, opt_out_list

# Bytespider policy
bytespider_policy: edge_block  # or: robots_disallow, allow

# Per-page JSON-LD validation sample size (check 2.8).
# Integer N (first N rendered HTML pages) or "all" (every page).
# Default: 10. On a 250+ page site, "all" trades minutes of runtime for
# completeness — each page is read from disk, regex-scanned, and JSON-parsed.
jsonld_sample_size: 10

# Web-validator fallback for check 2.10 (v0.6).
# Opt-in: POST nodes whose @type isn't in the curated offline rules
# (references/schema-org-rules.json) to validator.schema.org for advisory
# validation. Catches the Recipe / Product / VideoObject / Event / HowTo
# long tail without committing the skill to maintain an exhaustive
# offline catalog. Default: false (avoids network calls + rate limits).
# Free-but-network-bound: validator.schema.org is unofficial (Google-
# hosted contribution), rate-limited (~50 req/hr before 429), has no
# API contract, and may change output shape without notice. The audit
# bounds calls to one POST/run (the uncovered subset is batched into a
# single @graph) and degrades to MANUAL_VERIFY on any failure mode.
web_validator_fallback: false

# Cloudflare WAF API probe for check 3.4 (v0.8). When zone id + token
# (env CLOUDFLARE_API_TOKEN or SOPS path) are both set, the check
# queries the zone's custom WAF ruleset and verifies an enabled
# Bytespider-block rule. On verify the WARN downgrades to PASS.
# cloudflare_zone_id: 0123456789abcdef0123456789abcdef
# cloudflare_secret_path: secrets/cf-api.enc.yaml

# PageSpeed Insights v5 integration for check 4 (v0.9). When key
# (env PAGESPEED_API_KEY, inline, or SOPS path) is set, real Lighthouse
# scores + CrUX field-data are parsed. Free quota 25k req/day.
# pagespeed_api_key: AIzaSy...
# pagespeed_secret_path: secrets/pagespeed.enc.yaml
# pagespeed_sample_urls: 3            # piece URLs to sample beyond home
# pagespeed_strategy: mobile          # mobile | desktop | both
# pagespeed_include_crux: true        # parse CrUX field-data; no extra cost

# IndexNow keyfile (v0.5+). When set, check 11 phase F also probes
# /<indexnow_key>.txt against the live apex.
# indexnow_key: 0123456789abcdef0123456789abcdef
```

For an annotated walk-through of every key (including section-grouping
by check), see `templates/.launch-readiness.yml.example`.

## Web-validator fallback (check 2.10, v0.6)

The offline curated rules in `references/schema-org-rules.json` cover the
13 @types this skill audits on editorial sites (Article, Person, WebSite,
CollectionPage, ProfilePage, ImageObject, BreadcrumbList, ItemList,
ListItem, DefinedTerm, SpeakableSpecification, Occupation,
ScholarlyArticle). A consumer repo that emits Recipe (food blog), Product
(e-commerce), VideoObject (media site), Event / FAQPage / HowTo /
JobPosting / LocalBusiness, etc., will see those nodes silently skipped
by the offline 2.9.* checks.

Enable `web_validator_fallback: true` to POST uncovered-type nodes to
`https://validator.schema.org/validate` for advisory validation. The
fallback emits one `2.10.web_validator` finding per audit run:

- `PASS` — no uncovered types, or validator returned 0 errors
- `WARN` — validator flagged at least one non-severe issue
- `FAIL` — every flagged issue is marked severe
- `MANUAL_VERIFY` — endpoint unreachable / timed out / returned non-JSON

**Endpoint caveats (load-bearing, free-but-network-bound):**

- Unofficial: hosted by Google as a contribution, no API contract, output
  shape can change without notice. Cross-check flagged properties against
  the relevant Schema.org type page before treating as authoritative.
- Rate-limited: ~50 requests/hour before 429. The audit bounds itself to
  one POST per run (uncovered nodes batched into a single `@graph`),
  capped at 25 nodes.
- Network-bound: 15s timeout/request. On flaky connections the fallback
  degrades cleanly to MANUAL_VERIFY rather than blocking the run.
- Free: no auth, no API key, no billing surface. The trade is the
  endpoint stability listed above.

If a consumer site needs deterministic validation for a long-tail @type,
promote it from web-validator fallback to offline curated rules in
`references/schema-org-rules.json` (see the `_web_validator.expansion_policy`
block there).

## Dependencies

Required:
- `python3` ≥ 3.11
- `curl`, `grep`, `find`, `awk`
- Internet access (validators + Wikidata lookups)

Optional (auto-detected; check 4 degrades if missing):
- `lhci` / `lighthouse` CLI (for Core Web Vitals on non-Vercel stacks)
- `vercel:performance-optimizer` skill (for Vercel/Next.js Core Web Vitals)
- `vercel:vercel-firewall` skill (for edge-WAF rule templates)

## Output schemas

See `checks/SCHEMA.md` for the JSON shape of each check's output.

## Curation scaffold (v0.5)

Inline-link curation (and the future `mentions[]` JSON-LD edges that the
v0.5 `mentions[]` strip just emptied) is **LLM-curated**, not
mechanically derived. The prior TFIDF noun-chunk pass injected 385
inline links that had to be reverted on 2026-05-14; the failure mode was
distinctiveness-without-topicality. The scaffold below is the
replacement direction.

**This skill ships only the scaffold.** It does NOT call any LLM API.
The full curation run is post-flip operator work; v0.5 preps the
batches so a Claude Code subagent (the LLM-in-the-harness) can do the
curation. No `anthropic` / `openai` SDK key required.

### Files

- `scripts/curate_inline_links.py` — driver. Reads the corpus TSX dir,
  parses each piece's `(slug, title, body)`, builds the full corpus
  link table, chunks the corpus into batches of N (default 25), and
  writes one self-contained markdown task file per batch to
  `.curation/batch-NN.md` plus a top-level `manifest.json`.
- `templates/curate-inline-links-prompt.md` — the prompt the subagent
  reads. Load-bearing constraints (anchor must be a topical entity, not
  a generic phrase; max 3 links per piece; ship only
  `confidence_score >= 4`; zero links is a valid output).
- Config (under `curation:` in `.launch-readiness.yml`):

  ```yaml
  curation:
    corpus_tsx_dir: client/src/content/writing  # default
    batch_size: 25                              # default
    output_dir: .curation                       # default
    body_excerpt_words: 0                       # 0 = full body
    canonical_origin: https://example.com       # for link-table URLs
  ```

### Invocation pattern A — parallel one-shot

In a Claude Code session:

```
python3 .claude/skills/IEO-launch-audit/scripts/curate_inline_links.py \
  --repo . --batch-size 25
```

Then dispatch one `general-purpose` subagent per batch in parallel,
each pointed at its batch file. Each subagent reads the file (prompt +
pieces + link table all self-contained), produces the JSON array,
returns it. Aggregate the JSON outputs into a single
`.curation/suggestions.json`. v0.5 stops here; v0.6+ wires that JSON
back into the site (inline-link injection + `mentions[]` re-derivation
under the LLM-curated regime).

### Invocation pattern B — recurring (`/loop`)

For a published site where the corpus grows slowly, re-curate on a
cadence:

```
/loop 1w /curate-links
```

Where `/curate-links` is a (future) repo-local slash command that
re-runs the driver and dispatches subagents. The `/loop` skill
re-invokes on the interval; the watchdog detects budget/stuck states.
Stabilise the driver across two or three manual runs before scheduling
a loop; don't iterate on the tool and the corpus simultaneously.

### Invocation pattern C — scheduled (`/schedule`)

Same flow as `/loop`, but bounded to a specific cron expression:

```
/schedule "0 3 1 * *" /curate-links
```

Runs the driver + dispatches subagents at 03:00 on the first of each
month. Use when re-curation should align with content-publishing
cadence rather than wall-clock interval.

### Verification

Dry-run reports what the driver would emit without writing:

```
python3 .claude/skills/IEO-launch-audit/scripts/curate_inline_links.py \
  --repo . --dry-run
```

Emits JSON to stdout with `pieces_parsed`, `batch_count`, first batch's
piece slugs, and the would-write file list.

## Cross-references

- `references/research-2026-05.md` — synthesis of the four-subagent research
  pass (May 2026) that informs this skill's check thresholds and fix
  recommendations. Cite when explaining a finding.
- `README.md` — public-facing skill documentation (for promotion to global
  skills or external publication).
- `CHANGELOG.md` — version history of check definitions + threshold
  changes.

## Versioning

This skill follows SemVer at the check level. Adding new checks bumps
MINOR. Changing failure thresholds for existing checks bumps PATCH (with
note in `CHANGELOG.md`). Removing checks bumps MAJOR (breaking change for
CI consumers).

Current: **0.7.0** (typed-citation graph). Shipped two infrastructure
pieces and the corpus pass that exercises them:

Infrastructure (skill side):
- Two-pass curation pattern: pass 1 builds a corpus-wide concept
  catalogue (named operator-class concepts + originator slug +
  originator section); pass 2 emits typed citations against the
  catalogue. Solves the cross-batch concept-resolution problem v0.6
  hit (subagent in batch 3 couldn't see batch 7 to pin originators).
- Section-anchor pattern: tracked `section-anchors.json` artifact
  maps each piece's h2/h3 to slugified IDs. Citations target the
  specific section where a concept lives, not the article home.
  Stability lever: re-running the anchor script + diffing the JSON
  surfaces moved anchors (text-stable when h2 wording is stable).
- Path-fragment link form: visible inline links land at
  `/writing/<slug>/#<section>` (path resolves prerendered HTML,
  fragment scrolls in-page). Replaces v0.6's hash-form `#/writing/`
  which couldn't carry section anchors.
- Schema emitter pivot: drops `mentions[]` entirely (loose
  relatedness graph); emits `citation[]` (Schema.org CreativeWork
  with section-anchored @id, concept name, typed relation in
  description). Schema.org-valid; no cito: namespace dependency.
- Check 8 fixes: double-glob bug (top-level + `**/*` counted flat
  layouts twice); 8.4 now reads citation[] OR mentions[] (v0.7
  emitters can choose either signal).

Corpus pass (against the source repo):
- 286 named operator-class concepts catalogued.
- 194 typed citations across 127 source pieces (109 target pieces).
- Relation mix: groundedBy 71 / extendedBy 49 / discussedIn 43 /
  substantiatedBy 29 / contradictedBy 2.
- 121 visible inline path-fragment links applied across the corpus.
- Surfaced asymmetric origin chains the loose graph couldn't (e.g.
  the 2007 thesis as canonical originator of concepts referenced
  by 2024-2025 pieces).

v0.5/v0.6 deliverables still apply: `live_probe_origin` config split,
`sitemap_lastmod_mode: editorial`, offline Schema.org rules,
configurable `jsonld_sample_size`, Wikidata property enumeration,
`audit_diff.py`, check 10 external backlinks, 2.10 web-validator
fallback.

v0.8+ roadmap: post-flip live external audits (Screaming Frog
parity check, Lighthouse CrUX integration); cron-style scheduled
re-curation as the corpus grows; offline-rules expansion to
Organization / WebPage / BreadcrumbList ListItem (flagged by
2.10's web-validator fallback as promotion candidates); GSC + Bing
Webmaster API integration once verification clears; richer
relation typology (CiTO under extended @context) for sites that
want scholarly-grade citation typing.
