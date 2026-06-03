"""Section-aware chunking with rich metadata for financial documents."""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

# Priority section labels (matched in chunk text / headers)
SECTION_PATTERNS: list[tuple[str, str]] = [
    ("PRIVATE_CLIENT_GROUP", r"(?i)private\s+client\s+group|\bPCG\b"),
    ("RISK_FACTORS", r"(?i)risk\s+factors|item\s*1a"),
    ("MD_AND_A", r"(?i)management['\u2019]?s\s+discussion|item\s*7\b|\bMD&A\b"),
    ("FINANCIAL_HIGHLIGHTS", r"(?i)financial\s+highlights|selected\s+financial"),
    ("BUSINESS", r"(?i)^item\s*1\b[^0-9]|description\s+of\s+business|\bbusiness\s+overview"),
    ("SEGMENTS", r"(?i)business\s+segments?|segment\s+information"),
    ("FINANCIAL_STATEMENTS", r"(?i)financial\s+statements|consolidated\s+statements"),
]

FINANCIAL_KEYWORDS = (
    "revenue",
    "net income",
    "assets under",
    "client assets",
    "advisors",
    "financial advisors",
    "growth",
    "percent",
    "%",
    "billion",
    "million",
    "segment",
    "private client",
    "wealth management",
    "investment advisory",
    "financial planning",
    "aum",
    "administration",
)


@dataclass
class ChunkRecord:
    content: str
    chunk_index: int
    metadata: dict


def _detect_section(text: str) -> str:
    head = text[:800]
    for label, pattern in SECTION_PATTERNS:
        if re.search(pattern, head, re.MULTILINE):
            return label
    lower = text.lower()
    if "private client group" in lower or " pcg " in lower:
        return "PRIVATE_CLIENT_GROUP"
    if "risk factor" in lower:
        return "RISK_FACTORS"
    if "management's discussion" in lower or "md&a" in lower:
        return "MD_AND_A"
    return "GENERAL"


def _extract_filing_year(filename: str, filed_at: str | None = None) -> str | None:
    if filed_at and len(filed_at) >= 4:
        return filed_at[:4]
    match = re.search(r"(20\d{2})", filename)
    return match.group(1) if match else None


def chunk_plain_text(
    text: str,
    *,
    company_name: str,
    ticker: str,
    filing_type: str,
    source_document: str,
    filing_year: str | None = None,
    chunk_size: int = 1400,
    overlap: int = 250,
) -> list[ChunkRecord]:
    if not text.strip():
        return []

    records: list[ChunkRecord] = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        start = end - overlap
        if not piece:
            continue
        section = _detect_section(piece)
        records.append(
            ChunkRecord(
                content=piece,
                chunk_index=idx,
                metadata={
                    "company_name": company_name,
                    "ticker": ticker,
                    "filing_type": filing_type,
                    "filing_year": filing_year,
                    "section_name": section,
                    "page_number": None,
                    "source_document": source_document,
                },
            )
        )
        idx += 1
    return records


def chunk_pdf_path(
    path: Path,
    *,
    company_name: str,
    ticker: str,
    filing_type: str,
    filing_year: str | None = None,
    chunk_size: int = 1400,
    overlap: int = 250,
) -> list[ChunkRecord]:
    reader = PdfReader(str(path))
    all_records: list[ChunkRecord] = []
    global_index = 0

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        start = 0
        while start < len(page_text):
            end = start + chunk_size
            piece = page_text[start:end].strip()
            start = end - overlap
            if not piece:
                continue
            section = _detect_section(piece)
            all_records.append(
                ChunkRecord(
                    content=piece,
                    chunk_index=global_index,
                    metadata={
                        "company_name": company_name,
                        "ticker": ticker,
                        "filing_type": filing_type,
                        "filing_year": filing_year or _extract_filing_year(path.name),
                        "section_name": section,
                        "page_number": page_num,
                        "source_document": path.name,
                    },
                )
            )
            global_index += 1
    return all_records
