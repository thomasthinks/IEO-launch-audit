# ROADMAP.md — IEO-launch-audit

What's beyond v1.0. Not a commitment; a holding area for candidates ranked by
"would this catch a class of finding the skill misses today, and is it
portable across consumers."

## v1.3+ candidates

### GSC live-API integration (service-account JWT or 3-legged OAuth)

v1.2 shipped the GSC snapshot-reader path (operator exports Index Coverage
JSON; audit reads it). The trade is operator-side staleness — re-export
periodically. v1.3 would close that loop with live GSC API integration:
service-account credentials → JWT signed with RSA-SHA256 → OAuth token →
`searchconsole.googleapis.com/v1/sites/<site>/searchAnalytics/query` and
`v1/urlInspection/index:inspect`.

Auth complexity is the open question. RSA-SHA256 signing isn't in Python's
stdlib (`hashlib` has the hash, but no RSA private-key signing). Two paths:
- **Optional dependency on `cryptography`** — clean code, but breaks the
  stdlib-only stance.
- **Shell out to `openssl rsa`** — keeps stdlib-only at the cost of a new
  binary dependency (openssl is near-universal on Linux/Mac; less reliable
  on Windows but the rest of the skill assumes Unix-ish env).

Decision deferred to when a consumer pushes for it. Until then, the
snapshot-reader path (v1.2) is the working answer.

### Real-user CrUX dashboard / longer-trend analysis

v1.2 shipped `crux-trend.py` (append-per-run CSV + direction summary). The
next layer would be a "show me the last N runs as ASCII line charts" or
"alert when category regresses 2 runs in a row" feature. Tradeoff: this
drifts from "audit per build" toward "monitoring product," which is
arguably out-of-scope. Holding for now; v1.2's CSV is the substrate.

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
- **Regulatory-compliance auditing (EU AI Act, CCPA, DSA, etc.).** Different
  audit class from SEO/IEO/GEO — compliance is lawyer territory, not
  crawler territory. EU AI Act Article 50 (the most-asked-about 2026
  surface) imposes machine-readable marking on AI *providers* (model labs)
  and visible disclosure on *deployers* publishing AI content on matters of
  public interest, with an editorial-control exemption that covers most
  human-edited sites. Enforcement priority is providers + large platforms,
  not individual essay/blog sites. Out of scope; consult counsel.
