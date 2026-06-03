"""Required chunk metadata fields for pgvector storage and filtering."""

from typing import Any

REQUIRED_METADATA_KEYS = (
    "company_name",
    "ticker",
    "filing_type",
    "filing_year",
    "section_name",
    "page_number",
    "source_document",
)


def finalize_chunk_metadata(
    metadata: dict[str, Any] | None,
    *,
    company_name: str,
    ticker: str,
    filing_type: str,
    source_document: str,
    filing_year: str | int | None = None,
    section_name: str | None = None,
    page_number: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge chunk metadata and ensure all required keys are present before storage.
    Does not remove extra keys (e.g. filed_at, source).
    """
    base: dict[str, Any] = dict(metadata or {})
    if extra:
        base.update(extra)

    section = section_name or base.get("section_name") or "GENERAL"
    year = filing_year if filing_year is not None else base.get("filing_year")
    page = page_number if page_number is not None else base.get("page_number")

    out = {
        "company_name": str(base.get("company_name") or company_name),
        "ticker": str(base.get("ticker") or ticker).upper(),
        "filing_type": str(base.get("filing_type") or filing_type),
        "filing_year": str(year) if year is not None else None,
        "section_name": str(section),
        "page_number": int(page) if page is not None else None,
        "source_document": str(base.get("source_document") or source_document),
    }
    for key, value in base.items():
        if key not in out:
            out[key] = value
    return out
