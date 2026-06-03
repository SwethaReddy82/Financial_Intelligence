"""Detect comparative / regulatory questions and extract target companies."""

import re

from app.rag.company_detection import extract_tickers_from_query
from app.core.config import settings

COMPARATIVE_PATTERNS = re.compile(
    r"(?i)\b(compare|comparison|comparing|versus|vs\.?|differ|difference|differences|"
    r"similarities|contrast|across|between|both|each other|relative to|how do .+ and)\b"
)

RISK_COMPARE_PATTERNS = re.compile(
    r"(?i)\b(risk|risks|regulatory|regulation|compliance|supervis|capital requirement|stress test)\b"
)

FINANCE_DOMAIN_TERMS = (
    "sec",
    "10-k",
    "10q",
    "10-q",
    "annual report",
    "filing",
    "business strategy",
    "financial metrics",
    "regulation",
    "wealth management",
    "risk factors",
    "banking",
    "investment firm",
    "investment firms",
    "company comparison",
    "revenue",
    "net income",
    "capital ratio",
    "client assets",
    "advisors",
    "aum",
    "assets under management",
    "fee-based",
    "basel",
    "ccar",
    "occ",
    "finra",
    "federal reserve",
    "cfpb",
    "wealth",
    "advisor",
    "advisory",
    "private client",
    "client assets under administration",
    "income statement",
    "balance sheet",
    "cash flow",
    "earnings",
    "guidance",
    "valuation",
    "profitability",
    "margin",
    "segment",
    "assets",
    "liabilities",
    "equity",
    "jpmorgan",
    "raymond james",
    "morgan stanley",
    "goldman",
    "schwab",
)

OUT_OF_DOMAIN_HINTS = (
    "ipl",
    "cricket",
    "sports",
    "weather",
    "temperature",
    "joke",
    "trivia",
    "movie",
    "recipe",
    "code",
    "coding",
    "python bug",
    "javascript bug",
)


def domain_relevance_score(query: str, tickers_mentioned: list[str]) -> tuple[str, float]:
    q = query.lower()
    finance_hits = sum(1 for term in FINANCE_DOMAIN_TERMS if term in q)
    ood_hits = sum(1 for term in OUT_OF_DOMAIN_HINTS if term in q)
    ticker_bonus = 1 if tickers_mentioned else 0
    risk_bonus = 1 if RISK_COMPARE_PATTERNS.search(query) else 0
    finance_question_intent = bool(
        re.search(
            r"(?i)\b(compare|analy[sz]e|explain|describe|summari[sz]e|evaluate|assess)\b",
            query,
        )
    )
    company_context = bool(
        re.search(
            r"(?i)\b(company|firm|bank|wealth|advisors?|assets?|revenue|earnings|risk|regulat|filing|report)\b",
            query,
        )
    )

    raw = (
        (0.12 * finance_hits)
        + (0.28 * ticker_bonus)
        + (0.18 * risk_bonus)
        + (0.14 if finance_question_intent and company_context else 0.0)
        - (0.40 * ood_hits)
        + (0.25 if (ticker_bonus and finance_hits >= 1) else 0.0)
    )
    score = max(0.0, min(1.0, round(raw, 3)))

    detected_domain = "financial_intelligence" if score >= settings.domain_relevance_threshold else "out_of_domain"
    return detected_domain, score

def analyze_query(query: str, ticker_filter: str | None = None) -> dict:
    is_comparative = bool(COMPARATIVE_PATTERNS.search(query))
    tickers_mentioned = extract_tickers_from_query(query)
    is_risk_focus = bool(RISK_COMPARE_PATTERNS.search(query))

    # "Compare RJF and MS risks" without explicit compare word
    if len(tickers_mentioned) >= 2:
        is_comparative = True

    if ticker_filter and ticker_filter.upper() not in tickers_mentioned:
        tickers_mentioned.insert(0, ticker_filter.upper())

    from app.rag.company_detection import detect_companies_from_query

    detected = detect_companies_from_query(query)
    detected_domain, relevance = domain_relevance_score(query, tickers_mentioned)
    retrieval_skipped = relevance < settings.domain_relevance_threshold

    return {
        "is_comparative": is_comparative,
        "is_risk_focus": is_risk_focus,
        "tickers_mentioned": tickers_mentioned,
        "detected_companies": [
            {"ticker": c.ticker, "company_name": c.company_name} for c in detected
        ],
        "detected_domain": detected_domain,
        "domain_relevance_score": relevance,
        "retrieval_skipped": retrieval_skipped,
        "use_per_ticker_retrieval": is_comparative and not ticker_filter,
        "response_mode": "comparative" if is_comparative else "standard",
    }
