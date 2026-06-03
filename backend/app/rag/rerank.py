"""Re-rank retrieved chunks: semantic score + section + company + financial signals."""

import logging
import re
from dataclasses import dataclass

from app.rag.chunking import FINANCIAL_KEYWORDS, SECTION_PATTERNS
from app.rag.entities import NAMED_REGULATORS

logger = logging.getLogger(__name__)

# Extra weight for priority sections (added to composite score)
SECTION_WEIGHTS: dict[str, float] = {
    "PRIVATE_CLIENT_GROUP": 0.22,
    "BUSINESS": 0.14,
    "RISK_FACTORS": 0.12,
    "MD_AND_A": 0.16,
    "FINANCIAL_HIGHLIGHTS": 0.18,
    "SEGMENTS": 0.12,
    "FINANCIAL_STATEMENTS": 0.08,
    "GENERAL": 0.0,
}

# Query intents → prefer these sections
QUERY_SECTION_HINTS: list[tuple[str, list[str]]] = [
    (
        r"(?i)wealth\s+management|private\s+client|pcg|advisor|financial\s+planning",
        ["PRIVATE_CLIENT_GROUP", "BUSINESS", "SEGMENTS"],
    ),
    (r"(?i)risk|regulat|compliance|supervis", ["RISK_FACTORS"]),
    (r"(?i)compar|differ|versus|across|between", ["RISK_FACTORS", "BUSINESS", "MD_AND_A"]),
    (r"(?i)revenue|earnings|financial\s+results|md&a", ["MD_AND_A", "FINANCIAL_HIGHLIGHTS"]),
    (r"(?i)segment|business\s+line", ["SEGMENTS", "BUSINESS"]),
]

TICKER_ALIASES: dict[str, list[str]] = {
    "RJF": ["raymond james", "rjf"],
    "JPM": ["jpmorgan", "jpm", "jpmc"],
    "MS": ["morgan stanley"],
    "GS": ["goldman sachs", "goldman"],
    "SCHW": ["schwab", "charles schwab"],
    "AAPL": ["apple"],
}


@dataclass
class ScoredChunk:
    chunk_id: str
    ticker: str
    content: str
    semantic_score: float
    composite_score: float
    form_type: str | None
    source_url: str | None
    metadata: dict
    section_name: str | None
    rerank_reasons: list[str]


def _infer_section(text: str, metadata: dict) -> str:
    if metadata.get("section_name"):
        return str(metadata["section_name"])
    lower = text[:1000].lower()
    for label, pattern in SECTION_PATTERNS:
        if re.search(pattern, text[:600], re.MULTILINE):
            return label
    if "private client group" in lower:
        return "PRIVATE_CLIENT_GROUP"
    if "risk factor" in lower:
        return "RISK_FACTORS"
    if "management's discussion" in lower or "md&a" in lower:
        return "MD_AND_A"
    return "GENERAL"


def _section_boost(section: str, query: str) -> tuple[float, str | None]:
    boost = SECTION_WEIGHTS.get(section, 0.0)
    reason = None
    for pattern, preferred in QUERY_SECTION_HINTS:
        if re.search(pattern, query):
            if section in preferred:
                boost += 0.12
                reason = f"query→{section}"
            break
    return boost, reason


def _financial_boost(text: str, query: str) -> tuple[float, bool]:
    lower = text.lower()
    q_lower = query.lower()
    hits = sum(1 for kw in FINANCIAL_KEYWORDS if kw in lower)
    q_hits = sum(1 for kw in FINANCIAL_KEYWORDS if kw in q_lower and kw in lower)
    has_numbers = bool(re.search(r"\$[\d,.]+\s*(billion|million|B|M)?|\d{1,3}(?:\.\d+)?%", lower))
    boost = min(0.2, hits * 0.025) + (0.08 if has_numbers else 0) + (0.05 if q_hits else 0)
    return boost, has_numbers or hits >= 3


def _regulatory_entity_boost(text: str) -> tuple[float, bool]:
    """Prefer chunks that name specific regulators/frameworks."""
    lower = text.lower()
    hits = 0
    for ent in NAMED_REGULATORS:
        if ent.lower() in lower:
            hits += 1
    boost = min(0.22, hits * 0.04)
    return boost, hits > 0


def _comparative_ticker_boost(
    chunk_ticker: str,
    tickers_mentioned: list[str],
    is_comparative: bool,
) -> tuple[float, str | None]:
    if not is_comparative or not tickers_mentioned:
        return 0.0, None
    if chunk_ticker.upper() in [t.upper() for t in tickers_mentioned]:
        return 0.08, "comparative_ticker"
    return 0.0, None


def _company_boost(ticker: str, query: str, metadata: dict) -> tuple[float, str | None]:
    aliases = TICKER_ALIASES.get(ticker.upper(), [ticker.lower()])
    q = query.lower()
    if any(a in q for a in aliases):
        return 0.1, "query_company_match"
    company = (metadata.get("company_name") or "").lower()
    if company and any(a in company for a in aliases):
        return 0.05, "metadata_company"
    return 0.0, None


def rerank_chunks(
    chunks: list[dict],
    query: str,
    ticker: str | None = None,
    final_k: int = 10,
    *,
    is_comparative: bool = False,
    tickers_mentioned: list[str] | None = None,
) -> list[ScoredChunk]:
    """Re-rank candidate chunks; return top final_k by composite score."""
    scored: list[ScoredChunk] = []

    for c in chunks:
        meta = c.get("metadata") or {}
        text = c.get("content") or c.get("excerpt") or ""
        semantic = float(c.get("score") or 0)
        section = _infer_section(text, meta)
        reasons: list[str] = []

        sec_b, sec_r = _section_boost(section, query)
        if sec_r:
            reasons.append(sec_r)
        fin_b, fin_dense = _financial_boost(text, query)
        if fin_dense:
            reasons.append("financial_metrics")
        co_b, co_r = _company_boost(c.get("ticker", ""), query, meta)
        if co_r:
            reasons.append(co_r)
        reg_b, reg_hit = _regulatory_entity_boost(text)
        if reg_hit:
            reasons.append("named_regulator")
        cmp_b, cmp_r = _comparative_ticker_boost(
            c.get("ticker", ""),
            tickers_mentioned or [],
            is_comparative,
        )
        if cmp_r:
            reasons.append(cmp_r)

        # Penalize wrong ticker when user specified one (not in comparative multi-company mode)
        if ticker and not is_comparative and c.get("ticker", "").upper() != ticker.upper():
            co_b -= 0.35

        composite = semantic + sec_b + fin_b + co_b + reg_b + cmp_b
        composite = min(1.0, round(composite, 4))

        scored.append(
            ScoredChunk(
                chunk_id=c["chunk_id"],
                ticker=c["ticker"],
                content=text,
                semantic_score=semantic,
                composite_score=composite,
                form_type=c.get("form_type"),
                source_url=c.get("source_url"),
                metadata=meta,
                section_name=section,
                rerank_reasons=reasons,
            )
        )

    scored.sort(key=lambda x: x.composite_score, reverse=True)

    # Comparative: ensure representation from each mentioned ticker in top-k
    top = scored[:final_k]
    if is_comparative and tickers_mentioned and len(tickers_mentioned) >= 2:
        top = _diversify_by_ticker(scored, tickers_mentioned, final_k)

    if logger.isEnabledFor(logging.INFO):
        logger.info(
            "rerank query=%r ticker=%s top_sections=%s",
            query[:80],
            ticker,
            [f"{t.section_name}:{t.composite_score}" for t in top[:5]],
        )

    return top


def _diversify_by_ticker(
    scored: list[ScoredChunk],
    tickers: list[str],
    final_k: int,
) -> list[ScoredChunk]:
    """Reserve slots so each compared company appears in the final context."""
    per_ticker_min = max(2, final_k // len(tickers))
    selected: list[ScoredChunk] = []
    seen_ids: set[str] = set()

    for t in tickers:
        count = 0
        for item in scored:
            if item.chunk_id in seen_ids:
                continue
            if item.ticker.upper() == t.upper():
                selected.append(item)
                seen_ids.add(item.chunk_id)
                count += 1
                if count >= per_ticker_min:
                    break

    for item in scored:
        if len(selected) >= final_k:
            break
        if item.chunk_id not in seen_ids:
            selected.append(item)
            seen_ids.add(item.chunk_id)

    selected.sort(key=lambda x: x.composite_score, reverse=True)
    return selected[:final_k]
