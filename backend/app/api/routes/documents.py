from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.db.models import Document, DocumentChunk

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/stats")
async def document_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Counts for demo dashboards — extend as ingestion matures."""
    try:
        doc_count = await db.scalar(select(func.count()).select_from(Document))
        chunk_count = await db.scalar(select(func.count()).select_from(DocumentChunk))
        return {
            "documents": doc_count or 0,
            "chunks": chunk_count or 0,
            "db_ok": True,
        }
    except (ConnectionRefusedError, OSError):
        return {
            "documents": 0,
            "chunks": 0,
            "db_ok": False,
            "hint": "Start PostgreSQL: make db-up",
        }
