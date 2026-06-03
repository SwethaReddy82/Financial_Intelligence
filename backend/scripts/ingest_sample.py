"""
Ingest the full wealth-intelligence knowledge base.

SEC (automatic): AAPL, RJF, JPM, MS, GS, SCHW — latest 10-K + 10-Q each.
Local (manual): PDFs/TXT in data/raw/ (flat) or optional subfolders

Usage: make ingest
"""

import asyncio
import sys

from app.core.config import settings
from app.db.session import async_session_factory
from app.ingestion.knowledge_base import (
    DEFAULT_KNOWLEDGE_BASE,
    KNOWLEDGE_BASE_TICKERS,
    LOCAL_DOCUMENT_FOLDERS,
)
from app.ingestion.local_documents import ingest_knowledge_base_folders
from app.ingestion.pipeline import ingest_ticker_filings


def _print_kb_overview() -> None:
    print("Knowledge base targets:")
    print("  SEC (10-K / 10-Q):", ", ".join(KNOWLEDGE_BASE_TICKERS.keys()))
    print("  Local: files in data/raw/ (+ optional subfolders)")
    for ticker, name in KNOWLEDGE_BASE_TICKERS.items():
        print(f"    {ticker} — {name}")


async def main() -> None:
    if not settings.openai_configured:
        print("Set a valid OPENAI_API_KEY in .env before ingesting.", file=sys.stderr)
        sys.exit(1)

    if "example.com" in settings.sec_user_agent.lower():
        print(
            "WARNING: Update SEC_USER_AGENT in .env with your real name and email (SEC policy).",
            file=sys.stderr,
        )

    _print_kb_overview()
    tickers = settings.ticker_list or list(DEFAULT_KNOWLEDGE_BASE.tickers)
    print(f"\nIngesting SEC forms {DEFAULT_KNOWLEDGE_BASE.sec_forms} for: {', '.join(tickers)}")

    async with async_session_factory() as db:
        for ticker in tickers:
            try:
                n = await ingest_ticker_filings(db, ticker)
                print(f"  SEC {ticker}: {n} chunks")
            except Exception as exc:
                print(f"  SEC {ticker}: failed — {exc}", file=sys.stderr)

        print("\nIngesting local PDFs from data/raw/ ...")
        try:
            local_results = await ingest_knowledge_base_folders(db)
            if not local_results:
                print(f"  No local files in {settings.data_raw_dir}/")
            for path, count in local_results.items():
                print(f"  Local {path}: {count} chunks")
        except Exception as exc:
            print(f"  Local ingest failed — {exc}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
