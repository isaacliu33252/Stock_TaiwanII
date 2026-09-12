# 2608.09988 OpenPM審查 + Group A+既有多agent debate引擎首次實測 — 交接記錄

**日期**：2026-08-16
**論文**：Cai, Guo, Liu et al. (2026), *"OpenPM: Auditable Point-in-Time Evaluation for LLM Portfolio-Management Agents"*
**結論**：**論文本身不適用（Group A+沒有LLM自主決策的portfolio agent），但使用者追問促成了對repo裡一套從未被評估過的多agent debate引擎的首次實測，結果不支持繼續投資這條路線。**

## 1. 論文核心與不適用理由

OpenPM是給「LLM讀市場資料、自主提出投資組合權重」的agent設計的評估基準：LLM analyst層對候選股打分→LLM constructor自主提出權重→**確定性(非LLM)的critic層**強制執行mandate/流動性限制。核心發現：analyst品質比constructor選擇更重要、equal-weight是很難打敗的baseline、換手率是主要成本驅動因子（不是價差）。

**不適用**：Group A+沒有任何一個環節是「LLM自主提出交易權重」——實際決策是PPO(RL)+確定性switch規則，LLM從未被允許自由決定部位大小。唯一沾邊的LLM/新聞情緒shadow機制（`project_llm_feature_generator_news`）用的是FinBERT分類器不是生成式agent，也用不到論文的contamination certificate機制。

## 2. 使用者追問：「LLM自主決策的portfolio agent 這是可以參考的？」

查證後發現repo裡**已經有一套從未被真正評估過的多agent架構**，剛好卡在這個問題的位置：

- `multi_agent_debate.py`（FinGenius架構移植）：`ChipAgent`/`RiskAgent`/`TechnicalAgent`三個專家對switch決策辯論投票，`DebateOrchestrator.run(use_llm=False, ...)`。
- `backtest_group_a_plus_switch_policy.py`有`--use-debate`/`--debate-rounds`接進去（`_switch_returns_debate`函式）。
- `DebateOrchestrator`確實有`use_llm=True`分支（真正呼叫LLM生成發言），但**從未被呼叫過**——唯一被測試的路徑是`use_llm=False`的規則式多數決。
- 搜遍`results/`、`tests/`：**找不到任何一次評估紀錄**。這套架構build出來後從沒被backtest過，連跟現行deterministic switch規則的比較都沒做過。

## 3. 首次實測：規則式debate(零成本) vs 現行deterministic switch規則

用同一個新鮮視窗(2025-01-02~2026-08-14)、同一個switch規則(`switch_deriv_ma20_dd5_score1_hold5`)比較：

| | Deterministic（現行production邏輯）| 規則式Debate（3-agent多數決，use_llm=False）|
|---|---|---|
| 最終報酬率 | 112.30% | 109.41%（-2.89pp）|
| Sharpe | 1.943 | 1.932（略低）|
| MDD | -26.07% | **-25.79%**（略淺）|
| 切換事件數 | 14次 | **9次**（少5次）|

**觀察**：多數決門檻確實降低了whipsaw（切換少5次），MDD也略改善，但代價是報酬率下降、Sharpe打平。行為模式明顯不同：deterministic版本在2026-06-08進防禦後還有兩次來回；辯論版本進防禦後**一路卡到視窗結束(08-14)都沒切回golden**，錯過後續反彈——多數決機制讓「該不該回到多頭」的反應變遲鈍。

輸出：`results/whatif_debate_rulebased_20260816*`（非production，`--output-prefix`/`--latest-pointer`已導向`whatif_`前綴）。

## 4. 結論

**連零成本的規則式辯論版本都沒有展現明顯優勢**——報酬率下降、Sharpe打平、只有MDD小幅改善。根因推測：三個agent(Chip/Risk/Technical)底層依賴的特徵（`chip_score`/`total_risk_score`/`ma_gap`/`exit_momentum`）跟現行deterministic規則本質上是同一組資訊，多數決只是把同樣的訊號重新包裝成投票，沒有帶來新資訊。**不建議往下接真正的LLM推理**——沒有理由預期讓LLM對同樣的特徵做「推理」會比多數決規則更好，還要多付API成本跟延遲。

這也呼應OpenPM論文自己的發現（analyst品質比decision機制本身更重要）：在花LLM成本之前，該先確認底層特徵有沒有超額資訊，而不是急著換更聰明的決策機制。

## Do Not Do
- 不要在沒有先補充新資訊來源（真正的新聞文本、財報逐字稿等）的情況下，把`use_llm=True`接上真正的LLM——三個agent目前看到的特徵跟deterministic規則完全重疊，沒有理由預期LLM推理會更好。
- `results/whatif_debate_rulebased_20260816*`是研究用途，不是production pointer。

## Next Step
若未來想真正讓這條線有意義，需要先給ChipAgent/RiskAgent/TechnicalAgent補充它們目前看不到的新資訊來源（真正新聞文本、財報逐字稿、法說會紀錄），再考慮`use_llm=True`；否則這是一條已知死路，不需要重複測試。
