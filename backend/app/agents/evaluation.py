"""Post-generation answer evaluation: groundedness, citations, relevance, hallucination risk."""

import re
from dataclasses import dataclass


@dataclass
class AnswerEvaluation:
    groundedness_score: float
    citation_coverage: float
    relevance_score: float
    hallucination_risk: float
    notes: str


def _extract_citation_ids(text: str) -> set[int]:
    return {int(m) for m in re.findall(r"\[(\d+)\]", text)}


def _sentence_overlap(answer: str, corpus: str) -> float:
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", answer) if len(s.strip()) > 20]
    if not sentences:
        return 0.5
    corpus_lower = corpus.lower()
    supported = sum(
        1 for s in sentences if any(word in corpus_lower for word in s.lower().split()[:6] if len(word) > 4)
    )
    return supported / len(sentences)


def evaluate_answer(
    answer: str,
    context: list[dict],
    confidence: float,
) -> AnswerEvaluation:
    if not answer or not context:
        return AnswerEvaluation(
            groundedness_score=0.0,
            citation_coverage=0.0,
            relevance_score=0.0,
            hallucination_risk=1.0,
            notes="No answer or no context.",
        )

    corpus = " ".join(c.get("excerpt") or c.get("content") or "" for c in context)
    cited = _extract_citation_ids(answer)
    available = set(range(1, len(context) + 1))
    citation_coverage = len(cited & available) / max(len(available), 1) if available else 0.0

    groundedness = _sentence_overlap(answer, corpus)
    if cited:
        groundedness = min(1.0, groundedness * 0.6 + citation_coverage * 0.4 + 0.1)

    relevance_scores = [float(c.get("score") or c.get("composite_score") or 0) for c in context]
    relevance_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    answer_nums = set(re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b", answer))
    corpus_nums = set(re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b", corpus))
    unsupported = [n for n in answer_nums if n not in corpus_nums and len(n) > 1]
    from app.agents.evidence import find_unmarked_inference_phrases

    inference_hits = find_unmarked_inference_phrases(answer)
    hallucination_risk = min(
        1.0,
        0.15 * len(unsupported)
        + (0.3 if not cited else 0)
        + (0.2 if confidence < 0.4 else 0)
        + (0.15 if inference_hits else 0),
    )

    financial_in_context = any(
        kw in corpus.lower() for kw in ("revenue", "advisor", "assets", "billion", "million", "private client")
    )
    financial_in_answer = any(kw in answer.lower() for kw in ("revenue", "advisor", "assets", "billion", "million"))
    notes_parts = []
    if financial_in_context and not financial_in_answer:
        notes_parts.append("Retrieved chunks contain financial metrics but answer may be too generic.")
    if unsupported:
        notes_parts.append(f"Unsupported numbers: {', '.join(unsupported[:3])}.")
    if inference_hits:
        notes_parts.append(
            f"Unmarked inference language: {', '.join(inference_hits[:4])}."
        )

    return AnswerEvaluation(
        groundedness_score=round(groundedness, 3),
        citation_coverage=round(citation_coverage, 3),
        relevance_score=round(relevance_score, 3),
        hallucination_risk=round(hallucination_risk, 3),
        notes=" ".join(notes_parts) or "OK",
    )
