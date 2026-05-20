#!/usr/bin/env python3
"""
Check 11 — Live-apex audit.

Hits the running production origin (not just the local dist/) to catch
issues the static-config audit cannot see: CDN-side trailing-slash
redirects, per-page meta drift, JSON-LD that diverges between source
and rendered HTML, inline links that point at slugs which no longer
resolve at the apex, and missing discovery artifacts on the live host.

Origin priority:
  1. --apex CLI flag
  2. live_probe_origin in .launch-readiness.yml
  3. canonical_origin in .launch-readiness.yml

If no origin can be resolved the check returns NOT_APPLICABLE.

Twelve phases (A-J default; K + L opt-in):
  A. Sitemap reachability sweep (HEAD every URL; flag non-2xx / 308 drift).
  B. JSON-LD audit on home + about + N sampled pieces (parse / present /
     type-baseline). Article subtypes (NewsArticle, BlogPosting,
     ScholarlyArticle, TechArticle, Report) satisfy the Article baseline
     per Schema.org hierarchy.
  C. Per-page meta audit (title / description / canonical / og:image /
     no rogue noindex).
  D. Inline-link audit on sample pieces — every internal href resolves
     (200 or 308).
  E. Security-header consistency across home + a piece + about.
  F. Discovery artifacts present (robots.txt, llms.txt, sitemap.xml,
     image-sitemap.xml, IndexNow keyfile when configured).
  G. Title + heading + meta-description hygiene (length ranges,
     H1 presence + uniqueness) — Screaming-Frog parity.
  H. Redirect-chain hygiene on sampled internal links (FAIL if >1 hop;
     WARN if exactly 1 hop).
  I. Orphan-page + un-sitemapped-link detection (sitemap vs internal-link
     graph reconciliation across home + about + sampled pieces).
  J. Meta-description duplicate detection across sampled pages.
  K. Brave Search indexability probe (opt-in via `brave_api_key`).
     Anthropic Claude.ai web-search routes through Brave; visibility is
     the practical Claude-citation eligibility lever.
  L. Multi-UA crawler probe (opt-in via `multi_ua_probe: true`, v1.5.1).
     Fetches apex as GPTBot / OAI-SearchBot / ClaudeBot / Claude-SearchBot /
     PerplexityBot / Google-Extended; compares response status + body
     size vs baseline browser UA. Catches CDN-layer AI-bot blocks
     invisible to source-side audits (Cloudflare default-block, AWS WAF,
     etc.).

Phases G-J reuse the existing page + link samples (no extra apex fetches).
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 "
    "IEO-launch-audit/live-apex"
)

# v1.5.1 — phase L multi-UA crawler probe. Issued as the canonical UA
# strings each engine publishes, verbatim. Source: each engine's first-
# party bot docs (developers.openai.com/api/docs/bots,
# support.claude.com/en/articles/8896518,
# docs.perplexity.ai/docs/resources/perplexity-crawlers,
# developers.google.com/search/docs/crawling-indexing/google-common-crawlers).
AI_BOT_UAS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.0; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-SearchBot": "Mozilla/5.0 (compatible; Claude-SearchBot/1.0; +https://www.anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot.html",
    "Google-Extended": "Google-Extended",
}

# Schema.org Article + subtypes that satisfy the per-piece "carries Article
# JSON-LD" baseline. Per Schema.org: NewsArticle, BlogPosting,
# ScholarlyArticle, TechArticle, Report all inherit from Article and are
# valid for an essay/post page.
ARTICLE_TYPES = {
    "Article", "NewsArticle", "BlogPosting",
    "ScholarlyArticle", "TechArticle", "Report",
    "AdvertiserContentArticle", "OpinionNewsArticle",
    "SatiricalArticle", "BackgroundNewsArticle",
    "AnalysisNewsArticle", "AskPublicNewsArticle",
    "ReportageNewsArticle", "ReviewNewsArticle",
    "SocialMediaPosting", "DiscussionForumPosting",
}

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

DEFAULT_PIECE_SAMPLE = 18
DEFAULT_LINK_SAMPLE = 5
# Title-tag display range (Google SERP truncation):
#   <30 chars = under-padded; >65 chars = truncated in mobile SERP.
# Overridable via .launch-readiness.yml `title_length_min` /
# `title_length_max` for sites whose editorial discipline intentionally
# runs outside Google's snippet-display range (e.g. operator-class
# long-form descriptors for IEO semantic richness).
TITLE_MIN, TITLE_MAX = 30, 65
# Meta-description display range (Google SERP):
#   <70 chars = thin; >160 chars = truncated in desktop SERP.
# Overridable via .launch-readiness.yml `description_length_min` /
# `description_length_max`.
DESC_MIN, DESC_MAX = 70, 160
# Conservative SEO-display advisory range. NOT overridable. When the
# operator-set range is wider than these defaults (i.e., the consumer
# has explicitly relaxed thresholds for editorial reasons), the check
# emits a soft-reminder INFO finding tracking pages outside the
# conservative range so the operator can see how much deviation is
# accumulating. Lets editorial-intentional long titles co-exist with a
# visible "consider tightening when voice allows" signal.
TITLE_ADVISORY_MIN, TITLE_ADVISORY_MAX = 30, 65
DESC_ADVISORY_MIN, DESC_ADVISORY_MAX = 70, 160
# Redirect-chain follow cap (safety stop on a misconfigured loop).
REDIRECT_MAX_HOPS = 5
DEFAULT_SECURITY_HEADERS = [
    "strict-transport-security",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "content-security-policy",
]


def fetch(url: str, timeout: int = 30, head: bool = False):
    method = "HEAD" if head else "GET"
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), (b"" if head else r.read())
    except urllib.error.HTTPError as e:
        return (
            e.code,
            dict(e.headers) if e.headers else {},
            (b"" if head or not e.fp else e.read()),
        )
    except Exception as e:
        return 0, {}, repr(e).encode()


def extract_jsonld(html: str) -> list:
    blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    parsed: list = []
    for b in blocks:
        try:
            parsed.append(json.loads(b))
        except Exception as e:
            parsed.append({"__parse_error__": str(e), "__raw__": b[:200]})
    return parsed


def jsonld_types(parsed: list) -> list[tuple[str, str]]:
    """Return list of (scope, type) for every @type seen, including inside
    @graph blocks. Parse errors surface as ('PARSE_ERROR', message)."""
    types: list[tuple[str, str]] = []
    for block in parsed:
        if not isinstance(block, dict):
            continue
        if "__parse_error__" in block:
            types.append(("PARSE_ERROR", block["__parse_error__"]))
            continue
        graph = block.get("@graph")
        if isinstance(graph, list):
            for n in graph:
                if isinstance(n, dict):
                    t = n.get("@type")
                    if isinstance(t, list):
                        for tt in t:
                            types.append(("graph", tt))
                    elif t:
                        types.append(("graph", t))
        else:
            t = block.get("@type")
            if isinstance(t, list):
                for tt in t:
                    types.append(("root", tt))
            elif t:
                types.append(("root", t))
    return types


def extract_meta(html: str) -> dict:
    title = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    description = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    canonical = re.search(r'<link\s+rel="canonical"\s+href="([^"]*)"', html)
    og_title = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
    og_type = re.search(r'<meta\s+property="og:type"\s+content="([^"]*)"', html)
    og_image = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
    robots_meta = re.search(
        r'<meta\s+name="robots"\s+content="([^"]*)"', html, re.IGNORECASE,
    )
    return {
        "title": title.group(1).strip() if title else None,
        "description": description.group(1) if description else None,
        "canonical": canonical.group(1) if canonical else None,
        "og:title": og_title.group(1) if og_title else None,
        "og:type": og_type.group(1) if og_type else None,
        "og:image": og_image.group(1) if og_image else None,
        "robots_meta": robots_meta.group(1) if robots_meta else None,
    }


def find_inline_links(html: str) -> list[str]:
    return re.findall(r'<a\s+[^>]*href="([^"]+)"', html)


def find_h1s(html: str) -> list[str]:
    """Return text contents of every <h1> on the page (inner HTML stripped
    to bare-text for length/uniqueness counting; we only care HOW MANY
    H1s exist and whether they're non-empty)."""
    return [
        re.sub(r"<[^>]+>", "", m).strip()
        for m in re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    ]


def follow_redirect_chain(url: str, max_hops: int = REDIRECT_MAX_HOPS,
                          timeout: int = 15) -> list[tuple[str, int]]:
    """Follow HTTP redirects manually via HEAD; return the chain as a list
    of (url, status). The terminal entry is the resolved 2xx/4xx/5xx URL.
    Stops at max_hops to bound chain-loop pathologies."""
    chain: list[tuple[str, int]] = []
    current = url
    for _ in range(max_hops + 1):
        req = urllib.request.Request(
            current, method="HEAD", headers={"User-Agent": UA},
        )
        try:
            # Disable urllib's auto-redirect so we can count hops.
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(req, timeout=timeout) as r:
                status = r.status
                location = r.headers.get("Location")
        except urllib.error.HTTPError as e:
            status = e.code
            location = e.headers.get("Location") if e.headers else None
        except Exception as e:
            chain.append((current, 0))
            chain.append((repr(e), 0))
            return chain
        chain.append((current, status))
        if status not in (301, 302, 303, 307, 308) or not location:
            return chain
        # Resolve relative Location values against the current URL.
        current = urllib.parse.urljoin(current, location)
    return chain


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Suppress urllib's transparent redirect-following so the caller can
    count hops + follow them manually."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


def is_internal(href: str, apex: str) -> bool:
    if href.startswith("/"):
        return True
    if href.startswith(apex):
        return True
    return False


def normalize_internal(href: str, apex: str) -> str | None:
    if href.startswith(apex):
        return href
    if href.startswith("/"):
        return apex.rstrip("/") + href
    return None


def _resolve_secret(repo: Path, secret_rel: str | None, env_var: str) -> str | None:
    """Resolve an API key, in priority order:
      1. <env_var> env var (explicit, no decryption needed).
      2. SOPS-decrypted secrets file at `secret_rel` (relative to repo).
         Requires `sops` on PATH. Mirrors the cf-api / pagespeed pattern.
    Returns None if no key is reachable. Caller treats None as 'not
    configured' and falls back to a skip-style finding.
    """
    tok = os.environ.get(env_var)
    if tok:
        return tok.strip()
    if not secret_rel:
        return None
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
        m = re.match(rf"^\s*{re.escape(env_var)}\s*:\s*(.+?)\s*$", line)
        if m:
            val = m.group(1).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            return val
    return None


def resolve_apex(args, config: dict) -> str | None:
    """Return apex origin (scheme://host, no trailing slash) or None."""
    raw = (
        getattr(args, "apex", None)
        or config.get("live_probe_origin")
        or config.get("canonical_origin")
    )
    if not raw:
        return None
    raw = raw.strip().rstrip("/")
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw
    return raw


@time_check
def run(args) -> CheckResult:
    config = load_config(args.config)
    result = CheckResult(check="11-live-apex")

    apex = resolve_apex(args, config)
    # Per-repo length-range overrides; defaults match Google's SERP
    # truncation thresholds, but consumer repos may relax to accommodate
    # editorial discipline (short brand-voice titles, long-form
    # operator-class descriptors). Check still emits WARN when outside
    # the operator-set range; the range itself is the configurable knob.
    try:
        title_min = int(config.get("title_length_min", TITLE_MIN))
        title_max = int(config.get("title_length_max", TITLE_MAX))
        desc_min = int(config.get("description_length_min", DESC_MIN))
        desc_max = int(config.get("description_length_max", DESC_MAX))
    except (TypeError, ValueError):
        title_min, title_max = TITLE_MIN, TITLE_MAX
        desc_min, desc_max = DESC_MIN, DESC_MAX
    result.config_used = {
        "apex": apex,
        "piece_sample": DEFAULT_PIECE_SAMPLE,
        "link_sample": DEFAULT_LINK_SAMPLE,
        "title_length_range": [title_min, title_max],
        "description_length_range": [desc_min, desc_max],
    }

    if not apex:
        result.findings.append(Finding(
            id="11.0.no_origin", severity="NOT_APPLICABLE",
            title="No live origin configured",
            fix_action=(
                "Pass --apex URL, or set live_probe_origin / canonical_origin "
                "in .launch-readiness.yml."
            ),
        ))
        return result

    random.seed(42)

    # ---- Phase 0: sitemap discovery -----------------------------------
    code, _h, body = fetch(f"{apex}/sitemap.xml")
    if code != 200:
        result.findings.append(Finding(
            id="11.0.sitemap_unreachable", severity="FAIL",
            title=f"sitemap.xml fetch returned HTTP {code}",
            current=code, expected=200,
            fix_action="Verify the live apex serves /sitemap.xml.",
        ))
        return result
    try:
        root = ET.fromstring(body.decode(errors="replace"))
    except ET.ParseError as e:
        result.findings.append(Finding(
            id="11.0.sitemap_malformed", severity="FAIL",
            title="sitemap.xml at live apex is malformed XML",
            current=str(e),
        ))
        return result
    urls: list[str] = []
    for u in root.findall("s:url", SITEMAP_NS):
        loc = u.find("s:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    if not urls:
        result.findings.append(Finding(
            id="11.0.sitemap_empty", severity="FAIL",
            title="sitemap.xml at live apex contained zero <url> entries",
        ))
        return result
    result.findings.append(Finding(
        id="11.0.sitemap_ok", severity="PASS",
        title=f"sitemap.xml fetched from live apex; {len(urls)} URLs",
    ))

    # ---- Phase A: reachability sweep ----------------------------------
    non_2xx: list[tuple[str, int]] = []
    redirects: list[tuple[str, str]] = []
    codes: Counter = Counter()
    for u in urls:
        code, headers, _b = fetch(u, head=True, timeout=15)
        codes[code] += 1
        if code in (301, 302, 307, 308):
            redirects.append((u, headers.get("Location", "-")))
        elif code < 200 or code >= 300:
            non_2xx.append((u, code))
    if non_2xx:
        result.findings.append(Finding(
            id="11.A.unreachable", severity="FAIL",
            title=f"{len(non_2xx)} sitemap URL(s) did not return 2xx",
            current=dict(codes),
            notes="; ".join(f"[{c}] {u}" for u, c in non_2xx[:5]),
            fix_action="Investigate each non-2xx URL; either fix routing or drop from sitemap.",
        ))
    else:
        result.findings.append(Finding(
            id="11.A.reachable", severity="PASS",
            title=f"All {len(urls)} sitemap URLs return 2xx",
            current=dict(codes),
        ))
    if redirects:
        result.findings.append(Finding(
            id="11.A.redirects", severity="WARN",
            title=(
                f"{len(redirects)} sitemap URL(s) return a redirect "
                "(trailing-slash drift or CDN canonicalization)"
            ),
            notes="; ".join(f"{u} -> {loc}" for u, loc in redirects[:3]),
            fix_action=(
                "Make sitemap entries match the canonical URL shape the CDN "
                "serves (slash or no-slash; pick one and align)."
            ),
        ))

    # ---- Pre-fetch HTML for analysis ----------------------------------
    piece_urls = [u for u in urls if "/writing/" in u and "/pillar/" not in u]
    sample_n = min(DEFAULT_PIECE_SAMPLE, len(piece_urls))
    sample_pieces = random.sample(piece_urls, sample_n) if piece_urls else []

    home_html = fetch(f"{apex}/")[2].decode(errors="replace")
    about_html = fetch(f"{apex}/about")[2].decode(errors="replace")
    pages: list[tuple[str, str]] = [("/", home_html), ("/about", about_html)]
    for u in sample_pieces:
        _c, _h, b = fetch(u)
        pages.append((u, b.decode(errors="replace")))

    # ---- Phase B: JSON-LD audit ---------------------------------------
    type_counter: Counter = Counter()
    parse_errors: list[str] = []
    pages_without_jsonld: list[str] = []
    per_page_types: dict[str, set[str]] = {}
    for (label, html) in pages:
        parsed = extract_jsonld(html)
        if not parsed:
            pages_without_jsonld.append(label)
            continue
        types_here: set[str] = set()
        for scope, t in jsonld_types(parsed):
            if t == "PARSE_ERROR":
                parse_errors.append(label)
                continue
            type_counter[t] += 1
            types_here.add(t)
        per_page_types[label] = types_here

    if parse_errors:
        result.findings.append(Finding(
            id="11.B.parse_errors", severity="FAIL",
            title=f"{len(parse_errors)} page(s) had JSON-LD parse errors",
            notes=", ".join(parse_errors[:5]),
            fix_action="Open each page; the embedded JSON-LD block is invalid JSON.",
        ))
    else:
        result.findings.append(Finding(
            id="11.B.parse_clean", severity="PASS",
            title=f"All {len(pages)} sampled pages' JSON-LD parses cleanly",
        ))
    if pages_without_jsonld:
        result.findings.append(Finding(
            id="11.B.missing_jsonld", severity="FAIL",
            title=f"{len(pages_without_jsonld)} page(s) carry no JSON-LD at all",
            notes=", ".join(pages_without_jsonld[:5]),
        ))
    else:
        result.findings.append(Finding(
            id="11.B.jsonld_present", severity="PASS",
            title="All sampled pages carry JSON-LD",
        ))

    # Home baseline: WebSite + Person somewhere in the graph.
    home_types = per_page_types.get("/", set())
    expected_home = {"WebSite", "Person"}
    missing_home = expected_home - home_types
    if missing_home:
        result.findings.append(Finding(
            id="11.B.home_baseline", severity="WARN",
            title=f"Home missing expected JSON-LD types: {sorted(missing_home)}",
            current=sorted(home_types),
            expected=sorted(expected_home),
            fix_action="Emit WebSite + Person JSON-LD on the home page.",
        ))
    else:
        result.findings.append(Finding(
            id="11.B.home_baseline", severity="PASS",
            title=f"Home carries WebSite + Person JSON-LD ({sorted(home_types)})",
        ))

    # Per-piece baseline: accept any Article subtype.
    piece_labels = [lbl for (lbl, _h) in pages if "/writing/" in lbl]
    pieces_missing_article = []
    for lbl in piece_labels:
        if not (per_page_types.get(lbl, set()) & ARTICLE_TYPES):
            pieces_missing_article.append(lbl)
    if pieces_missing_article:
        result.findings.append(Finding(
            id="11.B.piece_baseline", severity="FAIL",
            title=(
                f"{len(pieces_missing_article)}/{len(piece_labels)} sampled "
                f"pieces missing Article (or subtype) JSON-LD"
            ),
            notes=", ".join(pieces_missing_article[:5]),
            expected=sorted(ARTICLE_TYPES),
            fix_action=(
                "Each piece needs Article-class JSON-LD (Article, "
                "ScholarlyArticle, BlogPosting, etc.)."
            ),
        ))
    elif piece_labels:
        result.findings.append(Finding(
            id="11.B.piece_baseline", severity="PASS",
            title=(
                f"All {len(piece_labels)} sampled pieces carry an "
                "Article-class JSON-LD type"
            ),
        ))

    # ---- Phase C: per-page meta audit ---------------------------------
    no_title: list[str] = []
    no_desc: list[str] = []
    no_canonical: list[str] = []
    bad_canonical: list[tuple[str, str]] = []
    no_og_image: list[str] = []
    noindex_found: list[tuple[str, str]] = []
    apex_host = urllib.parse.urlparse(apex).netloc
    for (label, html) in pages:
        m = extract_meta(html)
        if not m["title"]:
            no_title.append(label)
        if not m["description"]:
            no_desc.append(label)
        if not m["canonical"]:
            no_canonical.append(label)
        elif apex_host and apex_host not in m["canonical"]:
            bad_canonical.append((label, m["canonical"]))
        if not m["og:image"]:
            no_og_image.append(label)
        if m["robots_meta"] and "noindex" in m["robots_meta"].lower():
            noindex_found.append((label, m["robots_meta"]))

    if no_title:
        result.findings.append(Finding(
            id="11.C.title", severity="FAIL",
            title=f"{len(no_title)} pages missing <title>",
            notes=", ".join(no_title[:5]),
        ))
    else:
        result.findings.append(Finding(
            id="11.C.title", severity="PASS",
            title="All sampled pages have <title>",
        ))
    if no_desc:
        result.findings.append(Finding(
            id="11.C.description", severity="WARN",
            title=f"{len(no_desc)} pages missing meta description",
            notes=", ".join(no_desc[:5]),
        ))
    else:
        result.findings.append(Finding(
            id="11.C.description", severity="PASS",
            title="All sampled pages have meta description",
        ))
    if no_canonical:
        result.findings.append(Finding(
            id="11.C.canonical", severity="WARN",
            title=f"{len(no_canonical)} pages missing <link rel=canonical>",
            notes=", ".join(no_canonical[:5]),
            fix_action="Emit canonical link on every page (especially home + about).",
        ))
    else:
        result.findings.append(Finding(
            id="11.C.canonical", severity="PASS",
            title="All sampled pages carry <link rel=canonical>",
        ))
    if bad_canonical:
        result.findings.append(Finding(
            id="11.C.canonical_host", severity="FAIL",
            title=(
                f"{len(bad_canonical)} canonical href(s) do not point at "
                f"{apex_host}"
            ),
            notes="; ".join(f"{l} -> {c}" for l, c in bad_canonical[:3]),
        ))
    if no_og_image:
        result.findings.append(Finding(
            id="11.C.og_image", severity="WARN",
            title=f"{len(no_og_image)} pages missing og:image",
            notes=", ".join(no_og_image[:5]),
            fix_action="Emit an og:image meta on every page (default to a site-wide fallback).",
        ))
    else:
        result.findings.append(Finding(
            id="11.C.og_image", severity="PASS",
            title="All sampled pages have og:image",
        ))
    if noindex_found:
        result.findings.append(Finding(
            id="11.C.noindex", severity="FAIL",
            title=f"{len(noindex_found)} page(s) carry noindex meta",
            notes="; ".join(f"{l}: {r}" for l, r in noindex_found[:3]),
            fix_action="Remove rogue noindex meta tag (likely staging leftover).",
        ))
    else:
        result.findings.append(Finding(
            id="11.C.noindex", severity="PASS",
            title="No noindex meta on any sampled page",
        ))

    # ---- Phase D: inline-link audit -----------------------------------
    # Re-uses HTML already fetched into `pages` (no extra fetches per piece);
    # also persists the link sample + per-piece href map so phases H + I can
    # re-use it. The link sample is drawn from sample_pieces (deterministic
    # via random.seed(42) earlier).
    page_html_by_url: dict[str, str] = {label: html for (label, html) in pages}
    link_sample: list[str] = []
    inline_hrefs_by_piece: dict[str, list[str]] = {}
    internal_link_targets: set[str] = set()
    if sample_pieces:
        link_sample_n = min(DEFAULT_LINK_SAMPLE, len(sample_pieces))
        link_sample = random.sample(sample_pieces, link_sample_n)
        broken_links: list[tuple[str, str, int]] = []
        total_links = 0
        for piece_url in link_sample:
            html = page_html_by_url.get(piece_url) or fetch(piece_url)[2].decode(errors="replace")
            hrefs = find_inline_links(html)
            inline_hrefs_by_piece[piece_url] = hrefs
            for href in hrefs:
                if not is_internal(href, apex):
                    continue
                target = normalize_internal(href.split("#")[0], apex)
                if not target:
                    continue
                total_links += 1
                internal_link_targets.add(target)
                code, _h2, _b2 = fetch(target, head=True, timeout=15)
                if code not in (200, 301, 302, 307, 308):
                    broken_links.append((piece_url, href, code))
        if broken_links:
            result.findings.append(Finding(
                id="11.D.broken_links", severity="FAIL",
                title=(
                    f"{len(broken_links)} broken internal link(s) out of "
                    f"{total_links} across {link_sample_n} sampled pieces"
                ),
                notes="; ".join(
                    f"[{c}] {p} -> {h}" for p, h, c in broken_links[:5]
                ),
            ))
        else:
            result.findings.append(Finding(
                id="11.D.links_ok", severity="PASS",
                title=(
                    f"All {total_links} internal links across "
                    f"{link_sample_n} sampled pieces resolve"
                ),
            ))

    # ---- Phase E: security-header consistency -------------------------
    e_targets = [f"{apex}/"]
    if sample_pieces:
        e_targets.append(random.choice(sample_pieces))
    e_targets.append(f"{apex}/about")
    header_values: dict[str, set[str]] = {h: set() for h in DEFAULT_SECURITY_HEADERS}
    for u in e_targets:
        _c, headers, _b = fetch(u, head=True, timeout=15)
        lc = {k.lower(): v for k, v in headers.items()}
        for h in DEFAULT_SECURITY_HEADERS:
            header_values[h].add(lc.get(h, "<MISSING>"))
    missing_headers = [h for h, v in header_values.items() if "<MISSING>" in v]
    inconsistent_headers = [
        h for h, v in header_values.items()
        if "<MISSING>" not in v and len(v) > 1
    ]
    if missing_headers:
        result.findings.append(Finding(
            id="11.E.missing_headers", severity="FAIL",
            title=f"Security headers missing on at least one page: {missing_headers}",
            fix_action="Apply header rules at the host config to ALL paths, not subset.",
        ))
    if inconsistent_headers:
        result.findings.append(Finding(
            id="11.E.inconsistent_headers", severity="WARN",
            title=f"Security headers inconsistent across pages: {inconsistent_headers}",
        ))
    if not missing_headers and not inconsistent_headers:
        result.findings.append(Finding(
            id="11.E.headers_ok", severity="PASS",
            title=(
                f"All {len(DEFAULT_SECURITY_HEADERS)} security headers present "
                "and consistent across home / piece / about"
            ),
        ))

    # ---- Phase F: discovery artifacts ---------------------------------
    artifact_paths = ["/robots.txt", "/llms.txt", "/sitemap.xml", "/image-sitemap.xml"]
    # IndexNow keyfile path: prefer config, else skip silently.
    indexnow_key = config.get("indexnow_key")
    if indexnow_key:
        artifact_paths.append(f"/{indexnow_key}.txt")
    missing_artifacts: list[tuple[str, int]] = []
    for path in artifact_paths:
        code, _h, _b = fetch(f"{apex}{path}", head=True, timeout=15)
        if code != 200:
            missing_artifacts.append((path, code))
    if missing_artifacts:
        # llms.txt / image-sitemap.xml are WARN-class; robots.txt + sitemap.xml are FAIL-class.
        critical = [p for p, _c in missing_artifacts if p in ("/robots.txt", "/sitemap.xml")]
        result.findings.append(Finding(
            id="11.F.discovery_artifacts",
            severity="FAIL" if critical else "WARN",
            title=(
                f"{len(missing_artifacts)} discovery artifact(s) not 200 at live apex"
            ),
            notes="; ".join(f"[{c}] {p}" for p, c in missing_artifacts),
        ))
    else:
        result.findings.append(Finding(
            id="11.F.discovery_artifacts", severity="PASS",
            title=f"All {len(artifact_paths)} discovery artifacts reachable at live apex",
        ))

    # ---- Phase G: title + heading + meta-description hygiene ---------
    # Reuses pages cache. Screaming-Frog parity: title length (<30 or >65
    # WARNs in Google SERP snippet display); H1 presence + uniqueness;
    # meta-description length (<70 or >160 chars truncates in SERP).
    title_short: list[tuple[str, int]] = []
    title_long: list[tuple[str, int]] = []
    h1_missing: list[str] = []
    h1_multi: list[tuple[str, int]] = []
    desc_short: list[tuple[str, int]] = []
    desc_long: list[tuple[str, int]] = []
    for (label, html) in pages:
        m = extract_meta(html)
        title = m.get("title")
        if title:
            tl = len(title)
            if tl < title_min:
                title_short.append((label, tl))
            elif tl > title_max:
                title_long.append((label, tl))
        h1s = find_h1s(html)
        if not h1s:
            h1_missing.append(label)
        elif len(h1s) > 1:
            h1_multi.append((label, len(h1s)))
        desc = m.get("description")
        if desc:
            dl = len(desc)
            if dl < desc_min:
                desc_short.append((label, dl))
            elif dl > desc_max:
                desc_long.append((label, dl))

    if title_short or title_long:
        offenders = title_short + title_long
        result.findings.append(Finding(
            id="11.G.title_length", severity="WARN",
            title=(
                f"{len(offenders)} page(s) outside title-tag display range "
                f"({title_min}-{title_max} chars)"
            ),
            notes="; ".join(f"{l} ({n}c)" for l, n in offenders[:5]),
            fix_action=(
                f"Rewrite title to {title_min}-{title_max} chars; under-padded "
                "titles waste SERP snippet space, over-padded ones get truncated. "
                "If the deviation is editorial-intentional, relax via "
                "`title_length_min` / `title_length_max` in .launch-readiness.yml."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="11.G.title_length", severity="PASS",
            title=f"All sampled titles within {title_min}-{title_max} char display range",
        ))

    # Soft-reminder advisory: when operator-set range is wider than the
    # conservative SEO-display range, surface the count of pages outside the
    # CONSERVATIVE range as INFO. Lets the operator track how much editorial
    # deviation is accumulating without flagging every long title as a WARN.
    if title_min < TITLE_ADVISORY_MIN or title_max > TITLE_ADVISORY_MAX:
        adv_offenders: list[tuple[str, int]] = []
        for (label, html) in pages:
            t = extract_meta(html).get("title")
            if not t:
                continue
            tl = len(t)
            if tl < TITLE_ADVISORY_MIN or tl > TITLE_ADVISORY_MAX:
                adv_offenders.append((label, tl))
        if adv_offenders:
            result.findings.append(Finding(
                id="11.G.title_length_advisory", severity="INFO",
                title=(
                    f"{len(adv_offenders)}/{len(pages)} page(s) outside conservative "
                    f"SEO display range ({TITLE_ADVISORY_MIN}-{TITLE_ADVISORY_MAX} chars)"
                ),
                notes=(
                    f"Operator range relaxed to {title_min}-{title_max} in config. "
                    "Soft reminder: consider tightening titles toward the conservative "
                    "range when it doesn't cost editorial voice. "
                    + "; ".join(f"{l} ({n}c)" for l, n in adv_offenders[:5])
                ),
            ))

    if h1_missing:
        result.findings.append(Finding(
            id="11.G.h1_missing", severity="FAIL",
            title=f"{len(h1_missing)} page(s) missing <h1>",
            notes=", ".join(h1_missing[:5]),
            fix_action="Every page needs exactly one <h1>; load-bearing for SEO + accessibility.",
        ))
    else:
        result.findings.append(Finding(
            id="11.G.h1_missing", severity="PASS",
            title="All sampled pages have an <h1>",
        ))
    if h1_multi:
        result.findings.append(Finding(
            id="11.G.h1_unique", severity="WARN",
            title=f"{len(h1_multi)} page(s) have multiple <h1> elements",
            notes="; ".join(f"{l} ({n}x)" for l, n in h1_multi[:5]),
            fix_action="Demote secondary <h1>s to <h2>; SEO + accessibility expect one H1 per page.",
        ))
    elif not h1_missing:
        result.findings.append(Finding(
            id="11.G.h1_unique", severity="PASS",
            title="Every sampled page has exactly one <h1>",
        ))

    if desc_short or desc_long:
        offenders = desc_short + desc_long
        result.findings.append(Finding(
            id="11.G.desc_length", severity="WARN",
            title=(
                f"{len(offenders)} page(s) outside meta-description display range "
                f"({desc_min}-{desc_max} chars)"
            ),
            notes="; ".join(f"{l} ({n}c)" for l, n in offenders[:5]),
            fix_action=(
                f"Rewrite meta description to {desc_min}-{desc_max} chars; "
                "short = thin snippet, long = SERP truncation. "
                "If the deviation is editorial-intentional, relax via "
                "`description_length_min` / `description_length_max` in .launch-readiness.yml."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="11.G.desc_length", severity="PASS",
            title=f"All sampled meta descriptions within {desc_min}-{desc_max} char display range",
        ))

    # Soft-reminder advisory for descriptions (mirrors title_length_advisory).
    if desc_min < DESC_ADVISORY_MIN or desc_max > DESC_ADVISORY_MAX:
        adv_desc_offenders: list[tuple[str, int]] = []
        for (label, html) in pages:
            d = extract_meta(html).get("description")
            if not d:
                continue
            dl = len(d)
            if dl < DESC_ADVISORY_MIN or dl > DESC_ADVISORY_MAX:
                adv_desc_offenders.append((label, dl))
        if adv_desc_offenders:
            result.findings.append(Finding(
                id="11.G.desc_length_advisory", severity="INFO",
                title=(
                    f"{len(adv_desc_offenders)}/{len(pages)} page(s) outside "
                    f"conservative SEO display range "
                    f"({DESC_ADVISORY_MIN}-{DESC_ADVISORY_MAX} chars)"
                ),
                notes=(
                    f"Operator range relaxed to {desc_min}-{desc_max} in config. "
                    "Soft reminder: consider tightening descriptions toward the "
                    "conservative range when it doesn't cost editorial voice. "
                    "Long descriptions can be intentional for GEO (LLM-citation "
                    "context) over SEO (SERP-snippet display). "
                    + "; ".join(f"{l} ({n}c)" for l, n in adv_desc_offenders[:5])
                ),
            ))

    # ---- Phase H: redirect-chain hygiene ------------------------------
    # Reuses the link sample collected in phase D. For each sampled
    # internal link, follow the redirect chain (HEAD, no auto-follow);
    # FAIL if >1 hop, WARN if exactly 1. Phase A already caught
    # sitemap-level redirect drift; phase H catches inline-link-level
    # redirect drift (slug renames + trailing-slash drift on inline hrefs).
    if link_sample and inline_hrefs_by_piece:
        h_targets: list[str] = []
        seen_targets: set[str] = set()
        for piece in link_sample:
            for href in inline_hrefs_by_piece.get(piece, []):
                if not is_internal(href, apex):
                    continue
                t = normalize_internal(href.split("#")[0], apex)
                if not t or t in seen_targets:
                    continue
                seen_targets.add(t)
                h_targets.append(t)
        # Cap to 25 unique targets so a single piece's many internal links
        # don't multiply the redirect-chain fetch budget.
        h_targets = h_targets[:25]
        multi_hop: list[tuple[str, int, str]] = []  # (url, hops, terminal)
        single_hop: list[tuple[str, str]] = []      # (url, location)
        for t in h_targets:
            chain = follow_redirect_chain(t)
            hop_count = max(0, len(chain) - 1)
            terminal = chain[-1][0] if chain else t
            if hop_count >= 2:
                multi_hop.append((t, hop_count, terminal))
            elif hop_count == 1:
                single_hop.append((t, terminal))
        if multi_hop:
            result.findings.append(Finding(
                id="11.H.redirect_chain", severity="FAIL",
                title=(
                    f"{len(multi_hop)} internal link(s) traverse >1 redirect "
                    f"hop (out of {len(h_targets)} sampled)"
                ),
                notes="; ".join(
                    f"{u} ({n} hops -> {t})" for u, n, t in multi_hop[:5]
                ),
                fix_action=(
                    "Update the source href to point directly at the terminal "
                    "URL; chained redirects compound latency + dilute link signal."
                ),
            ))
        elif single_hop:
            result.findings.append(Finding(
                id="11.H.redirect_chain", severity="WARN",
                title=(
                    f"{len(single_hop)} internal link(s) trigger a single "
                    f"redirect (out of {len(h_targets)} sampled)"
                ),
                notes="; ".join(f"{u} -> {t}" for u, t in single_hop[:5]),
                fix_action=(
                    "Rewrite hrefs to the canonical URL shape so the CDN "
                    "doesn't have to 308 on every fetch."
                ),
            ))
        else:
            result.findings.append(Finding(
                id="11.H.redirect_chain", severity="PASS",
                title=(
                    f"All {len(h_targets)} sampled internal links resolve "
                    "in 0 redirect hops"
                ),
            ))

    # ---- Phase I: orphan-page + un-sitemapped-link detection ---------
    # Reconcile two graphs without extra fetches:
    #   (1) sitemap_set   — every URL the sitemap claims is canonical
    #   (2) link_set      — every internal href observed across home +
    #                       about + sampled-piece HTML in `pages`
    # Sitemap URLs not in link_set: INFO (could be legitimate deep pages
    # OR genuine orphans; needs human judgment).
    # Link targets not in sitemap_set: WARN (the page is linked but the
    # canonical-discovery surface doesn't list it, so external crawlers
    # may not find it).
    sitemap_set = {u.rstrip("/") for u in urls}
    link_set: set[str] = set()
    for (_label, html) in pages:
        for href in find_inline_links(html):
            if not is_internal(href, apex):
                continue
            t = normalize_internal(href.split("#")[0], apex)
            if t:
                link_set.add(t.rstrip("/"))

    # Pages that are in sitemap but never linked from the sampled corpus.
    # Exclude sitemap URLs that ARE the sample (a piece is naturally not
    # going to be linked from itself), home, about, and pillar collection
    # pages (often only linked from nav).
    nav_like_paths = {"", "/about", "/writing"}
    sampled_set = {u.rstrip("/") for u in sample_pieces} | {
        f"{apex}".rstrip("/"), f"{apex}/about".rstrip("/")
    }
    apparent_orphans = sorted(
        u for u in sitemap_set
        if u not in link_set
        and u not in sampled_set
        and urllib.parse.urlparse(u).path.rstrip("/") not in nav_like_paths
    )
    # Internal-link targets that point at URLs the sitemap doesn't list.
    # Exclude fragment-only / off-apex / non-canonical paths already
    # filtered above.
    un_sitemapped = sorted(
        t for t in link_set
        if t not in sitemap_set
        and t.startswith(apex)
        and t != apex.rstrip("/")
    )

    if apparent_orphans:
        # Limited by sample size: with 18 sampled pieces, most "orphans" are
        # just unsampled. Treated as INFO not WARN for this reason. To use as
        # a definitive orphan-test, run with `--full-link-graph` once that's
        # wired up (TODO: would require fetching every sitemap URL's HTML).
        result.findings.append(Finding(
            id="11.I.apparent_orphans", severity="INFO",
            title=(
                f"{len(apparent_orphans)} sitemap URL(s) not linked from the "
                f"sampled link-graph (home + about + {sample_n} pieces)"
            ),
            notes="; ".join(apparent_orphans[:5]),
            fix_action=(
                "Mostly false-positives at this sample size — verify each by "
                "checking whether it has an inbound link from a pillar / index / "
                "related-pieces module. A page linked only from nav is fine."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="11.I.apparent_orphans", severity="PASS",
            title="No apparent orphans in the sampled link-graph",
        ))
    if un_sitemapped:
        result.findings.append(Finding(
            id="11.I.un_sitemapped", severity="WARN",
            title=(
                f"{len(un_sitemapped)} internal link target(s) point at URLs "
                "not present in sitemap.xml"
            ),
            notes="; ".join(un_sitemapped[:5]),
            fix_action=(
                "Either add the target to the sitemap (if it's canonical) or "
                "rewrite the href to the canonical URL the sitemap lists."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="11.I.un_sitemapped", severity="PASS",
            title="Every internal link target appears in the sitemap",
        ))

    # ---- Phase J: meta-description duplicate detection ---------------
    # Reuses pages cache. Each page should have a UNIQUE meta description
    # for SEO + SERP-display purposes; duplicates suggest a template-default
    # that overrides the per-page emitter.
    desc_to_pages: dict[str, list[str]] = {}
    for (label, html) in pages:
        d = extract_meta(html).get("description")
        if not d:
            continue
        # Normalize whitespace so trivial render-time diffs don't dodge
        # the dedup check.
        key = re.sub(r"\s+", " ", d.strip())
        desc_to_pages.setdefault(key, []).append(label)
    duplicates = {k: v for k, v in desc_to_pages.items() if len(v) > 1}
    if duplicates:
        sample_dupes = list(duplicates.items())[:3]
        # Operator-starting-point template: list the affected page paths
        # so the operator can edit each per-page meta-description emitter
        # without re-deriving the set from `notes`. Copy itself remains
        # editorial (`fix_safety: manual`); the template just speeds the
        # operator to the right call sites.
        affected_pages = sorted({lbl for v in duplicates.values() for lbl in v})
        fix_lines = [
            "Each of these pages currently shares its meta description "
            "with another page. Rewrite to a unique 70-160 char "
            "description that reflects the specific page's topic:",
            "",
        ]
        for label in affected_pages:
            fix_lines.append(f"  - {label}  (current: '{next(k for k, v in duplicates.items() if label in v)[:80]}...')")
        fix_lines.extend([
            "",
            "Guidance per page type:",
            "  / (home): brand + 1-line value-prop; use canonical brand voice.",
            "  /about: author identity + the singular through-line.",
            "  /writing/<slug>: piece-specific thesis + one operator detail.",
            "  pillar / collection pages: scope + counter-thesis posture.",
        ])
        result.findings.append(Finding(
            id="11.J.desc_duplicates", severity="WARN",
            title=(
                f"{len(duplicates)} meta-description value(s) shared across "
                f"multiple pages ({sum(len(v) for v in duplicates.values())} "
                f"pages affected out of {len(pages)})"
            ),
            notes="; ".join(
                f"'{k[:60]}…' on {len(v)} pages ({', '.join(v[:3])})"
                for k, v in sample_dupes
            ),
            fix_safety="manual",
            fix_template="\n".join(fix_lines),
            fix_action=(
                "Make each page's meta description unique; duplicates "
                "trigger Google's 'duplicate meta descriptions' warning in "
                "Search Console + waste SERP differentiation. See "
                "fix_template for the affected pages + per-page-type guidance."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="11.J.desc_duplicates", severity="PASS",
            title=f"All {len(desc_to_pages)} non-empty meta descriptions are unique across the sample",
        ))

    # ---- Phase K: Brave Search indexability probe (v1.1) -------------
    # Anthropic's Claude.ai web search routes through Brave Search (March
    # 2025 subprocessor list; Profound May 2025 measurement found 86.7%
    # citation-URL overlap between Claude's cited sources and Brave's
    # top-10 results, p<0.0001). Brave visibility correlates with Claude
    # citation eligibility — but Brave doesn't offer a Webmaster Tools
    # / Search Console product (confirmed by Brave staff in community
    # threads). The lever is *Brave visibility*, not *Brave submission*.
    #
    # This phase queries Brave Search for the apex's brand-entity query
    # and checks whether the canonical URL appears in the top-10 results.
    # Opt-in: requires `brave_api_key` (free tier: 1 req/sec, 2k req/month
    # at api.search.brave.com). When unconfigured, emits a single INFO.
    # Findings are advisory (INFO/MV); never FAIL — search-engine
    # visibility is emergent and noisy.
    repo_path = Path(getattr(args, "repo", ".") or ".")
    brave_key = (
        config.get("brave_api_key")
        or _resolve_secret(repo_path, config.get("brave_secret_path"), "BRAVE_API_KEY")
    )
    if not brave_key:
        result.findings.append(Finding(
            id="11.K.brave_probe", severity="INFO",
            title="Brave Search indexability probe skipped (no brave_api_key configured)",
            notes=(
                "Anthropic's Claude.ai web search routes through Brave Search "
                "(Profound May 2025: 86.7% citation-URL overlap). To enable this "
                "phase, set `brave_api_key` in .launch-readiness.yml or "
                "`brave_secret_path` to a SOPS file with BRAVE_API_KEY. Free tier: "
                "1 req/sec, 2k req/month at api.search.brave.com. NOTE: Brave does "
                "not offer a Webmaster Tools / Search Console product — the lever "
                "is *Brave visibility*, not *Brave submission*."
            ),
        ))
    else:
        # Default query: bare apex host. Operator can override for brand
        # queries that aren't just the domain name (e.g. "Author Name" or
        # "Brand Name") via `brave_probe_query`.
        default_query = urllib.parse.urlparse(apex).netloc
        query = config.get("brave_probe_query", default_query)
        api_url = (
            "https://api.search.brave.com/res/v1/web/search?"
            + urllib.parse.urlencode({"q": query, "count": 10})
        )
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "X-Subscription-Token": brave_key,
                "User-Agent": "IEO-launch-audit/1.1 (+brave-probe)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", 0)
            if code == 429:
                result.findings.append(Finding(
                    id="11.K.brave_probe", severity="MANUAL_VERIFY",
                    title="Brave Search API rate-limited (HTTP 429); probe skipped this run",
                    notes=(
                        "Free-tier limit is 1 req/sec, 2k req/month. Try again or "
                        "check api.search.brave.com dashboard for quota state."
                    ),
                ))
            else:
                result.findings.append(Finding(
                    id="11.K.brave_probe", severity="MANUAL_VERIFY",
                    title=f"Brave Search API returned HTTP {code}; probe skipped this run",
                    notes="Verify brave_api_key is valid and api.search.brave.com is reachable.",
                ))
            payload = None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            result.findings.append(Finding(
                id="11.K.brave_probe", severity="MANUAL_VERIFY",
                title="Brave Search API unreachable / non-JSON response; probe skipped this run",
                notes=str(e)[:200],
            ))
            payload = None
        if payload is not None:
            results = (payload.get("web") or {}).get("results") or []
            urls_seen = [(r.get("url") or "").rstrip("/") for r in results]
            apex_norm = apex.rstrip("/")
            apex_host = urllib.parse.urlparse(apex).netloc
            apex_match_idx = None
            host_match_idx = None
            for i, u in enumerate(urls_seen):
                if u == apex_norm:
                    apex_match_idx = i
                    break
            if apex_match_idx is None:
                for i, u in enumerate(urls_seen):
                    if apex_host and apex_host in u:
                        host_match_idx = i
                        break
            if apex_match_idx is not None:
                result.findings.append(Finding(
                    id="11.K.brave_probe", severity="PASS",
                    title=(
                        f"Brave Search returned apex at rank #{apex_match_idx + 1} "
                        f"for query '{query}' (top {len(urls_seen)})"
                    ),
                    notes=(
                        "Apex visibility on Brave is the practical Claude-citation "
                        "eligibility lever — Claude.ai web search routes through Brave."
                    ),
                ))
            elif host_match_idx is not None:
                result.findings.append(Finding(
                    id="11.K.brave_probe", severity="INFO",
                    title=(
                        f"Brave Search returned a non-apex URL on this host at rank #"
                        f"{host_match_idx + 1} for query '{query}'"
                    ),
                    current=urls_seen[host_match_idx],
                    notes=(
                        "Apex itself not in top-10 but the host is represented. "
                        "Apex-first canonicalization may improve Claude-citation eligibility."
                    ),
                ))
            else:
                result.findings.append(Finding(
                    id="11.K.brave_probe", severity="INFO",
                    title=(
                        f"Apex not visible in Brave Search top-{len(urls_seen)} for "
                        f"query '{query}'"
                    ),
                    current=urls_seen[:5],
                    fix_safety="manual",
                    fix_action=(
                        "Brave indexing is via the Web Discovery Project (opt-in "
                        "telemetry from Brave-browser users) — site owners can't "
                        "directly submit. Practical levers: increase site discoverability "
                        "(linkbuilding, content depth, organic Google ranking), and "
                        "ensure robots.txt / sitemap / HTML rendering is crawler-friendly. "
                        "Try a different brand-entity query via `brave_probe_query` if "
                        "the default (bare domain) doesn't match how users search."
                    ),
                    notes=(
                        "Single Brave-API call per audit run. Free-tier quota: 2k/month."
                    ),
                ))

    # ---- Phase L: multi-UA crawler probe (v1.5.1, opt-in) ------------
    #
    # Source-side audits cannot see CDN-layer / hosting-layer AI-bot
    # blocks: an apex that serves cleanly to a browser may serve 403/429
    # or significantly-shorter bodies when fetched as GPTBot / ClaudeBot /
    # PerplexityBot / OAI-SearchBot. Verified evidence for the failure
    # mode + detection method:
    #
    # - Aleyda Solis on Humans of Martech Ep 202 (Jan 13, 2026): "I
    #   realized my hosting company was blocking AI bots. All the answers
    #   looked wrong and the share of voice was terrible. I only found
    #   it because I dug deep into the validation."
    # - Cloudflare default-block (opt-in-at-signup, July 2025): every new
    #   Cloudflare domain is prompted at signup with default-block as the
    #   recommended answer. 416B AI-bot requests blocked at edge July →
    #   Dec 2025 (Matthew Prince, WIRED interview Dec 2025).
    # - HUMAN Security: AI-crawler UA spoofing rates 1:5 (ChatGPT-User)
    #   to 1:88 (Perplexity-User) — UA-spoofing is real; UA+IP cross-
    #   check is the verified detection method.
    #
    # Opt-in via `multi_ua_probe: true` in `.launch-readiness.yml`.
    # Default off to honor "no surprise network probes" stance. When
    # enabled: 1 baseline fetch + N AI-bot fetches (N=6 by default).
    if config.get("multi_ua_probe") is True:
        baseline_code, _baseline_h, baseline_body = fetch(apex)
        if baseline_code != 200:
            result.findings.append(Finding(
                id="11.L.multi_ua_skip", severity="MANUAL_VERIFY",
                title=(
                    f"Multi-UA probe skipped: baseline fetch of {apex} returned "
                    f"HTTP {baseline_code}"
                ),
                notes=(
                    "Baseline browser-UA fetch must succeed (200) before "
                    "AI-bot UA comparisons are meaningful."
                ),
            ))
        else:
            baseline_size = len(baseline_body) if baseline_body else 0
            ua_results: list[tuple[str, int, int]] = []  # (name, code, body_size)
            for ua_name, ua_string in AI_BOT_UAS.items():
                try:
                    req = urllib.request.Request(
                        apex,
                        method="GET",
                        headers={"User-Agent": ua_string},
                    )
                    with urllib.request.urlopen(req, timeout=20) as r:
                        body = r.read()
                        ua_results.append((ua_name, r.status, len(body)))
                except urllib.error.HTTPError as e:
                    ua_results.append((ua_name, e.code, 0))
                except (urllib.error.URLError, TimeoutError, OSError):
                    ua_results.append((ua_name, 0, 0))

            blocked: list[str] = []
            shrunk: list[str] = []
            ok: list[str] = []
            unreachable: list[str] = []
            for ua_name, code, size in ua_results:
                if code == 0:
                    unreachable.append(ua_name)
                elif code in (403, 429, 503):
                    blocked.append(f"{ua_name} (HTTP {code})")
                elif code == 200 and baseline_size > 0 and size < baseline_size * 0.7:
                    pct = size * 100 / baseline_size
                    shrunk.append(f"{ua_name} ({pct:.0f}% of baseline size)")
                elif code == 200:
                    ok.append(ua_name)

            if blocked:
                result.findings.append(Finding(
                    id="11.L.ai_bot_blocked", severity="WARN",
                    title=(
                        f"{len(blocked)} of {len(AI_BOT_UAS)} AI-bot UAs receive "
                        "HTTP 403/429/503 from live apex (CDN/hosting-layer block)"
                    ),
                    current=blocked,
                    expected="AI bots receive same 200 response as baseline browser UA",
                    fix_safety="manual",
                    fix_action=(
                        "Check CDN bot-management settings (Cloudflare bot fight "
                        "mode, AWS WAF managed rules, Fastly bot detection). "
                        "Cloudflare's July 2025 default-block setting prompts new "
                        "domains at signup with default-block as recommended; "
                        "existing zones inherit prior setting. If AI-bot citation "
                        "eligibility is desired, set the override per-engine in "
                        "the CDN bot-management UI."
                    ),
                    notes=(
                        f"Baseline browser-UA fetch: {baseline_size} bytes. "
                        f"AI-bot results: blocked={blocked}, ok={ok}, "
                        f"shrunk={shrunk}, unreachable={unreachable}. "
                        "Robots.txt blocks would be visible to source-side audits "
                        "(check 3) — this finding catches the CDN-layer block "
                        "INVISIBLE to source-side."
                    ),
                ))
            elif shrunk:
                result.findings.append(Finding(
                    id="11.L.ai_bot_shrunk", severity="INFO",
                    title=(
                        f"{len(shrunk)} of {len(AI_BOT_UAS)} AI-bot UAs receive "
                        "significantly smaller body than baseline (possible "
                        "Cloudflare interstitial / WAF challenge / partial content)"
                    ),
                    current=shrunk,
                    notes=(
                        f"Baseline: {baseline_size} bytes. AI-bot UAs receive "
                        "<70% of baseline body size — likely a CAPTCHA / WAF "
                        "challenge page rather than real content. Verify by "
                        "curl-ing manually with the UA string."
                    ),
                ))
            elif unreachable and len(unreachable) == len(AI_BOT_UAS):
                result.findings.append(Finding(
                    id="11.L.multi_ua_network_error", severity="MANUAL_VERIFY",
                    title="All AI-bot UA fetches failed at network level",
                    notes=(
                        f"Baseline browser UA succeeded ({baseline_size} bytes) "
                        "but all AI-bot UAs failed (timeout / DNS / TLS). Likely "
                        "transient; re-run."
                    ),
                ))
            else:
                result.findings.append(Finding(
                    id="11.L.multi_ua_clean", severity="PASS",
                    title=(
                        f"All {len(ok)} probed AI-bot UAs receive 200 + comparable "
                        "body size from live apex"
                    ),
                    notes=(
                        f"Probed: {sorted(AI_BOT_UAS.keys())}. Baseline: "
                        f"{baseline_size} bytes. No CDN-layer AI-bot block "
                        "detected on the apex itself. (Per-path / per-route "
                        "blocks may still exist — this probe tests apex only.)"
                    ),
                ))

    # ---- Summary ------------------------------------------------------
    counts = Counter(f.severity for f in result.findings)
    result.summary = (
        f"Live-apex audit against {apex}: "
        f"{counts.get('PASS', 0)} PASS, "
        f"{counts.get('WARN', 0)} WARN, "
        f"{counts.get('FAIL', 0)} FAIL "
        f"across {len(pages)} pages + {len(urls)} sitemap entries."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("11-live-apex")
    # --repo + --config are inherited from base_argparser for orchestrator
    # compatibility but are not strictly required for this check.
    # Override --repo/--config defaults so the script can be run standalone:
    for action in parser._actions:
        if action.dest in ("repo", "config"):
            action.required = False
            if action.dest == "repo":
                action.default = "."
            if action.dest == "config":
                action.default = ".launch-readiness.yml"
    parser.add_argument(
        "--apex",
        default=None,
        help=(
            "Live origin to audit (e.g. https://example.com). "
            "Overrides live_probe_origin / canonical_origin from config."
        ),
    )
    args = parser.parse_args()
    emit(run(args))
