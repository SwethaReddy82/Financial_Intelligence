"""
Multi-agent LangGraph workflow:

  Retrieval → Validation (confidence routing) → Response generation
"""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.response import generate_grounded_answer
from app.agents.retrieval import run_retrieval
from app.agents.validation import validate_evidence

Route = Literal["refuse", "cautious", "answer"]


class CopilotState(TypedDict, total=False):
    message: str
    ticker: str | None
    context: list[dict]
    confidence: float
    route: Route
    validation_notes: str
    answer: str
    answer_body: str
    summary: str
    common_risks_text: str
    differences_text: str
    key_metrics: dict[str, str]
    evaluation: dict[str, Any] | None
    retrieval_debug: dict[str, Any] | None
    query_analysis: dict[str, Any] | None
    response_mode: str
    retrieved_evidence_text: str
    synthesized_insights_text: str
    coverage_text: str
    company_coverage: list[dict]
    user_answer: dict[str, Any] | None
    debug_info: dict[str, Any] | None


async def retrieval_node(state: CopilotState) -> dict:
    return await run_retrieval(state)


async def validation_node(state: CopilotState) -> dict:
    analysis = state.get("query_analysis") or {}
    if analysis.get("retrieval_skipped"):
        return {
            "confidence": 0.0,
            "route": "refuse",
            "validation_notes": state.get("validation_notes", ""),
            "company_coverage": [],
        }
    expected = analysis.get("tickers_mentioned") or []
    return validate_evidence(state.get("context", []), expected_tickers=expected or None)


def route_after_validation(state: CopilotState) -> str:
    if state.get("route") == "refuse":
        return "refuse"
    return "generate"


async def refuse_node(state: CopilotState) -> dict:
    return await generate_grounded_answer(state)


async def generate_node(state: CopilotState) -> dict:
    return await generate_grounded_answer(state)


def build_graph():
    graph = StateGraph(CopilotState)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("validate", validation_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validation,
        {"refuse": "refuse", "generate": "generate"},
    )
    graph.add_edge("refuse", END)
    graph.add_edge("generate", END)
    return graph.compile()


_copilot = build_graph()


async def run_copilot(message: str, ticker: str | None = None) -> dict:
    final = await _copilot.ainvoke(
        {
            "message": message,
            "ticker": ticker,
            "context": [],
            "confidence": 0.0,
            "route": "refuse",
            "validation_notes": "",
            "answer": "",
        }
    )
    context_sorted = sorted(
        final.get("context", []),
        key=lambda c: float(c.get("composite_score") or c.get("score") or 0),
        reverse=True,
    )
    sources = [
        {
            "chunk_id": c["chunk_id"],
            "ticker": c["ticker"],
            "excerpt": (c.get("excerpt") or "")[:400],
            "score": c.get("score"),
            "form_type": c.get("form_type"),
            "source_url": c.get("source_url"),
            "section_name": c.get("section_name"),
            "metadata": c.get("metadata"),
            "company_name": c.get("company_name") or (c.get("metadata") or {}).get("company_name"),
            "filing_type": c.get("filing_type") or (c.get("metadata") or {}).get("filing_type"),
            "filing_year": c.get("filing_year") or (c.get("metadata") or {}).get("filing_year"),
            "page_number": c.get("page_number") or (c.get("metadata") or {}).get("page_number"),
            "source_document": c.get("source_document")
            or (c.get("metadata") or {}).get("source_document"),
        }
        for c in context_sorted
    ]
    retrieval_debug = final.get("retrieval_debug")
    if retrieval_debug and hasattr(retrieval_debug, "__dict__"):
        retrieval_debug = retrieval_debug.__dict__
    return {
        "answer": final.get("answer", ""),
        "answer_body": final.get("answer_body", ""),
        "user_answer": final.get("user_answer"),
        "debug_info": final.get("debug_info"),
        "summary": final.get("summary", ""),
        "common_risks_text": final.get("common_risks_text", ""),
        "differences_text": final.get("differences_text", ""),
        "key_metrics": final.get("key_metrics") or {},
        "sources": sources,
        "confidence": final.get("confidence", 0.0),
        "route": final.get("route", "refuse"),
        "validation_notes": final.get("validation_notes", ""),
        "evaluation": final.get("evaluation"),
        "retrieval_debug": retrieval_debug,
        "response_mode": final.get("response_mode", "standard"),
        "retrieved_evidence_text": final.get("retrieved_evidence_text", ""),
        "synthesized_insights_text": final.get("synthesized_insights_text", ""),
        "company_coverage": final.get("company_coverage") or [],
    }
