# Sparse US->Taiwan Lead-Lag Graph, Relative-Return Targets - Group A+ Review

**Status: closed, null result. Research-only, no code promoted.**

## Background

User proposed a sparse directed lead-lag graph (US markets -> Taiwan) using
rolling hypothesis tests to keep only stable edges, feeding two narrow
1-day relative-return targets: 00631L vs 0050, and TSMC vs the 0050-ex-TSMC
proxy.

**Before building anything, found this mechanism already extensively
built and live**:
`docs/cross_market_graph_shadow_20260715.md` +
`scripts/evaluate/evaluate_cross_market_directed_graph_shadow.py` (30+
result files, 2026-07-15/16) use nearly identical source nodes
(TSM/SOXX/QQQ/TWD=X/NVDA/AMD/AVGO/ASML/^TNX) and target universe
(2330/0050/00631L/2454/2317/2308/2382), the same rolling t-stat
edge-stability selection method, and even the same node-ablation testing
(`minus2330`, `minus2308`, `minus2317`, etc.) the user described. It is
currently live in production as `cross_market_graph_shadow`
(`daily_signal.py`) / `cross_market_graph_advisory`
(`execution_plan.json`), advisory-only. Prior verdict: NO_ADD (5-day
horizon, binary) has weak-but-repeatable signal (AUC 0.532); REENTER is
unusable (AUC 0.485); kept as `NO_ADD_ONLY_SHADOW_FILTER`.

What was genuinely new in the user's proposal: the existing work's targets
are 5-day-horizon binary NO_ADD/REENTER classification. The user's two
targets are 1-day horizon and continuous (relative return spread, not a
threshold classification), and one of them (TSMC vs 0050-ex-TSMC) didn't
exist in any form before.

## What Was Built

`scripts/evaluate/evaluate_cross_market_lead_lag_relative_return_shadow.py`
-- reuses `load_source_closes`, `load_target_closes`,
`align_source_returns_to_taiwan_dates`, `add_composite_source_features`,
and critically `select_directed_edges()` **unmodified** from the existing
module (no duplication of the edge-selection logic itself). Only new code:

- `build_relative_return_targets()`: two continuous 1-day-forward targets,
  named to match the `target_*_ret1d_fwd` convention the existing
  `select_directed_edges()` already scans for, so no changes were needed
  to that function to make it work on these new targets.
  - `target_rel_00631l_vs_0050_ret1d_fwd` = 00631L's 1-day fwd return minus
    0050's 1-day fwd return.
  - `target_rel_2330_vs_0050_ex_tsmc_ret1d_fwd` = TSMC's 1-day fwd return
    minus the ex-TSMC-proxy's 1-day fwd return (reuses
    `group_a_plus/integrations/tsmc_concentration_divergence.py`'s exact
    formula, built earlier the same day for the TSMC concentration
    divergence line).
- `walk_forward_relative_return_model()`: a regression analogue of the
  existing module's `walk_forward_graph_action_models()` -- same
  walk-forward retrain-block structure and same per-block
  `select_directed_edges()` call, but fits `Ridge` regression (not
  `LogisticRegression`) and reports R²/correlation/directional-accuracy
  (not AUC/balanced-accuracy), since the targets are continuous.

12 unit tests (`tests/test_evaluate_cross_market_lead_lag_relative_return_shadow.py`,
covering the two target-construction formulas and the R²/directional-
accuracy helpers), all passing.

## Result

Real end-to-end run, 2019-01-02 to 2026-08-07, default parameters
(edge_window=250, tstat_threshold=2.0, min_windows=3,
stability_threshold=0.20, min_train_days=504, retrain_step=20):

| target | OOS rows | R² | correlation | directional accuracy |
|---|---:|---:|---:|---:|
| rel_00631L_vs_0050 (1d) | 1,338 | -0.007 | 0.002 | 53.1% |
| rel_2330_vs_0050_ex_tsmc (1d) | 1,336 | -0.006 | 0.027 | 50.4% |

**Both targets: essentially zero out-of-sample predictive power.** Negative
R² (worse than predicting the historical mean every day), correlation
between predicted and actual near zero for both, directional accuracy
barely above (00631L target) or exactly at (TSMC target) a 50% coin flip.

**This is not "no stable edges were found"** -- the edge-selection
mechanism worked as designed and repeatedly selected features it judged
"stable" by the rolling t-stat criterion (e.g. `src_SOXX_ret1d` selected in
60 of ~67 retrain blocks for the 00631L target;
`src_AVGO_ret5d`/`src_SOXX_ret3d`/`src_TSM_ret3d` frequently selected for
the TSMC target). The finding is sharper than "nothing passed the filter":
**features that repeatedly look statistically stable in-sample do not
translate into real next-day out-of-sample predictive power for either
relative-return target.**

## 2026-08-09 Follow-Up: Conditional Breakdown by Realized Winning Side

User asked whether flipping the target (0050-vs-00631L instead of
00631L-vs-0050) would change anything. Mathematically it cannot for a
linear model: sign-flipping a regression target leaves R², correlation,
and directional accuracy exactly unchanged (proven algebraically -- OLS/
Ridge coefficients flip sign symmetrically, so residuals, `abs(tstat)` in
`select_directed_edges()`, and sign-agreement are all invariant). Not
re-run for that reason.

Instead tested a genuinely different, asymmetric question: does prediction
quality differ depending on which side of each pair is actually winning
that day? Added `_metrics_by_realized_side()` -- a post-hoc stratification
of the *evaluation* only (never used to select features or fit the model,
which stays strictly walk-forward/past-only), splitting OOS days into
"first asset wins" (target > 0) vs "second asset wins" (target < 0), same
category of technique as the existing module's `_metrics_by_condition()`.

| target | side | rows | R² | directional accuracy |
|---|---|---:|---:|---:|
| 00631L vs 0050 | 00631L wins | 751 | -0.864 | 84.3% |
| 00631L vs 0050 | 0050 wins | 582 | -0.942 | 12.9% |
| TSMC vs ex-TSMC | TSMC wins | 656 | -1.027 | 79.6% |
| TSMC vs ex-TSMC | ex-TSMC wins | 673 | -1.739 | 22.0% |

**This sharpens the null result rather than complicating it.** The high
directional-accuracy numbers (84.3%, 79.6%) are not genuine skill -- they
are a base-rate artifact: over 2019-2026-08, 00631L (2x leveraged) and TSMC
structurally outperformed 0050 and the ex-TSMC basket respectively more
often than not (a multi-year AI/semiconductor bull market sample), so a
model that predicts "the structurally stronger side wins" nearly every day
scores high accuracy exactly on the days that side actually does win, and
scores correspondingly badly (12.9%, 22.0%) on the minority days it
doesn't. The unconditional 53.1%/50.4% directional accuracy reported above
was already this asymmetry diluted by the sample's class imbalance, not a
balanced weak signal.

**The decisive evidence is the conditional R², which is uniformly and
severely negative in every subset** (-0.86 to -1.74, far worse than the
already-negative unconditional R² of -0.007). Once the "free" accuracy from
guessing the trending side is removed by conditioning, the model has zero
magnitude-level skill in either direction. There is no genuine bidirectional
lead-lag predictability here at all -- only a structural bull-market bias
that a naive constant-prediction model would replicate without any
cross-market information whatsoever.

## 2026-08-09 Follow-Up: Parameter Sensitivity Sweep

Only one parameter setting (the defaults inherited from the existing
`cross_market_graph_shadow` work) had been run before this point. Swept
`edge_window` in {120, 250, 504} x `tstat_threshold` in {1.5, 2.0, 2.5}
(9 combinations, real 2019-2026-08-07 OOS run each) to confirm the null
result isn't an artifact of the single default setting.

| edge_window | tstat_threshold | 00631L-vs-0050 R² | 00631L-vs-0050 dir.acc | TSMC-vs-ex-TSMC R² | TSMC-vs-ex-TSMC dir.acc |
|---:|---:|---:|---:|---:|---:|
| 120 | 1.5 | -0.007 | 53.9% | -0.015 | 50.2% |
| 120 | 2.0 | +0.002 | 55.6% | -0.007 | 49.0% |
| 120 | 2.5 | +0.000 | 56.3% | -0.002 | 49.7% |
| 250 | 1.5 | -0.012 | 52.8% | -0.018 | 51.4% |
| 250 | 2.0 (default) | -0.007 | 53.1% | -0.006 | 50.4% |
| 250 | 2.5 | +0.001 | 53.9% | -0.003 | 49.5% |
| 504 | 1.5 | -0.015 | 52.9% | -0.018 | 50.3% |
| 504 | 2.0 | -0.010 | 53.3% | -0.011 | 50.2% |
| 504 | 2.5 | -0.006 | 55.3% | -0.003 | 50.1% |

**Confirmed robust, not a fluke of the default parameters.** R² stays in a
tight band around zero across every combination (-0.018 to +0.002 -- the
two barely-positive cells explain well under 1% of variance, noise not
signal). Directional accuracy never leaves the 49-56% range. No parameter
combination shows anything resembling real predictive power. This
strengthens rather than changes the closure verdict below.

## Interpretation

The existing 5-day NO_ADD signal (weak but real, AUC 0.532) and this
session's new 1-day relative-return targets (no signal, R² negative) point
to the same underlying conclusion from two different angles: whatever
genuine cross-market information transmission exists from these US factors
into Taiwan/00631L/TSMC, it operates on a slower (multi-day risk-regime)
timescale, not a 1-day relative-return timescale. Predicting *which* asset
outperforms tomorrow (00631L vs 0050, or TSMC vs the rest of the basket) is
a much harder, higher-frequency question than predicting a multi-day
risk-off regime shift, and this test found no evidence US markets solve it
at 1-day horizon via this feature set.

## Decision

**Closed, null result, no promotion.** Consistent with this project's own
signal-validation discipline: a negative R² OOS result is a clean, decisive
close, not something to keep tuning. Do not gate any Group A+ decision on
either of these two relative-return targets.

Does not change the existing `cross_market_graph_shadow`'s live status --
that mechanism's 5-day NO_ADD signal remains the one with actual (weak)
evidence behind it and stays exactly as it was
(`NO_ADD_ONLY_SHADOW_FILTER`, advisory-only). This review only tested two
new, narrower targets against the same infrastructure; it does not revisit
or weaken the prior 5-day-horizon conclusion.
