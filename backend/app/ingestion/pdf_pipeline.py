"""Ingest PDFs — delegates to local_documents (see ingest_knowledge_base_folders)."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.local_documents import ingest_knowledge_base_folders, ingest_local_file


async def ingest_pdf_file(
    db: AsyncSession,
    path: Path,
    ticker: str | None = None,
) -> int:
    return await ingest_local_file(db, path, form_type="PDF", ticker=ticker)


async def ingest_pdf_folder(db: AsyncSession, folder: Path) -> dict[str, int]:
    return await ingest_knowledge_base_folders(db)
