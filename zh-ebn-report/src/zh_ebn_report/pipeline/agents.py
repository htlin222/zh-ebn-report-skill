"""The 10 subagent functions.

Each subagent is an ``async`` function that takes structured inputs, calls the
Anthropic API with the appropriate prompt + cached knowledge base, and returns
the corresponding Pydantic result.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import ValidationError

from ..clients.anthropic import AnthropicClient
from ..config import PipelineConfig
from ..models import (
    ApaCheckResult,
    CaseDetailsDeidentified,
    CaseNarrative,
    CaspResult,
    CaspTool,
    InterventionAudit,
    PICO,
    PICOResult,
    Paper,
    SearchStrategy,
    Section,
    StudyDesign,
    SynthesisResult,
    TopicVerdict,
    VoiceCheckResult,
)
from .prompts import build_system

# ---------------------------------------------------------------------------
# Subagent 1: Topic Gatekeeper
# ---------------------------------------------------------------------------


async def run_topic_gatekeeper(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    user_topic_raw: str,
    ward_or_context: str,
    advancement_level: str,
    report_type: str,
) -> TopicVerdict:
    system = build_system(
        cfg,
        skill_refs=["topic-selection.md"],
        role_prompt_file="topic_gatekeeper.md",
    )
    user = (
        f"使用者題目原話：{user_topic_raw}\n"
        f"病房別/情境：{ward_or_context}\n"
        f"進階等級：{advancement_level}\n"
        f"報告類型：{report_type}\n\n"
        "請輸出 JSON。"
    )
    data = await llm.complete_json(
        tier="haiku",
        system_blocks=system,
        user_message=user,
        max_tokens=2048,
    )
    return TopicVerdict.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 2: PICO Builder
# ---------------------------------------------------------------------------


async def run_pico_builder(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    refined_topic_zh: str,
    refined_topic_en: str,
    clinical_scenario_zh: str,
) -> PICOResult:
    system = build_system(
        cfg,
        skill_refs=["pico-and-search.md"],
        role_prompt_file="pico_builder.md",
    )
    user = (
        f"Refined topic（中）：{refined_topic_zh}\n"
        f"Refined topic (en)：{refined_topic_en}\n"
        f"臨床情境：\n{clinical_scenario_zh}\n\n"
        "請輸出 JSON（對應 PICOResult）。"
    )
    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=2048,
    )
    return PICOResult.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 3: Search Strategist
# ---------------------------------------------------------------------------


async def run_search_strategist(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    pico: PICO,
    year_range_start: int,
    year_range_end: int,
) -> SearchStrategy:
    system = build_system(
        cfg,
        skill_refs=["pico-and-search.md"],
        role_prompt_file="search_strategist.md",
    )
    user = (
        f"PICO:\n{pico.model_dump_json(indent=2)}\n\n"
        f"年份範圍：{year_range_start}–{year_range_end}\n\n"
        "請輸出 JSON（對應 SearchStrategy）。"
    )
    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=3072,
    )
    # Inject year range in case LLM omits it
    data.setdefault("year_range_start", year_range_start)
    data.setdefault("year_range_end", year_range_end)
    return SearchStrategy.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 4: CASP Appraiser (parallel)
# ---------------------------------------------------------------------------


_CASP_PROMPT_FILES: dict[CaspTool, str] = {
    CaspTool.RCT: "casp_rct.md",
    CaspTool.SR: "casp_sr.md",
    CaspTool.COHORT: "casp_cohort.md",
    CaspTool.QUALITATIVE: "casp_qualitative.md",
}

_DESIGN_TO_TOOL: dict[StudyDesign, CaspTool] = {
    StudyDesign.RCT: CaspTool.RCT,
    StudyDesign.SR: CaspTool.SR,
    StudyDesign.MA: CaspTool.SR,
    StudyDesign.COHORT: CaspTool.COHORT,
    StudyDesign.CASE_CONTROL: CaspTool.COHORT,
    StudyDesign.QUALITATIVE: CaspTool.QUALITATIVE,
    StudyDesign.OTHER: CaspTool.RCT,  # conservative default
}


async def run_casp_appraiser(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    paper: Paper,
    pico: PICO,
) -> CaspResult:
    tool = _DESIGN_TO_TOOL[paper.study_design]
    prompt_file = _CASP_PROMPT_FILES[tool]
    system = build_system(
        cfg,
        skill_refs=["appraisal-tools.md", "phrasing-bank.md"],
        role_prompt_file=prompt_file,
    )
    user = (
        f"PICO 背景：\n{pico.model_dump_json(indent=2)}\n\n"
        f"論文 metadata：\n{paper.model_dump_json(indent=2, exclude={'abstract'})}\n\n"
        f"摘要：\n{paper.abstract or '(尚無摘要；請依 title + journal + design 做保守評估)'}\n\n"
        "請輸出 JSON（對應 CaspResult），paper_doi 請填入論文的 DOI。"
    )
    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=4096,
    )
    data.setdefault("paper_doi", paper.doi)
    return CaspResult.model_validate(data)


async def run_casp_parallel(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    papers: list[Paper],
    pico: PICO,
    max_concurrency: int,
) -> list[CaspResult]:
    sem = asyncio.Semaphore(max_concurrency)

    async def guarded(p: Paper) -> CaspResult:
        async with sem:
            return await run_casp_appraiser(llm=llm, cfg=cfg, paper=p, pico=pico)

    return await asyncio.gather(*(guarded(p) for p in papers))


# ---------------------------------------------------------------------------
# Subagent 5: Synthesiser (Opus)
# ---------------------------------------------------------------------------


async def run_synthesiser(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    pico: PICO,
    casp_results: list[CaspResult],
    papers: list[Paper],
) -> SynthesisResult:
    system = build_system(
        cfg,
        skill_refs=["appraisal-tools.md", "phrasing-bank.md"],
        role_prompt_file="synthesiser.md",
    )
    user = (
        f"PICO:\n{pico.model_dump_json(indent=2)}\n\n"
        f"Papers:\n"
        + "\n".join(p.model_dump_json(exclude={"abstract"}) for p in papers)
        + "\n\nCASP 評讀結果：\n"
        + "\n".join(c.model_dump_json() for c in casp_results)
        + "\n\n請輸出 JSON（對應 SynthesisResult）。"
    )
    data = await llm.complete_json(
        tier="opus",
        system_blocks=system,
        user_message=user,
        max_tokens=4096,
    )
    return SynthesisResult.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 6: Section Writer (parallel)
# ---------------------------------------------------------------------------


_SECTION_PROMPT_FILES: dict[str, str] = {
    # 讀書報告 8 章（摘要 + 7 主章）
    "摘要": "section_writer_摘要.md",
    "前言": "section_writer_前言.md",
    "主題設定": "section_writer_主題設定.md",
    "搜尋策略": "section_writer_搜尋策略.md",
    "評讀結果": "section_writer_評讀結果.md",
    "綜整": "section_writer_綜整.md",
    "應用建議": "section_writer_應用建議.md",
    "結論": "section_writer_結論.md",
    # 案例分析專用
    "方法": "section_writer_方法.md",
    "個案介紹": "section_writer_個案介紹.md",
    "應用與評值": "section_writer_應用.md",
}


async def run_section_writer(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    section_name: str,
    pico: PICO,
    search_strategy: SearchStrategy | None = None,
    casp_results: list[CaspResult] | None = None,
    papers: list[Paper] | None = None,
    synthesis: SynthesisResult | None = None,
    case_narrative: CaseNarrative | None = None,
    intervention_audit: InterventionAudit | None = None,
    advancement_level: str = "N2",
    other_sections: list[Section] | None = None,
    retry_feedback: str | None = None,
) -> Section:
    prompt_file = _SECTION_PROMPT_FILES[section_name]
    system = build_system(
        cfg,
        skill_refs=["phrasing-bank.md", "reading-report-template.md", "case-report-template.md"],
        role_prompt_file=prompt_file,
    )

    parts: list[str] = [f"PICO:\n{pico.model_dump_json(indent=2)}"]
    parts.append(f"進階等級：{advancement_level}")
    if search_strategy is not None:
        parts.append(f"SearchStrategy:\n{search_strategy.model_dump_json(indent=2)}")
    if papers is not None:
        parts.append(
            "Papers (citekeys + metadata):\n"
            + "\n".join(f"- [@{p.citekey()}] {p.authors[:2]} ({p.year}). {p.title}. {p.journal}." for p in papers)
        )
    if casp_results is not None:
        parts.append(
            "CASP results:\n"
            + "\n".join(c.model_dump_json(indent=2) for c in casp_results)
        )
    if synthesis is not None:
        parts.append(f"SynthesisResult:\n{synthesis.model_dump_json(indent=2)}")
    if case_narrative is not None:
        parts.append(f"CaseNarrative:\n{case_narrative.model_dump_json(indent=2)}")
    if intervention_audit is not None:
        parts.append(f"InterventionAudit:\n{intervention_audit.model_dump_json(indent=2)}")
    if other_sections:
        parts.append(
            "已完成節（僅供摘要撰寫員參考，不可抄襲）:\n"
            + "\n".join(
                f"## {s.section_name}\n{s.content_zh[:500]}..." for s in other_sections
            )
        )

    if retry_feedback:
        parts.append(retry_feedback)

    user = "\n\n".join(parts) + "\n\n請輸出 JSON（對應 Section）。"

    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=4096,
    )
    data.setdefault("section_name", section_name)
    return Section.model_validate(data)


async def run_section_writers_parallel(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    section_names: list[str],
    max_concurrency: int,
    **kwargs: Any,
) -> list[Section]:
    sem = asyncio.Semaphore(max_concurrency)

    async def guarded(name: str) -> Section:
        async with sem:
            return await run_section_writer(llm=llm, cfg=cfg, section_name=name, **kwargs)

    return await asyncio.gather(*(guarded(n) for n in section_names))


# ---------------------------------------------------------------------------
# Subagent 7: Voice Guard (Haiku)
# ---------------------------------------------------------------------------


async def run_voice_guard(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    full_draft_zh: str,
) -> VoiceCheckResult:
    system = build_system(
        cfg,
        skill_refs=["phrasing-bank.md"],
        role_prompt_file="voice_guard.md",
    )
    user = (
        "以下為完整報告草稿；請逐段掃描違規並輸出 JSON：\n\n"
        + full_draft_zh
    )
    data = await llm.complete_json(
        tier="haiku",
        system_blocks=system,
        user_message=user,
        max_tokens=3072,
    )
    return VoiceCheckResult.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 8: APA Formatter (Haiku)
# ---------------------------------------------------------------------------


async def run_apa_formatter(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    references_bib: str,
    papers: list[Paper],
    doi_validations_json: list[dict[str, Any]],
) -> ApaCheckResult:
    system = build_system(
        cfg,
        skill_refs=["phrasing-bank.md"],
        role_prompt_file="apa_formatter.md",
    )
    papers_json = "\n".join(p.model_dump_json(exclude={"abstract"}) for p in papers)
    doi_json = "\n".join(str(d) for d in doi_validations_json)
    user = (
        f"BibTeX:\n{references_bib}\n\n"
        f"Papers metadata:\n{papers_json}\n\n"
        f"DOI validation results (from CrossRef):\n{doi_json}\n\n"
        "請只對 format 做審查，並把 doi_validation_results 原樣帶到輸出。"
        " 輸出 JSON（對應 ApaCheckResult）。"
    )
    data = await llm.complete_json(
        tier="haiku",
        system_blocks=system,
        user_message=user,
        max_tokens=3072,
    )
    data.setdefault("doi_validation_results", doi_validations_json)
    try:
        return ApaCheckResult.model_validate(data)
    except ValidationError:
        # Fallback: ensure the three required keys exist.
        data.setdefault("format_issues", [])
        data.setdefault("apa_pass", False)
        return ApaCheckResult.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 9: Case Narrator (case only)
# ---------------------------------------------------------------------------


async def run_case_narrator(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    case_details: CaseDetailsDeidentified,
    pico: PICO,
) -> CaseNarrative:
    system = build_system(
        cfg,
        skill_refs=["case-report-template.md", "phrasing-bank.md"],
        role_prompt_file="case_narrator.md",
    )
    user = (
        f"PICO:\n{pico.model_dump_json(indent=2)}\n\n"
        f"已去識別化個案資料:\n{case_details.model_dump_json(indent=2)}\n\n"
        "請輸出 JSON（對應 CaseNarrative）。"
    )
    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=4096,
    )
    return CaseNarrative.model_validate(data)


# ---------------------------------------------------------------------------
# Subagent 10: Apply + Audit Auditor (case only)
# ---------------------------------------------------------------------------


async def run_apply_auditor(
    *,
    llm: AnthropicClient,
    cfg: PipelineConfig,
    synthesis: SynthesisResult,
    intervention_plan_zh: str,
    pre_observations: list[dict[str, Any]],
    post_observations: list[dict[str, Any]],
    deviations_from_plan: str | None,
) -> InterventionAudit:
    system = build_system(
        cfg,
        skill_refs=["case-report-template.md", "phrasing-bank.md"],
        role_prompt_file="apply_auditor.md",
    )
    import json

    user = (
        f"Synthesis:\n{synthesis.model_dump_json(indent=2)}\n\n"
        f"介入計畫：{intervention_plan_zh}\n\n"
        f"Pre-intervention 觀察：\n{json.dumps(pre_observations, ensure_ascii=False, indent=2)}\n\n"
        f"Post-intervention 觀察：\n{json.dumps(post_observations, ensure_ascii=False, indent=2)}\n\n"
        f"偏差：{deviations_from_plan or '(使用者未提供)'}\n\n"
        "請輸出 JSON（對應 InterventionAudit）。"
    )
    data = await llm.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=user,
        max_tokens=4096,
    )
    audit = InterventionAudit.model_validate(data)
    # M7: overwrite warning_too_perfect with deterministic OR of
    #    (LLM's self-reported flag) ∨ (derived-from-observations flag).
    # "完美無瑕" 情境：所有 post 觀察與 pre 完全相同（沒改變）或 100% 達標。
    audit.warning_too_perfect = audit.warning_too_perfect or _derive_too_perfect(
        pre_observations, post_observations
    )
    return audit


def _derive_too_perfect(
    pre: list[dict[str, Any]], post: list[dict[str, Any]]
) -> bool:
    """Return True when the Pre/Post comparison looks suspiciously clean.

    Triggers when all Post numerical outcomes are either identical to their
    Pre counterpart (no change at all, odd for a reported successful
    intervention) or all are at the extreme end of the scale (100% adherence,
    0% symptoms — rarely true in real nursing cases).
    """

    if not pre or not post:
        return False
    pre_vals = [_extract_numbers(o) for o in pre]
    post_vals = [_extract_numbers(o) for o in post]
    if not any(post_vals):
        return False

    pre_flat = [n for row in pre_vals for n in row]
    post_flat = [n for row in post_vals for n in row]
    if pre_flat and post_flat and pre_flat == post_flat:
        return True
    # All Post values at 0 or 100 — often a fabricated "everything resolved"
    if post_flat and all(v in (0, 100) for v in post_flat):
        return True
    return False


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_numbers(observation: dict[str, Any]) -> list[float]:
    """Extract any numbers from observation dict values for variance check."""

    out: list[float] = []
    for val in observation.values():
        if isinstance(val, int | float):
            out.append(float(val))
            continue
        if isinstance(val, str):
            for m in _NUM_RE.finditer(val):
                try:
                    out.append(float(m.group()))
                except ValueError:
                    pass
    return out
