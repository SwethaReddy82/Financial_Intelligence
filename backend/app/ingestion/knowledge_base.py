"""
Default wealth-intelligence knowledge base.

SEC (automatic): latest 10-K + 10-Q per ticker via EDGAR.
Local (manual drop): earnings transcripts, investor decks, PDF annual reports.
"""

from dataclasses import dataclass

# Tickers aligned with interview / financial-services knowledge base
KNOWLEDGE_BASE_TICKERS: dict[str, str] = {
    "AAPL": "Apple Inc.",
    "RJF": "Raymond James Financial",
    "JPM": "JPMorgan Chase",
    "MS": "Morgan Stanley",
    "GS": "Goldman Sachs",
    "SCHW": "Charles Schwab",
}

DEFAULT_SEC_FORMS = ("10-K", "10-Q")

# Subfolders under data/raw/ for non-SEC documents
LOCAL_DOCUMENT_FOLDERS: dict[str, str] = {
    "earnings_transcripts": "EARNINGS_TRANSCRIPT",
    "investor_presentations": "INVESTOR_PRESENTATION",
    "annual_reports": "ANNUAL_REPORT",
}


@dataclass(frozen=True)
class KnowledgeBaseSpec:
    tickers: tuple[str, ...]
    sec_forms: tuple[str, ...]
    sec_forms_per_ticker: int  # max one filing per form type (e.g. latest 10-K + 10-Q)


DEFAULT_KNOWLEDGE_BASE = KnowledgeBaseSpec(
    tickers=tuple(KNOWLEDGE_BASE_TICKERS.keys()),
    sec_forms=DEFAULT_SEC_FORMS,
    sec_forms_per_ticker=1,
)
