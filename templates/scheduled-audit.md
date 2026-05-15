# Scheduled audit recipe

The audit is invokable on-demand (one-shot pre-launch check or post-flip
hotfix verification), but most consumer repos benefit from running it on
a recurring cadence post-launch. This template covers the four common
ways to schedule it.

The skill itself ships no cron / loop wiring — that's consumer-side
infrastructure. This file documents the patterns that have been
exercised against the canonical consumer.

## What scheduled audits catch

Things that drift silently over time:

- **External-link rot** (check 11 phase D / phase I) — inline links to
  third-party sources go 404 / 500 / DNS-fail. Source repo can't see this.
- **CDN-side trailing-slash drift** (check 11 phase A) — CDN config edits
  introduce single-hop 308 chains on canonical URLs.
- **Sitemap/link-graph drift** (check 11 phase I) — silent slug renames
  leave the sitemap pointing at URLs that no inline link references.
- **CrUX trend regression** (check 4 + `crux-trend.py`) — Core Web Vitals
  drift after a content-heavy hero-image swap, a third-party script
  addition, a font-loading change.
- **Schema-graph node-count drift** (check 2) — emitter regression silently
  drops entities on a subset of pages.
- **Discovery-artifact reachability** (check 11 phase F) — robots.txt /
  llms.txt / sitemap.xml accidentally 404 after a host-config edit.
- **Meta-description duplication** (check 11 phase J) — a templated
  fallback gets activated after a per-page emitter regression.

Things the schedule does NOT catch (still needs human review):

- Content-quality regressions (check 9 is per-piece advisory; corpus-wide
  trends need editorial judgment).
- Wikidata entity-graph drift (check 5 needs operator action).
- Brand-voice / editorial-tic drift (check 9.9 is signal, not ground truth).

## Cadence by use case

| Use case | Cadence | Rationale |
|---|---|---|
| Production content site, low publish frequency | **Weekly** | Catches drift without burning audit budget |
| Production content site, daily publish | **Daily** | New URLs need IndexNow + sitemap reachability verification within 24h |
| Newly-launched site (first 30 days) | **Daily** | Spot CrUX drift, CDN-config regressions, first-week sitemap learnings |
| Established site, no recent edits | **Monthly** | Diff-vs-prior surfaces external drift cheaply |
| Pre-launch verification | **On-demand** | One-shot |
| Post-deploy verification | **On-deploy** | CI hook (see below) |

## Pattern A — `/loop` (Claude Code skill)

Use when you're already in a Claude Code session and want a self-pacing
recurring audit. Best for short-term drift watching during a campaign or
the first 30 days post-launch.

```
/loop 1w bash .claude/skills/IEO-launch-audit/scripts/audit.sh --report-only --diff
```

The `--diff` flag uses the auto-rotated prior report at
`.launch-readiness-report.prev.json` so each loop iteration surfaces
movement vs the previous run.

Stop the loop with `/loop --stop`. Loop history is visible in the Claude
Code session memory.

## Pattern B — `/schedule` (Claude Code remote routine)

Use when you want the audit to run server-side on a cron schedule even
when you're not at the keyboard. Cron expression supports the standard
5-field form.

```
/schedule "0 3 * * 1" bash .claude/skills/IEO-launch-audit/scripts/audit.sh --report-only --diff --output-dir /tmp/ieo-audit
```

Runs at 03:00 UTC every Monday. Output goes to `/tmp/ieo-audit/` since
remote routines don't have direct repo-root write access.

`/schedule list` shows the routine; `/schedule cancel <id>` stops it.

## Pattern C — System crontab

Use when you operate the audit-running host yourself and want
distribution-native scheduling. Add to the operator's crontab:

```cron
# Weekly IEO audit, Monday 03:00 local, diff vs prior, append CrUX trend.
0 3 * * 1 cd /path/to/repo && /usr/bin/env bash .claude/skills/IEO-launch-audit/scripts/audit.sh --report-only --diff && python3 .claude/skills/IEO-launch-audit/scripts/crux-trend.py
```

The `crux-trend.py` step appends one row to
`.launch-readiness-crux-trend.csv` so the operator can see CrUX direction
over time without re-running PSI calls.

For ops-shop integration: redirect the diff output to a Slack webhook or
email pipe. Example with `curl`:

```bash
0 3 * * 1 cd /path/to/repo && bash .../audit.sh --report-only --diff 2>&1 \
  && curl -s -X POST -H 'Content-type: application/json' \
       --data "{\"text\":\"$(head -30 .launch-readiness-diff.md | jq -Rs .)\"}" \
       https://hooks.slack.com/services/<webhook>
```

## Pattern D — GitHub Actions

Use when the audit should gate deployments OR run on a schedule alongside
CI. Drop this in `.github/workflows/ieo-audit.yml`:

```yaml
name: IEO weekly audit
on:
  schedule:
    - cron: "0 3 * * 1"   # Monday 03:00 UTC
  workflow_dispatch:        # manual trigger
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Run audit
        run: |
          bash .claude/skills/IEO-launch-audit/scripts/audit.sh \
            --checks 1-11 --report-only --diff
      - name: Append CrUX trend
        if: env.PAGESPEED_API_KEY != ''
        env:
          PAGESPEED_API_KEY: ${{ secrets.PAGESPEED_API_KEY }}
        run: |
          python3 .claude/skills/IEO-launch-audit/scripts/crux-trend.py
      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: ieo-audit-report
          path: |
            .launch-readiness-report.md
            .launch-readiness-report.json
            .launch-readiness-diff.md
            .launch-readiness-crux-trend.csv
      - name: Fail on regression
        run: |
          # Optional CI gate — fail the run if the diff surfaces any new FAIL.
          if grep -q '^.*FAIL' .launch-readiness-diff.md; then
            echo "Audit regressed; see uploaded reports."
            exit 1
          fi
```

For deploy gating, drop the `schedule` trigger and use `on: pull_request`
or `on: deployment` instead.

## Reading the trend

After a few runs accumulate, `crux-trend.py` is the operator's eye on
direction:

```bash
python3 .claude/skills/IEO-launch-audit/scripts/crux-trend.py --summary-only
```

Output shape:

```
# CrUX trend — .launch-readiness-crux-trend.csv  (last 5 of 12 runs)

  timestamp_utc       | page_lcp_p75/cat | page_cls_p75/cat | page_inp_p75/cat | origin_lcp_p75/cat | …
  ------------------- | ---------------- | ---------------- | ---------------- | ------------------ | …
  2026-05-15T03:00:00 | 1980/FAST        | 0.08/FAST        | 145/FAST         | 2100/FAST          | …
  2026-05-22T03:00:00 | 2030/FAST        | 0.08/FAST        | 152/FAST         | 2150/FAST          | …
  …

## Direction (latest vs prior)
  page   LCP  ↗
  page   CLS  →
  page   INP  →
  origin LCP  ↗
  origin CLS  →
  origin INP  ↗
```

`↗` = p75 rose ≥5% (regressing). `↘` = p75 dropped ≥5% (improving). `→`
= within ±5% noise. `(regress)` / `(improve)` markers indicate category
changes across FAST/AVERAGE/SLOW thresholds.

Trend interpretation belongs to the operator; the helper reports raw
direction, not "your site got worse."

## Stability before scheduling

A scheduled audit that catches false positives every run becomes noise
the operator stops reading. Before committing a scheduled run:

1. Run the audit manually 2-3 times against the live origin. Verify each
   finding either PASSes or is accepted-as-current with a documented
   reason.
2. Tune editorial-threshold keys (`title_length_min/max`,
   `description_length_min/max`) for your voice if defaults flag too many
   editorial-intentional deviations.
3. Configure opt-in integrations explicitly (`pagespeed_api_key`,
   `brave_api_key`, `cloudflare_zone_id`) so checks run consistently
   across scheduled invocations rather than degrading to MV randomly.
4. THEN add the cron/loop/schedule wrapper.

The skill is designed to stabilise at zero false-positives; if your
scheduled audit keeps firing on noise, the schedule isn't broken — the
config is.
