# 2605.12653 GroupA+ 導入審查（2026-07-17）

## PDF

- 檔案：`C:\Users\isaac\Downloads\2605.12653.pdf`
- 標題：`Plan Before You Trade: Inference-Time Optimization for RL Trading Agents`
- 方法名稱：`FinPILOT`
- 主題：用 forecaster 在推論時做 MPC-style planning，再執行第一步交易。

## 核心內容

論文主張：

- 傳統 RL trading agent 訓練完後通常是 static policy。
- FinPILOT 在 inference time 引入價格 forecaster，產生多步 price trajectory。
- 用 forecast trajectory 建立 imagined return objective。
- 每個交易步驟前，短暫更新 actor 或 policy，再執行第一步。
- 加入 forecast noise particles 與 downside-risk penalty，避免過度相信單一路徑。

重要實驗：

- TradeMaster DJ30 benchmark。
- 2012-2019 train、2020 validation、2021 test。
- 29 檔 DJ30 股票。
- 交易成本：`0.1%`。
- XGBoost forecaster 平均 test `R2 ≈ 0.01`。
- Planning horizon 主要使用 `H = 50`。
- PPO / SAC / A2C 改善較明顯，TD3 / DDPG 較弱。
- FX dataset 不重新調參也有部分改善。

主要限制：

- 只驗證 DJ30 與 FX benchmark。
- PPO / SAC 的最大回撤在部分結果中反而增加。
- 需要 forecaster 品質；forecast error 會直接污染 imagined reward。
- 真正的 inference-time actor update 有計算與穩定性風險。
- 結果不等於可直接外推到台股 ETF。

## 對 GroupA+ 的判斷

不建議導入完整 FinPILOT / MPC actor update。

原因：

- GroupA+ 最新策略不是線上訓練的 actor-critic trading agent。
- 現有 live pipeline 需要可重現、可審計，不適合每天推論時改 policy weights。
- 目前 NCF panel 仍有 7/20 estimate date mismatch：`00631L.TW` / `00632R.TW` panel date 是 `2026-07-16`，actual data date 是 `2026-07-17`。
- 7/20 review 已因 `institutional_0050` stale/missing 和 heterogeneous volatility high 被標為 manual review。
- 在 forecaster 新鮮度不足時使用 inference-time planning，會把 stale forecast 變成更強的交易建議，風險不合理。

## 可導入優點

### 1. Plan-before-trade / preview before execution

可導入。

GroupA+ 對應：

- 已產出 `report/group_a_plus/latest/rebalance_review_20260720.json`。
- 2605.12653 支持這個方向：交易前先用 forecaster / risk scenarios 做 preview，不直接下單。

建議：

- 所有 00631L 加碼 / rebalance 前，先產生 planning review。
- 若資料 stale 或 forecast mismatch，planning 結果只能是 `manual_review_required`。

導入層級：

- Yes：review / advisory
- No：自動 execution

### 2. Forecaster-aware imagined objective

可導入為 shadow。

GroupA+ 對應：

- 現有 forecaster 可視為 NCF v5 TabNet panel：
  - `h20_prob_up`
  - `h5_prob_up`
  - `confidence`
  - crash / drawdown / reentry 相關概率
- 可建立 FinPILOT-lite shadow score：
  - baseline target
  - no-00631L-add target
  - higher-cash target
  - staged-rebalance target

每個候選不真正更新 policy，只計算：

- expected return proxy
- downside penalty
- turnover cost
- data freshness penalty
- final imagined utility score

導入層級：

- Yes：shadow planning scorecard
- No：live policy update

### 3. Downside-risk penalty at inference time

可導入。

GroupA+ 對應：

- 已有 tail risk、heterogeneous vol、CVaR、drawdown、risk_score。
- 可把 downside penalty 寫入 7/20 review：
  - 若 heterogeneous vol high，00631L add utility 扣分。
  - 若 execution sources stale，apply disabled。

導入層級：

- Yes：manual review scoring
- No：自動權重改變

### 4. Forecast noise / particle robustness

可導入為 stress scenario。

GroupA+ 對應：

- 不需要真的 Monte Carlo 更新 actor。
- 可對 NCF forecast 做三種 scenario：
  - optimistic
  - base
  - downside
- 如果 00631L add 只在 optimistic scenario 好，則不允許自動加碼。

導入層級：

- Yes：scenario review
- No：交易規則

### 5. Cheating experiment / forecast-quality gate

可導入為 forecaster quality gate。

論文提醒：

- Planning 效果依賴 forecaster quality。
- 即使 `R2 ≈ 0.01` 有用，也要先知道 forecaster 是否可靠。

GroupA+ 對應：

- 若 NCF panel date mismatch、panel stale、drift audit 失敗，不能啟用 forecast-driven planning。
- 這和目前 7/20 blocker 一致。

導入層級：

- Yes：forecast freshness / quality gate
- No：忽略 stale 直接下單

## 不建議導入部分

### Inference-time actor weight update

不導入。

原因：

- 會破壞 daily signal 可重現性。
- 需要 GPU/梯度環境與穩定 checkpoint。
- 對小 ETF universe 的收益不明。
- 可能把 forecast error 放大成交易。

### Full MPC trajectory optimization

不導入 live。

原因：

- GroupA+ 已是明確 target-weight 策略。
- 目前更需要 execution governance，不是每天重解 portfolio policy。
- 交易成本、台股 ETF 流動性、資料新鮮度風險比 DJ30 benchmark 更重要。

### 直接用 XGBoost H=50 horizon 取代 NCF

不導入。

原因：

- GroupA+ 已有 NCF v5 / TabNet panel 與多次 panel drift 修正。
- 另訓 XGBoost forecaster 需要台股 ETF walk-forward 驗證。

## 對最新策略的影響

目前最新策略：

- `a2118_a2111_ncf_late_bull_deleverage`
- runner：`group_a_plus.runners.a2118`
- active status：`active`
- NCF panel：`results/ncf_00631l_panel_latest_20260716.csv`
- 7/20 estimate target：
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - cash = `30%`

2605.12653 不支持直接改 target weights。

可採用決策：

- 保留目前 target weights 作 reference。
- 7/20 不 auto rebalance。
- 不 auto add `00631L`。
- 新增或保留 planning review：交易前先 preview，資料新鮮度通過後才可人工 apply。

## 建議下一步

建立 FinPILOT-lite planning review artifact：

- `report/group_a_plus/latest/finpilot_lite_planning_review_20260720.json`

已完成：

- `scripts/evaluate/build_group_a_plus_finpilot_lite_planning_review.py`
- `report/group_a_plus/latest/finpilot_lite_planning_review_20260720.json`

建議欄位：

- `forecast_quality_gate`
- `forecast_freshness_gate`
- `candidate_plans`
- `base_target`
- `no_00631l_add`
- `higher_cash_buffer`
- `staged_rebalance`
- `downside_penalty_sources`
- `turnover_cost_proxy`
- `recommended_plan_for_manual_review`
- `auto_apply_allowed`

目前建議輸出：

- `forecast_freshness_gate = failed`
- `auto_apply_allowed = false`
- `recommended_plan_for_manual_review = no_00631l_add_or_wait_for_fresh_data`
- `active_allocation_impact = none`

實際輸出：

- `forecast_quality_gate = failed`
- `downside_risk_gate = high`
- `recommended_plan_for_manual_review = no_00631l_add_or_wait_for_fresh_data`
- `auto_apply_allowed = false`

## 最終決策

2605.12653 有可導入優點，但只導入為 planning / review / shadow。

Production decision：

- No：不導入完整 FinPILOT。
- No：不做 inference-time actor update。
- No：不改 GroupA+ target weights。
- No：不改 `Golden1_0531`。
- Yes：可導入 FinPILOT-lite planning review。
- Yes：強化 7/20 「preview before apply」與 forecaster freshness gate。
