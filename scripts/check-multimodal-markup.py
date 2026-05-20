#!/usr/bin/env python3
"""
Check 14 — Multimodal markup audit (figcaption + alt-text + HTML tables).

v1.4 opt-in. Walks sampled rendered HTML pages and audits semantic markup
density on content images + tabular data. Backed by SearchVIU 2025 and
Williams-Cook "Duck Test" (Feb 2026): LLM citation engines parse visible
HTML, not hidden metadata. Aleyda Solís AI-search checklist (practitioner-
tier) specifically calls out figcaption + HTML tables as multimodal-
markup recommendations.

Source tier: practitioner-consensus + indirect-methodology alignment
(neither SearchVIU nor Williams-Cook directly measure figcaption/table
deltas; both establish the upstream principle "visible HTML wins, hidden
metadata is ignored"). Findings default to INFO / PASS; WARN only when
density is unambiguously sparse on a page with >=3 content images.

Gated on operator declaration via `.launch-readiness.yml`:

  multimodal_markup_check: true   # opt-in

When unset, emits one INFO finding and skips. No false alarms on sites
that haven't opted in.

Stdlib only. Read-only against rendered HTML; no network calls.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


DEFAULT_SAMPLE_SIZE = 10

# Heuristic thresholds. Configurable via .launch-readiness.yml keys.
FIGCAPTION_PASS = 0.7      # >=70% of content imgs in figure+figcaption
FIGCAPTION_WARN = 0.3      # <30% triggers WARN when >=3 imgs
ALT_TEXT_PASS = 0.9        # >=90% of content imgs have alt=
ALT_TEXT_WARN = 0.7        # <70% triggers WARN when >=3 imgs
MIN_IMGS_FOR_WARN = 3      # don't fire WARN on sparse pages with 1-2 imgs


def find_content_images(html: str) -> tuple[list[str], bool]:
    """Extract <img> tags from content regions.

    Heuristic scope: if <main> or <article> present, restrict to its
    inner HTML. Otherwise fall back to whole-document scan and flag the
    caveat. Returns (list of alt-values or sentinel "__MISSING__",
    used_scope_flag).
    """
    used_scope = False
    main_match = re.search(r"<main\b[^>]*>(.*?)</main>", html, re.IGNORECASE | re.DOTALL)
    article_match = re.search(r"<article\b[^>]*>(.*?)</article>", html, re.IGNORECASE | re.DOTALL)
    if main_match:
        scope_html = main_match.group(1)
        used_scope = True
    elif article_match:
        scope_html = article_match.group(1)
        used_scope = True
    else:
        scope_html = html

    alts: list[str] = []
    for m in re.finditer(r"<img\b[^>]*>", scope_html, re.IGNORECASE):
        tag = m.group(0)
        alt_m = re.search(r'\balt=["\']([^"\']*)["\']', tag, re.IGNORECASE)
        alts.append(alt_m.group(1) if alt_m else "__MISSING__")
    return alts, used_scope


def count_figure_pairs(html: str) -> int:
    """Count <figure>...<figcaption>...</figure> pairs anywhere in the
    document. HTML5 spec requires figcaption inside figure."""
    figs = re.findall(r"<figure\b[^>]*>(.*?)</figure>", html, re.IGNORECASE | re.DOTALL)
    return sum(1 for body in figs if re.search(r"<figcaption\b", body, re.IGNORECASE))


def count_tables(html: str) -> int:
    """Count <table> tags, excluding nav/header/footer regions."""
    stripped = re.sub(
        r"<(nav|header|footer)\b[^>]*>.*?</\1>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return len(re.findall(r"<table\b", stripped, re.IGNORECASE))


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="14-multimodal-markup")

    # Gate: opt-in via config.
    if config.get("multimodal_markup_check") is not True:
        result.findings.append(Finding(
            id="14.skipped", severity="INFO",
            title="Multimodal-markup check skipped (multimodal_markup_check not set in .launch-readiness.yml)",
            notes=(
                "Opt-in: set `multimodal_markup_check: true` in config to audit "
                "content-image figcaption density, alt-text density, and HTML-"
                "table presence. Backed by SearchVIU 2025 + Williams-Cook Duck "
                "Test (Feb 2026): LLM citation engines parse visible HTML, not "
                "hidden metadata. Practitioner-tier evidence (Aleyda Solís AI-"
                "search checklist) — findings default to INFO/PASS, WARN only "
                "on unambiguously sparse pages with >=3 content images."
            ),
        ))
        return result

    figcaption_pass = float(config.get("multimodal_figcaption_pass", FIGCAPTION_PASS))
    figcaption_warn = float(config.get("multimodal_figcaption_warn", FIGCAPTION_WARN))
    alt_text_pass = float(config.get("multimodal_alt_text_pass", ALT_TEXT_PASS))
    alt_text_warn = float(config.get("multimodal_alt_text_warn", ALT_TEXT_WARN))
    sample_size = int(config.get("multimodal_sample_size", DEFAULT_SAMPLE_SIZE))

    # Locate build-output HTML root.
    html_roots = ["dist/public", "out", "_site", "public", "build"]
    html_root = next((repo / r for r in html_roots if (repo / r).exists()), None)
    if not html_root:
        result.findings.append(Finding(
            id="14.no_build", severity="MANUAL_VERIFY",
            title="No build-output directory found (dist/public, out, _site, public, build); cannot sample HTML",
            fix_action="Run the build pipeline before re-running the multimodal-markup check.",
        ))
        return result

    # Sample candidates: home, /about, plus piece pages from common roots.
    candidates: list[Path] = []
    for p in (html_root / "index.html", html_root / "about" / "index.html"):
        if p.exists():
            candidates.append(p)
    for piece_dir in ("writing", "blog", "posts", "articles"):
        pdir = html_root / piece_dir
        if pdir.exists():
            pieces = sorted(pdir.rglob("index.html"))
            candidates.extend(pieces[: sample_size - len(candidates)])
            if len(candidates) >= sample_size:
                break

    if not candidates:
        result.findings.append(Finding(
            id="14.no_pages", severity="MANUAL_VERIFY",
            title="No HTML pages found to sample for multimodal markup",
        ))
        return result

    total_imgs = 0
    total_with_alt = 0
    total_figcaption_paired = 0
    total_tables = 0
    pages_no_scope = 0
    pages_scanned = 0

    for page in candidates:
        try:
            html = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pages_scanned += 1
        alts, used_scope = find_content_images(html)
        if not used_scope:
            pages_no_scope += 1
        total_imgs += len(alts)
        total_with_alt += sum(1 for a in alts if a != "__MISSING__")
        total_figcaption_paired += count_figure_pairs(html)
        total_tables += count_tables(html)

    if pages_scanned == 0:
        result.findings.append(Finding(
            id="14.no_readable_pages", severity="MANUAL_VERIFY",
            title="Sampled HTML pages were unreadable",
        ))
        return result

    if total_imgs == 0:
        result.findings.append(Finding(
            id="14.no_content_images", severity="INFO",
            title=f"No <img> tags found in content scope across {pages_scanned} sampled pages",
            notes=(
                "Site may be text-only or use background-image CSS for visuals. "
                "Multimodal markup not applicable to images. Tabular content "
                "audit below still applies."
            ),
        ))
    else:
        figcaption_ratio = total_figcaption_paired / total_imgs
        alt_text_ratio = total_with_alt / total_imgs

        # Figcaption density finding.
        if figcaption_ratio >= figcaption_pass:
            result.findings.append(Finding(
                id="14.figcaption_dense", severity="PASS",
                title=(
                    f"{total_figcaption_paired}/{total_imgs} content images are "
                    f"wrapped in <figure>/<figcaption> ({figcaption_ratio:.0%})"
                ),
                notes=(
                    "figcaption sits in the rendered DOM and binds visual "
                    "context to the image — LLM citation engines pick this up "
                    "where they ignore JSON-LD ImageObject.description."
                ),
            ))
        elif figcaption_ratio < figcaption_warn and total_imgs >= MIN_IMGS_FOR_WARN:
            result.findings.append(Finding(
                id="14.figcaption_sparse", severity="WARN",
                title=(
                    f"Only {total_figcaption_paired}/{total_imgs} content images "
                    f"have <figure>/<figcaption> ({figcaption_ratio:.0%})"
                ),
                expected=f">={figcaption_pass:.0%} figcaption density on content images",
                fix_safety="manual",
                fix_action=(
                    "Wrap content images in <figure>...<figcaption>caption</figcaption></figure>. "
                    "Caption should bind visual context to the image (subject, "
                    "credit, date, source). Avoid empty captions or alt= duplicates."
                ),
                notes=(
                    "Practitioner-consensus tier (Aleyda Solís AI-search "
                    "checklist) + SearchVIU 2025 'visible HTML wins' alignment. "
                    "Not a confirmed ranking signal — but figcaption is the "
                    "load-bearing surface for LLMs to pick up image context "
                    "when JSON-LD ImageObject is ignored."
                ),
            ))
        else:
            result.findings.append(Finding(
                id="14.figcaption_partial", severity="INFO",
                title=(
                    f"{total_figcaption_paired}/{total_imgs} content images have "
                    f"<figure>/<figcaption> ({figcaption_ratio:.0%}) — partial coverage"
                ),
                notes="Direction is fine; consider wrapping more content images for LLM-extractable captions.",
            ))

        # Alt-text density finding.
        if alt_text_ratio >= alt_text_pass:
            result.findings.append(Finding(
                id="14.alt_text_dense", severity="PASS",
                title=(
                    f"{total_with_alt}/{total_imgs} content images carry alt= "
                    f"({alt_text_ratio:.0%})"
                ),
                notes=(
                    "Empty alt='' counts as present (decorative-image semantics). "
                    "LLM-extractable as image context where JSON-LD "
                    "ImageObject.caption is ignored."
                ),
            ))
        elif alt_text_ratio < alt_text_warn and total_imgs >= MIN_IMGS_FOR_WARN:
            result.findings.append(Finding(
                id="14.alt_text_sparse", severity="WARN",
                title=(
                    f"Only {total_with_alt}/{total_imgs} content images carry alt= "
                    f"({alt_text_ratio:.0%})"
                ),
                expected=f">={alt_text_pass:.0%} alt-text density on content images",
                fix_safety="manual",
                fix_action=(
                    "Add alt= to every content image. Descriptive alt for "
                    "informational images; alt='' for decorative. Existing a11y "
                    "tools (Lighthouse, axe-core) flag this from a screen-reader "
                    "angle; the IEO/GEO angle is the same DOM surface for LLM "
                    "image-context extraction."
                ),
                notes="Widely covered by a11y tooling; audited here from the IEO/GEO angle.",
            ))
        else:
            result.findings.append(Finding(
                id="14.alt_text_partial", severity="INFO",
                title=(
                    f"{total_with_alt}/{total_imgs} content images carry alt= "
                    f"({alt_text_ratio:.0%}) — partial coverage"
                ),
                notes="Consider promoting to full alt-text coverage; see Lighthouse / axe-core for the a11y-side audit.",
            ))

    # Tables informational finding.
    if total_tables > 0:
        result.findings.append(Finding(
            id="14.tables_present", severity="INFO",
            title=f"{total_tables} <table> elements detected across {pages_scanned} sampled pages",
            notes=(
                "HTML tables are LLM-extractable as tabular data. Screenshots "
                "of tables are NOT (SearchVIU 2025). If the site renders "
                "tabular content as images, convert to HTML tables "
                "(<table>/<thead>/<tbody>/<tr>/<td>) for citation-eligibility."
            ),
        ))
    elif total_imgs >= 5:
        result.findings.append(Finding(
            id="14.no_tables_image_heavy", severity="INFO",
            title=(
                f"No <table> elements across {pages_scanned} sampled pages, but "
                f"{total_imgs} content images detected"
            ),
            notes=(
                "Image-heavy site with no HTML tables. If any of those images "
                "render tabular data (charts, comparison tables, screenshots of "
                "data), LLMs cannot extract them as data. Consider converting "
                "to HTML tables."
            ),
        ))

    # Note when content scope couldn't be detected on any page.
    if pages_no_scope == pages_scanned and total_imgs > 0:
        result.findings.append(Finding(
            id="14.no_content_scope", severity="INFO",
            title=(
                "Could not isolate <main> or <article> on any sampled page; "
                "counted all <img> tags (may include chrome / logos / icons)"
            ),
            notes=(
                "Findings above may overcount chrome images. Consider wrapping "
                "primary content in <main> or <article> for cleaner content-"
                "image isolation in this and other audits."
            ),
        ))

    fig_pct = (total_figcaption_paired / total_imgs * 100) if total_imgs else 0
    alt_pct = (total_with_alt / total_imgs * 100) if total_imgs else 0
    result.summary = (
        f"Multimodal-markup: {pages_scanned} pages scanned. "
        f"Content imgs: {total_imgs}, figcaption: {total_figcaption_paired} "
        f"({fig_pct:.0f}%), alt: {total_with_alt} ({alt_pct:.0f}%), "
        f"tables: {total_tables}."
    )
    result.config_used = {
        "multimodal_markup_check": True,
        "figcaption_pass": figcaption_pass,
        "figcaption_warn": figcaption_warn,
        "alt_text_pass": alt_text_pass,
        "alt_text_warn": alt_text_warn,
        "sample_size": sample_size,
    }
    return result


if __name__ == "__main__":
    parser = base_argparser("14-multimodal-markup")
    args = parser.parse_args()
    emit(run(args))
