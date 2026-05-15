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
