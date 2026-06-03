"""Detect company names and tickers from user queries for metadata filtering."""

import re
from dataclasses import dataclass

from app.ingestion.knowledge_base import KNOWLEDGE_BASE_TICKERS

INDEXED_TICKERS = frozenset(KNOWLEDGE_BASE_TICKERS.keys())

# Longer phrases first
TICKER_ALIASES: list[tuple[str, str]] = [
    ("raymond james financial", "RJF"),
    ("raymond james", "RJF"),
    ("morgan stanley", "MS"),
    ("jpmorgan chase", "JPM"),
    ("jpmorgan", "JPM"),
    ("jpm chase", "JPM"),
    ("jpmc", "JPM"),
    ("goldman sachs", "GS"),
    ("goldman", "GS"),
    ("charles schwab", "SCHW"),
    ("schwab", "SCHW"),
    ("apple inc", "AAPL"),
    ("apple", "AAPL"),
]


@dataclass(frozen=True)
class DetectedCompany:
    ticker: str
    company_name: str


def extract_tickers_from_query(query: str) -> list[str]:
    q = query.lower()
    found: list[str] = []
    for phrase, ticker in TICKER_ALIASES:
        if phrase in q and ticker not in found:
            found.append(ticker)
    for ticker in INDEXED_TICKERS:
        if re.search(rf"\b{re.escape(ticker)}\b", query, re.I) and ticker not in found:
            found.append(ticker)
    return found


def detect_companies_from_query(query: str) -> list[DetectedCompany]:
    """Return companies mentioned in the query with display names."""
    companies: list[DetectedCompany] = []
    for ticker in extract_tickers_from_query(query):
        companies.append(
            DetectedCompany(
                ticker=ticker,
                company_name=KNOWLEDGE_BASE_TICKERS.get(ticker, ticker),
            )
        )
    return companies
