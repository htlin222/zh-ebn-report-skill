"""Reading-report / case-report template spec (single source of truth).

These numbers come straight from
``zh-ebn-report/references/reading-report-template.md`` and
``case-report-template.md``. Prompts, compliance checker and renderer must
read from here — never hard-code a word range elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WordRange:
    """CJK-character count range (inclusive)."""

    min: int
    max: int

    def contains(self, n: int) -> bool:
        return self.min <= n <= self.max

    def describe(self) -> str:
        if self.min == self.max:
            return f"約 {self.min} 字"
        return f"{self.min}–{self.max} 字"


@dataclass(frozen=True)
class SectionSpec:
    name: str
    word_range: WordRange
    required: bool
    must_cite_all_papers: bool = False
    must_cite_at_least: int = 0
    description: str = ""


# ---------------------------------------------------------------------------
# Reading-report section order (8-chapter structure)
# ---------------------------------------------------------------------------
# Matches reading-report-template.md §報告完整骨架 (摘要 + 7 main chapters).
# 「參考文獻」章由 Quarto/CSL 自動產出，不屬於 section writer 範圍。
READING_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(180, 260),  # 模板「約 200 字」，±30% 作為硬區間
        required=True,
        description="單段連續敘述；背景/方法/結果/結論各 1–2 句；末附 3–5 組中英並列關鍵詞。不得含引文。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_at_least=3,
        description="背景重要性→現行照護不足→動機→報告概述。至少 3 處引文。",
    ),
    SectionSpec(
        name="主題設定",
        word_range=WordRange(200, 400),
        required=True,
        description="PICO 四要素（中英並列）＋ 問題型態（Therapy/Harm/Diagnosis/Prognosis）；以表格呈現。",
    ),
    SectionSpec(
        name="搜尋策略",
        word_range=WordRange(500, 800),
        required=True,
        description="資料庫清單、六件套策略、Limits、搜尋歷程（起始→去重→納入）、引文追蹤、DOI 驗證。",
    ),
    SectionSpec(
        name="評讀結果",
        word_range=WordRange(500, 1000),
        required=True,
        must_cite_all_papers=True,
        description="摘要表 + 逐篇 CASP 要點（設計/樣本/主要結果/Oxford 等級）。每篇至少引用一次。",
    ),
    SectionSpec(
        name="綜整",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_all_papers=True,
        description="跨篇一致性、矛盾與解釋、整體證據強度、台灣脈絡可行度。依 Oxford 等級由高至低敘述。",
    ),
    SectionSpec(
        name="應用建議",
        word_range=WordRange(300, 600),
        required=True,
        description="假想應用情境：目標族群、建議措施 3–5 項、執行注意事項、成效評值指標。",
    ),
    SectionSpec(
        name="結論",
        word_range=WordRange(200, 300),
        required=True,
        description="回應 PICO、承認限制、對臨床/教育/研究的具體建議（不可含糊）。",
    ),
)


# ---------------------------------------------------------------------------
# Case-report section order (case-report-template.md §報告完整骨架)
# ---------------------------------------------------------------------------
# 案例分析保留既有 6 章制，僅把字數常數集中於此。
CASE_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(200, 300),
        required=True,
        description="五要素單段：個案特徵、臨床困境、實證方法、主要發現、應用結果。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_at_least=2,
        description="選案動機、現行常規及依據、筆者察覺的問題點、引出 5A。",
    ),
    SectionSpec(
        name="個案介紹",
        word_range=WordRange(700, 1200),
        required=True,
        description="條列式客觀資料：基本資料、病史、身體評估、檢驗、心理/社會/靈性。",
    ),
    SectionSpec(
        name="方法",
        word_range=WordRange(700, 1200),
        required=True,
        description="PICO + 搜尋策略 + 評讀工具；案例分析合併成單節敘述。",
    ),
    SectionSpec(
        name="綜整",
        word_range=WordRange(500, 800),
        required=True,
        must_cite_all_papers=True,
        description="跨篇一致性、矛盾、整體證據強度、應用到本個案的可行度。",
    ),
    SectionSpec(
        name="應用與評值",
        word_range=WordRange(1000, 1500),
        required=True,
        description="Apply（介入計畫、實施、挑戰）+ Audit（時間軸、前後客觀量表、偏差說明）。",
    ),
    SectionSpec(
        name="結論",
        word_range=WordRange(200, 400),
        required=True,
        description="回應 PICO、個案貢獻、對臨床與未來研究的建議。",
    ),
)


# ---------------------------------------------------------------------------
# TWNA 個案報告（N2/N3 送審；台灣護理學會 108.03.21 修訂 + 112.10.24 評分表）
# ---------------------------------------------------------------------------
# 權威來源：
#   https://www.nantou-nurses.org.tw/filecenter/B/8D6B3965FB98C2D071/
#       8D6B3965FB98C2D0712.pdf  ← 送審作業細則
#   https://www.nantou-nurses.org.tw/filecenter/B/8DBE1FA61590909071/
#       8DBE1FA615909090713.pdf  ← 審查評分表
#
# 全文限制：內文 ≤16 頁（每頁 30×20 = 600 CJK chars → 上限約 9600 CJK）。
# 下列各節範圍依評分權重（摘要 5 / 前言 5 / 文獻查證 15 / 護理評估 15 /
# 問題確立 10 / 護理措施 20 / 結果評值 10 / 討論結論 10 / 參考 5 = 100 分）
# 按比例配置，並保留 20% 緩衝。摘要硬上限 500 字由細則明訂。
TWNA_CASE_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(300, 500),
        required=True,
        description="500 字內（含標點）；涵蓋選案理由、照顧期間、評估方法、健康問題、照護措施與建議。不得含引文。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(400, 700),
        required=True,
        must_cite_at_least=2,
        description="個案選擇動機（2 分）+ 個案照護重要性（3 分）。",
    ),
    SectionSpec(
        name="文獻查證",
        word_range=WordRange(1000, 2000),
        required=True,
        must_cite_at_least=5,
        description="系統/組織/條理（3 分）+ 近期中英文（4 分）+ 能呈現與個案護理過程相關之文獻（8 分）；高證據等級實證文獻或照護指引尤佳。",
    ),
    SectionSpec(
        name="護理評估",
        word_range=WordRange(1200, 2200),
        required=True,
        description="含個案簡介；主客觀時效性（5 分）+ 整體性持續性評估（10 分）。",
    ),
    SectionSpec(
        name="問題確立",
        word_range=WordRange(500, 1000),
        required=True,
        description="客觀時效正確性（5 分）+ 主客觀資料與相關因素（5 分）。",
    ),
    SectionSpec(
        name="護理措施",
        word_range=WordRange(1500, 2800),
        required=True,
        description="目標獨特性（5 分）+ 連貫一致適當（5 分）+ 具體周詳個別可行（7 分）+ 文獻查證內容應用（3 分）。",
    ),
    SectionSpec(
        name="結果評值",
        word_range=WordRange(500, 1000),
        required=True,
        description="目標與措施有效性（4 分）+ 整體成效（4 分）+ 後續計畫（2 分）。",
    ),
    SectionSpec(
        name="討論與結論",
        word_range=WordRange(500, 1000),
        required=True,
        description="影響個案照護成效之因素（4 分）+ 限制與困難（3 分）+ 對日後護理實務之具體建議（3 分）。",
    ),
)


# ---------------------------------------------------------------------------
# TWNA 護理專案（N4 送審；台灣護理學會 108.03.21 修訂）
# ---------------------------------------------------------------------------
# 全文限制：內文 ≤20 頁（每頁 600 CJK chars → 上限約 12000 CJK）。
# 摘要硬上限 300 字由細則明訂。
TWNA_PROJECT_SECTION_ORDER: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="摘要",
        word_range=WordRange(200, 300),
        required=True,
        description="300 字內（含標點）；涵蓋現況、問題、目的、解決辦法、結果評值。不得含引文。",
    ),
    SectionSpec(
        name="前言",
        word_range=WordRange(400, 800),
        required=True,
        must_cite_at_least=2,
        description="專案背景、重要性、動機。",
    ),
    SectionSpec(
        name="現況分析",
        word_range=WordRange(800, 1500),
        required=True,
        description="以具體數據呈現單位現況、查檢結果、圖表分析。",
    ),
    SectionSpec(
        name="問題及導因確立",
        word_range=WordRange(500, 1000),
        required=True,
        description="依資料確立主要問題；以魚骨圖或 5-Why 分析導因。",
    ),
    SectionSpec(
        name="專案目的",
        word_range=WordRange(150, 400),
        required=True,
        description="可量化之具體目標（如提升率、降低率、合格率等）。",
    ),
    SectionSpec(
        name="文獻查證",
        word_range=WordRange(1000, 2000),
        required=True,
        must_cite_at_least=5,
        description="與問題及解決策略相關之近期中英文文獻；提供解決辦法之學術依據。",
    ),
    SectionSpec(
        name="解決辦法及執行過程",
        word_range=WordRange(2000, 3500),
        required=True,
        description="完整呈現各項措施、對應導因、執行步驟、時程與人員分工；為專案核心。",
    ),
    SectionSpec(
        name="結果評值",
        word_range=WordRange(800, 1500),
        required=True,
        description="介入前後比較；以圖表呈現量化指標；達成率計算。",
    ),
    SectionSpec(
        name="討論與結論",
        word_range=WordRange(500, 1000),
        required=True,
        description="成效因素、限制、推廣建議、未來延伸。",
    ),
)


# ---------------------------------------------------------------------------
# Global constants
# ---------------------------------------------------------------------------
MIN_REFERENCES: int = 5
"""reading-report-template.md §參考文獻：至少 5 篇（EBR 讀書/案例適用）。"""

MIN_HIGH_LEVEL_EVIDENCE: int = 2
"""reading-report-template.md §參考文獻：至少 2 篇高證據等級（SR/MA/RCT；Oxford I–II）。"""

APPENDIX_ORDER: tuple[str, ...] = (
    "A",  # 搜尋歷程表
    "B",  # CASP 評讀彙整
    "C",  # PRISMA 風格流程圖
    "D",  # Subagent 執行紀錄
)


# ---------------------------------------------------------------------------
# Per-kind limits (page cap + total body CJK cap + reference minimum)
# ---------------------------------------------------------------------------
# TWNA 送審細則：非表格每頁 30×20 = 600 CJK chars。故總字數 ≈ 頁數 × 600。
# 這是 HARD 上限（超過即不通過），compliance 會驗證。
PAGE_LIMIT_BY_KIND: dict[str, int] = {
    "reading": 15,        # 醫院自訂；建議 8–15 頁
    "case": 20,           # 實證案例分析；TEBNA 投稿約 15–25 頁
    "twna_case": 16,      # TWNA 硬規：內文 ≤16 頁
    "twna_project": 20,   # TWNA 硬規：內文 ≤20 頁
}

TOTAL_BODY_CJK_LIMIT_BY_KIND: dict[str, int] = {
    "reading": 15 * 600,
    "case": 20 * 600,
    "twna_case": 16 * 600,
    "twna_project": 20 * 600,
}

MIN_REFERENCES_BY_KIND: dict[str, int] = {
    "reading": 5,
    "case": 5,
    "twna_case": 5,       # 審查評分表要求「近期中英文獻」，實務常見 5-10 篇
    "twna_project": 10,   # 護理專案範圍較廣，文獻需更完整
}


# ---------------------------------------------------------------------------
# Lookup helpers (per-kind to avoid cross-kind overrides for shared names)
# ---------------------------------------------------------------------------
SECTION_WORD_RANGE_READING: dict[str, WordRange] = {
    s.name: s.word_range for s in READING_SECTION_ORDER
}
SECTION_WORD_RANGE_CASE: dict[str, WordRange] = {
    s.name: s.word_range for s in CASE_SECTION_ORDER
}
SECTION_WORD_RANGE_TWNA_CASE: dict[str, WordRange] = {
    s.name: s.word_range for s in TWNA_CASE_SECTION_ORDER
}
SECTION_WORD_RANGE_TWNA_PROJECT: dict[str, WordRange] = {
    s.name: s.word_range for s in TWNA_PROJECT_SECTION_ORDER
}


ReportKind = Literal["reading", "case", "twna_case", "twna_project"]

_ORDER_BY_KIND: dict[str, tuple[SectionSpec, ...]] = {
    "reading": READING_SECTION_ORDER,
    "case": CASE_SECTION_ORDER,
    "twna_case": TWNA_CASE_SECTION_ORDER,
    "twna_project": TWNA_PROJECT_SECTION_ORDER,
}

_WORD_RANGE_BY_KIND: dict[str, dict[str, WordRange]] = {
    "reading": SECTION_WORD_RANGE_READING,
    "case": SECTION_WORD_RANGE_CASE,
    "twna_case": SECTION_WORD_RANGE_TWNA_CASE,
    "twna_project": SECTION_WORD_RANGE_TWNA_PROJECT,
}


def word_range_for(kind: ReportKind, section_name: str) -> WordRange | None:
    table = _WORD_RANGE_BY_KIND.get(kind)
    if table is None:
        raise ValueError(f"Unknown ReportKind: {kind!r}")
    return table.get(section_name)


def section_order(kind: ReportKind) -> tuple[SectionSpec, ...]:
    order = _ORDER_BY_KIND.get(kind)
    if order is None:
        raise ValueError(f"Unknown ReportKind: {kind!r}")
    return order


def section_names(kind: ReportKind, *, exclude_abstract: bool = False) -> list[str]:
    order = section_order(kind)
    if exclude_abstract:
        return [s.name for s in order if s.name != "摘要"]
    return [s.name for s in order]


def required_section_names(kind: ReportKind) -> list[str]:
    return [s.name for s in section_order(kind) if s.required]


def page_limit_for(kind: ReportKind) -> int:
    return PAGE_LIMIT_BY_KIND[kind]


def total_body_cjk_limit_for(kind: ReportKind) -> int:
    return TOTAL_BODY_CJK_LIMIT_BY_KIND[kind]


def min_references_for(kind: ReportKind) -> int:
    return MIN_REFERENCES_BY_KIND[kind]
