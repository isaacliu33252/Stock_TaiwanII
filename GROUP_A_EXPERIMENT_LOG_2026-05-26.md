# Group A Experiment Log

Date: 2026-05-26
Status: Detailed experiment record after institutional-data integration and hard-crash-gate research
Scope: Group A only

## 1. Source Of Truth

This note records the full Group A experiment chain that happened after the 2026-05-24 handoff.

It does **not** replace the earlier primary handoff by default. As of 2026-05-26:

- The best recent OOS result inside this experiment set is the `conservative + institutional + DJI + hard crash gate` variant.
- The best `2008` proxy crash reference is still the older defensive cap-0.20 runtime payload from 2026-05-24.
- No single new model should be promoted as the sole production replacement yet, because the recent-window winner did not improve the `2008` crash window.

Primary reference documents and artifacts:

- Previous production/crash reference:
  - [`GROUP_A_LATEST_HANDOFF_2026-05-24.md`](GROUP_A_LATEST_HANDOFF_2026-05-24.md)
  - [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json)
- Clean OOS baseline without institutional features:
  - [`models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_cash50_20260525.zip`](models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_cash50_20260525.zip)
  - [`results/group_a_backtest_20250101_20260525_20260525_234149.json`](results/group_a_backtest_20250101_20260525_20260525_234149.json)
  - [`models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_20260525.zip`](models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_20260525.zip)
  - [`results/group_a_backtest_20250101_20260525_20260525_235629.json`](results/group_a_backtest_20250101_20260525_20260525_235629.json)
- Institutional-feature OOS default variant:
  - [`models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_20260526.zip)
  - [`results/group_a_backtest_20250101_20260525_20260526_011331.json`](results/group_a_backtest_20250101_20260525_20260526_011331.json)
  - [`results/group_a_twii_proxy_2008_20070701_20101231_20260526_035836.json`](results/group_a_twii_proxy_2008_20070701_20101231_20260526_035836.json)
  - [`results/signal_group_a_20260526_035234.json`](results/signal_group_a_20260526_035234.json)
  - [`results/signal_group_a_20260526_035234.csv`](results/signal_group_a_20260526_035234.csv)
- Conservative institutional variants:
  - [`models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_tripletv4_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_tripletv4_20260526.zip)
  - [`results/group_a_backtest_20250101_20260525_20260526_041135.json`](results/group_a_backtest_20250101_20260525_20260526_041135.json)
  - [`results/group_a_twii_proxy_2008_20070701_20101231_20260526_041157.json`](results/group_a_twii_proxy_2008_20070701_20101231_20260526_041157.json)
  - [`models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_tripletv3cash50_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_tripletv3cash50_20260526.zip)
  - [`results/group_a_backtest_20250101_20260525_20260526_042134.json`](results/group_a_backtest_20250101_20260525_20260526_042134.json)
  - [`results/group_a_twii_proxy_2008_20070701_20101231_20260526_042156.json`](results/group_a_twii_proxy_2008_20070701_20101231_20260526_042156.json)
- Hard-crash-gate variants:
  - [`models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_hardgate_tripletv4_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_hardgate_tripletv4_20260526.zip)
  - [`results/group_a_backtest_20250101_20260525_20260526_044653.json`](results/group_a_backtest_20250101_20260525_20260526_044653.json)
  - [`results/group_a_twii_proxy_2008_20070701_20101231_20260526_044710.json`](results/group_a_twii_proxy_2008_20070701_20101231_20260526_044710.json)
  - [`models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_hardgate_force_tripletv4_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_inst_dji_conservative_hardgate_force_tripletv4_20260526.zip)
  - [`results/group_a_backtest_20250101_20260525_20260526_045630.json`](results/group_a_backtest_20250101_20260525_20260526_045630.json)
  - [`results/group_a_twii_proxy_2008_20070701_20101231_20260526_045646.json`](results/group_a_twii_proxy_2008_20070701_20101231_20260526_045646.json)

## 2. Institutional Data Integration

The Group A pipeline now includes TWSE `T86` institutional-flow inputs end to end:

- DB table:
  - `institutional_data` in [`FinRL/data/stock_data.db`](FinRL/data/stock_data.db)
- Loader / trainer / signal integration:
  - [`FinRL/data/stock_db.py`](FinRL/data/stock_db.py)
  - [`train_dual_group_2024_2026.py`](train_dual_group_2024_2026.py)
  - [`generate_dual_group_signal.py`](generate_dual_group_signal.py)
- Regression coverage:
  - [`test_group_a_institutional_features.py`](test_group_a_institutional_features.py)

Current institutional DB status from `python3 FinRL/data/stock_db.py --stats`:

- `Institutional rows in DB = 4,641`

Group A ticker coverage in `institutional_data`:

- `0050.TW`: `1,550` rows, `2020-01-02` to `2026-05-25`
- `00631L.TW`: `1,547` rows, `2020-01-02` to `2026-05-25`
- `00632R.TW`: `1,544` rows, `2020-01-02` to `2026-05-25`

Feature columns enabled for Group A:

- `foreign_net_buy_ratio_5d`
- `investment_trust_net_buy_ratio_5d`
- `dealer_net_buy_ratio_5d`
- `institutional_total_net_buy_ratio_20d`

Important limitation:

- The current institutional history starts in `2020`, so the `2008` proxy tests do **not** validate true historical institutional alpha.
- In practice, the `2008` proxy primarily tests the price/regime logic, PVA logic, inverse-hedge logic, and any crash-gate logic under missing historical non-price context.

## 3. Clean OOS Experiment Matrix

Shared OOS setup for all rows below:

- Train window: `2020-01-01` to `2024-12-31`
- Actual Group A train rows vary by feature merge, but all backtests below use the same requested OOS window
- OOS backtest window: `2025-01-02` to `2026-05-25`
- Initial cash per group: `1,000,000`
- DCA enabled: `0050.TW = 5,000` on day `20`

| Variant | Profile | Action | Final value | Annual return | Sharpe | Max drawdown | Volatility | Trades | PVA |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline no-inst v3 | `default` | `triplet_v3_cash50` | `1,960,950.90` | `66.47%` | `2.3049` | `-23.61%` | `22.35%` | `56` | `24` |
| Baseline no-inst v4 | `default` | `triplet_v4` | `1,973,839.74` | `67.29%` | `2.3169` | `-23.61%` | `22.46%` | `56` | `28` |
| Institutional default | `default` | `triplet_v4` | `2,238,006.24` | `83.98%` | `2.4534` | `-24.16%` | `25.37%` | `56` | `32` |
| Institutional conservative | `conservative` | `triplet_v4` | `2,387,609.67` | `93.21%` | `2.6663` | `-19.15%` | `25.16%` | `24` | `13` |
| Institutional hardgate | `conservative` | `triplet_v4` | `2,442,787.34` | `96.58%` | `2.8277` | `-11.98%` | `24.26%` | `25` | `8` |
| Institutional hardgate + force rebalance | `conservative` | `triplet_v4` | `1,605,972.04` | `43.12%` | `2.5109` | `-12.72%` | `13.87%` | `115` | `0` |

Key OOS deltas:

- `triplet_v4` vs `triplet_v3_cash50` without institutional features:
  - `final_value +12,888.84`
  - `annual_return +0.83 pp`
  - `sharpe +0.0120`
  - `max_drawdown` unchanged
- Institutional default vs no-inst `triplet_v4`:
  - `final_value +264,166.50`
  - `annual_return +16.68 pp`
  - `sharpe +0.1365`
  - `max_drawdown -0.54 pp` worse
- Institutional conservative vs institutional default:
  - `final_value +149,603.43`
  - `annual_return +9.23 pp`
  - `sharpe +0.2129`
  - `max_drawdown +5.01 pp` better
- Institutional hardgate vs institutional conservative:
  - `final_value +55,177.67`
  - `annual_return +3.37 pp`
  - `sharpe +0.1614`
  - `max_drawdown +7.17 pp` better
- Institutional hardgate + force rebalance vs institutional hardgate:
  - `final_value -836,815.29`
  - `annual_return -53.46 pp`
  - `sharpe -0.3168`
  - `trades +90`

Interpretation:

- Action-schema refinement alone was incremental, not structural.
- Institutional features clearly added value in the `2025~2026` OOS window.
- The `conservative` profile was more important than `triplet_v4` vs `triplet_v3_cash50` at this stage.
- The `conservative triplet_v4` and `conservative triplet_v3_cash50` runs produced identical OOS and `2008` proxy outputs, so action-space granularity was not the limiting factor in that branch.
- The force-rebalance experiment should be treated as a rejected branch.

## 4. 2008 Proxy Stress Matrix

Shared crash setup:

- Proxy window: `2007-07-02` to `2010-12-31`
- Synthetic assets:
  - `0050.TW`: `1x` TWII return
  - `00631L.TW`: `2x` TWII return
  - `00632R.TW`: `-1x` TWII return
- Requested start / end:
  - `2007-07-01` to `2010-12-31`

| Variant | Final value | Annual return | Sharpe | Max drawdown | Volatility | Trades | PVA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-24 defensive cap20 reference | `1,525,036.08` | `12.97%` | `0.5395` | `-50.44%` | `24.43%` | `147` | `86` |
| Institutional default | `1,330,534.28` | `8.60%` | `0.3684` | `-54.17%` | `26.54%` | `145` | `83` |
| Institutional conservative | `1,191,199.98` | `5.19%` | `0.2497` | `-59.41%` | `28.22%` | `52` | `31` |
| Institutional hardgate | `1,192,918.12` | `5.23%` | `0.2512` | `-59.72%` | `28.24%` | `53` | `31` |
| Institutional hardgate + force rebalance | `1,126,847.43` | `3.51%` | `0.1905` | `-58.56%` | `27.54%` | `40` | `26` |

Key crash deltas:

- Institutional default vs 2026-05-24 defensive cap20 reference:
  - `final_value -194,501.80`
  - `annual_return -4.37 pp`
  - `sharpe -0.1711`
  - `max_drawdown -3.73 pp` worse
- Institutional conservative vs institutional default:
  - `final_value -139,334.31`
  - `annual_return -3.42 pp`
  - `sharpe -0.1187`
  - `max_drawdown -5.24 pp` worse
- Institutional hardgate vs institutional conservative:
  - `final_value +1,718.14`
  - `annual_return +0.04 pp`
  - `sharpe +0.0015`
  - `max_drawdown -0.31 pp` worse
- Institutional hardgate + force rebalance vs institutional hardgate:
  - `final_value -66,070.69`
  - `annual_return -1.72 pp`
  - `sharpe -0.0606`

Contextual benchmark:

- In the same TWII proxy framework, the `hold_0050` benchmark in the institutional-default crash run finished at `1,003,692.60` with `annual_return 0.11%`, `sharpe 0.0579`, and `max_drawdown -58.31%`.
- So these strategy branches still beat plain `0050` buy-and-hold on proxy final value, but the newer institutional / conservative / hardgate branches did **not** beat the older 2026-05-24 defensive crash reference.

Interpretation:

- The older defensive cap-0.20 runtime payload remains the strongest crash-defense reference.
- The institutional default model improved recent OOS but weakened crash behavior.
- The conservative profile improved recent OOS even more, but weakened crash behavior further.
- The hard crash gate improved recent OOS materially, but did not recover the `2008` crash objective.

## 5. Hard Crash Gate Implementation Record

Hard-crash-gate support was added to:

- [`train_dual_group_2024_2026.py`](train_dual_group_2024_2026.py)
- [`generate_dual_group_signal.py`](generate_dual_group_signal.py)

New Group A controls:

- `--group-a-enable-hard-crash-gate`
- `--group-a-hard-crash-risk-off-cash-floor`
- `--group-a-hard-crash-risk-off-inverse-floor`
- `--group-a-hard-crash-severe-cash-floor`
- `--group-a-hard-crash-severe-inverse-floor`

Implemented behavior:

- When the risk gate sees `risk_off` or `severe` conditions, the hard gate can:
  - zero or reduce leverage exposure,
  - enforce an explicit cash floor,
  - enforce an inverse floor,
  - persist those constraints into payload config for replay and signal generation.
- A second patch also allowed hard-gate events to bypass `min_rebalance_days` through a `force_rebalance` path.

Empirical result:

- The gate worked technically.
- The gate did **not** solve the `2008` crash problem.
- The extra `force_rebalance` logic made the recent OOS branch materially worse and should not be kept as the preferred path.

## 6. Latest Operational Snapshot

The last live-style signal generated in this experiment chain used the institutional-default OOS model:

- Artifact:
  - [`results/signal_group_a_20260526_035234.json`](results/signal_group_a_20260526_035234.json)
  - [`results/signal_group_a_20260526_035234.csv`](results/signal_group_a_20260526_035234.csv)
- Requested signal date:
  - `2026-05-26`
- Actual market data date:
  - `2026-05-25`
- Signal mode:
  - `live_start`
- Signal status:
  - `rebalance`
- Reason:
  - `pva_overlay_j`
- Effective target label:
  - `0050 77.8% / 00631L 12.2% / cash 10%`
- Target shares from the live-start calculation used at that time:
  - `0050.TW = 7,791`
  - `00631L.TW = 3,552`
  - `00632R.TW = 0`

Note:

- No fresh signal was promoted from the later `conservative` or `hardgate` branches, because those branches were still under crash-validation review.

## 7. Recommendation

Current decision boundary:

- If the priority is **best recent OOS performance**, the strongest research result in this batch is:
  - `conservative + institutional + DJI + hard crash gate`
- If the priority is **crash-defense continuity**, the safer reference remains:
  - [`results/group_a_twii_proxy_2008_defensive_cap20_20260524.json`](results/group_a_twii_proxy_2008_defensive_cap20_20260524.json)

Recommended interpretation as of 2026-05-26:

- Keep the institutional-feature integration. It is valuable.
- Do not promote the hard-gate branch to sole production status yet.
- Treat the `conservative` and `hardgate` results as evidence that the recent-window policy can be improved, but that the crash-defense gap still sits in earlier regime detection rather than in action-schema tuning or post-trigger flooring alone.

Most likely next research step:

- Add earlier regime detection or a more structural de-risking trigger, instead of repeating more `triplet_v3/v4` or floor-parameter micro-sweeps.

## 8. Reproduction Notes

Representative commands used in this experiment chain:

Backfill institutional data:

```bash
python3 FinRL/data/stock_db.py \
  --add-institutional 0050.TW,00631L.TW,00632R.TW \
  --start 2020-01-01 \
  --end 2026-05-25
```

Institutional default clean OOS:

```bash
python3 train_dual_group_2024_2026.py \
  --group-filter group_a \
  --train-start 2020-01-01 \
  --train-end 2024-12-31 \
  --backtest-start 2025-01-01 \
  --backtest-end 2026-05-25 \
  --download-end 2026-05-25 \
  --timesteps 100000 \
  --seed 42 \
  --group-a-model-name group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_20260526 \
  --group-a-profile default \
  --group-a-action-schema triplet_v4 \
  --group-a-00631l-max-weight 0.20 \
  --group-a-00632r-max-weight 0.30 \
  --group-a-enable-dca \
  --group-a-dca-day 20 \
  --group-a-dca-0050 5000 \
  --group-a-enable-llm-sentiment \
  --group-a-llm-sentiment-path FinRL/data/sentiment/llm_market_sentiment_daily.csv \
  --group-a-enable-pva-sigmoid \
  --group-a-pva-weight 0.32 \
  --group-a-pva-j-state-weight 0.19 \
  --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 \
  --group-a-pva-s-state-drift-boost 0.0 \
  --group-a-pva-s-state-max-weight 0.32 \
  --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 \
  --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-inverse-max-hold-days 5 \
  --group-a-enable-institutional
```

Conservative hardgate clean OOS:

```bash
python3 train_dual_group_2024_2026.py \
  --group-filter group_a \
  --train-start 2020-01-01 \
  --train-end 2024-12-31 \
  --backtest-start 2025-01-01 \
  --backtest-end 2026-05-25 \
  --download-end 2026-05-25 \
  --timesteps 100000 \
  --seed 42 \
  --group-a-model-name group_a_oos_2020_2024_cap20_inst_dji_conservative_hardgate_tripletv4_20260526 \
  --group-a-profile conservative \
  --group-a-action-schema triplet_v4 \
  --group-a-enable-dca \
  --group-a-dca-day 20 \
  --group-a-dca-0050 5000 \
  --group-a-enable-llm-sentiment \
  --group-a-llm-sentiment-path FinRL/data/sentiment/llm_market_sentiment_daily.csv \
  --group-a-enable-institutional \
  --group-a-enable-hard-crash-gate \
  --group-a-hard-crash-risk-off-cash-floor 0.30 \
  --group-a-hard-crash-risk-off-inverse-floor 0.15 \
  --group-a-hard-crash-severe-cash-floor 0.50 \
  --group-a-hard-crash-severe-inverse-floor 0.30 \
  --group-a-enable-pva-sigmoid \
  --group-a-pva-weight 0.32 \
  --group-a-pva-j-state-weight 0.19 \
  --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 \
  --group-a-pva-s-state-drift-boost 0.0 \
  --group-a-pva-s-state-max-weight 0.32 \
  --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 \
  --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-00631l-max-weight 0.20 \
  --group-a-00632r-max-weight 0.30 \
  --group-a-inverse-max-hold-days 5
```

Run the `2008` proxy stress test against any saved payload:

```bash
python3 backtest_group_a_twii_proxy_2008.py \
  --payload <payload_json> \
  --start 2007-07-01 \
  --end 2010-12-31
```

## 2026-05-26 Shared Margin Regime Experiment

Goal: replace noisy per-ticker ETF margin inputs with a shared basket-level margin regime signal for `group A`.

Code integration:

- Added `GROUP_A_MARGIN_SHARED_FEATURE_COLUMNS` in `train_dual_group_2024_2026.py`
- Added `attach_group_a_margin_shared_features_db_first(...)`
- Added payload gate `payload_uses_group_a_margin_shared_features(...)`
- Added CLI flag `--group-a-enable-margin-shared`
- Added signal/proxy support in `generate_dual_group_signal.py` and `backtest_group_a_twii_proxy_2008.py`
- Added regression smoke `test_group_a_margin_shared_features.py`

Shared margin feature set:

- `group_a_shared_margin_balance_utilization`
- `group_a_shared_short_balance_utilization`
- `group_a_shared_margin_flow_ratio_5d`
- `group_a_shared_short_flow_ratio_5d`
- `group_a_shared_short_margin_balance_ratio`
- `group_a_shared_margin_balance_growth_z_20d`

Implementation note:

- This is not full-market TWSE financing breadth yet.
- Current version aggregates `0050.TW / 00631L.TW / 00632R.TW` daily margin and short data into one shared regime block, then feeds it as shared state.
- It is still cleaner than per-ticker ETF margin slots, but should be treated as a basket-level proxy rather than true market-wide financing breadth.

Artifacts:

- OOS payload/result: `results/group_a_backtest_20250101_20260525_20260526_132125.json`
- OOS model: `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_marginshared_20260526.zip`
- `2008` proxy: `results/group_a_twii_proxy_2008_20070701_20101231_20260526_132207.json`

OOS comparison (`2025-01-02 ~ 2026-05-25`):

| Variant | Final value | Annual return | Sharpe | Max drawdown | Volatility | Trades | PVA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Institutional only | 2,238,006.24 | 83.98% | 2.4534 | -24.16% | 25.37% | 56 | 32 |
| Institutional + per-ticker margin | 2,102,199.73 | 75.46% | 2.1681 | -28.63% | 26.68% | 56 | 28 |
| Institutional + shared margin | 2,104,672.11 | 75.62% | 2.2693 | -26.15% | 25.38% | 56 | 31 |

`2008` proxy comparison (`2007-07-02 ~ 2010-12-31`):

| Variant | Final value | Annual return | Sharpe | Max drawdown | Volatility | Trades | PVA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Institutional only | 1,330,534.28 | 8.60% | 0.3684 | -54.17% | 26.54% | 145 | 83 |
| Institutional + per-ticker margin | 1,262,781.38 | 6.98% | 0.3149 | -52.57% | 24.96% | 149 | 88 |
| Institutional + shared margin | 1,230,896.22 | 6.19% | 0.2839 | -55.17% | 26.14% | 128 | 75 |

Interpretation:

- Shared margin is better than per-ticker margin on recent OOS quality:
  - `final_value +2,472.38`
  - `sharpe +0.1012`
  - `max_drawdown +2.48 pp`
  - `volatility -1.30 pp`
- But shared margin is still clearly worse than institutional-only:
  - `final_value -133,334.13`
  - `annual_return -8.36 pp`
  - `sharpe -0.1842`
  - `max_drawdown -1.99 pp`
- In `2008` proxy, shared margin is the weakest of the three on return/Sharpe and also slightly worse than institutional-only on drawdown.

Conclusion:

- If margin data is used at all, the shared basket-level version is preferable to per-ticker ETF margin slots.
- But neither margin variant currently beats the institutional-only branch.
- Mainline `group A` should remain institutional-only unless a later version brings in genuine market-wide financing breadth rather than ETF-basket proxy data.

Repro command:

```bash
python3 train_dual_group_2024_2026.py \
  --group-filter group_a \
  --train-start 2020-01-01 \
  --train-end 2024-12-31 \
  --backtest-start 2025-01-01 \
  --backtest-end 2026-05-25 \
  --download-end 2026-05-25 \
  --timesteps 100000 \
  --seed 42 \
  --group-a-model-name group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_marginshared_20260526 \
  --group-a-profile default \
  --group-a-action-schema triplet_v4 \
  --group-a-00631l-max-weight 0.20 \
  --group-a-00632r-max-weight 0.30 \
  --group-a-enable-dca \
  --group-a-dca-day 20 \
  --group-a-dca-0050 5000 \
  --group-a-enable-llm-sentiment \
  --group-a-llm-sentiment-path FinRL/data/sentiment/llm_market_sentiment_daily.csv \
  --group-a-enable-pva-sigmoid \
  --group-a-pva-weight 0.32 \
  --group-a-pva-j-state-weight 0.19 \
  --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 \
  --group-a-pva-s-state-drift-boost 0.0 \
  --group-a-pva-s-state-max-weight 0.32 \
  --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 \
  --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-inverse-max-hold-days 5 \
  --group-a-enable-institutional \
  --group-a-enable-margin-shared
```

## 2026-05-26 Market-Wide Margin Regime Experiment

Goal: replace ETF-basket margin proxy with real TWSE market-level margin aggregates.

Code / data changes:

- Added `market_margin_data` table in `FinRL/data/stock_db.py`
- Added `query_market_margin_data()` and `--add-market-margin`
- Added `GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS`
- Added `attach_group_a_market_margin_shared_features_db_first(...)`
- Added payload gate `payload_uses_group_a_market_margin_shared_features(...)`
- Added CLI flag `--group-a-enable-market-margin`
- Added regression smoke `test_group_a_market_margin_shared_features.py`

Coverage:

- `market_margin_data` rows in DB: `2425`
- Recent training window available: `2020-01-02 ~ 2026-05-25`
- `2008 proxy` window available: `2007-07-02 ~ 2010-12-31`

Market-level feature set:

- `group_a_market_margin_balance_utilization`
- `group_a_market_short_balance_utilization`
- `group_a_market_short_margin_balance_ratio`
- `group_a_market_margin_flow_to_balance_5d`
- `group_a_market_short_flow_to_balance_5d`
- `group_a_market_margin_balance_growth_z_20d`
- `group_a_market_short_balance_growth_z_20d`

Artifacts:

- OOS payload/result: `results/group_a_backtest_20250101_20260525_20260526_162421.json`
- OOS model: `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_marketmargin_20260526.zip`
- `2008` proxy: `results/group_a_twii_proxy_2008_20070701_20101231_20260526_162439.json`

Comparison summary:

| Variant | OOS Final | OOS Sharpe | OOS MDD | `2008` Final | `2008` Sharpe | `2008` MDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Institutional only | 2,238,006.24 | 2.4534 | -24.16% | 1,330,534.28 | 0.3684 | -54.17% |
| Institutional + per-ticker margin | 2,102,199.73 | 2.1681 | -28.63% | 1,262,781.38 | 0.3149 | -52.57% |
| Institutional + basket shared margin | 2,104,672.11 | 2.2693 | -26.15% | 1,230,896.22 | 0.2839 | -55.17% |
| Institutional + market-wide margin | 2,124,309.59 | 2.3638 | -24.44% | 1,150,170.63 | 0.2059 | -54.04% |

Interpretation:

- Market-wide margin is the best of the three margin variants on recent OOS:
  - vs per-ticker margin: `final_value +22,109.87`, `sharpe +0.1957`, `MDD +4.18 pp`
  - vs basket shared margin: `final_value +19,637.48`, `sharpe +0.0946`, `MDD +1.70 pp`
- It still does not beat institutional-only on recent OOS:
  - `final_value -113,696.65`
  - `annual_return -7.12 pp`
  - `sharpe -0.0896`
- In `2008` proxy it is the weakest on return / Sharpe, although drawdown is marginally shallower than institutional-only:
  - `MDD -54.04%` vs `-54.17%`

Conclusion:

- If margin data stays in the design, market-wide TWSE aggregation is the correct direction.
- But even real market-wide margin breadth still does not justify replacing the institutional-only main branch.
- Current evidence says:
  - `institutional-only` remains the best deployable mainline
  - `market-wide margin` is a useful research branch, but not yet a promotion candidate

## 2026-05-26 Market-Wide Margin Gate Experiment

Goal: keep `institutional-only` as the main PPO feature set, but weakly integrate TWSE market-wide margin data as a gate-only shared state for `group A`.

Code / logic changes:

- Added `PortfolioEnv.hidden_shared_feature_cols` so gate-only shared columns can stay in the panel but stay out of the PPO observation
- Added `PortfolioEnv._market_margin_snapshot()` and Group A market-margin gate handling inside `_apply_risk_gate()`
- Added CLI flag `--group-a-enable-market-margin-gate`
- Added payload config `group_a_market_margin_gate_config`
- Updated `generate_dual_group_signal.py` to reconstruct gate-only hidden shared columns from payload
- Extended `test_group_a_market_margin_shared_features.py` with gate-only payload / env smoke coverage

Gate defaults used in this run:

- risk-off triggers when at least 2 of these fire:
  - `market_margin_flow_to_balance_5d <= -0.020`
  - `market_short_flow_to_balance_5d >= 0.100`
  - `market_margin_balance_growth_z_20d <= -0.75`
  - `market_short_balance_growth_z_20d >= 0.75`
- severe triggers on stricter combinations:
  - margin flow `<= -0.035`
  - short flow `>= 0.160`
  - margin growth z `<= -1.25`
  - short growth z `>= 1.50`
- action policy:
  - risk-off: zero `00631L` first
  - severe: force `cash >= 20%` and `00632R >= 10%`

Artifacts:

- OOS payload/result: `results/group_a_backtest_20250101_20260525_20260526_182613.json`
- OOS model: `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_marketmargingate_20260526.zip`
- `2008` proxy: `results/group_a_twii_proxy_2008_20070701_20101231_20260526_182631.json`

Results:

| Variant | OOS Final | OOS Sharpe | OOS MDD | OOS Trades | `2008` Final | `2008` Sharpe | `2008` MDD | `2008` Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Institutional only | 2,238,006.24 | 2.4534 | -24.16% | 56 | 1,330,534.28 | 0.3684 | -54.17% | 145 |
| Institutional + market-wide margin feature | 2,124,309.59 | 2.3638 | -24.44% | 56 | 1,150,170.63 | 0.2059 | -54.04% | 146 |
| Institutional + market-wide margin gate | 2,038,923.83 | 2.3433 | -22.96% | 90 | 1,183,257.37 | 0.2394 | -55.73% | 259 |

Interpretation:

- Versus institutional-only, the gate version is worse on recent OOS:
  - `final_value -199,082.41`
  - `annual_return -12.52 pp`
  - `sharpe -0.1102`
  - `MDD +1.20 pp` improvement
  - `trades +34`
- Versus the market-wide margin feature version, the gate version is also worse on OOS:
  - `final_value -85,385.76`
  - `annual_return -5.41 pp`
  - `sharpe -0.0206`
  - `MDD +1.49 pp` improvement
- In `2008` proxy, the gate version is slightly better than the market-wide feature version on return / Sharpe:
  - `final_value +33,086.74`
  - `annual_return +0.86 pp`
  - `sharpe +0.0335`
- But it is still clearly worse than institutional-only and even deepens drawdown:
  - `final_value -147,276.91`
  - `annual_return -3.62 pp`
  - `sharpe -0.1289`
  - `MDD -1.56 pp`

Conclusion:

- Market-wide margin works better as a weak gate than as a direct alpha feature only on one narrow axis: it modestly improves `2008` return / Sharpe versus the direct market-margin feature branch.
- That improvement is not enough to justify promotion:
  - recent OOS is weaker than both `institutional-only` and `market-wide margin feature`
  - `2008` drawdown still worsens versus `institutional-only`
- Current status remains:
  - `institutional-only` is still the mainline
  - `market-wide margin gate` is recorded as a useful negative result, not a deployment candidate

## 2026-05-26 Local TWII/0050 Regime Gate + Defensive Template Switch

Goal: combine the two highest-priority improvement ideas into one clean OOS branch:

1. add an earlier local `TWII/0050` regime detector
2. switch from the primary `institutional-only` PPO output into defensive templates during risk-off / severe states

Implementation note:

- This branch does **not** swap in the older non-OOS defensive checkpoint.
- It keeps the clean `2020~2024` OOS training standard and only adds a rule-layer template switch on top of the new institutional-only branch.
- That makes the comparison cleaner: the recent OOS and `2008` proxy changes come from the local regime layer, not from mixing checkpoints with different training windows.

Code / logic changes:

- Added Group A local regime gate defaults, CLI flags, payload config, and env wiring in `train_dual_group_2024_2026.py`
- Added early local panel features:
  - `0050_close_ma60_ratio`
  - `0050_drawdown_20`
  - `0050_drawdown_60`
  - `0050_volatility_20`
  - `0050_volatility_20_z`
  - `0050_return_5d_raw`
  - `twse_index_return_5d_raw`
- Added `PortfolioEnv._local_regime_snapshot()` with hysteresis and recovery streak logic
- Added template switch inside `_apply_risk_gate()`:
  - risk-off template: `0050_only`
  - severe template: `0050_70_00632R_30`
- Added signal/payload reconstruction support in `generate_dual_group_signal.py`
- Added regression smoke in `test_group_a_local_regime_gate.py`

Local gate defaults used in this run:

- `risk_off_score_threshold = 2`
- `severe_score_threshold = 3`
- `risk_off_clear_days = 3`
- `severe_clear_days = 4`
- `recovery_ma60_ratio = 1.01`
- `recovery_momentum_21 = 0.01`
- `recovery_drawdown_20 = -0.03`
- `recovery_twse_return_5d = 0.0`
- `risk_off_template = 0050_only`
- `severe_template = 0050_70_00632R_30`

Artifacts:

- OOS payload/result: `results/group_a_backtest_20250101_20260525_20260526_193252.json`
- OOS model: `models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip`
- `2008` proxy: `results/group_a_twii_proxy_2008_20070701_20101231_20260526_193325.json`

Results:

| Variant | OOS Final | OOS Sharpe | OOS MDD | OOS Vol | OOS Trades | `2008` Final | `2008` Sharpe | `2008` MDD | `2008` Vol | `2008` Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Institutional only | 2,238,006.24 | 2.4534 | -24.16% | 25.37% | 56 | 1,330,534.28 | 0.3684 | -54.17% | 26.54% | 145 |
| Local regime + template switch | 2,058,975.61 | 2.3039 | -24.99% | 24.15% | 63 | 1,494,398.92 | 0.5724 | -38.02% | 20.43% | 310 |
| Old defensive cap20 crash reference | n/a | n/a | n/a | n/a | n/a | 1,525,036.08 | 0.5395 | -50.44% | 24.43% | 147 |

Comparison versus institutional-only on recent OOS (`2025-01-02 ~ 2026-05-25`):

- `final_value -179,030.63`
- `annual_return -11.25 pp`
- `sharpe -0.1495`
- `MDD -0.84 pp` worse
- `volatility -1.22 pp`
- `trades +7`
- `PVA -8`

Comparison versus institutional-only on `2008` proxy (`2007-07-02 ~ 2010-12-31`):

- `final_value +163,864.64`
- `annual_return +3.71 pp`
- `sharpe +0.2041`
- `MDD +16.15 pp` improvement
- `volatility -6.10 pp`
- `trades +165`
- `PVA -40`

Comparison versus old defensive cap20 crash reference on `2008` proxy:

- `final_value -30,637.16`
- `annual_return -0.66 pp`
- `sharpe +0.0329`
- `MDD +12.42 pp` improvement
- `volatility -4.00 pp`
- `trades +163`
- `PVA -43`

Interpretation:

- This is the first post-`institutional-only` branch that materially improves the crash window instead of just shifting recent OOS.
- The cost is clear: recent OOS gets worse.
- The crash improvement is also meaningful, not cosmetic:
  - `2008` proxy Sharpe rises above both `institutional-only` and the old defensive cap20 reference
  - `2008` proxy MDD compresses from `-54.17%` to `-38.02%`
  - realized volatility also drops materially
- The trade count roughly doubles in `2008` proxy, so this behavior is more active and more template-driven than the mainline branch.

Conclusion:

- `institutional-only` remains the best mainline for recent OOS performance.
- `local regime + template switch` is the strongest crash-defense branch tested so far under the clean OOS standard.
- It should be treated as a risk-control branch or switching overlay candidate, not a direct replacement for the institutional-only mainline.
