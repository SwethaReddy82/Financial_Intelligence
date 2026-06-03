"""Evidence separation, coverage metrics, and inference language controls."""

import re
from dataclasses import dataclass
from typing import Literal

CoverageStatus = Literal["complete", "partial", "missing"]

TICKER_DISPLAY_NAMES: dict[str, str] = {
    "JPM": "JPMorgan",
    "RJF": "Raymond James",
    "MS": "Morgan Stanley",
    "GS": "Goldman Sachs",
    "SCHW": "Charles Schwab",
    "AAPL": "Apple",
}

INSUFFICIENT_EVIDENCE = "Insufficient evidence retrieved"

INFERENCE_WORDS = re.compile(
    r"(?i)\b(implied|assumed|likely|probably|perhaps|may have|might have|seems to|appears to)\b"
)

INFERENCE_MARKER = re.compile(r"(?i)\[?\s*inference\s*\]?:")


@dataclass
class CompanyCoverage:
    ticker: str
    display_name: str
    status: CoverageStatus
    chunk_count: int
    strong_chunk_count: int


def display_name_for_ticker(ticker: str) -> str:
    t = (ticker or "?").upper()
    return TICKER_DISPLAY_NAMES.get(t, t)


def compute_company_coverage(
    context: list[dict],
    expected_tickers: list[str] | None = None,
) -> list[CompanyCoverage]:
    """
    complete: >=2 chunks with composite/score >= 0.35 OR >=1 strong + 800+ chars
    partial: at least one chunk but below complete bar
    missing: no chunks for that ticker
    """
    expected = [t.upper() for t in (expected_tickers or []) if t]
    if not expected:
        expected = sorted({(c.get("ticker") or "").upper() for c in context if c.get("ticker")})

    by_ticker: dict[str, list[dict]] = {t: [] for t in expected}
    for c in context:
        t = (c.get("ticker") or "").upper()
        if t in by_ticker:
            by_ticker[t].append(c)

    results: list[CompanyCoverage] = []
    for ticker in expected:
        chunks = by_ticker.get(ticker, [])
        scores = [
            float(c.get("composite_score") or c.get("score") or 0) for c in chunks
        ]
        strong = sum(1 for s in scores if s >= 0.35)
        total_chars = sum(len(c.get("excerpt") or c.get("content") or "") for c in chunks)

        if not chunks:
            status: CoverageStatus = "missing"
        elif strong >= 2 or (strong >= 1 and total_chars >= 800):
            status = "complete"
        else:
            status = "partial"

        results.append(
            CompanyCoverage(
                ticker=ticker,
                display_name=display_name_for_ticker(ticker),
                status=status,
                chunk_count=len(chunks),
                strong_chunk_count=strong,
            )
        )
    return results


def format_coverage_block(coverage: list[CompanyCoverage]) -> str:
    if not coverage:
        return "Coverage:\n(none)"
    lines = ["Coverage:"]
    for c in coverage:
        lines.append(f"{c.display_name} → {c.status}")
    return "\n".join(lines)


def format_retrieved_evidence(context: list[dict], max_excerpt_chars: int = 420) -> str:
    """Verbatim excerpts from retrieval only — not model synthesis."""
    if not context:
        return f"Retrieved Evidence:\n{INSUFFICIENT_EVIDENCE}"

    lines = ["Retrieved Evidence:"]
    for i, c in enumerate(context, start=1):
        meta = c.get("metadata") or {}
        section = c.get("section_name") or meta.get("section_name") or "GENERAL"
        year = meta.get("filing_year") or "?"
        doc = meta.get("source_document") or c.get("form_type") or "filing"
        ticker = c.get("ticker", "?")
        excerpt = (c.get("excerpt") or c.get("content") or "").strip()
        if len(excerpt) > max_excerpt_chars:
            excerpt = excerpt[: max_excerpt_chars - 3].rstrip() + "..."
        score = float(c.get("composite_score") or c.get("score") or 0)
        lines.append(
            f"- [{i}] {display_name_for_ticker(ticker)} ({ticker}) | {section} | {doc} ({year}) "
            f"| relevance={score:.2f}\n  \"{excerpt}\""
        )
    return "\n".join(lines)


def find_unmarked_inference_phrases(text: str) -> list[str]:
    """Words that imply speculation unless the line is explicitly marked as inference."""
    if not text:
        return []
    hits: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or INFERENCE_MARKER.search(stripped):
            continue
        for m in INFERENCE_WORDS.finditer(stripped):
            word = m.group(0).lower()
            if word not in hits:
                hits.append(word)
    return hits


def coverage_confidence_penalty(coverage: list[CompanyCoverage]) -> tuple[float, str]:
    penalty = 0.0
    notes: list[str] = []
    for c in coverage:
        if c.status == "missing":
            penalty += 0.15
            notes.append(f"{c.display_name}: no retrieved chunks")
        elif c.status == "partial":
            penalty += 0.08
            notes.append(f"{c.display_name}: partial coverage ({c.chunk_count} chunks)")
    return min(0.4, penalty), "; ".join(notes)


def inference_confidence_penalty(text: str) -> tuple[float, str]:
    violations = find_unmarked_inference_phrases(text)
    if not violations:
        return 0.0, ""
    penalty = min(0.25, 0.1 + 0.04 * len(violations))
    return penalty, f"Unmarked inference language: {', '.join(violations[:5])}"


def citation_confidence_penalty(citation_coverage: float) -> tuple[float, str]:
    if citation_coverage >= 0.25:
        return 0.0, ""
    if citation_coverage <= 0:
        return 0.2, "No bracket citations [n] in synthesized text"
    return 0.1, f"Low citation coverage ({citation_coverage:.0%})"


def should_refuse_synthesis(
    context: list[dict],
    route: str,
    citation_coverage: float,
    hallucination_risk: float,
    *,
    groundedness_score: float | None = None,
) -> bool:
    """Only block synthesis when evidence is truly inadequate — not missing [n] markers."""
    if route == "refuse" or not context:
        return True
    if groundedness_score is not None and groundedness_score < 0.15:
        return True
    if hallucination_risk >= 0.85:
        return True
    return False


def build_insufficient_response(
    *,
    retrieved_evidence_text: str,
    coverage_text: str,
    validation_notes: str,
    confidence: float,
) -> str:
    return (
        f"{retrieved_evidence_text}\n\n"
        f"{coverage_text}\n\n"
        f"Synthesized Insights:\n{INSUFFICIENT_EVIDENCE}\n\n"
        f"Validation:\n{validation_notes.strip() or 'Evidence below threshold for synthesis.'}\n\n"
        f"Confidence Score:\n{confidence:.2f}"
    )


def assemble_full_answer(
    retrieved_evidence_text: str,
    coverage_text: str,
    synthesized_body: str,
    *,
    sources_section: str = "",
    confidence: float,
) -> str:
    parts = [retrieved_evidence_text, "", coverage_text, "", "Synthesized Insights:", synthesized_body]
    if sources_section:
        parts.extend(["", sources_section])
    parts.extend(["", f"Confidence Score:\n{confidence:.2f}"])
    return "\n".join(parts)
