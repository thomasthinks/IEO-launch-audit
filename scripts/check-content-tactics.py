#!/usr/bin/env python3
"""
Check 09 — Content tactics (advisory).

Per-piece scoring against the 9-item content posture checklist. Emits
corpus-level coverage summary + per-piece flags.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


def has_thesis_block(text: str) -> bool:
    return "data-thesis-block" in text


def has_inline_citation(text: str) -> bool:
    # Crude: presence of "(Outlet, Year)" or "et al." or "Year)"
    return bool(re.search(r"\(\w[^)]{2,40},\s*(19|20)\d{2}\)|et\s+al\.?", text))


def has_quotation(text: str) -> bool:
    # Multi-character quoted span in body, OR <blockquote>
    return bool(re.search(r'"[^"]{40,}"|<blockquote', text))


def has_firstparty_data(text: str) -> bool:
    # Heuristic: dollar amounts, percentages with named contexts, named years
    return bool(re.search(r'\$\d[\d,.]*\s?[BMK]?|\d+%\s+\w', text))


def has_qa_subheads(text: str) -> bool:
    return bool(re.search(r"<h[23][^>]*>[^<]*\?\s*</h[23]>", text))


def has_year_in_title(text: str) -> bool:
    m = re.search(r'title:\s*["\'][^"\']*\b(19|20)\d{2}\b[^"\']*["\']', text)
    return bool(m)


def has_author_byline(text: str) -> bool:
    return bool(re.search(r"author-byline|className=\"byline|byline-block", text, re.IGNORECASE))


def has_first_person(text: str) -> bool:
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL)
    if not paragraphs:
        return False
    body = " ".join(paragraphs)
    return bool(re.search(r"\bI\s+(am|was|have|had|wrote|saw|ran|built|watched|operated)\b", body))


# v0.4: AI-content fingerprint detection
def extract_body_text(text: str) -> str:
    """Plain-text body from TSX/HTML/MD."""
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL)
    if not paragraphs:
        # Markdown fallback: take everything after the second '---' frontmatter
        m = re.match(r"^---\n.*?\n---\n(.*)", text, re.DOTALL)
        body = m.group(1) if m else text
        body = re.sub(r"^#+ ", "", body, flags=re.MULTILINE)  # strip headers
    else:
        body = " ".join(paragraphs)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body)
    return body.strip()


def sentence_length_variance(body: str) -> tuple[float, float]:
    """Return (mean, stddev) of sentence-length-in-words. Uniformity = AI fingerprint."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'(\[])", body)
    lengths = [len(s.split()) for s in sentences if s.strip() and len(s.split()) >= 3]
    if len(lengths) < 5:
        return 0.0, 0.0
    mean = sum(lengths) / len(lengths)
    variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return mean, variance ** 0.5


def transition_word_density(body: str) -> float:
    """Overused transition words signal machine-generated prose. Per 1000w."""
    transitions = [
        r"\bmoreover\b", r"\bfurthermore\b", r"\badditionally\b",
        r"\bconsequently\b", r"\bhowever\b", r"\btherefore\b",
        r"\bin addition\b", r"\bin conclusion\b", r"\bnotably\b",
        r"\bsignificantly\b", r"\bclearly\b",
    ]
    words = len(body.split()) or 1
    hits = sum(len(re.findall(t, body, re.IGNORECASE)) for t in transitions)
    return hits / words * 1000


def em_dash_density(body: str) -> float:
    """Em-dashes per 500 words; >2/500w is a common AI signal."""
    em_dashes = body.count("—") + len(re.findall(r"&mdash;", body))
    words = len(body.split()) or 1
    return em_dashes / words * 500


# v1.5.1 — check 9.10 front-loading signals.
#
# Indig "The science of how AI pays attention" (Growth Memo, Feb 2026):
# 18,012 verified citations from 1.2M ChatGPT responses; 44.2% from first
# 30% of text; entity density 20.6% in cited text vs 5-8% baseline;
# definitive language in 36.2% of cited text vs 20.2% uncited. p<0.0001.
# All-MiniLM-L6-v2 semantic embeddings @ cosine 0.55.
#
# Mechanistic prior: Liu et al. "Lost in the Middle" (TACL 2024,
# peer-reviewed) — LLMs preferentially attend to beginning + end of
# context. Verified primary, but measures in-context retrieval not
# web-citation; cite as mechanism, not direct replication.
#
# ChatGPT-only boundary is mandatory in finding text (Indig's data is
# ChatGPT-only).
_DECLARATIVE_COPULA_RE = re.compile(
    r"\b\w[\w\-]+\s+(is|are|means|refers\s+to|involves|denotes|describes)\s+\w",
    re.IGNORECASE,
)

_HEADING_RE = re.compile(
    r"<h[23]\b[^>]*>(.*?)</h[23]>|^\s*#{2,3}\s+(.+)$",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


def extract_headings(text: str) -> list[str]:
    """Return visible H2/H3-ish headings from HTML/TSX/Markdown."""
    headings: list[str] = []
    for html_h, md_h in _HEADING_RE.findall(text):
        raw = html_h or md_h
        cleaned = re.sub(r"<[^>]+>", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            headings.append(cleaned)
    return headings


def evidence_container_types(text: str, body: str) -> set[str]:
    """Detect extractable answer-support units from visible-ish content.

    These are observational citation-absorption features from 2026 GEO
    research, not causal guarantees.
    """
    combined = f"{body}\n{text}"
    headings = extract_headings(text)
    heading_blob = " ".join(headings)
    found: set[str] = set()
    if re.search(
        r"\b([A-Z][\w\- ]{1,60}\s+)?(is|are|means|refers\s+to|is\s+defined\s+as)\b",
        body,
        re.IGNORECASE,
    ):
        found.add("definitions")
    if (
        re.search(r"\b(vs\.?|versus|compared\s+with|compared\s+to|alternative[s]?|pros\s+and\s+cons)\b", combined, re.IGNORECASE)
        or re.search(r"\b(compare|comparison|alternatives?|tradeoffs?|pros|cons)\b", heading_blob, re.IGNORECASE)
        or re.search(r"<table[\s>]", text, re.IGNORECASE)
    ):
        found.add("comparisons")
    if re.search(
        r"(\b\d+(?:\.\d+)?%\b|\b\d+(?:,\d{3})+(?:\.\d+)?\b|\$\d|"
        r"\b\d+(?:\.\d+)?\s*(million|billion|seconds?|minutes?|hours?|days?|months?|years?)\b)",
        body,
        re.IGNORECASE,
    ):
        found.add("numbers")
    if (
        re.search(r"\b(step\s+\d+|first,|second,|third,|finally,|how\s+to|checklist|workflow)\b", combined, re.IGNORECASE)
        or re.search(r"<ol[\s>]", text, re.IGNORECASE)
    ):
        found.add("procedures")
    if re.search(r"```|<pre[\s>]|<code[\s>]", text, re.IGNORECASE):
        found.add("code_examples")
    if len(headings) >= 3 and (re.search(r"<ul[\s>]|<ol[\s>]", text, re.IGNORECASE) or body.count(";") >= 3):
        found.add("structured_units")
    return found


def query_facets(text: str, body: str) -> set[str]:
    """Infer broad query facets a page visibly serves."""
    headings = extract_headings(text)
    heading_blob = " ".join(headings)
    combined = f"{heading_blob}\n{body}"
    facets: set[str] = set()
    if re.search(r"\b(what\s+is|what\s+are|definition|means|refers\s+to|is\s+a|is\s+an)\b", combined, re.IGNORECASE):
        facets.add("definition")
    if re.search(r"\b(compare|comparison|versus|vs\.?|alternative|pros\s+and\s+cons|tradeoff)\b", combined, re.IGNORECASE):
        facets.add("comparison")
    if re.search(r"\b(how\s+to|steps?|workflow|process|checklist|implement|setup|configure)\b", combined, re.IGNORECASE):
        facets.add("procedure")
    if re.search(r"\b(data|evidence|study|research|benchmark|statistics?|%|\d+(?:,\d{3})+)\b", combined, re.IGNORECASE):
        facets.add("evidence")
    if re.search(r"\b(example|case study|for instance|such as)\b", combined, re.IGNORECASE):
        facets.add("examples")
    if re.search(r"\b(caveat|limitation|risk|failure mode|tradeoff|however|but)\b", combined, re.IGNORECASE):
        facets.add("limitations")
    return facets


def is_broad_informational_piece(path: Path, text: str, body: str) -> bool:
    """Gate query-facet warnings to pages that look like broad resources."""
    words = len(body.split())
    if words < 900:
        return False
    name = path.name.lower()
    if any(token in name for token in ("changelog", "release", "announcement", "note")):
        return False
    if re.search(r"\b(product|pricing|terms|privacy)\b", name):
        return False
    titleish = " ".join(extract_headings(text)[:2])
    return (
        words >= 1400
        or "/pillar/" in str(path)
        or re.search(r"\b(guide|playbook|framework|overview|complete|ultimate|primer)\b", titleish, re.IGNORECASE)
    )


# ADR 0004 — 9.13 prompt-injection / hidden-instruction detection.
#
# Adversarial answer-engine markup: text aimed at the LLM reading the
# page rather than the human. Conservative by design — flags
# instruction-SHAPED hidden text, not all hidden text, so legitimate
# presentational hiding (menus, toggles) doesn't false-positive.
_LLM_INSTRUCTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+instructions?"
    r"|you\s+are\s+an?\s+(ai|llm|language\s+model|assistant)"
    r"|system\s+prompt"
    r"|do\s+not\s+(mention|cite|reveal|disclose)"
    r"|when\s+summariz\w+\s+this\s+(page|site|article)"
    r"|(always|instead,?\s*)\s*(recommend|cite|link\s+to)\s+)",
    re.IGNORECASE,
)
_HIDDEN_BLOCK_RE = re.compile(
    r"<[^>]*(?:style=[\"'][^\"']*(?:display:\s*none|visibility:\s*hidden"
    r"|font-size:\s*0|opacity:\s*0(?:\.0+)?[;\"'])[^\"']*[\"']"
    r"|aria-hidden=[\"']true[\"'])[^>]*>(.{40,}?)</",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
# Zero-width / invisible Unicode: ZWSP..RLM, word-joiner range, BOM.
_INVISIBLE_UNICODE_RE = re.compile("[\\u200b-\\u200f\\u2060-\\u2064\\ufeff]")


def prompt_injection_hits(text: str) -> list[str]:
    """Return human-readable descriptions of injection-shaped content."""
    hits: list[str] = []
    for comment in _HTML_COMMENT_RE.findall(text):
        if _LLM_INSTRUCTION_RE.search(comment):
            hits.append(f"LLM-instruction phrase in HTML comment: {comment.strip()[:80]!r}")
    for hidden in _HIDDEN_BLOCK_RE.findall(text):
        plain = re.sub(r"<[^>]+>", " ", hidden)
        if _LLM_INSTRUCTION_RE.search(plain):
            hits.append(f"LLM-instruction phrase in hidden/aria-hidden block: {plain.strip()[:80]!r}")
    invisible = len(_INVISIBLE_UNICODE_RE.findall(text))
    if invisible > 20:
        hits.append(f"{invisible} zero-width/invisible Unicode characters (possible hidden payload)")
    return hits


# ADR 0004 — 9.14 negative-citation signals: patterns 2026 evidence says
# backfire (CTA overload, repeated-term stuffing).
_CTA_RE = re.compile(
    r"\b(sign\s+up|buy\s+now|subscribe|get\s+started|book\s+a\s+demo"
    r"|start\s+(your\s+)?free\s+trial|contact\s+us\s+today|limited\s+time)\b",
    re.IGNORECASE,
)


def cta_density(body: str) -> float:
    """CTA phrases per 1000 words."""
    words = len(body.split()) or 1
    return len(_CTA_RE.findall(body)) / words * 1000


def top_term_share(body: str) -> tuple[str, float]:
    """Most frequent non-stopword term and its share of all words (%).

    A crude stuffing proxy: >4% of body words being one content term is
    unusual for natural prose.
    """
    stop = {
        "the", "and", "for", "that", "with", "this", "you", "your", "are",
        "was", "were", "have", "has", "had", "not", "but", "can", "will",
        "from", "they", "their", "them", "its", "it's", "when", "what",
        "how", "why", "who", "which", "than", "then", "there", "here",
        "into", "onto", "over", "under", "about", "more", "most", "some",
        "all", "also", "just", "like", "one", "two", "our", "out", "use",
    }
    words = [w.lower().strip(".,;:!?\"'()[]") for w in body.split()]
    words = [w for w in words if len(w) >= 3 and w not in stop]
    if len(words) < 100:
        return "", 0.0
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    term, n = max(freq.items(), key=lambda kv: kv[1])
    return term, n * 100 / len(words)


# ADR 0004 — 9.15 dated-currency language ("as of Q3 2026", "updated
# March 2026"). Explicit currency markers correlated with citation in
# July 2026 industry syntheses; advisory only.
_DATED_CURRENCY_RE = re.compile(
    r"\b(as\s+of\s+(early\s+|mid-?\s*|late\s+)?(q[1-4]\s+)?(19|20)\d{2}"
    r"|as\s+of\s+(january|february|march|april|may|june|july|august"
    r"|september|october|november|december)\s+(19|20)\d{2}"
    r"|(updated|last\s+updated|current\s+as\s+of|reviewed)\s*(:|\s+in|\s+on)?\s+"
    r"[a-z]*\s*(19|20)\d{2})",
    re.IGNORECASE,
)


def front_loading_signals(body: str) -> tuple[bool, int]:
    """Compute front-loading signals over the first 30% of body text.

    Returns (has_declarative_claim, entity_count_first_30pct):
    - has_declarative_claim: True if the first 30% of words contains
      at least one declarative copula pattern (X is Y / X means Y /
      X refers to Y / X involves Y / X denotes Y / X describes Y).
    - entity_count_first_30pct: count of distinct multi-word title-
      cased phrases in the first 30% (proxy for named entity density).
    """
    words = body.split()
    if len(words) < 60:
        return False, 0
    first_30_words = words[: max(60, int(len(words) * 0.30))]
    first_30_text = " ".join(first_30_words)
    has_claim = bool(_DECLARATIVE_COPULA_RE.search(first_30_text))
    entities = set()
    for m in re.findall(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b",
        first_30_text,
    ):
        entities.add(m)
    return has_claim, len(entities)


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="09-content-tactics")

    content_roots = [
        repo / "client/src/content/writing",
        repo / "src/content", repo / "content/posts", repo / "content/essays",
    ]
    content_dir = next((r for r in content_roots if r.exists()), None)
    if not content_dir:
        result.findings.append(Finding(
            id="9.0.no_content", severity="MANUAL_VERIFY",
            title="No content directory found",
        ))
        return result

    pieces = list(content_dir.glob("*.tsx"))
    if not pieces:
        pieces = list(content_dir.rglob("*.md"))

    if not pieces:
        result.findings.append(Finding(
            id="9.0.empty", severity="MANUAL_VERIFY",
            title="No piece files found",
        ))
        return result

    counts = {
        "thesis_block": 0, "inline_citation": 0, "quotation": 0,
        "firstparty_data": 0, "qa_subheads": 0, "author_byline": 0,
        "first_person": 0, "no_year_in_title": 0,
    }
    # v0.4: AI-content fingerprint aggregates
    sentence_means: list[float] = []
    sentence_stddevs: list[float] = []
    transition_densities: list[float] = []
    em_dash_densities: list[float] = []
    # v1.5.1: front-loading aggregates (check 9.10).
    front_loaded_pieces = 0       # pieces with claim + ≥2 entities in first 30%
    pieces_with_claim = 0
    pieces_with_entity_density = 0   # ≥2 entities in first 30%
    front_loading_scored = 0      # pieces with ≥60w body (denominator)
    # ADR 0003 — citation-absorption / multi-query stability signals.
    evidence_scored = 0
    evidence_strong = 0
    evidence_mixed = 0
    evidence_type_counts: dict[str, int] = {}
    query_facet_scored = 0
    query_facet_strong = 0
    query_facet_narrow: list[str] = []
    query_facet_counts: dict[str, int] = {}
    # ADR 0004 — 9.13/9.14/9.15 aggregates.
    injection_hits_by_piece: list[tuple[str, list[str]]] = []
    cta_densities: list[float] = []
    stuffing_flagged: list[tuple[str, str, float]] = []  # (piece, term, share%)
    negative_signal_scored = 0
    dated_currency_pieces = 0
    dated_currency_scored = 0

    total = len(pieces)
    for p in pieces:
        text = p.read_text(encoding="utf-8")
        if has_thesis_block(text):
            counts["thesis_block"] += 1
        if has_inline_citation(text):
            counts["inline_citation"] += 1
        if has_quotation(text):
            counts["quotation"] += 1
        if has_firstparty_data(text):
            counts["firstparty_data"] += 1
        if has_qa_subheads(text):
            counts["qa_subheads"] += 1
        if has_author_byline(text):
            counts["author_byline"] += 1
        if has_first_person(text):
            counts["first_person"] += 1
        if not has_year_in_title(text):
            counts["no_year_in_title"] += 1

        # v0.4 fingerprint metrics
        body = extract_body_text(text)
        if body and len(body.split()) >= 50:
            m, s = sentence_length_variance(body)
            if m > 0:
                sentence_means.append(m)
                sentence_stddevs.append(s)
            transition_densities.append(transition_word_density(body))
            em_dash_densities.append(em_dash_density(body))

        # v1.5.1: 9.10 front-loading signals.
        if body and len(body.split()) >= 60:
            front_loading_scored += 1
            has_claim, entity_count = front_loading_signals(body)
            if has_claim:
                pieces_with_claim += 1
            if entity_count >= 2:
                pieces_with_entity_density += 1
            if has_claim and entity_count >= 2:
                front_loaded_pieces += 1

        if body and len(body.split()) >= 150:
            evidence_scored += 1
            evidence_types = evidence_container_types(text, body)
            for t in evidence_types:
                evidence_type_counts[t] = evidence_type_counts.get(t, 0) + 1
            if len(evidence_types) >= 2:
                evidence_strong += 1
            elif len(evidence_types) == 1:
                evidence_mixed += 1

        if body and is_broad_informational_piece(p, text, body):
            query_facet_scored += 1
            facets = query_facets(text, body)
            for facet in facets:
                query_facet_counts[facet] = query_facet_counts.get(facet, 0) + 1
            if len(facets) >= 4:
                query_facet_strong += 1
            elif len(facets) <= 2:
                query_facet_narrow.append(p.name)

        # ADR 0004 — 9.13 prompt-injection scan runs on RAW text (hidden
        # markup is by definition outside extracted body text).
        hits = prompt_injection_hits(text)
        if hits:
            injection_hits_by_piece.append((p.name, hits))

        # ADR 0004 — 9.14/9.15 body-side signals.
        if body and len(body.split()) >= 150:
            negative_signal_scored += 1
            cta_densities.append(cta_density(body))
            term, share = top_term_share(body)
            if share > 4.0:
                stuffing_flagged.append((p.name, term, round(share, 1)))
            dated_currency_scored += 1
            if _DATED_CURRENCY_RE.search(body):
                dated_currency_pieces += 1

    # Translate to findings
    def pct(n: int) -> float:
        return n * 100 / total if total else 0

    for tactic, n in counts.items():
        p = pct(n)
        severity = "PASS" if p >= 70 else ("WARN" if p >= 40 else "INFO")
        result.findings.append(Finding(
            id=f"9.{tactic}", severity=severity,
            title=f"{n}/{total} ({p:.0f}%) pieces exhibit '{tactic.replace('_', ' ')}'",
            fix_safety="manual",
            notes=(
                "Advisory; this check does not block flip. " +
                ("Per Princeton/Georgia Tech KDD 2024 + 2026 followups, these tactics correlate with LLM citation lift. "
                 "Caution (ADR 0004, 2026-07 critical survey of 45 studies): such gains are stage-local — "
                 "over-optimizing body content for citation has been measured to REDUCE retrieval presence 9-16%; "
                 "apply only where editorially true." if tactic in ("inline_citation", "quotation", "firstparty_data") else "")
            ),
        ))

    # v0.4 — AI-content fingerprint findings
    if sentence_stddevs:
        # Cross-corpus average stddev; uniform stddev across pieces = AI signal
        avg_stddev = sum(sentence_stddevs) / len(sentence_stddevs)
        avg_mean = sum(sentence_means) / len(sentence_means)
        # Human variance typically 8-15 words for essay prose
        if avg_stddev < 6:
            result.findings.append(Finding(
                id="9.fp.sentence_uniformity", severity="WARN",
                title=f"Low sentence-length variance: avg stddev={avg_stddev:.1f}, mean={avg_mean:.1f} words",
                fix_safety="manual",
                notes="Stddev <6 across the corpus is an AI-content detection signal. Human essay prose typically stddev 8-15.",
            ))
        else:
            result.findings.append(Finding(
                id="9.fp.sentence_variance", severity="PASS",
                title=f"Sentence-length variance: avg stddev={avg_stddev:.1f}, mean={avg_mean:.1f} (human-like)",
            ))

    if transition_densities:
        avg_trans = sum(transition_densities) / len(transition_densities)
        if avg_trans > 8:
            result.findings.append(Finding(
                id="9.fp.transition_overuse", severity="WARN",
                title=f"Transition-word density: avg {avg_trans:.1f}/1000w (AI fingerprint risk)",
                fix_safety="manual",
                notes="Phrases like 'moreover/furthermore/additionally/consequently' at >8/1000w across corpus is a common AI signal.",
            ))
        else:
            result.findings.append(Finding(
                id="9.fp.transitions", severity="PASS",
                title=f"Transition-word density within normal range: {avg_trans:.1f}/1000w",
            ))

    if em_dash_densities:
        avg_em = sum(em_dash_densities) / len(em_dash_densities)
        max_em = max(em_dash_densities)
        if avg_em > 2.5:
            result.findings.append(Finding(
                id="9.fp.em_dash_density", severity="WARN",
                title=f"Em-dash density: avg {avg_em:.2f}/500w, max {max_em:.2f}/500w",
                fix_safety="manual",
                notes="Em-dash overuse is a strong AI-content fingerprint. Target ≤2/500w.",
            ))
        else:
            result.findings.append(Finding(
                id="9.fp.em_dashes", severity="PASS",
                title=f"Em-dash density: avg {avg_em:.2f}/500w (within range)",
            ))

    # 9.10 — Front-loading positional signals (v1.5.1).
    #
    # Indig "The science of how AI pays attention" (Growth Memo Feb 2026)
    # measured 18,012 ChatGPT citations and found 44.2% concentrated in the
    # first 30% of text; entity density 20.6% in cited passages vs 5-8%
    # baseline; definitive language in 36.2% of cited text vs 20.2% uncited.
    # Methodology disclosed: all-MiniLM-L6-v2 sentence embeddings @ cosine
    # 0.55, p<0.0001. ChatGPT-only — boundary preserved in finding text.
    #
    # Heuristic per piece (first 30% of body words):
    #   - declarative copula (X is Y / X means Y / X refers to Y / etc.)
    #   - ≥2 distinct title-cased multi-word entities (proxy for entity density)
    # A piece is "front-loaded" when both signals fire.
    if front_loading_scored > 0:
        pct_front_loaded = front_loaded_pieces * 100 / front_loading_scored
        pct_claim = pieces_with_claim * 100 / front_loading_scored
        pct_entity = pieces_with_entity_density * 100 / front_loading_scored
        if pct_front_loaded >= 60:
            severity = "PASS"
        elif pct_front_loaded >= 30:
            severity = "INFO"
        else:
            severity = "WARN"
        result.findings.append(Finding(
            id="9.10.front_loading", severity=severity,
            title=(
                f"{front_loaded_pieces}/{front_loading_scored} "
                f"({pct_front_loaded:.0f}%) pieces front-load a declarative "
                "claim + ≥2 entities in the first 30% of body text"
            ),
            current={
                "pieces_with_declarative_claim_in_first_30pct": (
                    f"{pieces_with_claim}/{front_loading_scored} ({pct_claim:.0f}%)"
                ),
                "pieces_with_entity_density_in_first_30pct": (
                    f"{pieces_with_entity_density}/{front_loading_scored} ({pct_entity:.0f}%)"
                ),
            },
            fix_safety="manual",
            fix_action=(
                "For pieces that fail: rewrite the opening so the first ~30% "
                "carries the main definitional claim (X is Y / X means Y) AND "
                "≥2 named entities (people, products, places, terms). Resist "
                "throat-clearing intros. The thesis-first checkpoint (9.1) is "
                "adjacent — same intent, different lens."
            ),
            notes=(
                "Mechanism: Liu et al. 'Lost in the Middle' (TACL 2024, "
                "peer-reviewed) — LLMs preferentially attend to beginning + "
                "end of context. Production-side observation: Indig 18K-"
                "citation methodology (44.2% / first 30%). **ChatGPT-only** "
                "boundary; not yet replicated on Claude / Gemini / Perplexity / "
                "AIO with disclosed methodology. PASS ≥60%, INFO 30-60%, WARN "
                "<30% of pieces front-loaded. Heuristic only — entity density "
                "uses title-cased phrase proxy, not full NER."
            ),
        ))

    # 9.11 — Evidence-container density (ADR 0003).
    #
    # April 2026 citation-absorption research separates source selection
    # from answer-level influence. Pages with higher observed influence
    # are richer in extractable support units: definitions, numerical
    # facts, comparison content, procedural steps, code/examples, and
    # clear structure. This is advisory and observational; do not claim
    # causal lift from adding any one feature.
    if evidence_scored > 0:
        pct_strong = evidence_strong * 100 / evidence_scored
        pct_partial = (evidence_strong + evidence_mixed) * 100 / evidence_scored
        if pct_strong >= 60:
            severity = "PASS"
        elif pct_partial >= 60:
            severity = "INFO"
        else:
            severity = "WARN"
        result.findings.append(Finding(
            id="9.11.evidence_container_density", severity=severity,
            title=(
                f"{evidence_strong}/{evidence_scored} ({pct_strong:.0f}%) "
                "scored pieces expose ≥2 extractable evidence-container types"
            ),
            current={
                "pieces_with_at_least_one_type": (
                    f"{evidence_strong + evidence_mixed}/{evidence_scored} "
                    f"({pct_partial:.0f}%)"
                ),
                "type_counts": dict(sorted(evidence_type_counts.items())),
                "types_tested": [
                    "definitions",
                    "comparisons",
                    "numbers",
                    "procedures",
                    "code_examples",
                    "structured_units",
                ],
            },
            fix_safety="manual",
            fix_action=(
                "For sparse pieces, add visible answer-support units only "
                "where editorially true: definitions, comparison sections, "
                "named numbers/statistics, procedural steps, worked examples, "
                "or list/table structure. Do not add Q&A wrappers as a "
                "substitute for evidence."
            ),
            notes=(
                "ADR 0003 / arXiv:2604.25707: citation selection and "
                "citation absorption differ. High-influence cited pages were "
                "observationally richer in extractable evidence units. This "
                "finding is an advisory structural proxy, not a causal "
                "ranking claim."
            ),
        ))

    # 9.12 — Query-facet coverage / downside-risk advisory (ADR 0003).
    #
    # IF-GEO and related 2026 work warn that optimizing for one query can
    # degrade adjacent intents. Static audit proxy: broad informational
    # pages should usually expose several visible query facets rather than
    # serving only one narrow intent.
    if query_facet_scored > 0:
        pct_strong = query_facet_strong * 100 / query_facet_scored
        if pct_strong >= 60:
            severity = "PASS"
        elif query_facet_narrow:
            severity = "WARN"
        else:
            severity = "INFO"
        result.findings.append(Finding(
            id="9.12.query_facet_coverage", severity=severity,
            title=(
                f"{query_facet_strong}/{query_facet_scored} ({pct_strong:.0f}%) "
                "broad informational pieces cover ≥4 query facets"
            ),
            current={
                "facet_counts": dict(sorted(query_facet_counts.items())),
                "narrow_broad_pages_sample": query_facet_narrow[:10],
                "facets_tested": [
                    "definition",
                    "comparison",
                    "procedure",
                    "evidence",
                    "examples",
                    "limitations",
                ],
            },
            fix_safety="manual",
            fix_action=(
                "For broad guide or pillar pages that are narrow, add missing "
                "facets only when useful to readers: definition, comparison, "
                "procedure, evidence, examples, and limitations/caveats. "
                "Short essays, announcements, product pages, changelogs, and "
                "intentionally narrow pieces are not expected to cover every facet."
            ),
            notes=(
                "ADR 0003 / IF-GEO: multi-query stability matters because "
                "single-query edits can create downside risk for adjacent "
                "intents. This is an INFO-first structural proxy; it does not "
                "run live LLM probes or claim each page needs every facet."
            ),
        ))

    # 9.13 — Prompt-injection / hidden-instruction detection (ADR 0004).
    #
    # Adversarial answer-engine markup is an emerging spam signal for
    # AI-citation trackers and crawler operators. Conservative patterns:
    # instruction-shaped text in HTML comments / hidden-styled blocks /
    # aria-hidden blocks, plus abnormal invisible-Unicode density.
    if injection_hits_by_piece:
        result.findings.append(Finding(
            id="9.13.prompt_injection", severity="WARN",
            title=(
                f"{len(injection_hits_by_piece)}/{total} pieces contain "
                "injection-shaped hidden content aimed at AI readers"
            ),
            current={name: hits for name, hits in injection_hits_by_piece[:10]},
            fix_safety="manual",
            fix_action=(
                "Remove LLM-directed instructions from comments, hidden "
                "blocks, and aria-hidden markup. If flagged text is "
                "legitimate (e.g. a blog post ABOUT prompt injection "
                "quoting examples), verify manually and ignore."
            ),
            notes=(
                "ADR 0004. Patterns flag instruction-SHAPED hidden text "
                "only, not all hidden text. False-positive risk on content "
                "that discusses prompt injection — hence WARN, not FAIL."
            ),
        ))
    else:
        result.findings.append(Finding(
            id="9.13.prompt_injection", severity="PASS",
            title="No injection-shaped hidden content detected across corpus",
        ))

    # 9.14 — Negative-citation signals (ADR 0004): CTA overload +
    # repeated-term stuffing. 2026 evidence (critical survey + peer
    # tooling) treats these as patterns that backfire in AI retrieval.
    if negative_signal_scored > 0:
        avg_cta = sum(cta_densities) / len(cta_densities)
        problems = bool(stuffing_flagged) or avg_cta > 5
        result.findings.append(Finding(
            id="9.14.negative_citation_signals",
            severity="INFO" if problems else "PASS",
            title=(
                f"Negative-signal scan: avg CTA density {avg_cta:.1f}/1000w; "
                f"{len(stuffing_flagged)}/{negative_signal_scored} pieces "
                "flag term-repetition >4%"
            ),
            current={"stuffing_sample": stuffing_flagged[:8]} if stuffing_flagged else None,
            fix_safety="manual",
            fix_action=(
                "For flagged pieces: vary phrasing where one term dominates "
                ">4% of body words; keep CTA phrasing out of informational "
                "body copy. Both patterns read as promotional/stuffed to "
                "retrieval-stage filters."
            ) if problems else None,
            notes=(
                "Advisory only. Keyword-stuffing-style tactics measurably "
                "hurt position-adjusted visibility in 2026 GEO benchmarks; "
                "the >4% single-term share and >5 CTA/1000w thresholds are "
                "conservative heuristics, not published cutoffs."
            ),
        ))

    # 9.15 — Dated-currency language (ADR 0004). Explicit "as of <date>"
    # / "updated <date>" markers in body copy correlated with AI citation
    # in July 2026 industry syntheses. Advisory; sitemap/meta freshness
    # is audited elsewhere — this is the visible-text layer.
    if dated_currency_scored > 0:
        pct_dated = dated_currency_pieces * 100 / dated_currency_scored
        result.findings.append(Finding(
            id="9.15.dated_currency", severity="INFO",
            title=(
                f"{dated_currency_pieces}/{dated_currency_scored} "
                f"({pct_dated:.0f}%) pieces carry explicit dated-currency "
                "language in body text"
            ),
            fix_safety="manual",
            fix_action=(
                "Where accuracy allows, add visible currency markers to "
                "evergreen pieces ('as of Q3 2026', 'updated March 2026'). "
                "Only where true — a fake freshness stamp is worse than none."
            ),
            notes=(
                "Correlational evidence only (Ahrefs/Previsible July 2026 "
                "syntheses: dated language among citation correlates). "
                "Advisory; never a gate."
            ),
        ))

    # 9.fanout — Query Fan-Out retrievability proxy (v1.3).
    #
    # Google AI Mode decomposes user queries into 5-11+ sub-queries (Google
    # Search Central + I/O 2025 blog primary docs). Pages that answer
    # multiple sub-intents get cited at the chunk level — Surfer's 173,902-
    # URL study found 67.82% of AIO citations rank outside top-10 for the
    # parent query, corroborated by Ahrefs Feb 2026 (~62%).
    #
    # The CHECK CANNOT enumerate actual fan-out queries — those are model-
    # generated and stochastic (only 27% reproducible per Surfer). So this
    # is a STRUCTURAL RETRIEVABILITY PROXY: does the page expose the
    # heading-and-passage shape that lets AI engines locate the chunk that
    # answers each sub-query? Heuristic only; honest about the limitation
    # in the finding notes. For true fan-out audits, use the operator
    # advisory below.
    #
    # Heuristic per-piece signals (informed by Phase-2 verification):
    #   1. ≥3 question-shaped H2/H3 headings (sub-intent coverage).
    #   2. Entity diversity in headings (≥3 distinct named entities, very
    #      loose title-case heuristic).
    #   3. FAQPage/HowTo schema OR semantic <dl>/<details> answer blocks.
    #   4. Passage-length variety (avg paragraph word count between 40-150
    #      — chunkable LLM-friendly band).
    QUESTION_STARTERS = (
        "what", "how", "why", "when", "who", "where", "which",
        "is", "are", "do", "does", "can", "should", "will", "would",
    )
    fanout_signals_count = 0
    fanout_pieces_scored = 0
    per_piece_signal_breakdown: list[tuple[str, int]] = []
    for p in pieces:
        text = p.read_text(encoding="utf-8")
        signals = 0
        # Signal 1: question-shaped headings (TSX-style + markdown).
        heading_texts: list[str] = []
        heading_texts.extend(re.findall(r"<h[23]\b[^>]*>(.*?)</h[23]>", text, re.DOTALL | re.IGNORECASE))
        heading_texts.extend(re.findall(r"^\s*#{2,3}\s+(.+)$", text, re.MULTILINE))
        clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in heading_texts]
        clean_headings = [h for h in clean_headings if h]
        question_headings = sum(
            1 for h in clean_headings
            if h.rstrip().endswith("?")
            or h.split()[0].lower() in QUESTION_STARTERS
            if h.split()  # non-empty
        )
        if question_headings >= 3:
            signals += 1
        # Signal 2: entity diversity — title-cased multi-word phrases in
        # headings (very rough; named-concepts proxy). Lower-bound 3
        # distinct ≥2-word title-cased phrases across headings.
        entity_set: set = set()
        for h in clean_headings:
            for m in re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b", h):
                entity_set.add(m)
        if len(entity_set) >= 3:
            signals += 1
        # Signal 3: FAQ/HowTo schema OR semantic answer blocks.
        if (
            re.search(r"FAQPage|HowTo", text, re.IGNORECASE)
            or re.search(r"<dl[\s>]|<details[\s>]", text, re.IGNORECASE)
        ):
            signals += 1
        # Signal 4: passage-length variety (avg paragraph 40-150 words).
        # Use the existing extract_body_text helper.
        body = extract_body_text(text)
        if body:
            paragraphs = re.split(r"\n{2,}", body)
            paragraphs = [p_ for p_ in paragraphs if len(p_.split()) >= 20]
            if paragraphs:
                avg_para_words = sum(len(p_.split()) for p_ in paragraphs) / len(paragraphs)
                if 40 <= avg_para_words <= 150:
                    signals += 1
        per_piece_signal_breakdown.append((str(p.name), signals))
        if signals >= 3:
            fanout_signals_count += 1
        if body and len(body.split()) >= 50:
            fanout_pieces_scored += 1

    if fanout_pieces_scored > 0:
        pct_strong = fanout_signals_count * 100 / fanout_pieces_scored
        severity = "PASS" if pct_strong >= 60 else "INFO"
        result.findings.append(Finding(
            id="9.fanout.heuristic", severity=severity,
            title=(
                f"{fanout_signals_count}/{fanout_pieces_scored} ({pct_strong:.0f}%) "
                "pieces hit ≥3 of 4 Query Fan-Out retrievability signals"
            ),
            current={
                "signal_distribution": {
                    str(s): sum(1 for _n, sig in per_piece_signal_breakdown if sig == s)
                    for s in range(5)
                },
                "signals_tested": [
                    "≥3 question-shaped H2/H3 headings",
                    "≥3 distinct named entities in headings",
                    "FAQPage/HowTo schema OR <dl>/<details> answer blocks",
                    "avg paragraph length 40-150 words (chunkable LLM-friendly band)",
                ],
            },
            fix_safety="manual",
            fix_action=(
                "Reshape under-performing pieces: add question-shaped H2/H3s "
                "(sub-intent coverage); structure answer blocks via <dl>/<details> "
                "or FAQPage schema; trim or split paragraphs into the 40-150 "
                "word chunkable band."
            ),
            notes=(
                "Structural retrievability proxy; cannot enumerate actual "
                "fan-out queries (model-generated, stochastic). Google Search "
                "Central + I/O 2025 confirm the mechanism; Surfer 173,902-URL "
                "+ Ahrefs Feb 2026 confirm 62-68% of AIO citations rank "
                "outside the parent query's top-10. For true fan-out audits, "
                "see 9.fanout.advisory. Caveat (ADR 0004, Search Central "
                "Live Milan 2026-06): 'forcing paragraph chunking for AI is "
                "useless; content organization must follow human readability "
                "criteria' — treat these signals as readability-first "
                "structure, not AI-targeted chunking. July 2026 correlate: "
                "direct Q&A shape (question heading + concise answer) among "
                "citation correlates as AIO citations from top-10 organic "
                "fell 76%→38% over 8 months."
            ),
        ))

    # 9.fanout.advisory — pointer to true fan-out tools (always emit one
    # INFO regardless of heuristic pass/fail).
    result.findings.append(Finding(
        id="9.fanout.advisory", severity="INFO",
        title=(
            "Query Fan-Out coverage requires LLM probe; heuristic check "
            "above is a structural proxy only"
        ),
        fix_safety="manual",
        fix_action=(
            "For true fan-out audits with model-generated sub-queries: "
            "Locomotive Agency's Query Fan-Out Tool (free, patent-methodology "
            "simulation), QueryBurst (free), or Otterly.AI (free tier). The "
            "audit's heuristic is informed by these tools' findings but does "
            "not replicate model behavior."
        ),
        notes=(
            "v1.4 candidate: optional opt-in LLM probe mirroring the v0.5 "
            "curation-scaffold pattern (driver creates batches; subagent "
            "dispatches to Claude/Gemini for fan-out generation + coverage "
            "scoring). Not shipping in v1.3 — stays opt-in to honor the "
            "no-paid-API + stdlib-only stance."
        ),
    ))

    # Coverage rating
    pct_summary = sum(counts.values()) / (len(counts) * total) * 100 if total else 0
    if pct_summary >= 60:
        rating = "GREEN"
    elif pct_summary >= 35:
        rating = "YELLOW"
    else:
        rating = "RED"
    result.findings.append(Finding(
        id="9.coverage_rating", severity="INFO",
        title=f"Overall content-tactics coverage: {rating} ({pct_summary:.0f}% average)",
        notes="GREEN ≥60%, YELLOW 35-60%, RED <35%. Advisory only.",
    ))

    result.summary = f"Content tactics coverage: {rating} ({pct_summary:.0f}% avg across {total} pieces)."
    return result


if __name__ == "__main__":
    parser = base_argparser("09-content-tactics")
    args = parser.parse_args()
    emit(run(args))
