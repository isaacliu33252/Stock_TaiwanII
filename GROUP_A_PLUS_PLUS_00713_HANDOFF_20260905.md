# GroupA++ 00713 Cash Sleeve Handoff - 2026-09-05

## Decision

Implemented GroupA++ as the latest GroupA+ family extension by adding `00713.TW` (元大台灣高息低波) as a cash-funded sleeve.

- Active runner remains `a2118_a2111_ncf_late_bull_deleverage`.
- Latest strategy manifest enables `group_a_plusplus_00713_cash_sleeve_weight = 0.05`.
- Funding source is cash only. The change does not reduce `0050.TW` or `00631L.TW`.
- `00632R.TW` remains zero by default under the separate inverse-ETF discipline guard.

## Current 2026-09-07 1M Target

Built from data through `2026-09-04`.

| Asset | Weight | Reference shares | Price |
|---|---:|---:|---:|
| 0050.TW | 52.6954% | 4,883 | 107.90 |
| 00631L.TW | 17.3046% | 4,722 | 36.64 |
| 00632R.TW | 0.0000% | 0 | 9.81 |
| 00679B.TWO | 0.0000% | 0 | 25.78 |
| 00713.TW | 5.0000% | 788 | 63.45 |
| cash | 25.0000% | - | - |

Estimated cash after rounding before costs: `250111.61`.

## Backtest Check

Compared the same a2118 parameters with 00713 sleeve off (`0%`) versus on (`5%`), initial value `1,000,000`.

| Window | Base final | GroupA++ final | Delta final | Delta Sharpe | Delta MDD |
|---|---:|---:|---:|---:|---:|
| 2020-01-02 to 2026-09-04 | 4,869,221.10 | 5,069,688.97 | +200,467.88 | +0.0194 | +0.0705pp |
| 2024-01-02 to 2026-09-04 | 2,870,685.54 | 2,910,387.97 | +39,702.43 | +0.0064 | -0.2014pp |
| 2025-01-02 to 2026-09-04 | 2,123,517.09 | 2,142,999.02 | +19,481.93 | +0.0056 | +0.0613pp |
| 2026-05-01 to 2026-09-04 | 1,078,963.73 | 1,089,808.14 | +10,844.41 | +0.0981 | +0.0419pp |

Interpretation: 00713 5% cash sleeve improved final value in all checked windows and improved Sharpe in all checked windows. The only measured drawback was a small max-drawdown deterioration in the 2024-2026 window.

## Files Changed

- `backtest_group_a_plus_policy_signal.py`: added `00713.TW` to the GroupA+/GroupA++ tradable ticker tuple.
- `config/group_a_plus_watchlist.json`: renamed watchlist config to GroupA++ and added 00713 news keywords.
- `group_a_plus/runners/a2118.py`: added `_add_00713_cash_sleeve()` and the manifest-controlled `group_a_plusplus_00713_cash_sleeve_weight` runner parameter.
- `group_a_plus/operations/daily_signal.py`: fixed ticker freshness SQL placeholders to support dynamic ticker counts and surfaced `strategy_family` / `group_a_plusplus_extension`.
- `report/group_a_plus/latest/strategy.json`: enabled `group_a_plusplus_00713_cash_sleeve_weight = 0.05`.
- `report/group_a_plus/latest/live_signal.json`: regenerated latest pointer with GroupA++ 00713 target.

## Validation

- `python3 -m py_compile backtest_group_a_plus_policy_signal.py group_a_plus/runners/a2118.py group_a_plus/runners/latest.py group_a_plus/operations/daily_signal.py group_a_plus/operations/execution_plan.py`
- `.venv/bin/python -m group_a_plus.runners.latest --start 2026-05-01 --end 2026-09-04 --initial-value 1000000 --output results/group_a_plusplus_runner_latest_20260904.json --frame-output results/group_a_plusplus_runner_latest_20260904_frame.csv`
- `.venv/bin/python -m group_a_plus.operations.daily_signal --as-of 2026-09-07 --portfolio-value 1000000 --output results/group_a_plusplus_live_signal_v2_20260907.json --latest-pointer report/group_a_plus/latest/live_signal.json`
- `python3 -m pytest tests/test_run_ncf_daily_pipeline.py -q` -> `23 passed, 5 warnings`

## Source Comparison Follow-Up

Added `scripts/evaluate/build_group_a_plusplus_strategy_source_comparison.py` and generated:

- `report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.json`
- `report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.md`
- `report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.xlsx`

Conclusion: GroupA++ can run with `golden1_0531`, `golden2_0830`, and latest strategy in the same review surface, but order execution should use `groupA++_latest_strategy`. `golden2_0830` remains research-only because `report/group_a_plus/latest/golden2_multi_window_gate.json` is `research_only_no_multi_window_pass` with pass ratio `2/4`.

`git diff --check` still reports pre-existing trailing whitespace in `FinRL/data/technical_indicators.py` and `FinRL/v2/environments/taiwan_stock_env.py`; none are from this GroupA++ change set.

## 2026-09-05 Late Update - NCF_00713 Gate And 10% Sleeve

User requested `建立ncf_00713`, then approved adding the NCF signal into
GroupA++ latest strategy, and finally changed the full 00713 sleeve from 5%
to 10%.

### Final Decision

- `ncf_00713` is now an actual daily NCF artifact, not only a manual idea.
- Latest GroupA++ strategy now uses `00713.TW` as a cash-funded sleeve with
  `group_a_plusplus_00713_cash_sleeve_weight = 0.10`.
- `group_a_plusplus_00713_ncf_enabled = true` is enabled in latest strategy.
- The NCF gate only resizes the 00713 sleeve against `cash`.
- It must not reduce `0050.TW`, `00631L.TW`, `00632R.TW`, or `00679B.TWO`.
- If the 00713 NCF signal is missing while the gate is enabled, the current
  implementation keeps the base sleeve instead of failing open to zero; this is
  intentional to avoid accidental deactivation from an artifact outage.

### NCF_00713 Artifact Creation

Created `scripts/misc/ncf_00713.py` as a wrapper around the existing standard
ETF NCF pipeline (`scripts.misc.ncf_0050`) with:

- `base.TICKER = "00713.TW"`
- default output pattern `results/ncf_00713_YYYYMMDD.json`
- project root inserted into `sys.path` so the script can be launched directly
  from `scripts/misc/`.

Manual run used:

```bash
.venv/bin/python scripts/misc/ncf_00713.py \
  --train-start 2017-09-19 \
  --val-start 2025-01-01 \
  --val-end latest \
  --output results/ncf_00713_latest_20260907.json \
  --val-predictions-output results/ncf_00713_panel_latest_20260907.csv \
  --full-panel \
  --no-tabnet
```

Generated:

- `results/ncf_00713_latest_20260907.json`
- `results/ncf_00713_panel_latest_20260907.csv`

Model/data summary:

- ticker: `00713.TW`
- raw rows: `2179`
- raw data range: `2017-09-19` to `2026-09-04`
- live signal date: `2026-09-04`
- H1: return `-0.02%`, predicted price `63.44`, direction `DOWN`, prob `0.3439`
- H5: return `+0.35%`, predicted price `63.67`, direction `UP`, prob `0.5943`
- H20: return `+1.91%`, predicted price `64.66`, direction `UP`, prob `0.7864`
- ensemble direction: `UP`
- ensemble calibrated probability up: `0.5554`
- ensemble weighted return: `+0.1143%`
- confidence: `0.3983` (low-confidence warning)
- forward 20d MDD >5% probability: `0.050065`
- forward 20d gain >5% probability: `0.160081`

### Pipeline / Archive Integration

Updated `scripts/run/run_ncf_daily_pipeline.py`:

- added `commands["ncf_00713"]`
- added CLI argument `--train-start-00713`, default `2017-09-19`
- added 00713 panel to `build_ncf_panel_manifest.py --panels`
- added 00713 result and panel paths to the daily pipeline summary
- added 00713 to the NCF signal summary block
- honors `--no-external-features` for 00713 as well

Updated `scripts/evaluate/append_ncf_signal_archive.py`:

- added `ncf_00713_latest_{stamp}.json` to dated sources
- added `ncf_00713_latest_` to backfill discovery
- updated help text to include `{00631l,00632r,00713}`

Updated `group_a_plus/operations/ops_health.py`:

- added `ncf_00713` to `MODULE_OUTPUT_PATTERNS`

Generated/updated:

- `results/ncf_panel_manifest_20260907.json`
  - panel count: `5`
  - combined hash:
    `95432766a74a5e5ea749f850e22287c4d24aae2e370240d651629bffb28eb03b`
- `results/ncf_signal_archive.jsonl`
  - appended latest `00713.TW` row
  - archive row contains H1/H5/H20 probabilities and blend probabilities

### Strategy Integration

Updated `group_a_plus/integrations/ncf.py`:

- added `ncf_00713_cash_sleeve_decision()`
- decision output includes:
  - status
  - base weight
  - scale
  - effective weight
  - cash released
  - reason
  - signal date / actual date
  - probability, confidence, drawdown risk, upside reward
  - thresholds

Default NCF gate thresholds:

- full sleeve if `calibrated_prob_up >= 0.54`
- half/partial sleeve zone starts at `calibrated_prob_up >= 0.50`
- confidence minimum: `0.30`
- max allowed 20d MDD >5% probability: `0.20`
- minimum 20d gain >5% probability: `0.08`

Current live 00713 decision for data date `2026-09-04`:

```json
{
  "status": "applied",
  "base_weight": 0.1,
  "scale": 1.0,
  "effective_weight": 0.1,
  "cash_released": 0.0,
  "reason": "full_sleeve_allowed",
  "signal_date": "2026-09-04",
  "actual_date": "2026-09-04",
  "direction": "UP",
  "calibrated_prob_up": 0.5554,
  "confidence": 0.3983,
  "prob_fwd_mdd_gt5_h20": 0.050065,
  "prob_fwd_gain_gt5_h20": 0.160081
}
```

Updated `group_a_plus/runners/a2118.py`:

- imports `ncf_00713_cash_sleeve_decision`
- added `_resize_00713_cash_sleeve()` to move only between `00713.TW` and
  `cash`
- added `ncf_00713_path` runner parameter
- added `group_a_plusplus_00713_ncf_enabled` runner parameter
- resolves latest `ncf_00713` automatically if explicit path is omitted
- writes the decision under:
  `report["group_a_plusplus_extension"]["ncf_sleeve_decision"]`
- runner `live_weights` now reflects the NCF-adjusted 00713 sleeve

Updated `group_a_plus/operations/daily_signal.py`:

- imports `ncf_00713_cash_sleeve_decision`
- added `_resize_00713_cash_sleeve()`
- added `_apply_00713_ncf_sleeve()`
- final live signal `target_weights` now uses the 00713 NCF decision after
  existing high-risk and TSMC weakness trims
- adds the final decision under:
  `ncf_live_overlay["ncf_00713_sleeve"]`

Updated `report/group_a_plus/latest/strategy.json`:

```json
"ncf_00713_path": "results/ncf_00713_latest_20260907.json",
"group_a_plusplus_00713_cash_sleeve_weight": 0.10,
"group_a_plusplus_00713_ncf_enabled": true
```

### 5% Versus 10% Check

Backtest-like comparison using the same current latest strategy parameters and
only changing `group_a_plusplus_00713_cash_sleeve_weight`.

2020-01-02 to 2026-09-08:

- 5% final value: `5,080,475`
- 10% final value: `5,289,571`
- delta: `+209,096`
- annual return: `27.58%` to `28.36%`
- max drawdown: `-22.39%` to `-22.31%`

2024-01-02 to 2026-09-08:

- delta final value: `+42,028`
- annual return delta: about `+0.80pp`
- max drawdown changed by about `-0.19pp` (slightly worse)

2025-01-02 to 2026-09-08:

- delta final value: `+19,533`
- annual return delta: about `+0.86pp`
- max drawdown changed by about `+0.06pp` (slightly better)

Interpretation: 10% had a positive return impact in these checks. Risk impact
was small because this is funded from cash and does not increase the 0050/00631L
main exposure.

### 2026-09-08 1M Output After 10% Change

Generated:

- `results/group_a_plusplus_live_signal_v2_predict_20260908_from_20260904_total1000000_ncf00713_10pct.json`
- latest pointer:
  `results/group_a_plusplus_live_signal_v2_latest_ncf00713.json`
- point-in-time snapshot:
  `results/ncf_snapshots/2026/09/04/a2118_a2111_ncf_late_bull_deleverage_20260905T235125_5e29e91ee770.json`

Signal:

- requested as-of: `2026-09-08`
- actual data date: `2026-09-04`
- execution allowed: `True`
- strategy family: `groupA++`
- 00713 NCF decision: `full_sleeve_allowed`

Target weights / values for `1,000,000`:

| Asset | Weight | Target value | Reference shares |
|---|---:|---:|---:|
| 0050.TW | 52.6954% | 526,954 | 4,883 |
| 00631L.TW | 17.3046% | 173,046 | 4,722 |
| 00632R.TW | 0.0000% | 0 | 0 |
| 00679B.TWO | 0.0000% | 0 | 0 |
| 00713.TW | 10.0000% | 100,000 | 1,576 |
| cash | 20.0000% | 200,000 | - |

### Validation Commands Run

```bash
python3 -m py_compile \
  scripts/misc/ncf_00713.py \
  scripts/evaluate/append_ncf_signal_archive.py \
  scripts/run/run_ncf_daily_pipeline.py \
  group_a_plus/operations/ops_health.py
```

```bash
python3 -m py_compile \
  group_a_plus/integrations/ncf.py \
  group_a_plus/runners/a2118.py \
  group_a_plus/operations/daily_signal.py
```

```bash
git diff --check -- \
  report/group_a_plus/latest/strategy.json \
  group_a_plus/integrations/ncf.py \
  group_a_plus/runners/a2118.py \
  group_a_plus/operations/daily_signal.py
```

```bash
.venv/bin/python group_a_plus/operations/daily_signal.py \
  --as-of 2026-09-08 \
  --portfolio-value 1000000 \
  --max-business-stale-days 3 \
  --lookback-days 260 \
  --output results/group_a_plusplus_live_signal_v2_predict_20260908_from_20260904_total1000000_ncf00713_10pct.json \
  --latest-pointer results/group_a_plusplus_live_signal_v2_latest_ncf00713.json
```

All above validation completed successfully in this session.

### Important Caveats

- Historical backtests above compare fixed 00713 sleeve weights. The new
  `ncf_00713` gate is currently a live/latest-signal gate, not a full
  historical point-in-time 00713 panel gate.
- A true historical NCF-gated 00713 backtest would require applying
  `results/ncf_00713_panel_latest_20260907.csv` row-by-row through the
  historical simulation.
- Current `ncf_00713` confidence is only `0.3983`; it passes the gate but should
  not be treated as a high-conviction alpha source.
- The practical interpretation remains: 00713 is a cash enhancer sleeve, not a
  core risk-on allocation.

## 2026-09-06 Follow-Up - Historical NCF-Gated Backtest

User asked whether GroupA++ needs retraining, then requested continuation. The
answer was: no immediate main-strategy retrain is required, but the previously
noted caveat should be tested by applying `ncf_00713_panel_latest_20260907.csv`
row-by-row in a historical replay.

### Evaluator Added

Created:

- `scripts/evaluate/backtest_group_a_plusplus_00713_ncf_gate.py`

Generated:

- `report/group_a_plus/latest/group_a_plusplus_00713_ncf_gate_backtest.json`
- `report/group_a_plus/latest/group_a_plusplus_00713_ncf_gate_backtest.md`
- `results/group_a_plusplus_00713_ncf_gate_backtest_curves.csv`

Method:

- replays latest `a2118` execution regimes
- compares fixed 00713 sleeves: 0%, 5%, 10%
- compares `gated_10pct_delay1`
- uses `ncf_00713_panel_latest_20260907.csv`
- applies a 1-trading-day signal delay so day t allocation uses the prior
  available NCF panel row, avoiding same-day close look-ahead
- uses existing `_simulate_costed_curve()` share-tracked simulator and existing
  transaction-cost assumptions

### Initial Finding And Gate Refinement

The first live gate design was too sensitive because low confidence alone could
halve the 00713 sleeve. In the 2025-2026 NCF panel window it changed 188/407
days and hurt final value by about `-154,989` versus fixed 10%, despite improving
Sharpe/MDD. That was not acceptable for a cash-enhancer sleeve.

Refined `ncf_00713_cash_sleeve_decision()`:

- low confidence now records `low_confidence_no_cut`
- low confidence alone no longer reduces 00713
- probability cuts require confirmed confidence
- high tail drawdown risk can still cut
- stale/missing NCF keeps the base sleeve rather than accidentally zeroing it

### Refined Historical Gate Result

Using the refined gate and 1-trading-day delay:

Summary:

- windows tested: `2`
- gated beats fixed 10% final-value windows: `1/2`
- gated beats fixed 10% Sharpe windows: `1/2`
- gated non-worse MDD windows: `2/2`
- average final-value delta versus fixed 10%: `-3,708.76`

Window `2025-01-02` to `2026-09-04`:

| Variant | Final value | Annual return | Sharpe | MDD | Rebalances | Cost |
|---|---:|---:|---:|---:|---:|---:|
| fixed 0% | 2,123,517.09 | 56.98% | 2.0530 | -16.44% | 7 | 9,090.98 |
| fixed 5% | 2,142,999.02 | 57.84% | 2.0585 | -16.38% | 7 | 9,270.06 |
| fixed 10% | 2,162,531.53 | 58.70% | 2.0625 | -16.32% | 7 | 9,451.31 |
| gated 10% delay1 | 2,155,111.50 | 58.37% | 2.0493 | -16.32% | 26 | 13,439.31 |

Delta `gated 10% delay1` versus fixed 10%:

- final value: `-7,420.03`
- annual return: `-0.33pp`
- Sharpe: `-0.0132`
- MDD: `0.0000`
- extra rebalances: `+19`
- extra cost: `+3,888.00`
- gate changed days: `20/407`
- mean effective 00713 weight: `9.6314%`

Window `2026-05-01` to `2026-09-04`:

| Variant | Final value | Annual return | Sharpe | MDD | Rebalances | Cost |
|---|---:|---:|---:|---:|---:|---:|
| fixed 0% | 1,078,963.73 | 25.32% | 0.9494 | -13.12% | 4 | 3,673.33 |
| fixed 5% | 1,089,808.14 | 29.10% | 1.0469 | -13.07% | 4 | 3,794.70 |
| fixed 10% | 1,100,693.73 | 32.96% | 1.1414 | -13.03% | 4 | 3,914.02 |
| gated 10% delay1 | 1,100,696.23 | 32.96% | 1.1414 | -13.03% | 4 | 3,912.93 |

Delta `gated 10% delay1` versus fixed 10%:

- final value: `+2.51`
- annual return: `0.00pp`
- Sharpe: `0.0000`
- MDD: `0.0000`
- gate changed days: `1/89`
- mean effective 00713 weight: `10.0000%`

### Current Practical Decision

- Keep GroupA++ 00713 base sleeve at 10%.
- Keep the live `ncf_00713` gate enabled, but with the refined conservative
  behavior.
- Do not claim the historical NCF gate improves returns yet; the refined gate is
  best interpreted as an emergency risk valve / diagnostic guard.
- No immediate main-strategy retrain is required.
- A future true promotion would require:
  - more NCF_00713 panel history than the current 2025-2026 window
  - threshold sweep with transaction costs
  - multi-window validation
  - comparison against fixed 10% as the benchmark, not only against 0% or 5%

### Validation Run 2026-09-06

```bash
python3 -m py_compile \
  group_a_plus/integrations/ncf.py \
  scripts/evaluate/backtest_group_a_plusplus_00713_ncf_gate.py
```

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plusplus_00713_ncf_gate.py
```

```bash
.venv/bin/python group_a_plus/operations/daily_signal.py \
  --as-of 2026-09-08 \
  --portfolio-value 1000000 \
  --max-business-stale-days 3 \
  --lookback-days 260 \
  --output results/group_a_plusplus_live_signal_v2_predict_20260908_from_20260904_total1000000_ncf00713_10pct.json \
  --latest-pointer results/group_a_plusplus_live_signal_v2_latest_ncf00713.json
```

All completed successfully.

## 2026-09-06 Follow-Up - Golden1 / Golden2 / Latest GroupA++ 2026-09-08 Prediction

User requested:

> 在groupA++,使用golden1_0531 ,golden2_0830 及最新策略,以1百萬, 預測9/8

Important naming note:

- No `golden1_0530` artifact was found in the repository.
- The valid baseline release name is `golden1_0531`.

### Artifacts Generated

Three GroupA++-style predictions/comparisons were generated for `2026-09-08`,
using portfolio value `1,000,000` and actual market data through `2026-09-04`.

Source runs:

- `results/group_a_plusplus_golden1_0531_override_runner_20260908.json`
- `results/group_a_plusplus_golden1_0531_override_frame_20260908.csv`
- `results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260908.json`
- `results/golden2_0830/group_a_plusplus_golden2_0830_override_frame_20260908.csv`
- `results/group_a_plusplus_live_signal_v2_predict_20260908_from_20260904_total1000000_ncf00713_10pct.json`

Comparison outputs:

- `report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260908.json`
- `report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260908.md`
- `report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260908.xlsx`

### Common Inputs

- actual data date: `2026-09-04`
- requested prediction date: `2026-09-08`
- portfolio value: `1,000,000`
- 00713 sleeve: `10%`
- `ncf_00713` source: `results/ncf_00713_latest_20260907.json`
- `ncf_00713` decision for all three variants: `full_sleeve_allowed`
- 00713 effective weight for all three variants: `10%`

`ncf_00713` live inputs:

- direction: `UP`
- calibrated probability up: `0.5554`
- confidence: `0.3983`
- forward 20d MDD >5% probability: `0.050065`
- forward 20d gain >5% probability: `0.160081`

### Three-Way 2026-09-08 Result

| Source | 0050.TW | 00631L.TW | 00632R.TW | 00679B.TWO | 00713.TW | cash |
|---|---:|---:|---:|---:|---:|---:|
| golden1_0531 GroupA++ | 69.1629% | 10.8371% | 0.0000% | 0.0000% | 10.0000% | 10.0000% |
| golden2_0830 GroupA++ what-if | 47.0000% | 10.1039% | 16.4782% | 0.0000% | 10.0000% | 16.4179% |
| latest GroupA++ | 52.6954% | 17.3046% | 0.0000% | 0.0000% | 10.0000% | 20.0000% |

Reference shares using the common latest prices:

| Source | 0050.TW | 00631L.TW | 00632R.TW | 00679B.TWO | 00713.TW |
|---|---:|---:|---:|---:|---:|
| golden1_0531 GroupA++ | 6,409 | 2,957 | 0 | 0 | 1,576 |
| golden2_0830 GroupA++ what-if | 4,355 | 2,757 | 16,797 | 0 | 1,576 |
| latest GroupA++ | 4,883 | 4,722 | 0 | 0 | 1,576 |

### How Each Variant Was Run

`golden1_0531 GroupA++` was run by pinning:

- `golden_signal_path_override = results/signal_group_a_golden1_0531_predict_20260707_from_20260706_total1000000.json`
- `ncf_panel_631l_path = results/ncf_00631l_panel_latest_20260907.csv`
- `ncf_00713_path = results/ncf_00713_latest_20260907.json`
- `group_a_plusplus_00713_cash_sleeve_weight = 0.10`
- `group_a_plusplus_00713_ncf_enabled = true`

`golden2_0830 GroupA++ what-if` was run by pinning:

- `golden_signal_path_override = results/golden2_0830/signal_group_a_golden2_0830_20260831.json`
- `ncf_panel_631l_path = results/golden2_0830/ncf_00631l_panel_golden2_0830.csv`
- `ncf_00713_path = results/ncf_00713_latest_20260907.json`
- `group_a_plusplus_00713_cash_sleeve_weight = 0.10`
- `group_a_plusplus_00713_ncf_enabled = true`

`latest GroupA++` was run through the active latest strategy manifest:

- `report/group_a_plus/latest/strategy.json`
- `group_a_plusplus_00713_cash_sleeve_weight = 0.10`
- `group_a_plusplus_00713_ncf_enabled = true`

### Decision

- Use `latest GroupA++` for orders.
- Treat `golden1_0531 GroupA++` as a pinned research comparator.
- Treat `golden2_0830 GroupA++ what-if` as a frozen-release comparator only.
- Do not modify the frozen `golden2_0830` release files.
- The golden2 what-if includes `00632R.TW = 16.4782%`; this comes from the
  frozen golden2 signal's PVA hedge leg and should not be confused with the
  current latest GroupA++ execution source.

### Validation Run 2026-09-06

```bash
python3 -m py_compile \
  group_a_plus/runners/a2118.py \
  group_a_plus/integrations/ncf.py \
  group_a_plus/operations/daily_signal.py \
  scripts/evaluate/backtest_group_a_plusplus_00713_ncf_gate.py
```

```bash
git diff --check -- \
  group_a_plus/runners/a2118.py \
  group_a_plus/integrations/ncf.py \
  group_a_plus/operations/daily_signal.py \
  scripts/evaluate/backtest_group_a_plusplus_00713_ncf_gate.py \
  GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md
```

Both completed successfully.

## 2026-09-06 Follow-Up - Sleeve Weight Changed From 10% To 12%

User asked for a fixed-weight comparison across candidates (10% baseline, then
15%, then 12%), including an isolated COVID-crash check, then decided to set
the live sleeve weight to 12%.

### Method

Same fixed-weight comparison as the 5%-vs-10% check earlier in this document
(`run_a2118()` with `group_a_plusplus_00713_ncf_enabled=False` to isolate the
sleeve-weight effect from the live NCF gate, holding every other production
parameter fixed), extended to two additional window sets:

1. The same 4 standard windows used for the 5%-vs-10% check
   (2020-01-02, 2024-01-02, 2025-01-02, 2026-05-01, all through 2026-09-04).
2. Two COVID-specific windows, added because none of the 4 standard windows
   contain an isolated severe-crash episode: `covid_2020` full calendar year
   (2020-01-02 to 2020-12-31) and the tighter crash-to-recovery episode alone
   (2020-01-31 to 2020-06-01, matching the `_stress_episodes()` boundary used
   elsewhere in this codebase).

### 10% vs 15% (4 standard windows)

| Window | 10% final | 15% final | Delta final | Delta Sharpe | Delta MDD (pp) |
|---|---:|---:|---:|---:|---:|
| 2020-01-02 to 2026-09-04 | 5,289,571 | 5,503,544 | +213,973 | +0.0160 | +0.07 |
| 2024-01-02 to 2026-09-04 | 2,954,458 | 2,971,349 | +42,312 | +0.0056 | -0.19 |
| 2025-01-02 to 2026-09-04 | 2,162,532 | 2,182,114 | +19,583 | +0.0025 | +0.06 |
| 2026-05-01 to 2026-09-04 | 1,100,694 | 1,111,621 | +10,927 | +0.0916 | +0.04 |

15% beat 10% on final value and Sharpe in all 4 windows; MDD was mixed and
small in magnitude.

### 10% vs 15% (COVID-specific windows) -- the trend reverses under real crash stress

| Window | Variant | Final value | Sharpe | MDD |
|---|---|---:|---:|---:|
| covid_2020 full year | 0% | 1,285,414 | 1.8148 | -14.64% |
| covid_2020 full year | 10% | 1,297,750 | 1.7676 | -17.03% |
| covid_2020 full year | 15% | 1,303,886 | 1.7421 | -18.22% |
| crash episode only (01-31 to 06-01) | 0% | 970,828 | -0.7018 | -11.45% |
| crash episode only (01-31 to 06-01) | 10% | 969,422 | -0.5964 | -13.83% |
| crash episode only (01-31 to 06-01) | 15% | 968,716 | -0.5516 | -15.03% |

Isolating the crash-only episode (excluding the subsequent V-shaped recovery)
shows the sleeve weight's cost clearly: higher 00713 weight monotonically
worsens both final value and MDD during the actual drawdown, because 00713
is real (if lower) equity beta funded out of what would otherwise be pure,
zero-beta cash. The full-year 2020 number looks favorable only because the
subsequent recovery more than offsets the worse drawdown -- the 4 standard
windows never isolate a crash-without-recovery-yet period, which is why they
showed a uniformly positive trend. **The "higher weight is strictly better"
pattern from the 5%/10%/15% comparisons does not extend into an actual crash
and should not be read as generalizing indefinitely.**

### 12% vs 10% (all 6 windows) -- the actual decision point

| Window | 10% final | 12% final | Delta final | Delta Sharpe | Delta MDD (pp) |
|---|---:|---:|---:|---:|---:|
| 2020-01-02 to 2026-09-04 | 5,289,571 | 5,374,574 | +85,002 | +0.0067 | +0.03 |
| 2024-01-02 to 2026-09-04 | 2,954,458 | 2,971,349 | +16,891 | +0.0024 | -0.08 |
| 2025-01-02 to 2026-09-04 | 2,162,532 | 2,170,359 | +7,827 | +0.0012 | +0.02 |
| 2026-05-01 to 2026-09-04 | 1,100,694 | 1,105,059 | +4,366 | +0.0370 | +0.02 |
| covid_2020 full year | 1,297,750 | 1,300,207 | +2,457 | -0.0101 | -0.48 |
| covid crash episode only | 969,422 | 969,140 | -282 | +0.0185 | -0.48 |

12% sits roughly at half the 15% gain in the calm windows and roughly 40% of
15%'s MDD cost in the crash episode (-0.48pp vs -1.20pp) -- a middle ground
between the 10% baseline and the more aggressive 15% option.

### Decision

Set `group_a_plusplus_00713_cash_sleeve_weight = 0.12` in
`report/group_a_plus/latest/strategy.json` (`active_strategy.runner_params`),
replacing the prior 0.10. `group_a_plusplus_00713_ncf_enabled` remains `true`
and unchanged -- the NCF gate scales this new 12% base weight the same way
it scaled the prior 10% base weight; nothing about the gate itself changed.

This is a deliberate, informed trade-off (accepted after seeing the crash-
period MDD cost above), not a "12% is strictly better" claim the way 5%->10%
and 10%->15% looked in the 4 calm standard windows alone.

### Files Changed

- `report/group_a_plus/latest/strategy.json`: `group_a_plusplus_00713_cash_sleeve_weight` 0.10 -> 0.12.

### Note On A Process Mistake This Session

An earlier what-if run in this session (a 1.5M-total, GroupA++-only-tickers
scenario for a 2026-09-07 prediction) was executed via
`group_a_plus.operations.execution_plan` with only `--output` redirected and
`--latest-pointer` left at its default -- which silently overwrote the real
`report/group_a_plus/latest/execution_plan.json` with the hypothetical
scenario's holdings/cash/target. Caught immediately from the tool's own
printed "Latest pointer: report/group_a_plus/latest/execution_plan.json"
line, and restored from the auto-generated `execution_plan.json.bak`
(pre-existing pattern; see `feedback_execution_plan_latest_pointer_default_overwrite`
project memory from 2026-07-27/28 documenting the same failure mode). All
subsequent what-if runs in this session explicitly set both `--output` and
`--latest-pointer` to scratch paths. This note is left here as a second,
independent confirmation of that memory's guidance, in case the memory
record is ever pruned.

## 2026-09-06 Follow-Up - 2609.02014 Spectral 00679B Hedge Review

User asked to analyze `C:\Users\isaac\Downloads\2609.02014.pdf` for
Deep hedging / conditional elicitability / spectral risk measure ideas that
could improve GroupA++ latest strategy, especially 00679B as a hedge.

### Paper Takeaways Imported

The useful import is the risk objective and validation discipline, not the
full option-hedging actor-critic system:

- dynamic / time-consistent CVaR: evaluate short-horizon risk along the path,
  not only terminal wealth;
- spectral tail loss: combine multiple tail depths instead of relying on one
  Sharpe/MDD number;
- scoring-function lesson: tail-sensitive objectives are useful at moderate
  confidence levels, but can become unstable at extreme tails when samples are
  scarce;
- hedge usefulness must be measured after costs and in the actual action
  space.

Not imported into production:

- no live actor-critic allocator;
- no basket-option pricing surrogate;
- no DCC-GARCH simulator;
- no automatic 00679B target-weight change.

### New Shadow Evaluator

Added:

- `scripts/evaluate/build_group_a_plusplus_2609_02014_spectral_00679b_hedge_review.py`

Generated:

- `report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.md`
- `report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.json`

The evaluator runs current GroupA++ via `run_a2118()` and tests whether adding
a cash-funded 00679B sleeve improves:

`spectral_loss = 0.50 * ES95 + 0.30 * ES97.5 + 0.20 * ES99`

Tested variants:

- base latest GroupA++;
- static 00679B sleeves: 5%, 10%, 15%, 20%, funded only from available cash;
- dynamic spectral-min-loss sleeve: causal rolling lookback, candidates
  0/5/10/15/20%;
- conditional-correlation sleeves: 5% and 10%, active only when lagged 63-day
  correlation between base strategy and 00679B is <= -0.05 and 00679B's own
  lagged 63-day return is >= -2%.

### Results

Aggregate:

- windows tested: 4
- spectral promotion candidate windows: 1/4
- all windows pass: false

Window table:

| Window | Best spectral variant | Promote? | Base final | Best final | Delta final | Base MDD | Best MDD | Base spectral | Best spectral |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 COVID | static_00679b_05pct | true | 961,215 | 969,616 | +8,402 | -17.51% | -17.19% | 0.0333 | 0.0332 |
| 2022 rate hike | static_00679b_15pct | false | 850,712 | 817,384 | -33,328 | -18.08% | -21.24% | 0.0177 | 0.0173 |
| 2024-2026 live | static_00679b_20pct | false | 2,971,083 | 2,884,913 | -86,170 | -20.94% | -19.80% | 0.0450 | 0.0440 |
| 2025-2026 live | static_00679b_20pct | false | 2,173,785 | 2,135,619 | -38,166 | -16.30% | -16.56% | 0.0435 | 0.0430 |

Conditional-correlation check:

| Window | Variant | Active days | Avg sleeve | Delta final | Delta MDD | Delta spectral |
|---|---|---:|---:|---:|---:|---:|
| 2020 COVID | conditional_corr_00679b_05pct | 50 | 2.17% | +4,796 | -0.10pp | +0.0007 |
| 2020 COVID | conditional_corr_00679b_10pct | 50 | 4.35% | +9,552 | -0.21pp | +0.0017 |
| 2022 rate hike | conditional_corr_00679b_05pct | 42 | 1.04% | -4,527 | -0.44pp | +0.0000 |
| 2022 rate hike | conditional_corr_00679b_10pct | 42 | 2.08% | -9,039 | -0.87pp | +0.0000 |
| 2024-2026 live | conditional_corr_00679b_05pct | 219 | 1.74% | -25,559 | +0.00pp | -0.0001 |
| 2024-2026 live | conditional_corr_00679b_10pct | 219 | 3.48% | -51,009 | -0.00pp | -0.0001 |
| 2025-2026 live | conditional_corr_00679b_05pct | 148 | 1.86% | -7,246 | -0.00pp | -0.0001 |
| 2025-2026 live | conditional_corr_00679b_10pct | 148 | 3.73% | -14,532 | -0.00pp | -0.0001 |

### Decision

Do not add 00679B to the latest GroupA++ production weights.

Reason:

- 00679B helps in the 2020 COVID window, but this is only 1/4 tested windows.
- In 2022 rate-hike stress, 00679B reduces spectral loss slightly only by
  sacrificing final value and worsening MDD materially.
- In 2024-2026 and 2025-2026, 00679B slightly improves spectral loss, but the
  price is large final-value drag.
- The conditional-correlation version reduces the 2022 damage versus static
  sleeves, but still does not clear the promotion bar.

Useful import retained:

- keep the spectral tail scorecard as a research diagnostic for future hedge
  candidates;
- use it before reconsidering 00679B, 00751B, gold ETF, put overlay, or any
  other hedge sleeve;
- do not cite the paper as support for adding 00679B today.

Validation:

- `.venv/bin/python scripts/evaluate/build_group_a_plusplus_2609_02014_spectral_00679b_hedge_review.py`
- `python3 -m py_compile scripts/evaluate/build_group_a_plusplus_2609_02014_spectral_00679b_hedge_review.py`
- `git diff --check -- scripts/evaluate/build_group_a_plusplus_2609_02014_spectral_00679b_hedge_review.py report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.md report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.json GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md`

### 2026-09-06 Continuation - Spectral Profile Sensitivity

Added scoring-function sensitivity inspired by the paper's log/power vs
saturating scoring-function discussion. The evaluator now reports three
spectral profiles:

- `moderate_tail_sensitive`: 50% ES95 + 30% ES97.5 + 20% ES99;
- `deep_tail_sensitive`: 20% ES95 + 30% ES97.5 + 50% ES99;
- `extreme_tail_saturating`: 70% ES95 + 25% ES97.5 + 5% ES99.

Aggregate result:

- `moderate_tail_sensitive`: 1/4 windows pass;
- `deep_tail_sensitive`: 1/4 windows pass;
- `extreme_tail_saturating`: 1/4 windows pass.

This confirms the no-promotion decision is not an artifact of one arbitrary
spectral weighting. 00679B's small spectral-loss improvement in some windows
is still bought with too much final-value drag and/or MDD deterioration.

### 2026-09-06 Continuation - Short-Horizon Dynamic Risk Check

Added a short-horizon check to match the paper's finding that dynamic risk
objectives can be more useful over shorter remaining maturities than terminal
static risk alone. The evaluator now reports 5-day and 20-day rolling spectral
loss deltas versus base GroupA++.

Best-spectral variants by window:

| Window | Best variant | Delta 5d spectral | Delta 20d spectral |
|---|---|---:|---:|
| 2020 COVID | static_00679b_05pct | +0.0035 | -0.0029 |
| 2022 rate hike | static_00679b_15pct | -0.0021 | +0.0012 |
| 2024-2026 live | static_00679b_20pct | -0.0006 | -0.0019 |
| 2025-2026 live | static_00679b_20pct | +0.0003 | +0.0033 |

Negative delta means rolling-horizon spectral loss improved. The short-horizon
evidence is mixed, not promotable:

- 2020 improves 20d but worsens 5d;
- 2022 improves 5d but worsens 20d;
- 2024-2026 improves both 5d and 20d, but with large final-value drag;
- 2025-2026 worsens both 5d and 20d.

This closes another possible positive angle from the paper: even when judging
00679B on short-horizon dynamic risk-to-go rather than terminal metrics, the
benefit is not stable enough to justify production exposure.

### 2026-09-06 Continuation - Block Bootstrap Tail-Sample Stability

Added paired 20-day block bootstrap stability checks for each window's
best-spectral 00679B variant. This addresses the paper's warning that very
tail-sensitive scores can be unstable when extreme-tail samples are scarce.

Bootstrap summary:

| Window | Variant | P(spectral improves) | P(final improves) | P(MDD improves) |
|---|---|---:|---:|---:|
| 2020 COVID | static_00679b_05pct | 60.8% | 91.4% | 74.6% |
| 2022 rate hike | static_00679b_15pct | 67.2% | 1.2% | 2.0% |
| 2024-2026 live | static_00679b_20pct | 96.2% | 20.0% | 58.0% |
| 2025-2026 live | static_00679b_20pct | 76.4% | 25.6% | 22.4% |

Interpretation:

- 00679B's spectral-loss improvement can be statistically visible in some
  windows, especially 2024-2026.
- But final-value improvement is weak or negative in 3/4 windows.
- MDD improvement is also unstable and poor in 2022/2025-2026.
- 2022 remains the structural blocker: the best spectral variant has only
  1.2% bootstrap probability of improving final value and only 2.0% probability
  of improving MDD.

Conclusion unchanged: use this as a diagnostic scorecard, not a production
allocation rule.

### 2026-09-06 Continuation - 00679B Hedge Readiness State

Added a daily 00679B hedge readiness state to the same evaluator. This imports
the paper's state-design idea (price/risk state, previous action, capacity,
and dependence state) in a lightweight diagnostic form:

- 63-day and 126-day correlation between base GroupA++ returns and 00679B;
- 00679B 63-day return;
- 00679B 126-day drawdown;
- base GroupA++ 126-day drawdown;
- base GroupA++ 20-day realized volatility;
- available cash capacity;
- previous dynamic 00679B sleeve.

The readiness score is lagged one day and is diagnostic-only. Levels:

- `high`: score >= 0.70;
- `medium`: score >= 0.45;
- `low`: score < 0.45.

Latest state on the live windows ending 2026-09-04:

| Window | Latest level | Score | Corr63 | Corr126 | 00679B 63d return | 00679B DD126 | Base DD126 | Base vol20 | Cash capacity |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-2026 live | low | 0.2080 | -0.0408 | +0.0664 | -2.90% | -8.17% | -8.94% | 15.77% | 18.00% |
| 2025-2026 live | low | 0.2080 | -0.0408 | +0.0664 | -2.90% | -8.17% | -8.94% | 15.77% | 18.00% |

Interpretation:

- 00679B is not currently a high-readiness hedge.
- 63-day correlation is only slightly negative; 126-day correlation is positive.
- 00679B's own 63-day return is negative and below the conditional-correlation
  gate's -2% threshold.
- Available cash capacity is now 18% because GroupA++ latest strategy currently
  reserves a 12% 00713 sleeve.

This is useful as a daily diagnostic, but still not a production signal.

### 2026-09-06 Continuation - Stress Path Perturbation

Added deterministic stress-path perturbation checks inspired by the paper's
perturbed-path validation setup. For each window's best-spectral 00679B sleeve,
the base GroupA++ return path is held fixed and the 00679B return path is
modified under four scenarios:

- `historical`: actual 00679B returns;
- `negative_corr_hedge`: 00679B rallies mildly when base GroupA++ falls;
- `stock_bond_down`: 2022-like long-duration bond failure, 00679B falls more
  on equity-risk shock days;
- `carry_drag`: small daily bond carry drag.

Key results:

| Window | Scenario | Delta final | Delta MDD | Delta spectral | Delta 20d spectral |
|---|---|---:|---:|---:|---:|
| 2020 COVID | negative_corr_hedge | +13,498 | +0.59pp | -0.0006 | -0.0048 |
| 2020 COVID | stock_bond_down | +2,315 | -0.08pp | +0.0007 | -0.0000 |
| 2022 rate hike | negative_corr_hedge | -14,548 | -1.42pp | -0.0010 | -0.0022 |
| 2022 rate hike | stock_bond_down | -50,123 | -4.78pp | +0.0009 | +0.0042 |
| 2024-2026 live | negative_corr_hedge | +316,177 | +2.24pp | -0.0030 | -0.0127 |
| 2024-2026 live | stock_bond_down | -514,537 | -0.93pp | +0.0031 | +0.0182 |
| 2025-2026 live | negative_corr_hedge | +148,124 | +1.00pp | -0.0024 | -0.0065 |
| 2025-2026 live | stock_bond_down | -243,213 | -2.57pp | +0.0035 | +0.0206 |

Interpretation:

- If 00679B genuinely becomes a negative-correlation hedge, it can help.
- If the market is in a 2022-like stock-bond-down regime, 00679B can be very
  damaging.
- The current 2026-09-04 readiness state is `low`, so the evidence points to
  not opening a 00679B sleeve now.

Decision unchanged: 00679B stays out of production weights; readiness and
stress-path diagnostics remain useful shadow infrastructure.

### 2026-09-07 Continuation - Transaction Cost Sensitivity

Added transaction-cost sensitivity for each window's best-spectral 00679B
sleeve, inspired by the paper's explicit proportional transaction-cost setup.
The check replays the same best-spectral sleeve under 0/10/20/50 bps sleeve
cost assumptions.

Key result:

| Window | Variant | Delta final @0bps | Delta final @20bps | Delta final @50bps | Delta MDD @20bps | Delta spectral @20bps |
|---|---|---:|---:|---:|---:|---:|
| 2020 COVID | static_00679b_05pct | +8,499 | +8,402 | +8,256 | +0.31pp | -0.0001 |
| 2022 rate hike | static_00679b_15pct | -33,083 | -33,328 | -33,696 | -3.16pp | -0.0004 |
| 2024-2026 live | static_00679b_20pct | -82,377 | -86,170 | -91,851 | +1.14pp | -0.0010 |
| 2025-2026 live | static_00679b_20pct | -35,358 | -38,166 | -42,372 | -0.27pp | -0.0005 |

Interpretation:

- Transaction cost is not the root cause of 00679B's failure.
- Even at 0 bps, 00679B still drags final value in 2022, 2024-2026, and
  2025-2026.
- The no-promotion decision is robust to cheaper trading assumptions.

Conclusion unchanged: keep 00679B out of production weights.

### 2026-09-07 Final Confirmation - 00679B Removal Recommendation

User asked whether the recommendation is to remove / keep removed `00679B`.

Confirmed recommendation:

- keep `00679B.TWO` removed from GroupA++ production weights;
- do not add `00679B.TWO` back to latest strategy target allocation;
- keep `00679B.TWO` only in watchlist / shadow diagnostics / readiness
  monitoring.

Reason summary:

- Latest hedge readiness state ending 2026-09-04 is `low` with score `0.2080`.
- 63-day correlation is only slightly negative (`-0.0408`), while 126-day
  correlation is positive (`+0.0664`).
- 00679B's own 63-day return is negative (`-2.90%`), below the conditional
  readiness gate's `-2%` threshold.
- Historical benefit is concentrated in 2020 COVID; only 1/4 main windows
  passed the spectral promotion gate.
- 2022 rate-hike stress remains the structural blocker: the best-spectral
  static 15% sleeve improved spectral loss slightly but lost `33,328` per
  1M and worsened MDD by `3.16pp`.
- 2024-2026 and 2025-2026 showed small spectral-loss reductions, but with
  large final-value drag (`-86,170` and `-38,166` per 1M respectively).
- Bootstrap confirmed the issue is not random noise: in 2022 the best-spectral
  variant had only `1.2%` probability of improving final value and only `2.0%`
  probability of improving MDD.
- Stress-path perturbation confirmed the regime dependency: 00679B helps in a
  true negative-correlation hedge world, but is very damaging in a 2022-like
  stock-bond-down world.
- Transaction-cost sensitivity confirmed cost is not the root cause: even at
  `0 bps`, 00679B still drags final value in 2022, 2024-2026, and 2025-2026.

Operational instruction:

- The active/latest GroupA++ strategy should continue to use `00679B.TWO: 0`.
- Do not cite arXiv 2609.02014 as support for adding 00679B today.
- Reconsider 00679B only if hedge readiness becomes `high` and a fresh
  spectral + bootstrap + stress-path review passes across all required windows.

Artifacts:

- `scripts/evaluate/build_group_a_plusplus_2609_02014_spectral_00679b_hedge_review.py`
- `report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.md`
- `report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.json`
