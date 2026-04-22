# Subagent 角色目錄與輸入/輸出契約

本技能以 **10 個具名 subagent** 分工，每個角色只做一件事、只吃它需要的脈絡、產出固定結構的結果。主協調者（orchestrator）負責依 5A 時序 dispatch，並在彼此獨立的階段**並行**呼叫，把多個 agent 的結果彙整成可審稿的草稿。

> **為什麼要分工**：單一 agent 端到端寫完報告容易幻覺（數值瞎編、角色混淆、檢核遺漏）。拆成小角色後，每個 agent 的 scope 小、驗證容易、可重跑。這也是 `htlin222/robust-lit-review` 產出可通過 PRISMA 27 項稽核的核心設計。

---

## 時序總覽

```
[讀書報告]
Phase 1  題目守門員          →  CP1
Phase 2  PICO 建構員          →  CP2
Phase 3  搜尋策略師           →  CP3
         PubMed 抓 / RIS 匯入 + 去重 + DOI 驗證 → CP4
Phase 4  CASP 評讀員 × N（並行）    → CP5
Phase 5  綜整整合員           →  CP6
Phase 6  分節撰寫員 × 4（並行）     → CP7
Phase 7  語氣守門員 + APA 7 格式員（並行）  → CP8
Phase 8  Quarto render → DRAFT DOCX   → CP9

[案例分析 在 Phase 5 後插入 Phase 5.5]
Phase 5.5  個案敘事員 + 應用審計員（並行）
Phase 6    分節撰寫員 × 6（並行）
```

並行原則：**彼此輸入沒有依賴**的 agent 一律並行（Phase 4 內 N 篇 CASP、Phase 6 內各節、Phase 7 的語氣與 APA、Phase 5.5 的個案與應用）。不並行 = 浪費時間。

---

## 角色 1：題目守門員（Topic Gatekeeper）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 1，Ask 前置 |
| 模型建議 | Haiku 4.5 |
| 並行 | 否 |
| 知識來源（必讀） | `references/topic-selection.md` |

**用途**：使用者打入的題目通常很糊（例：「我想寫疼痛」），這個角色把它變成能通過審查的具體題目；同時攔下五大地雷主題（文獻極少、爭議、倫理敏感、無法操作、非護理範疇）。

**輸入契約**：
```yaml
user_topic_raw: string        # 使用者原話，例："我想寫壓傷"
ward_or_context: string       # 病房別，例："外科加護"
advancement_level: N1|N2|N3|N4
report_type: reading|case
```

**輸出契約**：
```yaml
verdict: feasible | needs_refinement | not_recommended
refined_topic_zh: string      # 具體化後的題目
refined_topic_en: string      # 英文譯名（給後續 PICO/搜尋使用）
landmine_flags: [string]      # 命中哪些地雷（空陣列 = 沒問題）
rationale_zh: string          # 2-4 句說明為何可行/需修改/不建議
alternative_topics_zh: [string]  # 若 verdict 非 feasible，給 2-3 個替代建議
```

**拒絕規則**：
- 若命中「倫理敏感」地雷（如替代醫學宣稱、臨終議題對立觀點），verdict 必定 `not_recommended`，交回人類護理師討論
- 不自行跳過 CP1，使用者需明確選「批准/修改/棄題」

---

## 角色 2：PICO 建構員（PICO Builder）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 2，Ask |
| 模型建議 | Sonnet 4.6 |
| 並行 | 否 |
| 知識來源 | `references/pico-and-search.md`（PICO 四要素與問題型態） |

**輸入契約**：
```yaml
refined_topic_zh: string
refined_topic_en: string
clinical_scenario_zh: string   # 1-2 段描述臨床情境
```

**輸出契約**：
```yaml
pico:
  population_zh: string
  population_en: string
  intervention_zh: string
  intervention_en: string
  comparison_zh: string         # 不可為「無介入」；若使用者想比 placebo 也必須寫明"standard care"
  comparison_en: string
  outcome_zh: string            # 必須可測量
  outcome_en: string
  question_type: Therapy | Harm | Diagnosis | Prognosis
picot_extension: {time: string | null, study_design: string | null}
validation_warnings: [string]   # 例："Outcome 仍有模糊感"
```

**拒絕規則**：
- Comparison 欄位偵測到「無介入」「不做」「none」，自動改寫為「routine care」並加 `validation_warnings`
- Outcome 偵測到「恢復良好」「改善」類詞彙，回報要求改為量化指標

---

## 角色 3：搜尋策略師（Search Strategist）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 3，Acquire |
| 模型建議 | Sonnet 4.6 |
| 並行 | 否（但與後續 API 呼叫並行執行）|
| 知識來源 | `references/pico-and-search.md`（六件套、欄位碼速查、100–1000 校準、引文追蹤、去重） |

**輸入契約**：
```yaml
pico: PICO                     # 前一階段輸出
target_databases: [PubMed, Cochrane, CINAHL, Airiti, ...]
year_range: {start: int, end: int}  # 預設近 5 年
```

**輸出契約**：
```yaml
six_piece_strategy:
  primary_terms: [string]       # 3-5 個
  synonyms: [string]            # 5-10 個
  mesh_terms: [string]          # PubMed MeSH
  cinahl_headings: [string]     # CINAHL Subject Headings
  boolean_query_pubmed: string  # 可直接貼到 PubMed
  boolean_query_cochrane: string
  boolean_query_cinahl: string
  field_codes_used: {pubmed: string, cinahl: string, cochrane: string}

predicted_hits_per_db:          # 初估；pipeline 會實際 API 呼叫驗證
  pubmed: int | null
  cochrane: manual_import       # 無 API，需使用者提供
  cinahl: manual_import
  airiti: manual_import

tuning_plan:                    # 若實際篇數不在 100-1000，接下來怎麼調
  if_too_narrow: [string]       # 放寬動作
  if_too_wide: [string]         # 收緊動作
```

**拒絕規則**：
- Boolean 超過 3 個 `OR` 連接的自由字群 → 警告可能超過 5000 篇
- 沒有至少一個 MeSH 詞 → 拒絕輸出，要求重寫

---

## 角色 4：CASP 評讀員（CASP Appraiser）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 4，每一篇納入文獻一個 agent |
| 模型建議 | Sonnet 4.6 |
| 並行 | **是**（`asyncio.gather`，一次 N 個，N = 納入篇數） |
| 知識來源 | `references/appraisal-tools.md` + `references/phrasing-bank.md`（CASP 評論的標準句型） |

**輸入契約**：
```yaml
paper:
  title: string
  authors: [string]
  year: int
  journal: string
  doi: string
  study_design: RCT | SR | MA | Cohort | Case-Control | Qualitative
abstract_or_full_text: string
pico_context: PICO              # 用於判斷 applicability
```

**輸出契約**：
```yaml
paper_doi: string               # 回傳 anchor
tool_used: CASP-RCT | CASP-SR | CASP-Cohort | CASP-Qualitative
checklist_items:
  - q_no: int
    question_zh: string
    answer: Yes | No | Cannot_tell
    rationale_zh: string        # 1-3 句，禁止「效度尚可」這種含糊詞
validity_zh: string             # 效度評論
importance_zh: string           # 重要性評論
applicability_zh: string        # 在台灣護理脈絡下的可用性
oxford_level_2011: I | II | III | IV | V
warnings:                       # 會被 CP5 標紅的訊號
  - sample_size_below_30: bool
  - p_value_insignificant_but_strong_claim: bool
  - single_site_study: bool
  - conflict_of_interest_declared: bool
```

**拒絕規則**：
- `rationale_zh` 含「尚可」「大致」「似乎」等含糊詞 → 重寫
- Oxford Level 與 study_design 不匹配（例如 Cohort 被標為 Level I）→ 自動降級 + `warnings`

---

## 角色 5：綜整整合員（Synthesiser）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 5，所有 CASP 評讀員完成後 |
| 模型建議 | **Opus 4.7**（跨篇推論、矛盾偵測需要最強模型） |
| 並行 | 否 |
| 知識來源 | `references/appraisal-tools.md` + `references/phrasing-bank.md`（「綜整」段的句型） |

**輸入契約**：
```yaml
pico: PICO
casp_results: [CASPResult]      # 全部 2-5 篇的評讀結果
papers: [Paper]                 # 完整 metadata
```

**輸出契約**：
```yaml
consistency_analysis_zh: string  # 結果彼此一致處
contradictions_zh:               # 明顯矛盾點
  - topic: string
    paper_a: doi
    paper_b: doi
    disagreement: string
    likely_reason: string        # 人口不同、介入劑量不同、outcome 定義不同等
overall_evidence_strength: strong | moderate | limited | conflicting
clinical_feasibility_taiwan_zh: string  # 台灣護理脈絡下可行度
recommended_intervention_summary_zh: string
limitations_zh: [string]
```

**拒絕規則**：
- 若所有 paper 被評為 Level III–V，`overall_evidence_strength` 必定 `limited`，且 `limitations_zh` 必須提到證據等級
- 若存在 `contradictions_zh` 但 agent 試圖下「結論明確」，拒絕輸出

---

## 角色 6：分節撰寫員（Section Writer）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 6，撰稿 |
| 模型建議 | Sonnet 4.6 |
| 並行 | **是**（讀書報告 4 節同時 / 案例分析 6 節同時） |
| 知識來源 | `references/phrasing-bank.md`（句型庫）+ 對應章節模板（`reading-report-template.md` 或 `case-report-template.md`） |

**每節都是獨立的 agent 實例**。讀書報告節次：
- 前言（Introduction）
- 方法（Methods，含搜尋與評讀）
- 綜整（Synthesis）
- 結論（Conclusion）

案例分析另加「個案介紹」「應用與評值」兩節。

**輸入契約（單節版）**：
```yaml
section_name: 前言 | 方法 | 綜整 | 結論 | 個案介紹 | 應用與評值
pico: PICO
relevant_data:                  # 不同節吃不同輸入
  search_strategy: SearchStrategy | null
  casp_results: [CASPResult] | null
  synthesis: SynthesisResult | null
  case_details: CaseDetails | null         # 案例分析專用
  application_records: ApplicationRecord | null
advancement_level: N1|N2|N3|N4  # 決定用字深度
```

**輸出契約**：
```yaml
section_name: string
content_zh: string              # 純文字，繁體中文，套 phrasing-bank 標準句型
word_count_estimate: int        # 該節字數（審查常規：前言 500-800、其他節有對應範圍）
citation_placeholders: [string] # 內文的 [@citekey] 佔位，對應 references.bib
self_check:
  uses_bi_jia_not_wo: bool      # 全文用「筆者」不用「我」
  uses_ge_an_not_bing_ren: bool # 全文用「個案」不用「病人」
  formal_register_only: bool    # 無口語化
  cites_phrasing_bank: bool     # 有使用句型庫範本
```

**拒絕規則**：
- `self_check` 任一 false → 自動重寫一次
- `content_zh` 出現「我覺得」「我認為」「我們發現」→ 拒絕
- 引用沒對應 citation key → 拒絕

---

## 角色 7：語氣守門員（Voice Guard）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 7，定稿前 |
| 模型建議 | Haiku 4.5 |
| 並行 | **是**（與角色 8 APA 格式員並行） |
| 知識來源 | `SKILL.md` 的「寫作風格核心守則」+ `references/phrasing-bank.md` |

**用途**：全文掃描台灣護理報告語氣違規，產出違規清單 + 改寫建議。

**輸入契約**：
```yaml
full_draft_zh: string
```

**輸出契約**：
```yaml
violations:
  - category: 第一人稱誤用 | 病患稱謂錯誤 | 口語化 | 動詞非書面語 | 含糊語言
    location_excerpt: string    # 出事的原句
    suggested_rewrite: string   # 建議改寫
    severity: high | medium | low
total_violations: int
pass_threshold_met: bool        # 0 high + ≤3 medium 才算 pass
```

**拒絕規則**：
- `pass_threshold_met` false → 退回角色 6 重寫該節
- 偵測到含糊語言（「大致上」「似乎」「可能有」）→ 必列 high

---

## 角色 8：APA 7 格式員（APA Formatter）

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 7，與角色 7 並行 |
| 模型建議 | Haiku 4.5（呼叫 CrossRef 由 Python 處理，LLM 只做格式審查） |
| 並行 | **是** |
| 知識來源 | `references/phrasing-bank.md` 的 APA 7 範例 |

**輸入契約**：
```yaml
references_bib: string           # BibTeX 全文
papers: [Paper]                  # 對照用的 Paper 物件
```

**輸出契約**：
```yaml
format_issues:
  - citekey: string
    issue: missing_doi | wrong_author_format | 中英混排錯誤 | 年份缺失 | ...
    suggested_fix: string
doi_validation_results:          # 由 Python CrossRef client 帶入
  - citekey: string
    doi_resolvable: bool
    metadata_matches_paper: bool   # title/authors/year 是否一致
    mismatch_details: string | null
apa_pass: bool                   # 零 format_issues + 所有 DOI 驗證通過
```

**拒絕規則**：
- DOI 無法由 CrossRef 解析 → 該篇列 `missing_doi`，要求人工核對
- CrossRef 回傳的 title 與 Paper.title 差異 > 10% (by token) → 列 metadata 不一致，高警告

---

## 角色 9：個案敘事員（Case Narrator）— 案例分析專用

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 5.5（案例分析專用） |
| 模型建議 | Sonnet 4.6 |
| 並行 | 與角色 10 可並行 |
| 知識來源 | `references/case-report-template.md` + `references/phrasing-bank.md` |

**前置保護**：進入本角色前，主協調者必先呼叫 `utils/deid.py` 檢查輸入是否含姓名、病歷號、身分證字號 pattern；命中即退件、不 dispatch。

**輸入契約**：
```yaml
case_details_deidentified:        # 已去識別化的個案資料
  demographics: {age_group: string, sex: string}  # 不接受出生年月日
  chief_complaint_zh: string
  present_illness: string
  past_medical_history: [string]
  family_history: [string]
  allergies: [string]
  medications_on_admission: [string]
  examinations: [dict]
  nursing_assessment: dict
timeline:                         # 評估時間序（可用相對時間，如 "入院第一日"）
  - timestamp: string
    event: string
    observations: string
```

**輸出契約**：
```yaml
case_introduction_section_zh: string  # 個案介紹段
diagnostic_reasoning_section_zh: string  # 診斷推理段
deid_check_passed: bool              # 最終輸出再次自查，確認未帶出識別資訊
direct_quotes:                       # 個案/家屬/護理師原話（已以引號標記）
  - speaker: 個案 | 家屬 | 護理師 | 醫師
    quote_zh: string
```

**拒絕規則**：
- `deid_check_passed` false（回傳內容仍含姓名 pattern）→ 整段重寫
- 無任何 `direct_quotes` → 警告，因為案例分析審查會注意有無「人性化」敘述

---

## 角色 10：應用審計員（Apply+Audit Auditor）— 案例分析專用

| 屬性 | 值 |
|---|---|
| 觸發時機 | Phase 5.5，與角色 9 可並行 |
| 模型建議 | Sonnet 4.6 |
| 並行 | 是 |
| 知識來源 | `references/case-report-template.md`（Apply/Audit 結構）+ `references/phrasing-bank.md` |

**輸入契約**：
```yaml
synthesis: SynthesisResult              # 來自綜整整合員
intervention_plan_zh: string             # 使用者擬的介入計畫
pre_intervention_observations:
  - timestamp: string
    subjective: string
    objective: {scale: string, value: number | string}
post_intervention_observations:
  - timestamp: string
    subjective: string
    objective: {scale: string, value: number | string}
deviations_from_plan: string | null      # 實際執行與計畫的差異
```

**輸出契約**：
```yaml
apply_section_zh: string                 # 「如何把證據應用到個案」段
audit_section_zh: string                 # 「應用後的評值」段
time_stamped_table:                      # 結構化的時間軸，給 renderers 產 Quarto 表格
  - timestamp: string
    subjective_zh: string
    objective_data: {scale: string, value: string}
    note: string
deviation_explanation_zh: string | null  # 若 deviations_from_plan 非 null，必須有解釋
warning_too_perfect: bool                # 若沒任何 deviation，自動 true（審查者討厭過度完美）
```

**拒絕規則**：
- `warning_too_perfect` 為 true，且使用者未在輸入中標明「本次執行毫無意外」→ 主動回報建議使用者補一個合理的小偏差
- 缺少具體數值（只有主觀描述）→ 退回要求補客觀量表

---

## 主協調者的使用方式

```python
# 簡化示意，實作見 src/zh_ebn_report/pipeline/orchestrator.py
async def run_reading_report(user_input):
    # Phase 1-3 sequential
    topic = await topic_gatekeeper(user_input)
    await checkpoint("CP1", topic)

    pico = await pico_builder(topic)
    await checkpoint("CP2", pico)

    strategy = await search_strategist(pico)
    await checkpoint("CP3", strategy)

    papers = await execute_searches(strategy)  # PubMed API + 人工匯入
    await checkpoint("CP4", papers)

    # Phase 4 parallel
    casp_results = await asyncio.gather(*[
        casp_appraiser(paper) for paper in papers
    ])
    await checkpoint("CP5", casp_results)

    # Phase 5 sequential
    synthesis = await synthesiser(pico, casp_results, papers)
    await checkpoint("CP6", synthesis)

    # Phase 6 parallel
    sections = await asyncio.gather(*[
        section_writer(name, pico, ...) for name in [
            "前言", "方法", "綜整", "結論"
        ]
    ])
    await checkpoint("CP7", sections)

    # Phase 7 parallel
    voice_check, apa_check = await asyncio.gather(
        voice_guard(assemble(sections)),
        apa_formatter(bibliography, papers)
    )
    await checkpoint("CP8", (voice_check, apa_check))

    # Phase 8 render
    docx_path = quarto_render(sections, bibliography, appendices)
    await checkpoint("CP9", docx_path)
    return docx_path
```

---

## 共通守則（所有 subagent 必讀）

每個 agent 的 system prompt 都會注入以下守則（透過 `prompts/_base.md`）：

1. **繁體中文輸出**；英文專有名詞（藥名、診斷名）保留原文
2. **自稱「筆者」**，不用「我」「我們」「本人」
3. **個案稱「個案」**，不用「病人」「患者」「case 小姐」
4. **禁止模糊語**：「大致上」「似乎」「可能有」「應該是」全部改為有依據的具體描述
5. **必用引號標出原話**（個案、家屬、護理師、文獻直接引用）
6. **數字與單位齊全**：不能寫「疼痛下降」，要寫「NRS 由 7 分下降至 3 分」
7. **不做臨床決策**：agent 只能**綜整與建議**，最終決策屬護理師
8. **不得編造 DOI 或引文**：所有引文必須對應 `references.bib` 的實際條目

違反 1–8 任一條的輸出會被 orchestrator 拒收並要求重寫。

---

## 與 skill 其他參考檔案的對應關係

| Subagent | 必讀參考檔案 |
|---|---|
| 題目守門員 | `topic-selection.md` |
| PICO 建構員 | `pico-and-search.md`（PICO 段） |
| 搜尋策略師 | `pico-and-search.md`（搜尋段、六件套、欄位碼、校準、引文追蹤） |
| CASP 評讀員 | `appraisal-tools.md`、`phrasing-bank.md` |
| 綜整整合員 | `appraisal-tools.md`、`phrasing-bank.md`（綜整段句型） |
| 分節撰寫員 | `phrasing-bank.md` + `reading-report-template.md` 或 `case-report-template.md` |
| 語氣守門員 | `SKILL.md` 寫作守則 + `phrasing-bank.md` |
| APA 7 格式員 | `phrasing-bank.md`（APA 範例段） |
| 個案敘事員 | `case-report-template.md` + `phrasing-bank.md` |
| 應用審計員 | `case-report-template.md` + `phrasing-bank.md` |

這些檔案由 Python pipeline 在呼叫 Anthropic SDK 時以 **prompt caching** 注入；對同一個 run 只付一次 cache 建立成本，之後 N 次呼叫都讀 cache，token 成本壓到最低。
