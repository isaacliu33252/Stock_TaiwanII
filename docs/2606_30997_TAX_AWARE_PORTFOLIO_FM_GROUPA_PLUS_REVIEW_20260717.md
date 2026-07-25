# 2606.30997 GroupA+ 導入審查（2026-07-17）

## PDF

- 檔案：`C:\Users\isaac\Downloads\2606.30997.pdf`
- 標題：`A Three-Phase Foundation Model for Tax-Aware Personalized Portfolio Management`
- 主題：foundation model + portfolio RL + MoE + tax-aware personalization

## 結論

有優點可借鑑，但不建議導入 GroupA+ 最新策略的 live target weights。

可導入方向：

- 導入到 manual review / shadow scorecard。
- 用於檢查 rebalance timing、cash buffer、turnover cap、00631L 加碼是否需要人工確認。
- 不導入 DRL / Chronos / MoE 本體。
- 不改 `a2118_a2111_ncf_late_bull_deleverage`。
- 不改 `Golden1_0531`。

主要原因：

- 論文實證只在 10 檔美股、June 2026、14 trading days 做短窗驗證。
- 假設 zero transaction cost。
- 長窗 alpha 明顯轉弱，60d / 90d 多數仍為負。
- Phase 3 tax personalization 沒有完整實證，只是架構提案。
- GroupA+ 是台股 ETF 組合，稅務與個人化 brokerage lot-level 邏輯不直接適用。

## 可導入優點

### 1. Explicit cash token / cash is an active allocation

論文重點：

- 現金應該作為 allocation softmax 中的主動資產，而不是交易失敗後的殘餘。
- 避免策略陷入 HOLD / cash trap。

GroupA+ 對應：

- 最新 7/20 estimate 已有 `cash = 30%`。
- 可把現金部位寫入 rebalance review 的主動判斷，而不是只看 `0050 / 00631L`。

建議導入：

- 在 7/20 manual review scorecard 中加入：
  - `cash_buffer_target`
  - `cash_buffer_actual`
  - `cash_buffer_gap`
  - `cash_buffer_policy = active_risk_buffer`

導入層級：

- Yes：report / advisory
- No：live target weight auto-change

### 2. Allocation-driven execution with rebalance threshold

論文重點：

- 不讓 per-ticker BUY/HOLD/SELL action head 阻擋 allocation target。
- 當目前權重和目標權重差距超過 `delta_reb` 時才 rebalance。

GroupA+ 對應：

- GroupA+ 已是 target-weight driven。
- 目前更需要的是「是否真的值得在 7/20 做 rebalance」的 review gate。

建議導入：

- 在 manual review 中加入 drift threshold：
  - `max_weight_drift`
  - `rebalance_threshold`
  - `rebalance_needed_by_drift`
  - `rebalance_allowed_by_data_freshness`

導入層級：

- Yes：manual review / execution planning
- No：自動改 target weights

### 3. Redeployment-aware turnover

論文重點：

- 賣出後同日買入是一個 rebalance decision，不應被當成兩次獨立 turnover 懲罰。
- 但仍需要 hard turnover cap 防止過度交易。

GroupA+ 對應：

- 專案已存在 `turnover_capped_execution_shadow`。
- 可把「sell-to-buy redeployment」概念加進 review 文案與統計欄位。

建議導入：

- 在 rebalance review 中區分：
  - `gross_turnover`
  - `net_redeployment_turnover`
  - `buy_notional`
  - `sell_notional`
  - `turnover_cap_used`

導入層級：

- Yes：shadow execution review
- No：改 production execution path

### 4. Objective-conditioned routing

論文重點：

- 單一 reward 不能同時服務 momentum、growth、defensive、tax-aware 等目標。
- 用 intent router / MoE 將目標分流。

GroupA+ 對應：

- GroupA+ 目前已有多個狀態：golden1、defensive、trough/reentry、late-bull deleverage。
- 不需要導入 MoE PPO，但可以導入「目標狀態標籤」讓 review 更清楚：
  - `objective = capital_preservation`
  - `objective = maintain_core_exposure`
  - `objective = controlled_reentry`
  - `objective = avoid_leveraged_add`

建議導入：

- 7/20 review 的 objective 應標為：
  - `capital_preservation_with_core_0050_exposure`
  - `avoid_00631l_auto_add`

導入層級：

- Yes：review schema / commentary
- No：MoE / PPO live model

### 5. Trust-first preview before apply

論文重點：

- 個人化或模型 adaptation 前，先 preview，使用者確認後才 apply。

GroupA+ 對應：

- 這很適合目前情境：7/20 因資料 stale、NCF mismatch、異質波動 high，應先產生 review，不自動下單。

建議導入：

- 將 7/20 動作分成：
  - `preview = manual_review_required`
  - `apply = disabled_until_data_fresh_and_user_confirmed`

導入層級：

- Yes：execution decision record
- No：自動 execution

## 不建議導入部分

### Chronos foundation model branch

不導入原因：

- 論文顯示 Chronos 可能造成 ticker representation collapse，需要額外 contrastive loss 修正。
- 對 GroupA+ 目前的 ETF 小宇宙，導入成本高於預期收益。
- 現有 NCF v5 / TabNet / risk overlays 已有更直接的台股資料驗證。

### DRL / PPO portfolio actor critic

不導入原因：

- 實證視窗太短。
- zero transaction cost 不符合台股 ETF 實務。
- 10 檔美股結果不能外推到 `0050 / 00631L / 00632R / 00679B`。

### Tax-aware personalization / LoRA

不導入原因：

- 台灣 ETF 策略不是美國 brokerage tax-lot harvesting 問題。
- Phase 3 沒有完整 empirical evaluation。
- GroupA+ 目前目標是固定策略與風控，不是每個使用者個人化。

### Natural language goal parser

不導入原因：

- 對策略績效無直接幫助。
- 可能增加操作 ambiguity。
- 目前用結構化 strategy / review JSON 更安全。

## 對 GroupA+ 最新策略的判斷

目前最新策略：

- `a2118_a2111_ncf_late_bull_deleverage`
- active runner：`group_a_plus.runners.a2118`
- NCF panel：`results/ncf_00631l_panel_latest_20260716.csv`
- live estimate 7/20 target：
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - `cash = 30%`

2606.30997 不支持直接改這些權重。

可採用的決策語句：

- `cash` 是主動風險緩衝，不是剩餘資產。
- `00631L` 加碼必須通過 objective/risk/freshness review。
- 若 data freshness 不過關，採用 preview-only，不 apply。

## 建議下一步

建立 7/20 rebalance review artifact：

- `report/group_a_plus/latest/rebalance_review_20260720.json`

已完成：

- `scripts/evaluate/build_group_a_plus_rebalance_review.py`
- `report/group_a_plus/latest/rebalance_review_20260720.json`

建議欄位：

- `requested_as_of_date`
- `actual_data_date`
- `strategy_id`
- `base_target_weights`
- `golden1_reference_weights`
- `cash_buffer_policy`
- `objective`
- `rebalance_needed_by_drift`
- `rebalance_allowed_by_freshness`
- `allow_00631l_add`
- `manual_review_required`
- `blocking_reasons`
- `advisory_sources`

建議決策：

- `manual_review_required = true`
- `allow_00631l_add = false`
- `auto_rebalance_allowed = false`
- `active_allocation_impact = none`

實際輸出決策：

- `manual_review_required = true`
- `allow_00631l_add = false`
- `auto_rebalance_allowed = false`
- `target_weight_change_allowed = false`

Blocking reasons：

- `required strategy sources are stale or missing: ['institutional_0050']`
- `execution_plan actual_data_date 2026-07-15 does not match live actual_data_date 2026-07-17`
- `heterogeneous_vol_regime_advisory recommends avoiding 00631L add until manual review`

## 最終決策

2606.30997 有可導入優點，但只導入為 review / shadow / execution governance 概念。

Production decision：

- No：不導入 live target weights。
- No：不導入 Chronos / DRL / MoE。
- No：不改 `Golden1_0531`。
- Yes：可導入 7/20 manual rebalance review scorecard。
