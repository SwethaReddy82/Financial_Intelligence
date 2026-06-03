import logging

from fastapi import APIRouter, HTTPException
from openai import AuthenticationError, RateLimitError
from pydantic import BaseModel, Field

from app.agents.graph import run_copilot
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _root_cause(exc: BaseException) -> BaseException:
    """Unwrap LangGraph / ExceptionGroup chains to the underlying error."""
    seen: set[int] = set()
    current = exc
    while id(current) not in seen:
        seen.add(id(current))
        if current.__cause__ is not None:
            current = current.__cause__
            continue
        if isinstance(current, BaseExceptionGroup) and current.exceptions:
            current = current.exceptions[0]
            continue
        break
    return current


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    ticker: str | None = Field(None, description="Optional filter, e.g. AAPL")


class ChunkMetadata(BaseModel):
    company_name: str | None = None
    ticker: str | None = None
    filing_type: str | None = None
    filing_year: str | None = None
    section_name: str | None = None
    page_number: int | None = None
    source_document: str | None = None


class SourceCitation(BaseModel):
    chunk_id: str
    ticker: str
    excerpt: str
    score: float | None = None
    form_type: str | None = None
    source_url: str | None = None
    section_name: str | None = None
    company_name: str | None = None
    filing_type: str | None = None
    filing_year: str | None = None
    page_number: int | None = None
    source_document: str | None = None
    metadata: ChunkMetadata | None = None
    title: str | None = None


class UserAnswer(BaseModel):
    answer: str = ""
    key_details: list[str] = []
    relevant_metrics: list[str] = []
    sources: list[str] = []
    confidence: str = "Low"
    confidence_percent: int = 0
    confidence_display: str = "Low (0%)"
    text: str = ""


class RetrievedChunkDebug(BaseModel):
    chunk_id: str
    ticker: str | None = None
    section_name: str | None = None
    relevance_score: float | None = None


class DebugInfo(BaseModel):
    detected_companies: list[dict[str, str]] = []
    detected_domain: str | None = None
    domain_relevance_score: float | None = None
    retrieval_skipped: bool = False
    retrieval_skip_reason: str | None = None
    applied_filters: dict = {}
    retrieved_chunks: list[RetrievedChunkDebug] = []
    relevance_scores: list[float] = []
    additional_sources: list[str] = []
    groundedness_score: float | None = None
    confidence_display: str | None = None
    confidence_percent: int | None = None
    citation_coverage: float | None = None
    hallucination_risk: float | None = None
    has_unmarked_inference: bool | None = None
    validation_notes: str = ""
    company_coverage: list[dict] = []
    route: str = ""
    confidence_score: float = 0.0
    response_mode: str = ""
    evaluation_notes: str | None = None


class ChatResponse(BaseModel):
    user_answer: UserAnswer
    debug_info: DebugInfo
    sources: list[SourceCitation] = []
    # Legacy fields kept for compatibility; mirror user_answer where possible
    answer: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    route: str = "refuse"


def _build_source_citations(sources_raw: list[dict]) -> list[SourceCitation]:
    from app.agents.user_response import format_source_title

    sources: list[SourceCitation] = []
    for s in sources_raw:
        meta = s.get("metadata") or {}
        title = format_source_title({**meta, **s})
        sources.append(
            SourceCitation(
                chunk_id=s["chunk_id"],
                ticker=s["ticker"],
                excerpt=s.get("excerpt", ""),
                score=s.get("score"),
                form_type=s.get("form_type"),
                source_url=s.get("source_url"),
                section_name=s.get("section_name"),
                company_name=s.get("company_name") or meta.get("company_name"),
                filing_type=s.get("filing_type") or meta.get("filing_type"),
                filing_year=s.get("filing_year") or meta.get("filing_year"),
                page_number=s.get("page_number") or meta.get("page_number"),
                source_document=s.get("source_document") or meta.get("source_document"),
                title=title,
                metadata=ChunkMetadata(
                    company_name=meta.get("company_name") or s.get("company_name"),
                    ticker=meta.get("ticker") or s.get("ticker"),
                    filing_type=meta.get("filing_type") or s.get("filing_type"),
                    filing_year=meta.get("filing_year") or s.get("filing_year"),
                    section_name=meta.get("section_name") or s.get("section_name"),
                    page_number=meta.get("page_number") or s.get("page_number"),
                    source_document=meta.get("source_document") or s.get("source_document"),
                ),
            )
        )
    return sources


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Run the agentic copilot workflow (retrieve → answer with citations)."""
    if not settings.openai_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "OpenAI API key is missing or still the .env.example placeholder. "
                "Set OPENAI_API_KEY in the project root .env file and restart the backend."
            ),
        )

    try:
        result = await run_copilot(message=request.message, ticker=request.ticker)
        ua_raw = result.get("user_answer") or {}
        di_raw = result.get("debug_info") or {}

        if not ua_raw.get("answer") and not ua_raw.get("text"):
            legacy = (result.get("answer_body") or result.get("answer") or "").strip()
            if legacy:
                ua_raw = {
                    "answer": legacy,
                    "key_details": [],
                    "relevant_metrics": [],
                    "sources": [],
                    "confidence": "Medium",
                    "text": legacy,
                }

        user_answer = UserAnswer(
            answer=ua_raw.get("answer", ""),
            key_details=ua_raw.get("key_details", []),
            relevant_metrics=ua_raw.get("relevant_metrics", []),
            sources=ua_raw.get("sources", []),
            confidence=ua_raw.get("confidence", "Low"),
            confidence_percent=int(ua_raw.get("confidence_percent", 0)),
            confidence_display=ua_raw.get("confidence_display", "Low (0%)"),
            text=ua_raw.get("text") or ua_raw.get("answer", ""),
        )
        debug_info = DebugInfo(
            detected_companies=di_raw.get("detected_companies", []),
            detected_domain=di_raw.get("detected_domain"),
            domain_relevance_score=di_raw.get("domain_relevance_score"),
            retrieval_skipped=bool(di_raw.get("retrieval_skipped", False)),
            retrieval_skip_reason=di_raw.get("retrieval_skip_reason"),
            applied_filters=di_raw.get("applied_filters", {}),
            retrieved_chunks=[
                RetrievedChunkDebug(**c) for c in di_raw.get("retrieved_chunks", [])
            ],
            relevance_scores=di_raw.get("relevance_scores", []),
            additional_sources=di_raw.get("additional_sources", []),
            groundedness_score=di_raw.get("groundedness_score"),
            confidence_display=di_raw.get("confidence_display"),
            confidence_percent=di_raw.get("confidence_percent"),
            citation_coverage=di_raw.get("citation_coverage"),
            hallucination_risk=di_raw.get("hallucination_risk"),
            has_unmarked_inference=di_raw.get("has_unmarked_inference"),
            validation_notes=di_raw.get("validation_notes", ""),
            company_coverage=di_raw.get("company_coverage", []),
            route=di_raw.get("route", result.get("route", "refuse")),
            confidence_score=di_raw.get("confidence_score", result.get("confidence", 0.0)),
            response_mode=di_raw.get("response_mode", ""),
            evaluation_notes=di_raw.get("evaluation_notes"),
        )

        return ChatResponse(
            user_answer=user_answer,
            debug_info=debug_info,
            sources=_build_source_citations(result.get("sources", [])),
            answer=user_answer.text,
            confidence=result.get("confidence", 0.0),
            route=result.get("route", "refuse"),
        )
    except (AuthenticationError, RateLimitError, ConnectionRefusedError) as exc:
        _raise_service_unavailable(exc)
    except Exception as exc:
        root = _root_cause(exc)
        if isinstance(root, (AuthenticationError, RateLimitError, ConnectionRefusedError)):
            _raise_service_unavailable(root)
        logger.exception("chat failed")
        raise HTTPException(status_code=500, detail=str(root)) from exc


def _raise_service_unavailable(exc: BaseException) -> None:
    if isinstance(exc, AuthenticationError):
        raise HTTPException(
            status_code=503,
            detail=(
                "Invalid OPENAI_API_KEY. Update ~/wealth-intelligence-copilot/.env "
                "then stop ALL uvicorn processes and run: make backend"
            ),
        ) from None
    if isinstance(exc, RateLimitError):
        raise HTTPException(
            status_code=503,
            detail="OpenAI rate limit or quota exceeded. Check billing at platform.openai.com.",
        ) from None
    if isinstance(exc, ConnectionRefusedError):
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to PostgreSQL. Start with: make db-up",
        ) from None
    raise HTTPException(status_code=503, detail=str(exc)) from None
