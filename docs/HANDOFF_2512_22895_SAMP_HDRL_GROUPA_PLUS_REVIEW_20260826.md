# Handoff: 2512.22895 SAMP-HDRL for GroupA+

Date: 2026-08-26  
Paper: `C:/Users/isaac/Downloads/2512.22895.pdf`  
Title: `SAMP-HDRL: Segmented Allocation with Momentum-Adjusted Utility for Multi-agent Portfolio Management via Hierarchical Deep Reinforcement Learning`

## Decision

Do not change the latest live strategy.

Latest strategy remains:

- `a2118_a2111_ncf_late_bull_deleverage`

Do not import now:

- full hierarchical DRL allocator
- DDPG/HDRL target-weight generation
- automatic dynamic clustering that overrides A21.18 regime constraints
- SHAP as a live causal gate
- softmax capital allocator as the live cash/ETF decision engine

## Paper Summary

The paper proposes SAMP-HDRL:

- dynamic K-means asset grouping into two asset buckets;
- upper-level agent for global market information;
- lower-level agents for mask-constrained intra-group allocation;
- utility-based allocation across risk-free asset and two risky groups;
- momentum-adjusted utility and rebound detection;
- SHAP analysis for post-hoc interpretability.

The paper reports outperformance across 2019-2021 market regimes versus traditional and DRL baselines, with ablations supporting upper-lower coordination, dynamic clustering, and capital allocation.

## Transferable Ideas

Useful for GroupA+ as review/shadow design:

1. Dynamic two-bucket grouping  
   Use rolling Sortino, downside volatility, momentum, and stress-correlation to classify GroupA+ assets or fifth-asset candidates into quality/ordinary buckets.

2. Mask-constrained allocation  
   Reinforces existing regime constraints: golden1 should not freely mix inverse and leveraged long sleeves without a policy reason.

3. Hierarchical cash/risky budget  
   Keep cash/risk-budget decision separate from ETF selection. This supports current A21.18 guarded cash behavior.

4. Momentum/rebound gate  
   Before adding 00631L, distinguish real rebound from technical bounce. This is a possible shadow gate, not a live allocator.

5. Explainability audit  
   Use attribution-style reporting to explain why 0050, 00631L, 00632R, and cash sleeves are active.

## Why No Live Change

GroupA+ is a small constrained ETF/cash regime strategy, not a broad stock-universe portfolio. Dynamic clustering has much less benefit with four ETFs plus cash.

The paper itself lists limitations:

- staged rather than strictly end-to-end optimization;
- missing explicit inter-cluster dependency modeling;
- SHAP is post-hoc, not causal or real-time;
- evaluation is mostly price-based and lacks broader signals;
- future work still needs more realistic transaction, liquidity, and slippage treatment.

Current GroupA+ live issue is not missing model complexity. The practical issue is exposure clarity: 00631L and 00632R can appear together, creating offsetting leveraged/inverse exposure. SAMP-HDRL does not solve that directly unless imported as constraints and review diagnostics.

## Recommended Shadow Experiments

Only if reopened:

1. `samp_hdrl_dynamic_bucket_shadow`  
   Rolling two-bucket classification for GroupA+ assets/candidates. No weight changes.

2. `samp_hdrl_rebound_gate_00631l_shadow`  
   Check whether 00631L additions work better only after true rebound signals.

3. `samp_hdrl_cash_temperature_shadow`  
   Compare current cash/risky sleeve against a temperature-scaled diagnostic. Shadow only.

4. `samp_hdrl_explainability_daily_audit`  
   Daily sleeve attribution: 0050 core, 00631L leverage, 00632R hedge, cash defense.

## Artifact

- `report/group_a_plus/latest/2512_22895_samp_hdrl_readiness_review.json`
- `report/group_a_plus/latest/2512_22895_dynamic_bucket_shadow.json`
- `report/group_a_plus/latest/2512_22895_rebound_gate_00631l_shadow.json`
- `report/group_a_plus/latest/2512_22895_cash_temperature_shadow.json`
- `report/group_a_plus/latest/2512_22895_explainability_daily_audit.json`
- `report/group_a_plus/latest/2512_22895_inter_cluster_dependency_shadow.json`
- `report/group_a_plus/latest/2512_22895_promotion_review.json`

## Experiment Update: Dynamic Bucket Shadow

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_dynamic_bucket_shadow.py
```

Latest data date:

- `2026-08-25`

Latest 75-trading-day bucket result:

- quality: `0050.TW`, `00631L.TW`
- ordinary: `00632R.TW`, `00679B.TWO`

Latest feature notes:

- `00631L.TW` has strong 20d momentum but weak 60d momentum and high downside volatility.
- `00632R.TW` is not a quality growth asset, but it has strong negative stress correlation versus `0050.TW`, so it can still be a hedge candidate.
- `00679B.TWO` is weak on this window and does not improve the current latest strategy.
- Cluster quality scores were tied (`0.625` vs `0.625`), so K-means separation is weak with only four active ETFs.

Decision:

- `supports_new_00631l_add = true`
- `supports_00632r_hedge = true`
- `ambiguous_leverage_inverse_mix = true`
- `target_weight_change_allowed = false`
- `production_effect = none`

Interpretation:

This confirms the current live ambiguity. The market structure supports a bullish core (`0050`/`00631L`) and also supports a hedge (`00632R`) because downside stress correlation is negative. It does not resolve whether both should be added aggressively at the same time. Therefore this shadow is useful for explanation, but not strong enough for promotion.

## Experiment Update: 00631L Rebound Gate Shadow

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_rebound_gate_00631l_shadow.py
```

Imported paper idea:

- momentum-adjusted utility with rebound detection;
- fixed shadow rule only, no parameter sweep.

Fixed rule:

- prior 3-day 00631L mean return below `-0.3%`;
- latest 2 daily returns both positive;
- 0050 5d return not worse than `-3%`;
- 00631L vs 0050 5d spread not worse than `-3%`.

Latest result for 2026-08-25:

- `latest_true_rebound_gate = false`
- prior decline mean: `0.0448%`
- recent rebound minimum daily return: `-2.0953%`
- 0050 5d return: `-0.4766%`
- 00631L 5d return: `-0.3735%`

Historical forward result:

- rebound events: `146`
- rebound event mean 20d 00631L excess vs 0050: `+1.36%`
- rebound event win rate vs 0050: `56.85%`
- rebound event bad 20d MDD <= -5% rate: `71.92%`
- non-rebound mean 20d 00631L excess vs 0050: `+2.21%`
- non-rebound win rate vs 0050: `66.25%`

Decision:

- `rebound_gate_has_forward_value = false`
- `supports_new_00631l_add_today = false`
- `target_weight_change_allowed = false`
- `production_effect = none`

Interpretation:

This simple rebound gate does not add useful information. It finds enough historical events, but the selected events are not better than non-events and drawdown risk stays high. It should not be used to justify adding 00631L today.

## Experiment Update: Cash Temperature Shadow

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_cash_temperature_shadow.py
```

Imported paper idea:

- treat risk-free/cash as a baseline asset;
- use a temperature-scaled capital allocation diagnostic between cash and risky sleeve;
- no optimization, no live allocator, no target-weight change.

Live input:

- live cash weight: `20.8159%`
- risky sleeve after removing cash:
  - `0050.TW`: `59.3553%`
  - `00631L.TW`: `9.4204%`
  - `00632R.TW`: `31.2242%`

Latest 75-day risky-sleeve metrics:

- mean daily return: `0.0601%`
- daily volatility: `1.0647%`
- downside volatility: `0.8844%`
- 20d momentum: `3.5415%`
- Sortino: `0.0680`

Temperature diagnostics:

- T=0.50 diagnostic cash: `32.3184%`
- T=0.75 diagnostic cash: `37.9238%`
- T=1.00 diagnostic cash: `40.8640%`
- T=1.50 diagnostic cash: `43.8712%`
- T=2.00 diagnostic cash: `45.3932%`

Decision:

- `live_cash_bias = live_cash_lower_than_diagnostic`
- `supports_increasing_cash = true`
- `supports_decreasing_cash = false`
- `target_weight_change_allowed = false`
- `production_effect = none`

Interpretation:

This shadow supports the manual conservative interpretation: the live cash weight near `20.8%` is lower than the paper-inspired cash/risky diagnostic range of roughly `32%` to `45%`. It does not authorize a live strategy change, but it supports using higher cash in a discretionary conservative execution plan.

## Experiment Update: Explainability Daily Audit

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_explainability_daily_audit.py
```

Imported paper idea:

- explain hierarchical sleeve decisions;
- use an attribution-style audit instead of importing post-hoc SHAP as a live gate.

Inputs:

- latest live signal: `results/group_a_combined_live_latest.json`
- 0050 NCF debug output: `results/ncf_0050_latest_20260826_debug.json`
- 00631L NCF debug output: `results/ncf_00631l_latest_20260826_debug.json`
- 2512.22895 dynamic bucket shadow;
- 2512.22895 rebound gate shadow;
- 2512.22895 cash temperature shadow.

Latest live exposure:

- 0050 target: `47.0000%`
- 00631L target: `7.4595%`
- 00632R target: `24.7246%`
- cash target: `20.8159%`
- approximate long exposure: `61.9190%`
- approximate hedge exposure: `24.7246%`
- approximate net directional exposure: `37.1943%`

Sleeve audit:

- `0050_core`: neutral-to-mild bullish. 0050 NCF is UP but confidence is only `0.4823`.
- `00631L_leverage`: do not add aggressively. 00631L NCF is strong, but rebound gate is false today.
- `00632R_hedge`: hedge has a reason, but size needs manual review because it will drag if Taiwan market rises.
- `cash_defense`: cash is likely low for conservative execution because cash-temperature diagnostic is about `40.8640%` versus live `20.8159%`.

Decision:

- `overall_view = ambiguous_leverage_inverse_mix_prefer_conservative_cash`
- `is_clean_bullish_signal = false`
- `is_clean_bearish_signal = false`
- `supports_00631l_aggressive_add = false`
- `supports_00632r_as_hedge = true`
- `supports_more_cash_for_conservative_execution = true`
- `target_weight_change_allowed = false`
- `production_effect = none`

Interpretation:

This audit converts the paper's hierarchical interpretability idea into a practical daily GroupA+ diagnostic. It confirms that today's signal is not clean bullish or bearish. It is a bullish core plus hedge, with enough ambiguity to prefer conservative execution and more cash.

## Experiment Update: Inter-Cluster Dependency Shadow

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_inter_cluster_dependency_shadow.py
```

Imported paper limitation:

- The paper notes that dynamic clustering does not explicitly capture inter-cluster dependencies.
- For GroupA+, this matters because `quality = 0050/00631L` and `ordinary = 00632R/00679B` may diversify or hedge the quality sleeve.

Latest window:

- window: `2026-05-12` to `2026-08-25`
- quality bucket: `0050.TW`, `00631L.TW`
- ordinary bucket: `00632R.TW`, `00679B.TWO`

Cluster-level dependency:

- ordinary corr between quality and ordinary sleeves: `-0.9551`
- downside semi-corr: `-0.3667`
- stress corr when 0050 < 0: `-0.9502`
- stress corr when 0050 < -1%: `-0.9753`

Pair-level notes:

- `0050.TW` vs `00632R.TW`
  - ordinary corr: `-0.9809`
  - stress corr when 0050 < 0: `-0.9575`
  - stress corr when 0050 < -1%: `-0.9623`
  - interpretation: strong hedge relationship.
- `0050.TW` vs `00679B.TWO`
  - ordinary corr: `0.1108`
  - stress corr when 0050 < 0: `-0.3626`
  - stress corr when 0050 < -1%: `-0.3936`
  - interpretation: weak-to-moderate defensive diversifier, not a strong hedge.
- `00631L.TW` vs `00632R.TW`
  - ordinary corr: `-0.9942`
  - stress corr when 0050 < 0: `-0.9845`
  - interpretation: 00632R hedges 00631L very directly, but this also confirms the cost of holding both sides.

Decision:

- `supports_00632r_hedge = true`
- `supports_00679b_as_defensive_diversifier = true`
- `target_weight_change_allowed = false`
- `production_effect = none`

Interpretation:

This experiment supports the existence of a hedge/diversification role for the ordinary bucket. It strengthens the explanation for why `00632R` can appear as hedge. It does not justify a large `00632R` position by itself, and it does not justify buying `00679B` today because the live strategy gives `00679B` zero and the diversifier signal is only moderate.

## Promotion Review

Completed on 2026-08-26.

Command:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_promotion_review.py
```

Decision:

- `promote_any_component_to_live_strategy = false`
- `change_latest_strategy = false`
- `latest_strategy_after_review = a2118_a2111_ncf_late_bull_deleverage`
- `target_weight_change_allowed = false`
- `train_hdrl_or_ddpg_now = false`
- `allow_auto_rebalance = false`
- `production_effect = none`

Retained:

- dynamic bucket shadow: useful for explanation, not trading;
- explainability daily audit: useful for interpreting ambiguous sleeves;
- inter-cluster dependency shadow: useful for hedge/diversifier diagnostics;
- cash temperature shadow: useful as conservative discretionary cash reference.

Rejected for promotion:

- 00631L rebound gate: latest gate is false and historical event selection was not better than non-events.

Blocking reasons:

- no component has trade permission;
- 00631L rebound gate failed;
- cash-temperature is diagnostic only;
- dynamic bucket cluster separation is weak;
- HDRL/DDPG training is not approved for GroupA+.

## Final Conclusion

2512.22895 has useful governance concepts, but it should not replace A21.18 or change live weights now. Keep it as a shadow/review candidate.

## Independent Verification Update (2026-08-27)

Performed as a completeness audit after the original 2026-08-26 review, before the 2026-08-27 market open (no new trading-day data exists yet at audit time; `ohlcv` max date was still `2026-08-26`).

### Test coverage gap

Unlike every other paper import in this batch (2411.19649, 2605.17307, 2606.09104, 2607.15195 -- each has a `tests/test_build_group_a_plus_*.py` per script), **2512.22895 has zero test files**:

```
find tests -iname "*2512_22895*"   # -> no matches
```

All 6 scripts exist and all 7 report artifacts exist, but there is no automated regression coverage for this paper's imports. This is a real gap relative to project convention, not a blocker on the "do not change live weights" conclusion.

### Live re-run: two diagnostics flipped since the original write-up

All 6 build scripts were re-run directly (no wrapper) and all exited `0`:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_dynamic_bucket_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_rebound_gate_00631l_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_cash_temperature_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_explainability_daily_audit.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_inter_cluster_dependency_shadow.py
.venv/bin/python scripts/evaluate/build_group_a_plus_2512_22895_promotion_review.py
```

`dynamic_bucket_shadow`, `rebound_gate_00631l_shadow`, `inter_cluster_dependency_shadow`, and `promotion_review` reproduced their originally documented decisions unchanged.

`cash_temperature_shadow` and `explainability_daily_audit` did **not** reproduce -- both are snapshot diagnostics that read the live signal/holdings state at run time, and the live state moved between the original write-up and this re-run (`results/signal_group_a_*.csv` shows three intraday signal runs on `2026-08-26`: `00:21`, `09:28`, `20:29`; the re-run picked up the `20:29` end-of-day snapshot, which carries a higher live cash weight than whatever snapshot the original write-up used):

| Field | Original (2026-08-26 write-up) | Re-run (2026-08-27, pre-open) |
|---|---|---|
| `cash_temperature_shadow.live_cash_bias` | `live_cash_lower_than_diagnostic` | `live_cash_near_diagnostic` |
| `cash_temperature_shadow.supports_increasing_cash` | `true` | `false` |
| `explainability_daily_audit.overall_view` | `ambiguous_leverage_inverse_mix_prefer_conservative_cash` | `bullish_core_with_defensive_overlay` |
| `explainability_daily_audit.supports_more_cash_for_conservative_execution` | `true` | `false` |

Full re-run output:

```json
// cash_temperature_shadow
{
  "live_cash_bias": "live_cash_near_diagnostic",
  "production_effect": "none",
  "reference_diagnostic_cash_weight": 0.43663,
  "reference_temperature": 1.0,
  "supports_decreasing_cash": false,
  "supports_increasing_cash": false,
  "target_weight_change_allowed": false
}

// explainability_daily_audit
{
  "ambiguous_leverage_inverse_mix": true,
  "is_clean_bearish_signal": false,
  "is_clean_bullish_signal": false,
  "overall_view": "bullish_core_with_defensive_overlay",
  "production_effect": "none",
  "supports_00631l_aggressive_add": false,
  "supports_00632r_as_hedge": true,
  "supports_more_cash_for_conservative_execution": false,
  "target_weight_change_allowed": false
}
```

### Interpretation

This is not a bug in the scripts. `cash_temperature_shadow` and `explainability_daily_audit` are both point-in-time reads of `results/group_a_combined_live_latest.json` and the live holdings snapshot -- they are designed to answer "what does today's live position look like against this paper's diagnostic lens right now," not to produce a stable historical verdict. The live cash weight genuinely increased between the two runs (consistent with the `strategy_trust_gate = ABSTAIN` / `crash_risk_alert = medium` state observed on `2026-08-25`), so the diagnostic correctly flipped with it.

Practical consequence: any specific number or verdict in the "Experiment Update" sections above (and in any other paper-import handoff with a "latest snapshot" style report) should be read as **the state on the date it was generated**, not as a standing fact. Re-run the underlying script for a current answer instead of quoting this document's numbers as current.

None of this changes the governing decision: `promote_any_component_to_live_strategy = false`, `target_weight_change_allowed = false`, latest strategy remains `a2118_a2111_ncf_late_bull_deleverage`.

### Recommended follow-up (not yet done)

- Add `tests/test_build_group_a_plus_2512_22895_*.py` for the 6 scripts, matching the pattern used by 2606.09104 / 2607.15195, so this paper's imports get the same regression coverage as its siblings.
