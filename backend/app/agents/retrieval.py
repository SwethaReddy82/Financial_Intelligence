"""Retrieval agent: vector search + financial-aware re-ranking."""

import logging

from app.agents.tools import search_filings

logger = logging.getLogger(__name__)


async def run_retrieval(state: dict) -> dict:
    query = state["message"]
    ticker = state.get("ticker")

    logger.info("RETRIEVAL AGENT query=%r ticker=%s", query, ticker)

    context, debug, analysis = await search_filings(query=query, ticker=ticker)

    debug_payload = None
    if debug:
        debug_payload = debug if isinstance(debug, dict) else debug.__dict__

    return {
        "context": context,
        "retrieval_debug": debug_payload,
        "query_analysis": analysis,
        "response_mode": analysis.get("response_mode", "standard"),
        "route": "refuse" if analysis.get("retrieval_skipped") else state.get("route", "refuse"),
        "confidence": 0.0 if analysis.get("retrieval_skipped") else state.get("confidence", 0.0),
        "validation_notes": (
            "This assistant specializes in financial filings, annual reports, and company analysis. "
            "Please ask a finance-related question."
            if analysis.get("detected_domain") == "out_of_domain"
            else state.get("validation_notes", "")
        ),
    }
