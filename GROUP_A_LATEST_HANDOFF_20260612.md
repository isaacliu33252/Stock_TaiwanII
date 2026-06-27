# Group A Latest Strategy Handoff - 2026-06-12

## Current production strategy

Production release:

`latest_group_a_improved_0050_step0300bp_stepgate105_ma60_brake30_631l0_tdcc18`

Stable live files:

- `results/group_a_combined_live_latest.json`
- `results/group_a_combined_live_latest.csv`
- `results/group_a_combined_bundle_latest.json`

Main runner:

- `run_group_a_combined_signal.py`

Signal generator:

- `generate_dual_group_signal.py`

TDCC config:

- `group_a_tdcc_improved_config_destination_primary.json`

## Production logic

Current production pipeline:

1. Group A PPO production model generates base allocation.
2. PVA overlay adjusts base target.
3. 0050 step limiter is available at `3%`.
4. `stepgate105`: if 0050 price is above `MA60 * 1.05`, release the 0050 step limiter.
5. MA60 brake: if 0050 price <= MA60, cap 0050 at `30%`.
6. If MA60 brake is active, cap 00631L at `0%`.
7. TDCC crowding overlay:
   - caution cap for 00631L: `18%`
   - risk_off cap for 00631L: `0%`
   - released 00631L budget goes to 0050

Reason for TDCC cap change:

- Previous caution cap `10%` was too conservative.
- Three-window replay showed `18%` improves full-window and recent-year Final while keeping MDD almost unchanged.
- YTD loses slightly versus cap `10%`, but the difference is small.

## Latest live signal

As-of run date: `2026-06-12`

Actual data date: `2026-06-11`

Signal status: `rebalance`

Signal reason:

`pva_overlay_s; trend_gate_released_0050_step`

Target weights:

| Ticker | Weight |
|---|---:|
| 0050.TW | 59.58% |
| 00631L.TW | 10.42% |
| 00679B.TWO | 0.00% |
| 00632R.TW | 0.00% |
| Cash | 30.00% |

Target shares:

| Ticker | Shares |
|---|---:|
| 0050.TW | 7605 |
| 00631L.TW | 3996 |
| 00679B.TWO | 0 |
| 00632R.TW | 0 |

TDCC state:

- `caution`
- Current 00631L target is `10.42%`, below the new caution cap `18%`.
- Therefore TDCC does not alter the latest live target.

## Comparison with Golden1_0531 latest signal

Both use actual data date `2026-06-11`.

| Item | Golden1_0531 | Latest production tdcc18 | Difference |
|---|---:|---:|---:|
| 0050 | 50.00% | 59.58% | +9.58% |
| 00631L | 20.00% | 10.42% | -9.58% |
| Cash | 30.00% | 30.00% | 0.00% |
| 00679B | 0.00% | 0.00% | 0.00% |
| 00632R | 0.00% | 0.00% | 0.00% |

Shares:

| Ticker | Golden1_0531 | Latest production tdcc18 | Difference |
|---|---:|---:|---:|
| 0050.TW | 6382 | 7605 | +1223 |
| 00631L.TW | 7671 | 3996 | -3675 |
| 00679B.TWO | 0 | 0 | 0 |
| 00632R.TW | 0 | 0 | 0 |

Interpretation:

- Golden1_0531 is more aggressive because it keeps 00631L at `20%`.
- Latest production shifts roughly half of that 00631L exposure into 0050.
- Latest production is designed for lower drawdown and volatility, not maximum Final.

## Backtest / replay comparison

Primary replay window:

`2025-01-02 ~ 2026-06-11`

Latest production replay files:

- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20250102_20260611.json`
- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20250102_20260611.csv`

Recent-year replay:

- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20250602_20260611.json`
- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20250602_20260611.csv`

YTD replay:

- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20260102_20260611.json`
- `results/group_a_latest_stepgate105_tdcc_cap_sweep_small_20260102_20260611.csv`

Full-window comparison:

| Strategy | Final | Sharpe | MDD | Vol |
|---|---:|---:|---:|---:|
| Golden1_0531 base | 2.144M | 2.035 | -29.94% | 0.283 |
| Golden1_0531 + old TDCC | 2.084M | 2.162 | -29.83% | 0.264 |
| latest tdcc18 | 2.056M | 2.864 | -9.43% | 0.190 |
| latest stepgate/MA brake without TDCC | 2.061M | 2.783 | -10.09% | 0.196 |
| Meta best shadow | 2.250M | 2.674 | -17.93% | 0.231 |

Conclusion:

- Golden1_0531 has higher Final than latest production.
- Latest production has much better Sharpe, drawdown, and volatility.
- Meta best shadow has the highest Final, but it is still not promoted due to weaker risk profile and incomplete stress validation for the latest profile.

## TDCC cap sweep result

Compared TDCC caution caps `10%`, `12%`, `15%`, and `18%`.

Full window:

| Cap | Final | Sharpe | MDD | Vol |
|---|---:|---:|---:|---:|
| 10% | 2.009M | 2.844 | -9.39% | 0.185 |
| 12% | 2.024M | 2.849 | -9.42% | 0.187 |
| 15% | 2.041M | 2.856 | -9.43% | 0.188 |
| 18% | 2.056M | 2.864 | -9.43% | 0.190 |

Recent year:

| Cap | Final | Sharpe | MDD |
|---|---:|---:|---:|
| 10% | 2.108M | 3.588 | -10.11% |
| 15% | 2.127M | 3.580 | -10.11% |
| 18% | 2.139M | 3.579 | -10.11% |

YTD:

| Cap | Final | Sharpe | MDD |
|---|---:|---:|---:|
| 10% | 1.501M | 3.285 | -11.32% |
| 15% | 1.500M | 3.277 | -11.33% |
| 18% | 1.500M | 3.277 | -11.33% |

Decision:

- Promote TDCC caution cap `18%`.
- It improves full/recent Final and keeps risk close to cap `10%`.
- YTD is slightly worse, but the loss is small.

## Meta Ensemble status

Meta files:

- `results/group_a_meta_ensemble_real_backtest_20250101_20260611.json`
- `results/group_a_meta_ensemble_real_backtest_20250101_20260611.csv`
- `results/group_a_meta_real_vote_tune_sweep_20250101_20260611.json`
- `results/group_a_meta_real_vote_tune_sweep_20250101_20260611.csv`

Best Meta profile:

`adaptive_momcash_price_severe12_vote_bearfilter_recovery_defense22`

Latest sweep result:

- Final: `2.250M`
- Sharpe: `2.674`
- MDD: `-17.93%`
- Vol: `0.231`

Decision:

- Keep Meta as shadow/advisory only.
- Do not replace production with Meta yet.
- Reason: Final is higher, but MDD/Vol are materially worse than latest production, and the latest profile does not yet have complete 2008 stress validation.

## 2008 stress note

Existing 2008 proxy evidence:

- `results/group_a_meta_adaptive_micro_twii_proxy_2008_20070701_20101231_20260603_ranking.csv`

Best existing Meta-style 2008 variant:

`adaptive_momcash_price_severe12`

Result:

- Final: `1.608M`
- Sharpe: `0.746`
- MDD: `-41.98%`

Important limitation:

- The 2008 proxy does not have true TDCC/A2C/SAC historical data.
- Existing 2008 stress uses price-regime proxy behavior.
- Attempting to rerun the 2008 script on 2026-06-12 hit a payload/model observation mismatch:
  - checkpoint expected 37-dim observation
  - current default payload built 39-dim observation
- Do not use that failed rerun as evidence against the strategy; use the existing generated 2008 proxy results unless the payload/model alignment is fixed.

## Verification completed

Commands run successfully:

```bash
python3 -m py_compile run_group_a_combined_signal.py replay_group_a_latest_stepgate_tdcc.py
MPLCONFIGDIR=/tmp/matplotlib-group-a-combined python3 run_group_a_combined_signal.py --as-of-date 2026-06-12
```

Latest production signal was regenerated after the TDCC cap change.

## Next recommended work

1. Keep production at `tdcc18` unless new data shows YTD deterioration.
2. Add a cached TDCC state replay path permanently; current sweep tool now has cache support but can still be optimized.
3. If considering Meta promotion, first implement a proper 2008 stress for the selected `defense22` profile.
4. Do not compare Meta, Golden1, and latest production as strict A/B unless they are run from the same payload/model feature set.
