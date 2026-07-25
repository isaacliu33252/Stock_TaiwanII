# FinStressTS Baseline Compare Shadow（2026-07-17）

## Purpose

This is a research-only follow-up to the FinStressTS counterfactual shadow.

It compares the `2026-07-20` reference weights, no-`00631L`, reduced leverage,
and simple transparent dynamic gates under the same mechanism-specific stress
scenarios.

## Candidates

- `reference_20260720`: `0050.TW 50% / 00631L.TW 20% / cash 30%`
- `no_00631l_reference_cash`: `0050.TW 50% / cash 50%`
- `reduced_leverage`: `0050.TW 70% / 00631L.TW 10% / cash 20%`
- `rolling_vol_gate`: use reference weights unless 00631L rolling volatility is high
- `trend_gate`: use reference weights unless 00631L is below MA60 or 20-day return is negative
- `combined_vol_trend_gate`: union of volatility and trend gates

## Artifacts

- Script: `scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py`
- Output: `results/group_a_plus_finstressts_baseline_compare_shadow_20260717.json`
- Latest pointer: `report/group_a_plus/latest/finstressts_baseline_compare_shadow.json`
- Daily pipeline: `finstressts_baseline_compare_shadow` runs as a best-effort
  diagnostic after `finstressts_counterfactual_shadow`.

## Policy

This is shadow-only:

- no live target-weight change
- no auto-rebalance
- no `00631L` add
- keep `Golden1_0531` unchanged

## 2026-07-17 Result

Input:

- common `0050.TW` / `00631L.TW` close panel through `2026-07-17`
- scenario rows: `2809`

Summary:

- best shadow candidate by fewest tail failures: `combined_vol_trend_gate`
- candidates beating no-`00631L` on both ES95 and max drawdown: `0`
- `allow_00631l_add = false`

Wins versus no-`00631L`:

| Candidate | Wins / 5 | Tail failures / 5 |
| --- | ---: | ---: |
| `reference_20260720` | `0` | `4` |
| `reduced_leverage` | `0` | `4` |
| `rolling_vol_gate` | `0` | `2` |
| `trend_gate` | `0` | `1` |
| `combined_vol_trend_gate` | `0` | `1` |

Interpretation:

- `combined_vol_trend_gate` is the best research candidate because it reduces
  tail failures from `4 / 5` to `1 / 5`.
- It still does not beat no-`00631L` on both ES95 and max drawdown in any tested
  scenario.
- Therefore it is not promotable and does not justify adding `00631L`.

Conclusion:

- Keep as shadow-only research.
- Do not change GroupA+ latest strategy.
- Do not change `Golden1_0531`.
- Do not rebalance or add `00631L`.
