"""Pydantic models for the zh-ebn-report pipeline.

These models define the structured contracts between every subagent, the
orchestrator, and the Quarto renderer. Every contract in
``zh-ebn-report/references/subagent-roles.md`` has a counterpart here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReportType(str, Enum):
    """Report type ↔ submit target.

    - ``EBR_READING`` / ``reading``: 實證讀書報告（N1/N2，醫院自訂格式，8 章，
      含 5A）。
    - ``EBR_CASE`` / ``case``: 實證案例分析（N3，TEBNA 風格，7 章，含 5A +
      個案應用）。
    - ``TWNA_CASE``: 台灣護理學會個案報告（N2/N3 送審，9 章，≤16 頁，摘要
      ≤500 字；傳統護理過程架構）。
    - ``TWNA_PROJECT``: 台灣護理學會護理專案（N4 送審，10 章，≤20 頁，摘要
      ≤300 字）。

    ``READING`` / ``CASE`` 為 ``EBR_READING`` / ``EBR_CASE`` 的舊別名，保留
    向後相容。新程式碼請用有意義的長名。
    """

    EBR_READING = "reading"
    EBR_CASE = "case"
    TWNA_CASE = "twna_case"
    TWNA_PROJECT = "twna_project"

    # Backwards-compat aliases (same enum member, different name)
    READING = "reading"
    CASE = "case"


class AdvancementLevel(str, Enum):
    N1 = "N1"
    N2 = "N2"
    N3 = "N3"
    N4 = "N4"


class QuestionType(str, Enum):
    THERAPY = "Therapy"
    HARM = "Harm"
    DIAGNOSIS = "Diagnosis"
    PROGNOSIS = "Prognosis"


class StudyDesign(str, Enum):
    RCT = "RCT"
    SR = "SR"
    MA = "MA"
    COHORT = "Cohort"
    CASE_CONTROL = "Case-Control"
    QUALITATIVE = "Qualitative"
    OTHER = "Other"


class OxfordLevel(str, Enum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"


class SourceDB(str, Enum):
    PUBMED = "PubMed"
    SCOPUS = "Scopus"
    EMBASE = "Embase"
    COCHRANE = "Cochrane"
    CINAHL = "CINAHL"
    AIRITI = "Airiti"
    TAIWAN_THESIS = "TaiwanThesis"
    OTHER = "Other"


class CaspTool(str, Enum):
    RCT = "CASP-RCT"
    SR = "CASP-SR"
    COHORT = "CASP-Cohort"
    QUALITATIVE = "CASP-Qualitative"


class CheckpointId(str, Enum):
    CP1 = "CP1"
    CP2 = "CP2"
    CP3 = "CP3"
    CP4 = "CP4"
    CP5 = "CP5"
    CP6 = "CP6"
    CP7 = "CP7"
    CP8 = "CP8"
    CP9 = "CP9"


class PipelinePhase(str, Enum):
    INIT = "init"
    TOPIC = "topic"
    PICO = "pico"
    SEARCH = "search"
    APPRAISE = "appraise"
    SYNTHESISE = "synthesise"
    WRITE = "write"
    CHECK = "check"
    RENDER = "render"


# ---------------------------------------------------------------------------
# Topic gatekeeper (Subagent 1)
# ---------------------------------------------------------------------------


class TopicVerdict(BaseModel):
    verdict: Literal["feasible", "needs_refinement", "not_recommended"]
    refined_topic_zh: str
    refined_topic_zh_question: str
    """疑問句式篇名（模板建議格式），例：「…是否能…？」。Renderer 優先採用此欄位作為 DOCX 標題。"""
    refined_topic_en: str
    landmine_flags: list[str] = Field(default_factory=list)
    rationale_zh: str
    alternative_topics_zh: list[str] = Field(default_factory=list)

    @field_validator("refined_topic_zh_question")
    @classmethod
    def must_be_question_form(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("refined_topic_zh_question 不可為空")
        markers = ("？", "?", "是否", "能否", "可否")
        if not any(m in stripped for m in markers):
            raise ValueError(
                "refined_topic_zh_question 須為疑問句（含『？』『是否』『能否』或『可否』）"
            )
        return stripped


# ---------------------------------------------------------------------------
# PICO (Subagent 2)
# ---------------------------------------------------------------------------


class PICO(BaseModel):
    population_zh: str
    population_en: str
    intervention_zh: str
    intervention_en: str
    comparison_zh: str
    comparison_en: str
    outcome_zh: str
    outcome_en: str
    question_type: QuestionType

    @field_validator("comparison_zh", "comparison_en")
    @classmethod
    def comparison_not_none(cls, v: str) -> str:
        lowered = v.lower().strip()
        banned = {"無介入", "不做", "none", "no intervention", "nothing", "無"}
        if lowered in banned:
            raise ValueError(
                "Comparison 不得為『無介入』；請改為 routine care 或替代介入"
            )
        return v


class PicotExtension(BaseModel):
    time: str | None = None
    study_design: str | None = None


class PICOResult(BaseModel):
    pico: PICO
    picot_extension: PicotExtension = Field(default_factory=PicotExtension)
    validation_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Search strategy (Subagent 3)
# ---------------------------------------------------------------------------


class SixPieceStrategy(BaseModel):
    primary_terms: list[str]
    synonyms: list[str]
    mesh_terms: list[str]
    cinahl_headings: list[str]
    boolean_query_pubmed: str
    boolean_query_cochrane: str
    boolean_query_cinahl: str
    field_codes_used: dict[str, str]

    @field_validator("primary_terms")
    @classmethod
    def primary_terms_count(cls, v: list[str]) -> list[str]:
        if not 3 <= len(v) <= 5:
            raise ValueError("primary_terms 必須為 3–5 個")
        return v

    @field_validator("synonyms")
    @classmethod
    def synonyms_count(cls, v: list[str]) -> list[str]:
        if not 5 <= len(v) <= 10:
            raise ValueError("synonyms 必須為 5–10 個")
        return v

    @field_validator("mesh_terms")
    @classmethod
    def mesh_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("至少需一個 PubMed MeSH 詞")
        return v

    @field_validator("boolean_query_pubmed", "boolean_query_cochrane", "boolean_query_cinahl")
    @classmethod
    def no_oversized_or_cluster(cls, v: str) -> str:
        # search_strategist.md:44 — 禁止 > 3 個 OR 連接的自由字群（> 4 terms）。
        # Count OR operators inside each parenthesized group; flag if any
        # single group has more than 3 OR (i.e. 5+ terms).
        import re as _re

        for group_match in _re.finditer(r"\(([^()]+)\)", v):
            inner = group_match.group(1)
            or_count = len(_re.findall(r"\b[Oo][Rr]\b", inner))
            if or_count > 3:
                raise ValueError(
                    f"Boolean 查詢出現 {or_count + 1} 個 OR-連接自由字群"
                    f"（{group_match.group()[:50]}…）；search_strategist.md "
                    "規定單一群最多 4 terms (3 OR)，以免命中超過 5000 篇"
                )
        return v


class TuningPlan(BaseModel):
    if_too_narrow: list[str]
    if_too_wide: list[str]


class PredictedHits(BaseModel):
    pubmed: int | None = None
    scopus: int | None = None
    embase: int | None = None
    cochrane: Literal["manual_import"] | int = "manual_import"
    cinahl: Literal["manual_import"] | int = "manual_import"
    airiti: Literal["manual_import"] | int = "manual_import"


class SearchStrategy(BaseModel):
    six_piece_strategy: SixPieceStrategy
    predicted_hits_per_db: PredictedHits
    tuning_plan: TuningPlan
    year_range_start: int
    year_range_end: int


# ---------------------------------------------------------------------------
# Paper (search results + validation)
# ---------------------------------------------------------------------------


class Paper(BaseModel):
    title: str
    authors: list[str]
    year: int
    journal: str
    doi: str
    doi_validated: bool = False
    doi_metadata_matches: bool | None = None
    study_design: StudyDesign
    oxford_level: OxfordLevel
    source_db: SourceDB
    abstract: str | None = None

    def citekey(self) -> str:
        """Generate a BibTeX cite key: first-author-surname + year + first-title-word.

        PubMed delivers authors as "Surname Initials" (e.g., "Kumar R"), so the
        surname is the *first* whitespace-separated token — not the last. For
        "Surname, Initials" comma-form we also take the leading token.
        """

        if not self.authors:
            surname = "Anon"
        else:
            first_author = self.authors[0].strip()
            # Strip trailing comma if present ("Kumar, R" → ["Kumar,", "R"])
            head = first_author.split()[0] if first_author else "Anon"
            surname = head.rstrip(",")
        first_word = (self.title.split(" ", 1)[0] if self.title else "paper").lower()
        safe_word = "".join(c for c in first_word if c.isalnum())[:10]
        return f"{surname.lower()}{self.year}{safe_word}"


class SearchHistoryRow(BaseModel):
    """One row of the 搜尋歷程表."""

    keywords: str
    database: SourceDB
    field_limit: str
    initial_hits: int
    deduplicated_hits: int
    inclusion_criteria: str
    exclusion_criteria: str
    included_count: int
    note: str


class SearchResult(BaseModel):
    strategy: SearchStrategy
    history: list[SearchHistoryRow]
    papers: list[Paper]


# ---------------------------------------------------------------------------
# CASP appraisal (Subagent 4)
# ---------------------------------------------------------------------------


class CaspItem(BaseModel):
    q_no: int
    question_zh: str
    answer: Literal["Yes", "No", "Cannot_tell"]
    rationale_zh: str

    @field_validator("rationale_zh")
    @classmethod
    def no_vague_words(cls, v: str) -> str:
        vague = ["尚可", "大致", "似乎", "應該是", "可能有"]
        hits = [w for w in vague if w in v]
        if hits:
            raise ValueError(f"rationale 含模糊詞：{hits}")
        return v


class CaspWarnings(BaseModel):
    sample_size_below_30: bool = False
    p_value_insignificant_but_strong_claim: bool = False
    single_site_study: bool = False
    conflict_of_interest_declared: bool = False


class CaspResult(BaseModel):
    paper_doi: str
    tool_used: CaspTool
    checklist_items: list[CaspItem]
    validity_zh: str
    importance_zh: str
    applicability_zh: str
    oxford_level_2011: OxfordLevel
    warnings: CaspWarnings = Field(default_factory=CaspWarnings)


# ---------------------------------------------------------------------------
# Synthesis (Subagent 5)
# ---------------------------------------------------------------------------


class Contradiction(BaseModel):
    topic: str
    paper_a: str  # DOI
    paper_b: str  # DOI
    disagreement: str
    likely_reason: str


class SynthesisResult(BaseModel):
    consistency_analysis_zh: str
    contradictions_zh: list[Contradiction] = Field(default_factory=list)
    overall_evidence_strength: Literal["strong", "moderate", "limited", "conflicting"]
    clinical_feasibility_taiwan_zh: str
    recommended_intervention_summary_zh: str
    limitations_zh: list[str]

    @field_validator("limitations_zh")
    @classmethod
    def limitations_min_three(cls, v: list[str]) -> list[str]:
        # synthesiser.md:37 — limitations_zh 必須至少 3 條；LLM 有時只給 1–2。
        non_empty = [item for item in v if item.strip()]
        if len(non_empty) < 3:
            raise ValueError(
                f"limitations_zh 僅 {len(non_empty)} 條；synthesiser.md 要求至少 3 條"
                "（文獻品質、樣本代表性、與台灣情境差異）"
            )
        return v


# ---------------------------------------------------------------------------
# Section writing (Subagent 6)
# ---------------------------------------------------------------------------


SectionName = Literal[
    # EBR 讀書報告 8 章（摘要 + 7 主章；參考文獻由 Quarto/CSL 產出）
    "摘要",
    "前言",
    "主題設定",
    "搜尋策略",
    "評讀結果",
    "綜整",
    "應用建議",
    "結論",
    # EBR 案例分析專用（TEBNA 5A 風格）
    "方法",
    "個案介紹",
    "應用與評值",
    "討論",
    # TWNA 個案報告（傳統護理過程 9 章，送 N2/N3）
    "文獻查證",
    "護理評估",
    "問題確立",
    "護理措施",
    "結果評值",
    "討論與結論",
    # TWNA 護理專案（N4，額外 3 章）
    "現況分析",
    "問題及導因確立",
    "專案目的",
    "解決辦法及執行過程",
]


class SectionSelfCheck(BaseModel):
    uses_bi_jia_not_wo: bool
    uses_ge_an_not_bing_ren: bool
    formal_register_only: bool
    cites_phrasing_bank: bool


class Section(BaseModel):
    section_name: SectionName
    content_zh: str
    word_count_estimate: int
    citation_placeholders: list[str] = Field(default_factory=list)
    self_check: SectionSelfCheck


# ---------------------------------------------------------------------------
# Voice guard (Subagent 7)
# ---------------------------------------------------------------------------


class VoiceViolation(BaseModel):
    category: Literal[
        "第一人稱誤用",
        "病患稱謂錯誤",
        "口語化",
        "動詞非書面語",
        "含糊語言",
    ]
    location_excerpt: str
    suggested_rewrite: str
    severity: Literal["high", "medium", "low"]


class VoiceCheckResult(BaseModel):
    violations: list[VoiceViolation]
    total_violations: int
    pass_threshold_met: bool


# ---------------------------------------------------------------------------
# APA 7 formatter (Subagent 8)
# ---------------------------------------------------------------------------


class ApaIssue(BaseModel):
    citekey: str
    issue: str
    suggested_fix: str


class DoiValidation(BaseModel):
    citekey: str
    doi: str
    doi_resolvable: bool
    metadata_matches_paper: bool
    mismatch_details: str | None = None


class ApaCheckResult(BaseModel):
    format_issues: list[ApaIssue]
    doi_validation_results: list[DoiValidation]
    apa_pass: bool


# ---------------------------------------------------------------------------
# Case report specific (Subagents 9, 10)
# ---------------------------------------------------------------------------


class CaseDemographics(BaseModel):
    age_group: str  # 例如 "50–60 歲"
    sex: Literal["M", "F", "Other"]


class TimelineEvent(BaseModel):
    timestamp: str  # 可用相對時間 "入院第一日"
    event: str
    observations: str


class CaseDetailsDeidentified(BaseModel):
    demographics: CaseDemographics
    chief_complaint_zh: str
    present_illness_zh: str
    past_medical_history: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications_on_admission: list[str] = Field(default_factory=list)
    examinations: list[dict[str, str]] = Field(default_factory=list)
    nursing_assessment: dict[str, str] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)


class DirectQuote(BaseModel):
    speaker: Literal["個案", "家屬", "護理師", "醫師"]
    quote_zh: str


class CaseNarrative(BaseModel):
    case_introduction_section_zh: str
    diagnostic_reasoning_section_zh: str
    deid_check_passed: bool
    direct_quotes: list[DirectQuote]

    @field_validator("direct_quotes")
    @classmethod
    def requires_case_and_family_quote(cls, v: list[DirectQuote]) -> list[DirectQuote]:
        # section_writer_個案介紹.md:33-34 — 必須有 ≥1 個案原話 + ≥1 家屬原話。
        speakers = {q.speaker for q in v}
        missing = {"個案", "家屬"} - speakers
        if missing:
            raise ValueError(
                f"direct_quotes 缺少 {missing} 原話；"
                "個案介紹必須同時有個案原話與家屬原話各 ≥ 1"
            )
        return v


class Observation(BaseModel):
    timestamp: str
    subjective: str
    objective_scale: str
    objective_value: str


class InterventionAudit(BaseModel):
    apply_section_zh: str
    audit_section_zh: str
    time_stamped_table: list[dict[str, str]]
    deviation_explanation_zh: str | None
    warning_too_perfect: bool

    @field_validator("time_stamped_table")
    @classmethod
    def requires_min_two_rows_with_keys(
        cls, v: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        # section_writer_應用.md:38-39 — ≥2 時間戳記觀察 + 客觀量表數字。
        if len(v) < 2:
            raise ValueError(
                f"time_stamped_table 僅 {len(v)} 筆；至少需要 2 筆"
                "（Pre 與 Post 各一，用於呈現介入前後變化）"
            )
        required_any = (
            {"timestamp", "scale", "value"},
            {"時間", "量表", "數值"},
        )
        for idx, row in enumerate(v):
            keys = set(row.keys())
            if not any(req.issubset(keys) for req in required_any):
                raise ValueError(
                    f"time_stamped_table[{idx}] 缺少必要欄位；需同時含"
                    " timestamp/scale/value（或中文等義）以呈現客觀量表數字"
                )
        return v


# ---------------------------------------------------------------------------
# HITL Checkpoints
# ---------------------------------------------------------------------------


class Checkpoint(BaseModel):
    cp_id: CheckpointId
    timestamp: datetime
    user_choice: str
    rationale: str | None = None
    phase_snapshot_path: str


# ---------------------------------------------------------------------------
# Compliance (programmatic template validator, consumed by CP7)
# ---------------------------------------------------------------------------


class ComplianceIssueRecord(BaseModel):
    section: str
    rule: str
    detail: str
    severity: Literal["error", "warning"] = "error"


class ComplianceReportRecord(BaseModel):
    passed: bool
    issues: list[ComplianceIssueRecord] = Field(default_factory=list)
    retries_used: int = 0


# ---------------------------------------------------------------------------
# Run state (full pipeline)
# ---------------------------------------------------------------------------


class RunConfig(BaseModel):
    run_id: str
    report_type: ReportType
    advancement_level: AdvancementLevel
    user_topic_raw: str
    ward_or_context: str
    clinical_scenario_zh: str | None = None
    case_file_path: Path | None = None
    target_databases: list[SourceDB] = Field(
        default_factory=lambda: [
            SourceDB.PUBMED,
            SourceDB.SCOPUS,
            SourceDB.EMBASE,
            SourceDB.COCHRANE,
            SourceDB.CINAHL,
            SourceDB.AIRITI,
        ]
    )
    year_range_start: int
    year_range_end: int


class RunState(BaseModel):
    config: RunConfig
    current_phase: PipelinePhase = PipelinePhase.INIT
    topic_verdict: TopicVerdict | None = None
    pico_result: PICOResult | None = None
    search_result: SearchResult | None = None
    casp_results: list[CaspResult] = Field(default_factory=list)
    evidence_downgrades: list[dict[str, str]] = Field(default_factory=list)
    synthesis: SynthesisResult | None = None
    sections: list[Section] = Field(default_factory=list)
    voice_check: VoiceCheckResult | None = None
    apa_check: ApaCheckResult | None = None
    case_narrative: CaseNarrative | None = None
    intervention_audit: InterventionAudit | None = None
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    compliance_report: ComplianceReportRecord | None = None
    rendered_docx_path: Path | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
