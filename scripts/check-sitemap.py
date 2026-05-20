#!/usr/bin/env python3
"""
Check 07 — Sitemap accuracy.

Parses sitemap.xml, verifies presence + structural validity, samples
lastmod claims against source file mtimes (when source files can be
located via slug → file mapping).
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact,
    find_frontmatter_for_slug, load_config, load_frontmatter, time_check,
)


# Default frontmatter patterns when sitemap_lastmod_mode == "editorial"
# and the config doesn't override `slug_to_frontmatter_map`. Repo-portable
# defaults; ordered most-specific-first.
DEFAULT_EDITORIAL_PATTERNS = [
    "docs/editorial/drafts/*{slug}*.md",
    "writing-drafts/*{slug}*.md",
    "content/**/*{slug}*.md",
    "posts/**/*{slug}*.md",
]
DEFAULT_EDITORIAL_DATE_KEYS = [
    "dateModified",
    "originalPublicationDate",
    "publishedDate",
]


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse_sitemap(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    urls = []
    for u in root.findall(f"{SITEMAP_NS}url"):
        loc = u.find(f"{SITEMAP_NS}loc")
        lastmod = u.find(f"{SITEMAP_NS}lastmod")
        urls.append({
            "loc": loc.text if loc is not None else None,
            "lastmod": lastmod.text if lastmod is not None else None,
        })
    return urls


def find_source_file(repo: Path, slug: str) -> Path | None:
    """Try common source-content locations to locate a file that produces this slug."""
    candidates = [
        f"docs/editorial/drafts/*{slug}*.md",
        f"content/**/{slug}*.md",
        f"content/**/{slug}.md",
        f"src/content/**/{slug}*.md",
        f"posts/**/{slug}*.md",
        f"client/src/content/writing/*{slug}*.tsx",
        f"writing-drafts/*{slug}*.md",
    ]
    for pat in candidates:
        matches = list(repo.glob(pat))
        if matches:
            return matches[0]
    return None


def parse_iso_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        # Force timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="07-sitemap-accuracy")

    sm_path = find_artifact(repo, config, "sitemap_xml", [
        "dist/public/sitemap.xml", "public/sitemap.xml", "out/sitemap.xml",
        "_site/sitemap.xml", "build/sitemap.xml", "static/sitemap.xml",
    ])

    if not sm_path:
        result.findings.append(Finding(
            id="7.1.missing", severity="FAIL",
            title="sitemap.xml not found",
            fix_safety="manual",
            fix_action="Build the site to emit sitemap.xml; or set artifacts.sitemap_xml in config.",
        ))
        return result

    try:
        urls = parse_sitemap(sm_path)
    except ET.ParseError as e:
        result.findings.append(Finding(
            id="7.1.malformed", severity="FAIL",
            title="sitemap.xml malformed",
            current=str(e), fix_safety="manual",
        ))
        return result

    result.findings.append(Finding(
        id="7.1.parses", severity="PASS",
        title=f"sitemap.xml parses cleanly; {len(urls)} URLs",
    ))

    # 7.2 — lastmod accuracy (sample of 20)
    #
    # Two modes:
    #   * file_mtime (default, v0.4): compare sitemap <lastmod> against
    #     source file mtime. Correct for sites where the build pipeline
    #     preserves mtimes from authoring.
    #   * editorial: compare against editorial date keys (dateModified /
    #     originalPublicationDate / publishedDate) read from a
    #     frontmatter source file located via configured glob patterns.
    #     Correct for backdated catalogues where every source file
    #     shares a build-step mtime but the editorially-correct lastmod
    #     lives in the piece's frontmatter.
    lastmod_mode = config.get("sitemap_lastmod_mode", "file_mtime")
    editorial_cfg = config.get("slug_to_frontmatter_map") or {}
    if isinstance(editorial_cfg, dict):
        patterns: list[str] = []
        if editorial_cfg.get("pattern"):
            patterns.append(editorial_cfg["pattern"])
        if editorial_cfg.get("fallback_pattern"):
            patterns.append(editorial_cfg["fallback_pattern"])
        date_keys = editorial_cfg.get("date_keys") or DEFAULT_EDITORIAL_DATE_KEYS
    else:
        patterns = []
        date_keys = DEFAULT_EDITORIAL_DATE_KEYS
    if not patterns:
        patterns = DEFAULT_EDITORIAL_PATTERNS

    sample = urls[:20]
    matched = mtime_mismatches = all_identical = unverifiable = 0
    lastmod_values = []
    for u in sample:
        if not u["loc"] or not u["lastmod"]:
            continue
        lastmod_values.append(u["lastmod"][:10])
        # Slug = last path segment of loc
        slug = u["loc"].rstrip("/").rsplit("/", 1)[-1]
        sitemap_dt = parse_iso_date(u["lastmod"])
        if not sitemap_dt:
            unverifiable += 1
            continue

        if lastmod_mode == "editorial":
            fm_path = find_frontmatter_for_slug(repo, slug, patterns)
            if not fm_path:
                unverifiable += 1
                continue
            fm = load_frontmatter(fm_path)
            if not fm:
                unverifiable += 1
                continue
            editorial_dt = None
            for key in date_keys:
                raw = fm.get(key)
                if raw:
                    editorial_dt = parse_iso_date(str(raw))
                    if editorial_dt:
                        break
            if not editorial_dt:
                unverifiable += 1
                continue
            diff_days = abs((sitemap_dt - editorial_dt).days)
        else:
            src = find_source_file(repo, slug)
            if not src:
                unverifiable += 1
                continue
            src_mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc)
            diff_days = abs((sitemap_dt - src_mtime).days)

        if diff_days <= 1:
            matched += 1
        else:
            mtime_mismatches += 1

    truth_label = "editorial frontmatter" if lastmod_mode == "editorial" else "source mtime"

    # All-identical-lastmod check
    if lastmod_values and len(set(lastmod_values)) == 1:
        result.findings.append(Finding(
            id="7.2.all_identical", severity="FAIL",
            title="All sampled lastmod values are identical (suggests build-timestamp not per-piece date)",
            current=lastmod_values[0],
            fix_safety="manual",
            fix_action=(
                "Update sitemap emitter to derive lastmod from per-piece source "
                f"({truth_label}), not build time. Google discounts sitemaps "
                "with all-identical lastmod."
            ),
        ))
    elif unverifiable >= len(sample) - 2:
        miss_label = (
            "frontmatter source file or date key"
            if lastmod_mode == "editorial"
            else "source files"
        )
        result.findings.append(Finding(
            id="7.2.unverifiable", severity="MANUAL_VERIFY",
            title=f"Cannot map sitemap URLs to {miss_label} (slug -> source lookup failed)",
            fix_safety="manual",
            fix_action=(
                f"Verify manually that sitemap lastmod matches {truth_label}. "
                "If mode=editorial, check slug_to_frontmatter_map.pattern + date_keys."
            ),
        ))
    elif mtime_mismatches > matched:
        result.findings.append(Finding(
            id="7.2.mismatches", severity="WARN",
            title=(
                f"sitemap lastmod mismatch vs {truth_label} on "
                f"{mtime_mismatches}/{matched + mtime_mismatches} sampled URLs"
            ),
            fix_safety="manual",
        ))
    else:
        result.findings.append(Finding(
            id="7.2.accuracy", severity="PASS",
            title=(
                f"sitemap lastmod accurate vs {truth_label} on "
                f"{matched}/{matched + mtime_mismatches} verifiable sampled URLs"
            ),
        ))

    # 7.3 — Static pages present
    #
    # Compare path-normalised forms so the home URL matches whether the
    # sitemap emits it as `<APEX>`, `<APEX>/`, or just `/` and however the
    # config carries it. Strip trailing slashes from both sides; treat the
    # bare apex (empty-path) as equivalent to `/`.
    #
    # v1.6.5: expected list is now config-driven via `expected_static_pages`.
    # Pre-v1.6.5 hardcoded ["/", "/writing", "/about", "/contact"] —
    # portfolio-shaped default that produced false positives on product
    # sites. New default: ["/"]. Portfolio consumers add the rest via
    # config.
    canonical = config.get("canonical_origin", "")
    apex = canonical.rstrip("/")
    static_pages_seen = {(u["loc"] or "").rstrip("/") for u in urls if u["loc"]}
    expected_static = config.get("expected_static_pages", ["/"])
    if not isinstance(expected_static, list):
        expected_static = ["/"]
    missing_static = []
    if canonical:
        for sp in expected_static:
            # For the root ("/"), the normalised target is the bare apex.
            sp_norm = sp if sp.startswith("/") else "/" + sp
            target = apex if sp_norm == "/" else apex + sp_norm.rstrip("/")
            if target not in static_pages_seen:
                missing_static.append(sp_norm)
        if missing_static:
            result.findings.append(Finding(
                id="7.3.static_pages", severity="WARN",
                title=f"Configured static pages missing from sitemap: {missing_static}",
                fix_safety="manual",
                fix_action=(
                    "Either add the missing static pages to the sitemap "
                    "emitter, OR adjust `expected_static_pages` in "
                    ".launch-readiness.yml if the page set doesn't apply to "
                    "this site shape (e.g., product sites typically don't "
                    "have /writing or /contact). Default expected: [\"/\"]; "
                    "override with a custom list for portfolios, blogs, "
                    "documentation sites, etc."
                ),
            ))
        else:
            result.findings.append(Finding(
                id="7.3.static_pages", severity="PASS",
                title=(
                    f"All {len(expected_static)} configured static page(s) "
                    "present in sitemap"
                ),
            ))

    # 7.4 — Per-engine freshness band coverage (v1.3).
    #
    # Each AI engine has a different freshness preference, per Phase 2
    # verification (ConvertMate 2026, Profound, Ahrefs Feb 2026):
    #   Perplexity ~30d  → 76-82% of cited content under 30 days
    #   ChatGPT   ~90d  → 70%+ under 12 months but cliff at 3 months
    #   AI Overviews ~180d → 50% under 13 weeks (smoothed from Amsive)
    #   Claude     unknown → not enough independent measurement to score
    #
    # The check reports DISTRIBUTION as INFO across the consumer's
    # target_engines list. Operator decides whether to backfill freshness
    # for an under-represented engine.
    target_engines = config.get("target_engines") or ["chatgpt", "perplexity", "aio"]
    if isinstance(target_engines, str):
        target_engines = [target_engines]
    PER_ENGINE_BANDS = {
        "perplexity": 30,
        "chatgpt": 90,
        "aio": 180,
        "ai_overviews": 180,
        "google_ai_mode": 180,
        # Claude omitted: insufficient independent measurement as of 2026-05.
    }
    now = datetime.now(timezone.utc)
    ages_days: list[int] = []
    for u in urls:
        if not u.get("lastmod"):
            continue
        dt = parse_iso_date(u["lastmod"])
        if dt is None:
            continue
        ages_days.append((now - dt).days)
    if ages_days:
        n = len(ages_days)
        ages_sorted = sorted(ages_days)
        median_age = ages_sorted[n // 2]
        bands_present: list[tuple[str, int, int, int, float]] = []
        # (engine, threshold_days, under_band, total, pct)
        for eng in target_engines:
            key = eng.lower().strip()
            threshold = PER_ENGINE_BANDS.get(key)
            if threshold is None:
                continue
            under = sum(1 for a in ages_days if a <= threshold)
            pct = under * 100 / n
            bands_present.append((eng, threshold, under, n, pct))
        if bands_present:
            result.findings.append(Finding(
                id="7.4.engine_freshness", severity="INFO",
                title=(
                    f"Per-engine freshness distribution (median age {median_age}d) "
                    "across " + ", ".join(e for e, _t, _u, _n, _p in bands_present)
                ),
                current={
                    "median_age_days": median_age,
                    "lastmod_count": n,
                    "bands": [
                        {
                            "engine": e,
                            "threshold_days": t,
                            "under_band": u,
                            "total": tot,
                            "pct_under_band": round(p, 1),
                        }
                        for (e, t, u, tot, p) in bands_present
                    ],
                },
                notes=(
                    "Per-engine bands: Perplexity ~30d (Profound May 2025), "
                    "ChatGPT ~90d (Profound Jan-Mar 2026), AIO ~180d "
                    "(ConvertMate 2026; Amsive 13-week smoothed). Claude "
                    "omitted — insufficient independent measurement 2026-05. "
                    "Configure via `target_engines:` list."
                ),
            ))

    # 7.5 — Substantive-delta detection (v1.3, opt-in).
    #
    # December 2025 core update: cosmetic dateModified flips no longer
    # trigger freshness boost (Mueller on record + Sterling Sky case
    # studies). The audit can verify substantive delta via Wayback CDX
    # API content-digest comparison — identical digests = bit-identical =
    # cosmetic (or no change). When digests differ, fetch the prior
    # snapshot + current HTML and compute a difflib ratio: <10% delta =
    # cosmetic-only.
    #
    # Opt-in via `freshness_delta_check: true` — adds 10s-2min to audit
    # budget. Sample size defaults to 5 URLs (random; deterministic via
    # random.seed(42)). Stdlib-only.
    if config.get("freshness_delta_check") is True:
        import random
        import urllib.error
        import urllib.parse
        import urllib.request
        from difflib import SequenceMatcher

        sample_n = int(config.get("freshness_delta_sample_size", 5))
        urls_with_lastmod = [u for u in urls if u.get("loc") and u.get("lastmod")]
        if not urls_with_lastmod:
            result.findings.append(Finding(
                id="7.5.delta_skip", severity="INFO",
                title="Substantive-delta check skipped: no sitemap URLs carry lastmod",
            ))
        else:
            random.seed(42)
            sample_urls = (
                random.sample(urls_with_lastmod, sample_n)
                if len(urls_with_lastmod) > sample_n
                else urls_with_lastmod
            )
            cosmetic_only: list[tuple[str, float]] = []
            substantive: list[tuple[str, float]] = []
            delta_unverifiable: list[str] = []  # local to 7.5; do not shadow the 7.2 counter
            for u in sample_urls:
                loc = u["loc"]
                # Query Wayback CDX for the most recent snapshot's content
                # digest. Stdlib-only.
                cdx_url = (
                    "https://web.archive.org/cdx/search/cdx?"
                    + urllib.parse.urlencode({
                        "url": loc,
                        "output": "json",
                        "limit": "-1",
                        "fl": "timestamp,digest",
                    })
                )
                try:
                    req = urllib.request.Request(
                        cdx_url,
                        headers={"User-Agent": "IEO-launch-audit/1.3"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as r:
                        rows = json.loads(r.read().decode("utf-8"))
                except (urllib.error.URLError, urllib.error.HTTPError,
                        json.JSONDecodeError, TimeoutError, OSError):
                    delta_unverifiable.append(loc)
                    continue
                if not isinstance(rows, list) or len(rows) < 2:
                    delta_unverifiable.append(loc)
                    continue
                # rows[0] is header, rows[-1] is most recent snapshot.
                prior_ts, prior_digest = rows[-1][0], rows[-1][1]
                # Fetch current HTML (visible-text only)
                try:
                    req = urllib.request.Request(
                        loc,
                        headers={"User-Agent": "IEO-launch-audit/1.3"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as r:
                        current_html = r.read().decode("utf-8", errors="replace")
                except (urllib.error.URLError, urllib.error.HTTPError,
                        TimeoutError, OSError):
                    delta_unverifiable.append(loc)
                    continue
                # Fetch prior snapshot
                wayback_url = f"https://web.archive.org/web/{prior_ts}id_/{loc}"
                try:
                    req = urllib.request.Request(
                        wayback_url,
                        headers={"User-Agent": "IEO-launch-audit/1.3"},
                    )
                    with urllib.request.urlopen(req, timeout=20) as r:
                        prior_html = r.read().decode("utf-8", errors="replace")
                except (urllib.error.URLError, urllib.error.HTTPError,
                        TimeoutError, OSError):
                    delta_unverifiable.append(loc)
                    continue
                # Visible-text diff using SequenceMatcher.
                def strip(s):
                    s = re.sub(r"<script\b.*?</script>", " ", s, flags=re.DOTALL | re.IGNORECASE)
                    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
                    s = re.sub(r"<[^>]+>", " ", s)
                    return re.sub(r"\s+", " ", s).strip()
                cur_text = strip(current_html)
                prior_text = strip(prior_html)
                if not cur_text or not prior_text:
                    delta_unverifiable.append(loc)
                    continue
                ratio = SequenceMatcher(None, prior_text, cur_text).ratio()
                # ratio close to 1.0 → near-identical; <10% delta = cosmetic.
                delta = 1 - ratio
                if delta < 0.10:
                    cosmetic_only.append((loc, ratio))
                else:
                    substantive.append((loc, ratio))
            scored = len(cosmetic_only) + len(substantive)
            if scored == 0:
                result.findings.append(Finding(
                    id="7.5.substantive_delta", severity="MANUAL_VERIFY",
                    title=(
                        f"Substantive-delta check unverifiable on all {len(sample_urls)} "
                        "sampled URLs (no Wayback snapshots or fetch failures)"
                    ),
                    notes=(
                        "Wayback CDX returned no prior snapshot OR current/prior "
                        "fetch failed. Re-run after the site has a Wayback history. "
                        f"{len(delta_unverifiable)} URL(s) unverifiable."
                    ),
                ))
            elif cosmetic_only:
                samples = [f"{loc} (ratio {r:.2f})" for loc, r in cosmetic_only[:5]]
                result.findings.append(Finding(
                    id="7.5.substantive_delta", severity="WARN",
                    title=(
                        f"{len(cosmetic_only)}/{scored} sampled URLs show "
                        "<10% text delta vs prior Wayback snapshot — possible "
                        "cosmetic dateModified flips"
                    ),
                    current=samples,
                    fix_safety="manual",
                    fix_action=(
                        "Review the flagged URLs. If dateModified bumped without "
                        "substantive content change, the consequence is dual: "
                        "(a) Google's December 2025 core update treats cosmetic "
                        "flips as low-trust signal noise (industry post-mortem "
                        "consensus; Mueller on record about scaled minor edits); "
                        "(b) LLM rerankers have measurable recency bias — arXiv:"
                        "2509.11353 'Do Large Language Models Favor Recent Content?' "
                        "(ACM SIGIR-AP 2025, peer-reviewed) measured rank shifts of "
                        "up to 95 positions and pairwise-preference reversals of up "
                        "to 25% on average across 7 LLMs (GPT-3.5/4/4o, LLaMA-3 "
                        "8B/70B, Qwen-2.5 7B/72B) with synthetic date injection on "
                        "TREC DL21+DL22 (p<0.05). Either revert the date or add "
                        "substantive content."
                    ),
                    notes=(
                        f"Sample: {scored} scored, {len(delta_unverifiable)} unverifiable. "
                        "Threshold: <10% delta = cosmetic. Method: Wayback CDX "
                        "content-digest API + difflib.SequenceMatcher on visible-text diff. "
                        "**Scope of the arXiv:2509.11353 evidence:** LLM-as-reranker "
                        "behavior on TREC passages (controlled experiment), NOT "
                        "production-citation telemetry. Pair with Ahrefs 16.975M-"
                        "citation study (Jul 2025, ChatGPT cites content 393-458 "
                        "days newer than organic) for production-side observation, "
                        "and Bing's May 2026 grounding statement: 'In grounding, a "
                        "stale fact produces a misleading response.'"
                    ),
                ))
            else:
                result.findings.append(Finding(
                    id="7.5.substantive_delta", severity="PASS",
                    title=(
                        f"All {scored} sampled URLs have substantive content delta "
                        "(>10%) vs prior Wayback snapshot"
                    ),
                    notes=(
                        f"{len(delta_unverifiable)} unverifiable. Cosmetic-flip-class "
                        "concerns: not detected at this sample size."
                    ),
                ))

    result.summary = (
        f"Sitemap: {len(urls)} URLs, lastmod-accuracy (mode={lastmod_mode}) sample "
        f"{matched}/{matched + mtime_mismatches} OK, {unverifiable} unverifiable."
    )
    result.config_used = {
        "sitemap_lastmod_mode": lastmod_mode,
        "editorial_patterns": patterns if lastmod_mode == "editorial" else None,
        "editorial_date_keys": date_keys if lastmod_mode == "editorial" else None,
        "target_engines": target_engines,
        "freshness_delta_check": config.get("freshness_delta_check") is True,
    }
    return result


if __name__ == "__main__":
    parser = base_argparser("07-sitemap-accuracy")
    args = parser.parse_args()
    emit(run(args))
