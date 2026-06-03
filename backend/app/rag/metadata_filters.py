"""Build SQL metadata filters for retrieval."""

from sqlalchemy import or_

from app.db.models import Document, DocumentChunk


def apply_ticker_metadata_filter(stmt, tickers: list[str]):
    """
    Restrict retrieval to chunks whose document or chunk metadata matches tickers.
    Semantic ordering/limit is applied after this filter.
    """
    if not tickers:
        return stmt
    upper = [t.upper() for t in tickers]
    if len(upper) == 1:
        t = upper[0]
        return stmt.where(
            or_(
                Document.ticker == t,
                DocumentChunk.chunk_metadata["ticker"].astext == t,
            )
        )
    return stmt.where(
        or_(
            Document.ticker.in_(upper),
            DocumentChunk.chunk_metadata["ticker"].astext.in_(upper),
        )
    )
