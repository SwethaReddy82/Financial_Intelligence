"""SEC filings and PDF ingestion pipeline."""

from app.ingestion.pipeline import ingest_ticker_filings

__all__ = ["ingest_ticker_filings"]
