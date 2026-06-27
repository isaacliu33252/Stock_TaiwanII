# Group A Golden1_0531 Improvement Experiment

Date: 2026-05-31
Status: Research complete, no production promotion
Scope: Group A only

## 1. Baseline

Production release remains:

- [`Golden1_0531`](GROUP_A_GOLDEN1_0531_RELEASE.md)

The production entrypoint, payload, and live signal were not changed.

## 2. PVA Runtime Micro-Sweep

Evidence:

- [`results/group_a_Golden1_0531_pva_micro_sweep_20260531.json`](results/group_a_Golden1_0531_pva_micro_sweep_20260531.json)
- [`results/group_a_Golden1_0531_dual_objective_20260531.json`](results/group_a_Golden1_0531_dual_objective_20260531.json)

The first sweep tested `243` runtime combinations without PPO retraining.

The best dual-objective shadow candidate is:

- [`results/group_a_candidate_Golden1_0531_pva036_j015_20260531.json`](results/group_a_candidate_Golden1_0531_pva036_j015_20260531.json)

Changes versus `Golden1_0531`:

- `pva_weight: 0.32 -> 0.36`
- `pva_j_state_weight: 0.19 -> 0.15`
- Keep `pva_min_leverage_scale = 0.40`
- Keep `pva_buy_dip_strength = 0.95`
- Keep all local-regime settings unchanged

The sweep produced the same observed metrics for `pva_min_leverage_scale = 0.35`, `0.40`, and `0.45` in this candidate neighborhood. The shadow manifest keeps the production value `0.40` to minimize unnecessary changes.

Recent OOS comparison on `2025-01-02` to `2026-05-25`:

| Metric | Golden1_0531 | Shadow candidate | Delta |
| --- | ---: | ---: | ---: |
| Final value | `2,058,975.61` | `2,061,509.36` | `+2,533.75` |
| Annual return | `72.7260%` | `72.8868%` | `+0.1608 pp` |
| Sharpe | `2.303933` | `2.307882` | `+0.003948` |
| Max drawdown | `-24.9939%` | `-24.9909%` | `+0.0031 pp` |
| Trades | `63` | `63` | `0` |
| Fees | `21,338.36` | `21,286.15` | `-52.21` |

TWII 2008 proxy comparison:

| Metric | Golden1_0531 | Shadow candidate | Delta |
| --- | ---: | ---: | ---: |
| Final value | `1,494,398.92` | `1,494,175.46` | `-223.46` |
| Sharpe | `0.572420` | `0.572326` | `-0.000094` |
| Max drawdown | `-38.0202%` | `-38.0194%` | `+0.0008 pp` |
| Trades | `310` | `310` | `0` |

Interpretation:

- The OOS improvement is real but small.
- Crash behavior is effectively unchanged.
- This does not justify changing the production strategy during the three-month trial.
- Retain the candidate for shadow comparison through `2026-08-31`.

## 3. Local-Regime Hysteresis Sweep

Evidence:

- [`results/group_a_Golden1_0531_local_regime_sweep_20260531.json`](results/group_a_Golden1_0531_local_regime_sweep_20260531.json)

Tested:

- `risk_off_clear_days = 3, 5, 7`
- `severe_clear_days = 4, 6, 8`
- `severe_template = 0050_70_00632R_30, 0050_only`

Result:

- Keep the existing Golden1_0531 local-regime configuration.
- Increasing `risk_off_clear_days` to `7` improved crash proxy drawdown from `-38.02%` to `-36.19%`, but reduced recent OOS final value by about `61,162`.
- Replacing the severe inverse template with `0050_only` reduced crash trades materially, but worsened crash proxy drawdown to roughly `-54%` to `-55%`.
- Changing `severe_clear_days` did not materially change results in this tested matrix.

## 4. Decision

- Keep production release: `Golden1_0531`
- Do not modify live execution rules during the trial period.
- Track shadow candidate: `Golden1_0531_shadow_pva036_j015`
- Revisit promotion only after the `2026-08-31` review with actual execution data.

## 5. Full-Feature Training Run — 2026-06-03

Training command:
```
python3 train_dual_group_2024_2026.py \
  --group-filter group_a --timesteps 300000 --seed 42 \
  --group-a-action-schema triplet_v4 \
  --group-a-enable-dca --group-a-dca-day 20 --group-a-dca-0050 5000 \
  --group-a-enable-pva-features --group-a-enable-pva-sigmoid \
  --group-a-enable-llm-sentiment \
  --group-a-enable-institutional \
  --group-a-enable-local-regime-gate \
  --group-a-00631l-max-weight 0.20 \
  --group-a-pva-weight 0.32 --group-a-pva-s-state-max-weight 0.35 \
  --group-a-pva-j-state-weight 0.19 --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-local-regime-risk-off-score-threshold 2 \
  --group-a-local-regime-severe-score-threshold 3 \
  --group-a-local-regime-risk-off-clear-days 3 \
  --group-a-local-regime-severe-clear-days 4 \
  --group-a-local-regime-risk-off-template 0050_only \
  --group-a-local-regime-severe-template 0050_70_00632R_30
```

Results:

| Metric | Full-Feature Run | Golden1_0531 | Basic (triplet_v2) |
| --- | ---: | ---: | ---: |
| Final Value | 2,686,446 | 2,058,976 | 3,572,755 |
| Annual Return | 55.51% | — | — |
| Sharpe | **1.860** | **2.30** | 1.857 |
| MDD | **-29.42%** | **-25%** | -36.15% |
| Trades | 109 | 63 | — |
| PVA triggers | 44 | — | — |
| DCA triggers | 28 | — | — |
| Total invested | 1,140,000 | — | — |
| Net profit | 1,546,446 | — | — |

Observation:
- Final value is higher than Golden1_0531 (2.69M vs 2.06M) but Sharpe 1.86 < 2.30 and MDD -29.42% > -25%.
- Higher return but worse risk-adjusted metrics suggests excessive volatility / overfitting.
- Basic triplet_v2 with no overlays achieved highest final value (3.57M) but worst MDD (-36.15%).
- Adding full feature set (PVA + sentiment + institutional + regime gate) did NOT improve risk-adjusted performance over Golden1_0531.

Conclusion: Golden1_0531 remains the production standard. Full-feature approach needs further tuning before promotion.
Evidence: `results/group_a_backtest_20240101_20260508_20260603_150406.json`

## 6. Meta Ensemble Shadow Signal Wrapper — 2026-06-03

Production remains unchanged.

Added:

- `run_group_a_meta_ensemble_shadow_signal.py`

Purpose:

- Convert the selected meta-ensemble allocator profile into a stable advisory-only live shadow signal.
- Read the selected profile from `group_a_meta_ensemble_real_config.json`.
- Consume the latest allocator sweep, currently `results/group_a_meta_real_allocator_sweep_20260603_v2.json`.
- Generate stable shadow artifacts:
  - `results/group_a_meta_ensemble_shadow_live_latest.json`
  - `results/group_a_meta_ensemble_shadow_live_latest.csv`
  - `results/group_a_meta_ensemble_shadow_bundle_latest.json`

Validation run:

```bash
python3 run_group_a_meta_ensemble_shadow_signal.py \
  --base-signal-json results/group_a_combined_live_latest.json
```

Output snapshot for `actual_data_date=2026-06-02`:

| Field | Value |
| --- | ---: |
| Profile | `ppo_dominant_tdcc_cap` |
| Status | `rebalance` |
| 0050 target weight | `74.75%` |
| 00631L target weight | `0.00%` |
| 00632R target weight | `0.75%` |
| Cash target weight | `24.50%` |
| Target 0050 shares | `7,260` |
| Target 00631L shares | `0` |
| Target 00632R shares | `756` |

Decision:

- Keep as shadow only.
- Do not promote because the selected profile improves Sharpe/MDD but still trails Golden1_0531 and TDCC overlay in final value.
- Use this wrapper for daily research tracking alongside the frozen Golden1_0531 production trial.

## 7. Meta Risk-Off Relaxation Sweep — 2026-06-03

Production remains unchanged.

Implemented:

- `evaluate_group_a_meta_real_riskoff_sweep.py`

Purpose:

- Direction 1: reduce `risk_off` defensive intensity.
- Direction 2: test less binary TDCC risk-off handling by allowing fixed/tiered `00631L` caps.
- Keep the research isolated from `Golden1_0531` production execution.

Validation command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --output results/group_a_meta_real_riskoff_sweep_20260603_fast.json
```

Best candidate:

- `cap08_primary_rule05`

Configuration meaning:

- Risk-off allocator: `ppo=0.95`, `rule_based=0.05`
- TDCC risk-off `00631L` cap: `8%`
- Released leverage budget destination: `0050`
- Cash is intentionally reduced versus the prior meta shadow candidate.

Comparison on `2025-06-02` to `2026-06-02`:

| Metric | Prior meta shadow | `cap08_primary_rule05` | Delta |
| --- | ---: | ---: | ---: |
| Final value | `2,281,971.38` | `2,308,897.81` | `+26,926.43` |
| Sharpe | `4.0962` | `4.0306` | `-0.0656` |
| Max drawdown | `-9.7295%` | `-10.2233%` | `-0.4938 pp` |
| Rebalances | `46` | `39` | `-7` |
| Fees | `12,252.66` | `11,011.26` | `-1,241.40` |
| Final cash weight | `24.47%` | `2.50%` | `-21.97 pp` |
| Final 00631L weight | `0.00%` | `8.01%` | `+8.01 pp` |

Comparison versus same-window Golden1 base and latest TDCC overlay:

- Versus Golden1 base: final value still lower by `70,054.04`, Sharpe higher by `0.1538`, MDD improved by `0.9903 pp`.
- Versus latest TDCC overlay: final value lower by `7,543.34`, Sharpe lower by `0.0179`, MDD worse by `0.1989 pp`.

Shadow signal update:

- `group_a_meta_ensemble_real_config.json` now selects `cap08_primary_rule05` for shadow signal generation.
- `run_group_a_meta_ensemble_shadow_signal.py` now defaults to `results/group_a_meta_real_riskoff_sweep_20260603_fast.json`.
- Latest generated shadow signal for `actual_data_date=2026-06-02`:
  - `0050.TW = 89.25%`, target `8,669` shares
  - `00631L.TW = 8.00%`, target `2,166` shares
  - `00632R.TW = 0.25%`, target `252` shares
  - Cash `2.50%`

Decision:

- Keep `cap08_primary_rule05` as the active meta shadow candidate.
- Do not promote to production.
- The change improves the meta candidate's return problem, but the reduced cash buffer makes it less defensive than the prior shadow version.

## 8. Cash Floor And Small-Inverse Follow-Up — 2026-06-03

Production remains unchanged.

Follow-up command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --output results/group_a_meta_real_riskoff_cashfloor_sweep_20260603.json
```

Tested:

- `00631L` cap fine grid: `5%`, `6%`, `7%`, `8%`
- Cash floor: `10%`, `15%`
- Small inverse ETF cleanup: set `00632R` to zero when below `1%`

Key results on `2025-06-02` to `2026-06-02`:

| Candidate | Final value | Sharpe | MDD | Rebalances | Cash | 00631L |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cap08_primary_rule05` | `2,308,897.81` | `4.0306` | `-10.2233%` | `39` | `2.50%` | `8.01%` |
| `cap08_primary_rule05_cash10` | `2,268,929.99` | `4.0963` | `-9.8203%` | `39` | `9.98%` | `8.01%` |
| `cap08_primary_rule05_cash10_noinv` | `2,268,770.09` | `4.0963` | `-9.8164%` | `37` | `9.98%` | `8.01%` |
| `cap08_primary_rule05_cash15` | `2,236,428.37` | `4.1423` | `-9.5048%` | `39` | `14.97%` | `8.01%` |
| `cap08_primary_rule05_cash15_noinv` | `2,236,055.08` | `4.1431` | `-9.4977%` | `37` | `14.97%` | `8.01%` |

Decision:

- Keep active meta shadow candidate as `cap08_primary_rule05`.
- Do not switch to cash-floor variants because the return drag is too large for the incremental drawdown improvement.
- Do not apply small-inverse cleanup yet; it reduces rebalances by `2` but gives up a little final value and only marginally improves MDD.
- If a more conservative shadow is needed later, `cap08_primary_rule05_cash10_noinv` is the best risk-balanced fallback, not a primary candidate.

## 9. Advanced Risk Controls Sweep — 2026-06-03

Production remains unchanged.

Follow-up command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --output results/group_a_meta_real_advanced_controls_sweep_20260603.json
```

Tested all remaining proposed controls:

- Trailing stop: reduce `00631L` cap to `3%` after `3%` or `5%` strategy drawdown.
- Momentum cash floor: dynamic cash floor from `0050` MA20/MA60 state.
- Fine TDCC tiering: score `<1.2 => 8%`, `1.2~1.6 => 5%`, `1.6~2.0 => 3%`, `>2.0 => 0%`.
- Conditional `00632R`: only allow inverse if `0050 < MA60` and 5-day return `< -3%`; otherwise remove sub-`1%` inverse allocations.
- Composite score: final value plus Sharpe/MDD bonuses, penalties for low cash and extra rebalances.

Top results on `2025-06-02` to `2026-06-02`:

| Candidate | Final value | Sharpe | MDD | Rebalances | Cash | 00631L | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `adv_conditional_inverse` | `2,309,162.02` | `4.0296` | `-10.2230%` | `39` | `2.74%` | `8.01%` | `2,310,479.98` |
| `cap08_primary_rule05` | `2,308,897.81` | `4.0306` | `-10.2233%` | `39` | `2.50%` | `8.01%` | `2,309,765.48` |
| `adv_stop5_cap03` | `2,305,500.76` | `4.0248` | `-10.3561%` | `40` | `2.50%` | `8.01%` | `2,304,920.57` |
| `adv_momentum_cash` | `2,293,270.70` | `4.0719` | `-10.1129%` | `39` | `2.50%` | `8.01%` | `2,296,333.74` |
| `adv_all_controls` | `2,290,338.44` | `4.0635` | `-10.2491%` | `39` | `2.74%` | `5.01%` | `2,293,318.57` |

Interpretation:

- `adv_conditional_inverse` is the only advanced variant that beats `cap08_primary_rule05` on both final value and composite score.
- It improves final value by `264.21` versus `cap08_primary_rule05` and removes the latest sub-`1%` inverse allocation.
- Trailing stop variants did not help; they either reduced final value or worsened MDD in this window.
- Momentum cash floor improved Sharpe but gave up too much final value.
- Fine TDCC tiering maps the current pressure score (`1.4489`) to a `5%` cap; this underperforms the simpler `8%` fixed cap.
- The full combined control stack is too conservative relative to the return objective.

Shadow signal update:

- `group_a_meta_ensemble_real_config.json` now selects `adv_conditional_inverse`.
- `run_group_a_meta_ensemble_shadow_signal.py` now defaults to `results/group_a_meta_real_advanced_controls_sweep_20260603.json`.
- Latest generated shadow signal for `actual_data_date=2026-06-02`:
  - `0050.TW = 89.25%`, target `8,669` shares
  - `00631L.TW = 8.00%`, target `2,166` shares
  - `00632R.TW = 0.00%`, target `0` shares
  - Cash `2.75%`

Decision:

- Active meta shadow candidate becomes `adv_conditional_inverse`.
- Do not promote to production.
- The improvement is small but directionally cleaner: it removes negligible inverse exposure and slightly improves final value/MDD versus the prior active meta shadow.

## 10. 2008 TWII Proxy Stress Test for Active Meta Shadow — 2026-06-03

Production remains unchanged.

Command:

```bash
python3 backtest_group_a_meta_adv_2008.py
```

Output:

- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_162332.json`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_162332.csv`

Method:

- Replay the canonical Golden1_0531 2008 TWII proxy PVA events and monthly DCA purchases.
- Apply the active shadow profile `adv_conditional_inverse`.
- Because 2008 TDCC history is unavailable, use price-regime risk-off as the overlay trigger.
- A2C/SAC 2008 histories are unavailable; fallback allocation uses PPO where needed.

Result window: `2007-07-02` to `2010-12-31`, `873` rows.

| Strategy | Final value | Sharpe | MDD | Rebalances | Fees | Contribution return |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Golden1_0531_canonical_2008_proxy` | `1,494,398.92` | `0.5724` | `-38.0202%` | `310` | `77,500.50` | `23.5040%` |
| `GroupA_meta_adv_conditional_inverse_2008_proxy` | `1,174,042.62` | `0.3125` | `-55.1801%` | `125` | `12,938.67` | `-2.9717%` |
| `hold_0050` | `1,003,692.60` | `0.0579` | `-58.3081%` | `0` | `0.00` | n/a |
| `blend50` | `899,192.04` | `0.0438` | `-71.8785%` | `0` | `0.00` | n/a |

Delta versus canonical:

- Final value: `-320,356.29`
- Sharpe: `-0.2599`
- MDD: `-17.1599 percentage points`
- Rebalances: `-185`
- Contribution return: `-26.4757 percentage points`

Interpretation:

- The active meta shadow candidate improves the short 2025-2026 real-data window, but fails this 2008 proxy stress test.
- The price-regime proxy spends `289 / 873` rows in risk-off and the replay ends with high cash (`29.16%`), which reduces recovery participation.
- Conditional inverse triggered `15` times and did not compensate for the reduced recovery exposure.
- This is strong evidence to keep `adv_conditional_inverse` as advisory-only and not promote it over canonical Golden1_0531.
- A possible next test is a crisis-specific recovery override: after risk-off clears, force cash below `10%` and restore `00631L` cap faster during MA60 recovery.

## 11. 2008 Recovery Override Sweep — 2026-06-03

Production remains unchanged.

Command:

```bash
python3 backtest_group_a_meta_adv_2008.py
```

Output:

- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_162857.json`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_162857.csv`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_162857_ranking.csv`

Tested:

- Recovery cash cap: force cash down to `10%` or `5%` after `0050 > MA60` and 21-day momentum turns positive.
- Recovery leverage step: during recovery, redeploy cash into `00631L` up to `12%` or `18%`.
- Severe inverse hedge: increase `00632R` to `3%`, `5%`, or `8%` only under crash conditions, including relaxed versions.
- Combo variants combining recovery cash cap, leverage step, and severe inverse.

Top results:

| Variant | Final value | Sharpe | MDD | Rebalances | Cash | 00631L | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `recovery_cash05` | `1,202,791.14` | `0.3383` | `-55.2213%` | `125` | `4.87%` | `16.81%` | Best final value; recovery triggered `61` times. |
| `recovery_leverage_step18` | `1,200,898.00` | `0.3365` | `-55.2178%` | `102` | `9.75%` | `18.38%` | Similar return with fewer rebalances. |
| `combo_cash05_severe05_relaxed` | `1,200,162.87` | `0.3360` | `-55.2207%` | `125` | `4.87%` | `16.81%` | Severe inverse triggered `3` times but reduced final value. |
| `recovery_cash10` | `1,195,753.34` | `0.3322` | `-55.2115%` | `125` | `9.76%` | `16.83%` | Cleaner conservative recovery variant. |
| `adv_conditional_inverse` | `1,174,042.62` | `0.3125` | `-55.1801%` | `125` | `29.16%` | `16.91%` | Current active shadow baseline. |

Interpretation:

- Recovery cash cap is the only useful improvement in this 2008 proxy test.
- `recovery_cash05` improves final value by `28,748.52` versus current `adv_conditional_inverse`, but still trails canonical Golden1_0531 by `291,607.78`.
- `recovery_leverage_step18` is attractive operationally because it gets nearly the same result with `23` fewer rebalances than `recovery_cash05`.
- Severe inverse hedge did not work: strict variants triggered `0` times; relaxed variants triggered `3~5` times but reduced final value and barely changed MDD.
- None of the tested improvements closes the gap versus canonical Golden1_0531, so the conclusion remains: do not promote the meta overlay over production.

Next candidate, if continuing:

- Test a crisis-aware allocator that disables the meta rule sleeve in recovery and reverts to canonical PPO/PVA targets when `0050 > MA60` for `5~10` sessions.

## 12. Corrected 2008 Full Rebalance Event Sweep — 2026-06-03

Production remains unchanged.

Important correction:

- Sections 10 and 11 used a PVA-only event replay and therefore missed most PPO rebalance events.
- This understated the meta overlay in 2008 because canonical Golden1_0531 trades far more often than the `pva_sigmoid_history` subset.
- The corrected sweep below runs the PPO model on the 2008 proxy path, captures every `_rebalance` target, then applies the overlay variants to that full event stream.

Command:

```bash
python3 backtest_group_a_meta_adv_2008.py
```

Output:

- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_163629.json`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_163629.csv`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_163629_ranking.csv`

Base exact capture:

| Strategy | Final value | Sharpe | MDD | Trades/events |
| --- | ---: | ---: | ---: | ---: |
| `Golden1_0531_current_payload_exact_capture` | `1,525,036.08` | `0.5395` | `-50.4417%` | `147` |
| `adv_conditional_inverse` | `1,538,254.19` | `0.6533` | `-47.7594%` | `216` |

Top corrected variants:

| Variant | Final value | Sharpe | MDD | Rebalances | Severe inverse triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `severe_inverse_05_fast` | `1,564,015.00` | `0.6803` | `-46.3644%` | `215` | `27` |
| `severe_inverse_08_relaxed` | `1,561,143.30` | `0.6784` | `-46.2739%` | `217` | `21` |
| `combo_cash05_severe05_relaxed` | `1,558,590.90` | `0.6568` | `-46.8540%` | `217` | `21` |
| `severe_inverse_05_relaxed` | `1,550,682.54` | `0.6670` | `-46.8873%` | `217` | `21` |
| `adv_conditional_inverse` | `1,538,254.19` | `0.6533` | `-47.7594%` | `216` | `9` |

Interpretation:

- Corrected result reverses the PVA-only conclusion: full-event meta overlay improves the current 2008 proxy capture.
- Current `adv_conditional_inverse` improves versus exact-captured base by:
  - Final value: `+13,218.11`
  - Sharpe: `+0.1138`
  - MDD: `+2.6823 percentage points`
- Best corrected candidate is `severe_inverse_05_fast`:
  - Final value improvement versus exact-captured base: `+38,978.92`
  - Sharpe improvement: `+0.1408`
  - MDD improvement: `+4.0773 percentage points`
- Recovery cash controls are no longer the main driver after full event capture; the portfolio already ends near `1.24%` cash.
- Severe inverse works in the corrected flow because full PPO rebalance events create more risk-off opportunities; the fast trigger fires `27` times.

Decision:

- Keep production unchanged.
- Keep current meta shadow advisory-only.
- Add `severe_inverse_05_fast` as the next shadow candidate to test on the real 2025-2026 data window before any config selection change.

## 13. Real-Data Check for 2008 Best Candidate — 2026-06-03

Production remains unchanged.

Requested window: `2025-01-01` to `2026-05-03`.

Actual window: `2025-01-02` to `2026-04-30`, `318` rows.  The local DB/cache only had Group A prices through `2026-04-30` for this run.

Commands:

```bash
python3 backtest_group_a_meta_ensemble_real.py \
  --start 2025-01-01 \
  --end 2026-05-03 \
  --download-end 2026-05-03 \
  --output results/group_a_meta_ensemble_real_backtest_20250101_20260503.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260503.json \
  --output results/group_a_meta_real_riskoff_sweep_20250101_20260503.json
```

Output:

- `results/group_a_meta_ensemble_real_backtest_20250101_20260503.json`
- `results/group_a_meta_ensemble_real_backtest_20250101_20260503.csv`
- `results/group_a_meta_real_riskoff_sweep_20250101_20260503.json`
- `results/group_a_meta_real_riskoff_sweep_20250101_20260503.csv`

Baseline/source results:

| Strategy | Final value | Sharpe | MDD | Trades/rebalances |
| --- | ---: | ---: | ---: | ---: |
| `Golden1_0531_base_exact` | `1,857,045.54` | `2.0948` | `-24.9939%` | `61` |
| `latest_tdcc_overlay` | `1,805,641.42` | `2.1420` | `-24.4224%` | `46` |
| `meta_ensemble_real_source` | `1,827,982.76` | `2.5498` | `-18.1186%` | `87` |

Sweep highlights:

| Variant | Final value | Sharpe | MDD | Rebalances | Cash | Triggers |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `adv_momentum_cash` | `1,823,881.37` | `2.3125` | `-20.9143%` | `68` | `22.06%` | momentum cash `42` |
| `cap08_primary_rule05` | `1,816,440.61` | `2.1844` | `-23.8048%` | `68` | `22.06%` | none |
| `adv_conditional_inverse` | `1,816,208.38` | `2.1829` | `-23.8228%` | `68` | `22.06%` | conditional inverse `8` |
| `severe_inverse_05_fast` | `1,816,208.38` | `2.1829` | `-23.8228%` | `68` | `22.06%` | severe inverse `0` |
| `severe_inverse_08_relaxed` | `1,816,208.38` | `2.1829` | `-23.8228%` | `68` | `22.06%` | severe inverse `0` |

Interpretation:

- `severe_inverse_05_fast` is useful in the corrected 2008 proxy, but it did not trigger at all in this real-data window.
- It produces exactly the same real-window result as `adv_conditional_inverse`, so it is not a real-data improvement by itself.
- `adv_momentum_cash` is the best sweep variant for this real-data window, improving versus latest TDCC by `+18,239.95` and improving MDD by `3.5081 percentage points`.
- However, `adv_momentum_cash` still trails Golden1_0531 base exact by `-33,164.18`, though with better Sharpe and lower MDD.

Decision:

- Do not select `severe_inverse_05_fast` as the active real-data shadow candidate yet.
- If optimizing for stress robustness only, keep it as a 2008 crash-specific guard.
- If optimizing this real-data window, `adv_momentum_cash` is the candidate to compare against the current selected profile.

## 14. Data Completeness Check and Latest Real-Data Rerun — 2026-06-03

Production remains unchanged.

Data refresh/check command:

```bash
python3 refresh_group_data.py \
  --group a \
  --target-date 2026-06-02 \
  --summary-path results/data_refresh_group_a_20260602_check.json
```

Result:

- Status: `already_current`
- Group A raw caches cover `2020-01-02` to `2026-06-02`
- Market caches cover `2020-01-02` to `2026-06-02`
- DuckDB `ohlcv`:
  - `0050.TW`: max `2026-06-02`
  - `00631L.TW`: max `2026-06-02`
  - `00632R.TW`: max `2026-06-02`

Note:

- The prior `2026-05-03` requested end date was a Sunday, so the real-data run correctly stopped at the previous available trading date, `2026-04-30`.
- After confirming data completeness to `2026-06-02`, the real-data window was rerun through `2026-06-03`.

Commands:

```bash
python3 backtest_group_a_meta_ensemble_real.py \
  --start 2025-01-01 \
  --end 2026-06-03 \
  --download-end 2026-06-03 \
  --output results/group_a_meta_ensemble_real_backtest_20250101_20260603.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603.json \
  --output results/group_a_meta_real_riskoff_sweep_20250101_20260603.json
```

Actual window: `2025-01-02` to `2026-06-02`, `340` rows.

Baseline/source results:

| Strategy | Final value | Sharpe | MDD | Trades/rebalances |
| --- | ---: | ---: | ---: | ---: |
| `Golden1_0531_base_exact` | `2,144,019.37` | `2.3827` | `-24.9939%` | `64` |
| `latest_tdcc_overlay` | `2,053,779.30` | `2.4095` | `-24.4224%` | `50` |
| `meta_ensemble_real_source` | `2,068,809.64` | `2.8118` | `-18.1186%` | `93` |

Latest sweep highlights:

| Variant | Final value | Sharpe | MDD | Rebalances | Cash | Triggers |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `adv_momentum_cash` | `2,081,791.81` | `2.5880` | `-20.9143%` | `71` | `30.96%` | momentum cash `42` |
| `cap08_primary_rule05` | `2,073,321.86` | `2.4570` | `-23.8048%` | `71` | `30.96%` | none |
| `adv_conditional_inverse` | `2,073,080.09` | `2.4556` | `-23.8228%` | `71` | `31.21%` | conditional inverse `8` |
| `severe_inverse_05_fast` | `2,073,080.09` | `2.4556` | `-23.8228%` | `71` | `31.21%` | severe inverse `0` |

Interpretation:

- Data is already complete for Group A through `2026-06-02`.
- `severe_inverse_05_fast` still has `0` severe triggers in the latest real-data window and is identical to `adv_conditional_inverse`.
- `adv_momentum_cash` remains the best real-data sweep variant:
  - Versus latest TDCC: `+28,012.52`
  - Versus base exact: `-62,227.56`
  - MDD improves versus base exact by `4.0796 percentage points`
- Base exact still has the highest final value, while meta variants improve risk metrics.

## 15. Combined Momentum-Cash + Severe-Inverse Optimization — 2026-06-03

Production remains unchanged.

Goal:

- Combine the real-data strength of `adv_momentum_cash` with the 2008 crash robustness of `severe_inverse_05_fast`.
- Test whether a single candidate can remain competitive in the latest real-data window and still improve the 2008 proxy stress test.

Code changes:

- Added `combo_momcash_severe03_fast`, `combo_momcash_severe05_fast`, and `combo_momcash_severe08_relaxed`.
- Added the same momentum cash-floor logic to the corrected 2008 proxy replay, so both real-data and stress-test sweeps use comparable controls.

Latest real-data command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603.json \
  --output results/group_a_meta_real_combo_sweep_20250101_20260603.json
```

2008 corrected command:

```bash
python3 backtest_group_a_meta_adv_2008.py \
  --output results/group_a_meta_combo_twii_proxy_2008_20070701_20101231_20260603.json
```

Latest real-data window: `2025-01-02` to `2026-06-02`.

| Variant | Final value | Sharpe | MDD | Rebalances | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `adv_momentum_cash` | `2,081,791.81` | `2.5880` | `-20.9143%` | `71` | Best final value. |
| `combo_momcash_severe05_fast` | `2,081,695.60` | `2.5858` | `-20.9384%` | `67` | Only `-96.22` final value; `4` fewer rebalances; severe inverse `0` triggers. |
| `adv_conditional_inverse` | `2,073,080.09` | `2.4556` | `-23.8228%` | `71` | Current conditional profile. |

2008 corrected proxy:

| Variant | Final value | Sharpe | MDD | Rebalances | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `severe_inverse_05_fast` | `1,564,015.00` | `0.6803` | `-46.3644%` | `215` | Best final value in 2008. |
| `combo_momcash_severe05_fast` | `1,547,440.28` | `0.6772` | `-45.5268%` | `215` | Better MDD than severe-only, but `-16,574.71` final value. |
| `adv_conditional_inverse` | `1,538,254.19` | `0.6533` | `-47.7594%` | `216` | Current conditional profile. |

Interpretation:

- `combo_momcash_severe05_fast` is the best balanced candidate so far.
- In real data, it is practically tied with `adv_momentum_cash` on final value and Sharpe, while reducing rebalances from `71` to `67`.
- In 2008, it sacrifices return versus `severe_inverse_05_fast`, but improves MDD to `-45.5268%`, the best drawdown among the compared candidates.
- Severe inverse still does not trigger in the latest real-data window, so its value is purely crash-regime optionality.

Decision:

- Do not promote production.
- For a balanced shadow candidate, prefer `combo_momcash_severe05_fast`.
- For latest-window return only, prefer `adv_momentum_cash`.
- For 2008 final value only, prefer `severe_inverse_05_fast`.

## 16. LLM Sentiment Filled to 2026-06-03 — 2026-06-03

Production remains unchanged.

Reason:

- Previous LLM sentiment feature file only covered through `2026-05-20`.
- The market/price data already covered through `2026-06-02`, so the latest real-data replay had neutral `0.0` LLM values after `2026-05-20`.

Refresh commands:

```bash
python3 fetch_ltn_news_jsonl.py \
  --keyword 台股 \
  --start-date 2026-05-21 \
  --end-date 2026-06-03 \
  --max-pages 20 \
  --sleep-ms 300 \
  --output ../news/ltn_mainstream_2026-05-21_to_2026-06-03.jsonl \
  --verbose

python3 prepare_ltn_llm_sentiment_bundle.py \
  --input-dir ../news \
  --merged-output data/news/liberty_times/ltn_mainstream_202002_20260603_merged.jsonl \
  --sentiment-output FinRL/data/sentiment/llm_market_sentiment_daily.csv \
  --metadata-output data/news/liberty_times/ltn_mainstream_202002_20260603_metadata.json \
  --mode rule_based \
  --text-columns title,snippet
```

Refresh result:

- New LTN fetch: `400` records from `2026-05-21` to `2026-06-03`.
- Merged LTN bundle: `79` source files, `13,946` merged rows.
- `FinRL/data/sentiment/llm_market_sentiment_daily.csv`: `2,275` rows, date range `2020-02-01` to `2026-06-03`.
- Newly populated sentiment dates after the old cutoff: `2026-05-21` to `2026-05-27`, and `2026-06-03`.
- Note: this used the repo's existing `rule_based` sentiment builder, not an external OpenAI/API LLM scoring call.

Rerun commands:

```bash
python3 backtest_group_a_meta_ensemble_real.py \
  --start 2025-01-01 \
  --end 2026-06-03 \
  --download-end 2026-06-03 \
  --output results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json \
  --output results/group_a_meta_real_combo_sweep_20250101_20260603_llmfilled.json
```

Actual replay window: `2025-01-02` to `2026-06-02`, `340` rows.

Source replay, before vs after LLM fill:

| Source | Final value | Sharpe | MDD | Rebalances | Final cash |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before LLM fill | `2,068,809.64` | `2.8118` | `-18.1186%` | `93` | `43.93%` |
| After LLM fill | `2,078,857.64` | `2.8180` | `-18.1186%` | `93` | `39.93%` |

Latest sweep after LLM fill:

| Variant | Final value | Sharpe | MDD | Rebalances | Final cash | Composite score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `adv_momentum_cash` | `2,101,933.92` | `2.6029` | `-20.9143%` | `71` | `11.98%` | `2,110,467.19` |
| `combo_momcash_severe05_fast` | `2,101,836.77` | `2.6007` | `-20.9384%` | `67` | `12.23%` | `2,114,232.27` |
| `cap08_primary_rule05` | `2,093,382.04` | `2.4730` | `-23.8048%` | `71` | `11.98%` | `2,091,948.07` |
| `adv_conditional_inverse` | `2,093,137.92` | `2.4716` | `-23.8228%` | `71` | `12.23%` | `2,091,613.67` |
| `severe_inverse_05_fast` | `2,093,137.92` | `2.4716` | `-23.8228%` | `71` | `12.23%` | `2,091,613.67` |

Interpretation:

- LLM fill improved the latest-window source replay by `+10,048.00` final value without changing MDD.
- In the sweep, `adv_momentum_cash` remains the best by final value.
- `combo_momcash_severe05_fast` remains the best balanced/composite candidate and is only `-97.15` behind `adv_momentum_cash` by final value, with `4` fewer rebalances.
- `severe_inverse_05_fast` still has `0` severe triggers in the latest real-data window, so its advantage remains a 2008/crash-regime property.

## 17. One-by-One Improvement Sweep — LLM, Momentum Cash, Crash Gate — 2026-06-03

Production remains unchanged.

### 17.1 True LLM Scoring Check

The pipeline already supports `openai_compatible` mode through `build_llm_sentiment_features.py` and `prepare_ltn_llm_sentiment_bundle.py`.

Environment check:

- `OPENAI_API_KEY`: missing
- `OPENAI_MODEL`: missing
- `OPENAI_BASE_URL`: missing

Decision:

- True external LLM scoring cannot be executed in this environment yet.
- Keep the current filled file as rule-based LTN sentiment.
- Revisit once an API key/model/base URL is available.

### 17.2 Momentum Cash Floor Sweep

Code change:

- Parameterized momentum cash floor values in `evaluate_group_a_meta_real_riskoff_sweep.py`.
- Added:
  - `adv_momcash_light_12_08`
  - `adv_momcash_mid_18_12`
  - `adv_momcash_high_22_15`
  - `adv_momcash_base05_15_10`
- Mirrored comparable variants in `backtest_group_a_meta_adv_2008.py`.

Latest real-data command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json \
  --output results/group_a_meta_real_momcash_floor_sweep_20250101_20260603_llmfilled.json
```

Latest real-data results:

| Variant | Final value | Sharpe | MDD | Rebalances | Composite score |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adv_momcash_mid_18_12` | `2,102,547.66` | `2.6328` | `-20.2125%` | `71` | `2,113,415.68` |
| `adv_momentum_cash` | `2,101,933.92` | `2.6029` | `-20.9143%` | `71` | `2,110,467.19` |
| `adv_momcash_high_22_15` | `2,099,950.03` | `2.6695` | `-19.2719%` | `71` | `2,113,784.03` |
| `adv_momcash_light_12_08` | `2,101,225.14` | `2.5727` | `-21.6124%` | `71` | `2,107,410.47` |

Interpretation:

- `adv_momcash_mid_18_12` is the best latest-window return improvement:
  - Versus `adv_momentum_cash`: `+613.74` final value, Sharpe `+0.0298`, MDD improves by `0.7018 percentage points`.
- `adv_momcash_high_22_15` has the best MDD/Sharpe among pure momentum-cash variants, but gives up `2,547.63` final value versus `adv_momcash_mid_18_12`.

2008 stress command:

```bash
python3 backtest_group_a_meta_adv_2008.py \
  --output results/group_a_meta_momcash_floor_twii_proxy_2008_20070701_20101231_20260603.json
```

2008 stress results:

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `momentum_cash` | `1,521,155.10` | `0.6488` | `-46.9840%` | `216` |
| `momcash_mid_18_12` | `1,516,395.79` | `0.6469` | `-46.8048%` | `216` |
| `momcash_high_22_15` | `1,509,108.94` | `0.6436` | `-46.5640%` | `216` |
| `combo_momcash_severe05_fast` | `1,547,440.28` | `0.6772` | `-45.5268%` | `215` |
| `severe_inverse_05_fast` | `1,564,015.00` | `0.6803` | `-46.3644%` | `215` |

Interpretation:

- Pure momentum cash floor tuning helps latest data, but does not beat severe/combo variants in 2008.
- `adv_momcash_mid_18_12` is useful as a latest-window return candidate, not as the balanced candidate.

### 17.3 Crash Gate / Severe Inverse Weight Sweep

Code change:

- Added severe inverse fast/strict variants:
  - `severe_inverse_08_fast`
  - `severe_inverse_10_fast`
  - `severe_inverse_05_crash_strict`
  - `combo_momcash_severe08_fast`
  - `combo_momcash_severe10_fast`

Latest real-data command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json \
  --output results/group_a_meta_real_crashgate_sweep_20250101_20260603_llmfilled.json
```

Latest real-data result:

- Severe inverse triggers remained `0`.
- `combo_momcash_severe05_fast`, `combo_momcash_severe08_fast`, and `combo_momcash_severe10_fast` were identical in the latest window:
  - final `2,101,836.77`
  - Sharpe `2.6007`
  - MDD `-20.9384%`
  - rebalances `67`

2008 stress command:

```bash
python3 backtest_group_a_meta_adv_2008.py \
  --output results/group_a_meta_crashgate_twii_proxy_2008_20070701_20101231_20260603.json
```

2008 stress results:

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `severe_inverse_05_fast` | `1,564,015.00` | `0.6803` | `-46.3644%` | `215` |
| `severe_inverse_08_fast` | `1,581,376.75` | `0.6985` | `-45.4746%` | `215` |
| `severe_inverse_10_fast` | `1,592,949.60` | `0.7106` | `-44.8777%` | `215` |
| `combo_momcash_severe05_fast` | `1,547,440.28` | `0.6772` | `-45.5268%` | `215` |
| `combo_momcash_severe08_fast` | `1,564,586.41` | `0.6959` | `-44.6244%` | `215` |
| `combo_momcash_severe10_fast` | `1,576,015.08` | `0.7084` | `-44.0192%` | `215` |

Interpretation:

- `severe_inverse_10_fast` is now the best 2008 final-value candidate.
- `combo_momcash_severe10_fast` is the best balanced candidate so far:
  - Latest real-data: identical to combo05 because severe trigger count is `0`.
  - 2008: improves versus combo05 by `+28,574.80` final value and MDD by `1.5076 percentage points`.
  - It also has better 2008 MDD than severe-only `severe_inverse_10_fast`, while giving up `16,934.52` final value.

Updated decision:

- Latest-window return only: `adv_momcash_mid_18_12`.
- Latest-window MDD/Sharpe only: `adv_momcash_high_22_15`.
- 2008 final value only: `severe_inverse_10_fast`.
- Balanced shadow candidate: `combo_momcash_severe10_fast`.
- Do not promote production until 2020 and 2022 stress tests are added.

## 18. 2020 / 2022 Stress Checks — 2026-06-03

Production remains unchanged.

Important caveat:

- These are stress/in-sample behavior checks because the shadow models were trained on the 2020-2023 era.
- Use them to inspect crash/bear-market behavior, not as clean OOS evidence.

### 18.1 2020 COVID Crash Check

Commands:

```bash
python3 backtest_group_a_meta_ensemble_real.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --download-end 2020-12-31 \
  --output results/group_a_meta_ensemble_real_backtest_20200101_20201231_llmfilled.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20200101_20201231_llmfilled.json \
  --output results/group_a_meta_real_crashgate_sweep_20200101_20201231_llmfilled.json
```

Source replay:

| Strategy | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `base_exact` | `1,332,698.12` | `1.5146` | `-21.5747%` | n/a |
| `meta_ensemble_real_source` | `1,356,193.31` | `1.9187` | `-17.3977%` | `56` |

Sweep highlights:

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `adv_momcash_high_22_15` | `1,325,460.39` | `1.7740` | `-16.4915%` | `56` |
| `adv_momcash_mid_18_12` | `1,321,111.68` | `1.7345` | `-17.4377%` | `56` |
| `adv_momentum_cash` | `1,317,844.83` | `1.7043` | `-18.1436%` | `56` |
| `combo_momcash_severe10_fast` | `1,316,987.81` | `1.6996` | `-18.1960%` | `54` |

Interpretation:

- Severe inverse did not differentiate variants in 2020.
- `adv_momcash_high_22_15` is the best 2020 sweep candidate and improves MDD versus the source replay, but gives up source final value.
- COVID-style fast crash/rebound favors a stronger momentum cash floor, not inverse exposure.

### 18.2 2022 Bear-Market Check

Commands:

```bash
python3 backtest_group_a_meta_ensemble_real.py \
  --start 2022-01-01 \
  --end 2022-12-31 \
  --download-end 2022-12-31 \
  --output results/group_a_meta_ensemble_real_backtest_20220101_20221231_llmfilled.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20220101_20221231_llmfilled.json \
  --output results/group_a_meta_real_crashgate_sweep_20220101_20221231_llmfilled.json
```

Source replay:

| Strategy | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `base_exact` | `761,708.80` | `-1.4456` | `-32.2567%` | n/a |
| `meta_ensemble_real_source` | `813,251.99` | `-1.2607` | `-26.6468%` | `44` |

Sweep highlights:

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `adv_momcash_high_22_15` | `757,137.24` | `-1.6828` | `-30.5783%` | `43` |
| `adv_momcash_mid_18_12` | `748,734.62` | `-1.6797` | `-31.6201%` | `43` |
| `adv_momentum_cash` | `742,560.08` | `-1.6763` | `-32.3898%` | `43` |
| `combo_momcash_severe10_fast` | `741,817.26` | `-1.6785` | `-32.4584%` | `36` |

Interpretation:

- Severe inverse again did not differentiate variants.
- `adv_momcash_high_22_15` is the best sweep variant for 2022, but the source meta replay is materially better than all overlay variants.
- This argues against promoting any sweep overlay purely from 2022 behavior.

Updated cross-window view:

| Objective | Current best |
| --- | --- |
| Latest 2025-2026 final value | `adv_momcash_mid_18_12` |
| Latest 2025-2026 MDD/Sharpe | `adv_momcash_high_22_15` |
| 2008 final value | `severe_inverse_10_fast` |
| 2008 balanced final+MDD | `combo_momcash_severe10_fast` |
| 2020 stress sweep | `adv_momcash_high_22_15` |
| 2022 stress sweep | `adv_momcash_high_22_15`, but source meta replay is better |

Decision:

- Best new practical improvement: keep `combo_momcash_severe10_fast` as the balanced crash-aware shadow candidate.
- Also track `adv_momcash_high_22_15` as a defensive cash-floor candidate because it wins 2020 and 2022 sweep behavior.
- Do not promote production. The evidence is mixed across windows, and the 2020/2022 checks are not clean OOS.

## 19. Adaptive Selector + Price-Decoupled Severe Trigger — 2026-06-03

Production remains unchanged.

Goal:

- Direction 1: make the overlay adaptive instead of using a single static momentum-cash floor.
- Direction 2: decouple `severe_inverse` from TDCC/risk-off state so price crashes can trigger inverse protection directly.

Code changes:

- `evaluate_group_a_meta_real_riskoff_sweep.py`
  - Added `adaptive_momentum_cash`.
  - Added `severe_price_only`.
  - Added `adaptive_momcash_price_severe10`.
  - Added `adaptive_high_price_severe10`.
- `backtest_group_a_meta_adv_2008.py`
  - Mirrored the adaptive and price-decoupled severe trigger logic.

Adaptive logic:

- `adaptive_momcash_price_severe10`
  - Normal floor profile: mid momentum cash (`18% / 12% / 2.5%`).
  - If price is below MA60 and 20-day return is worse than `-3%`, use high floor behavior.
  - Severe inverse can trigger when:
    - price is below MA60,
    - 5-day return < `-2%`,
    - 20-day return < `-5%`,
    - regardless of TDCC state.
- `adaptive_high_price_severe10`
  - Same price-decoupled severe trigger.
  - Higher defensive cash floor (`22% / 15% / 2.5%`).

Latest real-data command:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json \
  --output results/group_a_meta_real_adaptive_price_severe_sweep_20250101_20260603_llmfilled.json
```

Latest real-data results:

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_momcash_price_severe10` | `2,118,915.31` | `2.7454` | `-17.7391%` | `71` | `9` |
| `adaptive_high_price_severe10` | `2,114,372.47` | `2.7625` | `-17.3970%` | `70` | `9` |
| `adv_momcash_mid_18_12` | `2,102,547.66` | `2.6328` | `-20.2125%` | `71` | `0` |
| `combo_momcash_severe10_fast` | `2,101,836.77` | `2.6007` | `-20.9384%` | `67` | `0` |

2008 proxy stress:

```bash
python3 backtest_group_a_meta_adv_2008.py \
  --output results/group_a_meta_adaptive_price_severe_twii_proxy_2008_20070701_20101231_20260603.json
```

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `severe_inverse_10_fast` | `1,592,949.60` | `0.7106` | `-44.8777%` | `215` |
| `adaptive_momcash_price_severe10` | `1,586,106.77` | `0.7226` | `-43.1473%` | `215` |
| `adaptive_high_price_severe10` | `1,572,557.08` | `0.7132` | `-43.1362%` | `214` |
| `combo_momcash_severe10_fast` | `1,576,015.08` | `0.7084` | `-44.0192%` | `215` |

2020 stress:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20200101_20201231_llmfilled.json \
  --output results/group_a_meta_real_adaptive_price_severe_sweep_20200101_20201231_llmfilled.json
```

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_high_price_severe10` | `1,348,056.63` | `1.8825` | `-14.8815%` | `55` | `7` |
| `adaptive_momcash_price_severe10` | `1,344,189.79` | `1.8534` | `-15.2584%` | `57` | `7` |
| `adv_momcash_high_22_15` | `1,325,460.39` | `1.7740` | `-16.4915%` | `56` | `0` |
| `combo_momcash_severe10_fast` | `1,316,987.81` | `1.6996` | `-18.1960%` | `54` | `0` |

2022 stress:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20220101_20221231_llmfilled.json \
  --output results/group_a_meta_real_adaptive_price_severe_sweep_20220101_20221231_llmfilled.json
```

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_high_price_severe10` | `758,270.26` | `-1.7270` | `-30.3126%` | `43` | `23` |
| `adv_momcash_high_22_15` | `757,137.24` | `-1.6828` | `-30.5783%` | `43` | `0` |
| `adaptive_momcash_price_severe10` | `752,045.73` | `-1.7413` | `-30.9658%` | `52` | `23` |
| `combo_momcash_severe10_fast` | `741,817.26` | `-1.6785` | `-32.4584%` | `36` | `0` |

Interpretation:

- Decoupling severe inverse from TDCC/risk-off state worked: severe triggers now appear in latest data, 2020, and 2022.
- `adaptive_momcash_price_severe10` is the best latest-window and strong 2008 return candidate.
- `adaptive_high_price_severe10` is the best defensive candidate across 2020 and 2022, and it has the best latest-window MDD among the adaptive candidates.
- In 2022, `adaptive_high_price_severe10` improves final value and MDD versus `adv_momcash_high_22_15`, but Sharpe/composite is slightly worse.

Updated decision:

- Best return-oriented shadow candidate: `adaptive_momcash_price_severe10`.
- Best defense-oriented shadow candidate: `adaptive_high_price_severe10`.
- Prior balanced candidate `combo_momcash_severe10_fast` is now superseded by the adaptive price-severe variants.
- Production still remains unchanged until this adaptive logic is converted into the live shadow signal path and observed out-of-sample.

## 20. Adaptive Micro-Tuning — 2026-06-03

Production remains unchanged.

Goal:

- Fine-tune only the adaptive variants from Section 19.
- Test whether inverse weight, trigger strictness, or a middle cash-floor profile improves the current adaptive candidates.

Code changes:

- Added adaptive micro variants in both real and 2008 proxy sweep scripts:
  - `adaptive_momcash_price_severe08`
  - `adaptive_momcash_price_severe12`
  - `adaptive_momcash_price_severe10_soft`
  - `adaptive_momcash_price_severe10_strict`
  - `adaptive_balanced20_13_price_severe10`

Commands:

```bash
python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20250101_20260603_llmfilled.json \
  --output results/group_a_meta_real_adaptive_micro_sweep_20250101_20260603_llmfilled.json

python3 backtest_group_a_meta_adv_2008.py \
  --output results/group_a_meta_adaptive_micro_twii_proxy_2008_20070701_20101231_20260603.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20200101_20201231_llmfilled.json \
  --output results/group_a_meta_real_adaptive_micro_sweep_20200101_20201231_llmfilled.json

python3 evaluate_group_a_meta_real_riskoff_sweep.py \
  --source results/group_a_meta_ensemble_real_backtest_20220101_20221231_llmfilled.json \
  --output results/group_a_meta_real_adaptive_micro_sweep_20220101_20221231_llmfilled.json
```

Latest 2025-2026:

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_momcash_price_severe12` | `2,122,846.01` | `2.7607` | `-17.5283%` | `71` | `9` |
| `adaptive_momcash_price_severe10` | `2,118,915.31` | `2.7454` | `-17.7391%` | `71` | `9` |
| `adaptive_high_price_severe10` | `2,114,372.47` | `2.7625` | `-17.3970%` | `70` | `9` |
| `adaptive_balanced20_13_price_severe10` | `2,118,184.20` | `2.7534` | `-17.5699%` | `71` | `9` |

2008 proxy stress:

| Variant | Final value | Sharpe | MDD | Rebalances |
| --- | ---: | ---: | ---: | ---: |
| `adaptive_momcash_price_severe12` | `1,607,687.75` | `0.7465` | `-41.9752%` | `215` |
| `severe_inverse_10_fast` | `1,592,949.60` | `0.7106` | `-44.8777%` | `215` |
| `adaptive_momcash_price_severe10` | `1,586,106.77` | `0.7226` | `-43.1473%` | `215` |
| `adaptive_high_price_severe10` | `1,572,557.08` | `0.7132` | `-43.1362%` | `214` |

2020 stress:

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_high_price_severe10` | `1,348,056.63` | `1.8825` | `-14.8815%` | `55` | `7` |
| `adaptive_momcash_price_severe12` | `1,347,827.21` | `1.8661` | `-15.0191%` | `57` | `7` |
| `adaptive_balanced20_13_price_severe10` | `1,345,787.53` | `1.8660` | `-15.0859%` | `57` | `7` |
| `adaptive_momcash_price_severe10` | `1,344,189.79` | `1.8534` | `-15.2584%` | `57` | `7` |

2022 stress:

| Variant | Final value | Sharpe | MDD | Rebalances | Severe triggers |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive_high_price_severe10` | `758,270.26` | `-1.7270` | `-30.3126%` | `43` | `23` |
| `adv_momcash_high_22_15` | `757,137.24` | `-1.6828` | `-30.5783%` | `43` | `0` |
| `adaptive_balanced20_13_price_severe10` | `754,751.35` | `-1.7374` | `-30.6418%` | `52` | `23` |
| `adaptive_momcash_price_severe12` | `752,285.01` | `-1.7467` | `-30.9435%` | `52` | `23` |

Interpretation:

- Increasing severe inverse from `10%` to `12%` improves both latest-window and 2008 results.
- `adaptive_momcash_price_severe12` becomes the best return-oriented and 2008-stress candidate.
- `adaptive_high_price_severe10` remains the better defense-oriented candidate for 2020/2022 and latest-window MDD.
- Soft trigger is identical to the current 10% version in the tested windows; strict trigger hurts 2022 and does not improve enough elsewhere.
- `adaptive_balanced20_13_price_severe10` is stable but does not beat the two leaders.

Updated decision:

- Best return / 2008 candidate: `adaptive_momcash_price_severe12`.
- Best defensive candidate: `adaptive_high_price_severe10`.
- Do not promote production. Next useful step is to convert both into live shadow profiles and compare daily drift out-of-sample.
