# zh-ebn-report

[![Build & Release Skill](https://github.com/htlin222/zh-ebn-report-skill/actions/workflows/release.yml/badge.svg)](https://github.com/htlin222/zh-ebn-report-skill/actions/workflows/release.yml)
[![GitHub Release](https://img.shields.io/github/v/release/htlin222/zh-ebn-report-skill?include_prereleases&label=skill%20version)](https://github.com/htlin222/zh-ebn-report-skill/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Skills Protocol](https://img.shields.io/badge/protocol-vercel--labs%2Fskills-blue)](https://github.com/vercel-labs/skills)
[![Compatible Agents](https://img.shields.io/badge/agents-40%2B-green)](https://github.com/vercel-labs/skills#supported-agents)

> 台灣護理人員撰寫實證護理報告（實證讀書報告、實證案例分析）的完整教練技能——專為護理進階制度 N1–N4 升等、台灣護理學會與台灣實證護理學會審查格式而設計。

## 這個 skill 給誰用？

給**台灣的護理人員**。你只要打入一個糊的題目（例如「早期下床」「壓瘡」「譫妄的處理」），這份 skill 會帶著你跑完實證 5A 步驟，最後產出一份真的可以送審升等的報告草稿。

## 能做什麼

- **選題把關**：把糊的題目具體化為符合審查格式的陳述句 + 疑問句版篇名；避開五大地雷主題（文獻極少、爭議太大、倫理敏感、無法操作、非護理範疇）
- **PICO 建構**：自動輸出中英並列 PICO，禁止「無介入」當 C、強制量化 O、標註 Therapy / Harm / Diagnosis / Prognosis 問題型態
- **六件套搜尋策略**：主詞 / 同義字 / MeSH / CINAHL Heading / Boolean / 欄位碼；搭配 PubMed 100–1000 甜蜜區校準法則與反向/正向引文追蹤
- **CASP 評讀**：RCT、SR、Cohort、Qualitative 四套檢核表；Oxford 2011 證據等級；禁止「效度尚可」等含糊語言
- **綜整整合**：跨篇一致性分析、矛盾點偵測、整體證據強度判定、台灣脈絡可行度（健保、護病比、家屬文化、訓練門檻、組織支持）
- **分節撰寫員平行 dispatch**：
  - 讀書報告 8 章：摘要 / 前言 / 主題設定 / 搜尋策略 / 評讀結果 / 綜整 / 應用建議 / 結論
  - 案例分析 7 章：摘要 / 前言 / 個案介紹 / 方法 / 綜整 / 應用與評值 / 結論
- **語氣守門員**：攔截「我覺得」「病人」「大致上」「似乎」等違規用語，自動改為「筆者」「個案」「書面語」
- **APA 7 格式員 + DOI 驗證**：CrossRef API 逐篇驗證 DOI 有效性與 metadata 一致性

## AI 使用規範（2026 版台灣護理學會）

這份 skill 符合台灣護理學會與台灣實證護理學會規範：AI 可協助完整生成草稿，但：
- AI 不列為作者
- 在研究方法或致謝段**主動揭露** AI 工具名稱、版本、使用方式
- 作者必須**逐節審閱與修訂** AI 產出，並簽署 Audit 責任聲明
- 建議將 AI 輔助生成部分作為補充資料一併提交

Pipeline 每次輸出的 DOCX 自動附上這三份文件，使用者 audit 後簽名即可送審。

## Install

```bash
npx skills add htlin222/zh-ebn-report-skill
npx skills add -g htlin222/zh-ebn-report-skill                  # 全域
npx skills add htlin222/zh-ebn-report-skill --agent claude-code # 指定 agent
```

安裝後在 Claude Code 等相容 agent 中直接輸入糊題目（例：「我要寫 N3 譫妄報告」），skill 自動觸發。

## Skill structure

```
zh-ebn-report/
├── SKILL.md
└── references/
    ├── ai-disclosure.md              — 2026 台灣護理 AI 使用規範與揭露/Audit/Subagent 紀錄三份模板
    ├── appraisal-tools.md            — CASP × 4 checklist + Oxford 2011 證據等級
    ├── case-report-template.md       — 案例分析完整模板（N3-N4 主用）
    ├── phrasing-bank.md              — 台灣護理報告標準句型庫（含 APA 7 範例）
    ├── pico-and-search.md            — PICO 設定 + 六件套搜尋 + 欄位碼速查 + 100-1000 校準 + 引文追蹤 + DOI 驗證
    ├── reading-report-template.md    — 實證讀書報告模板（N1-N2 主用）
    ├── subagent-roles.md             — 10 個具名 subagent 分工與輸入/輸出契約
    └── topic-selection.md            — 選題指引與五大地雷主題
```

## 與 Python pipeline 的關係

這份 skill 是**知識庫**，可在任何相容 agent 中單獨使用。若搭配 [zh-ebn-report Python pipeline](https://github.com/htlin222/ebn-report)（同作者開發），可進一步自動化 PubMed/Scopus/Embase 搜尋、CrossRef DOI 驗證、Quarto → DOCX 渲染與 9 個 HITL checkpoint 管理。單用 skill 亦可完整走完 5A 流程。

## Protocol

遵循 [vercel-labs/skills](https://github.com/vercel-labs/skills) protocol。每次 push 到 `main` 觸發 GitHub Action，打包成 `.skill` 檔並發布 release（以 commit SHA 作為版本標籤）。

## License

[MIT License](LICENSE) © 2026 htlin222
