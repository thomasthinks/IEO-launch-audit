#!/usr/bin/env python3
"""
Check 03 — AI-bot directives (robots.txt + llms.txt + llms-full.txt).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact, load_config, time_check,
)


def _resolve_cf_token(repo: Path, config: dict) -> str | None:
    """Find a Cloudflare API token, in priority order:

    1. CLOUDFLARE_API_TOKEN env var (explicit, no decryption needed).
    2. SOPS-decrypted secrets file at `cloudflare_secret_path` in config
       (default: `secrets/cf-api.enc.yaml`). Requires `sops` on PATH.

    Returns None if no token is reachable. Caller treats None as
    "probe-not-configured" and leaves the existing finding behaviour
    untouched.
    """
    tok = os.environ.get("CLOUDFLARE_API_TOKEN")
    if tok:
        return tok.strip()
    secret_rel = config.get("cloudflare_secret_path", "secrets/cf-api.enc.yaml")
    secret_path = repo / secret_rel
    if not secret_path.exists():
        return None
    try:
        out = subprocess.run(
            ["sops", "-d", str(secret_path)],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        m = re.match(r"^\s*CLOUDFLARE_API_TOKEN\s*:\s*(.+?)\s*$", line)
        if m:
            val = m.group(1).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            return val
    return None


def _probe_cf_bytespider_rule(zone_id: str, token: str) -> tuple[str, str]:
    """Query the zone's http_request_firewall_custom entrypoint ruleset
    and check for an enabled block-rule whose expression mentions
    Bytespider (case-insensitive).

    Returns (status, detail) where status is one of:
      * "verified" — enabled block-rule referencing bytespider found
      * "no_rule" — API reachable but no matching enabled rule
      * "api_error" — API unreachable or unexpected shape

    Keep this stdlib-only; no `requests` / `cloudflare` SDK dependency.
    """
    url = (
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}"
        "/rulesets/phases/http_request_firewall_custom/entrypoint"
    )
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return ("api_error", f"{type(e).__name__}: {e}")
    if not data.get("success"):
        return ("api_error", f"CF API success=false: {data.get('errors')}")
    rules = (data.get("result") or {}).get("rules") or []
    for r in rules:
        if r.get("action") != "block":
            continue
        if r.get("enabled") is False:
            continue
        expr = (r.get("expression") or "").lower()
        if "bytespider" in expr:
            return ("verified", f"rule id={r.get('id', '?')} expr={r.get('expression')}")
    return ("no_rule", f"{len(rules)} rule(s) inspected; none block Bytespider")


CITATION_CLASS_BOTS = [
    "OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User",
    "PerplexityBot", "Perplexity-User", "Bingbot", "Applebot",
    "DuckAssistBot", "MistralAI-User", "GoogleOther", "Google-NotebookLM",
    "Amazonbot", "Meta-ExternalAgent",
    # v1.2.1 additions:
    # - Google-Agent: user-triggered fetcher for Gemini Agent + AI Mode,
    #   added to Google's official crawler list on 2026-03-20. Citation-
    #   class because it fetches at user prompt, not for training.
    # - Meta-ExternalFetcher: user-prompted fetches from Meta AI products;
    #   complements Meta-ExternalAgent (the crawler). Documented in the
    #   ai-robots-txt project.
    "Google-Agent", "Meta-ExternalFetcher",
]
TRAINING_CLASS_BOTS = [
    "GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Applebot-Extended",
    # v1.2.1 addition: Cohere's training-class crawler. Documented in
    # the ai-robots-txt project; previously not enumerated in the skill.
    "cohere-training-data-crawler",
]

# v1.2.1 — undocumented-by-design crawlers that publish no stable
# user agent and spoof browser fingerprints (per Cloudflare reporting,
# 2025-2026). Flagged as a known-gap INFO so consumers know UA-based
# policy alone is insufficient; bot-management at the WAF layer
# (JA4 / JA3 TLS fingerprinting, behavioural heuristics) is the
# practical defense. The audit cannot test for these via robots.txt.
KNOWN_UNDOCUMENTED_AI_CRAWLERS = ["Grok (xAI)", "DeepSeek"]


def parse_robots_txt(content: str) -> dict[str, list[str]]:
    """Parse robots.txt into {user-agent: [Allow/Disallow lines]}."""
    out: dict[str, list[str]] = {}
    current = "*"
    for line in content.splitlines():
        stripped = line.split("#")[0].strip()
        if not stripped:
            continue
        m = re.match(r"^(User-agent|Allow|Disallow|Sitemap)\s*:\s*(.*)$", stripped, re.IGNORECASE)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "user-agent":
            current = val
            out.setdefault(current, [])
        elif key in ("allow", "disallow"):
            out.setdefault(current, []).append(f"{key.title()}: {val}")
        elif key == "sitemap":
            out.setdefault("__sitemaps__", []).append(val)
    return out


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="03-ai-bot-directives")

    robots_path = find_artifact(repo, config, "robots_txt", [
        "robots.txt", "public/robots.txt", "dist/public/robots.txt",
        "static/robots.txt", "out/robots.txt", "_site/robots.txt",
    ])
    if not robots_path:
        result.findings.append(Finding(
            id="3.1.missing", severity="FAIL",
            title="robots.txt not found",
            fix_safety="safe",
            fix_template="templates/robots.txt",
            fix_action="Create robots.txt from template; reference sitemap.",
        ))
        return result

    content = robots_path.read_text(encoding="utf-8")
    rules = parse_robots_txt(content)

    # 3.1 — Sitemap directive
    sitemaps = rules.get("__sitemaps__", [])
    if sitemaps:
        result.findings.append(Finding(
            id="3.1.sitemap_directive", severity="PASS",
            title=f"robots.txt references {len(sitemaps)} sitemap(s)",
            current=sitemaps,
        ))
    else:
        result.findings.append(Finding(
            id="3.1.sitemap_directive", severity="WARN",
            title="robots.txt has no Sitemap: directive",
            fix_safety="safe",
            fix_action="Add 'Sitemap: <canonical_origin>/sitemap.xml' to robots.txt.",
        ))

    addressed = set(rules.keys()) - {"__sitemaps__", "*"}
    addressed_lower = {a.lower() for a in addressed}

    # 3.2 — Citation-class coverage
    missing_citation = [b for b in CITATION_CLASS_BOTS if b.lower() not in addressed_lower]
    # Wildcard implicit allow counts as covered IF no Disallow: / for *
    wildcard_rules = rules.get("*", [])
    wildcard_blocks_all = any(r == "Disallow: /" for r in wildcard_rules)
    if not wildcard_blocks_all and missing_citation:
        # Implicit allow via wildcard. Soften severity.
        result.findings.append(Finding(
            id="3.2.citation_class_implicit", severity="INFO",
            title=f"{len(missing_citation)} citation-class bots rely on wildcard Allow (implicit)",
            current=missing_citation,
            fix_safety="safe",
            fix_action="Add explicit Allow blocks per bot to make policy auditable. See templates/robots.txt.",
        ))
    elif wildcard_blocks_all and missing_citation:
        result.findings.append(Finding(
            id="3.2.citation_class_blocked", severity="FAIL",
            title=f"{len(missing_citation)} citation-class bots blocked by wildcard Disallow",
            current=missing_citation,
            fix_safety="safe",
            fix_action="Add explicit Allow rules for citation-class bots.",
        ))
    else:
        result.findings.append(Finding(
            id="3.2.citation_class", severity="PASS",
            title=f"All {len(CITATION_CLASS_BOTS)} citation-class bots addressed (explicit)",
        ))

    # 3.3 — Training-class policy explicitness
    missing_training = [b for b in TRAINING_CLASS_BOTS if b.lower() not in addressed_lower]
    if missing_training:
        result.findings.append(Finding(
            id="3.3.training_class", severity="WARN",
            title=f"{len(missing_training)} training-class bots have no explicit policy",
            current=missing_training,
            fix_safety="safe",
            fix_action="Add explicit Allow or Disallow per bot. Document policy decision.",
        ))
    else:
        result.findings.append(Finding(
            id="3.3.training_class", severity="PASS",
            title=f"All {len(TRAINING_CLASS_BOTS)} training-class bots have explicit policy",
        ))

    # 3.4 — Bytespider
    #
    # Bytespider ignores robots.txt; the robots.txt entry is a signal only.
    # If config carries `cloudflare_zone_id`, probe the CF Custom Rules
    # ruleset to verify a real edge-block is in place; on hit, downgrade
    # the WARN to PASS. Probe is optional — when no token is reachable,
    # behaviour is unchanged from prior versions.
    cf_zone_id = config.get("cloudflare_zone_id")
    cf_probe_status: str | None = None
    cf_probe_detail: str = ""
    if cf_zone_id:
        cf_token = _resolve_cf_token(repo, config)
        if cf_token:
            cf_probe_status, cf_probe_detail = _probe_cf_bytespider_rule(cf_zone_id, cf_token)

    if "bytespider" in addressed_lower:
        bytespider_rules = next(v for k, v in rules.items() if k.lower() == "bytespider")
        if any("Disallow: /" in r for r in bytespider_rules):
            if cf_probe_status == "verified":
                result.findings.append(Finding(
                    id="3.4.bytespider", severity="PASS",
                    title="Bytespider Disallowed in robots.txt + Cloudflare WAF block-rule verified via API",
                    current=cf_probe_detail,
                ))
            elif cf_probe_status == "no_rule":
                result.findings.append(Finding(
                    id="3.4.bytespider", severity="WARN",
                    title="Bytespider Disallowed in robots.txt but CF API found no edge block-rule",
                    current=cf_probe_detail,
                    fix_safety="manual",
                    fix_action="Add a Cloudflare WAF Custom Rule: action=block, expression "
                               "contains 'bytespider' (lower(http.user_agent)).",
                ))
            elif cf_probe_status == "api_error":
                result.findings.append(Finding(
                    id="3.4.bytespider", severity="WARN",
                    title="Bytespider Disallowed in robots.txt; CF WAF probe failed (unverifiable)",
                    current=cf_probe_detail,
                    fix_safety="manual",
                    fix_action="Inspect CF API token scope (Zone:Read + Zone WAF:Read) "
                               "or set CLOUDFLARE_API_TOKEN; otherwise verify edge block manually.",
                ))
            else:
                # No probe configured — preserve prior behaviour.
                result.findings.append(Finding(
                    id="3.4.bytespider", severity="WARN",
                    title="Bytespider Disallowed in robots.txt — but Bytespider ignores robots.txt",
                    fix_safety="manual",
                    fix_action="Add edge/WAF block (Vercel firewall, Cloudflare WAF, nginx rule). "
                               "See templates/vercel-headers.json.example for example. "
                               "Set `cloudflare_zone_id` in .launch-readiness.yml to auto-verify a CF block-rule.",
                ))
        else:
            result.findings.append(Finding(
                id="3.4.bytespider", severity="INFO",
                title="Bytespider addressed but not Disallowed; verify edge policy if you want to block.",
            ))
    else:
        result.findings.append(Finding(
            id="3.4.bytespider", severity="WARN",
            title="Bytespider not addressed in robots.txt or edge WAF",
            fix_safety="safe",
            fix_action="Add Bytespider Disallow in robots.txt + edge WAF rule.",
        ))

    # 3.5 — llms.txt presence (v1.2.1: severity downgraded WARN → INFO).
    # 2026 disconfirmation: ~300K-domain SE Ranking analysis (Nov 2025)
    # found zero statistically-significant correlation between llms.txt
    # presence and AI citation rate. AEO Engine's 90-day study found
    # 0.1% of AI-bot requests target llms.txt. No major LLM provider
    # (OpenAI / Anthropic / Google / Meta / Mistral) commits to reading
    # it in production as of Q1 2026. Primary value remaining: dev-tool
    # context for Cursor / Claude Code / Codex (AGENTS.md serves that
    # role explicitly now). Cheap to ship + harmless; not a citation
    # lever. See SE Ranking + AEO Engine + AEO Press sources.
    llms_path = find_artifact(repo, config, "llms_txt", [
        "llms.txt", "public/llms.txt", "dist/public/llms.txt",
        "static/llms.txt", "out/llms.txt",
    ])
    if llms_path:
        result.findings.append(Finding(
            id="3.5.llms_txt", severity="PASS",
            title="llms.txt present",
            current=str(llms_path.relative_to(repo)),
            notes=(
                "Cheap signal of editorial intent; no measured AI-citation "
                "lift per 2026 large-N studies. Primary consumers are "
                "developer tools, not search/answer engines."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="3.5.llms_txt", severity="INFO",
            title="llms.txt missing (cheap-but-not-load-bearing in 2026)",
            fix_safety="safe",
            fix_template="templates/llms.txt",
            fix_action=(
                "Optional: emit llms.txt from template. 2026 disconfirmation: "
                "SE Ranking 300K-domain study + AEO Engine 90-day bot-log "
                "analysis show no measurable AI-citation lift. Major LLM "
                "providers don't fetch it in production. Cheap and harmless "
                "to ship; do not treat as a citation lever."
            ),
        ))

    # 3.5b — Known undocumented AI crawlers (v1.2.1 INFO).
    # Grok (xAI) and DeepSeek publish no stable crawler user-agents and
    # spoof browser fingerprints per Cloudflare's 2025-2026 reporting.
    # robots.txt enforcement is impossible against them. Flagged here so
    # consumers know UA-based policy alone leaves a gap; bot management
    # at the WAF tier (JA4 TLS fingerprinting / behavioural heuristics)
    # is the practical defense.
    result.findings.append(Finding(
        id="3.5b.undocumented_crawlers", severity="INFO",
        title=(
            f"{len(KNOWN_UNDOCUMENTED_AI_CRAWLERS)} AI crawler(s) publish no "
            "documented user-agent and cannot be UA-blocked"
        ),
        current=KNOWN_UNDOCUMENTED_AI_CRAWLERS,
        fix_safety="manual",
        fix_action=(
            "If blocking these matters, configure WAF-tier defenses "
            "(Cloudflare bot management, JA4 fingerprinting, Vercel BotID). "
            "robots.txt + UA-based audits cannot reach them by design."
        ),
        notes=(
            "Cloudflare documented Grok spoofing Safari/Chrome UAs with "
            "rotating IPs. DeepSeek publishes no crawler docs. Expect this "
            "list to grow as more AI providers ship crawlers without "
            "self-identification."
        ),
    ))

    # 3.6 — llms-full.txt presence
    llms_full_path = find_artifact(repo, config, "llms_full_txt", [
        "llms-full.txt", "public/llms-full.txt", "dist/public/llms-full.txt",
        "static/llms-full.txt", "out/llms-full.txt",
    ])
    if llms_full_path:
        result.findings.append(Finding(
            id="3.6.llms_full_txt", severity="PASS",
            title="llms-full.txt present",
        ))
    else:
        result.findings.append(Finding(
            id="3.6.llms_full_txt", severity="INFO",
            title="llms-full.txt missing (optional; emerging standard)",
            fix_safety="safe",
            fix_template="templates/llms-full.txt",
            fix_action="Optional: emit llms-full.txt with plain-text dump of anchor pieces.",
        ))

    result.summary = (
        f"robots.txt: {len(CITATION_CLASS_BOTS) - len(missing_citation)}/{len(CITATION_CLASS_BOTS)} citation-class addressed, "
        f"{len(TRAINING_CLASS_BOTS) - len(missing_training)}/{len(TRAINING_CLASS_BOTS)} training-class explicit. "
        f"llms.txt {'present' if llms_path else 'missing'}. "
        f"llms-full.txt {'present' if llms_full_path else 'missing'}."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("03-ai-bot-directives")
    args = parser.parse_args()
    emit(run(args))
