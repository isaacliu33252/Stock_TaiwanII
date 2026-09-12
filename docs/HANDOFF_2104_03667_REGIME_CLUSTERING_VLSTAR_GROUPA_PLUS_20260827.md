# Handoff: 2104.03667 Market Regime Detection (VLSTAR / Hierarchical Clustering) for GroupA+

Date: 2026-08-27
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`
Paper: `C:/Users/isaac/Downloads/2104.03667.pdf`
Title: `Market Regime Detection via Realized Covariances: A Comparison between Unsupervised Learning and Nonlinear Models` (Bucci & Ciciretti, arXiv:2104.03667, 2021)
Scope: GroupA+ / A21.18 import review.

## At a Glance

Six investigations were run on this paper, all closed. None change any live weight.

| # | Question | Answer |
|---|---|---|
| Original review | Do cluster-regime / VLSTAR-lite beat the existing `switch_ma80_dd11` rule for the golden1/defensive switch decision? | **No.** Existing rule wins on Sharpe and MDD, full-window and in every stress episode tested. |
| Follow-up 1 | Was the original VLSTAR-lite hyperparameter choice (`gamma=3, threshold=0.5`) just a bad pick? | **Partly.** Better hyperparameters exist for the standalone-momentum-filter test (Test A), but none of 35 combinations beat the existing rule for the switch decision (Test B). Flagged as an overfitting-risk search. |
| Follow-up 2 | Does properly *selecting* the transition variable (not tuning hyperparameters) help? | **Gets closer, still no.** Drawdown-based, un-tuned defaults: Sharpe gap to the existing rule narrows to 0.015 (from 0.026), but MDD is still 3.5pp worse. |
| Follow-up 3 | Does requiring both detectors to agree (AND) help? | **No, makes it worse.** Cluster carries no real signal; ANDing it with the working VLSTAR-lite signal only discards good calls. |
| Follow-up 4 | Is the one open thread (standalone 0050 momentum filter, Test A) actually robust? | **No.** A real date-window bug was found and fixed (see below); after fixing it, a per-year breakdown shows the win is concentrated in one year (2024) and the detector was inactive during 2020's COVID crash. Not a validated edge. |
| Follow-up 5 | Does adding a 5th asset (`00713.TW`) to the cluster-regime feature set help (testing the "too low-dimensional" diagnosis directly)? | **No, makes it worse on every metric.** Not explained by collinearity (corr with 0050 is only 0.37) -- more likely a dimensionality-to-sample-size and regime-relevance issue. Refutes "just add more assets." |

**Bottom line: closed_negative for the switch decision (four independent angles agree), the one adjacent open thread is closed as not robust, and the "just use a bigger asset pool" idea is directly refuted.** See "Bottom Line" at the end for the full statement.

## Final Decision

Do not change live weights.

- `target_weight_change_allowed = false`
- `replace_a2118 = false`
- `train_vlstar_now = false` (no full VLSTAR NLS estimation)

Latest active strategy remains `a2118_a2111_ncf_late_bull_deleverage`.

## Paper Summary

The paper detects two market regimes (calm / highly volatile) from monthly realized correlation matrices of 9 CME futures (S&P500, VIX, 2y/10y Treasury, Fed Funds, gold, silver, copper, crude), 2010-2020, hourly data from Bloomberg. Two competing detectors:

1. **VLSTAR**: vector logistic smooth-transition autoregression. A diagonal transition matrix `G_t` is a logistic function of a single exogenous transition variable (chosen by a linearity test across candidates); regime = "volatile" when `G_t > 0.5`.
2. **Agglomerative hierarchical clustering** (AGNES, Ward linkage, Manhattan distance) on features extracted from realized correlation matrices, K=2.

Validation: (a) synthetic data with known ground-truth regimes; (b) a naive momentum strategy vs. the same strategy filtered to go flat whenever the volatile regime is detected. VLSTAR is reported as the best-performing model in both tests.

## Adaptation for Group A+

Group A+ has none of the paper's 9 futures or hourly data. This review substitutes Group A+'s actual core ETF universe (`0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`) at daily frequency, and runs the paper's own validation method (naive-momentum filter) directly on `0050.TW`. A second, Group A+-specific test checks whether either detector tracks or improves on the existing `switch_risk_ma80_dd11_total6_hold5_eg015_xg015` golden1/defensive trigger.

## Simplifications (stated explicitly, same standard as prior papers)

- **VLSTAR-lite**: instead of a full nonlinear-VAR NLS estimation with a linearity-test-selected transition variable, uses trailing 21d realized volatility of `0050.TW` as the transition variable, with an expanding-window causal median as location parameter `c_t` and a fixed slope. Captures VLSTAR's defining idea (smooth logistic transition on an exogenous driver) without full multivariate NLS.
- **Cluster-regime**: AGNES/Ward fit on an expanding window of monthly realized-correlation feature vectors, refit every 3 months (quarterly, matching this project's established CHMM refit cadence), nearest-centroid assignment between refits.

## Causality

All regime series use only data available up to and including the labeled date. Every detector's classification is additionally lagged by one trading day before being applied to any return series (decide on close(t), act on t+1), matching this project's look-ahead-bug guard (`feedback_lookahead_bug_same_day_signal_decision`).

## Files Added (all five stages)

Original review:

- `scripts/evaluate/build_group_a_plus_2104_03667_regime_clustering_review.py`
- `tests/test_build_group_a_plus_2104_03667_regime_clustering_review.py` (3 tests, all passing)
- `report/group_a_plus/latest/2104_03667_regime_clustering_review.json`
- `results/regime_clustering_2104_03667_curve.csv` (daily blended curve, for inspection)

Follow-up 1 (gamma/threshold sweep):

- `scripts/evaluate/build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py`
- `tests/test_build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py` (3 tests)
- `report/group_a_plus/latest/2104_03667_vlstar_lite_sensitivity_sweep.json`

Follow-up 2 (transition-variable selection):

- `scripts/evaluate/build_group_a_plus_2104_03667_transition_variable_selection.py`
- `tests/test_build_group_a_plus_2104_03667_transition_variable_selection.py` (3 tests)
- `report/group_a_plus/latest/2104_03667_transition_variable_selection.json`

Follow-up 3 (cluster AND vlstar-lite):

- `scripts/evaluate/build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py`
- `tests/test_build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py` (3 tests)
- `report/group_a_plus/latest/2104_03667_cluster_vlstar_and_combination.json`

Follow-up 4 (year-split OOS check):

- `scripts/evaluate/build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py`
- `tests/test_build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py` (3 tests)
- `report/group_a_plus/latest/2104_03667_momentum_filter_year_split_validation.json`

Follow-up 5 (00713.TW asset-pool expansion check):

- `scripts/evaluate/build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py`
- `tests/test_build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py` (2 tests)
- `report/group_a_plus/latest/2104_03667_00713_asset_pool_expansion_check.json`

**17 tests total across the 6 scripts, all passing as of 2026-08-27.**

## Results

Coverage: 116 monthly realized-correlation feature rows, `2017-01-31` .. `2026-08-31` (limited by `00679B.TWO`'s 2017-01-11 launch date, the binding constraint across the 4-asset universe).

### A. Paper's own validation: naive momentum(0050) unfiltered vs. regime-filtered

| Strategy | ann_ret | ann_vol | Sharpe | MDD | downside_vol |
|---|---|---|---|---|---|
| unfiltered | 14.39% | 14.29% | 1.007 | -21.47% | 13.15% |
| cluster-filtered | 4.44% | 10.16% | 0.437 | -21.71% | 13.01% |
| vlstar-lite-filtered | 4.14% | 6.68% | 0.619 | -13.42% | 10.67% |

- **Cluster-filtered is strictly worse**: lower Sharpe *and* a slightly worse MDD than doing nothing. No value.
- **VLSTAR-lite-filtered genuinely cuts MDD** (-21.47% -> -13.42%, a real ~37% relative drawdown reduction) but at a steep cost: Sharpe falls to 0.619 (-38%) and return falls to 4.14% (-71%). This reproduces the paper's directional claim (VLSTAR beats clustering, filtering reduces downside) but the magnitude is a real risk/return trade, not a free improvement — consistent with the detector being very trigger-happy (see below).

### B. Group A+ full-window: golden1 vs. existing rule-switch vs. the two new detectors, blended exactly like the existing switch policy

| Strategy | ann_ret | ann_vol | Sharpe | MDD |
|---|---|---|---|---|
| golden1_alone | 30.82% | 27.63% | 1.116 | -37.02% |
| switch_ma80_dd11_rule (existing) | 27.17% | 23.44% | **1.159** | **-31.08%** |
| cluster_regime_switch | 28.88% | 25.93% | 1.114 | -36.38% |
| vlstar_lite_regime_switch | 27.89% | 24.62% | 1.133 | -34.61% |

The existing rule has the best Sharpe *and* the best (lowest) MDD of all four. Both new detectors sit strictly between golden1-alone and the existing rule -- neither beats it on either axis.

### Agreement with the existing switch_ma80_dd11 regime label

| Detector | day-by-day agreement | both defensive | detector-only defensive | rule-only defensive |
|---|---|---|---|---|
| cluster_regime | 55.6% | 180 | 540 | 174 |
| vlstar_lite_regime | 41.7% | 347 | 930 | 7 |

`vlstar_lite_regime` catches 347/354 = 98% of the rule's defensive days (high recall) but flags defensive on 930 extra days the rule does not (69% of all days total) -- very low precision. This over-triggering is exactly why it cuts MDD in test A but destroys most of the return.

### Episode-level cumulative return (blended switch curve)

| Episode | golden1 | rule_switch | cluster_switch | vlstar_switch |
|---|---|---|---|---|
| COVID crash 2020 | -25.90% | **-24.27%** | -24.07%* | -24.33% |
| 2022 bear (full year) | -25.29% | **-21.02%** | -24.57% | -23.44% |
| 2025-04 tariff shock | -7.18% | **-4.23%** | -5.69% | -5.69% |

*Cluster edges the rule by 0.2pp in COVID specifically, but loses clearly in the other two episodes and on every full-window aggregate metric -- not a robust pattern.

The existing rule wins (or is statistically tied) in every episode tested.

## Interpretation

This is the fourth regime-detection-from-covariance/correlation-structure paper tested against Group A+'s existing `switch_ma80_dd11` trigger (after 2605.07852 CHASM, 2606.23492 CHMM, 2501.16659 EMVRS), and it reaches the same conclusion as the first three: a statistical/ML regime detector fit on Group A+'s small 4-ETF universe does not beat the existing simple MA-gap + drawdown rule. The one partially positive finding -- VLSTAR-lite's real MDD reduction on the paper's own naive-momentum validation -- is a genuine risk/return trade-off (much less return for less drawdown), not a dominant improvement, and it does not carry through to the actual Group A+ golden1/defensive switch context, where it underperforms the existing rule on both Sharpe and MDD.

Hierarchical clustering (the paper's simpler, non-nonlinear baseline) has no value in any test run here -- it is not even directionally useful as a drawdown-reduction tool (test A), let alone as a switch-signal replacement (test B).

Full VLSTAR (proper multivariate NLS estimation with a linearity-test-selected transition variable) is not warranted: even the simplified proxy, using the paper's own most-favorable transition-variable choice (realized volatility, closely related to what a linearity test on this small universe would likely select anyway), underperforms the existing rule. There is no evidence a more faithful implementation would change this conclusion enough to justify the estimation cost.

## What Was Verified (not just asserted)

- Both detectors implemented and run against real Group A+ price history (`FinRL/data/stock_data.db`), not synthetic-only.
- A real bug was caught and fixed during testing: `_monthly_corr_features` did not guard against `NaN` correlations from near-zero-variance months, which crashed `sklearn.AgglomerativeClustering`. Fixed by treating an undefined (NaN) correlation as 0 ("no measurable co-movement signal") -- see the code comment at the fix site.
- `tests/test_build_group_a_plus_2104_03667_regime_clustering_review.py` has 3 tests (happy path with synthetic stress data, insufficient-history blocking path, `write_review` round-trip), matching this project's established sibling-paper test convention (2411.19649 / 2605.17307 / 2606.09104 / 2607.15195) -- unlike 2512.22895, which was found to have zero test coverage in the 2026-08-27 audit of that paper.
- All numbers in the tables above are taken from a live re-run against the current database (`2026-08-27`), not copied from an earlier draft.

## Commands (all five stages)

```bash
# Original review
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_regime_clustering_review.py

# Follow-up 1: gamma/threshold sweep
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py

# Follow-up 2: transition-variable selection
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_transition_variable_selection.py

# Follow-up 3: cluster AND vlstar-lite combination
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py

# Follow-up 4: year-split OOS check (also where the date-window bug was found)
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py

# Follow-up 5: 00713.TW asset-pool expansion check
.venv/bin/python scripts/evaluate/build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py

# All tests (17 total)
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_2104_03667_regime_clustering_review.py \
  tests/test_build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py \
  tests/test_build_group_a_plus_2104_03667_transition_variable_selection.py \
  tests/test_build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py \
  tests/test_build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py \
  tests/test_build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py -q
```

## Follow-up 1: VLSTAR-lite gamma/threshold sensitivity sweep (2026-08-27)

The original review used one fixed, untested hyperparameter choice for VLSTAR-lite (`gamma_scale=3.0`, `threshold=0.5`). Since that combination was the *only* one showing any positive signal (real MDD reduction on test A), the open question was whether the closed_negative verdict reflected the method or just that one bad choice. This follow-up sweeps `gamma_scale in {1, 1.5, 2, 3, 4, 6, 8} x threshold in {0.5, 0.6, 0.7, 0.8, 0.9}` (35 combinations) and re-evaluates both original tests for every combination.

Files:

- `scripts/evaluate/build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py`
- `tests/test_build_group_a_plus_2104_03667_vlstar_lite_sensitivity_sweep.py` (3 tests, passing)
- `report/group_a_plus/latest/2104_03667_vlstar_lite_sensitivity_sweep.json`

### Result

**Test A (paper's own naive-momentum(0050) filter validation): yes, better hyperparameters exist.** Several combinations Pareto-dominate the unfiltered baseline (higher Sharpe *and* better MDD simultaneously) -- e.g. `gamma_scale=2.0, threshold=0.8`: Sharpe 1.284 vs. baseline 1.007 (+28%), MDD -18.96% vs. baseline -21.47% (better). The original `gamma_scale=3.0, threshold=0.5` pick was indeed a poor choice on this axis, not representative of the method's ceiling.

**Test B (Group A+ golden1/defensive switch-blend, the decision that actually matters): no, none of the 35 combinations beat the existing `switch_ma80_dd11` rule.** Every single combination has both worse Sharpe (-0.006 to -0.057) and worse MDD (-3.53pp to -6.70pp) than the existing rule. The closest is `gamma_scale=3.0, threshold=0.7` (Sharpe 1.154 vs. rule's 1.159, MDD -35.02% vs. rule's -31.08%) -- still strictly worse on both axes.

### Interpretation -- and an explicit overfitting caveat

This sweep is a **single continuous in-sample window with no holdout**, and 35 combinations were compared post-hoc to find the best one -- exactly the "multiple rounds of tuning on a fixed window" pattern this project treats as a standing overfitting risk (`feedback_overfitting_fixed_window_tuning`). Nearby (gamma, threshold) pairs are highly correlated (not 35 independent draws), and the "winning" combinations were selected by looking at results after the fact. **The Test A dominance finding should not be read as "this hyperparameter combination works" -- it should be read as "the VLSTAR-lite mechanism is not structurally incapable of a Sharpe/MDD win on a standalone 0050 momentum filter; a properly out-of-sample-validated version might."** No walk-forward or year-split validation has been done on the sweep itself.

Practically, this does not change the governing decision for Group A+: the question that matters is Test B, and the existing switch rule dominates the entire grid there with no exception. The Test A finding is scoped to a hypothetical standalone 0050 momentum-timing sleeve that Group A+ does not currently run -- not to the golden1/defensive switch decision.

Updated decision fields:

- `target_weight_change_allowed = false` (unchanged)
- `replace_a2118 = false` (unchanged)
- `train_vlstar_now = false` (unchanged)
- `any_combination_dominates_baseline_test_a = true` (new finding, standalone-filter context only)
- `any_combination_dominates_existing_rule_test_b = false` (confirms original verdict for the decision that matters)

## Follow-up 2: transition-variable selection by the paper's own principle, not by backtest performance (2026-08-27)

The gamma/threshold sweep (Follow-up 1) is a performance-driven multiple-comparison search and was explicitly caveated as an overfitting risk. This second follow-up instead reproduces the paper's actual selection principle: VLSTAR chooses its transition variable via a linearity test across candidates, picked by a statistical criterion, *not* by which one performs best in backtest. This follow-up does the same: it scores 5 already-available Group A+ regime features (`neg_ma_gap`, `neg_drawdown`, `realized_vol_0050_20d`, `tail_risk_score`, `total_risk_score` -- all already columns in the existing switch policy's own feature file) by Pearson correlation with next-day 0050 squared return (a volatility-regime-shift proxy, not Sharpe/MDD), picks the single best one, and evaluates it with the paper's own **un-tuned default** hyperparameters (`gamma_scale=3.0, threshold=0.5` -- deliberately not the sweep-selected values, to avoid compounding that search).

Files:

- `scripts/evaluate/build_group_a_plus_2104_03667_transition_variable_selection.py`
- `tests/test_build_group_a_plus_2104_03667_transition_variable_selection.py` (3 tests, passing)
- `report/group_a_plus/latest/2104_03667_transition_variable_selection.json`

### Result

Selection (by correlation with next-day volatility, not performance):

| Candidate | corr with next-day 0050 squared return |
|---|---|
| neg_ma_gap | +0.1108 |
| **neg_drawdown** | **+0.2299 (selected)** |
| realized_vol_0050_20d | +0.1633 |
| tail_risk_score | +0.1537 |
| total_risk_score | +0.1443 |

`neg_drawdown` (i.e. deeper drawdown = more stress) wins clearly -- intuitive, and not cherry-picked by trading performance.

**Test A (paper's own naive momentum(0050) filter), no hyperparameter tuning at all:**

| | sharpe | mdd | ann_ret |
|---|---|---|---|
| unfiltered baseline | 1.094 | -21.47% | 17.58% |
| drawdown-filtered | **1.273** | **-16.46%** | 16.09% |

*(Numbers corrected 2026-08-27 by Follow-up 4 -- see that section. The original run of this follow-up used the full 0050 price history from 2017-01-11, which included ~3 years before the regime-features CSV's own 2020-01-02 start where the filter was silently inactive, diluting the comparison. Restricting to the honest overlap window strengthened the result, it did not weaken it.)*

A genuine Pareto win (better Sharpe *and* better MDD) using only the paper's own non-performance selection principle and un-tuned defaults -- no post-hoc search over this result. This is a more credible finding than Follow-up 1's sweep result, because nothing here was chosen by looking at Sharpe/MDD. **However, see Follow-up 4: this full-window win does not survive a per-year breakdown and should not be read as a validated edge.**

**Test B (Group A+ golden1/defensive switch-blend, the decision that matters):**

| | sharpe | mdd |
|---|---|---|
| golden1_alone | 1.116 | -37.02% |
| existing switch_ma80_dd11 rule | **1.159** | **-31.08%** |
| drawdown-transition-variable switch | 1.144 | -34.61% |

`dominates_existing_rule = False` -- still does not beat the existing rule (MDD is 3.5pp worse), but the Sharpe gap has narrowed to 0.015 (vs. 0.026-0.057 for every combination in the Follow-up 1 sweep), the closest any 2104.03667-derived detector has come to the existing rule across both follow-ups. Volatile-day share is 45.3%, roughly double the existing rule's own defensive-day share (~22%) -- still somewhat over-triggered, but far less than the original realized-vol-based VLSTAR-lite's 69%.

### Interpretation

This closes the loop opened by Follow-up 1 in a methodologically cleaner way: using the paper's own (non-performance) variable-selection principle plus untouched default hyperparameters, VLSTAR-lite gets meaningfully closer to -- but still does not beat -- the existing Group A+ switch rule. This is a more honest, lower-overfitting-risk version of "does a better-specified VLSTAR-lite help," and the answer is still no for the switch decision, though the margin is now small enough that it is a legitimate (not resounding) loss rather than a dominated one. The existing `switch_ma80_dd11` rule's own construction (MA-gap + drawdown + a 6-component risk score, combined and tuned together) is effectively already an ensemble of the same signal family being tested here one at a time -- which is a plausible structural reason single-variable VLSTAR-lite keeps falling just short: it is being asked to match a multi-factor rule with one factor.

Updated decision fields:

- `target_weight_change_allowed = false` (unchanged)
- `replace_a2118 = false` (unchanged)
- `train_vlstar_now = false` (unchanged)
- `any_variable_dominates_existing_rule_test_b = false`

## Follow-up 3: cluster AND vlstar-lite combination (2026-08-27)

Both prior follow-ups converge on the same story: single-signal VLSTAR-lite gets close to but never beats the existing rule, plausibly because the existing rule is already a tuned multi-factor combination while every tested VLSTAR-lite variant is single-input. This follow-up tests whether requiring the paper's own two detectors to *agree* (cluster-regime AND the follow-up-2 drawdown-based VLSTAR-lite, both reused exactly as already built -- no new hyperparameter search) reduces false positives enough to close the gap.

Files:

- `scripts/evaluate/build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py`
- `tests/test_build_group_a_plus_2104_03667_cluster_vlstar_and_combination.py` (3 tests, passing)
- `report/group_a_plus/latest/2104_03667_cluster_vlstar_and_combination.json`

### Result: the AND combination is worse, not better, on both tests

*(Test A numbers below corrected 2026-08-27 for the same date-window issue described in Follow-up 4 -- fixed in this script too. The qualitative conclusion, AND is worse than vlstar-only, is unchanged by the fix.)*

**Test A** (naive momentum(0050) filter): baseline sharpe=1.094/mdd=-21.47%; cluster-only sharpe=0.313/mdd=-21.71%; vlstar-only (drawdown) sharpe=1.273/mdd=-16.46%; **AND-combined sharpe=1.069/mdd=-25.63%** -- worse than the unfiltered baseline on MDD, and far worse than vlstar-only alone on both axes.

**Test B** (Group A+ switch-blend, unaffected by the date-window issue -- it was already aligned to the switch-curve CSV): existing rule sharpe=1.159/mdd=-31.08%; cluster-only sharpe=1.114/mdd=-36.38%; vlstar-only sharpe=1.144/mdd=-34.61%; **AND-combined sharpe=1.135/mdd=-36.50%** -- worse MDD than *either individual detector*, and does not dominate the existing rule.

`and_dominates_existing_rule_test_b = false`, `and_beats_both_single_detectors_test_b = false`.

### Interpretation

Requiring agreement collapses the volatile-day share from ~45% (either detector alone) to 18.3% -- but the outcome is worse, not more precise. This confirms the original review's finding that cluster-regime carries no real signal (it behaved as noise relative to the existing rule from the start): ANDing a working signal (VLSTAR-lite) with an uninformative one does not filter for quality, it just randomly discards some of the working signal's correct calls while gaining nothing, so performance degrades on both tests simultaneously. This closes off the combination-based angle cleanly -- there is no more value to extract from combining these two specific detectors.

## Follow-up 4: out-of-sample check on the standalone 0050 momentum-filter thread (2026-08-27)

The user asked to actually try validating the one open thread this paper left behind: the standalone 0050 momentum-filter finding from Follow-up 2 (Sharpe 1.007->1.144, MDD -21.47%->-17.29% on the full window), which was explicitly flagged as unvalidated out-of-sample. This follow-up breaks that comparison down by calendar year.

Files:

- `scripts/evaluate/build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py`
- `tests/test_build_group_a_plus_2104_03667_momentum_filter_year_split_validation.py` (3 tests, passing)
- `report/group_a_plus/latest/2104_03667_momentum_filter_year_split_validation.json`

### A real bug found and fixed along the way

Building the year-by-year breakdown surfaced a genuine date-window bug in Follow-up 2's Test A (now fixed in `build_group_a_plus_2104_03667_transition_variable_selection.py`): the regime-features CSV (source of the selected `drawdown` transition variable) only starts `2020-01-02`, while the 0050 price history used for the momentum strategy itself starts `2017-01-11` (bounded by `00679B.TWO`'s launch date across the 4-asset universe). For any date before 2020-01-02, the filter flag was silently `False` via `reindex().fillna(False)` -- i.e. "filter inactive" was indistinguishable from "filter detected calm," diluting the comparison with ~3 years where the mechanism could not possibly fire. Fixed by restricting the Test A window to dates >= the regime-features CSV's own start.

Effect of the fix: the pooled full-window numbers got **slightly stronger**, not weaker (Sharpe 1.007->**1.094** unfiltered baseline over the honest window, filtered 1.144->**1.273**; MDD improvement -21.47%->-16.46%). The bug had been *diluting* the effect, not inflating it -- but fixing it was necessary to make the next check (per-year breakdown) meaningful at all.

### Per-year breakdown: the aggregate improvement is NOT broad-based

| Year | n_days | unfiltered Sharpe | filtered Sharpe | unfiltered MDD | filtered MDD | wins both? |
|---|---|---|---|---|---|---|
| 2020 | 245 | 1.848 | 1.848 | -7.58% | -7.58% | no (identical -- see below) |
| 2021 | 243 | 0.807 | 0.515 | -11.29% | -12.61% | **no, loses both** |
| 2022 | 246 | -0.596 | -0.699 | -19.61% | -8.91% | no (loses Sharpe, wins MDD) |
| 2023 | 239 | 0.941 | 0.515 | -6.08% | -6.85% | **no, loses both** |
| 2024 | 242 | 0.886 | **1.514** | -18.72% | **-8.06%** | **yes** |
| 2025 | 243 | 2.187 | 1.714 | -9.11% | -8.24% | no (loses Sharpe, wins MDD) |
| 2026 (partial, 157d) | 157 | 1.647 | 2.599 | -17.68% | -7.33% | yes, but partial year |

`n_full_years = 6` (2020-2025), `n_years_filtered_wins_both = 1` (2024 only), `broad_based_edge = False`.

**2020 (the COVID year) shows literally zero effect** -- not because the detector correctly judged 2020 calm, but because `_causal_vlstar_lite`'s 252-trading-day warmup (needed before the expanding-window median/scale stabilize) consumes essentially the drawdown series' entire first year (it starts 2020-01-02). The detector was not operational during the one crisis in this window that GroupA+ actually cares most about historically. Its only clean win is 2024; two years are clean losses (2021, 2023); two more are mixed (better MDD, worse Sharpe).

### Interpretation -- this materially downgrades the standalone-filter thread

The full-window Pareto win reported in Follow-up 2 is real but **concentrated**, not broad-based: it is driven substantially by one favorable year (2024) plus the still-partial 2026, while three of the five other full years are flat-to-negative on Sharpe. This is exactly the "single continuous window, not independent-year split" failure mode this project has flagged as a promotion blocker on other papers (e.g. `chasm_online_changepoint_dynamics_regime_detection`). Combined with the fact that the detector was not even active during 2020's crash (the warmup issue), this standalone-momentum-filter thread should now be characterized as **an interesting but fragile in-sample pattern, not a validated edge** -- weaker than how it was described in Follow-ups 2 and 3. It remains out of Group A+'s current scope regardless, so this does not change any live decision, but the earlier framing ("genuine but not yet out-of-sample-validated improvement") was too optimistic; the corrected framing is "does not survive a basic year-split check."

**Caveat on this check itself**: the transition variable (drawdown) was selected once using the *full* sample's correlation with next-day volatility, not re-selected per year/fold. A true walk-forward re-selection was not attempted here.

## Follow-up 5: does adding a 5th asset (00713.TW) to the cluster-regime feature set help? (2026-08-27)

The "Interpretation" section above diagnoses cluster-regime's failure as partly a low-dimensionality problem (Group A+'s 4 core tickers give only 6 pairwise correlations to cluster on). The user asked to test this directly: does adding one more asset -- `00713.TW` (元大台灣高息低波, an existing fifth-asset candidate from the 2411.19649 review, data available 2017-09-19 onward) -- to the correlation-clustering feature set improve the detector.

Files:

- `scripts/evaluate/build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py` (thin wrapper: calls the original review's already-tested `build_review()` with a 5-ticker `core_tickers` argument -- no new detector logic)
- `tests/test_build_group_a_plus_2104_03667_00713_asset_pool_expansion_check.py` (2 tests, passing)
- `report/group_a_plus/latest/2104_03667_00713_asset_pool_expansion_check.json`

### Result: expansion makes cluster-regime worse on every single metric

| Metric | 4 tickers (baseline) | 5 tickers (+00713) |
|---|---|---|
| Cluster volatile-day share | 41.1% | 55.7% (more trigger-happy) |
| Test A cluster-filtered Sharpe | 0.437 | **0.066** |
| Test A cluster-filtered MDD | -21.71% | **-30.39%** |
| Test B cluster_regime_switch Sharpe | 1.114 | 1.063 |
| Test B cluster_regime_switch MDD | -36.38% | -36.83% |
| Agreement with existing switch rule | 55.6% | 45.6% (worse than a coin flip) |

`expansion_helps_test_a = false`, `expansion_helps_test_b = false` -- not a single metric improved.

### Interpretation

Checked whether `00713.TW`'s correlation with `0050.TW` explains this: it is `0.37` over the overlap window -- moderate, not near-collinear the way `00631L`/`00632R` are with `0050` by construction. So near-collinearity is not the mechanism here. The more likely explanation: expanding the feature vector from 6 pairwise correlations (`C(4,2)`) to 10 (`C(5,2)`) increases the clustering distance metric's dimensionality without a proportional increase in the number of monthly observations available to fit on, and `00713`'s own correlation dynamics do not obviously co-move with genuine market-stress transitions -- so the added dimension contributes noise to the Ward-linkage distance calculation rather than signal. This directly refutes the naive "more assets = better clustering" intuition for this specific case: dimensionality-to-sample-size ratio and genuine regime-relevance of the added asset both matter, not just asset count. Simply padding Group A+'s cluster-regime feature set with another Taiwan-equity-flavored ETF is not a path forward; the paper's own 9-asset universe spanned equities, rates, commodities, and volatility -- a kind of cross-asset-class diversity Group A+'s current long-only Taiwan ETF + one bond ETF universe cannot replicate without going outside its existing regime-constrained scope.

## Bottom Line

2104.03667 does not have anything worth importing into Group A+'s live strategy. Keep as closed research for the golden1/defensive switch decision: across four independent tests (the original review's two detectors, the 35-combination gamma/threshold sweep, the principled non-performance transition-variable selection, and the cluster-AND-vlstar combination), every single variant tested against the actual switch-blend context (Test B) loses to the existing `switch_ma80_dd11` rule on both Sharpe and MDD, and combining the two detectors makes things worse rather than better. The margin narrows considerably with the disciplined transition-variable selection (Sharpe gap 0.015 vs. the original 0.026) but never flips. No shadow monitor is recommended for the switch-decision use case. This is now a well-explored dead end for the switch decision -- original review, hyperparameter sweep, principled variable selection, and detector combination all point the same direction, so no further angle is queued.

The standalone-0050-momentum-filter thread (outside Group A+'s current scope in any case) was tried out per follow-up 4: it does **not** survive a basic year-split check. Its full-window Sharpe/MDD improvement is concentrated almost entirely in one year (2024), two of the other five full years are clean losses, and the detector was not even operational during 2020's crash due to its own warmup period. This thread is now closed too, downgraded from "flagged for the record" to "checked and found fragile" -- no further work is queued on it.

Follow-up 5 directly tested and refuted the natural next question, "would a bigger asset pool fix cluster-regime": adding `00713.TW` made every single metric worse, not better, and the cause does not look like simple collinearity (correlation with 0050 is only 0.37). Padding Group A+'s cluster-regime feature set with more Taiwan-equity-style ETFs is not a viable path forward without genuinely cross-asset-class diversity (equities + rates + commodities + volatility, as the original paper used), which is outside Group A+'s current regime-constrained, long-only Taiwan-ETF-plus-one-bond-ETF universe.

All six investigations on this paper are now complete. No further angle is queued.
