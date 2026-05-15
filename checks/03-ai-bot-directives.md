# Check 03 — AI-bot directives (robots.txt + llms.txt + llms-full.txt)

## Why this matters

Two parallel crawler classes matter in 2026:

1. **Citation-class crawlers** (PerplexityBot, OAI-SearchBot, Claude-SearchBot,
   Bingbot, Applebot, DuckAssistBot) — these crawl in response to user
   queries and produce attributed citations. Allowing them is the floor for
   appearing in AI-powered search results.

2. **Training-class crawlers** (GPTBot, ClaudeBot, Google-Extended, CCBot,
   Meta-ExternalAgent, Applebot-Extended) — these crawl for training-set
   inclusion in foundation models. Allowing them puts the content in the
   parametric knowledge of future LLMs, which is the slower, broader,
   more durable citation path.

For an editorial / essay site with no paywall, the consensus is to allow
both classes. For sites with proprietary data or first-publication revenue,
the calculus differs.

A separate concern: **Bytespider (ByteDance/TikTok)** ignores robots.txt
and crawls aggressively. It is not citation-class. Block at the edge / WAF
rather than relying on robots.txt.

The `llms.txt` convention (https://llmstxt.org) is read aspirationally —
near-zero direct LLM crawler consumption in 2026 — but does feed
developer-side agents (Cursor, Continue, Aider, Cline). Cheap to ship;
signals editorial intent. The companion `llms-full.txt` (full-text dump for
ingestion) is shipped by Anthropic, Vercel, LangGraph.

**Cited sources:** llmstxt.org spec; Anthropic three-bot framework (ALM
Corp May 2026); OpenAI crawler documentation; Google Search docs on
Google-Extended; W3C robots.txt spec.

## What's checked

### 3.1 — robots.txt presence and parseability

| Assertion | Pass | Fail |
|---|---|---|
| `robots.txt` exists at site root | yes | no |
| Parses as valid robots.txt | yes | malformed |
| Contains a `Sitemap:` directive | yes | no |

### 3.2 — Citation-class bot coverage

robots.txt should explicitly Allow (or implicitly allow via no Disallow)
these user-agents:

- `OAI-SearchBot` (OpenAI ChatGPT Search citations)
- `ChatGPT-User` (OpenAI user-triggered fetch on /browse)
- `Claude-SearchBot` (Anthropic Claude search index)
- `Claude-User` (Anthropic user-triggered)
- `PerplexityBot` (Perplexity index)
- `Perplexity-User` (Perplexity user fetch)
- `Bingbot` (Bing index, used by Copilot)
- `Applebot` (Apple Spotlight / Siri)
- `DuckAssistBot` (DuckDuckGo AI search)
- `MistralAI-User` (Mistral chat)
- `GoogleOther` (Google R&D crawls)
- `Google-NotebookLM` (Google NotebookLM)
- `Amazonbot` (Amazon Alexa / Rufus)
- `Meta-ExternalAgent` (Meta AI products)

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| All 14 citation-class user-agents have explicit Allow OR site has no Disallow | yes | 1-3 missing | 4+ missing |

### 3.3 — Training-class bot policy

robots.txt should explicitly state policy on each training-class
user-agent. "Explicit" is the gate, not "Allow" or "Disallow" — both are
valid policies, but the file should make the choice visible.

Training-class user-agents to address:
- `GPTBot` (OpenAI training)
- `ClaudeBot` (Anthropic training)
- `Google-Extended` (Google training opt-out flag — note: not a true bot, a signaling header)
- `CCBot` (Common Crawl, feeds ~all training sets)
- `Applebot-Extended` (Apple training)
- `Meta-ExternalAgent` (Meta training)

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| All 6 training-class user-agents have explicit Allow or Disallow | yes | 1-2 implicit | 3+ implicit |

### 3.4 — Bytespider posture

Bytespider ignores robots.txt. The robots.txt entry is a signal but not
enforcement.

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Bytespider mentioned in robots.txt (Allow or Disallow) | yes | — | no |
| If Disallow in robots.txt: edge/WAF rule also exists | yes | robots.txt only | no |

### 3.5 — llms.txt presence and shape

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| `llms.txt` exists at site root | yes | — | no |
| Contains a top-level title (`# Site Name`) | yes | no | — |
| Contains pillar/section headers (`## AI`, `## Travel`, etc.) | yes | no | — |
| Lists key URLs (pillar hubs, RSS, sitemap, ADR index if applicable) | yes | partial | no |

### 3.6 — llms-full.txt presence

`llms-full.txt` (full-text dump for LLM ingestion) sits alongside
`llms.txt`. Optional but increasingly standard.

| Assertion | Pass | Warn |
|---|---|---|
| `llms-full.txt` exists | yes | no |
| Contains plain-text versions of pillar/anchor pieces | yes | partial |

### 3.7 — Sitemap reference

robots.txt should reference all sitemap files.

| Assertion | Pass | Fail |
|---|---|---|
| robots.txt `Sitemap:` directive present | yes | no |
| References `sitemap.xml` | yes | no |
| References `image-sitemap.xml` (if exists) | yes | no |
| References `rss.xml` (informational; not standard but useful) | yes | — |

## How to fix

### Fix 3.1 — robots.txt baseline

Template at `templates/robots.txt`. Minimal:

```
# robots.txt
# Documented per IEO-launch-audit (check 03)

User-agent: *
Allow: /

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/image-sitemap.xml

# --- Citation-class bots (always allow for max LLM exposure) ---
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: Claude-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Perplexity-User
Allow: /

User-agent: Bingbot
Allow: /

User-agent: Applebot
Allow: /

User-agent: DuckAssistBot
Allow: /

User-agent: MistralAI-User
Allow: /

User-agent: GoogleOther
Allow: /

User-agent: Google-NotebookLM
Allow: /

User-agent: Amazonbot
Allow: /

User-agent: Meta-ExternalAgent
Allow: /

# --- Training-class bots (operator policy decision; default: allow for editorial / no-paywall sites) ---
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

User-agent: Applebot-Extended
Allow: /

# --- Bytespider: block at edge/WAF instead; robots.txt entry is a signal only ---
User-agent: Bytespider
Disallow: /
```

**Auto-fix safety: safe** (template-driven; preserves existing custom
rules if present).

### Fix 3.2 — Bytespider edge/WAF rule

For Vercel: use `vercel:vercel-firewall` patterns. Example `vercel.json`
rule:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "firewall": {
    "rules": [
      {
        "name": "Block Bytespider",
        "conditions": [
          {"type": "header", "key": "user-agent", "op": "ire", "value": "bytespider"}
        ],
        "action": {"mitigate": {"action": "deny"}}
      }
    ]
  }
}
```

For Cloudflare: WAF custom rule matching `User-Agent: Bytespider`, action
block.

For nginx: `if ($http_user_agent ~* "bytespider") { return 403; }`.

**Auto-fix safety: manual** (edge config varies by host; operator
applies).

### Fix 3.3 — llms.txt template

Template at `templates/llms.txt`. Structure:

```markdown
# Site Name

> One-paragraph site summary. What's here, who's writing, what pillars.

## AI

- [Title 1](https://example.com/writing/slug-1): One-line description.
- [Title 2](https://example.com/writing/slug-2): One-line description.

## Travel

- ...

## Healthcare

- ...

## Reference

- [About](https://example.com/about)
- [Writing index](https://example.com/writing)
- [RSS](https://example.com/rss.xml)
- [Sitemap](https://example.com/sitemap.xml)
```

**Auto-fix safety: safe** (template-driven; derives from existing pillar
+ piece data).

### Fix 3.4 — llms-full.txt template

Template at `templates/llms-full.txt`. Each entry:

```
# Title 1

URL: https://example.com/writing/slug-1
Author: Author Name
Date: 2024-01-08
Pillar: AI

<full body prose, plain text>

---

# Title 2

...
```

Limit to anchor/pillar pieces, not the full 250-piece catalog (too large
for most LLM-ingestion windows).

**Auto-fix safety: safe** (derives from existing piece bodies + selection
heuristic: signature + pillar pieces only).

## Failure ratings

- **FAIL (must fix before flip):** robots.txt missing, no Sitemap directive,
  3+ citation-class bots not addressed, training-class policy unstated.
- **WARN (should fix before flip):** llms.txt missing, llms-full.txt missing,
  Bytespider not addressed.
- **PASS:** all assertions hold.

## Cited research

- [LLMs.txt spec (llmstxt.org)](https://llmstxt.org/)
- [The AI User-Agent Landscape in 2026](https://nohacks.co/blog/ai-user-agents-landscape-2026)
- [ai-robots-txt project](https://github.com/ai-robots-txt/ai.robots.txt/blob/main/robots.txt)
- [Anthropic three-bot framework](https://almcorp.com/blog/anthropic-claude-bots-robots-txt-strategy/)
- [Anthropic clarifies Claude bots](https://searchengineland.com/anthropic-claude-bots-470171)
- [OpenAI crawlers overview](https://developers.openai.com/api/docs/bots)
- [GPTBot vs OAI-SearchBot vs ChatGPT-User](https://www.amicited.com/blog/gptbot-vs-oai-searchbot/)
- [LLMs.txt: Why AI Crawlers Ignore It (audit)](https://www.longato.ch/llms-recommendation-2025-august/)
- [llms.txt Explained (May 2026)](https://codersera.com/blog/llms-txt-complete-guide-2026/)

## Implementation notes

The script `scripts/check-ai-bots.py`:
1. Parses robots.txt and inventories which user-agents have Allow/Disallow rules
2. Diffs against the canonical 14-citation + 6-training list
3. Reads llms.txt and llms-full.txt (if present)
4. Reports gaps with concrete fix snippets

The script does NOT verify that the edge/WAF rule for Bytespider is
actually in place — that requires runtime testing (curl with Bytespider
user-agent header against the live origin). That check moves to a
post-flip verification.

### Optional: Cloudflare WAF probe (3.4)

When `cloudflare_zone_id` is set in `.launch-readiness.yml` AND a CF API
token is reachable (env `CLOUDFLARE_API_TOKEN` OR SOPS-decryptable file
at `cloudflare_secret_path`, default `secrets/cf-api.enc.yaml`), check
3.4 queries:

```
GET https://api.cloudflare.com/client/v4/zones/<zone_id>/rulesets/phases/http_request_firewall_custom/entrypoint
Authorization: Bearer <token>
```

and verifies an enabled rule with `action: block` whose `expression`
contains `bytespider` (case-insensitive). On verify the WARN downgrades
to PASS. The probe is optional and stdlib-only (urllib + subprocess);
when neither token nor zone is configured the prior behaviour is
unchanged. Required token scope: Zone:Read + Zone WAF:Read.
