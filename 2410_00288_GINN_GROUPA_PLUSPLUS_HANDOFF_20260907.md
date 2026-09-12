# 2410.00288 GINN / GroupA++ Handoff

Date: 2026-09-07  
Paper: `C:\Users\isaac\Downloads\2410.00288.pdf`  
Title: GARCH-Informed Neural Networks for Volatility Prediction in Financial Markets  
Scope: groupA++ latest strategy, NCF00631L direction/risk use  
Final decision: `do_not_promote_stop_full_ginn_pipeline`  
Production impact: none

## Final Status

The paper analysis and project-specific experiments are complete for the current purpose: deciding whether GARCH-informed NN / GINN should be added to groupA++ latest strategy.

Conclusion:

Do not add GINN to groupA++ latest strategy. Do not build the full LSTM plus GARCH hybrid training pipeline now.

No changes were made to:

- `report/group_a_plus/latest/strategy.json`
- Golden1_0531 artifacts
- Golden2_0830 artifacts
- NCF live gate
- 00631L target weights
- order generation

Only research/shadow artifacts were created.

## Paper Takeaways

The paper proposes GARCH-Informed Neural Network, where an LSTM volatility model is regularized by GARCH variance forecasts.

Relevant points:

- It predicts volatility/variance, not price direction.
- It explicitly relies on the idea that first moment/direction is hard to predict, while second moment/volatility has more structure.
- The reported best loss weight is `lambda=0.01`.
- GINN-0 is close to GINN and effectively learns GARCH output.
- The paper's own discussion notes GINN is smoother than GARCH and can miss volatility peaks.
- Metrics are volatility R2/MSE/MAE, not portfolio PnL, Acc, AUC, Brier, drawdown, or trading usefulness.

Interpretation for groupA++:

GINN is not a new directional alpha source. At best it is a more sophisticated volatility smoother / regularizer.

## Important Correction

The claim "existing volatility features rank low" is not fully accurate for the available audit.

From `results/xgb_audit_00631l_20260630.json`:

| scope | feature | rank | grade |
|---|---:|---:|---|
| aggregate | `volatility_20` | `13/135` | A |
| aggregate | `volatility_60` | `20/135` | A |
| H20 | `volatility_20` | `7/135` | A |
| H20 | `volatility_60` | `17/135` | A |
| H20 | `vix_spike_x_vol20` | `38/135` | B |

Corrected thesis:

Volatility-level features have descriptive information, but project tests do not show that GARCH/GINN second-moment features convert that information into stable H20 direction accuracy, calibration, or no-add policy lift.

## Experiments Completed

### 1. Paper Review / Coverage Check

Artifact:

- `report/group_a_plus/latest/2410_00288_ginn_volatility_review_20260907.md`
- `report/group_a_plus/latest/2410_00288_ginn_volatility_review_20260907.json`
- `scripts/evaluate/build_group_a_plus_2410_00288_ginn_volatility_review.py`

Result:

- Existing NCF00631L panel did not contain explicit GARCH-informed features.
- Existing GJR-GARCH shadow already exists and remains `shadow_only_no_weight_change`.
- 2026-09-07 recomputed GJR state:
  - `evidence=watch`
  - `GJR gamma=0.316525`
  - `GJR/symmetric variance ratio=0.852468`
  - `vol_model_disagreement=True`
  - `asymmetry_shock=False`

Decision:

Research-only. No latest strategy change.

### 2. GARCH-Informed Calibration Shadow

Artifact:

- `scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.json`
- `results/2410_00288_ginn_ncf00631l_shadow_predictions.csv`

Method:

Baseline was existing NCF00631L `prob_up_h20`. Candidate used logistic calibration with GARCH/GJR-informed volatility features under purged walk-forward validation.

Result:

| model | Acc | AUC | Brier |
|---|---:|---:|---:|
| baseline NCF `prob_up_h20` | `0.6127` | `0.8419` | `0.2261` |
| GARCH-informed calibration | `0.5784` | `0.6289` | `0.2835` |
| delta | `-0.0343` | `-0.2130` | `+0.0574` |

Interpretation:

Worse Acc, worse AUC, worse Brier. Do not promote.

### 3. Feature Family Ablation

Artifact:

- `scripts/evaluate/ablate_group_a_plus_2410_00288_ginn_ncf00631l_features.py`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.json`

Result:

| feature set | Acc | dAcc | AUC | dAUC | Brier | dBrier |
|---|---:|---:|---:|---:|---:|---:|
| raw NCF `prob_up_h20` | `0.6127` | `0.0000` | `0.8419` | `0.0000` | `0.2261` | `0.0000` |
| all volatility families | `0.5784` | `-0.0343` | `0.6289` | `-0.2130` | `0.2835` | `+0.0574` |
| GJR asymmetry only | `0.5784` | `-0.0343` | `0.4281` | `-0.4138` | `0.2534` | `+0.0273` |
| GARCH all only | `0.5735` | `-0.0392` | `0.4447` | `-0.3972` | `0.2546` | `+0.0285` |
| realized vol only | `0.5588` | `-0.0539` | `0.8969` | `+0.0549` | `0.2895` | `+0.0634` |
| symmetric GARCH only | `0.5343` | `-0.0784` | `0.8090` | `-0.0329` | `0.2437` | `+0.0176` |
| baseline logit only | `0.5245` | `-0.0882` | `0.8419` | `0.0000` | `0.2491` | `+0.0230` |
| vol cluster only | `0.4853` | `-0.1275` | `0.7450` | `-0.0969` | `0.2551` | `+0.0291` |

Interpretation:

No feature family improves both Acc and Brier. `realized_vol_only` improves AUC but hurts Acc and Brier, so it is not usable for live strategy.

### 4. Simple Volatility No-Add Gate

Artifact:

- `scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_no_add_gate.py`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_gate.md`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_gate.json`

Method:

Only on NCF-bullish rows, test whether high volatility should block new 00631L exposure.

Result:

All simple gates passed `0/4` purged folds.

Examples:

| gate | pass | blocked rows | blocked gain | allowed gain | blocked MDD>5 | allowed MDD>5 |
|---|---:|---:|---:|---:|---:|---:|
| `realized_var_20_top25` | `0/4` | `35` | `0.2324` | `0.1336` | `0.3571` | `0.4400` |
| `garch_gjr_var_top25` | `0/4` | `30` | `0.2177` | `0.2242` | `0.1176` | `0.3578` |
| `garch_disagreement_top25` | `0/4` | `17` | `0.2622` | `0.2240` | `0.0667` | `0.3369` |

Interpretation:

High volatility often coincides with profitable trend/rebound periods. A simple high-vol no-add gate would block too many useful 00631L opportunities.

### 5. Conditional Volatility No-Add Gate

Method:

Tested high volatility plus bad-state conditions:

- high volatility AND negative 5d return
- high GARCH/GJR volatility AND negative 5d return
- GARCH disagreement AND negative 1d return
- high realized volatility AND weak NCF bull

Result:

Best weak gate:

- `realized_var_20_top25_and_weak_ncf`
- pass `1/4` folds
- blocked rows `7`
- allowed rows `65`
- blocked H20 gain `0.1169`
- allowed H20 gain `0.2326`
- blocked MDD>5 `0.3333`
- allowed MDD>5 `0.2415`

Interpretation:

There is a weak hint, but sample size is too small and fold stability is insufficient. Do not promote. Keep only as live-forward observation.

### 6. Live-Forward Shadow Snapshot

Artifact:

- `scripts/run/build_group_a_plus_2410_00288_ginn_no_add_forward_shadow.py`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_forward_shadow.json`
- `results/2410_00288_ginn_no_add_forward_shadow_log.jsonl`

Important bug fixed:

The first snapshot accidentally used `volatility_feature_date=2026-08-07` because a helper excluded live rows. The script was corrected to:

- use realized historical rows only for the threshold
- compute live-date volatility from OHLCV through the signal date

Corrected latest snapshot:

- signal date: `2026-09-04`
- volatility feature date: `2026-09-04`
- `prob_up_h20=0.7694`
- `ensemble_prob_up=0.6933`
- `confidence=0.3866`
- `realized_var_20=0.0005205`
- `realized_var_20_threshold=0.0020862`
- `garch_gjr_over_sym=1.0785`
- bullish: `true`
- weak bull: `false`
- high realized var: `false`
- would trigger shadow no-add: `false`
- production action: `none`

Forward H20 outcome can be checked after `2026-10-09`.

## Final Decision Logic

The full GINN pipeline is not justified because:

1. The paper targets volatility, not direction.
2. GINN mostly regularizes or smooths GARCH output; it does not add a new information dimension.
3. Plain GARCH, GJR, realized volatility, vol clustering, and combined volatility-family tests were already run.
4. These low-cost prerequisite tests did not improve NCF00631L direction metrics or no-add gate behavior.
5. Existing project history already warns that high volatility is not equivalent to downside risk for 00631L.

Therefore:

Stop this branch unless new evidence appears.

## Restart Conditions

Only reopen this research branch if at least one condition becomes true:

- A new non-volatility information source is paired with GARCH state, such as TXO positioning, dealer futures/options, SOXX/TSM/2330 leadership, or flow/liquidity transition.
- There are enough live-forward rows for the weak gate to evaluate out-of-sample after H20 labels arrive.
- A future NCF architecture already has an auxiliary volatility head for another reason, making GINN-style loss nearly free to test.
- A portfolio replay shows volatility state improves final value, drawdown, or missed-rebound cost despite not improving direction metrics.

## Recommended Next Research Direction

If the goal is improving NCF00631L direction accuracy or 00631L add timing, prioritize:

- 00631L vs 0050 relative strength and lead/lag
- TX/TXO positioning and option pressure
- 2330/TSM/SOXX leadership divergence
- trend persistence vs mean reversion state
- downside event classifiers rather than volatility-level forecasts
- funding/flow/liquidity regime transitions

## Verification

Commands run:

```bash
.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_2410_00288_ginn_volatility_review.py
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py
.venv/bin/python -m py_compile scripts/evaluate/ablate_group_a_plus_2410_00288_ginn_ncf00631l_features.py
.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_no_add_gate.py
.venv/bin/python -m py_compile scripts/run/build_group_a_plus_2410_00288_ginn_no_add_forward_shadow.py
git diff --check -- related 2410.00288 scripts/reports
```

Result:

- Related script syntax checks passed.
- Related `git diff --check` checks passed.
- Global `git diff --check` may still show unrelated pre-existing trailing whitespace in other files.

## Artifact Index

Review and closure:

- `report/group_a_plus/latest/2410_00288_ginn_volatility_review.md`
- `report/group_a_plus/latest/2410_00288_ginn_volatility_review.json`
- `report/group_a_plus/latest/2410_00288_ginn_volatility_review_20260907.md`
- `report/group_a_plus/latest/2410_00288_ginn_volatility_review_20260907.json`
- `report/group_a_plus/latest/2410_00288_ginn_volatility_closure_20260907.md`
- `2410_00288_GINN_GROUPA_PLUSPLUS_HANDOFF_20260907.md`

Evaluation:

- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.json`
- `results/2410_00288_ginn_ncf00631l_shadow_predictions.csv`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.json`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_gate.md`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_gate.json`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_forward_shadow.json`
- `results/2410_00288_ginn_no_add_forward_shadow_log.jsonl`

Scripts:

- `scripts/evaluate/build_group_a_plus_2410_00288_ginn_volatility_review.py`
- `scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py`
- `scripts/evaluate/ablate_group_a_plus_2410_00288_ginn_ncf00631l_features.py`
- `scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_no_add_gate.py`
- `scripts/run/build_group_a_plus_2410_00288_ginn_no_add_forward_shadow.py`
