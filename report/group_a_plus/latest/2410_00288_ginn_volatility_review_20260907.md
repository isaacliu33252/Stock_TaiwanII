# 2410.00288 GINN Volatility Review

- Policy: `research_only_no_weight_change`
- Decision: promotion_allowed_now=`False`
- Latest strategy weight change: `False`
- Recommended next step: `build_garch_informed_ncf00631l_shadow_panel_and_purged_walkforward`

## Paper Takeaways

- GINN uses GARCH variance as a teacher/regularizer for an LSTM volatility model.
- The paper's best reported lambda is 0.01, and GINN-0 is close, so the GARCH teacher carries most of the useful regularization.
- The model is evaluated on volatility R2/MSE/MAE, not direction accuracy or trading PnL.
- The authors warn that GINN is smoother than GARCH and can miss peak magnitude/timing.

## Current Coverage

- NCF00631L panel: `results/ncf_00631l_panel_latest_20260907.csv` rows=`407` dates=`2025-01-02` to `2026-09-04`
- Explicit GARCH-informed panel columns: `[]`
- Existing GJR shadow status: `available` date=`2026-09-07` policy=`shadow_only_no_weight_change` evidence=`watch`
- GJR gamma: `0.316525` LR p-value=`0.000000`
- GJR/symmetric variance ratio: `0.852468` disagreement=`True` asymmetry_shock=`False`

## Transfer Candidates

| idea | status | latest strategy change | mapping |
|---|---|---:|---|
| GARCH-informed volatility teacher for NCF00631L | candidate_shadow | False | Add PIT GARCH/GJR forecast variance, variance-ratio, persistence, and negative-shock flags to the NCF00631L feature panel. |
| Auxiliary volatility head with GINN loss | candidate_shadow | False | Train an auxiliary NN head to forecast next-day or H5/H20 realized variance while the existing NCF direction/tail heads remain primary. |
| Volatility-conditioned abstention / no-add gate for 00631L | candidate_shadow | False | Use high forecast variance or GARCH/GJR disagreement only to raise add thresholds or require human review; never as an automatic bullish/bearish signal. |
| Dedicated time-series holdout for lambda/model selection | governance_requirement | False | Use existing purged walk-forward windows plus a separate tuning window for lambda/teacher weight and freeze before live evaluation. |

## Deferred

- Directly set lambda=0.01 in production: The paper tuned lambda on global equity indices, not 00631L Taiwan leveraged ETF data.
- Use volatility forecast as a direction classifier: The paper predicts variance, not return direction; mapping high volatility to UP/DOWN would be an unsupported extra assumption.
- Replace current GJR shadow with active allocation rule: The repository already records significant in-sample asymmetry but failed earlier OOS promotion gates; current GJR policy remains shadow_only_no_weight_change.
- Adopt the full 3-layer 256-width LSTM blindly: NCF00631L sample size is much smaller than the paper's index datasets; a smaller ablation-first model is safer.

## Required Validation

- Purged walk-forward comparison of baseline NCF vs GARCH-informed NCF.
- Ablation separating realized-vol columns, symmetric GARCH, GJR ratio, and auxiliary loss.
- Direction metrics: accuracy, balanced accuracy, AUC, Brier, calibration slope.
- Portfolio metrics: final value, max drawdown, worst 20d return, turnover, missed rebound cost.
- Spike-timing review because the paper warns smooth GINN outputs can miss peak magnitude.

## Conclusion

可以導入，但只應先導入為 shadow：新增 GARCH-informed NCF00631L volatility feature / auxiliary head / abstention gate 評估。暫時不應改 groupA++ 最新策略權重、golden1_0531 或 golden2_0830。
