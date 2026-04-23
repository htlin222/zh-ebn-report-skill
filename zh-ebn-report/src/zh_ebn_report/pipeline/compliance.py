"""Programmatic template-compliance checker.

Runs deterministic rules against the draft before CP7. Prompts can fail or lie
about word counts; this module is the boss. All rules read constants from
``zh_ebn_report.spec`` so the template is the single source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..models import (
    ComplianceIssueRecord,
    ComplianceReportRecord,
    OxfordLevel,
    Paper,
    RunState,
    Section,
    TopicVerdict,
)
from .evidence_guard import _LEVEL_RANK, _ceiling_for
from ..spec import (
    MIN_HIGH_LEVEL_EVIDENCE,
    MIN_REFERENCES,
    ReportKind,
    SectionSpec,
    min_references_for,
    page_limit_for,
    section_order,
    total_body_cjk_limit_for,
)

Severity = Literal["error", "warning"]


@dataclass
class ComplianceIssue:
    """One deterministic violation of the template spec."""

    section: str
    rule: str
    detail: str
    severity: Severity = "error"

    def format(self) -> str:
        tag = "❌" if self.severity == "error" else "⚠"
        return f"{tag} [{self.section}] {self.rule}: {self.detail}"


@dataclass
class ComplianceReport:
    issues: list[ComplianceIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary_zh(self) -> str:
        if not self.issues:
            return "✓ 全部通過模板規範"
        lines = [f"共 {len(self.errors)} 項錯誤、{len(self.warnings)} 項警示："]
        lines.extend(i.format() for i in self.issues)
        return "\n".join(lines)

    def issues_for_section(self, section: str) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.section == section]

    def to_record(self, *, retries_used: int = 0) -> ComplianceReportRecord:
        return ComplianceReportRecord(
            passed=self.passed,
            issues=[
                ComplianceIssueRecord(
                    section=i.section,
                    rule=i.rule,
                    detail=i.detail,
                    severity=i.severity,
                )
                for i in self.issues
            ],
            retries_used=retries_used,
        )


# ---------------------------------------------------------------------------
# CJK-character counting (matches human intuition for 中文字數)
# ---------------------------------------------------------------------------
_CJK_RE = re.compile(r"[一-鿿]")
_CITE_RE = re.compile(r"\[@[^\]]+\]")
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def count_cjk(text: str) -> int:
    """Count CJK ideographs only — excludes punctuation, English, numbers."""

    return len(_CJK_RE.findall(text))


def count_cjk_excluding_tables_and_cites(text: str) -> int:
    """Body-only CJK count: strip markdown tables and citation placeholders.

    Several sections have a rule like "字數不含表格本身"; this helper keeps the
    counter honest about what is actually prose.
    """

    stripped = _MARKDOWN_TABLE_RE.sub("", text)
    stripped = _CITE_RE.sub("", stripped)
    return count_cjk(stripped)


# ---------------------------------------------------------------------------
# Per-section rules
# ---------------------------------------------------------------------------
def _check_word_count(section: Section, spec: SectionSpec) -> list[ComplianceIssue]:
    count = count_cjk_excluding_tables_and_cites(section.content_zh)
    if spec.word_range.contains(count):
        return []
    return [
        ComplianceIssue(
            section=section.section_name,
            rule="word_count",
            detail=(
                f"實際 {count} 字，應落在 {spec.word_range.describe()}"
                "（自評 word_count_estimate 不算數，以 CJK 字數為準）"
            ),
        )
    ]


def _check_citation_coverage(
    section: Section, spec: SectionSpec, papers: list[Paper]
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    placeholders = set(section.citation_placeholders)
    if spec.must_cite_at_least and len(placeholders) < spec.must_cite_at_least:
        issues.append(
            ComplianceIssue(
                section=section.section_name,
                rule="citation_min",
                detail=(
                    f"僅 {len(placeholders)} 處引文，模板要求至少 "
                    f"{spec.must_cite_at_least} 處"
                ),
            )
        )
    if spec.must_cite_all_papers and papers:
        citekeys_expected = {f"@{p.citekey()}" for p in papers}
        missing = citekeys_expected - placeholders
        if missing:
            issues.append(
                ComplianceIssue(
                    section=section.section_name,
                    rule="citation_coverage",
                    detail=(
                        f"未引用 {len(missing)} 篇文獻："
                        + ", ".join(sorted(missing))
                    ),
                )
            )
    # Banned generic tokens — Paper 1 / Paper 2 instead of author-year
    if spec.name == "評讀結果":
        body = section.content_zh
        banned = re.findall(r"Paper\s*[1-9]", body, flags=re.IGNORECASE)
        if banned:
            issues.append(
                ComplianceIssue(
                    section=section.section_name,
                    rule="author_year_reference",
                    detail=(
                        f"發現 {len(banned)} 處使用 Paper N 代號，"
                        "須改為作者姓氏＋年代"
                    ),
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Top-level checks
# ---------------------------------------------------------------------------
def check_sections(state: RunState, *, kind: ReportKind) -> ComplianceReport:
    """Run all deterministic rules on the assembled sections + topic + refs."""

    report = ComplianceReport()
    order = section_order(kind)
    sections_by_name = {s.section_name: s for s in state.sections}

    # 1. Required-section presence
    for spec in order:
        if spec.required and spec.name not in sections_by_name:
            report.issues.append(
                ComplianceIssue(
                    section=spec.name,
                    rule="missing_section",
                    detail="模板要求此章節但草稿未產出",
                )
            )

    # 2. Per-section rules
    papers = state.search_result.papers if state.search_result else []
    for spec in order:
        sec = sections_by_name.get(spec.name)
        if sec is None:
            continue
        report.issues.extend(_check_word_count(sec, spec))
        report.issues.extend(_check_citation_coverage(sec, spec, papers))

    # 3. Title must have a question form (EBR 類別；TWNA 傳統個案報告題目多為敘述句，不強制)
    if kind in ("reading", "case"):
        report.issues.extend(_check_title(state.topic_verdict))

    # 4. References (kind-specific minimum)
    report.issues.extend(_check_references(papers, kind=kind))

    # 4b. Defense-in-depth: evidence level must not exceed OCEBM ceiling
    # for the study design (guardrail should have already fixed this at
    # APPRAISE phase; this catches regressions / manual state edits).
    report.issues.extend(_check_evidence_level_vs_design(papers))

    # 4c. DOI must be validated by CrossRef (no fabricated citations).
    report.issues.extend(_check_doi_validation(papers))

    # 4d. 摘要 must not contain citation placeholders.
    report.issues.extend(_check_abstract_no_citations(sections_by_name))

    # 5. Total-body length (hard page cap for TWNA submissions)
    report.issues.extend(_check_total_length(state, kind=kind))

    # 6. Anonymity (TWNA hard rule: 不得出現機構名、人員姓名、致謝對象)
    if kind in ("twna_case", "twna_project"):
        report.issues.extend(_check_anonymity(state))

    return report


def _check_title(verdict: TopicVerdict | None) -> list[ComplianceIssue]:
    if verdict is None:
        return [
            ComplianceIssue(
                section="篇名",
                rule="missing_title",
                detail="尚無 topic_verdict，無法驗證篇名",
            )
        ]
    q = getattr(verdict, "refined_topic_zh_question", "") or ""
    markers = ("？", "?", "是否", "能否", "可否")
    if not any(m in q for m in markers):
        return [
            ComplianceIssue(
                section="篇名",
                rule="question_form",
                detail=(
                    f"refined_topic_zh_question={q!r} 非疑問句；"
                    "模板建議用疑問句式呈現 PICO"
                ),
            )
        ]
    return []


_HIGH_LEVELS = {OxfordLevel.I, OxfordLevel.II}


def _check_doi_validation(papers: list[Paper]) -> list[ComplianceIssue]:
    """S4: any paper with unresolved DOI (or CrossRef metadata mismatch) is an
    error. The searcher sets ``doi_validated`` via CrossRef; a False here
    means either the DOI does not resolve or CrossRef returned different
    metadata from what the LLM produced — both are signals of fabrication or
    stale citations.
    """

    issues: list[ComplianceIssue] = []
    for p in papers:
        if not p.doi_validated:
            issues.append(
                ComplianceIssue(
                    section="參考文獻",
                    rule="doi_unvalidated",
                    detail=(
                        f"[{p.doi}] DOI 未通過 CrossRef 驗證；"
                        "_base.md 硬性規定禁止編造 DOI"
                    ),
                )
            )
            continue
        if p.doi_metadata_matches is False:
            issues.append(
                ComplianceIssue(
                    section="參考文獻",
                    rule="doi_metadata_mismatch",
                    detail=(
                        f"[{p.doi}] CrossRef metadata 與 paper 不一致（"
                        f"title='{p.title[:40]}…'）；可能引文錯植"
                    ),
                )
            )
    return issues


def _check_abstract_no_citations(
    sections_by_name: dict[str, Section],
) -> list[ComplianceIssue]:
    """S5: 摘要 must not contain citation placeholders.

    section_writer_摘要.md:35 明文「禁止任何引文佔位」。LLM 可能偷加，
    compliance 這裡強制為零。
    """

    sec = sections_by_name.get("摘要")
    if sec is None or not sec.citation_placeholders:
        return []
    return [
        ComplianceIssue(
            section="摘要",
            rule="abstract_no_citations",
            detail=(
                f"摘要含 {len(sec.citation_placeholders)} 個引文佔位："
                + ", ".join(sec.citation_placeholders[:3])
                + "；模板規定摘要不得引用文獻"
            ),
        )
    ]


def _check_evidence_level_vs_design(
    papers: list[Paper],
) -> list[ComplianceIssue]:
    """Defense-in-depth: flag any Paper whose Oxford level exceeds the OCEBM
    ceiling for its study design.

    ``evidence_guard.enforce_evidence_levels`` normally runs at the end of the
    APPRAISE phase and writes corrected values back. This check catches the
    case where someone edits the state file by hand, or a future code path
    forgets to call the guardrail. Errors, not warnings — if you see these in
    a finished run, something upstream is wrong.
    """

    issues: list[ComplianceIssue] = []
    for p in papers:
        ceiling, reason = _ceiling_for(p)
        if _LEVEL_RANK[p.oxford_level] < _LEVEL_RANK[ceiling]:
            issues.append(
                ComplianceIssue(
                    section="參考文獻",
                    rule="evidence_level_vs_design",
                    detail=(
                        f"[{p.doi}] {p.study_design.value} 標為 "
                        f"Level {p.oxford_level.value}；OCEBM 2011 最高 "
                        f"Level {ceiling.value}（{reason}）"
                    ),
                )
            )
    return issues


def _check_references(
    papers: list[Paper], *, kind: ReportKind = "reading"
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    min_required = min_references_for(kind)
    if len(papers) < min_required:
        issues.append(
            ComplianceIssue(
                section="參考文獻",
                rule="min_count",
                detail=(
                    f"納入文獻僅 {len(papers)} 篇，{kind} 模板要求至少 "
                    f"{min_required} 篇"
                ),
            )
        )
    # High-level evidence requirement applies to EBR types where evidence grading
    # is central; TWNA traditional case/project reports use references more
    # broadly (practice guidelines, textbook-style) and do not require Oxford
    # I–II specifically.
    if kind in ("reading", "case"):
        high_count = sum(1 for p in papers if p.oxford_level in _HIGH_LEVELS)
        if high_count < MIN_HIGH_LEVEL_EVIDENCE:
            issues.append(
                ComplianceIssue(
                    section="參考文獻",
                    rule="min_high_level_evidence",
                    detail=(
                        f"高證據等級（Oxford I–II）僅 {high_count} 篇，"
                        f"模板要求至少 {MIN_HIGH_LEVEL_EVIDENCE} 篇"
                    ),
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Total length + anonymity (TWNA hard rules)
# ---------------------------------------------------------------------------
def _check_total_length(
    state: RunState, *, kind: ReportKind
) -> list[ComplianceIssue]:
    """Enforce TWNA's hard page cap (16 or 20 pages) by total body CJK count.

    TWNA細則: 非表格每頁 30×20 = 600 CJK chars. So total body ≤ pages × 600.
    Excludes 摘要 (separate field with its own cap) and tables/citations.
    """

    limit = total_body_cjk_limit_for(kind)
    pages = page_limit_for(kind)
    total = 0
    for sec in state.sections:
        if sec.section_name == "摘要":
            continue
        total += count_cjk_excluding_tables_and_cites(sec.content_zh)
    if total > limit:
        return [
            ComplianceIssue(
                section="全文",
                rule="total_length",
                detail=(
                    f"正文合計 {total} 字（不含摘要、表格、引文），"
                    f"超過 {kind} 模板 {pages} 頁 × 每頁 600 字 = {limit} 字上限"
                ),
            )
        ]
    return []


# TWNA 硬禁止出現在內文的字串 pattern。匿名檢查以 regex 簡易偵測；不保證
# 100% 準確，但能攔下明顯的違規（機構名、致謝、常見署名格式）。
_INSTITUTION_PATTERNS = (
    r"醫院",
    r"醫學中心",
    r"診所",
    r"聯醫",
    r"部立",
    r"附設",
    r"大學附設",
)

_ACKNOWLEDGEMENT_PATTERNS = (
    r"致謝",
    r"感謝",
    r"Acknowledge",
    r"acknowledge",
)


def _check_anonymity(state: RunState) -> list[ComplianceIssue]:
    """Flag institution names, acknowledgement sections and obvious Chinese
    personal names in TWNA-targeted drafts.

    TWNA細則明文：不得出現所屬機構名稱、相關人員姓名及致謝對象（不符者不予通過）。
    """

    issues: list[ComplianceIssue] = []
    inst_re = re.compile("|".join(_INSTITUTION_PATTERNS))
    ack_re = re.compile("|".join(_ACKNOWLEDGEMENT_PATTERNS))
    # Naive Chinese-name heuristic: 2–3 CJK chars following a title like
    # 張醫師 / 李護理長 / 王先生 — catches obvious slips without too many
    # false positives. Authors of cited papers in references are NOT scanned
    # (references section is added by the renderer, not by section writers).
    name_re = re.compile(r"[一-鿿]{1,2}(?:醫師|護理長|主任|組長|先生|小姐|女士|教授)")

    for sec in state.sections:
        text = sec.content_zh
        for m in inst_re.finditer(text):
            # Skip generic "本院" / "醫院口腔" 等泛指：require surrounding context
            # of 2+ CJK chars before the match (likely proper noun like "台大醫院")
            start = m.start()
            before = text[max(0, start - 3) : start]
            if before and len([c for c in before if "一" <= c <= "鿿"]) >= 2:
                issues.append(
                    ComplianceIssue(
                        section=sec.section_name,
                        rule="anonymity_institution",
                        detail=(
                            f"疑似出現機構名稱：'…{before}{m.group()}…'；"
                            "TWNA 規範不得出現所屬機構名"
                        ),
                    )
                )
                break  # one finding per section is enough
        if ack_re.search(text):
            issues.append(
                ComplianceIssue(
                    section=sec.section_name,
                    rule="anonymity_acknowledgement",
                    detail="偵測到致謝/感謝字樣；TWNA 規範不得出現致謝對象",
                )
            )
        for m in name_re.finditer(text):
            issues.append(
                ComplianceIssue(
                    section=sec.section_name,
                    rule="anonymity_personal_name",
                    detail=(
                        f"疑似出現人員姓名：'{m.group()}'；"
                        "TWNA 規範不得出現相關人員姓名"
                    ),
                    severity="warning",  # heuristic, may have false positives
                )
            )
            break
    return issues


# ---------------------------------------------------------------------------
# Prompt-feedback helper
# ---------------------------------------------------------------------------
def retry_feedback_for_section(
    section_name: str, report: ComplianceReport
) -> str | None:
    """Convert section-specific issues into a directive for a retry pass.

    Returned string is appended to the section writer's user prompt on retry;
    ``None`` if there is nothing to fix.
    """

    issues = report.issues_for_section(section_name)
    if not issues:
        return None
    lines = ["【上一次輸出未通過程式化驗證，請針對以下問題重寫】"]
    for i in issues:
        lines.append(f"- {i.rule}: {i.detail}")
    lines.append("請嚴格滿足所有規則後再次輸出 JSON。")
    return "\n".join(lines)
