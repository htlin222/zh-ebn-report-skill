# PICO 設定與文獻搜尋策略

---

## PICO 四要素

PICO 是實證醫學將「模糊的臨床困擾」轉化為「可以被回答的臨床問題」的標準工具。

| 要素 | 代表 | 內容 | 例子 |
|---|---|---|---|
| **P** | Patient / Population | 什麼樣的病人 | 接受腹部手術後的成人 |
| **I** | Intervention | 你想用的介入 | 嚼口香糖 |
| **C** | Comparison | 對照方式 | 一般術後照護 |
| **O** | Outcome | 想看到的結果 | 恢復腸蠕動的時間 |

### 有時會擴展成 PICOT 或 PICOS

- **T**ime：觀察的時間範圍
- **S**tudy design：限定的研究設計

## 問題型態（一定要標明）

PICO 問題有四種型態，決定你要找什麼研究設計的文獻：

| 型態 | 英文 | 適合的研究設計 | 例子 |
|---|---|---|---|
| 治療型 | Therapy | RCT、Meta-analysis | EMLA 是否能減輕腰椎穿刺疼痛 |
| 傷害型 | Harm | Case-control、Cohort | 長時間臥床是否增加頭痛風險 |
| 診斷型 | Diagnosis | 診斷性研究 | CAM 量表是否能準確診斷譫妄 |
| 預後型 | Prognosis | Cohort study | 術後臥床時間是否影響頭痛發生率 |

## PICO 寫作格式（台灣實證護理標準格式）

每個 PICO 一定要**中英並列**，因為：
1. 審查者要看你會不會用正確的英文關鍵字
2. 方便後續 PubMed 搜尋
3. 國際化專業形象

**標準格式**：

```
（○）[主題中文名稱]
Patient = [中文](English term)
Intervention = [中文](English term)
Comparison = [中文](English term)
Outcome = [中文](English term)
問題型態：[治療型 Therapy / 傷害型 Harm / 診斷型 Diagnosis / 預後型 Prognosis]
```

**實際範例**：

```
（一）EMLA 於腰椎穿刺之應用
Patient = 腰椎穿刺患者 (lumbar puncture)
Intervention = 使用 EMLA (EMLA)
Comparison = 不使用 EMLA (EMLA)
Outcome = 減輕疼痛 (pain reduce)
問題型態：Therapy 治療型
```

## PICO 設定常見錯誤

### 錯誤 1：Comparison 寫「無介入」

❌ Comparison = 未接受任何處置
✅ Comparison = 現行標準照護（routine care）

臨床上幾乎沒有「完全不做」的情境，審查者看到會退。

### 錯誤 2：Outcome 太模糊

❌ Outcome = 恢復良好
✅ Outcome = 術後 24 小時內腸蠕動恢復時間（小時）

Outcome 要**可測量、可觀察、可比較**。

### 錯誤 3：Population 太廣

❌ P = 住院病人
✅ P = 6–16 歲接受診斷性腰椎穿刺的兒童

P 要有具體的年齡、性別、疾病、處置等條件。

### 錯誤 4：一個 PICO 問兩件事

❌ I = 使用 EMLA 與音樂療法
✅ 分成兩個 PICO：PICO-1 測 EMLA、PICO-2 測音樂療法

每個 PICO 只問**一個變項**的效果。

---

## 文獻搜尋策略

### 使用的資料庫（依證據等級排序）

**次級資料庫（整合證據）** — 優先搜尋：
1. **Cochrane Library** — 最高證據等級的系統性回顧
2. **JBI (Joanna Briggs Institute)** — 護理專用實證資料庫
3. **UpToDate** — 臨床決策支援，可作背景參考
4. **DynaMed** — 臨床決策支援

**初級資料庫（原始研究）**：
5. **PubMed** — 最大的醫學資料庫
6. **Embase** — 歐洲系統，藥物研究豐富
7. **CINAHL** — 護理與相關健康文獻專用
8. **華藝線上圖書館（Airiti Library）** — 中文文獻
9. **臺灣博碩士論文知識加值系統** — 國內學位論文

### 關鍵字設定

**步驟**：
1. 先用 PICO 的原始中英文關鍵字試搜
2. 到 PubMed **MeSH Database** 查詢正式醫學術語
3. 找出同義詞、上位詞、下位詞擴大搜尋
4. 用**布林邏輯**組合：
   - `AND` 縮小範圍（交集）
   - `OR` 擴大範圍（聯集）
   - `NOT` 排除（少用）

**範例檢索語法**（PubMed）：

```
("lumbar puncture"[MeSH] OR "spinal puncture"[MeSH]) 
AND 
("bed rest"[MeSH] OR "postural" OR "recumbent") 
AND 
("post-dural puncture headache"[MeSH] OR "headache"[MeSH]) 
Filters: Humans, RCT, Meta-Analysis, Systematic Review, 2015-2025, English
```

### 六件套搜尋策略表（可重現、可審查的標準格式）

一個強健的搜尋策略**不只是一串 Boolean**，而是把查詢拆成可彼此交叉驗證的六個素材。審查者看到完整六件套會大幅提高信任度，因為這表示策略背後有可追溯的詞彙選擇。

**六件套**：

| # | 要素 | 數量 | 用途 |
|---|---|---|---|
| 1 | **主詞（Primary terms）** | 3–5 個 | 最直接描述主題的精確詞組 |
| 2 | **同義字與替代詞（Synonyms）** | 5–10 個 | 擴大召回率；同義詞、縮寫、別名、作者習慣用語 |
| 3 | **PubMed MeSH 詞** | 視主題 | 經 MeSH Database 查到的正式醫學術語 |
| 4 | **CINAHL Subject Headings** | 視主題 | CINAHL 的護理專用主題詞（與 MeSH 有出入） |
| 5 | **Boolean 整合查詢** | 1 條 | 將 1–4 以 AND / OR 整合後的實際可貼上字串 |
| 6 | **資料庫欄位碼** | 依資料庫 | 限縮到標題、摘要、關鍵字欄位，排除全文誤命中 |

**實作範例：音樂療法對術後焦慮**

```
1. 主詞：
   - music therapy
   - music intervention
   - 音樂療法
   - 術後焦慮

2. 同義字與替代詞：
   - music medicine / music-based intervention / receptive music listening
   - preoperative anxiety / postoperative anxiety / perioperative anxiety
   - 音樂介入 / 術前焦慮 / 術後焦慮 / 圍手術期焦慮

3. PubMed MeSH 詞：
   - "Music Therapy"[Mesh]
   - "Anxiety"[Mesh]
   - "Postoperative Period"[Mesh]

4. CINAHL Subject Headings：
   - MH "Music Therapy+"（含下位詞）
   - MH "Anxiety+"
   - MH "Postoperative Care"

5. Boolean 整合查詢（PubMed 版）：
   ("Music Therapy"[Mesh] OR "music therapy"[tiab] OR "music intervention"[tiab])
   AND
   ("Anxiety"[Mesh] OR "anxiety"[tiab])
   AND
   ("Postoperative Period"[Mesh] OR "postoperative"[tiab] OR "post-surgery"[tiab])

6. 欄位碼（見下一節速查）：
   PubMed: [Mesh] + [tiab]
   CINAHL: MH + TI + AB
```

在搜尋歷程表中，六件套會作為「搜尋前的策略文件」附在表前或附錄，讓審查者能看到**從 PICO → 關鍵字 → 查詢**的完整推論鏈。

---

### 資料庫欄位碼速查表

欄位碼（field codes / search tags）把查詢限縮到特定欄位，避開全文誤命中。沒有欄位碼的 Boolean 容易把 5000 篇無關的文章吸進來。

| 資料庫 | 欄位碼 | 含義 | 何時使用 |
|---|---|---|---|
| **PubMed** | `[tiab]` | 標題或摘要 | 預設；最常用，兼顧召回與精確 |
| | `[ti]` | 僅標題 | 搜尋主題非常明確、避免摘要雜訊 |
| | `[Mesh]` | 正式 MeSH 詞 | 使用 MeSH Database 查到的主題 |
| | `[Majr]` | 主題為 Major MeSH | 想鎖定文獻的**核心主題**而非附帶提及 |
| | `[au]` | 作者 | 已知特定作者的既有研究 |
| | `[pt]` | Publication Type | 配合 `randomized controlled trial[pt]` |
| **CINAHL** | `MH` | CINAHL Subject Heading（含下位詞 `+`） | 等同 PubMed 的 MeSH |
| | `MW` | Word in Subject Heading | 主題詞詞根模糊匹配 |
| | `TI` | 標題 | 主題很明確時使用 |
| | `AB` | 摘要 | 擴大召回 |
| | `MM` | Major Subject | 等同 Major MeSH |
| **Cochrane Library** | `:ti,ab,kw` | 標題、摘要、關鍵字三欄聯合 | 預設最常用 |
| | `:ti` | 僅標題 | 收緊 |
| | MeSH descriptor | 右側面板勾選 | 以 MeSH tree 瀏覽 |
| **華藝 Airiti** | 標題 / 關鍵字 / 摘要 | 進階搜尋下拉選單 | 中文主題詞搜尋 |
| **臺灣博碩士論文** | 論文名稱 / 關鍵字 / 摘要 | 進階搜尋下拉選單 | 中文學位論文 |

**經驗法則**：
- 英文資料庫：主題詞用主題欄位碼（`[Mesh]`/`MH`/MeSH descriptor）、自由字用 `[tiab]`/`TI+AB`/`:ti,ab,kw`
- 中文資料庫：標題與關鍵字並用；避免只搜「全文」會洗出大量無關文獻

---

### 結果數量校準法則（100–1000 甜蜜區）

搜尋完第一次看結果篇數，就能大致判斷策略是否合理：

| 初始結果篇數 | 意義 | 調整動作 |
|---|---|---|
| **< 50** | 太窄，可能錯過合理證據 | 加同義字、拿掉部分 Filter（如研究類型限制）、把 `[ti]` 改 `[tiab]`、年份從 5 年放寬到 10 年 |
| **100–1000** | **甜蜜區**，繼續做納入/排除篩選 | 不動，逐篇看標題摘要 |
| **1000–5000** | 稍寬，可接受但篩選吃力 | 若時間許可可直接篩；否則加一個主題限制詞或縮年份 |
| **> 5000** | 太寬，不可接受 | 把自由字改 MeSH / Subject Heading、加研究設計 Filter、縮年份、拿掉 `OR` 過多的同義字群 |

**為什麼是 100–1000**：這個範圍足以在一小時內以標題摘要快速篩完，又夠寬容納邊緣相關的文獻。實證研究（特別是 robust-lit-review 的自動化經驗）一致發現低於 100 篇容易漏掉好證據、超過 1000 篇在非 SR 情境下會造成篩選疲勞、品質下滑。

**每次調整都要記**：搜尋歷程表的「備註」欄寫清楚這次調整是收緊還是放寬、換了哪個關鍵字/Filter、上一輪篇數與本輪篇數對比。這讓審查者能驗證你的迭代過程是有根據的。

---

### 搜尋 Limits 設定（建議）

- **Publication type**：Systematic Review, Meta-Analysis, RCT
- **Year**：近 5 年（若文獻少可放寬到 10 年）
- **Species**：Humans
- **Language**：English, Chinese
- **Age group**：依 PICO 設定

### 搜尋歷程紀錄（一定要寫）

**表格呈現（升級版，含可重現性欄位）**：

| 關鍵字 | 資料庫 | 欄位限定 | 搜尋結果篇數 | 去重後篇數 | 納入條件 | 排除條件 | 納入篇數 | 備註（迭代原因） |
|---|---|---|---|---|---|---|---|---|
| EMLA AND lumbar puncture | PubMed | `[tiab]` + `[Mesh]` | 31 | 31 | 符合題意、證據等級高、可全文下載、英文 | 年代久遠、無全文、介入措施不符 | 2 | 初次搜尋即落在甜蜜區，無須調整 |
| 腰椎穿刺 OR 脊髓穿刺 | 華藝 | 標題 + 關鍵字 | 27 | 24（跨 PubMed 去重 3） | 符合題意 | 介入措施不符 | 2 | 第一次搜尋全文欄位 >200 篇太寬，改為標題+關鍵字後降到 27 |

**三個新欄位的意義**：
- **欄位限定**：記錄用了哪些欄位碼，等於是對「為什麼只有這麼多篇」的直接解釋
- **去重後篇數**：跨資料庫以 DOI + 標題前 50 字比對，避免同篇被重複計入納入清單
- **備註（迭代原因）**：每一輪的調整決策——甜蜜區法則是否達成、換了哪個 Filter、上下輪對比

**敘述補充**：說明為什麼最後納入這幾篇（通常是「主題最相近 + 證據等級最高 + 發表時間最近」）。如果某篇納入但 CASP 有疑慮，也要在這裡先點出。

### 引文追蹤與去重（補漏與可重現性）

資料庫 Boolean 搜尋會漏掉兩類文獻：
1. **作者用詞跟你想的不一樣**（主題詞沒命中）
2. **資料庫沒收錄**（期刊太新、太地區性、會議論文）

補救方法是**引文追蹤（citation chasing / snowballing）**，做完可以讓審查者覺得你「搜得很徹底」。

#### 反向引文追蹤（Backward citation chasing）

**做法**：納入的每一篇文章，看它的 reference list，找出相關的老文獻。

**用途**：
- 找到經典研究、理論源頭
- 補足你在資料庫用新詞沒搜到的舊文獻
- 引文追蹤的標準第一步

**實作**：讀完納入文章後，列出其 reference list 中**與 PICO 相關**的 2–3 篇，到 PubMed/Google Scholar 看是否需要納入。

#### 正向引文追蹤（Forward citation chasing）

**做法**：納入的每一篇文章，看**誰引用了它**，找出相關的新文獻。

**用途**：
- 找到比你原本搜尋還新的文獻
- 看主題演進方向、有沒有後續 RCT 或 SR 驗證
- 找到作者習慣用的新詞

**實作**（任選其一）：
- **Google Scholar**：搜標題 → 點擊該文 → 下方的「**Cited by N**」連結 → 篩 5 年內且相關的
- **OpenAlex**（`openalex.org`）：免費 API 查 `cited_by_count` 與 cited works 清單
- **Web of Science / Scopus**：如機構有訂閱

**紀律**：正反向追蹤都要**寫進搜尋歷程的敘述**，不是偷偷納入。例如：「另以 Google Scholar 對 Smith (2020) 進行正向引文追蹤，發現 Lin (2023) 的後續 RCT，納入本次評讀。」

#### 跨資料庫去重（Deduplication）

同一篇文章常被 PubMed、Cochrane、CINAHL 重複收錄，直接相加會灌水納入篇數，審查者一看就知道你沒去重。

**標準做法（兩階比對）**：
1. **第一階 — DOI 主鍵**：有 DOI 的文獻以 DOI 完全比對；相同即為同一篇
2. **第二階 — 標題前 50 字 + 第一作者姓氏 + 年份**：沒有 DOI 或 DOI 不一致時使用；標題前綴相同即人工判定是否同篇

**工具建議**：
- EndNote、Zotero 內建「Find Duplicates」功能，拿來做第一輪自動去重
- 再由人工看一遍，特別留意會議摘要 vs. 正式期刊版（兩者常有不同 DOI 但內容幾乎相同）

**搜尋歷程表**要記「去重後篇數」那欄，讓審查者看到每個資料庫原始命中與去重後的差異。

#### DOI 驗證（引用前必做）

寫報告引用每一篇前，**逐篇驗 DOI 能不能解析**，避免：
- LLM 生成引文時幻覺（編造不存在的 DOI）
- 複製貼上字元錯誤（全形/半形、連字號）
- 期刊撤稿後 DOI 失效

**手動驗證**：在瀏覽器輸入 `https://doi.org/<DOI>`，能正確跳轉到該文即可。

**程式化驗證（進階）**：呼叫 CrossRef API `https://api.crossref.org/works/<DOI>`，除了檢查 DOI 存在，還能核對回傳的 title / authors / year 是否與你記錄的 Paper 一致。Pipeline 會自動做這步。

**發現 DOI 驗證失敗**：把該篇**移除納入清單**，不要硬塞。在搜尋歷程的備註欄記「DOI 驗證失敗，改以替代文獻 XXX 替代」。

---

### PRISMA-style 流程圖（加分項）

可以畫一個簡化流程圖：

```
Identification（識別階段）
  ↓  PubMed: 31 篇
  ↓  Cochrane: 8 篇
  ↓  CINAHL: 12 篇
  ↓  合計：51 篇
  ↓
Screening（篩選階段）
  ↓  排除重複：-5
  ↓  排除主題不符：-28
  ↓  排除年代久遠：-10
  ↓
Eligibility（資格審查）
  ↓  全文評估：8 篇
  ↓  排除介入不符：-4
  ↓
Included（納入）：4 篇
```

---

## 快速查核表

寫完 PICO 和搜尋策略後，用這個清單確認：

- [ ] P 有具體條件（年齡、性別、疾病、處置）
- [ ] I 只有一個變項
- [ ] C 是現行標準照護或替代介入，不是「無介入」
- [ ] O 可測量、可觀察
- [ ] 標明問題型態（4 種之一）
- [ ] 中英文關鍵字並列
- [ ] 至少搜尋 2 個資料庫
- [ ] **六件套搜尋策略**完整（主詞 / 同義字 / MeSH / CINAHL Heading / Boolean / 欄位碼）
- [ ] 有交代布林邏輯、Limits **與欄位碼**
- [ ] **初始篇數落在 100–1000 甜蜜區**；否則記錄調整歷程
- [ ] 有**跨資料庫去重**（DOI + 標題比對），搜尋歷程表有「去重後篇數」欄
- [ ] 有做**正向/反向引文追蹤**，並寫入敘述
- [ ] 每篇引用文獻的 **DOI 皆已驗證**（doi.org 可解析）
- [ ] 有表格化的搜尋歷程（欄位限定、去重後篇數、備註皆填寫）
- [ ] 最終納入 2–5 篇（讀書報告）或 2–4 篇（案例分析）
- [ ] 至少 1 篇高證據等級（Level I 或 II）
