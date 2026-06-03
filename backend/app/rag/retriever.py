"""Vector retrieval with metadata filtering, re-ranking, and debug logging."""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Document, DocumentChunk
from app.db.session import async_session_factory
from app.rag.company_detection import DetectedCompany, detect_companies_from_query
from app.rag.embeddings import embed_query
from app.rag.metadata_filters import apply_ticker_metadata_filter
from app.rag.rerank import ScoredChunk, rerank_chunks

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    ticker: str
    content: str
    score: float
    form_type: str | None = None
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)
    section_name: str | None = None
    semantic_score: float | None = None
    composite_score: float | None = None
    rerank_reasons: list[str] = field(default_factory=list)


@dataclass
class RetrievalDebug:
    query: str
    ticker: str | None
    detected_companies: list[dict[str, str]]
    applied_filters: dict[str, Any]
    candidate_count: int
    final_count: int
    chunk_ids: list[str]
    scores: list[float]
    sections: list[str | None]
    rerank_reasons: list[list[str]]
    detected_domain: str | None = None
    domain_relevance_score: float | None = None
    retrieval_skipped: bool = False
    skip_reason: str | None = None
    top_semantic_score: float | None = None


def _resolve_metadata_filters(
    query: str,
    ticker_param: str | None,
    analysis: dict,
) -> tuple[list[DetectedCompany], dict[str, Any], list[str] | None]:
    """
    Choose tickers for metadata filtering.

    Priority: explicit API ticker > companies detected in query > analysis tickers.
    Comparative multi-company mode uses IN filter over all mentioned tickers.
    """
    detected = detect_companies_from_query(query)
    applied: dict[str, Any] = {}
    filter_tickers: list[str] | None = None

    if ticker_param:
        t = ticker_param.upper()
        filter_tickers = [t]
        applied = {"filter": "api_ticker", "tickers": filter_tickers}
    elif analysis.get("use_per_ticker_retrieval"):
        mentioned = [x.upper() for x in (analysis.get("tickers_mentioned") or [])]
        if mentioned:
            filter_tickers = mentioned
            applied = {
                "filter": "comparative_metadata",
                "tickers": filter_tickers,
                "match": "document.ticker OR metadata.ticker",
            }
    elif detected:
        filter_tickers = [c.ticker for c in detected]
        applied = {
            "filter": "query_detected_company",
            "tickers": filter_tickers,
            "match": "document.ticker OR metadata.ticker",
        }
    elif analysis.get("tickers_mentioned"):
        filter_tickers = [x.upper() for x in analysis["tickers_mentioned"]]
        applied = {
            "filter": "query_tickers",
            "tickers": filter_tickers,
            "match": "document.ticker OR metadata.ticker",
        }

    return detected, applied, filter_tickers


def _normalize_chunk_metadata(row, max_chars: int) -> dict:
    meta = dict(row.chunk_metadata or {})
    meta.setdefault("company_name", meta.get("company_name") or row.ticker)
    meta.setdefault("ticker", row.ticker)
    meta.setdefault("filing_type", row.form_type or meta.get("filing_type"))
    meta.setdefault("source_document", row.title or meta.get("source_document"))
    meta.setdefault("section_name", meta.get("section_name") or "GENERAL")
    if meta.get("filing_year") is None and row.title:
        import re

        year_m = re.search(r"(20\d{2})", row.title)
        if year_m:
            meta["filing_year"] = year_m.group(1)
    return meta


async def retrieve_context(
    query: str,
    ticker: str | None = None,
    top_k: int | None = None,
    candidate_k: int | None = None,
    query_analysis: dict | None = None,
) -> tuple[list[RetrievedChunk], RetrievalDebug | None]:
    """
    Metadata-filtered cosine search, then re-rank to top_k.
    Semantic similarity runs within the filtered candidate pool.
    """
    analysis = query_analysis or {}
    is_comparative = bool(analysis.get("is_comparative"))
    tickers_mentioned: list[str] = analysis.get("tickers_mentioned") or []

    detected, applied_filters, filter_tickers = _resolve_metadata_filters(
        query, ticker, analysis
    )
    detected_payload = [
        {"ticker": c.ticker, "company_name": c.company_name} for c in detected
    ]

    final_k = top_k or settings.retrieval_top_k
    if is_comparative:
        final_k = max(final_k, getattr(settings, "retrieval_comparative_top_k", 12))
    pool_k = candidate_k or settings.retrieval_candidate_k
    if is_comparative:
        pool_k = max(pool_k, 50)
    if filter_tickers:
        pool_k = max(pool_k, pool_k * max(1, len(filter_tickers)))

    max_chars = settings.retrieval_max_chunk_chars

    debug = RetrievalDebug(
        query=query,
        ticker=ticker,
        detected_companies=detected_payload,
        applied_filters=applied_filters,
        candidate_count=0,
        final_count=0,
        chunk_ids=[],
        scores=[],
        sections=[],
        rerank_reasons=[],
        detected_domain=analysis.get("detected_domain"),
        domain_relevance_score=analysis.get("domain_relevance_score"),
    )

    logger.info(
        "Detected company: %s",
        detected_payload if detected_payload else "(none)",
    )
    logger.info(
        "Applied filters: %s",
        applied_filters if applied_filters else "(none — semantic search over full index)",
    )

    if not settings.openai_configured:
        return [], debug

    async with async_session_factory() as db:
        chunk_count = await db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.embedding.isnot(None)
            )
        )
    if not chunk_count:
        logger.info("retrieval skipped: no embedded chunks in database")
        return [], debug

    query_vector = await embed_query(query)

    try:
        async with async_session_factory() as db:
            distance = DocumentChunk.embedding.cosine_distance(query_vector)
            stmt = (
                select(
                    DocumentChunk.id,
                    DocumentChunk.content,
                    DocumentChunk.chunk_metadata,
                    Document.ticker,
                    Document.form_type,
                    Document.title,
                    Document.source_url,
                    distance.label("distance"),
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.embedding.isnot(None))
                .order_by(distance)
                .limit(pool_k)
            )
            if filter_tickers:
                stmt = apply_ticker_metadata_filter(stmt, filter_tickers)

            rows = (await db.execute(stmt)).all()
    except (ConnectionRefusedError, OSError) as exc:
        logger.warning("retrieval db error: %s", exc)
        return [], debug

    debug.candidate_count = len(rows)
    if rows:
        top_semantic = max(0.0, 1.0 - float(rows[0].distance))
        debug.top_semantic_score = round(top_semantic, 4)
        if top_semantic < settings.retrieval_min_top_similarity:
            debug.retrieval_skipped = True
            debug.skip_reason = (
                f"top_similarity_below_threshold ({top_semantic:.3f} < "
                f"{settings.retrieval_min_top_similarity:.3f})"
            )
            logger.info(
                "Retrieval skipped: true (reason=%s)",
                debug.skip_reason,
            )
            return [], debug

    candidates: list[dict] = []
    for row in rows:
        semantic = max(0.0, 1.0 - float(row.distance))
        meta = _normalize_chunk_metadata(row, max_chars)
        section = meta.get("section_name") or "GENERAL"
        candidates.append(
            {
                "chunk_id": str(row.id),
                "ticker": row.ticker,
                "content": row.content,
                "excerpt": row.content[:max_chars],
                "score": round(semantic, 4),
                "form_type": row.form_type,
                "source_url": row.source_url,
                "metadata": meta,
                "section_name": section,
            }
        )

    ranked: list[ScoredChunk] = rerank_chunks(
        candidates,
        query,
        ticker=filter_tickers[0] if filter_tickers and len(filter_tickers) == 1 else ticker,
        final_k=final_k,
        is_comparative=is_comparative,
        tickers_mentioned=tickers_mentioned or (filter_tickers or []),
    )

    results: list[RetrievedChunk] = []
    for item in ranked:
        excerpt = item.content[:max_chars]
        meta = item.metadata or {}
        results.append(
            RetrievedChunk(
                chunk_id=item.chunk_id,
                ticker=item.ticker,
                content=excerpt,
                score=item.composite_score,
                form_type=item.form_type,
                source_url=item.source_url,
                metadata=meta,
                section_name=item.section_name or meta.get("section_name"),
                semantic_score=item.semantic_score,
                composite_score=item.composite_score,
                rerank_reasons=item.rerank_reasons,
            )
        )
        debug.chunk_ids.append(item.chunk_id)
        debug.scores.append(item.composite_score)
        debug.sections.append(item.section_name)
        debug.rerank_reasons.append(item.rerank_reasons)

    debug.final_count = len(results)

    logger.info("Retrieved chunk IDs: %s", debug.chunk_ids)
    logger.info("Retrieved scores: %s", debug.scores)

    if settings.debug_retrieval:
        logger.info(
            "RETRIEVAL DEBUG query=%r candidates=%d final=%d sections=%s",
            query,
            debug.candidate_count,
            debug.final_count,
            debug.sections,
        )
        for i, r in enumerate(results, 1):
            logger.info(
                "  chunk[%d] id=%s meta_ticker=%s section=%s composite=%.3f preview=%.120s",
                i,
                r.chunk_id,
                (r.metadata or {}).get("ticker"),
                r.section_name,
                r.composite_score or 0,
                r.content[:120].replace("\n", " "),
            )

    return results, debug
