# 2604.09060v2 AEGIS-lite Shadow Backtest — GroupA+ Handoff

Date: 2026-08-13  
Author note: Codex 2026-08-13

## Status

Completed.  The AEGIS paper was reviewed, a research-only AEGIS-lite advisory
and shadow backtest/sweep were implemented, and all variants were tested.

Final decision: **do not promote to active GroupA+ latest strategy**.

No production artifact was changed:

- `golden1_0531` unchanged.
- `report/group_a_plus/latest/strategy.json` unchanged.
- production live pointers unchanged.
- no orders created.

## Source Paper

Source file reviewed:

`C:\Users\isaac\Downloads\2604.09060v2.pdf`

Paper title:

`Taming the Black Swan: A Momentum-Gated Hierarchical Optimisation Framework for Asymmetric Alpha Generation`

Paper framework:

- VAM: volatility-adjusted momentum, roughly `return / realized volatility`.
- Minimax correlation: greedy construction of a large, low-correlation basket.
- SLSQP Sortino optimizer: constrained allocation using downside deviation.

Existing review:

`docs/HANDOFF_2604_09060_AEGIS_MOMENTUM_MINIMAX_CORRELATION_GROUPA_PLUS_20260813.md`

That earlier review correctly concluded that the paper's minimax-correlation
basket construction does **not** transfer to GroupA+, because GroupA+ has a
small, highly collinear tradable universe, not a large cross-sectional equity
candidate pool.

## What Was Implemented

Only the transferable parts were implemented as research-only diagnostics:

1. VAM gate for 00631L adds:
   - computes rolling VAM for `0050.TW` and `00631L.TW`;
   - flags 00631L add risk when `00631L` VAM is below `0050`, non-positive,
     or realized-volatility ratio is too high.

2. Constrained Sortino reference allocation:
   - uses SLSQP over `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`, `cash`;
   - uses a 3-month or configurable lookback;
   - constrained near active weights with max absolute deviation;
   - output is advisory/reference only.

3. Shadow replay/backtest:
   - baseline is GroupA+ latest strategy historical target weights;
   - shadow variants modify those weights research-only;
   - replay includes transaction costs.

4. Full variant sweep:
   - `VAM-only`;
   - `Sortino-only`;
   - `VAM+Sortino`;
   - 63d / 126d lookback variants;
   - monthly and daily Sortino re-optimization.

Minimax correlation was intentionally **not** implemented.

## Files Added

Implementation:

- `scripts/evaluate/build_group_a_plus_aegis_lite_advisory.py`
- `scripts/evaluate/backtest_group_a_plus_aegis_lite_shadow.py`
- `scripts/evaluate/sweep_group_a_plus_aegis_lite_shadow.py`

Tests:

- `tests/test_build_group_a_plus_aegis_lite_advisory.py`
- `tests/test_backtest_group_a_plus_aegis_lite_shadow.py`
- `tests/test_sweep_group_a_plus_aegis_lite_shadow.py`

Reports produced:

- `report/group_a_plus/latest/aegis_lite_advisory.json`
- `report/group_a_plus/latest/aegis_lite_advisory.md`
- `report/group_a_plus/latest/aegis_lite_shadow_backtest.md`
- `report/group_a_plus/latest/aegis_lite_shadow_sweep.md`
- `results/group_a_plus_aegis_lite_shadow_backtest_latest.json`
- `results/group_a_plus_aegis_lite_shadow_backtest_curve_latest.csv`
- `results/group_a_plus_aegis_lite_shadow_sweep_latest.json`
- `results/group_a_plus_aegis_lite_shadow_sweep_latest.csv`

History output:

- `report/group_a_plus/aegis_lite_advisory/history/aegis_lite_advisory_20260813.json`
- `report/group_a_plus/aegis_lite_advisory/history/aegis_lite_advisory_20260813.md`

## Single-Day Advisory Result

Command run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_aegis_lite_advisory.py \
  --as-of 2026-08-13 \
  --end 2026-08-13
```

Output:

- `report/group_a_plus/latest/aegis_lite_advisory.json`
- `report/group_a_plus/latest/aegis_lite_advisory.md`

Result:

- advisory status: `review_00631l_adds`
- VAM gate: `does_not_support_00631l_add`
- reason: `00631L_vam_below_0050`
- VAM 0050: `1.3803240597577204`
- VAM 00631L: `1.2320071025816643`
- 00631L/0050 realized-volatility ratio: `1.9773551278241632`
- Sortino base: `2.1452683926157894`
- Sortino reference: `2.423171219990557`
- Sortino reference weight:
  - `0050.TW`: `0.3800000001460466`
  - `00631L.TW`: near `0`
  - `00632R.TW`: `0.14999999998301097`
  - `00679B.TWO`: `0.06901734038140098`
  - `cash`: `0.4009826594784476`

Interpretation:

The single-day advisory was conservative and did not support new 00631L adds.
This is only a diagnostic; it does not affect active execution.

## Single Variant Backtest Result

Command run:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_aegis_lite_shadow.py \
  --start 2025-01-02 \
  --end 2026-08-13 \
  --initial-value 1000000
```

Output:

- `results/group_a_plus_aegis_lite_shadow_backtest_latest.json`
- `results/group_a_plus_aegis_lite_shadow_backtest_curve_latest.csv`
- `report/group_a_plus/latest/aegis_lite_shadow_backtest.md`

Window:

- `2025-01-02` to `2026-08-13`
- 391 rows
- initial value: `1,000,000`

Baseline latest strategy:

- final value: `1,723,054.8498421307`
- annual return: `0.4021120874497399`
- Sharpe: `1.8324699485769995`
- Sortino: `1.9238327987241137`
- max drawdown: `-0.141071352180828`

AEGIS-lite shadow:

- final value: `1,295,469.7993410814`
- annual return: `0.17445627223566484`
- Sharpe: `1.7603612755747644`
- Sortino: `1.8025889234415327`
- max drawdown: `-0.13515923355449944`

Delta shadow minus baseline:

- final value: `-427,585.05050104926`
- annual return: `-0.22765581521407507`
- Sharpe: `-0.07210867300223511`
- Sortino: `-0.12124387528258107`
- max drawdown: `+0.005912118626328566`

Execution activity:

- baseline rebalances: `7`
- shadow rebalances: `14`
- baseline transaction cost: `10,004.903161846196`
- shadow transaction cost: `11,015.304821816635`
- VAM block days: `152`
- Sortino updates: `18`

Interpretation:

The default `VAM+Sortino` shadow slightly reduced maximum drawdown by about
0.59 percentage points, but the final value and Sortino were materially worse.
This fails promotion.

## Full Sweep Result

Command run:

```bash
.venv/bin/python scripts/evaluate/sweep_group_a_plus_aegis_lite_shadow.py \
  --start 2025-01-02 \
  --end 2026-08-13 \
  --initial-value 1000000
```

Output:

- `results/group_a_plus_aegis_lite_shadow_sweep_latest.json`
- `results/group_a_plus_aegis_lite_shadow_sweep_latest.csv`
- `report/group_a_plus/latest/aegis_lite_shadow_sweep.md`

All swept variants failed promotion.

Ranked results:

| Rank | Variant | Final Delta | Sortino Delta | Sharpe Delta | MaxDD Delta | Promotion |
|---:|---|---:|---:|---:|---:|---|
| 1 | `vam_only_126d` | `-157830.51` | `-0.023072` | `-0.002815` | `0.004248` | `False` |
| 2 | `vam_only_63d` | `-197284.17` | `-0.050241` | `-0.051897` | `0.004248` | `False` |
| 3 | `vam63_sortino63_monthly` | `-407711.91` | `-0.079982` | `-0.038165` | `0.005912` | `False` |
| 4 | `vam126_sortino63_monthly` | `-427585.05` | `-0.121244` | `-0.072109` | `0.005912` | `False` |
| 5 | `vam126_sortino126_monthly` | `-372038.47` | `-0.093619` | `-0.101939` | `-0.009856` | `False` |
| 6 | `sortino_only_126d_monthly` | `-411874.53` | `-0.253726` | `-0.236438` | `-0.009856` | `False` |
| 7 | `sortino_only_63d_monthly` | `-472928.60` | `-0.356655` | `-0.264892` | `0.005912` | `False` |
| 8 | `vam126_sortino63_daily` | `-503389.81` | `-0.621359` | `-0.489718` | `0.034460` | `False` |

Best variant:

- `vam_only_126d`
- final value delta: `-157,830.50629071612`
- Sortino delta: `-0.023072488039265204`
- max drawdown delta: `+0.004247891664243442`

Even the best variant loses substantial return and has worse Sortino.

## Decision

Do **not** promote AEGIS-lite to active GroupA+ latest strategy.

Reasons:

1. No variant improved final value.
2. No variant improved Sortino.
3. VAM-only variants reduce drawdown slightly, but the return drag is too large.
4. Sortino variants perform worse, especially daily Sortino re-optimization.
5. Daily Sortino creates excessive turnover/rebalances and the largest loss.

This should remain research-only.

## Verification

Tests run:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_aegis_lite_advisory.py \
  tests/test_backtest_group_a_plus_aegis_lite_shadow.py \
  tests/test_sweep_group_a_plus_aegis_lite_shadow.py \
  -q
```

Result:

`9 passed in 9.30s`

Compile check:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/backtest_group_a_plus_aegis_lite_shadow.py \
  scripts/evaluate/sweep_group_a_plus_aegis_lite_shadow.py \
  scripts/evaluate/build_group_a_plus_aegis_lite_advisory.py
```

Result:

passed.

## Re-Run Commands

Single-day advisory:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_aegis_lite_advisory.py \
  --as-of 2026-08-13 \
  --end 2026-08-13
```

Default AEGIS-lite shadow backtest:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_aegis_lite_shadow.py \
  --start 2025-01-02 \
  --end 2026-08-13 \
  --initial-value 1000000
```

Full sweep:

```bash
.venv/bin/python scripts/evaluate/sweep_group_a_plus_aegis_lite_shadow.py \
  --start 2025-01-02 \
  --end 2026-08-13 \
  --initial-value 1000000
```

## Operational Warning

Do not wire these scripts into active daily execution.

Acceptable uses:

- daily advisory report;
- research dashboard;
- promotion-gate input;
- future comparison if the tradable universe expands.

Not acceptable without a new explicit promotion review:

- changing `report/group_a_plus/latest/strategy.json`;
- changing `a2118.py` active weights;
- changing golden1 weights;
- applying AEGIS-lite reference weights to execution plans;
- adding minimax-correlation selection to current GroupA+ universe.

## Final Conclusion

AEGIS is a sound paper for large-universe cross-sectional momentum stock
selection, but its core minimax mechanism still does not fit GroupA+.

The reduced AEGIS-lite pieces were tested anyway.  They did not pass.

Keep AEGIS-lite as research-only and do not deploy.
