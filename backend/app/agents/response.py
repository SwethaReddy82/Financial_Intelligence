"""Response generation: evidence-first standard + comparative analysis."""

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.evaluation import AnswerEvaluation, evaluate_answer
from app.agents.evidence import (
    INSUFFICIENT_EVIDENCE,
    INFERENCE_WORDS,
    compute_company_coverage,
    find_unmarked_inference_phrases,
    format_retrieved_evidence,
    coverage_confidence_penalty,
    inference_confidence_penalty,
    should_refuse_synthesis,
)
from app.agents.evidence_prompts import (
    COMPARATIVE_OUTPUT_FORMAT,
    EVIDENCE_RULES,
    USER_FACING_OUTPUT_FORMAT,
    WRITING_STYLE,
)
from app.agents.user_response import build_debug_info, build_user_answer
from app.agents.validation import post_validate_answer
from app.core.config import settings

logger = logging.getLogger(__name__)

VAGUE_BANNED = (
    "extensive regulations",
    "various regulations",
    "regulatory bodies",
    "legal risks",
    "operational challenges",
    "numerous risks",
    "significant oversight",
    "subject to regulation",
)

REGULATOR_LIST_STR = ", ".join(
    ["SEC", "Federal Reserve", "OCC", "FINRA", "FDIC", "CFPB", "CFTC", "Basel III", "CCAR", "PCAOB"]
)


def _format_context(context: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(context, start=1):
        meta = c.get("metadata") or {}
        section = c.get("section_name") or meta.get("section_name") or "GENERAL"
        year = meta.get("filing_year") or "?"
        doc = meta.get("source_document") or c.get("form_type") or "filing"
        blocks.append(
            f"[{i}] {c['ticker']} | {section} | {doc} ({year}) | relevance={c.get('score', 0):.2f}\n"
            f"{c.get('excerpt') or c.get('content', '')}"
        )
    return "\n\n".join(blocks)


def _group_context_by_ticker(context: list[dict]) -> str:
    from app.agents.evidence import display_name_for_ticker

    by_ticker: dict[str, list[str]] = {}
    for i, c in enumerate(context, start=1):
        t = c.get("ticker", "?")
        by_ticker.setdefault(t, []).append(
            f"[{i}] {c.get('section_name', 'GENERAL')} | score={c.get('score', 0):.2f}\n"
            f"{c.get('excerpt') or c.get('content', '')[:1200]}"
        )
    parts = []
    for t, blocks in sorted(by_ticker.items()):
        label = display_name_for_ticker(t)
        parts.append(f"=== {label} ({t}) ===\n" + "\n\n".join(blocks))
    return "\n\n".join(parts)


def _build_standard_prompt(route: str) -> str:
    strict = route == "cautious"
    return (
        "You are a financial intelligence assistant briefing wealth management executives "
        "on SEC filings and annual reports.\n"
        + EVIDENCE_RULES
        + WRITING_STYLE
        + ("- Be conservative; omit unsupported claims.\n" if strict else "")
        + USER_FACING_OUTPUT_FORMAT
    )


def _build_comparative_prompt(route: str, tickers: list[str]) -> str:
    companies = ", ".join(tickers) if tickers else "each company in the excerpts"
    return (
        "You are a financial intelligence assistant comparing companies for an executive audience.\n"
        f"Compare: {companies}. Use ONLY the numbered excerpts.\n"
        + EVIDENCE_RULES
        + WRITING_STYLE
        + "\nHighlight meaningful similarities and differences — be specific, not generic.\n"
        + ("\nBe conservative; only compare where excerpts support it.\n" if route == "cautious" else "")
        + COMPARATIVE_OUTPUT_FORMAT
    )


def _parse_synthesis_sections(raw: str, is_comparative: bool) -> dict:
    """Parse user-facing LLM output."""
    out: dict = {
        "synthesized_raw": raw,
        "answer_body": raw,
        "summary": "",
        "common_risks_text": "",
        "differences_text": "",
        "key_details": [],
        "relevant_metrics": [],
        "key_metrics": {},
        "sources_section": "",
        "confidence_label": None,
    }

    conf_m = re.search(
        r"(?is)Confidence:\s*(High|Medium|Low)(?:\s*\((\d+)%\))?", raw
    )
    if conf_m:
        out["confidence_label"] = conf_m.group(1).strip()
        if conf_m.group(2):
            out["confidence_percent"] = int(conf_m.group(2))
    else:
        score_m = re.search(r"(?is)Confidence Score:\s*([\d.]+)", raw)
        if score_m:
            try:
                s = float(score_m.group(1))
                out["confidence_label"] = "High" if s >= 0.7 else "Medium" if s >= 0.45 else "Low"
            except ValueError:
                pass

    trim = raw
    for pat in (r"(?is)Confidence:.*$", r"(?is)Confidence Score:.*$"):
        m = re.search(pat, trim)
        if m:
            trim = trim[: m.start()].strip()

    sources_m = re.search(r"(?is)Sources:\s*(.*?)$", trim, re.MULTILINE)
    if sources_m:
        out["sources_section"] = sources_m.group(1).strip()
        trim = trim[: sources_m.start()].strip()

    metrics_m = re.search(
        r"(?is)Relevant Metrics:\s*(.*?)(?=Sources:|Confidence:|$)", trim
    )
    if not metrics_m:
        metrics_m = re.search(r"(?is)Key Metrics:\s*(.*?)(?=Sources:|Confidence:|$)", trim)
    if metrics_m:
        block = metrics_m.group(1).strip()
        out["relevant_metrics"] = [
            ln.lstrip("-•* ").strip()
            for ln in block.splitlines()
            if ln.strip() and not ln.strip().lower().startswith("confidence")
        ]
        for key in ("Revenue", "Assets", "Advisors", "Growth"):
            line = re.search(rf"(?im)^{key}:\s*(.+)$", block)
            if line:
                out["key_metrics"][key.lower()] = line.group(1).strip()

    details_m = re.search(
        r"(?is)Key Details:\s*(.*?)(?=Relevant Metrics:|Key Metrics:|Sources:|Confidence:|$)",
        trim,
    )
    if details_m:
        out["key_details"] = [
            ln.lstrip("-•* ").strip()
            for ln in details_m.group(1).splitlines()
            if ln.strip()
        ]
        trim = trim[: details_m.start()].strip() + "\n" + trim[details_m.end() :]

    answer_m = re.search(
        r"(?is)Answer:\s*(.*?)(?=Key Details:|Relevant Metrics:|Key Metrics:|Sources:|$)",
        trim,
    )
    if not answer_m and is_comparative:
        answer_m = re.search(
            r"(?is)Summary:\s*(.*?)(?=Key Details:|Common Risks:|Differences:|$)", trim
        )
    if answer_m:
        out["answer_body"] = answer_m.group(1).strip()
        out["summary"] = out["answer_body"]

    if not out["answer_body"].strip():
        # LLM may omit headings — use prose before Key Details / Metrics
        fallback = trim.strip()
        for header in (
            "Key Details:",
            "Relevant Metrics:",
            "Key Metrics:",
            "Sources:",
        ):
            idx = fallback.find(header)
            if idx > 0:
                fallback = fallback[:idx].strip()
        fallback = re.sub(r"^(?i)answer:\s*", "", fallback).strip()
        if len(fallback) > 40:
            out["answer_body"] = fallback
            out["summary"] = fallback

    if is_comparative:
        common_m = re.search(r"(?is)Common Risks:\s*(.*?)(?=Differences:|$)", trim)
        if common_m:
            out["common_risks_text"] = common_m.group(1).strip()
        diff_m = re.search(r"(?is)Differences:\s*(.*?)$", trim)
        if diff_m:
            out["differences_text"] = diff_m.group(1).strip()

    return out


def _check_vague_language(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in VAGUE_BANNED if p in lower]


def _coverage_from_state(state: dict, context: list[dict]) -> list:
    if state.get("company_coverage"):
        from app.agents.evidence import CompanyCoverage

        return [
            CompanyCoverage(
                ticker=c["ticker"],
                display_name=c["display_name"],
                status=c["status"],
                chunk_count=c.get("chunk_count", 0),
                strong_chunk_count=c.get("strong_chunk_count", 0),
            )
            for c in state["company_coverage"]
        ]
    analysis = state.get("query_analysis") or {}
    expected = analysis.get("tickers_mentioned") or []
    return compute_company_coverage(context, expected or None)


async def generate_grounded_answer(state: dict) -> dict:
    context = state.get("context", [])
    route = state.get("route", "answer")
    confidence = float(state.get("confidence", 0))
    response_mode = state.get("response_mode", "standard")
    analysis = state.get("query_analysis") or {}
    is_comparative = response_mode == "comparative"

    coverage_list = _coverage_from_state(state, context)
    retrieved_evidence_text = format_retrieved_evidence(context)
    company_coverage_payload = [
        {
            "ticker": c.ticker,
            "display_name": c.display_name,
            "status": c.status,
            "chunk_count": c.chunk_count,
            "strong_chunk_count": c.strong_chunk_count,
        }
        for c in coverage_list
    ]

    base_return = {
        "retrieved_evidence_text": retrieved_evidence_text,
        "company_coverage": company_coverage_payload,
        "response_mode": response_mode,
    }

    if route == "refuse" or not context:
        conf = confidence if context else 0.0
        domain = (analysis.get("detected_domain") or "").lower()
        ood_message = (
            "This assistant specializes in financial filings, annual reports, and company analysis. "
            "Please ask a finance-related question."
        )
        user_answer = build_user_answer(
            parsed={},
            context=context,
            confidence=conf,
            route="refuse",
            is_comparative=is_comparative,
            insufficient=True,
        )
        if domain == "out_of_domain":
            user_answer["answer"] = ood_message
            user_answer["text"] = (
                "Answer:\n"
                f"{ood_message}\n\n"
                "Confidence:\nLow (0%)"
            )
        debug_info = build_debug_info(
            retrieval_debug=state.get("retrieval_debug"),
            evaluation=None,
            validation_notes=state.get("validation_notes", INSUFFICIENT_EVIDENCE),
            route="refuse",
            confidence=conf,
            company_coverage=company_coverage_payload,
            context=context,
            response_mode=response_mode,
            additional_sources=user_answer.get("additional_sources"),
        )
        return {
            **base_return,
            "user_answer": user_answer,
            "debug_info": debug_info,
            "answer": user_answer["text"],
            "answer_body": user_answer["answer"],
            "synthesized_insights_text": "",
            "summary": "",
            "common_risks_text": "",
            "differences_text": "",
            "key_metrics": {},
            "confidence": conf,
            "validation_notes": state.get("validation_notes", ""),
            "evaluation": None,
        }

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key or None,
        temperature=0.12 if route == "cautious" else 0.28,
    )

    tickers_mentioned = analysis.get("tickers_mentioned") or list({c.get("ticker") for c in context})

    if is_comparative:
        system = SystemMessage(content=_build_comparative_prompt(route, tickers_mentioned))
        evidence = _group_context_by_ticker(context)
        human = HumanMessage(
            content=(
                f"Comparative question: {state['message']}\n\n"
                f"Excerpts for synthesis ({len(context)}); cite by [n]:\n{evidence}"
            )
        )
    else:
        system = SystemMessage(content=_build_standard_prompt(route))
        human = HumanMessage(
            content=(
                f"Question: {state['message']}\n\n"
                f"Excerpts for synthesis ({len(context)}):\n{_format_context(context)}"
            )
        )

    if settings.debug_retrieval:
        logger.info(
            "LLM SYNTHESIS mode=%s excerpts=%d tickers=%s",
            response_mode,
            len(context),
            tickers_mentioned,
        )

    response = await llm.ainvoke([system, human])
    synthesis_raw = (response.content or "").strip()

    parsed = _parse_synthesis_sections(synthesis_raw, is_comparative)
    body_for_eval = parsed.get("summary") or parsed.get("answer_body") or synthesis_raw

    inference_hits = find_unmarked_inference_phrases(synthesis_raw)
    if inference_hits:
        synthesis_raw = INFERENCE_WORDS.sub("[removed-inference]", synthesis_raw)
        parsed = _parse_synthesis_sections(synthesis_raw, is_comparative)
        body_for_eval = parsed.get("summary") or parsed.get("answer_body") or synthesis_raw

    post = post_validate_answer(body_for_eval, context)
    penalty = post.get("confidence_penalty", 0.0)
    notes = state.get("validation_notes", "") + post.get("validation_notes_append", "")

    vague_hits = _check_vague_language(synthesis_raw)
    if vague_hits:
        notes += f" Vague phrasing: {', '.join(vague_hits[:3])}."
        penalty += 0.05

    inf_penalty, inf_note = inference_confidence_penalty(synthesis_raw)
    if inf_penalty:
        penalty += inf_penalty
        notes += f" {inf_note}."

    cov_penalty, cov_note = coverage_confidence_penalty(coverage_list)
    if cov_penalty:
        penalty += cov_penalty
        if cov_note:
            notes += f" {cov_note}."

    evaluation: AnswerEvaluation = evaluate_answer(body_for_eval, context, confidence)
    # Bracket citations are optional in user-facing format; penalize lightly only
    if evaluation.citation_coverage <= 0 and evaluation.groundedness_score < 0.35:
        penalty += 0.05
        notes += " Limited bracket citations in synthesis."

    adjusted_confidence = max(0.0, round(confidence - penalty, 3))

    refuse_synth = should_refuse_synthesis(
        context,
        route,
        evaluation.citation_coverage,
        evaluation.hallucination_risk,
        groundedness_score=evaluation.groundedness_score,
    )
    if refuse_synth or INSUFFICIENT_EVIDENCE.lower() in body_for_eval.lower():
        synthesized = INSUFFICIENT_EVIDENCE
        adjusted_confidence = min(adjusted_confidence, 0.25)
        notes += " Synthesis suppressed — insufficient cited evidence."
        parsed["summary"] = ""
        parsed["common_risks_text"] = ""
        parsed["differences_text"] = ""
        parsed["answer_body"] = INSUFFICIENT_EVIDENCE
        parsed["key_metrics"] = {}
    else:
        synthesized = synthesis_raw

    insufficient = (
        refuse_synth
        or INSUFFICIENT_EVIDENCE.lower() in (parsed.get("answer_body") or "").lower()
    )
    parsed["synthesized_raw"] = synthesis_raw
    user_answer = build_user_answer(
        parsed=parsed,
        context=context,
        confidence=adjusted_confidence,
        route=route,
        is_comparative=is_comparative,
        insufficient=insufficient,
    )
    debug_info = build_debug_info(
        retrieval_debug=state.get("retrieval_debug"),
        additional_sources=user_answer.get("additional_sources"),
        evaluation={
            "groundedness_score": evaluation.groundedness_score,
            "citation_coverage": evaluation.citation_coverage,
            "relevance_score": evaluation.relevance_score,
            "hallucination_risk": evaluation.hallucination_risk,
            "has_unmarked_inference": bool(find_unmarked_inference_phrases(synthesized)),
            "notes": evaluation.notes,
        },
        validation_notes=notes.strip(),
        route=route,
        confidence=adjusted_confidence,
        company_coverage=company_coverage_payload,
        context=context,
        response_mode=response_mode,
    )

    if settings.debug_retrieval:
        logger.info(
            "ANSWER EVAL groundedness=%.3f citations=%.3f hallucination=%.3f inference_hits=%s",
            evaluation.groundedness_score,
            evaluation.citation_coverage,
            evaluation.hallucination_risk,
            find_unmarked_inference_phrases(synthesized),
        )

    return {
        **base_return,
        "user_answer": user_answer,
        "debug_info": debug_info,
        "answer": user_answer["text"],
        "answer_body": user_answer["answer"],
        "synthesized_insights_text": synthesized,
        "summary": parsed.get("summary", ""),
        "common_risks_text": parsed.get("common_risks_text", ""),
        "differences_text": parsed.get("differences_text", ""),
        "key_metrics": parsed.get("key_metrics", {}),
        "confidence": adjusted_confidence,
        "validation_notes": notes.strip(),
        "evaluation": {
            "groundedness_score": evaluation.groundedness_score,
            "citation_coverage": evaluation.citation_coverage,
            "relevance_score": evaluation.relevance_score,
            "hallucination_risk": evaluation.hallucination_risk,
            "has_unmarked_inference": bool(find_unmarked_inference_phrases(synthesized)),
            "notes": evaluation.notes,
        },
    }
