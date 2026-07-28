# Trough Re-entry Proposal (arXiv:2509.05922), Sample Expansion, and Value Attribution — 2026-07-26/27

## Status

**Fully analyzed, not promoted, no code fix needed.** This is a same-session
continuation of `GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md`'s
Part H (00631L<->0050 relief-gate research), started after that thread's
negative-OOS conclusion (H6). No production code was changed. Three new,
genuine NCF backfills were built (2021, 2023, 2024). One real design
limitation was found in a *shadow evaluator* (not production) and clearly
documented but not fixed (low priority, does not affect any live decision).
The final, corrected verdict: the production re-entry-acceleration mechanism
already works correctly, but its real economic value is negligible
(+1,527.6 TWD net, on ~NT$1-1.4M portfolios, across 9 years of data,
7 genuinely-eligible events) -- not worth further engineering investment.

## Origin

User proposed a new module `group_a_plus/integrations/trough_reentry_nowcast.py`
inspired by arXiv:2509.05922 ("Predicting Market Troughs: A Machine Learning
Approach with Causal Interpretation"), citing a local PDF
(`/mnt/c/Users/isaac/Downloads/2509.05922v1.pdf`) and claiming their own
prior experiment found: entry->trough only protects ~1.33%, trough->H5
re-entry already captures ~3.15%, but T+1 re-entry leaks ~1.74% more --
implying re-entry timing (not exit timing) is the bigger opportunity.
Proposed a 3-action (`NO_REENTRY`/`PARTIAL_REENTRY`/`FULL_REENTRY`) module
gated to `group_a_plus_defensive`/`group_a_plus_recovery` regimes, using a
list of Taiwan-specific features (TXO PCR, TXO skew, IV term structure,
台指期 basis, foreign futures/options positioning, market breadth,
limit-down count, Amihud illiquidity, USD/TWD reversal, TSM ADR reversal,
SOX reversal, 2330 relative strength), with an explicit note that the paper
is US-market research and Taiwan needs its own point-in-time OOS validation.

## Part 1: grounding (via a background research fork, read-only)

### 1a. The paper itself (68 pages, read in full)

- **Trough definition**: Bry-Boschan algorithm on daily S&P 500 log price
  (backward-looking peak/trough dating, extended past sample end to avoid
  labeling leakage). Positive label for the 5 trading days immediately
  before each dated trough. **Only 7 dated troughs in the entire
  2013-2025 sample**; the true hold-out test window (Jul 2023-Jun 2025)
  contains only **2** of them.
- **Method**: SVM (linear, low-C) on 15 RF-selected features from 200+
  engineered ones, SMOTE for imbalance, isotonic calibration. Causal side:
  DML-PLR (linear) vs. DML-APE (non-linear), with Cinelli-Hazlett
  sensitivity analysis.
- **Features/causal drivers**: predictive SHAP top features --
  `gex_oi_roc63_scaled_std`, `credit_spread_roc63_scaled_std`. Causal
  (DML-APE, robust): `ffr_slope` trend (negative, robust across
  specifications), volatility of options-implied risk appetite
  (significant *only* under the non-linear APE model, not the linear PLR),
  and **Amihud illiquidity trend volatility whose sign reverses between
  PLR (-0.0608, stabilizing) and APE (+0.0160, destabilizing)** -- a real
  instability in the paper's own causal claim, not a robust, uncontested
  finding.
- **Performance**: SVM ROC AUC 0.8905, Brier 0.0170 on hold-out.
  LassoCV had higher AUC (0.9495) but useless Brier (0.2528, uncalibrated).
  VIX>40 heuristic AUC 0.6656. Economic backtest: fixed-size Sharpe peaks
  2.01-2.03 at 10-12 day holds, but **the pyramiding variant has >100% max
  drawdown ("risk of ruin") at 5-7 day holds -- the paper's own authors
  call this "completely uninvestable."**
- **The paper's own explicit caveat**: it is "a good capitulation detector
  and a poor bear-to-bull trend-switching validator" -- cannot distinguish
  a real bottom from a bear-market rally, and should never be used
  standalone, only as one component alongside longer-term regime filters.
  Authors flag their own OOS evidence (2 troughs) as thin and want
  pre-2013 data (incl. 2008 GFC) before trusting it further.

### 1b. Existing repo state -- near-total overlap, already live-wired

`group_a_plus/integrations/trough_nowcast.py` (built 2026-07-14, iterated
v1-v7) already has state space `("NO_TROUGH", "CAPITULATION_WARNING",
"PARTIAL_REENTRY", "FULL_REENTRY")` -- matching the user's proposed 3
states almost exactly. **It is already live-wired**, not shadow-only: into
`daily_signal.py` (diagnostic alert) and `execution_plan.py`
(`_trough_nowcast_buy_fraction()` -- `PARTIAL_REENTRY` can raise the
buy-staging fraction 0.4 -> 0.7; `FULL_REENTRY` structurally supported but
disabled by policy). Regime name check: `group_a_plus_defensive` **is**
confirmed as a real, currently-used regime label in this codebase (found
directly in `run_a2118()`'s `execution_regime` output during this
investigation) -- the user's proposed gating regime name was correct.

Nearly every proposed Taiwan feature already has a computed, live-wired
counterpart inside `trough_nowcast.py` / `evaluate_00631l_multisource_crash_risk.py`:
TXO PCR (volume+OI, z-scored), foreign TXO put/call OI change, market
margin forced-repay/balance stress, SOXX put/call IV skew, USD/TWD
return/risk-off z-score, Amihud illiquidity (`amihud_z60`), TSM ADR
rebound-from-5d-low, 2330 rebound-from-5d-low, GroupA breadth, limit-down
count (`limit_down_count_groupa`). Only two proposed features are
genuinely not yet computed anywhere: TXO's own near/far-month IV term
structure specifically (only SOXX's put/call skew exists), and 台指期
basis.

A separate, directly-on-point prior investigation also exists:
`docs/a2119_reentry_regret_gate_and_trough_override_20260715.md` (07-15)
tested exactly this "opportunity is faster re-entry, not exit" framing,
found real-but-tiny value (+634 to +1,205 portfolio value on only 2
eligible days), and explicitly did not promote (too few eligible events,
no OOS windows).

**The user's cited numbers (entry->trough 1.33%, trough->H5 3.15%, T+1
leak 1.74%) do not appear anywhere in this repo** -- checked via direct
grep against `results/group_a_plus_trough_nowcast_buy_attempt_alignment_*.json`
and both existing handoff docs; only an unrelated disk-usage-percentage
false-positive substring match was found. These figures are not sourced
from this codebase's existing trough_nowcast analysis; their origin is
unconfirmed.

**Recommendation given to the user at this point**: don't build a new
module -- the existing one already covers the proposed design almost
exactly and has already been shadow-tested extensively without promotion.
If anything, add the two genuinely-missing features (TXO IV term
structure, 台指期 basis) to the *existing* module. But first check whether
the underlying blocker is really a feature gap or a sample-size problem,
since troughs are rare events by construction.

## Part 2: sample-size investigation

### 2a. Data-depth ceiling

`FinRL/data/stock_data.db`: `ohlcv` back to 2009-01-02, but
`taifex_options_daily` (TXO) only from **2020-01-02**,
`derivative_institutional_data` (foreign futures/options positioning) only
from **2018-06-05**, `margin_data` only from **2020-01-02**. No matter how
far back the NCF ML panel is backfilled, **any pre-2020 Taiwan correction
(e.g. 2015-2016) has zero options/institutional-flow feature coverage** --
a hard data ceiling, not a modeling limitation.

### 2b. Four paths considered, two chosen

1. Extend real backfills within the options-data-available window
   (2020+): cheap, uses the established `ncf_00631l.py --train-start
   2015-06-01 --val-start ... --full-panel` command family (same as the
   existing 2017-2019/2020/2022 backfills). **Chosen.**
2. Lower the trough definition threshold (smaller pullbacks, not just full
   bear-market troughs): most sample-increasing, but weakens correspondence
   to genuine capitulation. **Not chosen** -- risks redefining the very
   thing being measured.
3. Cross-market pooling (US options/VIX data, deeper history, more
   troughs including 2008): conflates "does the mechanism generalize
   across markets" with "does it work for Taiwan specifically," and
   Taiwan's corrections aren't independent of US ones anyway (beta to
   US tech/semis). **Not chosen.**
4. Synthetic scenario augmentation, using this project's already-adopted
   governance methodology from `docs/2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_REVIEW_20260718.md`
   (`build_group_a_plus_synthetic_augmentation_validation_audit.py`'s
   size-matched-null + block-permutation test, already governed, not
   ad hoc). That paper's own guidance: synthetic data is credible for
   *rare-regime diagnostics* (which trough detection is) and weak for
   near-efficient directional prediction. **Chosen as a future option**,
   not executed this session (superseded by the real-data path below,
   which turned out sufficient).

### 2c. Built three real backfills

Same command family as every prior backfill in this project:
```bash
python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 \
    --val-start <YEAR>-01-01 --val-end <YEAR>-12-31 --full-panel \
    --val-predictions-output results/ncf_00631l_panel_backfill_<YEAR>_20260726.csv \
    --output results/ncf_00631l_<YEAR>_backfill_20260726.json
```
- **2021**: 243 rows, 2021-01-04 to 2021-12-30. Run and verified first
  (real ML training, background, ~20 min).
- **2023**: 239 rows, 2023-01-03 to 2023-12-29.
- **2024**: 242 rows, 2024-01-02 to 2024-12-31.

Note on process: 2023 and 2024 were initially launched in parallel
background jobs; the user asked to run them sequentially instead ("跑會很久,
不然會跑很久") -- the 2024 job was killed (`kill`, confirmed via
`task-notification` exit code 144) and 2023 finished alone, then 2024 was
launched fresh afterward. Both completed successfully with the modern
schema (`actual_up_h20` present, etc.) -- confirmed better/newer than a
stale `results/ncf_00631l_panel_2023.csv` file found in the repo (created
2026-06-26, missing several modern columns like `prob_fwd_mdd_gt5_h20`
and `actual_up_h20`; not usable with current evaluators, superseded by the
fresh 2023 backfill).

### 2d. Found and worked around a real panel-mismatch bug in a shadow evaluator

`scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py`'s
`DEFAULT_WINDOWS` uses `PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"`
(confirmed date range: 2025-01-02 to 2026-07-06 only) for **both**
`covid_2020` (2020-01-02..2020-12-31) and `inflation_2022`
(2022-01-03..2022-12-30) -- zero date overlap in either case. This is the
same class of bug as the 07-16 DFL-advisory `covid_2020` panel-blind
finding (`GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md`
item #9), independently rediscovered here in a different evaluator. **Not
fixed in the source file this session** -- worked around by constructing a
corrected, explicit 9-window list (below) with the correct year-matched
panel for every window, which is what all further analysis in this
document uses. Flagging the source-level fix as a candidate for later,
lower-priority cleanup, since this evaluator's own `DEFAULT_WINDOWS` is
still wrong for anyone who runs it with `--windows default`.

### 2e. Nine-window sweep, corrected panels

```
2017_bull,2017-01-03,2017-12-29,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample
2018_correction,2018-01-02,2018-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample
2019_recovery,2019-01-02,2019-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample
covid_2020,2020-01-02,2020-12-31,results/ncf_00631l_panel_backfill_2020_20260716.csv,stress_window
2021_new_oos,2021-01-04,2021-12-30,results/ncf_00631l_panel_backfill_2021_20260726.csv,out_of_sample
inflation_2022,2022-01-03,2022-10-29,results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv,stress_window
2023_recovery,2023-01-03,2023-12-29,results/ncf_00631l_panel_backfill_2023_20260726.csv,out_of_sample
2024_bull,2024-01-02,2024-12-31,results/ncf_00631l_panel_backfill_2024_20260726.csv,out_of_sample
active_2025_2026,2025-01-02,2026-07-24,results/ncf_00631l_panel_latest_20260725.csv,tuning_window
```

`evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py --windows "<above>"`:

```
window            missed_rebound_without_partial   partial_reentry_days   buy_attempt_days
2017_bull                13                              0                      46
2018_correction          22                              0                      82
2019_recovery            11                              0                      38
covid_2020               29                              8 (now correctly counted -- was
                                                              likely undercounted before
                                                              due to the panel mismatch)
2021_new_oos             39                              1                     101
inflation_2022           18                             18 (ditto -- previously panel-blind)
                                                                                  92
2023_recovery            19                              0                      46
2024_bull                32                              0                      66
active_2025_2026         66                             14                     159
TOTAL                   249                             41                     706
```

**Key finding**: in the three genuinely new OOS years (2021, 2023, 2024),
`PARTIAL_REENTRY` fires essentially never (0, 0, 1) -- consistent with
these being calm bull years without real capitulation events. Real signal
concentrates in `covid_2020`, `inflation_2022` (both newly-corrected here),
and `active_2025_2026`.

## Part 3: three rounds of self-correction on the economic value question

This section is deliberately kept as a full, honest record of the
correction process itself, not just the final number -- each of the first
two conclusions was wrong for a specific, identified reason, and the
process of finding those reasons is itself informative about how these
evaluators work.

### 3a. First claim (WRONG): "8 of 9 windows show zero economic effect"

Ran `evaluate_group_a_plus_trough_nowcast_shadow.py` (not the
buy-attempt-alignment script) across the same 9 corrected windows and
compared `staging_counterfactual.delta_accelerated_minus_baseline` per
window. Result: **exactly zero** `final_value`/`sharpe_ratio`/
`max_drawdown` delta in 8 of 9 windows (including `covid_2020` with 8
`PARTIAL_REENTRY` days and `inflation_2022` with 18), and a small
*negative* delta in `active_2025_2026` (-1,349 final value, -0.0059
Sharpe). Verified `covid_2020`'s baseline vs. accelerated metrics dicts
were **byte-identical**, ruling out rounding-level near-zero and
confirming a structural non-effect in this specific evaluator.

**Root cause found**: `simulate_staging_policy()` inside that file only
re-evaluates `buy_fraction` when `regime != current_regime` (i.e., only on
the single day a regime transition happens) -- it never looks at
`trough_state` again until the *next* regime change. Confirmed directly:
in `covid_2020`, `execution_regime` changed to `group_a_plus_defensive` on
**2020-02-18** and did not change again until **2020-06-03** (a single
3.5-month continuous defensive stretch); `PARTIAL_REENTRY` didn't fire
until **2020-03-23** (over a month into that stretch, since it requires
capitulation *and* confirmed rebound, which by construction develops after
the regime shift, not on day one). By the time the signal existed, this
evaluator's simulation had already frozen its buy-fraction decision back
on 02-18 and never revisited it.

### 3b. Correction: this is a shadow-evaluator artifact, not production behavior

Checked `group_a_plus/operations/execution_plan.py`'s
`_trough_nowcast_buy_fraction()` directly: it reads `signal["trough_nowcast"]["state"]`
fresh every time `execution_plan.py` runs (i.e., daily, as part of the
daily pipeline) -- **no dependency on whether the regime changed that
day**. Production does not have the limitation found in 3a. This means
**the "zero effect" claim in 3a was an artifact of a specific shadow
evaluator's crude simulation design, not evidence about real production
behavior or about `trough_nowcast`'s underlying value.** The evaluator
limitation is real and worth fixing eventually (it likely understated
`trough_nowcast`'s apparent value in every "not promoted" verdict that
relied on it, including the original 07-14 handoff), but was not fixed
this session -- flagged as a known issue only.

Cross-checked against the buy-attempt-alignment script's per-event data:
on 2020-03-23 specifically, a real buy attempt occurred with `trough_state:
PARTIAL_REENTRY`, `attempted_buy_weight: {0050.TW: 0.0169}`,
`executed_buy_weight: {0050.TW: 0.0118}` -- ratio ~0.7, exactly matching
the intended `partial_buy_fraction`. Production-style logic does engage
correctly when both conditions align.

### 3c. Second calc (WRONG in a different way): a rough +1,454 TWD estimate with sign-anomaly contamination

Computed, for every event across all 9 windows with `trough_state` in
`(PARTIAL_REENTRY, FULL_REENTRY)`: `incremental_weight = executed - attempted*0.4`
(the counterfactual baseline fraction), multiplied by the ticker's forward
5-day return and portfolio value, summed. Got **+1,454.1 TWD** total --
but several `00631L.TW` events showed *negative* incremental values (e.g.
`2026-03-05: -0.04203`), which is structurally impossible if `executed`
were always `attempted * (0.7 or 0.4)`.

**Root cause found**: those events had `blocked: {"00631L.TW":
"volatility_gate_high_vol"}` and `executed_buy_weight: {}` (empty) for
that ticker -- the trade was blocked *entirely*, independent of
`buy_fraction`. The calculation wrongly assumed the baseline-fraction
(0.4) trade would have executed unblocked, when in reality the same
volatility-gate/extreme-risk block would have applied regardless of
acceleration. Confirmed directly on the `2026-03-05` event: `attempted:
{00631L.TW: 0.105087}`, `executed: {}`, `blocked:
{00631L.TW: "volatility_gate_high_vol"}`.

### 3d. Final, clean calculation

Restricted strictly to `trough_state == "PARTIAL_REENTRY" and
allowed_fast_reentry == True` (the script's own definition of "genuinely
accelerated, not blocked" -- exactly matching the aggregate
`allowed_fast_reentry_days: 7` figure from the alignment summary):

```
window            date         ticker    incremental_weight   fwd_5d_return   value(TWD)
covid_2020        2020-03-23   0050.TW        +0.51%             +7.13%          +318
inflation_2022    2022-03-09   0050.TW        +0.11%             -0.23%            -2
inflation_2022    2022-07-18   0050.TW        +0.09%             +2.19%           +17
active_2025_2026  2025-10-02   0050.TW        +0.98%             +3.04%          +341
active_2025_2026  2026-02-03   0050.TW        +0.62%             +3.50%          +300
active_2025_2026  2026-02-23   0050.TW        +2.98%             +1.74%          +749
active_2025_2026  2026-02-26   0050.TW        +0.25%             -5.30%          -194

TOTAL: +1,527.6 TWD (7 events, ~NT$1-1.4M portfolios, 9-year sample)
```

**Final verdict**: production's mechanism is correct and does engage as
designed (3b) -- the earlier "zero effect" claim (3a) was wrong, an
artifact of one specific shadow evaluator's crude simulation. But once
correctly measured (3d, excluding the guard-blocked contamination from
3c), the real economic value is **negligible** -- roughly NT$1,528 of
cumulative benefit on a ~NT$1M portfolio across 9 years, i.e., on the
order of 0.15% *total*, not annualized. 5 of the 7 genuinely-eligible
events are in the most recent `active_2025_2026` window, not historical
crises -- the mechanism has essentially never mattered economically in
any of the real stress windows (2018, 2020, 2022) tested.

## Conclusion

Across three related research threads today (00631L<->0050 relative
rotation -> relief-gate -> trough re-entry), the pattern converges: each
mechanism is well-motivated, has a working implementation (either
pre-existing or built this session), and each measured economic value is
too small (or, per the relief-gate's H6, doesn't generalize OOS) to
justify further engineering investment. This thread specifically
concludes: **do not build the proposed new `trough_reentry_nowcast.py`
module** -- the existing `trough_nowcast.py` already covers its design
almost exactly, is already correctly wired into production, and (once
measured cleanly, correcting two rounds of the author's own calculation
errors) delivers economic value on the order of noise. The one concrete,
still-open item is the `evaluate_group_a_plus_trough_nowcast_shadow.py`
`DEFAULT_WINDOWS` panel-mismatch bug (2d) -- low priority, since it only
affects a diagnostic evaluator's own default convenience windows, not any
live decision, but should be fixed if that evaluator is used again.

## What was NOT done

- The `evaluate_group_a_plus_trough_nowcast_shadow.py` `DEFAULT_WINDOWS`
  panel-mismatch was not fixed at the source -- only worked around via an
  explicit corrected `--windows` argument for this session's analysis.
- The two genuinely-missing Taiwan features (TXO's own IV term structure,
  台指期 basis) were not built.
- The synthetic-augmentation path (2b, option 4) was not executed -- the
  real-data 9-window expansion turned out sufficient to reach a
  conclusion without it.
- No attempt was made to add a fourth backfill year (e.g. a second half of
  2022, or 2015-2016 pre-options-data years) -- the data-depth ceiling
  (Part 2a) makes pre-2020 years unable to compute the options/flow
  features this mechanism depends on regardless of ML backfill effort.
- `trough_nowcast.py` and `execution_plan.py` themselves were read but not
  modified -- confirmed correct, no fix needed there.

## Reproduction commands

```bash
# The three new backfills (same command family as all prior backfills)
python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start 2021-01-01 --val-end 2021-12-31 --full-panel \
    --val-predictions-output results/ncf_00631l_panel_backfill_2021_20260726.csv --output results/ncf_00631l_2021_backfill_20260726.json
python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start 2023-01-01 --val-end 2023-12-31 --full-panel \
    --val-predictions-output results/ncf_00631l_panel_backfill_2023_20260726.csv --output results/ncf_00631l_2023_backfill_20260726.json
python3 scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start 2024-01-01 --val-end 2024-12-31 --full-panel \
    --val-predictions-output results/ncf_00631l_panel_backfill_2024_20260726.csv --output results/ncf_00631l_2024_backfill_20260726.json

# The corrected 9-window sweep (buy-attempt alignment + shadow staging counterfactual)
WINDOWS="2017_bull,2017-01-03,2017-12-29,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample;\
2018_correction,2018-01-02,2018-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample;\
2019_recovery,2019-01-02,2019-12-31,results/ncf_00631l_panel_backfill_2017_2019_20260710.csv,out_of_sample;\
covid_2020,2020-01-02,2020-12-31,results/ncf_00631l_panel_backfill_2020_20260716.csv,stress_window;\
2021_new_oos,2021-01-04,2021-12-30,results/ncf_00631l_panel_backfill_2021_20260726.csv,out_of_sample;\
inflation_2022,2022-01-03,2022-10-29,results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv,stress_window;\
2023_recovery,2023-01-03,2023-12-29,results/ncf_00631l_panel_backfill_2023_20260726.csv,out_of_sample;\
2024_bull,2024-01-02,2024-12-31,results/ncf_00631l_panel_backfill_2024_20260726.csv,out_of_sample;\
active_2025_2026,2025-01-02,2026-07-24,results/ncf_00631l_panel_latest_20260725.csv,tuning_window"

python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py --windows "$WINDOWS" --output /tmp/trough_buy_alignment_9win.json
python3 scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py --windows "$WINDOWS" --output /tmp/trough_shadow_9win.json
```

## Files referenced

New this session:
- `results/ncf_00631l_panel_backfill_2021_20260726.csv` / `_2021_backfill_20260726.json`
- `results/ncf_00631l_panel_backfill_2023_20260726.csv` / `_2023_backfill_20260726.json`
- `results/ncf_00631l_panel_backfill_2024_20260726.csv` / `_2024_backfill_20260726.json`

Read/analyzed, not modified:
- `group_a_plus/integrations/trough_nowcast.py`
- `group_a_plus/operations/execution_plan.py` (`_trough_nowcast_buy_fraction`)
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_shadow.py` (bug
  found in `DEFAULT_WINDOWS` / `simulate_staging_policy`, not fixed)
- `scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py`
- `GROUP_A_PLUS_TROUGH_NOWCAST_SHADOW_HANDOFF_20260714.md`
- `docs/a2119_reentry_regret_gate_and_trough_override_20260715.md`
- `docs/2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_REVIEW_20260718.md`
- `/mnt/c/Users/isaac/Downloads/2509.05922v1.pdf` (the reviewed paper)
- `results/ncf_00631l_panel_2023.csv` (stale, superseded, schema-incompatible
  file discovered during this investigation -- not deleted)
