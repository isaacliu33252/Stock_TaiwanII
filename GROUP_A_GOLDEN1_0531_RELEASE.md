# Group A Production Release: Golden1_0531

Date: 2026-05-31
Status: Production implementation release
Scope: Group A only

## 1. Release Name

The current Group A production implementation strategy is named:

- `Golden1_0531`

This release name identifies the strategy currently executed by:

- [`run_group_a_combined_signal.py`](run_group_a_combined_signal.py)

## 2. Source Of Truth

- Release manifest:
  - [`results/group_a_release_Golden1_0531.json`](results/group_a_release_Golden1_0531.json)
- Model checkpoint:
  - [`models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip`](models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip)
- Full strategy payload:
  - [`results/group_a_backtest_20250101_20260525_20260526_193252.json`](results/group_a_backtest_20250101_20260525_20260526_193252.json)
- Stable latest signal:
  - [`results/group_a_combined_live_latest.json`](results/group_a_combined_live_latest.json)
  - [`results/group_a_combined_live_latest.csv`](results/group_a_combined_live_latest.csv)
- Stable latest bundle:
  - [`results/group_a_combined_bundle_latest.json`](results/group_a_combined_bundle_latest.json)
- Execution history workbook:
  - [`Group_A_history.xlsx`](Group_A_history.xlsx)

## 3. Strategy Stack

- PPO model trained on `2020-01-01` to `2024-12-31`
- OOS evaluation window: `2025-01-02` to `2026-05-25`
- Action schema: `triplet_v4`
- Exposure cap:
  - `00631L.TW = 0.20`
  - `00632R.TW = 0.30`
- Institutional features enabled
- LLM sentiment features and defensive sentiment gate enabled
- PVA/SJM continuous risk-scaling overlay enabled
- Local `TWII / 0050` regime defensive overlay enabled
- DCA evaluation setting: buy `0050.TW = 5,000` on day `20`

Disabled research branches:

- Hard crash gate
- Margin features
- Shared margin features
- Market margin gate
- Market margin shared features

## 4. PVA Runtime Configuration

- `pva_weight = 0.32`
- `pva_j_state_weight = 0.19`
- `pva_m_state_weight = 1.00`
- `pva_drift_threshold = 0.05`
- `pva_target_vol = 0.012`
- `pva_min_leverage_scale = 0.40`
- `pva_inverse_hedge_budget = 0.30`
- `pva_s_state_drift_boost = 0.00`
- `pva_s_state_max_weight = 0.32`
- `pva_buy_dip_strength = 0.95`

## 5. OOS Performance Reference

Source:

- [`results/group_a_backtest_20250101_20260525_20260526_193252.json`](results/group_a_backtest_20250101_20260525_20260526_193252.json)

Metrics:

- Final value: `2,058,975.61`
- Total return: `105.8976%`
- Annual return: `72.7260%`
- Sharpe: `2.303933`
- Max drawdown: `-24.9939%`
- Trades: `63`

## 6. Operational Snapshot

Signal generated for execution on `2026-06-01` using market data through `2026-05-29`:

- Status: `rebalance`
- Reason: `pva_overlay_j`
- Actual holdings source:
  - [`Group_A_history.xlsx`](Group_A_history.xlsx)
- Current shares:
  - `0050.TW = 89`
  - `00631L.TW = 0`
  - `00632R.TW = 0`
- Target allocation:
  - `0050.TW = 58.9243%`
  - `00631L.TW = 11.0757%`
  - `00632R.TW = 0.0000%`
  - `cash = 30.0000%`
- Target shares:
  - `0050.TW = 5,643`
  - `00631L.TW = 3,026`
  - `00632R.TW = 0`

## 7. Execution Command

```bash
python3 run_group_a_combined_signal.py \
  --xlsx Group_A_history.xlsx \
  --override-holdings-json '{"0050":89,"00631L":0,"00632R":0}' \
  --as-of-date 2026-06-01 \
  --download-end 2026-05-29
```

The holdings override is required because `Group_A_history.xlsx` is an execution-history workbook rather than the original dual-group inventory workbook format.

## 8. Three-Month Trial Plan

- Trial start: `2026-06-01`
- Trial end and full review date: `2026-08-31`
- Starting marked-to-market value before initial rebalance fees: `1,009,380.60`
- Estimated initial buy fees: `993.47`
- Estimated post-rebalance starting value: `1,008,387.13`

The review should compare:

- Actual ending total value
- Net external contributions
- Strategy return excluding external contributions
- Maximum drawdown during the trial
- Number of rebalances
- Fees
- Whether the local regime gate or inverse hedge was activated

## 9. Estimated Value On 2026-08-31

The estimate is based on the `Golden1_0531` OOS equity curve from `2025-01-02` to `2026-05-25`.

Method:

- Base estimate: convert the OOS annual return of `72.7260%` into a three-month compounded return of `14.6409%`.
- Historical distribution reference: calculate rolling calendar three-month returns from the OOS equity curve.
- DCA estimate: assume `5,000` is added on the scheduled day in June, July, and August.

| Scenario | Three-month return | Value without new DCA | Value with estimated DCA |
| --- | ---: | ---: | ---: |
| Stress reference: historical 10th percentile | `-14.8008%` | `859,137.73` | `873,371.36` |
| Flat market reference | `0.0000%` | `1,008,387.13` | `1,023,387.13` |
| Base estimate | `14.6409%` | `1,156,023.63` | `1,171,733.45` |
| Historical rolling median | `19.5250%` | `1,205,274.49` | `1,221,212.07` |
| Historical 75th percentile | `23.6539%` | `1,246,909.79` | `1,263,036.72` |

Historical worst rolling three-month observation:

- Return: `-23.2350%`
- Estimated value without new DCA: `774,087.92`

Operational target for the `2026-08-31` review:

- Base estimated total value with scheduled DCA: `1,171,733.45`

This is a planning estimate, not a guaranteed return. The OOS reference period was favorable overall, so the stress range must remain part of the review.

## 10. Improvement Research

Post-release runtime experiments are recorded separately:

- [`GROUP_A_GOLDEN1_0531_IMPROVEMENT_EXPERIMENT.md`](GROUP_A_GOLDEN1_0531_IMPROVEMENT_EXPERIMENT.md)

The production release remains frozen during the three-month trial. The current shadow candidate is:

- `Golden1_0531_shadow_pva036_j015`

It is a research candidate only and must not replace `Golden1_0531` before the `2026-08-31` review.
