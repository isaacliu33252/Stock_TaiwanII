# GroupA+ 2022 Defensive Regime Attribution Handoff - 2026-08-14

## Scope

Codex 2026-08-14 change. This is a research-only attribution diagnostic after the cash-floor and slow-bear classifier shadows. It does not change live strategy behavior, target weights, execution plans, manifests, or the daily pipeline.

The diagnostic isolates 2022 defensive-regime losses by replacing only the defensive basket, recovery basket, or defensive/recovery regime labels, then replaying the same active latest baseline with dividends and transaction costs.

## Files Changed

- `scripts/evaluate/evaluate_group_a_plus_2022_defensive_regime_attribution.py`
  - New research-only attribution script.
  - Uses `run_latest()` for the active latest baseline.
  - Uses existing dividend/cost simulator.
  - Writes JSON, CSV, episode CSV, and Markdown summary.
  - Contains `Codex 2026-08-14` attribution-only note.
- `tests/test_evaluate_group_a_plus_2022_defensive_regime_attribution.py`
  - Tests weight transfer, basket isolation variants, regime replacement, and defensive episode summarization.
  - Contains `Codex 2026-08-14` note.

## Outputs

- `results/group_a_plus_2022_defensive_regime_attribution_after_20260813_refresh.json`
- `results/group_a_plus_2022_defensive_regime_attribution_after_20260813_refresh.csv`
- `results/group_a_plus_2022_defensive_regime_attribution_after_20260813_refresh_episodes.csv`
- `results/group_a_plus_2022_defensive_regime_attribution_after_20260813_refresh.md`

Multi-window context:

- `results/group_a_plus_defensive_regime_attribution_2020_covid_after_20260813_refresh.json`
- `results/group_a_plus_defensive_regime_attribution_2024_2026_after_20260813_refresh.json`
- `results/group_a_plus_defensive_regime_attribution_2025_2026_after_20260813_refresh.json`

## 2022 Finding

2022 has one long defensive episode:

| Start | End | Days | Portfolio Return | 0050 Return | 00631L Return | 00679B Return | 00632R Return |
|---|---|---:|---:|---:|---:|---:|---:|
| 2022-02-24 | 2022-11-10 | 179 | -15.94% | -24.11% | -38.55% | -20.98% | +19.77% |

The 2022 loss was not caused by recovery timing. Recovery variants made no difference because the 2022 window stayed in `group_a_plus_defensive` for the long episode.

The issue was defensive basket exposure during a stock-bond selloff:

- current defensive basket held 0050 and 00679B exposure;
- both 0050 and 00679B fell sharply during the defensive episode;
- all-cash defensive removes that exposure and is the strongest 2022 diagnostic variant.

## 2022 Variant Results

Baseline latest final value: `846,876.29`.

| Variant | Final Delta | Sortino Delta | MDD Delta | Interpretation |
|---|---:|---:|---:|---|
| `defensive_all_cash` | +135,009.78 | +1.3778 | +16.68% | Strongest 2022 attribution; risk came from staying exposed in defensive |
| `defensive_to_cash_regime` | +135,009.78 | +1.3778 | +16.68% | Same as all-cash basket |
| `defensive_bond30_cash70` | +77,198.61 | +0.4891 | +10.92% | 00679B exposure hurt, but lower total exposure helped |
| `defensive_bond_to_cash` | +57,834.25 | +0.5223 | +6.19% | Removing 00679B helped materially |
| `defensive_to_golden1` | +10,166.29 | +0.4330 | -0.30% | Avoiding defensive was not enough and worsened MDD |
| `defensive_bond_to_0050` | -1,380.95 | +0.4407 | -2.15% | Shifting bond to equity did not solve 2022 |
| `defensive_replaced_by_recovery` | -34,501.11 | +0.4498 | -6.55% | Recovery-style risk was worse |

## Multi-Window Check

No single attribution variant passed all four windows on final value, Sortino, and MDD.

| Variant | 2020 | 2022 | 2024-2026 | 2025-2026 | Blocker |
|---|---:|---:|---:|---:|---|
| `defensive_all_cash` | -20,312.13 / +0.0402 / +8.57% | +135,009.78 / +1.3778 / +16.68% | +84,976.96 / +0.0189 / +0.00% | +65,503.43 / +0.0242 / -0.02% | 2020 final and tiny 2025 MDD fail |
| `defensive_bond_to_cash` | -25,912.75 / +0.0012 / +0.51% | +57,834.25 / +0.5223 / +6.19% | +100,078.26 / +0.1113 / +0.00% | +77,144.08 / +0.1907 / +0.44% | 2020 final fails |
| `defensive_bond30_cash70` | +5,011.85 / +0.3790 / +8.02% | +77,198.61 / +0.4891 / +10.92% | -12,866.56 / +0.0348 / +0.00% | -9,918.03 / +0.0726 / -0.34% | Recent final/MDD fail |
| `defensive_to_golden1` | -27,671.56 / -0.3089 / -4.97% | +10,166.29 / +0.4330 / -0.30% | +106,221.60 / -0.0346 / -5.00% | +93,744.31 / +0.0208 / -4.92% | MDD/Sortino fail |

Format: final delta / Sortino delta / MDD delta.

## Conclusion

The 2022 problem is now attributed to defensive basket composition under stock-bond selloff, especially 00679B and residual 0050 exposure during a long defensive episode.

But a static live replacement is not justified:

- all-cash defensive fixes 2022 strongly, but hurts 2020 final value;
- removing bond exposure fixes 2022 and recent windows, but hurts 2020 final value;
- keeping some bond/cash works in 2020 and 2022, but drags recent windows.

## Decision

Do not promote a static defensive basket change.

Next candidate should be conditional bond-risk-aware defensive basket selection, not another generic cash floor:

- detect stock-bond selloff / rate-hike-like defensive state;
- only then shift 00679B and some 0050 exposure to cash;
- keep crash-style defensive handling separate.

## Recommended Next Step

Build a small bond-risk-aware defensive basket shadow:

- Candidate trigger features:
  - 00679B trailing return below 0 over 20/60 days;
  - 00679B below moving average;
  - 0050 and 00679B rolling correlation positive or both negative;
  - defensive episode active.
- Candidate action:
  - shift 00679B to cash;
  - optionally shift 0050 to cash only when both stock and bond trend are negative.
- Required gate:
  - same parameter family must pass 2020, 2022, 2024-2026, and 2025-2026.

## Verification

- `.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_2022_defensive_regime_attribution.py -q`
  - `4 passed in 5.22s`
- `.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2022_defensive_regime_attribution.py`
- 2022 attribution and three multi-window context runs completed successfully after the 2026-08-13 data refresh.
