"""Ingest PDFs and text files from data/raw (flat layout or optional subfolders)."""

import re
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Document, DocumentChunk
from app.ingestion.document_loader import SUPPORTED_EXTENSIONS, load_document_text
from app.rag.chunking import chunk_pdf_path, chunk_plain_text
from app.rag.chunk_metadata import finalize_chunk_metadata
from app.ingestion.knowledge_base import KNOWLEDGE_BASE_TICKERS, LOCAL_DOCUMENT_FOLDERS
from app.rag.embeddings import embed_texts
from app.rag.vector_store import upsert_chunks

# Substring match on normalized filename → ticker (order: longer phrases first)
_FILENAME_TICKER_ALIASES: tuple[tuple[str, str], ...] = (
    ("RAYMOND JAMES", "RJF"),
    ("MORGAN STANLEY", "MS"),
    ("JPMORGAN", "JPM"),
    ("JPMC", "JPM"),
    ("GOLDMAN SACHS", "GS"),
    ("GOLDMAN", "GS"),
    ("CHARLES SCHWAB", "SCHW"),
    ("SCHWAB", "SCHW"),
    ("APPLE", "AAPL"),
)

_SKIP_FILES = {".gitkeep", ".ds_store"}


def _normalize_name(filename: str) -> str:
    stem = Path(filename).stem.upper()
    for ch in "-_.":
        stem = stem.replace(ch, " ")
    return " ".join(stem.split())


def infer_ticker(filename: str) -> str:
    """
    Infer ticker from filename.

    Examples:
      MS_10k1225.pdf → MS
      jpmc-corp-10k-2025.pdf → JPM
      Raymond James Financial 2025 Annual Report.pdf → RJF
    """
    normalized = _normalize_name(filename)
    known = set(KNOWLEDGE_BASE_TICKERS.keys())

    for phrase, ticker in _FILENAME_TICKER_ALIASES:
        if phrase in normalized:
            return ticker

    if "RAYMOND" in normalized and ("JAMES" in normalized or "10K" in normalized.replace(" ", "")):
        return "RJF"

    stem = Path(filename).stem.upper()
    for sep in ("_", "-", "."):
        if sep in stem:
            prefix = stem.split(sep)[0]
            if prefix in known:
                return prefix

    if stem[:4] in known:
        return stem[:4]
    if stem[:3] in known:
        return stem[:3]

    return stem[:16]


def infer_form_type(filename: str) -> str:
    """Infer document type from filename."""
    lower = filename.lower()
    if "10-q" in lower or "10q" in lower:
        return "10-Q"
    if "10-k" in lower or "10k" in lower:
        return "10-K"
    if "annual report" in lower:
        return "ANNUAL_REPORT"
    if "earnings" in lower and "transcript" in lower:
        return "EARNINGS_TRANSCRIPT"
    if "investor" in lower and ("presentation" in lower or "deck" in lower):
        return "INVESTOR_PRESENTATION"
    return "LOCAL_PDF"


async def ingest_local_file(
    db: AsyncSession,
    path: Path,
    form_type: str | None = None,
    ticker: str | None = None,
) -> int:
    symbol = (ticker or infer_ticker(path.name)).upper()[:16]
    doc_type = form_type or infer_form_type(path.name)
    company = KNOWLEDGE_BASE_TICKERS.get(symbol, symbol)
    filing_year = None
    year_m = re.search(r"(20\d{2})", path.name)
    if year_m:
        filing_year = year_m.group(1)

    if path.suffix.lower() == ".pdf":
        records = chunk_pdf_path(
            path,
            company_name=company,
            ticker=symbol,
            filing_type=doc_type,
            filing_year=filing_year,
        )
    else:
        text = load_document_text(path)
        records = chunk_plain_text(
            text,
            company_name=company,
            ticker=symbol,
            filing_type=doc_type,
            source_document=path.name,
            filing_year=filing_year,
        )

    if not records:
        return 0

    doc = Document(
        id=uuid.uuid4(),
        ticker=symbol,
        form_type=doc_type,
        title=path.name,
        source_url=str(path.resolve()),
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
                ticker=symbol,
                filing_type=doc_type,
                source_document=path.name,
                filing_year=filing_year or r.metadata.get("filing_year"),
                section_name=r.metadata.get("section_name"),
                page_number=r.metadata.get("page_number"),
            ),
            embedding=vec,
        )
        for r, vec in zip(records, vectors, strict=True)
    ]
    await upsert_chunks(db, chunk_rows)
    await db.commit()
    return len(chunk_rows)


def _iter_local_files(raw: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(raw.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.lower() in _SKIP_FILES:
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(path)
    return files


async def ingest_local_raw_files(db: AsyncSession) -> dict[str, int]:
    """Ingest all supported files directly in data/raw/."""
    raw = settings.data_raw_dir
    results: dict[str, int] = {}
    for path in _iter_local_files(raw):
        try:
            n = await ingest_local_file(db, path)
            ticker = infer_ticker(path.name)
            results[f"{ticker}:{path.name}"] = n
        except Exception:
            await db.rollback()
            results[path.name] = 0
            raise
    return results


async def ingest_knowledge_base_folders(db: AsyncSession) -> dict[str, int]:
    """
    Ingest local knowledge base files.

    Primary: PDFs/TXT in data/raw/ (flat layout).
    Optional: legacy subfolders if present.
    """
    raw = settings.data_raw_dir
    results: dict[str, int] = {}

    results.update(await ingest_local_raw_files(db))

    for folder_name, form_type in LOCAL_DOCUMENT_FOLDERS.items():
        folder = raw / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            key = f"{folder_name}/{path.name}"
            try:
                n = await ingest_local_file(db, path, form_type=form_type)
                results[key] = n
            except Exception:
                await db.rollback()
                results[key] = 0
                raise

    return results
