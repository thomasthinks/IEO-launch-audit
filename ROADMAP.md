# ROADMAP.md — IEO-launch-audit

What's beyond v1.0. Not a commitment; a holding area for candidates ranked by
"would this catch a class of finding the skill misses today, and is it
portable across consumers."

## v1.1 candidates

### GSC + Bing Webmaster API integration

The skill currently reports IndexNow ping success (check 6) and PSI / CrUX
field-data (check 4), but has no read-back from Google Search Console or
Bing Webmaster Tools for indexing coverage, crawl errors, mobile usability,
or search performance. Adding a `gsc_credentials_path:` + `bing_api_key:`
config block (graceful-degrade when absent, per standing principles) would
let check 7 (sitemap accuracy) cross-verify "submitted" against "indexed"
counts, and check 11 (live-apex audit) flag specific URLs flagged in the
Index Coverage report.

Auth complexity is the open question — GSC requires service-account or OAuth
flow; Bing is API-key. Probably warrants a `references/`-side doc on auth
setup that mirrors the PSI key flow.

### CiTO @context optionality

v0.7 introduced typed citations via the CiTO ontology
(`@context: ["https://schema.org", {"cito": "http://purl.org/spar/cito/"}]`).
Some consumers will want vanilla Schema.org @context for tooling that chokes
on multi-context JSON-LD. A config key like `cito_enabled: false` would let
the skill emit Schema.org-only `citation` arrays + flag in check 2 that
typed-citation richness is reduced.

### `audit-diff --verbose-pass` passthrough

v1.0's `audit_diff.py` collapses PASS rows to one-liner per check by default;
`--verbose-pass` expands them. The `audit.sh` orchestrator doesn't currently
expose this flag — `--verbose-pass` only works when invoking `audit_diff.py`
directly. Wiring it through `audit.sh` is mechanical.

### Narrow Article subtypes in offline rules

Check 2's offline schema rules currently cover 6 broad `Article` subtypes
(`Article`, `NewsArticle`, `BlogPosting`, `TechArticle`, `ScholarlyArticle`,
`SocialMediaPosting`). Long-tail subtypes (`Report`, `AnalysisNewsArticle`,
`OpinionNewsArticle`, `ReviewNewsArticle`, `SatiricalArticle`) fall through
to the v0.6 web-validator fallback when present. The fallback works, but
adding offline rules for the long-tail set is faster, deterministic, and
removes a network round-trip per build.

## v1.2+ candidates

### Scheduled re-curation routines

The skill is currently invoked manually or per-build. For sites already
launched, a `/loop weekly` (or scheduled-routine via Claude Code's
`schedule` skill) would surface drift over time: new dead links from
external rot, sitemap-vs-sitemap discrepancies after silent slug renames,
schema-graph node count divergence from piece count, etc. Probably ships
as a `templates/scheduled-audit.md` skill-side recipe rather than skill
code.

### Real-user CrUX dashboard

v1.0 parses CrUX field-data when PSI returns it, but the skill's output is
a snapshot per run. A consumer with a long enough post-launch tail could
benefit from a `crux-trend.py` helper that appends each run's CrUX
distribution to a local CSV + emits a trend summary. Tradeoff: this drifts
from "audit per build" toward "monitoring layer," which is arguably
out-of-scope. Holding for now.

### Per-piece `wordCount` / `readTime` frontmatter validation

Consumers like `thomasjankowski-site` carry `wordCount` + `readTime` in
piece frontmatter and emit them into JSON-LD. Check 2 currently validates
the JSON-LD shape but not the source-of-truth: does the frontmatter
`wordCount` actually match the rendered piece's word count? Drift here is
the kind of silent error external auditors don't catch (because they only
see the rendered HTML, which is internally consistent).

## Standing principles (gate for what gets in)

Pulled verbatim from `CLAUDE.md` § Standing principles — repeated here
because the roadmap reviews against them:

- **Standalone-runnable.** Every check is invokable on its own.
- **Audit-budget-aware.** New checks add minutes only when they catch a
  class of finding the existing checks can't.
- **Graceful degrade.** No hard-fail on absent config / API keys.
- **Portable / no consumer-specific assumptions.** No hardcoded paths,
  domain names, or `.launch-readiness.yml` schema assumptions beyond
  documented keys.

A candidate that violates any of the four needs a documented justification
in the version's CHANGELOG entry; otherwise it doesn't ship.

## Out-of-scope (declined)

- **Building a hosted dashboard.** The skill is a CLI / Claude-Code-skill
  artifact, not a SaaS surface. If someone wants a dashboard, they wrap
  the JSON output.
- **Crawl-the-whole-site mode.** Screaming Frog and Sitebulb do this well;
  the skill's edge is the synthesis layer (SEO + IEO + GEO best practices)
  + the consumer-repo-side checks (1-10) the crawlers can't see. Doubling
  the SF surface dilutes both edges.
- **Paid-API requirement.** PSI / CrUX / OPR are opt-in; the skill must
  ship a useful audit with zero API keys. Anything that makes a paid key
  required is declined on portability grounds.
