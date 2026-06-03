"""Agent tools — retrieval with re-ranking and comparative query handling."""

import logging

from app.agents.query_analysis import analyze_query
from app.core.config import settings
from app.rag.retriever import retrieve_context

logger = logging.getLogger(__name__)


async def search_filings(
    query: str,
    ticker: str | None = None,
    top_k: int | None = None,
) -> tuple[list[dict], object | None, dict]:
    analysis = analyze_query(query, ticker)
    domain = analysis.get("detected_domain")
    relevance = float(analysis.get("domain_relevance_score") or 0.0)
    skip_retrieval = bool(analysis.get("retrieval_skipped"))

    if settings.debug_retrieval:
        logger.info(
            "QUERY ANALYSIS comparative=%s risk_focus=%s tickers=%s detected=%s mode=%s",
            analysis["is_comparative"],
            analysis["is_risk_focus"],
            analysis["tickers_mentioned"],
            analysis.get("detected_companies"),
            analysis["response_mode"],
        )
    logger.info("Detected domain: %s", domain)
    logger.info("Domain relevance score: %.3f", relevance)
    logger.info("Retrieval skipped: %s", "true" if skip_retrieval else "false")

    if skip_retrieval:
        debug = {
            "query": query,
            "ticker": ticker,
            "detected_companies": analysis.get("detected_companies", []),
            "applied_filters": {},
            "candidate_count": 0,
            "final_count": 0,
            "chunk_ids": [],
            "scores": [],
            "sections": [],
            "rerank_reasons": [],
            "detected_domain": domain,
            "domain_relevance_score": relevance,
            "retrieval_skipped": True,
            "skip_reason": "domain_relevance_below_threshold",
            "top_semantic_score": None,
        }
        return [], debug, analysis

    chunks, debug = await retrieve_context(
        query=query,
        ticker=ticker,
        top_k=top_k,
        query_analysis=analysis,
    )

    results = [
        {
            "chunk_id": c.chunk_id,
            "ticker": c.ticker,
            "excerpt": c.content,
            "content": c.content,
            "score": c.score,
            "semantic_score": c.semantic_score,
            "composite_score": c.composite_score,
            "form_type": c.form_type,
            "source_url": c.source_url,
            "metadata": c.metadata,
            "section_name": c.section_name,
            "rerank_reasons": c.rerank_reasons,
            "company_name": (c.metadata or {}).get("company_name"),
            "filing_type": (c.metadata or {}).get("filing_type"),
            "filing_year": (c.metadata or {}).get("filing_year"),
            "page_number": (c.metadata or {}).get("page_number"),
            "source_document": (c.metadata or {}).get("source_document"),
        }
        for c in chunks
    ]
    return results, debug, analysis
