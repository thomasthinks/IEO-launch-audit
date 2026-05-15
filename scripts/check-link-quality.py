#!/usr/bin/env python3
"""
Check 08 — Internal-link quality.

Identifies the TFIDF trap: inline links with single-word generic anchors
linking to topically-unrelated targets. Reports anchor-text quality +
density + JSON-LD mentions[] quality.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact, load_config, time_check,
)


INLINE_LINK_RE = re.compile(r'<a\s+[^>]*href=["\']/(writing|posts|essays|articles)/([^"\']+)["\'][^>]*>([^<]+)</a>')


def count_words_in_paragraphs(text: str) -> int:
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL)
    words = 0
    for p in paragraphs:
        plain = re.sub(r"<[^>]+>", " ", p)
        words += len(plain.split())
    return words


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="08-internal-link-quality")

    # Find piece TSX/HTML files
    content_roots = [
        repo / "client/src/content/writing",
        repo / "src/content",
        repo / "content/posts",
        repo / "content/essays",
        repo / "content",
    ]
    content_dir = None
    for root in content_roots:
        if root.exists():
            content_dir = root
            break

    if not content_dir:
        result.findings.append(Finding(
            id="8.0.no_content", severity="MANUAL_VERIFY",
            title="No content directory found at common locations",
            fix_safety="manual",
            fix_action="Set content path manually or audit inline links per piece.",
        ))
        return result

    # Glob piece files. Use rglob (recursive) only; that already covers
    # both top-level and nested pieces. The prior implementation also
    # globbed `*.tsx` at top-level which double-counted in flat layouts.
    pieces = list(set(content_dir.rglob("*.tsx")) | set(content_dir.rglob("*.md")))
    if not pieces:
        result.findings.append(Finding(
            id="8.0.no_pieces", severity="MANUAL_VERIFY",
            title=f"No content files found at {content_dir}",
        ))
        return result

    total_links = 0
    single_word_links = 0
    multiword_named_concept_links = 0
    pieces_over_density = 0
    pieces_with_links = 0
    target_titles: dict[str, str] = {}

    # First pass: build slug→title index (for cross-checking anchor relevance)
    for p in pieces:
        text = p.read_text(encoding="utf-8")
        m_slug = re.search(r'slug:\s*["\']([^"\']+)["\']', text)
        m_title = re.search(r'title:\s*["\']([^"\']+)["\']', text)
        if m_slug and m_title:
            target_titles[m_slug.group(1)] = m_title.group(1)

    # Second pass: link quality
    for p in pieces:
        text = p.read_text(encoding="utf-8")
        matches = INLINE_LINK_RE.findall(text)
        if not matches:
            continue
        pieces_with_links += 1
        words = count_words_in_paragraphs(text) or 1
        link_count = len(matches)
        density = link_count / (words / 500) if words else 0
        if density > 2:
            pieces_over_density += 1
        total_links += link_count

        for _section, slug, anchor in matches:
            anchor = anchor.strip()
            anchor_words = anchor.split()
            if len(anchor_words) == 1:
                single_word_links += 1
            elif len(anchor_words) >= 2:
                target_title = target_titles.get(slug, "").lower()
                if target_title and anchor.lower() in target_title:
                    multiword_named_concept_links += 1

    # 8.1 — Single-word generic anchors
    if total_links > 0:
        sw_pct = single_word_links * 100 / total_links
        if sw_pct >= 30:
            result.findings.append(Finding(
                id="8.1.single_word", severity="FAIL",
                title=f"{single_word_links}/{total_links} ({sw_pct:.0f}%) inline links use single-word anchors (TFIDF trap)",
                fix_safety="safe",
                fix_action="Strip mechanical TFIDF auto-injected links; replace with hand-curated or LLM-curated.",
            ))
        elif sw_pct >= 10:
            result.findings.append(Finding(
                id="8.1.single_word", severity="WARN",
                title=f"{single_word_links}/{total_links} ({sw_pct:.0f}%) inline links use single-word anchors",
                fix_safety="manual",
            ))
        else:
            result.findings.append(Finding(
                id="8.1.single_word", severity="PASS",
                title=f"{single_word_links}/{total_links} ({sw_pct:.0f}%) single-word anchors (within tolerance)",
            ))

        # 8.2 — Anchor matches target title (named-concept signal)
        nc_pct = multiword_named_concept_links * 100 / total_links
        result.findings.append(Finding(
            id="8.2.named_concept", severity="PASS" if nc_pct >= 30 else "INFO",
            title=f"{multiword_named_concept_links}/{total_links} ({nc_pct:.0f}%) inline links anchor on target title text",
            notes="Higher is better; named-concept anchors match target piece's load-bearing claim.",
        ))

        # 8.3 — Density
        if pieces_over_density > 0:
            result.findings.append(Finding(
                id="8.3.density", severity="WARN",
                title=f"{pieces_over_density} pieces have >2 inline links per 500w (over Stratechery-model target)",
                fix_safety="manual",
                fix_action="Reduce inline-link density; surface relatedness via end-of-piece block instead.",
            ))
        else:
            result.findings.append(Finding(
                id="8.3.density", severity="PASS",
                title="Inline-link density within Stratechery-model target (<= 2 per 500w)",
            ))
    else:
        result.findings.append(Finding(
            id="8.1.no_inline_links", severity="INFO",
            title="No inline internal links detected in content; consider hand-curated named-concept links",
            fix_safety="manual",
        ))

    # 8.4 — JSON-LD article-to-article graph density. v0.7 accepts EITHER
    # citation[] (typed, section-anchored; v0.7 emitter) OR mentions[]
    # (loose graph; v0.6 emitter). Either signal is sufficient for the
    # density check -- crawlers parse both. If the consumer has migrated
    # to citation[] entirely (mentions[] dropped), the check still passes
    # against the citation[] count.
    graph_path = find_artifact(repo, config, "schema_graph_json", [
        "dist/public/schema-graph.json", "public/schema-graph.json",
    ])
    if graph_path:
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            articles = [n for n in graph.get("@graph", [])
                        if n.get("@type") in ("Article", "ScholarlyArticle")]
            graph_counts = [
                len(a.get("mentions", [])) + len(a.get("citation", []))
                for a in articles
            ]
            if graph_counts:
                avg = sum(graph_counts) / len(graph_counts)
                with_any = sum(1 for c in graph_counts if c > 0)
                pct_with = with_any * 100 / len(graph_counts)
                # Identify which signal predominates for the title.
                cite_total = sum(len(a.get("citation", [])) for a in articles)
                mentions_total = sum(len(a.get("mentions", [])) for a in articles)
                signal = (
                    "citation[]" if cite_total >= mentions_total
                    else "mentions[]"
                )
                result.findings.append(Finding(
                    id="8.4.graph_density",
                    severity="PASS" if pct_with >= 40 else "WARN",
                    title=(
                        f"{with_any}/{len(graph_counts)} ({pct_with:.0f}%) "
                        f"articles have {signal} edges; avg {avg:.1f} per piece"
                    ),
                ))
        except Exception:
            pass

    result.summary = (
        f"Internal links: {total_links} total across {pieces_with_links} pieces. "
        f"Single-word: {single_word_links} ({single_word_links * 100 // total_links if total_links else 0}%). "
        f"Over-density pieces: {pieces_over_density}."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("08-internal-link-quality")
    args = parser.parse_args()
    emit(run(args))
