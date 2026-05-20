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
                ("Per Princeton/Georgia Tech KDD 2024 + 2026 followups, these tactics correlate with LLM citation lift." if tactic in ("inline_citation", "quotation", "firstparty_data") else "")
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
                "see 9.fanout.advisory."
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
