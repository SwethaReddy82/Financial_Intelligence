"""Orchestrate: fetch filings → chunk → embed → store."""

import asyncio
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Document, DocumentChunk
from app.ingestion.knowledge_base import DEFAULT_KNOWLEDGE_BASE, KNOWLEDGE_BASE_TICKERS, KnowledgeBaseSpec
from app.rag.chunking import chunk_plain_text
from app.rag.chunk_metadata import finalize_chunk_metadata
from app.ingestion.sec_filings import download_filing_text, list_latest_filings_per_form
from app.rag.embeddings import embed_texts
from app.rag.vector_store import upsert_chunks

SEC_REQUEST_DELAY_SEC = 0.2


async def ingest_ticker_filings(
    db: AsyncSession,
    ticker: str,
    spec: KnowledgeBaseSpec | None = None,
) -> int:
    """
    Ingest latest SEC forms per ticker (default: one 10-K + one 10-Q).
    Returns number of chunks stored.
    """
    kb = spec or DEFAULT_KNOWLEDGE_BASE
    filings = await list_latest_filings_per_form(
        ticker,
        form_types=kb.sec_forms,
        per_form_limit=kb.sec_forms_per_ticker,
    )
    total_chunks = 0

    for filing in filings:
        await asyncio.sleep(SEC_REQUEST_DELAY_SEC)
        raw = await download_filing_text(filing)
        company = KNOWLEDGE_BASE_TICKERS.get(filing.ticker, filing.ticker)
        source_doc = f"{filing.ticker}_{filing.form_type}_{filing.filed_at}"
        records = chunk_plain_text(
            raw,
            company_name=company,
            ticker=filing.ticker,
            filing_type=filing.form_type,
            source_document=source_doc,
            filing_year=filing.filed_at[:4] if filing.filed_at else None,
        )
        if not records:
            continue

        doc = Document(
            id=uuid.uuid4(),
            ticker=filing.ticker,
            form_type=filing.form_type,
            title=f"{filing.ticker} {filing.form_type} ({filing.filed_at})",
            source_url=filing.filing_url,
            filed_at=date.fromisoformat(filing.filed_at) if filing.filed_at else None,
        )
        db.add(doc)
        await db.flush()

        texts = [r.content for r in records]
        vectors = await embed_texts(texts)
        chunk_rows = [
            DocumentChunk(
                document_id=doc.id,
                chunk_index=r.chunk_index,
                content=r.content,
                chunk_metadata=finalize_chunk_metadata(
                    r.metadata,
                    company_name=company,
                    ticker=filing.ticker,
                    filing_type=filing.form_type,
                    source_document=source_doc,
                    filing_year=filing.filed_at[:4] if filing.filed_at else None,
                    section_name=r.metadata.get("section_name"),
                    page_number=r.metadata.get("page_number"),
                    extra={"filed_at": filing.filed_at, "source": "sec_edgar"},
                ),
                embedding=vec,
            )
            for r, vec in zip(records, vectors, strict=True)
        ]
        await upsert_chunks(db, chunk_rows)
        total_chunks += len(chunk_rows)

    await db.commit()
    return total_chunks


async def ingest_sec_knowledge_base(
    db: AsyncSession,
    tickers: list[str] | None = None,
    spec: KnowledgeBaseSpec | None = None,
) -> dict[str, int]:
    """Ingest SEC filings for all knowledge-base tickers."""
    kb = spec or DEFAULT_KNOWLEDGE_BASE
    symbols = [t.upper() for t in (tickers or list(kb.tickers))]
    results: dict[str, int] = {}

    for ticker in symbols:
        await asyncio.sleep(SEC_REQUEST_DELAY_SEC)
        try:
            n = await ingest_ticker_filings(db, ticker, spec=kb)
            results[ticker] = n
        except Exception:
            await db.rollback()
            results[ticker] = 0
            raise  # caller may catch per-ticker in CLI

    return results
