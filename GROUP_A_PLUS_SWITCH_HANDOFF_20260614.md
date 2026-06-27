# GroupA+ / Golden1 Switch Handoff - 2026-06-14

## Current Objective

建立一套不用人工介入的 GroupA+ / Golden1_0531 決策流程：

1. Golden1_0531 與最新 GroupA+ 全部使用同一資金基準 `1,000,000`。
2. 多 Agent 審核流程提供 Research -> Debate -> Vote。
3. Policy Engine 把 Agent 建議轉成可執行 signal。
4. 回測 Golden1_0531 與 GroupA+ 防守策略的切換時間點。
5. 導入 FinMind / 本地籌碼資料，輔助切換判斷。

目前狀態：可用，但建議先以 shadow / 小額試行，不建議直接全量上線。

最新更新時間：`2026-06-14 17:10 CST`

最新關鍵變更：

- 已導入 FinMind 外資持股 `TaiwanStockShareholding`。
- 已導入 FinMind 台指期/台指選擇權法人資料：
  - `TaiwanFuturesInstitutionalInvestors`
  - `TaiwanOptionInstitutionalInvestors`
- 已把衍生品法人資料接進 `backtest_group_a_plus_switch_policy.py`。
- 已導入並接入空方壓力資料：
  - `TaiwanStockSecuritiesLending`
  - `TaiwanDailyShortSaleBalances`
- 已導入加權/櫃買報酬指數：
  - `TaiwanStockTotalReturnIndex`
- 最新推薦切換規則已由純價格規則改為：

```text
switch_deriv_ma20_dd5_score1_hold5
```

也就是：價格風險成立時，還需要至少 1 個衍生品法人風險確認，才切到 GroupA+ 防守。

- **2026-06-14 新增**：`TaiwanStockDayTrading`（當日沖資料）已匯入並接入 switch backtest。
  - `chip_day_trading_risk`：當日沖量 > 60日80分位 且 0050 5日跌 → risk +1
  - `chip_score` 擴充為 9 項子指標（新增第 9 項）
- **2026-06-14 新增**：`TaiwanFuturesDealerTradingVolumeDaily`（期貨自營商）和 `TaiwanOptionDealerTradingVolumeDaily`（選擇權自營商）已匯入並接入 switch backtest。
  - `chip_dealer_tx_risk`：TX 日盤自營商交易量 > 60日80分位 且 0050 5日跌 → risk +1
  - `chip_dealer_txo_risk`：TXO 日盤自營商交易量 > 60日80分位 且 0050 5日跌 → risk +1
  - `chip_score` 擴充為 11 項子指標（新增第 10、11 項）
  - DB 新增 tables：`dealer_futures_data`（36,163 rows）、`dealer_options_data`（32,344 rows）
- `government_bank`（八大公股行庫）和 `derivative_afterhours`（夜盤法人）因 FinMind Free tier 限制無法存取，待 Premium 升級後可加入

## Main Strategy Files

### Report / Review / Decision

- `group_a_plus_report_manager.py`
  - 管理 GroupA+ daily status 報告。
  - 輸出 JSON / MD / HTML / latest pointer。

- `check_group_a_plus_daily_status.py`
  - 產生每日狀態檢查。
  - 已接入 report manager。

- `generate_group_a_strategy_compare_html.py`
  - 產生 Latest GroupA+ vs Golden1_0531 HTML/JSON 比較。
  - 現在優先讀 `report/group_a_plus/latest/decision.json` 的 `signal_json`。
  - 因此 latest compare 使用 policy-adjusted GroupA+ signal，而不是舊的 27.6 萬 signal。

- `group_a_plus_review_tools.py`
  - Local ToolCollection。
  - 對應 FinGenius 的 ToolCollection 概念。
  - 提供 load latest daily status / strategy compare / baseline / JSON。

- `group_a_plus_review_agents.py`
  - Deterministic multi-agent 審核。
  - Agents:
    - `DataFreshnessAgent`
    - `RiskAgent`
    - `CostAgent`
    - `BenchmarkAgent`
  - Vote:
    - `approve`
    - `caution`
    - `shadow_only`
    - `block`

- `group_a_plus_review_pipeline.py`
  - 執行 Research -> Debate -> Vote。
  - 輸出 review JSON/HTML。

- `group_a_plus_decision_policy.py`
  - 把 review vote 轉成 executable decision。
  - 預設 `target_total_assets = 1,000,000`。
  - 目前 `caution` 會轉成 `caution_auto_adjusted`。
  - 自動調整：
    - 保留至少 `1%` cash-after-cost buffer。
    - 重新以 100 萬計算目標股數。

### Backtest / Switch

- `backtest_group_a_plus_policy_signal.py`
  - 回測 GroupA+ original / GroupA+ policy adjusted / Golden1_0531。
  - 使用靜態 target weights。
  - 用於確認 policy signal 對配置本身的影響。

- `backtest_group_a_plus_switch_policy.py`
  - 回測 Golden1_0531 與 GroupA+ 防守之間的切換規則。
  - 現在採用更真實的模擬：
    - 只有 regime 切換日重配。
    - 其餘日期持有股數，不每日重平衡。
  - 已導入本地籌碼資料作為 diagnostics / optional chip-confirm rules。

- `fetch_finmind_chip_data.py`
  - 新增的 FinMind 資料匯入器。
  - 支援：
    - `TaiwanStockInstitutionalInvestorsBuySell`
    - `TaiwanStockMarginPurchaseShortSale`
    - `TaiwanStockHoldingSharesPer`
    - `TaiwanStockShareholding`
    - `TaiwanFuturesInstitutionalInvestors`
    - `TaiwanOptionInstitutionalInvestors`
    - `TaiwanFuturesOpenInterestLargeTraders` (free level blocked)
    - `TaiwanOptionOpenInterestLargeTraders` (free level blocked)
    - `TaiwanStockDayTrading` ✅ 已匯入並接入 backtest
    - `TaiwanFuturesDealerTradingVolumeDaily` ✅ 已匯入並接入 backtest
    - `TaiwanOptionDealerTradingVolumeDaily` ✅ 已匯入並接入 backtest
    - `TaiwanStockGovernmentBankBuySell` (free level blocked)
    - `TaiwanFuturesInstitutionalInvestorsAfterHours` (free level blocked)
    - `TaiwanOptionInstitutionalInvestorsAfterHours` (free level blocked)
    - `TaiwanOptionOpenInterestLargeTraders` (free level blocked)
    - `TaiwanFuturesOpenInterestLargeTraders` (free level blocked)
    - `TaiwanStockTradingDailyReport` (free level blocked)
  - 寫入既有 DuckDB schema。

## Current Latest Pointers

- Daily status:
  - `report/group_a_plus/latest/daily_status.json`

- Strategy compare:
  - `report/group_a_plus/latest/strategy_compare.json`

- Review:
  - `report/group_a_plus/latest/review.json`

- Decision:
  - `report/group_a_plus/latest/decision.json`

- Decision backtest:
  - `report/group_a_plus/latest/decision_backtest.json`

- Switch backtest:
  - `report/group_a_plus/latest/switch_backtest.json`

## Current Latest Important Outputs

### Latest 100 萬 GroupA+ Policy Signal

- `results/group_a_plus_policy_signal_20260614_151117.json`
- `results/group_a_plus_policy_signal_20260614_151117.csv`

Key values:

- `total_assets`: `1,000,000`
- `policy_decision`: `caution_auto_adjusted`
- `allowed_for_execution`: `true`
- `target_shares`:
  - `0050.TW`: `5138`
  - `00631L.TW`: `0`
  - `00632R.TW`: `0`
  - `00679B.TWO`: `17327`
- `policy_adjusted_weights`:
  - `0050.TW`: about `52.38%`
  - `00631L.TW`: `0%`
  - `00632R.TW`: `0%`
  - `00679B.TWO`: about `46.37%`
  - `cash`: about `1.01%`
- `cash_after_cost`: about `10,092`

### Latest Golden1_0531 100 萬 Signal

- `results/signal_group_a_golden1_0531_predict_20260615_from_all_20260613_total1000000.json`

Target weights:

- `0050.TW`: `60%`
- `00631L.TW`: `20%`
- `00632R.TW`: `0%`
- `00679B.TWO`: `0%`
- `cash`: `20%`

## Decision Status

Latest review result:

- `decision`: `caution`
- Vote counts:
  - `approve`: `1`
  - `caution`: `3`
  - `block`: `0`
  - `shadow_only`: `0`

Policy Engine output:

- `decision`: `caution_auto_adjusted`
- `allowed_for_execution`: `true`

Reason codes:

- `data_freshness_agent`
- `cost_agent`
- `benchmark_agent`

Interpretation:

- Not a full approve.
- Allowed for reduced-risk execution due to automated cash-buffer adjustment.
- Should be treated as defensive/caution mode, not primary alpha replacement.

## Backtest Results

### Static Policy Signal Backtest

Command used:

```bash
python3 backtest_group_a_plus_policy_signal.py --start 2025-01-02 --end 2026-06-12 --initial-value 1000000
```

Latest output:

- `results/group_a_plus_policy_signal_backtest_20260614_152500.json`
- `report/group_a_plus/latest/decision_backtest.json`

Window:

- `2025-01-02 ~ 2026-06-12`
- rows: `348`
- initial value: `1,000,000`

Results:

| Variant | Final | Return | Sharpe | MDD |
|---|---:|---:|---:|---:|
| GroupA+ original weights | 1,558,455 | 55.85% | 1.950 | -15.72% |
| GroupA+ policy adjusted | 1,551,556 | 55.16% | 1.949 | -15.55% |
| Golden1_0531 1m | 2,114,578 | 111.46% | 2.098 | -27.54% |

Interpretation:

- Golden1 has much higher return but much deeper drawdown.
- GroupA+ policy adjusted is defensive.
- GroupA+ should not replace Golden1 as the main strategy based only on this backtest.

### Switch Backtest

Command used:

```bash
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-12 --initial-value 1000000
```

Latest output:

- `results/group_a_plus_switch_policy_backtest_20260614_163402.json`
- `results/group_a_plus_switch_policy_backtest_20260614_163402.csv`
- `results/group_a_plus_switch_policy_backtest_20260614_163402_curve.csv`
- `results/group_a_plus_switch_policy_backtest_20260614_163402_recommended_regime.csv`
- `report/group_a_plus/latest/switch_backtest.json`

Window:

- `2025-01-02 ~ 2026-06-12`
- rows: `348`
- initial value: `1,000,000`

Recommended rule:

```text
Default: Golden1_0531

Switch to GroupA+ defensive if:
  (0050 ma_gap <= -2% OR 0050 20-day drawdown <= -5%)
  AND derivative_score >= 1

Switch back to Golden1 if:
  at least 5 trading days in defensive mode
  AND 0050 ma_gap >= +1%
  AND 5-day momentum > 0
  AND derivative_score <= 1
```

Results:

| Strategy | Final | Return | Sharpe | MDD |
|---|---:|---:|---:|---:|
| Golden1_0531 | 2,114,578 | 111.46% | 2.098 | -27.54% |
| GroupA+ defensive | 1,551,556 | 55.16% | 1.949 | -15.55% |
| Original price switch `switch_ma20_dd5_hold5` | 1,985,589 | 98.56% | 2.418 | -19.85% |
| New derivative-confirm switch `switch_deriv_ma20_dd5_score1_hold5` | 2,059,820 | 105.98% | 2.496 | -19.85% |

Interpretation:

- Derivative-confirm switch still gives up some upside versus pure Golden1.
- It materially improves Sharpe versus pure Golden1 and versus the original pure-price switch.
- It keeps MDD at `-19.85%`, much lower than Golden1's `-27.54%`.
- This is now the best current candidate for production-style risk switching.

## Switch Events

Recommended rule events:

| Date | Action |
|---|---|
| 2025-01-13 | switch_to_group_a_plus_defensive |
| 2025-01-22 | switch_to_golden |
| 2025-02-03 | switch_to_group_a_plus_defensive |
| 2025-04-28 | switch_to_golden |
| 2025-11-14 | switch_to_group_a_plus_defensive |
| 2025-12-05 | switch_to_golden |
| 2026-03-04 | switch_to_group_a_plus_defensive |
| 2026-03-11 | switch_to_golden |
| 2026-03-12 | switch_to_group_a_plus_defensive |
| 2026-04-08 | switch_to_golden |
| 2026-06-08 | switch_to_group_a_plus_defensive |

As of `2026-06-12`, the rule remains in:

```text
GroupA+ defensive
```

It has not switched back to Golden1 yet.

## FinMind / Chip / Derivative Data Integration

### Local DB Tables Already Used

The switch backtest loads these existing DuckDB tables:

- `institutional_data`
- `margin_data`
- `market_margin_data`
- `shareholding_distribution`
- `foreign_shareholding_data`
- `short_sale_balance_data`
- `securities_lending_data`
- `derivative_institutional_data`
- `day_trading_data` ← 2026-06-14 新增
- `dealer_futures_data` ← 2026-06-14 新增
- `dealer_options_data` ← 2026-06-14 新增

These provide:

- 0050 institutional 5-day net buy/sell
- 0050 foreign 5-day net buy/sell
- 0050 margin balance 5-day change
- market margin balance 5-day change
- TDCC 0050 minority holder weekly change
- TDCC 0050 major holder weekly change
- 0050 foreign shareholding ratio 5-day change
- 0050 margin short balance 5-day change
- 0050 SBL short balance 5-day change
- 0050 securities lending 5-day volume
- 0050 day trading 5-day volume ← 2026-06-14 新增
- TX dealer futures volume 5-day ← 2026-06-14 新增
- TXO dealer options volume 5-day ← 2026-06-14 新增
- TX foreign futures net open interest
- TX foreign futures net open interest 5-day change
- TXO foreign call net open interest
- TXO foreign put net open interest
- TXO foreign put-call net open interest
- TXO foreign put-call net open interest 5-day change

### Chip Score

The switch backtest computes:

- `chip_inst_risk`
- `chip_foreign_risk`
- `chip_margin_risk`
- `chip_market_margin_risk`
- `chip_tdcc_risk`
- `chip_foreign_shareholding_risk`
- `chip_short_balance_risk`
- `chip_securities_lending_risk`
- `chip_day_trading_risk` ← 2026-06-14 新增
- `chip_dealer_tx_risk` ← 2026-06-14 新增
- `chip_dealer_txo_risk` ← 2026-06-14 新增
- `chip_score`（現為 11 項子指標總和）

The chip-confirm variants tested:

| Variant | Return | Sharpe | MDD |
|---|---:|---:|---:|
| switch_chip_ma20_dd5_score1_hold5 | 84.29% | 2.162 | -19.85% |
| switch_chip_ma20_dd5_score2_hold5 | 84.29% | 2.162 | -19.85% |
| switch_chip_ma60_dd8_score1_hold10 | 82.01% | 1.997 | -18.92% |

Conclusion:

- Chip score is useful for diagnostics.
- Chip score should not be a hard gate for switching yet.
- Hard chip-confirm reduced return and Sharpe.

### Derivative Score

The switch backtest now also computes:

- `derivative_futures_foreign_risk`
  - risk if TX foreign net OI is negative and 5-day change is also negative.
- `derivative_options_foreign_risk`
  - risk if TXO foreign put-call net OI is positive and 5-day change is also positive.
- `derivative_score`
  - sum of futures and options derivative risk flags.
- `total_risk_score`
  - `chip_score + derivative_score`.

Derivative-confirm variants tested:

| Variant | Return | Sharpe | MDD |
|---|---:|---:|---:|
| switch_deriv_ma20_dd5_score1_hold5 | 105.98% | 2.496 | -19.85% |
| switch_deriv_ma60_dd8_score1_hold10 | 83.58% | 1.995 | -18.92% |
| switch_risk_ma20_dd5_total2_hold5 | 97.07% | 2.396 | -19.85% |

Conclusion:

- Derivative-confirm improved the original price-only switch.
- Hard chip-confirm alone reduced return and Sharpe.
- Best current rule is `switch_deriv_ma20_dd5_score1_hold5`.

Recommended current usage:

```text
Price rule controls the candidate switch.
Derivative score confirms actual switch.
Chip score is logged for review and risk explanation.
```

## FinMind Importer

New script:

```bash
python3 fetch_finmind_chip_data.py --start 2026-06-09 --end 2026-06-12
```

Optional:

```bash
FINMIND_API_TOKEN=... python3 fetch_finmind_chip_data.py \
  --tickers 0050,00631L,00632R,00679B \
  --start 2026-06-09 \
  --end 2026-06-12 \
  --datasets institutional,margin,shareholding
```

Supported datasets:

- `institutional`
  - FinMind dataset: `TaiwanStockInstitutionalInvestorsBuySell`
  - writes to: `institutional_data`

- `margin`
  - FinMind dataset: `TaiwanStockMarginPurchaseShortSale`
  - writes to: `margin_data`

- `shareholding`
  - FinMind dataset: `TaiwanStockHoldingSharesPer`
  - writes to: `shareholding_distribution`

- `foreign_shareholding`
  - FinMind dataset: `TaiwanStockShareholding`
  - writes to: `foreign_shareholding_data`

- `securities_lending`
  - FinMind dataset: `TaiwanStockSecuritiesLending`
  - writes to: `securities_lending_data`

- `short_sale_balances`
  - FinMind dataset: `TaiwanDailyShortSaleBalances`
  - writes to: `short_sale_balance_data`

- `total_return_index`
  - FinMind dataset: `TaiwanStockTotalReturnIndex`
  - writes to: `total_return_index_data`

- `per`
  - FinMind dataset: `TaiwanStockPER`
  - writes to: `stock_per_data`
  - current status: ETF symbols returned no rows.

- `margin_maintenance`
  - FinMind dataset: `TaiwanTotalExchangeMarginMaintenance`
  - writes to: `margin_maintenance_data`
  - current status: blocked by FinMind free account level.

- `derivative_institutional`
  - FinMind datasets:
    - `TaiwanFuturesInstitutionalInvestors`
    - `TaiwanOptionInstitutionalInvestors`
  - writes to: `derivative_institutional_data`

- `derivative_large_trader`
  - FinMind datasets:
    - `TaiwanFuturesOpenInterestLargeTraders`
    - `TaiwanOptionOpenInterestLargeTraders`
  - writes to: `derivative_large_trader_data`
  - current status: blocked by FinMind free account level.

Latest derivative import command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-finmind python3 fetch_finmind_chip_data.py \
  --start 2025-01-02 \
  --end 2026-06-12 \
  --datasets derivative_institutional,derivative_large_trader \
  --futures-ids TX \
  --option-ids TXO
```

Latest derivative import result:

- `derivative_institutional`: `3,297` rows written.
  - TX futures institutional: `1,101` rows.
  - TXO options institutional: `2,196` rows.
- `derivative_large_trader`: `0` rows.
  - blocked by FinMind free level.

Latest derivative DB coverage:

| Table | Product | Start | End | Rows |
|---|---|---:|---:|---:|
| derivative_institutional_data | TX | 2025-01-02 | 2026-06-12 | 1,101 |
| derivative_institutional_data | TXO | 2025-01-02 | 2026-06-12 | 2,196 |

Latest `2026-06-12` derivative sample:

| Product | Investor | Metric | Value |
|---|---|---|---:|
| TX | 外資 | net open interest | -65,039 |
| TX | 投信 | net open interest | 57,111 |
| TX | 自營商 | net open interest | 3,568 |
| TXO 買權 | 外資 | net open interest | 2,347 |
| TXO 賣權 | 外資 | net open interest | 5,948 |

Latest foreign-shareholding import result:

- `foreign_shareholding_data`: `1,408` rows.
- Coverage: `2025-01-02 ~ 2026-06-12`.
- Products:
  - `0050.TW`
  - `00631L.TW`
  - `00632R.TW`
  - `00679B.TWO`
- 0050 latest foreign shareholding ratio:
  - `2026-06-12`: `6.35%`

Latest short-pressure / return-index import command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-finmind python3 fetch_finmind_chip_data.py \
  --start 2025-01-02 \
  --end 2026-06-12 \
  --datasets per,securities_lending,short_sale_balances,total_return_index,margin_maintenance \
  --tickers 0050,00631L,00632R,00679B \
  --index-ids TAIEX,TPEx
```

Latest short-pressure / return-index import result:

- `securities_lending`: `453` rows written.
- `short_sale_balances`: `1,392` rows written.
- `total_return_index`: `696` rows written.
- `per`: `0` rows; ETF symbols returned no rows.
- `margin_maintenance`: `0` rows; blocked by FinMind free level.

Latest DB coverage:

| Table | Product | Start | End | Rows |
|---|---|---:|---:|---:|
| securities_lending_data | 0050.TW | 2025-02-03 | 2026-06-12 | 148 |
| securities_lending_data | 00631L.TW | 2025-02-17 | 2026-06-12 | 102 |
| securities_lending_data | 00632R.TW | 2025-01-02 | 2026-05-21 | 121 |
| securities_lending_data | 00679B.TWO | 2025-01-16 | 2026-06-11 | 82 |
| short_sale_balance_data | 0050.TW | 2025-01-02 | 2026-06-12 | 348 |
| short_sale_balance_data | 00631L.TW | 2025-01-02 | 2026-06-12 | 348 |
| short_sale_balance_data | 00632R.TW | 2025-01-02 | 2026-06-12 | 348 |
| short_sale_balance_data | 00679B.TWO | 2025-01-02 | 2026-06-12 | 348 |
| total_return_index_data | TAIEX | 2025-01-02 | 2026-06-12 | 348 |
| total_return_index_data | TPEX | 2025-01-02 | 2026-06-12 | 348 |

Latest `2026-06-12` short-pressure sample for 0050:

| Metric | Value |
|---|---:|
| margin short current balance | 1,112,000 |
| SBL short current balance | 150,308,000 |
| SBL short sales | 1,641,000 |

Latest `2026-06-12` total-return index sample:

| Index | Price |
|---|---:|
| TAIEX | 100,933.47 |
| TPEX | 770.19 |

Notes:

- Anonymous FinMind requests may be rate limited.
- Token can be supplied via `FINMIND_API_TOKEN`.
- Large-trader OI datasets require higher FinMind account level.
- Total exchange margin maintenance requires higher FinMind account level.
- ETF symbols currently return no rows for `TaiwanStockPER`.

## Operational Recommendation

Do not full-launch latest GroupA+ as standalone primary strategy.

Recommended production posture:

1. Keep Golden1_0531 as default regime.
2. Use GroupA+ policy adjusted as defensive regime.
3. Use switch rule `switch_deriv_ma20_dd5_score1_hold5`:
   - switch to defensive when 0050 breaks down and derivative risk confirms.
   - switch back after recovery and derivative risk is no longer elevated.
4. Use chip score and short-pressure score as audit / explanation.
5. Run in shadow or partial capital first.

Suggested capital deployment:

- Conservative: 10% live / 90% shadow.
- Moderate: 25% live / 75% Golden-only.
- Do not allocate 100% until switch rule has additional OOS validation.

## Known Limitations

1. Switch backtest is based on static Golden1 and GroupA+ weights.
2. It does not yet include transaction cost on each regime switch.
3. It does not yet include tax/slippage for switch events.
4. It uses local DB chip/derivative data; daily refresh must be automated before production.
5. Chip-confirm rules were tested, but did not improve results.
6. Derivative-confirm improved this window, but needs OOS validation.
7. FinMind large-trader OI and total margin maintenance are blocked by current free account level.
8. ETF PER currently returns no rows.
9. No full PPO retraining was done.
10. No walk-forward optimization of switch thresholds yet.

## Suggested Next Steps

1. Add transaction costs to `backtest_group_a_plus_switch_policy.py`.
2. Add a daily `group_a_plus_switch_decision.py` that outputs:
   - current regime
   - whether to switch today
   - reason codes
   - target signal path
3. Add HTML report for switch backtest and current switch state.
4. Add OOS validation:
   - train/choose switch rule on 2025.
   - validate on 2026.
5. Test wider threshold grid:
   - MA window: 10 / 20 / 40 / 60
   - drawdown window: 10 / 20 / 40
   - entry drawdown: 4% / 5% / 6% / 7%
   - min hold: 3 / 5 / 10
6. Add cost-aware switch scoring:
   - return
   - Sharpe
   - MDD
   - switch count
   - expected transaction drag
7. Add OOS validation for derivative-confirm rules.
8. If a higher FinMind account level is available, import:
   - `TaiwanFuturesOpenInterestLargeTraders`
   - `TaiwanOptionOpenInterestLargeTraders`
   - `TaiwanTotalExchangeMarginMaintenance`
9. Evaluate whether `short_sale_balance_data` should become a hard gate or remain diagnostics.
10. Automate daily FinMind refresh before switch-decision generation.

## Verification Performed

Commands run:

```bash
python3 -m py_compile group_a_plus_decision_policy.py generate_group_a_strategy_compare_html.py group_a_plus_review_pipeline.py backtest_group_a_plus_policy_signal.py
python3 -m py_compile backtest_group_a_plus_switch_policy.py fetch_finmind_chip_data.py
python3 group_a_plus_decision_policy.py
python3 generate_group_a_strategy_compare_html.py
python3 group_a_plus_review_pipeline.py
python3 backtest_group_a_plus_policy_signal.py --start 2025-01-02 --end 2026-06-12 --initial-value 1000000
python3 backtest_group_a_plus_switch_policy.py --start 2025-01-02 --end 2026-06-12 --initial-value 1000000
MPLCONFIGDIR=/tmp/matplotlib-finmind python3 fetch_finmind_chip_data.py --start 2025-01-02 --end 2026-06-12 --datasets derivative_institutional,derivative_large_trader --futures-ids TX --option-ids TXO
MPLCONFIGDIR=/tmp/matplotlib-finmind python3 fetch_finmind_chip_data.py --start 2025-01-02 --end 2026-06-12 --datasets per,securities_lending,short_sale_balances,total_return_index,margin_maintenance --tickers 0050,00631L,00632R,00679B --index-ids TAIEX,TPEx
python3 -m json.tool report/group_a_plus/latest/decision.json
python3 -m json.tool report/group_a_plus/latest/decision_backtest.json
python3 -m json.tool report/group_a_plus/latest/switch_backtest.json
```

All syntax and JSON checks passed.

## Current Bottom Line

Latest practical recommendation:

```text
Use Golden1_0531 as the default strategy.
Use GroupA+ policy adjusted as the defensive regime.
Switch based on 0050 MA20 / 20-day drawdown rule, confirmed by derivative institutional risk.
Keep chip and short-pressure data as diagnostics for now, not a hard gate.
Current regime as of 2026-06-12: GroupA+ defensive.
```
