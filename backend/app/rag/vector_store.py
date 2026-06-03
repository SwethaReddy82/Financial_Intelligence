from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk


async def upsert_chunks(db: AsyncSession, chunks: list[DocumentChunk]) -> None:
    db.add_all(chunks)
