# CLAUDE.md — IEO-launch-audit

Agent orientation for any Claude instance working in this repo.

## What this repo is

A standalone Claude Code skill: pre-launch + post-launch SEO / IEO / GEO audit
for a static or SSG site. Eleven audit categories; ~5 min run against the
source repo (checks 1-10) + ~2-3 min extra against a live apex (check 11,
opt-in). See `README.md` for the full capability surface and `SKILL.md` for
the skill manifest (frontmatter + retrieval aliases + bash/path trigger
patterns).

## Origin

Extracted from `thomasjankowski-site` on 2026-05-15 via `git filter-repo`
(commit history preserved for `.claude/skills/IEO-launch-audit/**`). The skill
hit v1.0.0 (production-ready) in a single overnight arc — v0.7 → v0.8 → v0.9
→ v1.0 across ~10 hours, run against a real live origin (thomasjankowski.com
post-apex-flip) at every version bump. See `CHANGELOG.md` for the per-release
detail; the v0.7 → v1.0 arc is the load-bearing context for understanding the
skill's design choices.

Authoritative source for the broader build context is the
`thomasjankowski-site` repo (private). Cross-references that may be useful:

- `docs/decisions/0009-deploy-platform.md` — why Cloudflare Pages, why edge,
  what the audit assumes about the host.
- `docs/editorial/launch-plan.md` — F-1 apex flip, F-2 external-audit fix
  cycle. Context for what check 11 was built to catch.
- `.launch-readiness-report.md` (regenerated each run) — example audit output
  in the consumer repo shape.

## Dev workflow

- Edit files in `~/projects/IEO-launch-audit/` directly. The symlink at
  `~/.claude/skills/IEO-launch-audit` → this directory means edits propagate
  to global skill discovery immediately. No copy step.
- Test against any consumer repo with a `.launch-readiness.yml`. The
  `thomasjankowski-site` repo is the canonical reference consumer.
- Stdlib-Python by default. Optional integrations (PageSpeed Insights,
  Cloudflare WAF, OPR API) graceful-degrade when their config is absent —
  this is a hard rule, not a courtesy. The skill must always run, even with
  no API keys.

## Release workflow

1. Add a `CHANGELOG.md` entry under a new `## [X.Y.Z] — YYYY-MM-DD` heading.
   Follow the existing pattern: **Added** / **Changed** / **Fixed** sections,
   then **Audit-state shift** if a consumer-repo run shifted findings, then
   **Migration notes** for breaking changes.
2. Bump `metadata.version` in `SKILL.md` frontmatter.
3. Bump the **Status:** line in `README.md` if it leads with a version.
4. Commit. Follow Conventional Commits: `feat(skill):`, `fix(skill):`,
   `chore(skill):`, `docs(skill):`. Subject ≤100 chars, body unlimited.
5. Push. The skill is public on GitHub
   (`github.com/thomasthinks/IEO-launch-audit`); push lands publicly.
6. Tag the release if it's a notable milestone:
   `git tag -a v1.0.0 -m "..."` then `git push --tags`.

## Standing principles

Pulled from how v0.5 → v1.0 actually evolved. Each new check should respect
these unless there's a documented reason not to:

- **Standalone-runnable.** Every check is invokable on its own
  (`bash audit.sh --checks N`). No hard ordering dependencies.
- **Audit-budget-aware.** The skill aspires to run in ~5 minutes for
  checks 1-10. New checks add minutes only when they buy a class of finding
  the existing checks can't catch.
- **Graceful degrade.** When a config key, API key, or external endpoint is
  missing, the check emits an `MV` (missing-value) or `INFO` finding and
  continues. Never fail-hard on absent config; never crash the run.
- **Portable / no consumer-specific assumptions.** Nothing hardcoded for
  `thomasjankowski-site`. Consumer-specific state lives in
  `.launch-readiness.yml`; the skill reads keys, never the inverse.

## What not to do

- Don't import code from `thomasjankowski-site`. The cross-cut already
  happened during the extraction; new dependencies need to be in this repo
  or stdlib.
- Don't add paid-API integrations as defaults. PSI is opt-in; OPR is
  opt-in; CF WAF probe is opt-in. The skill's "no paid API required" stance
  is load-bearing for the README's positioning.
- Don't relax editorial-threshold defaults to match a single consumer's
  preferences. Defaults track widely-cited 2026 best practices (Google
  Search Central, web.dev/vitals, schema.org docs); per-consumer tuning
  belongs in `.launch-readiness.yml` keys.

## Next-up

See `ROADMAP.md` for v1.1 / v1.2+ candidates and the standing principles
that gate what gets in.
