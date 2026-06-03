"""Validation agent: evidence scoring, confidence, and routing decisions."""

from app.agents.evidence import (
    compute_company_coverage,
    coverage_confidence_penalty,
)
from app.core.config import settings


def validate_evidence(
    context: list[dict],
    expected_tickers: list[str] | None = None,
) -> dict:
    """
    Score retrieval quality and decide how to answer.

    Routes:
      - refuse: insufficient evidence — no LLM answer
      - cautious: partial evidence — strict grounded generation
      - answer: sufficient evidence — normal grounded generation
    """
    if not context:
        return {
            "confidence": 0.0,
            "route": "refuse",
            "validation_notes": (
                "No indexed documents matched this query. "
                "Run `make ingest` or add PDFs under data/raw/."
            ),
        }

    scores = [
        float(c.get("composite_score") or c.get("score") or 0) for c in context
    ]
    top = max(scores)
    avg = sum(scores) / len(scores)
    confidence = round(0.6 * top + 0.4 * avg, 3)
    strong = sum(1 for s in scores if s >= 0.5)

    refuse_at = settings.confidence_refuse_threshold
    cautious_at = settings.confidence_cautious_threshold

    if confidence < refuse_at:
        route = "refuse"
        notes = (
            f"Insufficient evidence (confidence {confidence:.0%}, threshold {refuse_at:.0%}). "
            f"Best chunk match {top:.0%}. Refusing to generate an ungrounded answer."
        )
    elif confidence < cautious_at:
        route = "cautious"
        notes = (
            f"Limited evidence (confidence {confidence:.0%}). "
            f"Using {len(context)} chunks ({strong} strong matches) with strict citation mode."
        )
    else:
        route = "answer"
        notes = (
            f"Strong evidence (confidence {confidence:.0%}) from "
            f"{len(context)} chunks ({strong} above 50% relevance)."
        )

    coverage = compute_company_coverage(context, expected_tickers)
    cov_penalty, cov_notes = coverage_confidence_penalty(coverage)
    if cov_penalty:
        confidence = max(0.0, round(confidence - cov_penalty, 3))
        if cov_notes:
            notes += f" Coverage: {cov_notes}."
        if any(c.status == "missing" for c in coverage) and route == "answer":
            route = "cautious"
            notes += " Downgraded to cautious due to missing company coverage."

    return {
        "confidence": confidence,
        "route": route,
        "validation_notes": notes,
        "company_coverage": [
            {
                "ticker": c.ticker,
                "display_name": c.display_name,
                "status": c.status,
                "chunk_count": c.chunk_count,
                "strong_chunk_count": c.strong_chunk_count,
            }
            for c in coverage
        ],
    }


def post_validate_answer(answer: str, context: list[dict]) -> dict:
    """
    Lightweight post-check: flag answers that look unsupported.
    Reduces confidence if the model may have hallucinated numbers.
    """
    if not answer or not context:
        return {"validation_notes_append": "", "confidence_penalty": 0.0}

    import re

    answer_nums = set(re.findall(r"\b\d{2,}(?:\.\d+)?%?\b", answer))
    if not answer_nums:
        return {"validation_notes_append": "", "confidence_penalty": 0.0}

    corpus = " ".join(c.get("excerpt", "") for c in context)
    unsupported = [n for n in answer_nums if n not in corpus]
    if not unsupported:
        return {"validation_notes_append": "", "confidence_penalty": 0.0}

    return {
        "validation_notes_append": (
            f" Validation flagged numeric claims not found verbatim in sources: "
            f"{', '.join(unsupported[:3])}."
        ),
        "confidence_penalty": 0.15,
    }
