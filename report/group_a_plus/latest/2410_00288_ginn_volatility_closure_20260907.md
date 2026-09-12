# 2410.00288 GINN Volatility Closure

- Paper: `C:\Users\isaac\Downloads\2410.00288.pdf`
- Topic: GARCH-Informed Neural Networks for volatility prediction
- Scope: groupA++ / latest strategy / NCF00631L
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_stop_full_ginn_pipeline`
- Latest strategy change: `False`
- Golden1_0531 change: `False`
- Golden2_0830 change: `False`

## Corrected Thesis

The user thesis is directionally correct, but one detail needs correction:
`results/xgb_audit_00631l_20260630.json` does not show realized volatility as uniformly low-ranked. In aggregate, `volatility_20` ranks `13/135`, and in H20 it ranks `7/135`. So the accurate statement is not "volatility has no information."

The accurate statement is:

Volatility-level features have descriptive information, but the project evidence does not show that a more elaborate GARCH/GINN version converts that second-moment information into stable H20 direction accuracy, calibration, or 00631L no-add policy lift.

## Evidence

Existing feature audit:

| source | feature | rank | note |
|---|---:|---:|---|
| aggregate | `volatility_20` | `13/135` | A grade, not weak |
| aggregate | `volatility_60` | `20/135` | A grade |
| H20 | `volatility_20` | `7/135` | A grade |
| H20 | `volatility_60` | `17/135` | A grade |
| H20 | `vix_spike_x_vol20` | `38/135` | B grade |

2410.00288 transfer tests:

| test | result |
|---|---|
| GARCH-informed calibration | Acc `0.6127 -> 0.5784`, AUC `0.8419 -> 0.6289`, Brier `0.2261 -> 0.2835` |
| Feature ablation | no feature family improved both Acc and Brier across folds |
| Plain/symmetric GARCH only | Acc `0.5343`, AUC `0.8090`, Brier `0.2437` |
| GJR/asymmetry only | Acc `0.5784`, AUC `0.4281`, Brier `0.2534` |
| Realized vol only | AUC improved, but Acc and Brier deteriorated |
| No-add gate | all simple gates passed `0/4` folds |
| Conditional no-add gate | best weak gate passed only `1/4` folds with 7 blocked rows |

Live-forward observation:

- Weak candidate gate: `realized_var_20_top25_and_weak_ncf`
- Latest signal date: `2026-09-04`
- Triggered: `False`
- Production action: `none`
- Forward H20 outcome can be checked after `2026-10-09`

## Why Full GINN Is Not Worth Implementing Now

The paper's key idea is valid for volatility forecasting, not direction forecasting. It explicitly separates the low predictability of first moments from the richer structure of second moments. For NCF00631L, the current target is H20 direction and trading usefulness, not variance MSE.

GINN also does not introduce a fundamentally new information dimension. It uses GARCH output as a regularizer or teacher; GINN-0 is effectively trained to reproduce GARCH predictions. The likely effect is smoothing and regularization, not new directional alpha.

Project tests already covered the low-cost prerequisite:

- Plain GARCH variance features were tested.
- GJR/asymmetry features were tested.
- Volatility-family ablations were tested.
- No-add/abstention gates were tested.

The results do not justify building the heavier LSTM plus GARCH hybrid training pipeline.

## Decision

Do not add GINN to groupA++ latest strategy.

Do not change:

- `report/group_a_plus/latest/strategy.json`
- Golden1_0531 artifacts
- Golden2_0830 artifacts
- NCF live decision gate
- 00631L target weights
- order generation

Keep only:

- paper review record
- ablation reports
- no-add gate report
- one live-forward shadow log for the weak candidate gate

## Better Next Research Direction

If improving NCF00631L direction accuracy remains the goal, prioritize new information dimensions rather than more sophisticated volatility smoothers:

- 00631L vs 0050 relative strength and lead/lag
- TX/TXO positioning and option pressure
- 2330/TSM/SOXX leadership divergence
- trend persistence vs mean reversion state
- downside event classifiers rather than variance-level forecasts
- funding/flow/liquidity regime transitions

## Related Artifacts

- `report/group_a_plus/latest/2410_00288_ginn_volatility_review_20260907.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.md`
- `report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.md`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_gate.md`
- `report/group_a_plus/latest/2410_00288_ginn_no_add_forward_shadow.json`
- `results/2410_00288_ginn_no_add_forward_shadow_log.jsonl`
