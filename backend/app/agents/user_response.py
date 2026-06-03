"""Format executive-quality user answers and separate debug payloads."""

import re
from typing import Any

from app.agents.evidence import INSUFFICIENT_EVIDENCE

_SECTION_LABELS = {
    "PRIVATE_CLIENT_GROUP": "Private Client Group",
    "RISK_FACTORS": "Risk Factors",
    "MD_AND_A": "Management Discussion & Analysis",
    "FINANCIAL_HIGHLIGHTS": "Financial Highlights",
    "BUSINESS": "Business",
    "SEGMENTS": "Business Segments",
    "FINANCIAL_STATEMENTS": "Financial Statements",
    "GENERAL": "General",
}

_FILING_LABELS = {
    "10-K": "Form 10-K",
    "10-Q": "Form 10-Q",
    "ANNUAL_REPORT": "Annual Report",
    "EARNINGS_TRANSCRIPT": "Earnings Transcript",
    "INVESTOR_PRESENTATION": "Investor Presentation",
}

_GENERIC_PHRASES = re.compile(
    r"(?i)\b("
    r"comprehensive service offering|focuses on enhancing|is committed to|aims to|"
    r"continues to focus|robust platform|holistic approach|leverage synergies|"
    r"best-in-class|drive value|strategic initiatives without|numerous initiatives"
    r")\b"
)

_MAX_USER_SOURCES = 3
_MAX_KEY_DETAILS = 5
_MAX_METRICS = 4


def confidence_label(confidence: float, route: str) -> str:
    if route == "refuse" or confidence < 0.35:
        return "Low"
    if route == "cautious" or confidence < 0.6:
        return "Medium"
    return "High"


def format_confidence_display(confidence: float, route: str) -> tuple[str, int]:
    """Return e.g. ('High (87%)', 87)."""
    label = confidence_label(confidence, route)
    pct = int(round(max(0.0, min(1.0, confidence)) * 100))
    return f"{label} ({pct}%)", pct


def _humanize_section(name: str | None) -> str | None:
    if not name:
        return None
    key = name.upper().replace(" ", "_")
    return _SECTION_LABELS.get(key, name.replace("_", " ").title())


def _humanize_filing_type(ft: str | None) -> str | None:
    if not ft:
        return None
    return _FILING_LABELS.get(ft.upper(), ft.replace("_", " ").title())


def _strip_citation_markers(text: str) -> str:
    return re.sub(r"\s*\[\d+\]", "", text).strip()


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _polish_prose(text: str) -> str:
    """Light cleanup for executive readability."""
    if not text:
        return text
    t = _strip_citation_markers(text)
    t = _GENERIC_PHRASES.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()


def format_source_title(source: dict[str, Any]) -> str:
    """Build a readable source line, e.g. Raymond James 2025 Annual Report — Private Client Group."""
    company = source.get("company_name") or source.get("ticker") or "Source"
    year = source.get("filing_year")
    filing = _humanize_filing_type(source.get("filing_type") or source.get("form_type"))
    section = _humanize_section(source.get("section_name"))

    doc = (source.get("source_document") or "").lower()
    if "annual report" in doc:
        title = f"{company} {year or ''} Annual Report".strip()
    elif filing and year:
        title = f"{company} {year} {filing}".strip()
    elif filing:
        title = f"{company} {filing}".strip()
    else:
        title = str(company)

    if section and section.lower() not in title.lower():
        return f"{title} — {section}"
    return title


def _chunk_score(item: dict[str, Any]) -> float:
    return float(
        item.get("composite_score")
        or item.get("score")
        or item.get("semantic_score")
        or 0
    )


def rank_sources_from_context(context: list[dict]) -> list[dict[str, Any]]:
    """Order chunks by relevance for source display."""
    ranked = sorted(context, key=_chunk_score, reverse=True)
    return ranked


def _unique_source_lines(
    sources: list[dict[str, Any]], max_items: int | None = None
) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for s in sources:
        line = format_source_title(s)
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
        if max_items and len(lines) >= max_items:
            break
    return lines


def _dedupe_bullets(items: list[str], max_items: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = _polish_prose(_normalize_ws(raw))
        if not item or len(item) < 8:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", item.lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def _dedupe_metrics(items: list[str], max_items: int) -> list[str]:
    seen_labels: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = _polish_prose(_strip_citation_markers(raw))
        if not item:
            continue
        label_key = item.split(":")[0].lower().strip() if ":" in item else item.lower()[:40]
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def _parse_bullet_block(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        line = _strip_citation_markers(line.strip())
        if not line:
            continue
        if line.startswith(("-", "•", "*")):
            line = line.lstrip("-•* ").strip()
        if line:
            items.append(line)
    return items


def build_user_answer_text(
    *,
    answer: str,
    key_details: list[str],
    relevant_metrics: list[str],
    sources: list[str],
    confidence_display: str,
) -> str:
    sections = [f"Answer:\n{answer.strip()}"]

    if key_details:
        sections.append("Key Details:\n" + "\n".join(f"- {d}" for d in key_details))

    if relevant_metrics:
        sections.append("Relevant Metrics:\n" + "\n".join(f"- {m}" for m in relevant_metrics))

    if sources:
        sections.append("Sources:\n" + "\n".join(f"- {s}" for s in sources))

    sections.append(f"Confidence:\n{confidence_display}")
    return "\n\n".join(sections)


def build_user_answer(
    *,
    parsed: dict,
    context: list[dict],
    confidence: float,
    route: str,
    is_comparative: bool,
    insufficient: bool,
) -> dict[str, Any]:
    confidence_display, confidence_percent = format_confidence_display(confidence, route)
    conf_level = confidence_label(confidence, route)

    ranked_ctx = rank_sources_from_context(context)
    all_source_lines = _unique_source_lines(ranked_ctx)
    user_sources = all_source_lines[:_MAX_USER_SOURCES]
    additional_sources = all_source_lines[_MAX_USER_SOURCES:]

    if insufficient:
        answer = (
            "The indexed filings do not contain enough relevant disclosure to answer this "
            "confidently. Try naming a specific company or asking about a segment such as "
            "Private Client Group, risk factors, or a specific metric."
        )
        return {
            "answer": answer,
            "key_details": [],
            "relevant_metrics": [],
            "sources": user_sources,
            "additional_sources": additional_sources,
            "confidence": conf_level,
            "confidence_percent": confidence_percent,
            "confidence_display": confidence_display,
            "text": build_user_answer_text(
                answer=answer,
                key_details=[],
                relevant_metrics=[],
                sources=user_sources,
                confidence_display=confidence_display,
            ),
        }

    answer_body = _polish_prose(
        parsed.get("summary") or parsed.get("answer_body") or ""
    )
    if not answer_body.strip():
        raw = (parsed.get("synthesized_raw") or "").strip()
        if raw and INSUFFICIENT_EVIDENCE.lower() not in raw.lower():
            answer_body = _polish_prose(raw[:2000])

    key_details = _dedupe_bullets(list(parsed.get("key_details") or []), _MAX_KEY_DETAILS)

    if is_comparative:
        extra: list[str] = []
        if parsed.get("common_risks_text"):
            extra.extend(_parse_bullet_block(parsed["common_risks_text"]))
        if parsed.get("differences_text"):
            extra.extend(_parse_bullet_block(parsed["differences_text"]))
        key_details = _dedupe_bullets(key_details + extra, _MAX_KEY_DETAILS)

    relevant_metrics = _dedupe_metrics(
        list(parsed.get("relevant_metrics") or []), _MAX_METRICS
    )

    km = parsed.get("key_metrics") or {}
    if len(relevant_metrics) < _MAX_METRICS and km:
        for label, key in (
            ("PCG net revenues", "revenue"),
            ("Client assets under administration", "assets"),
            ("Financial advisors", "advisors"),
            ("Growth", "growth"),
        ):
            val = km.get(key)
            if val and "not in" not in val.lower() and "not stated" not in val.lower():
                relevant_metrics = _dedupe_metrics(
                    relevant_metrics + [f"{label}: {_strip_citation_markers(val)}"],
                    _MAX_METRICS,
                )

    llm_sources: list[str] = []
    if parsed.get("sources_section"):
        llm_sources = [
            _polish_prose(line)
            for line in _parse_bullet_block(parsed["sources_section"])
        ]
    if llm_sources:
        user_sources = _dedupe_bullets(
            llm_sources[:_MAX_USER_SOURCES] + user_sources, _MAX_USER_SOURCES
        )
        # treat overflow LLM sources as additional
        extra_from_llm = llm_sources[_MAX_USER_SOURCES:]
        additional_sources = _dedupe_bullets(
            extra_from_llm + additional_sources, 20
        )

    return {
        "answer": answer_body,
        "key_details": key_details,
        "relevant_metrics": relevant_metrics,
        "sources": user_sources,
        "additional_sources": additional_sources,
        "confidence": conf_level,
        "confidence_percent": confidence_percent,
        "confidence_display": confidence_display,
        "text": build_user_answer_text(
            answer=answer_body,
            key_details=key_details,
            relevant_metrics=relevant_metrics,
            sources=user_sources,
            confidence_display=confidence_display,
        ),
    }


def build_debug_info(
    *,
    retrieval_debug: dict | None,
    evaluation: dict | None,
    validation_notes: str,
    route: str,
    confidence: float,
    company_coverage: list[dict],
    context: list[dict],
    response_mode: str,
    additional_sources: list[str] | None = None,
) -> dict[str, Any]:
    rd = retrieval_debug or {}
    ev = evaluation or {}

    retrieved_chunks = []
    chunk_ids = rd.get("chunk_ids") or []
    scores = rd.get("scores") or []
    for i, cid in enumerate(chunk_ids):
        ctx = next((c for c in context if c.get("chunk_id") == cid), None)
        retrieved_chunks.append(
            {
                "chunk_id": cid,
                "ticker": (ctx or {}).get("ticker"),
                "section_name": (ctx or {}).get("section_name")
                or ((ctx or {}).get("metadata") or {}).get("section_name"),
                "relevance_score": scores[i] if i < len(scores) else None,
            }
        )

    filters = rd.get("applied_filters") or {}
    applied_filters_readable = filters
    if filters.get("tickers"):
        applied_filters_readable = {
            "companies": filters.get("tickers"),
            "mode": filters.get("filter", "metadata"),
        }

    conf_display, conf_pct = format_confidence_display(confidence, route)

    return {
        "detected_companies": rd.get("detected_companies", []),
        "detected_domain": rd.get("detected_domain"),
        "domain_relevance_score": rd.get("domain_relevance_score"),
        "retrieval_skipped": bool(rd.get("retrieval_skipped")),
        "retrieval_skip_reason": rd.get("skip_reason"),
        "applied_filters": applied_filters_readable,
        "retrieved_chunks": retrieved_chunks,
        "relevance_scores": scores,
        "additional_sources": additional_sources or [],
        "groundedness_score": ev.get("groundedness_score"),
        "citation_coverage": ev.get("citation_coverage"),
        "hallucination_risk": ev.get("hallucination_risk"),
        "has_unmarked_inference": ev.get("has_unmarked_inference"),
        "validation_notes": validation_notes,
        "company_coverage": company_coverage,
        "route": route,
        "confidence_score": confidence,
        "confidence_display": conf_display,
        "confidence_percent": conf_pct,
        "response_mode": response_mode,
        "evaluation_notes": ev.get("notes"),
    }
