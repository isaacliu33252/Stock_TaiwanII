# Group A+ NCF H20 Confidence / PIT Governance Handoff - 2026-07-13

## Scope

This handoff records the completed analysis chain for 00631L NCF H20 bearish
signals, confidence calibration, rebound latency, and point-in-time historical
panel governance.

Final production decision:

```text
Do not promote H20 bearish / tail-score to an automatic overlay.
Keep it as crash-defense diagnostic / warning only.
Do not adjust production thresholds until enough OOS events accumulate on a
point-in-time signal panel.
```

## Completed Work

### 1. Confidence definition and OOS calibration

Conclusion:

- Correct A21.18 confidence is:

```text
confidence = abs(ensemble_prob_up - 0.5) * 2
```

- It is panel-aligned probability magnitude.
- It is not model agreement, prediction std, entropy, or validation score.
- Live A21.18 reads `confidence_panel_aligned`, not legacy composite JSON
  confidence.

OOS 2017-2019 calibration:

- Source panel: `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`
- Output:
  - `results/a2118_ncf_confidence_calibration_oos_2017_2019_20260713.json`
  - `results/a2118_ncf_event_overlay_value_oos_2017_2019_20260713.csv`

Finding:

- Active-style trigger had 0 events in 2017-2019:

```text
golden1 + ma_gap > 0.10 + prob_up_h20 < 0.33 = 0
```

Decision:

- OOS sample is insufficient for production threshold changes.

### 2. H20 bearish episode-level counterfactual

Output:

- `results/a2118_h20_bearish_episode_counterfactual_20260713.json`
- `results/a2118_h20_bearish_episode_counterfactual_20260713.csv`

Tested:

- H20 rules: fixed thresholds and rolling/expanding quantiles.
- Exits: `h5_ge_0p55`, `h20_gt_0p50`, `max_hold_5/10/20`.
- Destinations: `0050.TW`, `cash`, `00632R.TW`, `00679B.TWO`.
- `00751B` was removed because it is not in Group A+.

Best episode-level shape:

```text
prob_up_h20 < 0.33
tail_reward_risk_score_h20 < -0.30
exit when prob_up_h5 >= 0.55
destination cash or 00679B
```

Decision:

- Episode-level value exists in selected windows, but this is not enough for
  promotion.
- Portfolio-level validation is required.

### 3. Portfolio-level H20 tail-score shadow

Script:

- `scripts/evaluate/evaluate_a2118_h20_tail_score_shadow.py`

Output:

- `results/a2118_h20_tail_score_shadow_20260713.json`
- `results/a2118_h20_tail_score_shadow_20260713.csv`
- `results/a2118_h20_tail_score_shadow_windows_20260713.csv`

Finding:

- Full-period portfolio-level result fails despite some crash-window defense.
- 2025-2026 no-gate variants caused large final-value drag:

```text
cash 0.5:     about -209k
cash 1.0:     about -235k
00679B 0.5:   about -208k
00679B 1.0:   about -233k
```

Crash-window result:

- 2018 trade-war and 2026 Q1 show some drawdown/tail benefit.
- 2025 tariff shock was missed.
- 2025 late-bull pullback produced premium drag without enough protection.

Decision:

- H20 tail-score is diagnostic only, not an automatic overlay.

### 4. Predefined confidence gates

Tested gates:

```text
None, 0.30, 0.45, 0.55
```

Finding:

- `confidence >= 0.30`: does not solve premium drag.
- `confidence >= 0.45`: materially reduces events, but also removes key Q1
  2026 crash-defense behavior.
- `confidence >= 0.55`: 0 events in 2025-2026.

Decision:

- Confidence gate alone does not make H20 overlay promotable.
- Do not continue small threshold sweeps.

### 5. Re-entry delay and missed rebound

Script:

- `scripts/evaluate/evaluate_a2118_h20_delay_missed_rebound.py`

Output:

- `results/a2118_h20_delay_missed_rebound_20260713.json`
- `results/a2118_h20_delay_missed_rebound_episodes_20260713.csv`
- `results/a2118_h20_delay_missed_rebound_portfolio_delay_20260713.csv`

Finding:

- t+1 execution delay is real but not the main failure mode.
- Main failure mode is missed rebound:
  - H20 warning often stays active after 00631L has already bottomed.
  - Waiting for `prob_up_h5 >= 0.55` frequently exits after material rebound.
  - 00631L often continues higher after exit.

Representative no-gate, cash 1.0 episode summary:

| Panel | Episodes | Avg entry-to-trough | Avg trough-to-exit rebound | Avg t+1 exit-delay missed return | Avg post-exit 5d | Avg post-exit 10d |
|---|---:|---:|---:|---:|---:|---:|
| 2017-2019 | 7 | -1.24% | +1.68% | +0.37% | -1.35% | +1.20% |
| 2025-2026 | 10 | -1.33% | +3.15% | +1.74% | +7.74% | +9.33% |

Decision:

- The issue is not fixable by simply adding/removing one execution-delay day.
- Re-entry latency plus 00631L rebound convexity makes this unsuitable as
  automatic de-risk/re-entry logic.

### 6. Point-in-time historical NCF panel

Builder:

- `scripts/evaluate/build_ncf_pit_historical_panel.py`

Output:

- `results/ncf_00631l_pit_historical_panel_20260713.csv`
- `results/ncf_00631l_pit_historical_panel_20260713.json`
- `results/ncf_00631l_pit_historical_panel_manifest_20260713.json`

Coverage:

```text
rows: 1097
date_start: 2017-01-03
date_end: 2026-07-09
sources:
  oos_2017_2019      731 rows
  panel_2025_2026    366 rows
```

Leakage policy:

- Dropped realized future columns:
  - `actual_fwd_mdd_gt5_h20`
  - `forward_mdd_h20`
  - `actual_fwd_gain_gt5_h20`
  - `forward_gain_h20`
- Builder rejects retained columns with prefixes:
  - `actual_`
  - `forward_`
  - `target_`
  - `label_`

Retained as-of prediction columns:

- `prob_fwd_mdd_gt5_h20`
- `prob_fwd_gain_gt5_h20`
- `tail_reward_risk_score_h20`

These are model outputs available at the as-of date, not realized outcomes.

Decision:

- Use the PIT panel as the clean historical NCF signal surface for no-lookahead
  diagnostics.
- Keep original research panels only for calibration and label-based research.

## Governance Rule

Production thresholds must not be changed from small-sample diagnostics.

Thresholds affected:

- `h20_max`
- `confidence_min`
- `tail_reward_risk_score_h20`
- any derived H20 bearish gate

Required before any future production threshold change:

1. Enough OOS events on the PIT panel.
2. Cross-regime stability.
3. Crash-window scorecard improvement without large premium drag.
4. Portfolio-level shadow pass after costs and t+1 delay.
5. Independent confirmation if used for automatic de-risking.

Until those conditions are met:

```text
No production threshold adjustment.
No automatic H20 bearish overlay.
Warning-only use is allowed.
```

## Allowed Future Use of H20

Only two uses are reasonable:

1. Warning only:
   - mark crash-risk,
   - prohibit extra leverage,
   - add diagnostic commentary.

2. Intersection with an independent extreme-crash confirmation signal:
   - only for rare expected persistent selloffs,
   - not V-shaped rebound regimes,
   - must be re-tested independently OOS.

## Related Handoffs

- `GROUP_A_PLUS_H20_BEARISH_CRASH_DEFENSE_DIAGNOSTIC_HANDOFF_20260713.md`
- `GROUP_A_PLUS_NCF_00631L_PIT_HISTORICAL_PANEL_HANDOFF_20260713.md`

## Verification

Commands run across this workstream:

```bash
python3 -m py_compile scripts/evaluate/evaluate_a2118_h20_tail_score_shadow.py
python3 -m py_compile scripts/evaluate/evaluate_a2118_h20_delay_missed_rebound.py
python3 -m py_compile scripts/evaluate/build_ncf_pit_historical_panel.py
pytest -q tests/test_a2118_composite_confidence_sweep.py tests/test_sweep_a2118_shadow_improvements.py
pytest -q tests/test_build_ncf_pit_historical_panel.py tests/test_build_ncf_panel_manifest.py
```

Results:

```text
6 passed
5 passed
```

## Final Decision

Do not promote H20 bearish / tail-score to production overlay.

Keep H20 as:

```text
crash-defense diagnostic / warning only
```

Do not adjust production thresholds until sufficient OOS events accumulate on
the point-in-time historical NCF panel.
