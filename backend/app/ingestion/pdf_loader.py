"""Backward-compatible re-exports — use document_loader for new code."""

from app.ingestion.document_loader import chunk_text, load_document_text as load_pdf_text

__all__ = ["chunk_text", "load_pdf_text"]
