# GroupA+ H20 Bearish NCF Crash-Defense Diagnostic - 2026-07-13

## One-line conclusion

Do **not** promote the H20 bearish NCF / tail-score rule as an automatic
portfolio overlay. It has some crash-defense diagnostic value in selected
windows, but portfolio-level backtests show too much opportunity cost and
it misses at least one important shock window. Keep it as a warning signal
only unless a future study adds independent crash-signal confirmation.

## Scope

This session audited the A21.18 00631L NCF late-bull de-risk path from four
angles:

1. Confirm the exact `confidence` definition used by A21.18.
2. Run 2017-2019 out-of-sample calibration against the backfilled NCF panel.
3. Evaluate all H20 bearish candidates at episode level.
4. Convert the best episode candidate into portfolio-level shadow overlays
   and crash-window scorecards.

No active strategy manifest, daily signal, target weights, or execution path
was changed.

## Key files created or updated

New script:

- `scripts/evaluate/evaluate_a2118_h20_tail_score_shadow.py`

New / updated result artifacts:

- `results/a2118_ncf_confidence_calibration_oos_2017_2019_20260713.json`
- `results/a2118_ncf_event_overlay_value_oos_2017_2019_20260713.csv`
- `results/a2118_h20_bearish_episode_counterfactual_20260713.json`
- `results/a2118_h20_bearish_episode_counterfactual_20260713.csv`
- `results/a2118_h20_false_derisk_attribution_20260713.json`
- `results/a2118_h20_false_derisk_attribution_20260713.csv`
- `results/a2118_h20_tail_score_shadow_20260713.json`
- `results/a2118_h20_tail_score_shadow_20260713.csv`
- `results/a2118_h20_tail_score_shadow_windows_20260713.csv`

Note: `/results/` is ignored by git in this repo; the important numbers are
copied below for portability.

## Confidence definition confirmed

A21.18 must use the panel-aligned confidence value, not the older live JSON
composite confidence.

Correct definition:

```text
confidence = abs(ensemble_prob_up - 0.5) * 2
```

Meaning:

- It is probability magnitude away from 0.5.
- It is **not** model agreement.
- It is **not** model standard deviation.
- It is **not** entropy.
- It is **not** a validation score.

Relevant code:

- `scripts/misc/ncf_00631l.py`
  - `_build_expanding_horizon_ensemble_panel()` computes
    `prob_magnitude = abs(ensemble_prob_up - 0.5) * 2`.
  - panel `confidence` is written from that panel-aligned value.
- `group_a_plus/integrations/ncf.py`
  - `load_ncf_signal()` exposes `confidence_panel_aligned`.
- `group_a_plus/runners/a2118.py`
  - live trigger reads `confidence_panel_aligned`; if missing, it falls back
    to `0.0`, not the differently scaled composite confidence.

Active A21.18 parameters at the time of this audit:

```json
{
  "ncf_panel_631l_path": "results/ncf_00631l_panel_latest_20260707.csv",
  "h20_max": 0.33,
  "conf_min": 0.55,
  "h5_reentry_min": 0.55
}
```

## Existing 2025-2026 calibration recap

Source:

- `results/a2118_ncf_confidence_calibration_20260713.json`
- panel: `results/ncf_00631l_panel_latest_20260707.csv`
- coverage: 2025-01-02 to 2026-07-06
- rows: 354

Confidence distribution:

| Quantile | Value |
|---|---:|
| min | 0.0002 |
| p10 | 0.0533 |
| p25 | 0.1274 |
| median | 0.2502 |
| p75 | 0.3787 |
| p90 | 0.5315 |
| max | 0.8367 |

Event overlay value with `h20_max=0.33`, `h5_reentry_min=0.55`:

| conf_min | Events | Net value sum | Mean | Positive rate |
|---:|---:|---:|---:|---:|
| 0.55 | 0 | 0.0000 | n/a | n/a |
| 0.50 | 1 | +0.0235 | +0.0235 | 1.000 |
| 0.45 | 2 | +0.0570 | +0.0285 | 1.000 |
| 0.40 | 4 | +0.1459 | +0.0365 | 1.000 |
| 0.30 | 7 | -0.1685 | -0.0241 | 0.286 |

Initial reading before OOS: `0.40-0.50` looked interesting at episode level,
but sample size was too small to promote.

## 2017-2019 OOS confidence calibration

Source:

- panel: `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`
- report: `results/a2118_ncf_confidence_calibration_oos_2017_2019_20260713.json`
- event CSV: `results/a2118_ncf_event_overlay_value_oos_2017_2019_20260713.csv`
- coverage: 2017-01-03 to 2019-12-31
- panel rows: 731
- joined rows after price/frame alignment: 722

Result for the active-style trigger:

```text
golden1 days:                         685
golden1 + ma_gap > 0.10:               20
golden1 + ma_gap > 0.10 + h20 < 0.33:   0
```

For `conf_min = 0.55 / 0.50 / 0.45 / 0.40 / 0.30`, OOS event count was 0
because `prob_up_h20 < 0.33` never happened inside the late-bull `ma_gap`
condition.

Important interpretation:

- This is not evidence that the confidence threshold is calibrated.
- It is evidence that the active H20 bearish late-bull trigger is too sparse
  to have a comparable 2017-2019 OOS sample.

The 20 OOS late-bull rows had `prob_up_h20` between 0.468 and 0.939. Even
loosening H20 to 0.50-0.70 produced only one event and did not provide a
usable calibration basis.

## Episode-level counterfactual

The next step broadened the question:

> Does H20 bearish itself have episode-level value before imposing the
> A21.18 late-bull gate?

Source:

- `results/a2118_h20_bearish_episode_counterfactual_20260713.json`
- `results/a2118_h20_bearish_episode_counterfactual_20260713.csv`

Candidate entry rules tested:

- `prob_up_h20 < 0.33`
- `prob_up_h20 < 0.40`
- `prob_up_h20 < 0.45`
- `prob_up_h20 < 0.50`
- rolling q10 / q20 variants
- expanding q10 / q20 variants

Exit rules tested:

- `prob_up_h5 >= 0.55`
- `prob_up_h20 > 0.50`
- max hold 5 / 10 / 20 trading days

Counterfactual destinations kept inside GroupA+ universe:

- `0050.TW`
- `cash`
- `00632R.TW`
- `00679B.TWO`

`00751B.TWO` was explicitly excluded because it is not in GroupA+.

### Narrow H20 candidate: `h20 < 0.33`, exit `h5 >= 0.55`

2017-2019 OOS:

| Destination | Episodes | Sum value vs 00631L | Mean | Positive rate |
|---|---:|---:|---:|---:|
| cash | 8 | +0.0696 | +0.0087 | 0.875 |
| 00679B | 8 | +0.0689 | +0.0086 | 0.625 |
| 0050 | 8 | -0.0555 | -0.0069 | 0.250 |

2025-2026:

| Destination | Episodes | Sum value vs 00631L | Mean | Positive rate |
|---|---:|---:|---:|---:|
| cash | 26 | -0.0244 | -0.0009 | 0.615 |
| 00679B | 26 | -0.1389 | -0.0053 | 0.577 |
| 0050 | 26 | -0.1884 | -0.0072 | 0.423 |

Episode-level takeaway:

- In 2017-2019, H20 bearish was often a useful short-term de-risk warning.
- In 2025-2026, H20 bearish often led to false de-risk because 00631L
  rebounded hard.
- `0050` is not a good de-risk destination for this signal.

## False de-risk attribution

Source:

- `results/a2118_h20_false_derisk_attribution_20260713.json`
- `results/a2118_h20_false_derisk_attribution_20260713.csv`

Focus rules:

- `fixed_h20_lt_0p33__h5_ge_0p55`
- `fixed_h20_lt_0p45__h5_ge_0p55`

Best-looking filter:

```text
tail_reward_risk_score_h20 < -0.30
```

For `h20 < 0.33`, exit `h5 >= 0.55`, plus `tail_score < -0.30`:

2017-2019 OOS:

| Destination | Episodes | Sum value vs 00631L | Mean | Positive rate |
|---|---:|---:|---:|---:|
| cash | 8 | +0.0696 | +0.0087 | 0.875 |
| 00679B | 8 | +0.0689 | +0.0086 | 0.625 |
| 0050 | 8 | -0.0555 | -0.0069 | 0.250 |

2025-2026:

| Destination | Episodes | Sum value vs 00631L | Mean | Positive rate |
|---|---:|---:|---:|---:|
| cash | 10 | +0.0997 | +0.0100 | 0.700 |
| 00679B | 10 | +0.0757 | +0.0076 | 0.600 |
| 0050 | 10 | -0.0087 | -0.0009 | 0.600 |

This looked like the only plausible episode-level candidate:

```text
entry:
  prob_up_h20 < 0.33
  tail_reward_risk_score_h20 < -0.30

exit:
  prob_up_h5 >= 0.55

destination:
  cash or 00679B
```

However, it still needed portfolio-level testing because episode-level
counterfactuals ignore path interactions, regime weights, turnover, and
compounding.

## Portfolio-level shadow overlay

New script:

```bash
python3 scripts/evaluate/evaluate_a2118_h20_tail_score_shadow.py
```

Method:

- Start from A21.18 baseline with no NCF panel overlay.
- Only modify `golden1` days.
- Enter shadow regime when:

```text
prob_up_h20 < 0.33
tail_reward_risk_score_h20 < -0.30
```

- Hold until:

```text
prob_up_h5 >= 0.55
```

- Test destinations:
  - `cash`
  - `00679B.TWO`
- Test intensity:
  - `0.5`: move half of the 00631L weight to destination.
  - `1.0`: move all 00631L weight to destination.

Full-period results:

| Panel | Destination | Intensity | Events | Shadow days | Final value delta | Sharpe delta | Max DD delta |
|---|---|---:|---:|---:|---:|---:|---:|
| 2017-2019 | cash | 0.5 | 7 | 82 | -23,131 | +0.0086 | +0.0080 |
| 2017-2019 | cash | 1.0 | 7 | 82 | -28,355 | +0.0025 | +0.0080 |
| 2017-2019 | 00679B | 0.5 | 7 | 82 | -19,979 | +0.0158 | +0.0080 |
| 2017-2019 | 00679B | 1.0 | 7 | 82 | -22,053 | +0.0167 | +0.0080 |
| 2025-2026 | cash | 0.5 | 10 | 73 | -209,113 | +0.0413 | +0.0000 |
| 2025-2026 | cash | 1.0 | 10 | 73 | -235,131 | +0.0610 | +0.0000 |
| 2025-2026 | 00679B | 0.5 | 10 | 73 | -207,769 | +0.0462 | +0.0000 |
| 2025-2026 | 00679B | 1.0 | 10 | 73 | -232,503 | +0.0701 | +0.0000 |

Portfolio-level conclusion:

- The candidate improves Sharpe slightly in some variants.
- It can improve drawdown in some periods.
- But final value loss is too large.
- It is not promotable as a normal portfolio overlay.

## Crash-window defense scorecard

The user asked whether this might still be useful as crash defense rather
than return overlay. The script was extended to emit:

- `results/a2118_h20_tail_score_shadow_windows_20260713.csv`

Crash-window metrics:

- return delta
- max drawdown delta
- worst 5-day return delta
- worst 20-day return delta
- 5% expected tail loss delta
- time-under-water delta

Windows included:

- `trade_war_2018_full`: 2018-01-02 to 2018-12-31
- `trade_war_2018_q4`: 2018-10-01 to 2018-12-31
- `tariff_shock_2025`: 2025-03-17 to 2025-04-30
- `late_bull_pullback_2025`: 2025-08-01 to 2025-10-31
- `q1_2026_correction`: 2026-01-02 to 2026-04-30

### 2018 trade-war windows

All variants had the same effective window deltas because the triggered
days / weights did not differ materially inside the scored subwindow.

| Window | Return delta | Max DD delta | Worst 5d delta | Worst 20d delta | ETL delta |
|---|---:|---:|---:|---:|---:|
| 2018 full | +0.0030 | +0.0075 | +0.0055 | +0.0070 | +0.0014 |
| 2018 Q4 | +0.0065 | +0.0074 | +0.0055 | +0.0067 | +0.0019 |

This is real crash-defense value, but small.

### 2025 tariff shock

| Window | Return delta | Max DD delta | Worst 5d delta | Worst 20d delta | ETL delta |
|---|---:|---:|---:|---:|---:|
| 2025 tariff shock | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

The signal missed this important shock window entirely.

### 2025 late-bull pullback

| Destination | Intensity | Return delta | Max DD delta | Worst 20d delta | ETL delta |
|---|---:|---:|---:|---:|---:|
| cash | 0.5 | -0.0323 | 0.0000 | -0.0003 | +0.0013 |
| cash | 1.0 | -0.0505 | 0.0000 | -0.0004 | +0.0018 |
| 00679B | 0.5 | -0.0301 | 0.0000 | -0.0004 | +0.0015 |
| 00679B | 1.0 | -0.0462 | 0.0000 | -0.0007 | +0.0020 |

This is pure insurance cost without drawdown benefit.

### 2026 Q1 correction

| Destination | Intensity | Return delta | Max DD delta | Worst 5d delta | Worst 20d delta | ETL delta |
|---|---:|---:|---:|---:|---:|---:|
| cash | 0.5 | -0.0459 | +0.0298 | +0.0234 | +0.0233 | +0.0079 |
| cash | 1.0 | -0.0405 | +0.0421 | +0.0318 | +0.0313 | +0.0094 |
| 00679B | 0.5 | -0.0452 | +0.0299 | +0.0229 | +0.0227 | +0.0079 |
| 00679B | 1.0 | -0.0390 | +0.0421 | +0.0310 | +0.0302 | +0.0094 |

This is meaningful crash-defense behavior, but the premium is about 3.9-4.6%
of window return. It supports diagnostic/warning use, not automatic promotion.

## Predefined confidence-gate check

After the initial no-promotion decision, a final small check tested only a
few **predefined** confidence gates, not an open-ended threshold sweep:

```text
confidence_min = None / 0.30 / 0.45 / 0.55
```

The underlying candidate stayed fixed:

```text
prob_up_h20 < 0.33
tail_reward_risk_score_h20 < -0.30
exit when prob_up_h5 >= 0.55
destination = cash or 00679B
intensity = 0.5 or 1.0
```

The same script now emits `confidence_min` in:

- `results/a2118_h20_tail_score_shadow_20260713.csv`
- `results/a2118_h20_tail_score_shadow_windows_20260713.csv`
- `results/a2118_h20_tail_score_shadow_20260713.json`

Full-period result summary:

| Panel | Gate | Effect |
|---|---:|---|
| 2017-2019 | none | Best of these variants, but still final-value negative |
| 2017-2019 | >=0.30 / >=0.45 / >=0.55 | Fewer events and lower turnover, but final value remains negative |
| 2025-2026 | none | Large final-value drag, about -207k to -235k depending destination/intensity |
| 2025-2026 | >=0.30 | Slightly less drag, still about -199k to -220k |
| 2025-2026 | >=0.45 | Only 2 events / 10 shadow days; drag drops materially, but still no full-period edge |
| 2025-2026 | >=0.55 | 0 events; equivalent to doing nothing |

Representative 2025-2026 full-period numbers:

| Destination | Intensity | Confidence gate | Events | Shadow days | Final value delta | Sharpe delta |
|---|---:|---:|---:|---:|---:|---:|
| cash | 0.5 | none | 10 | 73 | -209,113 | +0.0413 |
| cash | 0.5 | 0.30 | 7 | 59 | -199,117 | +0.0431 |
| cash | 0.5 | 0.45 | 2 | 10 | -22,095 | +0.1020 |
| cash | 0.5 | 0.55 | 0 | 0 | 0 | 0 |
| cash | 1.0 | 0.45 | 2 | 10 | -1,920 | +0.1418 |
| 00679B | 1.0 | 0.45 | 2 | 10 | -8,150 | +0.1311 |

The 2025-2026 `confidence >= 0.45` gate reduces the premium, but it also
removes the crash-defense behavior that made the signal interesting.

Q1 2026 correction scorecard:

| Destination | Intensity | Confidence gate | Return delta | Max DD delta | Worst 5d delta | Worst 20d delta |
|---|---:|---:|---:|---:|---:|---:|
| 00679B | 1.0 | none | -0.0390 | +0.0421 | +0.0310 | +0.0302 |
| 00679B | 1.0 | 0.30 | -0.0377 | +0.0385 | +0.0315 | +0.0264 |
| 00679B | 1.0 | 0.45 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| cash | 1.0 | none | -0.0405 | +0.0421 | +0.0318 | +0.0313 |
| cash | 1.0 | 0.30 | -0.0399 | +0.0372 | +0.0321 | +0.0262 |
| cash | 1.0 | 0.45 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Interpretation:

- `confidence >= 0.30` does not solve the premium problem.
- `confidence >= 0.45` mostly turns the signal off during the key Q1 2026
  crash-defense window.
- `confidence >= 0.55` is effectively no-op in 2025-2026.

This reinforces the prior decision: confidence gating alone does not turn
this into a promotable automatic overlay.

## Execution delay and missed rebound diagnostic

User follow-up:

```text
分析回補延遲與 missed rebound
```

Added read-only diagnostic:

- `scripts/evaluate/evaluate_a2118_h20_delay_missed_rebound.py`
- `results/a2118_h20_delay_missed_rebound_20260713.json`
- `results/a2118_h20_delay_missed_rebound_episodes_20260713.csv`
- `results/a2118_h20_delay_missed_rebound_portfolio_delay_20260713.csv`

Method:

1. Rebuild the same H20 tail-score shadow variants.
2. Compare same-day target execution with a 1-trading-day delayed regime.
3. Isolate the pure H20 overlay delay impact by comparing against a delayed
   baseline regime too.
4. For every shadow episode, decompose 00631L into:
   - entry to trough return,
   - trough to exit-signal rebound,
   - t+1 exit-delay return,
   - post-exit 5/10/20 trading-day return.

Key result: execution delay is real, but it is not the main failure mode.
The larger problem is missed rebound while waiting for `prob_up_h5 >= 0.55`.

Pure H20 overlay t+1 delay impact, confidence gate = none:

| Panel | Destination | Intensity | Events | Shadow days | Same-day overlay delta | Delayed overlay delta | Incremental delay impact |
|---|---|---:|---:|---:|---:|---:|---:|
| 2017-2019 | cash | 0.5 | 7 | 82 | -23,131 | -26,423 | -3,293 |
| 2017-2019 | cash | 1.0 | 7 | 82 | -28,355 | -35,914 | -7,559 |
| 2017-2019 | 00679B | 0.5 | 7 | 82 | -19,979 | -23,008 | -3,030 |
| 2017-2019 | 00679B | 1.0 | 7 | 82 | -22,053 | -29,103 | -7,050 |
| 2025-2026 | cash | 0.5 | 10 | 73 | -209,113 | -207,343 | +1,771 |
| 2025-2026 | cash | 1.0 | 10 | 73 | -235,131 | -240,313 | -5,182 |
| 2025-2026 | 00679B | 0.5 | 10 | 73 | -207,769 | -207,728 | +41 |
| 2025-2026 | 00679B | 1.0 | 10 | 73 | -232,503 | -241,036 | -8,533 |

Sanity check: when `confidence >= 0.55` creates 0 H20 overlay events in
2025-2026, the pure overlay delay impact is exactly 0. This confirms the
incremental delay calculation is not just measuring baseline A21.18 delay.

Episode-level rebound decomposition, representative variant
`destination=cash`, `intensity=1.0`, confidence gate = none:

| Panel | Episodes | Avg entry-to-trough 00631L | Avg trough-to-exit rebound | Avg entry-to-exit 00631L | Avg t+1 exit-delay missed return | Avg post-exit 5d | Avg post-exit 10d | Avg post-exit 20d |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017-2019 | 7 | -1.24% | +1.68% | +0.43% | +0.37% | -1.35% | +1.20% | +3.37% |
| 2025-2026 | 10 | -1.33% | +3.15% | +1.81% | +1.74% | +7.74% | +9.33% | +13.38% |

2025-2026 is the important failure pattern:

- Average protected drawdown before trough: only about -1.33%.
- Average rebound already missed before the H5 re-entry signal: about +3.15%.
- Average extra return missed by t+1 re-entry execution: about +1.74%.
- After the exit signal, 00631L still averaged about +7.74% over 5 trading
  days and +9.33% over 10 trading days.

Largest illustrative 2025-2026 examples:

| Entry | Exit signal | Entry-to-trough | Trough-to-exit rebound | t+1 exit-delay missed return | Post-exit 5d | Post-exit 10d |
|---|---|---:|---:|---:|---:|---:|
| 2025-09-04 | 2025-09-10 | 0.00% | +9.03% | +0.05% | +1.97% | +8.30% |
| 2025-10-02 | 2025-11-05 | 0.00% | +10.30% | +1.91% | +1.60% | -8.11% |
| 2026-04-24 | 2026-05-18 | 0.00% | +8.68% | -3.17% | +11.81% | +22.23% |
| 2026-05-19 | 2026-05-20 | -1.40% | 0.00% | +7.01% | +21.08% | +32.90% |

Interpretation:

- The H20 bearish warning can occasionally identify crash-defense windows.
- But as a trading overlay, it often enters when 00631L is no longer falling,
  then waits for H5 confirmation after a material rebound already occurred.
- The re-entry rule is structurally too slow for leveraged rebound behavior.
- A simple t+1 execution delay adds friction, but the larger damage is
  signal/exit latency plus rebound convexity of 00631L.

Decision impact:

- Do not fix this branch with more threshold tuning.
- Do not promote H20 tail-score as automatic de-risk/re-entry logic.
- Keep it as crash-defense diagnostic only unless an independent crash
  confirmation source and a separate rebound recapture mechanism are both
  evaluated OOS.

## Final decision

Do not promote any automatic H20 bearish NCF / tail-score de-risk overlay.

Reasons:

1. Active A21.18 trigger has no comparable 2017-2019 OOS event sample.
2. Broader H20 bearish episodes are unstable across periods.
3. Episode-level positive candidates fail portfolio-level final-value tests.
4. Crash-window value exists in 2018 and 2026 Q1, but misses 2025 tariff
   shock and charges too much premium in 2025 late-bull pullback.
5. `0050` is specifically a poor destination for this signal.

Keep as diagnostic only:

```text
warning:
  prob_up_h20 < 0.33
  tail_reward_risk_score_h20 < -0.30
```

If used in daily reporting, label it as a crash-defense warning, not a
trade instruction.

## Future work constraints

Do **not** continue with small sweeps of:

- `conf_min`
- `h20_max`
- `tail_score_max`
- destination weights
- max-hold days

Those are likely to overfit the same small event set.

Only continue this branch if adding an independent crash confirmation source,
for example:

- realized-volatility / vol-of-vol spike
- options / TXO stress confirmation
- cross-asset liquidity shock
- institutional forced-selling proxy
- multi-source crash-risk ensemble from a separate model family

Any future candidate must be evaluated as:

1. warning-only diagnostic first,
2. crash-window scorecard second,
3. portfolio-level shadow last,
4. and must pass OOS windows before promotion.

## Verification

After adding the portfolio-level shadow script and crash-window scorecard,
the following tests passed:

```bash
pytest -q tests/test_a2118_composite_confidence_sweep.py tests/test_sweep_a2118_shadow_improvements.py
```

Result:

```text
6 passed
```
