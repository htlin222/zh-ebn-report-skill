"""Compose .qmd files, bibliography, and invoke Quarto to produce DOCX.

Layout under ``output/<run-id>/quarto/``::

    _quarto.yml
    report.qmd                # parent document
    sections/                 # one per SectionName
    references.bib
    ai-disclosure.qmd
    apa-7th-edition.csl       # copied from templates/
    appendix_*.qmd

The main ``render_to_docx`` function:
1. Writes all files
2. Runs ``quarto render report.qmd --to docx`` (a ``templates/reference.docx``
   style master is optional; if present it is copied next to the project and
   referenced via ``reference-doc:`` in ``_quarto.yml``)
3. Copies the DOCX to ``output/<run-id>/<topic>-DRAFT.docx``
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import AppConfig
from ..models import ReportType, RunState, Section
from ..spec import section_order
from ..state import run_dir
from .appendix import (
    casp_summary_qmd,
    prisma_flow_qmd,
    search_history_qmd,
    subagent_log_qmd,
)
from .bibliography import papers_to_bibtex

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[2].parent / "templates"


def _slugify(text: str) -> str:
    import re

    t = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE).strip("-")
    return t[:50] or "report"


def _ai_disclosure_block(state: RunState, *, pipeline_version: str, model_name: str) -> str:
    run_id = state.config.run_id
    return f"""
# AI 使用揭露段落

本報告於撰寫過程中使用生成式人工智慧工具輔助文獻檢索、文獻評讀、綜整與草稿撰寫。所使用工具為 Anthropic Claude（模型組合：Haiku 4.5 用於結構化檢核、Sonnet 4.6 用於大部分生成、Opus 4.7 用於跨篇綜整；透過 zh-ebn-report Pipeline v{pipeline_version} 呼叫，主要模型：{model_name}）。

AI 具體協助範圍包括：

1. 將臨床問題結構化為 PICO（subagent：PICO 建構員）
2. 產生六件套資料庫搜尋策略與 Boolean 檢索字串（subagent：搜尋策略師）
3. 依 CASP 工具產生各篇文獻評讀初稿（subagent：CASP 評讀員，多篇平行）
4. 跨篇綜整結果一致性與矛盾分析（subagent：綜整整合員）
5. 依台灣護理報告句型規範產生各章節草稿（subagent：分節撰寫員，多節平行）
6. 語氣與 APA 7 格式檢查（subagent：語氣守門員、APA 7 格式員）

所有 AI 產出內容皆經筆者於 9 個人類審核檢查點（CP1–CP9）逐節審閱與修訂。筆者對本文內容的真實性與準確性承擔全部責任。本報告之追溯性資料（包含各 checkpoint 決策紀錄、各 subagent 輸入輸出、搜尋歷程表）已一併整理於補充資料，run_id: {run_id}。

# Audit 責任聲明

本報告依台灣護理學會《生成式 AI 使用規範》與台灣實證護理學會《AI 輔助實證護理準則》之要求撰寫。

1. 生成式 AI（Anthropic Claude）依本研究方法所述範圍參與初稿生成；不列為作者。
2. 筆者已審閱並修訂 AI 產出之內容，對本文之真實性與準確性承擔全部責任。
3. 本報告附帶可追溯之 Pipeline 執行紀錄（run_id: {run_id}），可供審查單位調閱。
4. 引用之文獻均經 CrossRef 驗證 DOI 有效性，並由筆者複核 metadata 準確性。

報告人：______________________　　日期：______________
"""


def _quarto_yml(state: RunState, *, has_csl: bool, has_reference_doc: bool) -> str:
    parts = [
        "project:",
        "  type: default",
        "format:",
        "  docx:",
        "    toc: true",
        "    number-sections: true",
    ]
    if has_reference_doc:
        parts.append("    reference-doc: ../reference.docx")
    parts.append("bibliography: references.bib")
    if has_csl:
        parts.append("csl: apa-7th-edition.csl")
    parts.append("lang: zh-TW")
    return "\n".join(parts) + "\n"


def _compose_report_qmd(
    state: RunState, *, sections: list[Section], appendices: list[str]
) -> str:
    # 篇名優先採用疑問句版（模板審查偏好）
    if state.topic_verdict is not None:
        title = (
            state.topic_verdict.refined_topic_zh_question
            or state.topic_verdict.refined_topic_zh
        )
    else:
        title = "實證護理報告"

    lines = [
        "---",
        f'title: "{title}（DRAFT）"',
        'author: "（請於送審前填入）"',
        f'date: "{state.updated_at.date().isoformat()}"',
        "---",
        "",
    ]
    # Reorder sections to canonical template order
    kind = state.config.report_type.value  # "reading" | "case" | "twna_case" | "twna_project"
    canonical = [s.name for s in section_order(kind)]
    by_name: dict[str, Section] = {s.section_name: s for s in sections}
    ordered = [by_name[n] for n in canonical if n in by_name]
    # Any extras (case-specific sections not in spec) go at the end
    extras = [s for s in sections if s.section_name not in set(canonical)]

    for sec in ordered + extras:
        lines.append(f"# {sec.section_name}")
        lines.append("")
        lines.append(sec.content_zh)
        lines.append("")
    # Appendices appended as raw content (pre-ordered by caller)
    for app_text in appendices:
        lines.append("")
        lines.append(app_text)
    return "\n".join(lines) + "\n"


def render_to_docx(app_cfg: AppConfig, state: RunState) -> Path:
    rd = run_dir(app_cfg.pipeline, state.config.run_id)
    qd = rd / "quarto"
    qd.mkdir(exist_ok=True)

    # Bibliography
    if state.search_result is not None:
        (qd / "references.bib").write_text(
            papers_to_bibtex(state.search_result.papers), encoding="utf-8"
        )
    else:
        (qd / "references.bib").write_text("", encoding="utf-8")

    # CSL (optional)
    csl_src = _TEMPLATES_DIR / "apa-7th-edition.csl"
    has_csl = csl_src.exists()
    if has_csl:
        shutil.copy(csl_src, qd / "apa-7th-edition.csl")

    # Reference docx (optional but recommended)
    ref_src = _TEMPLATES_DIR / "reference.docx"
    has_reference_doc = ref_src.exists()
    if has_reference_doc:
        shutil.copy(ref_src, rd / "reference.docx")

    # _quarto.yml
    (qd / "_quarto.yml").write_text(
        _quarto_yml(state, has_csl=has_csl, has_reference_doc=has_reference_doc),
        encoding="utf-8",
    )

    # Appendices in canonical order: A 搜尋歷程 → B CASP → C PRISMA → D Subagent log
    appendix_parts: list[str] = []
    if state.search_result is not None:
        appendix_parts.append(search_history_qmd(state.search_result))
    if state.casp_results:
        appendix_parts.append(
            casp_summary_qmd(
                state.casp_results,
                state.search_result.papers if state.search_result else [],
            )
        )
    if state.search_result is not None:
        appendix_parts.append(prisma_flow_qmd(state.search_result))
    appendix_parts.append(subagent_log_qmd(state))
    appendix_parts.append(
        _ai_disclosure_block(
            state, pipeline_version="0.1.0", model_name=app_cfg.llm.sonnet_model
        )
    )

    # Report.qmd
    (qd / "report.qmd").write_text(
        _compose_report_qmd(state, sections=state.sections, appendices=appendix_parts),
        encoding="utf-8",
    )

    # Invoke quarto
    slug = _slugify(state.topic_verdict.refined_topic_zh if state.topic_verdict else "report")
    out_docx = qd / "report.docx"

    try:
        result = subprocess.run(
            ["quarto", "render", "report.qmd", "--to", "docx"],
            cwd=qd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            log.error("quarto stderr: %s", result.stderr)
            log.error("quarto stdout: %s", result.stdout)
    except FileNotFoundError:
        log.error(
            "quarto CLI not found. Install from https://quarto.org "
            "or render report.qmd manually."
        )
        # Fallback: return the .qmd path so the caller can still inspect.
        return qd / "report.qmd"

    if out_docx.exists():
        final_path = rd / f"{slug}-DRAFT.docx"
        shutil.copy(out_docx, final_path)
        return final_path
    return out_docx
