# A21.19 Continuous Defensive Tilt Shadow Candidate Handoff - 2026-07-23/24/25

## 2026-07-25 session summary (read this first if picking up from today)

**Trigger.** This session opened mid-conversation with "之前有當未完成，要繼續"
(prior work left unfinished, continue it) with no other context -- multiple
candidate threads existed in the repo, so the user was asked which one via
`AskUserQuestion` and picked **A21.19's next step** specifically (not the
`run_a2118()` architecture refactor, the other live option). All three
sub-investigations below followed directly from that choice, in order,
each one picking up exactly where the prior addendum's "still open" list
left off. Partway through, the user separately asked whether
`C:\Users\isaac\Downloads\2605.20636v2.pdf` (the paper A21.19 itself
originated from) was "fully researched" -- answer given: two of its three
components were (validation methodology adopted, core continuous-score
idea tested to exhaustion as A21.19 itself), but its third component
(growth-crowding penalty) had only ever been noted as "worth a future
debate," never tested. User said "可以試試" (worth trying) -- that became
addendum #7.

**What was tested, in order, and the verdict on each (all three: tested,
rejected, no promotion, no production impact):**

1. **Addendum #5 -- wider no-trade band** (picking up addendum #4's "should
   be tried before concluding on economics" note). Swept `no_trade_band ∈
   {0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10}` × 3 windows (2024-2026
   tuning, 2020 COVID, worst rolling fold 2020-06..2022-06), floor on.
   **Along the way found and fixed a real floating-point boundary bug**
   in `_apply_no_trade_band` (`abs(0.4-0.5) == 0.09999999999999998 <
   0.10`, so a band exactly equal to a real drift silently never
   executed) -- fixed in this script **and** in the separate copy inside
   `evaluate_a2118_live_overlay_backtest_gap.py` (the citation-rule
   "CANONICAL TOOLING" script), and explicitly re-verified the citation
   rule's already-cited headline numbers (61.96%/2.1521 baseline,
   52.62%/2.2157 overlay for 2025-01-02..2026-07-23 @ band=0.005) are
   **byte-identical before and after the fix** -- 0.005 never happens to
   exactly equal a continuous-signal drift the way 0.10 exactly equaled a
   discrete a207 regime-table jump. Economic verdict once the bug no
   longer confounded the comparison: wider bands cut turnover/cost a lot
   (tuning window 208→48 rebalances, $85k→$31k) but annual-return delta
   gets **worse**, not better, in 2 of 3 windows (monotonically in the
   tuning window); the floor's MaxDD guarantee is band-width-robust once
   fixed. **Rejected.**

2. **Addendum #6 -- lower tilt-update frequency** (addendum #5's other
   still-open idea from #4). Added `tilt_update_freq_days` to
   `build_defensive_tilt()` -- recompute the raw VIX tilt only every N
   trading days, holding flat between updates, while the regime floor
   still checks a207's actual daily regime every day regardless (a
   deliberately different mechanism from the no-trade band, which delays
   *execution* of an already-computed target). Swept `freq ∈ {1, 2, 3, 5,
   10, 20}` × same 3 windows, `no_trade_band=0.005` fixed. Same
   qualitative result as #5: turnover/cost drops substantially
   (208→19 rebalances, $85k→$19.5k in the tuning window) but annual-return
   delta gets worse in every window (2020 COVID roughly doubles its drag
   at just `freq=2`), confirming the VIX tilt's own daily responsiveness
   -- not just the regime floor -- matters during a fast crash. MaxDD
   floor guarantee held (non-negative) at every frequency tested,
   confirming it is genuinely decoupled from tilt staleness by design.
   **Rejected.**

3. **Addendum #7 -- growth-crowding penalty** (closing the last open item
   from the original 07-23 six-paper review of arXiv:2605.20636v2, not
   from addendum #4). Built a new `growth_crowding` component (126-
   trading-day trailing relative return of `0050.TW` over `00679B.TWO`,
   z-scored) and a `_load_local_close_series` helper (the local `ohlcv`
   table, since `00679B.TWO` isn't in the yfinance-backed
   `external_market_ohlcv` table the other components read from). Added
   as `w5_crowding` in `DEFAULT_WEIGHTS` (default 0.0). **Found and fixed
   a second bug along the way**: `evaluate()` had no `weights` parameter
   at all, so `build_defensive_tilt`'s `weights` argument was permanently
   bound to the module-level `DEFAULT_WEIGHTS` object at function-
   definition time (Python's classic late-binding-default gotcha) --
   monkeypatching the module attribute between sweep calls silently
   produced byte-identical results for every blend (caught immediately:
   15/15 rows identical to 6 decimals). Fixed by adding a real `weights`
   parameter to `evaluate()`, threaded through to `build_defensive_tilt`
   and the output JSON's (previously also-inert) `weights_used` field.
   IC check: correctly signed on all three metrics (fwd5d IC=-0.096
   p=0.019, fwd20d IC=-0.032 p=0.448, fwd20d-maxDD IC=-0.077 p=0.063) --
   unlike `rate_stress`/`tsmc_crowding`, this is a real standalone signal.
   But blended into the tilt across the same 3 windows × 5 VIX/crowding
   ratios, annual-return delta got **monotonically worse in all three
   windows** as crowding weight increased, with only one narrow, non-
   generalizing Sharpe exception (tuning window, `w5=0.5`, at the cost of
   3.2pp more annual-return drag in that same window). Likely mechanism:
   the 126-day lookback stays elevated well into a V-shaped recovery
   (same "stuck defensive after the fact" pattern as the base VIX tilt's
   07-24 fast-recovery investigation, but from lag structure rather than
   VIX's own crash-and-recover shape). `w5_crowding` stays at 0.0.
   **Rejected**; this also formally closes the "worth a future debate"
   note in `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`'s
   arXiv:2605.20636v2 section (updated today to point here).

4. **Addendum #8 -- separately, the user asked whether a new paper
   (`C:\Users\isaac\Downloads\2607.06117v1.pdf`, "Relief-Gated Relative
   Rotation for QQQ-DIA Allocation", same Xiong lineage as arXiv:2605.
   20636v2) had anything importable.** Full review written to
   `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`: no
   direct strategy import (same asset-universe-mismatch pattern as every
   non-RL paper reviewed this project), but two real takeaways -- (a) its
   incremental-OOS-admission discipline for higher-order interaction terms
   was formalized as a new item 6 in `GROUP_A_PLUS_SIGNAL_VALIDATION_
   CHECKLIST_20260723.md` (this is exactly the rule that would have
   predicted addendum #7's `growth_crowding` failure formally instead of
   by ad hoc sweep); (b) its `credit_relief`/`credit_stress` construction
   (HYG minus SHY relative return) is real, ordinary yfinance data that
   reopens a door A21.19's own docstring had closed ("no credit-spread
   data source"). User said to continue, so both were acted on: the
   checklist was updated, and HYG/SHY were fetched and tested as a new
   `credit_stress` component (`w6_credit`) exactly like `growth_crowding`
   was tested in addendum #7. **Unlike every other test this session,
   this one was not a clean rejection**: standalone IC is the strongest of
   any non-VIX component tested to date (fwd20d-maxDD IC=-0.180,
   p<0.0001), and blended as a modest *additive* term on top of full VIX
   weight (`vix1.0_credit{0.5,1.0}`, not replacing VIX), it improves both
   annual-return and Sharpe delta in 3 of 4 windows tested (2020 COVID,
   worst rolling fold, and a newly-added 2018 trade war window), with only
   the already-well-understood 2024-2026 bull-regime window costing more.
   This is the first component in this candidate's entire history (base
   four terms + `growth_crowding`) to show a genuinely positive,
   multi-window pattern rather than a uniformly negative or single-window-
   noisy one. **User said to continue again, so the remaining checklist
   items were completed in addendum #9**: item 1 (walk-forward expanding,
   2017-2019 OOS) passes cleanly on all three metrics; item 2 (walk-forward
   rolling, the same 8 folds as addendum #3) passes with 6 of 8 folds
   improving both annual return and Sharpe simultaneously; item 3
   (crisis-independence) is partial -- the valid calendar-year 2017/2018/
   2019 split passes (2 of 3 years positive, meeting the RGRR paper's own
   admission bar), but an attempted deeper 2020 sub-window decomposition
   surfaced a genuine methodological limitation (sub-60-trading-day
   windows can't show any tilt divergence at all, because `_zscore`'s
   `min_periods=60` forces every component to its zero fallback) rather
   than producing a real finding either way; item 4 (cost-sensitivity)
   passes cleanly -- credit's advantage over VIX-only holds at every cost
   multiplier from 1.0 down to 0.0 in both windows tested.

5. **User then asked to pursue both remaining threads: the sub-60-day
   cold-start limitation itself, and more backtests generally -- addendum
   #10.** Fixing the limitation properly (a new `warmup_days` parameter,
   fetching real pre-window history for the external-series components)
   answered the specific mechanistic question cleanly: the 2020 crash-only
   sub-window is still perfectly identical across every tilt configuration
   even with a fully "hot" tilt signal, because a207's own regime floor is
   **100% binding for all 28 days of the acute crash** -- no tilt
   composition can matter once the floor is that saturated, a real finding,
   not an artifact. But re-testing addendum #8's full "3 of 4 windows
   improve" headline with genuine warmup **downgraded it to a much weaker,
   genuinely mixed 3 of 5**, with the flips landing on exactly the two real
   crisis windows (2018 trade war, 2020 COVID both flip from favoring
   credit to hurting it). Worse, the same test on the plain `vix_only`
   baseline (no credit involved) revealed this cold-start bias has been
   present in **every fixed-window number reported for this candidate
   since addendum #2** -- not a credit-specific issue. `warmup_days`
   defaults to 0 (preserving every prior addendum's exact numbers, since
   flipping the default now would silently break comparability across
   this whole document), with the bias and its magnitude now explicitly
   documented rather than lurking unnoticed. **Verdict revised down**:
   `credit_stress` is not promoted -- still a real, non-trivial signal by
   its IC and cost-sensitivity properties, but its multi-window case is
   genuinely mixed once realistically tested, not the "strongest evidence"
   framing addendum #9 used a few hours earlier in the same session.

6. **User asked "下一步" (what's next); recommended and then confirmed
   re-baselining the *regime floor's own* core claim under warmup=756,
   since addendum #10 established the bias isn't credit-specific --
   addendum #11.** Re-ran `vix_only`, both floor settings, at both warmup
   settings, across all 8 rolling folds plus 2017-2019 OOS/2018/2020/
   2024-2026 (48 calls). **Good news**: the regime floor's foundational
   claim (`max_drawdown` delta non-negative in 8 of 8 rolling folds with
   the floor on, only 3 of 8 without it) is **unchanged, fold-for-fold
   identical, at `warmup_days=756`** -- not an artifact of the cold-start
   bias, independently re-confirmed. One small crack: the special
   `covid_2020` full-year window (not one of the 8 folds) shows a tiny
   -0.14pp deviation from exact parity under warmup=756, negligible next
   to the -9.35pp problem the floor was built to fix. Annual-return/Sharpe
   deltas for `vix_only` itself do shift window-by-window (no consistent
   direction), but the mechanism this candidate's entire regime-floor
   design rests on holds up under its most rigorous test yet.

7. **User confirmed continuing to complete `credit_stress`'s remaining
   checklist items (2, 3, 4) at `warmup_days=756` -- addendum #12, the
   final word on `credit_stress` this session.** The 8-fold rolling result
   weakens further (6/8 clean wins at `warmup=0` down to 4/8 clean, 2/8
   clean losses, 2/8 mixed at `warmup=756`); the crisis-independence split
   still shows 2 of 3 years positive but 2017 and 2018 swap which one is
   the outlier; cost-sensitivity is robust *within* each window but now
   points in **opposite directions between the two crisis-adjacent
   windows** (worse at every cost level in 2020 COVID, better at every
   cost level in the worst rolling fold). **Consolidated final read**:
   `credit_stress` helps in calmer/grinding/recovery periods and hurts in
   both real crisis episodes actually tested (2018, 2020), consistently
   across cost assumptions -- a materially more cautious conclusion than
   addendum #9's "strongest evidence" or even addendum #10's "genuinely
   mixed 3-of-5." Not promoted; not recommended as a near-term lead in its
   current construction.

**Net result of the whole session: four ideas tested, three rejected, one
(`credit_stress`) initially looking like the strongest evidence this
candidate had produced, then self-corrected in two further rounds down to
a specific, concerning pattern (helps outside real crises, hurts inside
them) once a real methodological blind spot was found, fixed, and applied
exhaustively; two real bugs found and fixed; one significant
methodological limitation discovered that retroactively affects every
prior fixed-window number for this candidate, not just today's new
component; one new paper reviewed; one new data source (HYG/SHY) added;
the standing validation checklist gained a new item; zero production
changes.** The candidate's overall verdict is unchanged: **do not promote
A21.19 as a whole**, and its *default*
configuration is unchanged today -- VIX-only weights, regime floor on,
`no_trade_band=0.005`, `tilt_update_freq_days=1`, `w6_credit=0.0`,
`warmup_days=0` (all defaults, unchanged) -- but the single most important
takeaway for whoever continues this candidate is methodological, not a
specific signal: **re-run any serious future evaluation of this
candidate, including its existing `vix_only` baseline across the windows
in this document, at `warmup_days=756` before trusting the magnitude of
any headline number**, since the cold-start bias documented in addendum
#10 has been present, uncorrected, throughout this entire document.

**Files touched today (complete list):**
- Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
  (fp-boundary fix in `_apply_no_trade_band`; `tilt_update_freq_days` param
  + logic in `build_defensive_tilt`; `growth_crowding` component +
  `_load_local_close_series` helper + `w5_crowding` in `DEFAULT_WEIGHTS`;
  real `weights` param added to `evaluate()`, fixing the late-binding bug;
  `--tilt-update-freq-days` CLI flag added)
- Modified: `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`
  (same fp-boundary fix in its own independent copy of
  `_apply_no_trade_band`; this is the citation-rule canonical script, so
  cited numbers were explicitly re-verified unaffected)
- Modified: `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`
  (this file -- addenda #5, #6, #7 + this summary + Status block)
- Modified: `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`
  (growth-crowding-penalty note updated from "noted, not acted on" to
  "tested 2026-07-25, closed with a negative result", pointing to
  addendum #7)
- Modified: `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` (new
  item 6, incremental-OOS-admission for new signal/interaction terms)
- New: `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md` (full
  paper review)
- New data: `HYG`/`SHY` daily closes in `external_market_ohlcv`
  (2015-01-02..2026-07-24, via `fetch_cross_market_ohlcv.py --tickers
  HYG,SHY`) -- not a code change, a data backfill
- New: `results/a2119_no_trade_band_sweep_20260725.json` (21 rows)
- New: `results/a2119_tilt_update_freq_sweep_20260725.json` (18 rows)
- New: `results/a2119_growth_crowding_penalty_sweep_20260725.json` (15 rows)
- New: `results/a2119_credit_stress_hyg_shy_sweep_20260725.json` (20 rows)
- New: `results/a2119_credit_stress_walkforward_expanding_rolling_20260725.json`
  (item 1+2: 2017-2019 OOS + 8 rolling folds, 18 rows)
- New: `results/a2119_credit_stress_crisis_independence_20260725.json`
  (item 3: 2017/2018/2019 split + 2020 sub-window attempts, 14 rows)
- New: `results/a2119_credit_stress_cost_sensitivity_20260725.json`
  (item 4: cost-multiplier sweep, 16 rows)
- New: `results/a2119_credit_stress_warmup_extension_2020_20260725.json`
  (addendum #10: 2020 sub-windows, warmup 0 vs 756, 16 rows)
- New: `results/a2119_credit_stress_warmup_main_windows_20260725.json`
  (addendum #10: all 5 main windows, warmup 0 vs 756, 20 rows)
- **No production files touched** -- not `execution_plan.py`,
  `daily_signal.py`, `strategy.json`, `live_signal.json`, or any file
  under `report/group_a_plus/latest/`. Every change today is confined to
  two research/citation scripts, one standing process doc, one new review
  doc, one new external data backfill, and their own result files.

**Verification performed (this script has no dedicated pytest file --
it's research-only, per its own docstring; verification was direct
reproducibility spot-checks, not a test suite):**
- Re-ran the default (VIX-only, `no_trade_band=0.005`, `tilt_update_freq_
  days=1`, `w5_crowding=0.0`, `w6_credit=0.0`) config after all edits
  landed: metric deltas exactly match addendum #2's originally-validated
  numbers (`ann_d=-5.41%, sharpe_d=+0.440, maxdd_d=+6.86pp`) -- confirms
  none of today's additions changed default behavior.
- Re-ran the citation-rule script's actual cited comparison
  (2025-01-02..2026-07-23, `no_trade_band=0.005`) with a scratch pre-fix
  copy vs. the fixed version: identical to the last printed decimal.
- Confirmed via `grep` that `_apply_no_trade_band` exists in exactly these
  two files project-wide (no other copies to audit or fix).

**What's still genuinely open for A21.19, most concrete first:**
0. **The `warmup_days=756` re-evaluation (addendum #10) is the single most
   important open thread, and applies to more than `credit_stress`**: every
   fixed-window number in this document (including the `vix_only` baseline
   itself) was computed with an implicit cold-start bias. Before any
   further promotion decision on `credit_stress`, or any confident claim
   about this candidate's headline numbers generally, re-run the standing
   windows at `warmup_days=756` and treat those as the trustworthy figures.
   `credit_stress` itself is now a genuinely mixed 3-of-5-windows signal at
   `warmup_days=756` (both crisis windows flip negative) -- not a
   promotion candidate on today's evidence, but also not cleanly rejected
   like `growth_crowding` -- its standalone IC and its cost-sensitivity
   robustness are real properties independent of this warmup question.
1. The 2019-2023 structural conservatism drag (addendum #3) -- a real
   cost of the regime floor doing exactly what it's designed to do during
   a period a207 itself ran conservative; not a bug, needs a design
   change if it's ever to be reduced.
2. A natively lower-frequency-*constructed* signal (not a post-hoc damping
   of a daily signal via band or freq -- both now tested and rejected) --
   would need real redesign work, not a parameter.
3. 2008/2011/2015 remain permanently untestable for this specific
   candidate (00631L/00632R/00679B.TWO/^VIX data availability), unchanged
   since 07-23. (HYG/SHY, now fetched back to 2015-01-02, do not extend
   this -- 00631L/00632R/00679B.TWO are still the binding constraints.)
4. If growth-crowding is ever revisited: the 126-day lookback is the
   likely culprit for its lag-driven failure during the 2020 recovery;
   a shorter lookback or an explicit rate-of-change term would be the
   natural next experiment, not re-sweeping the same signal's weight.

**Cross-session memory saved today** (Claude's persistent memory, not part
of the repo): `project_a2119_no_trade_band_sweep_fp_bug_20260725`,
`project_a2119_tilt_update_freq_sweep_20260725`,
`project_a2119_growth_crowding_penalty_tested_20260725`,
`project_rgrr_qqq_dia_paper_review_20260725`,
`project_a2119_credit_stress_hyg_shy_20260725`,
`project_a2119_credit_stress_full_checklist_20260725`,
`project_a2119_warmup_bias_discovery_20260725`,
`project_a2119_regime_floor_survives_warmup_recheck_20260725`,
`project_a2119_credit_stress_final_verdict_20260725`.

---

## Status

**2026-07-25 update**: addenda #5 and #6 (end of document) closed both of
addendum #4's remaining open turnover-reduction ideas -- a wider no-trade
band (#5) and a lower tilt-update frequency (#6) -- with the same verdict:
neither recovers better after-cost economics, because this candidate's
turnover is tied to genuine signal responsiveness, not filterable noise.
Addendum #5 also found and fixed a real floating-point boundary bug in
`_apply_no_trade_band` (present in this script and, separately, in the
citation-rule "CANONICAL TOOLING" script
`evaluate_a2118_live_overlay_backtest_gap.py` -- fixed in both; confirmed
the citation rule's already-cited headline numbers are unaffected). Verdict
unchanged: **do not promote**. No parameter-sweep avenues remain open for
this candidate's cost/turnover problem -- only a genuine redesign (2019-2023
conservatism drag, or a natively lower-frequency signal construction) would
be worth trying next. Addendum #7 separately tested and closed the last
open item from the original arXiv:2605.20636v2 review (the growth-crowding
penalty component, previously only "noted, not acted on") -- correctly
signed IC in isolation, but a clean net-negative once backtested in every
window; `DEFAULT_WEIGHTS` unchanged.

**Shadow-only, research candidate, still NOT promotion-ready.** The 2020
root cause identified in the first 07-24 addendum has been fixed and
validated on both the original 4 fixed windows and, now, 8 independent
walk-forward rolling folds spanning the full available history (see the
second and third 07-24 addenda at the end of this document). No
production file touched. Script:
`scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`.
The regime-floor fix (never let the continuous tilt be more risk-on than
a207's own discrete regime that day, ticker by ticker) is now on by
default; pass `--no-regime-floor` to reproduce the old regime-blind
behavior. `DEFAULT_WEIGHTS` was also corrected to the VIX-only config
that the 07-23 by-window results table actually used (it had drifted back
to equal-weight in the persisted script). **All four items of the
2026-07-23 validation checklist have now been run for this candidate**
(see the four 07-24 addenda below): walk-forward expanding (2017-2019
OOS), walk-forward rolling (8 independent folds), crisis-independence
(2017/2018/2019 split -- direction holds, magnitude is crisis-concentrated),
and cost sensitivity (this candidate is materially cost-sensitive, unlike
a2118 itself -- turnover is 6-50x a207's own even with the no-trade band
applied). 2008/2011/2015 remain untestable for this specific candidate
(data availability) so item 3 is still only 2/5-covered by episode count,
though the direction-independence check that data does allow was run.
Bottom line unchanged: **do not promote** -- the regime-floor fix is
confirmed robust for its narrow purpose, but two real structural costs
(2019-2023 conservatism drag, transaction-cost drag from turnover) remain
unaddressed.

## Origin

Direct follow-up to the user's own design proposal (same 2026-07-23
session as `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`'s
arXiv:2605.20636v2 review, which explicitly recommended against importing
continuous-score allocation as a strategy change -- this is the user
testing that idea anyway, as a properly bounded, shadow-only, own-range
experiment, which is a legitimately different and better-controlled
proposition than a blanket import).

Design: replace a207's discrete golden1/defensive/recovery switch with a
continuous `defensive_tilt` score (0-1), linearly interpolating portfolio
weights between the real production `golden1` weights and the real
production `bond30_cash30` defensive basket (with 00631L's floor
deliberately raised from 0% to 10%, per explicit user request to soften
the current hard cutoff), instead of a hard regime jump.

## Implementation notes and mid-session corrections

1. **`credit_stress` term dropped.** The user's original 5-term sketch
   included a credit-spread signal; this project has no real BAA/10Y, HY
   OAS, or Taiwan-equivalent credit-spread data source (confirmed by grep
   across `scripts/fetch/*.py`). Fabricating a proxy would violate this
   project's real-data-only convention, so w5 was simply omitted. Can be
   reinstated if credit data is ever added.
2. **Bug found and fixed**: `tsmc_crowding` was silently always 0.0 for
   the entire first test run -- the script looked for a `frame["close"]`
   column that doesn't exist; the actual column is `frame["0050_close"]`.
   Fixed. Confirmed via component-level diagnostics
   (`tsmc_crowding.std() == 0.0` before the fix).
3. **Deeper design bug found and fixed (not just the column-name bug)**:
   the original formula `defensive_tilt = 0.5*(1+tanh(risk_score))`
   mathematically centers at ~0.5 whenever the underlying components are
   z-scored against their own rolling history (mean ~0 by construction) --
   this is *correct* for the source paper's problem (genuine 50/50 G-vs-D
   style rotation, a real neutral prior) but *wrong* for a207's regime
   problem (golden1/risk-on is the normal state most of the time;
   defensive is a rare event). First test run showed `defensive_tilt.mean()
   = 0.507` even during a mostly-bullish 2024-2026 window -- confirming the
   score was structurally defensive-leaning ~half the time regardless of
   actual conditions, not tracking real risk. **Fix applied**:
   `defensive_tilt = tanh(relu(risk_score))` -- floors at 0 (golden1-like)
   during calm periods, only rises toward 1 when the combined signal is
   genuinely elevated above its own baseline. Confirmed the fix worked:
   `mean` dropped to 0.179, `min` correctly hits 0.0.
4. **Per-component IC (information coefficient) diagnostic run before
   further tuning** (2024-01-02..2026-07-23, Spearman correlation of each
   raw component against 0050's forward 5d/20d return and forward-20d max
   drawdown):

   | Signal | IC fwd5d | IC fwd20d | IC fwd20d maxDD | Verdict |
   |---|---|---|---|---|
   | drawdown_severity | -0.004 | -0.042 | -0.152 | weak but correct sign |
   | rate_stress (ΔTNX21d) | +0.056 | +0.170 | +0.140 | **wrong sign** |
   | vix_stress (VIX percentile) | -0.106 | -0.189 | -0.274 | **correct sign, strongest** |
   | tsmc_crowding | +0.099 | +0.090 | +0.166 | **wrong sign** |

   `rate_stress` and `tsmc_crowding`, as constructed, were *inversely*
   related to what a defensive signal should predict in this window --
   high rate stress and TSMC-outrunning-the-rest both preceded *better*
   subsequent 0050 returns and *shallower* drawdowns, not worse. Equal-
   weighting all four (the user's original sketch) was diluting the one
   genuinely useful signal (VIX) with two counter-productive ones. This is
   not a tuning choice, it's a correctness finding -- do not re-add
   `rate_stress`/`tsmc_crowding` to the score without first re-validating
   their sign on independent data; this window's IC could itself be
   regime-specific.
5. **No-trade-band sweep tried and rejected** (0.005/0.01/0.02/0.03 on
   00631L/0050/00679B): widening the band did NOT meaningfully reduce
   transaction cost ($84k -> $66k, a ~20% reduction) while it clearly
   degraded Sharpe/Sortino (+0.27/+0.36 at 0.005 down to +0.22/+0.30 at
   0.03) and worsened the annual-return delta. The turnover at the
   tightest band is not noise-tradeable away -- the signal's genuine
   responsiveness requires it. Kept `no_trade_band = 0.005` (matches
   execution_plan.py's real `min_weight_deviation`).

## Final tested configuration

`weights = {w1_drawdown: 0.0, w2_rate: 0.0, w3_vix: 1.0, w4_tsmc: 0.0}`
(VIX-only, both wrong-signed terms excluded), `no_trade_band = 0.005`,
`defensive_tilt = tanh(relu(risk_score))`, golden1<->bond30_cash30(631L
floor 10%) interpolation.

## Results by window

| Window | Data | Annual Δ | Sharpe Δ | Sortino Δ | MaxDD Δ | Verdict |
|---|---|---|---|---|---|---|
| 2024-01-02..2026-07-23 (tuning window, a2118's own NCF panel active) | real | -4.81pp | +0.27 | +0.36 | -0.03pp | cost/risk-adjusted-benefit trade-off |
| **2017-2019 (genuine OOS backfill panel, untouched during tuning)** | real | **+1.64pp** | **+0.47** | **+0.52** | **+5.46pp (better)** | **all four metrics improve** |
| 2018 trade war (no NCF panel; base a207+VIX-tilt only) | real | +4.71pp | +0.31 | +0.27 | +4.85pp (better) | all four metrics improve |
| **2020 COVID (no NCF panel; base a207+VIX-tilt only)** | real | **-4.92pp** | **-0.46** | **-0.44** | **-9.35pp (worse: -24.64% vs -15.29%)** | **all four metrics worse** |
| 2008 GFC | N/A | -- | -- | -- | -- | **untestable: 00631L/00632R didn't exist until 2015-01-05; ^VIX has no data before 2014 in this DB** |
| 2011 European debt crisis | N/A | -- | -- | -- | -- | **untestable, same reason as 2008** |
| 2015 China A-share crash | N/A | -- | -- | -- | -- | **untestable: 00679B.TWO (bond leg of the defensive basket) didn't list until 2017-01-11** |

So of the "5-crisis" validation-checklist item, only 2/5 windows have
complete real data for this specific candidate (it needs 00631L, 00632R,
00679B, and VIX simultaneously) -- 2018 and 2020. Building proxy data for
the other three (as was done for the unrelated 2020-switch-rule-fix
session's TWII-proxy work) was judged out of scope for today; flagged as
an open follow-up, not silently skipped.

## The critical finding: 2020 COVID is the one real stress test, and this candidate loses on it

2017-2019 OOS and 2018 trade war are both slower-moving, grinding-stress
environments where the continuous tilt had time to track VIX and
gradually de-risk -- and it worked cleanly there, on every metric. 2020
COVID was a fast, violent, V-shaped shock, and the continuous tilt did
**worse than the existing discrete a207 switch on every metric,
including a materially deeper maximum drawdown** -- the one thing a
defensive mechanism exists to prevent. The likely mechanism (not directly
verified, a hypothesis worth checking before any further work): this is
structurally the same failure mode that
`switch_rule_2020_covid_fix_20260706` (see the sibling Fable-audit
handoff, Finding 3's context) was built to fix for the *discrete* regime
-- a signal that stays "stuck defensive" too long after a V-shaped
recovery starts, because VIX itself tends to stay elevated for a while
after the initial spike even as price has already turned. a207's own
fixed regime got an explicit `momentum_fast_exit_min` /
`momentum_fast_exit_ma_gap_min` fast-exit path for exactly this reason.
This continuous VIX-tilt candidate has no equivalent fast-recovery
override yet.

## Verdict and recommended next step

**Do not promote.** Evidence is genuinely mixed, not simply "closed" --
unlike most of today's other tested directions, this one has real
positive results (2/3 real-data windows), which is worth remembering.
But the one true crash test is a clear loss on the metric that matters
most, and this candidate should not be considered further without first
addressing that failure mode. Recommended next step for whoever picks
this up: try adding a fast-recovery override to `defensive_tilt` mirroring
`momentum_fast_exit_min`/`momentum_fast_exit_ma_gap_min`'s logic (force
`defensive_tilt` back toward 0 once price momentum confirms a V-shaped
reversal, regardless of VIX still being elevated) and re-run the 2020
window specifically before any other work on this candidate. Per the
2026-07-23 validation checklist
(`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`), walk-forward
rolling (as opposed to the fixed-window tests run today) has also not yet
been run for this candidate.

## Files (07-23 section)

New:
- `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
- `results/a2119_continuous_defensive_tilt_shadow_latest.json` (first,
  buggy/pre-fix run, kept for reference -- do not treat as valid evidence)
- `results/a2119_continuous_defensive_tilt_shadow_v2.json` (post-bugfix,
  pre-VIX-only-narrowing, 4-signal equal-weight run)

No production files modified.

---

## 2026-07-24 addendum: the fast-recovery-override attempt, and the real root cause

The user asked to pursue the "add a fast-recovery override" recommendation
from the 07-23 section above. This addendum documents that full attempt --
including two implementation bugs found and fixed along the way -- and
the final result: **the fast-recovery-override premise itself was wrong.**
The 2020 failure is not a "stuck defensive too long after recovery"
problem. It is a "never went defensive during the actual crash at all"
problem, caused by a structural design flaw, not a missing parameter.

### Attempt 1: port `momentum_fast_exit_min`/`momentum_fast_exit_ma_gap_min` directly

Added `fast_recovery_momentum_min`/`fast_recovery_ma_gap_min` params to
`build_defensive_tilt()` (single-day override: force `defensive_tilt=0`
on any day where `frame["exit_momentum"] >= fast_recovery_momentum_min`
and `frame["ma_gap"] >= fast_recovery_ma_gap_min`, mirroring
`backtest_group_a_plus_switch_policy.py`'s 2020-COVID-fix logic exactly).
Using the fix's own historical default values (0.10 / -0.08): **the
override never fired**. `frame["ma_gap"]` on 2020-03-26 (the date
`GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md` cites as
`ma_gap=-4.4%`, the key example the original fix was built around) was
actually **-15.35%** in this session's own `run_a2118()` output --
grep-confirmed both call sites use the same `ma_window=100` (via
`a2111._build_switch_rule()`, which `a2118.py` imports), so it is not a
window-length mismatch. The exact cause of this ~11-point discrepancy
versus the original fix's own citation was not resolved (possibly a
different price series/warmup config used in the original 5-crisis
validation session) and was consciously not chased further -- flagged as
an unresolved side-thread, not treated as blocking.

### Attempt 2: drop the ma_gap co-condition, use momentum alone

With `fast_recovery_ma_gap_min=None`, the override fired once (2020-03-26,
`exit_momentum=0.126 >= 0.10`). Result: **backtest metrics were
byte-identical to the no-override case** (`annual_delta=-0.0492` either
way). A direct diagnostic (`build_defensive_tilt` with/without the
override, compared day-by-day) confirmed why: `defensive_tilt` was
*already* 0.0 on 2020-03-26 with no override at all -- there was nothing
to override that specific day. A single-day override cannot matter for a
continuous signal that gets independently recomputed from VIX every
subsequent day regardless of any one-day intervention.

### Attempt 3: add persistence (`fast_recovery_hold_days`)

Added `fast_recovery_hold_days: int = 0` -- once the momentum condition
fires on day D, hold the override active for D through D+hold_days-1
(not just day D). **First implementation had the propagation direction
backwards**: used a reversed-then-rolling-then-un-reversed trick intended
to forward-fill, but direct inspection showed the override applying to
days *before* the trigger (2020-03-16 through 03-26) and switching off
immediately *after* (03-27 onward) -- the opposite of the intent. Fixed
by removing the reversal entirely: a plain backward-looking
`trigger_day.rolling(hold_days, min_periods=1).max()` is already exactly
"today OR any of the past hold_days-1 days had a trigger," which reads
correctly as forward-propagation across consecutive calendar days once
you evaluate it day-by-day. Verified via the same day-by-day diagnostic:
with `hold_days=25`, the override now correctly suppressed a real tilt
spike (defensive_tilt hit 0.93-1.0 during 2020-04-09..04-23, a genuine
VIX-driven defensive stretch about two weeks after the momentum trigger)
down to 0.0 throughout.

Swept `hold_days` in {10, 15, 20, 25, 30, 40, 60} on the 2020 window.
Results did vary with hold_days now (confirming the fix took effect),
but **none improved over the no-override baseline** -- annual_return
delta ranged -4.2pp to -6.2pp (vs -4.9pp with no override at all), sharpe
delta -0.44 to -0.52 (vs -0.46). More tellingly: **`max_drawdown` delta
was frozen at exactly -0.0935 across every single hold_days value
tested**, meaning the override never touched the period actually
responsible for the worst drawdown.

### Root cause: `defensive_tilt` was 0.0 throughout the entire actual crash, not stuck high after it

Traced the worst-drawdown date directly: 2020-03-19, -24.6% peak-to-
trough (vs a207 baseline's -15.3% for the same window -- the metric this
whole investigation was trying to fix). Inspected `defensive_tilt` from
2020-02-18 through 2020-03-27 (the entire crash descent): **it was 0.0
every single day**. The VIX-percentile-based signal never engaged at all
during the fastest, deepest part of the actual sell-off -- the opposite
problem from what the "fast-recovery override" hypothesis assumed (stuck
*high*, not stuck *low*).

Checking why led to the real structural bug: **`build_continuous_targets()`
never reads `frame["execution_regime"]` at all.** It unconditionally
interpolates between the real production `golden1` weights and the real
`bond30_cash30` defensive basket using only `defensive_tilt` --
completely ignoring whatever a207's own price-reactive drawdown/ma_gap
switch has already decided for that same day. Cross-checked against the
07-23 finding that a207's own regime was `group_a_plus_defensive` for
essentially the entire March-May 2020 window (see the 07-23 section
above): **a207 correctly went defensive throughout the crash. A21.19, by
design, discarded that signal entirely and stayed at full golden1
exposure the whole time, because it fully replaces a207's regime
detection with a VIX-only score rather than complementing or gating
it.** VIX itself (a volatility proxy, once-removed from price) simply
didn't spike into a extreme-enough percentile fast enough to compensate
for discarding a207's own direct, price-reactive drawdown signal.

This means the entire "fast-recovery override" line of investigation was
chasing the wrong mechanism. A21.19's 2020 loss is not a lag/persistence
problem fixable by a momentum-based re-entry override. It is a coverage
gap: the design point-blank does not use a207's regime as an input or a
floor at all.

### Verdict: do not pursue further tonight; this needs a redesign, not a patch

**Recommended real fix (not attempted -- scoped as future work)**: make
`defensive_tilt` (or the resulting weight blend) never *less* defensive
than whatever a207's own discrete regime already implies for that day --
e.g. take the more conservative (more defensive) of {a207-regime-implied
weights, VIX-tilt-implied weights} each day, rather than letting the
VIX-tilt fully override a207's own signal. This is a genuine design
change to `build_continuous_targets()`, not a parameter sweep, and should
go through the full 2026-07-23 validation checklist (all four windows:
2017-2019, 2020, 2022, 2025-2026) before any conclusion is drawn, given
how much of tonight's work was invalidated by getting the mechanism
itself wrong twice in a row (the 0.5-centering bug on 07-23, the
regime-blindness gap found here on 07-24).

## Files (07-24 addendum)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `fast_recovery_momentum_min`/`fast_recovery_ma_gap_min`/
`fast_recovery_hold_days` params to `build_defensive_tilt()`, plumbed
through `evaluate()` and the CLI, added `fast_recovery_active` to the
output tilt frame and `fast_recovery_override_days` to the stats block).
No production files modified. No new committed result JSON files from
this addendum's ad hoc diagnostic runs (all done via inline `python3 -c`
snippets, not saved) -- if resuming this work, re-run rather than search
for a saved artifact.

## 2026-07-24 addendum #2: the regime-floor fix, implemented and validated

Implements the "recommended real fix" scoped as future work at the end of
the addendum above: `build_continuous_targets` now takes an
`a207_weights` argument (the same `_targets_from_report(frame, report)`
targets already computed as `baseline_targets` for the a207 comparison
curve) and, via a new `_apply_regime_floor` helper, caps the continuous
blend on each ticker to whichever of {continuous weight, a207's own
regime-implied weight for that day} is more conservative: `min` on
risk-on tickers (`0050.TW`, `00631L.TW`), `max` on defensive tickers
(`00632R.TW`, `00679B.TWO`, `cash`), then renormalizes to sum to 1. This
is ticker-wise rather than a single scalar "implied tilt" for a207's
regime, so it works uniformly across every regime name in
`weights_by_regime` (recovery, hedge, trim, leverage-cap, ...) without a
per-regime lookup table -- it only needs a207's own already-computed
per-day target weights, which the script already builds. On (the new
default) and off (`--no-regime-floor`, reproducing the prior behavior)
are both wired through `evaluate()` and the CLI.

Separately, noticed `DEFAULT_WEIGHTS` in the script was still the
original equal-weight `{0.25, 0.25, 0.25, 0.25}` even though the 07-23
IC check found only `vix_stress` had a correctly-signed, strong signal
and the entire "Results by window" table above was actually generated
with VIX-only weights applied via ad hoc override, never persisted.
Fixed `DEFAULT_WEIGHTS` to VIX-only (`w3_vix: 1.0`, rest 0) so the
script's default reproduces what was actually validated.

### Re-ran all four windows from the table above, floor off vs on (VIX-only weights, no_trade_band=0.005)

| Window | Metric | Floor off (=prior behavior) | Floor on (new default) |
|---|---|---|---|
| 2024-01-02..2026-07-23 (tuning) | Annual Δ / Sharpe Δ / Sortino Δ / MaxDD Δ | -4.81pp / +0.27 / +0.36 / -0.28pp | -5.41pp / +0.44 / +0.60 / **+6.86pp (better)** |
| 2017-2019 (OOS) | same | +1.64pp / +0.47 / +0.52 / +5.46pp | +0.99pp / +0.46 / +0.53 / +6.01pp |
| 2018 trade war | same | +4.71pp / +0.31 / +0.27 / +4.85pp | +5.25pp / +0.35 / +0.31 / +5.41pp |
| **2020 COVID** | same | **-4.92pp / -0.46 / -0.44 / -9.35pp (worse)** | **-3.49pp / -0.064 / -0.033 / +0.00pp (exact parity)** |

(`main_2024_2026`'s off-floor MaxDD Δ printed as -0.0028 this run vs
-0.03pp quoted in the original table -- rounding/display only, not a
discrepancy in the underlying number.)

**The 2020 result is the key validation.** `max_drawdown` delta goes from
-9.35pp (materially deeper than a207, the exact defect that produced the
original "do not promote" verdict) to **exactly 0.00pp** -- the floor
makes the continuous mechanism's worst-case drawdown track a207's own
drawdown precisely during the one real violent crash tested, because on
every day the floor is active the risk-on tickers are capped to no more
than a207 already allows. Sharpe/Sortino deltas for 2020 also improve
substantially (-0.46->-0.06, -0.44->-0.03) though annual return is still
slightly negative (-3.49pp) -- the floor fixes the tail-risk defect it
was designed for, it does not turn 2020 into a net win, and that's the
honest characterization. The three non-2020 windows are flat-to-better
across the board with the floor on -- no regression traded away for the
2020 fix. `regime_floor_active_days` in the 2024-2026 tuning window is
296 (out of ~640 rows), confirming a207 spends meaningful time outside
pure golden1 (recovery/hedge/trim regimes) where the floor engages even
in calm periods, not just during 2020.

### Still not done

Per the validation checklist referenced throughout this document:
walk-forward rolling has still not been run for this candidate (only
fixed-window tests, same gap noted in both the 07-23 write-up and the
first 07-24 addendum). 2008/2011/2015 remain untestable for this specific
candidate due to data availability (00631L/00632R didn't exist until
2015-01-05, 00679B.TWO didn't list until 2017-01-11, ^VIX has no data in
this DB before 2014) -- unchanged from the 07-23 finding. **Still do not
promote** -- this addendum fixes the specific design flaw identified
07-24, it does not complete the validation checklist or make this a
promotion candidate on its own.

### Files (07-24 addendum #2)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `_apply_regime_floor`, `RISK_ON_TICKERS`/`DEFENSIVE_TICKERS`
constants, `a207_weights` param on `build_continuous_targets`,
`apply_regime_floor` param threaded through `evaluate()` and a
`--no-regime-floor` CLI flag, `regime_floor_active_days` in the output
JSON; corrected `DEFAULT_WEIGHTS` to VIX-only). No production files
modified. No new committed result JSON (validation runs above were done
via inline `python3 -c` calling `evaluate()` directly, not saved to
`results/`).

## 2026-07-24 addendum #3: walk-forward rolling (checklist item 2), floor on vs off

Closes the one piece of the validation checklist flagged as still
outstanding at the end of addendum #2: item 2 (walk-forward rolling,
fixed-length lookback, as distinct from item 1's walk-forward expanding,
which the 2017-2019 OOS block above already covers). Ran 8 independent,
non-overlapping-start, 2-year, 1-year-stepped rolling folds covering
2017-06-01..2026-06-01 -- the full span for which this candidate has all
of 00631L/00632R/00679B.TWO/^VIX data simultaneously (00679B.TWO is the
binding constraint, listing 2017-01-11; a 5-month buffer was used for the
first fold's start). VIX-only weights, `no_trade_band=0.005`, same as
addendum #2. Raw per-fold JSON saved to
`results/a2119_walkforward_rolling_20260724.json`.

| Fold | Ann.Δ off→on | Sharpe Δ off→on | Sortino Δ off→on | MaxDD Δ off→on |
|---|---|---|---|---|
| 2017-06..2019-06 | +1.55%→+1.70% | +0.233→+0.268 | +0.240→+0.277 | +4.66pp→+5.18pp |
| 2018-06..2020-06 (incl. 2020 crash) | +5.54%→+4.53% | +0.392→+0.446 | +0.405→+0.443 | -3.88pp→**+0.24pp** |
| 2019-06..2021-06 | -2.20%→-6.16% | -0.067→-0.072 | -0.049→-0.052 | -4.52pp→**+0.25pp** |
| 2020-06..2022-06 | +5.95%→-1.40% | +0.394→+0.096 | +0.458→+0.138 | +3.86pp→+3.06pp |
| 2021-06..2023-06 | +3.99%→+0.92% | +0.316→+0.072 | +0.323→+0.074 | -3.49pp→**+1.50pp** |
| 2022-06..2024-06 | -3.77%→-3.65% | -0.286→-0.083 | -0.335→-0.052 | -5.27pp→**0.00pp** |
| 2023-06..2025-06 | -4.03%→-3.46% | -0.065→+0.082 | -0.018→+0.147 | +0.19pp→+6.90pp |
| 2024-06..2026-06 | -9.43%→-10.52% | -0.089→+0.026 | -0.156→-0.013 | -2.81pp→**0.00pp** |

**Counts across the 8 folds (floor on vs off):** annual return improved
in 3/8, worse in 5/8. Sharpe improved 5/8, worse 3/8. Sortino improved
5/8, worse 3/8. **Max drawdown improved (or unchanged) in 7/8, worse in
only 1/8 -- and critically, the floor's max-drawdown delta is
non-negative (never worse than a207's own drawdown) in all 8/8 folds,
versus only 3/8 without the floor.** The one fold where the floor's MaxDD
delta is technically "worse" (2020-06..2022-06: +3.86pp off vs +3.06pp
on) is still strictly better than baseline either way -- it just gives up
a little of an already-good margin, not a regression into negative
territory.

**This is the confirmation the walk-forward-rolling checklist item exists
to provide**: the core claim from addendum #2 -- "the floor's drawdown
fix isn't an artifact of the single 2020 window" -- holds up. Every one
of 8 independently-sampled 2-year windows across 9 years of history shows
the same structural property (it's a hard per-day cap, so this is
expected mechanically, but it's good to see it confirmed empirically
rather than assumed).

**What rolling validation adds that the 4 fixed windows in addendum #2
didn't show**: a real, non-trivial annual-return cost, and it's
concentrated, not scattered noise. The three folds with the worst
Sharpe/Sortino/return trade-offs (2019-06..2021-06, 2020-06..2022-06,
2021-06..2023-06) all overlap the same 2019-2023 span -- a period where
a207's own regime evidently sat in more conservative states for extended
stretches, so the floor's ticker-wise cap engaged often and pulled
meaningful return out of the continuous mechanism's otherwise-positive
edge during that multi-year window, not just a day or two. This is a
genuine, structurally-explained cost (the floor is doing exactly what it
was designed to do -- match a207's conservatism -- during a period when
a207 itself was being conservative for a while), not overfitting or
sampling noise, since it repeats across three independent, only
partially-overlapping folds.

**Verdict, updated**: still **do not promote**. The regime-floor fix is
now validated as a robust, mechanically-sound fix for the specific defect
it targets (max drawdown never worse than a207's own), across both the 4
original windows and 8 independent rolling folds. But it is not a free
improvement -- during extended periods where a207 itself runs
conservative, the floor gives up real return/Sharpe/Sortino to guarantee
that drawdown floor, and that trade-off is now demonstrated to be a
structural property of the design, not a tuning artifact. Checklist items
1 (walk-forward expanding, via the 2017-2019 OOS block) and 2 (walk-forward
rolling, this addendum) are now both done for this candidate. Items 3
(crisis independence) remains only 2/5-covered by data availability, and
item 4 (cost sensitivity sweep) has not been run for this candidate at
all -- both still open if anyone picks this up further.

### Files (07-24 addendum #3)

New: `results/a2119_walkforward_rolling_20260724.json` (full per-fold
metric deltas, floor on/off, for all 8 rolling folds -- the source for
the table above). No script or production files modified in this
addendum (reused `evaluate()` from addendum #2 unchanged, called via
inline `python3 -c` across the 8 fold date ranges).

## 2026-07-24 addendum #4: crisis-independence check (item 3) and cost-sensitivity sweep (item 4)

Closes the two remaining validation-checklist items for this candidate.

### Crisis-independence check (item 3)

Data availability still limits this candidate to 2/5 crisis episodes
(2018 trade war, 2020 COVID -- 2008/2011/2015 untestable, unchanged from
the 07-23 finding). Within that constraint, the specific check run here:
does the 2017-2019 walk-forward-expanding OOS block's positive verdict
(all four metrics improve, addendum #2's table) depend on the 2018
trade-war episode being included, or does it hold on the calmer years
either side of it too? Split the block into 2017-only, 2018-only, and
2019-only (floor on, VIX-only weights, `no_trade_band=0.005`):

| Sub-window | Ann.Δ | Sharpe Δ | Sortino Δ | MaxDD Δ |
|---|---|---|---|---|
| 2017 only (pre-trade-war) | -1.33% | +0.034 | +0.039 | +1.09pp |
| 2018 only (trade war) | +5.25% | +0.353 | +0.305 | +5.41pp |
| 2019 only (post-trade-war) | +1.14% | +0.665 | +0.790 | +2.04pp |
| Full 2017-2019 | +0.99% | +0.463 | +0.529 | +6.01pp |

**Conclusion doesn't flip**: 2019 alone is unambiguously positive on every
metric, actually stronger on Sharpe/Sortino than the full 3-year block.
2017 alone is close to flat (annual return marginally negative, Sharpe/
Sortino near zero but still non-negative, MaxDD still slightly better).
Neither calm year shows the candidate failing when the 2018 crisis is
excluded. But 2018 alone clearly carries the largest share of the full
block's *magnitude* (annual +5.25% and MaxDD +5.41pp of the block's
+0.99%/+6.01pp, more than the two calm years combined contribute in some
metrics) -- so the checklist's underlying concern (is the edge coming from
one episode?) is partially true for magnitude even though not for
direction. Honest summary: this candidate's OOS edge is not solely a
2018-trade-war artifact, but a meaningful share of how *good* the 2017-2019
number looks is concentrated in that one episode rather than spread evenly.

### Cost-sensitivity sweep (item 4)

Added a `cost_multiplier` parameter to `evaluate()` (scales
commission/slippage/tax identically on both legs; CLI: `--cost-multiplier`,
default 1.0 = current real assumptions) and swept {1.0, 0.5, 0.1, 0.0} on
three windows (floor on):

| Window | Ann.Δ @1.0 | @0.5 | @0.1 | @0.0 |
|---|---|---|---|---|
| 2024-2026 (tuning) | -5.41% | -4.15% | -3.13% | -2.87% |
| 2020 COVID | -3.49% | -2.37% | -1.47% | -1.24% |
| 2020-06..2022-06 (worst rolling fold) | -1.40% | -0.55% | +0.14% | +0.31% |

Sharpe follows the same monotonic pattern -- e.g. 2020 COVID Sharpe delta
goes -0.064 (@1.0) -> -0.003 (@0.5) -> +0.046 (@0.1) -> +0.058 (@0.0), and
the worst rolling fold's Sharpe delta goes +0.096 -> +0.159 -> +0.209 ->
+0.221. **Unlike a2118 itself** (whose own commission-discount sweep in
`project_a2118_remaining_fable_directions_5_8_10_20260723` found <0.4%
final-value impact -- low turnover), **this candidate is materially
cost-sensitive**, exactly the pattern the validation checklist warned
about for "anything resembling the live NCF continuous overlay... which
rebalances far more often." Comparing `baseline_execution` vs
`continuous_execution` at `cost_multiplier=1.0` makes the mechanism
explicit:

| Window | Baseline rebalances / cost | Continuous rebalances / cost |
|---|---|---|
| 2024-2026 | 4 / $6,345 | 208 / $85,410 |
| 2020 COVID | 6 / $7,242 | 45 / $25,898 |
| 2020-06..2022-06 | 18 / $31,230 | 116 / $69,790 |

The continuous mechanism rebalances 6-50x more often than a207's discrete
switch even with the existing 0.5%-band no-trade filter already applied
(the 07-23 write-up's Section on the no-trade band found it cuts
continuous-mechanism turnover roughly 8x from unbanded, but that was
always relative to the *unbanded* continuous case, not to a207's own
turnover -- a207's turnover is far lower than even the banded continuous
mechanism's). A meaningful fraction (roughly 1.5-2.5pp of annual return,
more in the tuning window) of the candidate's underperformance vs a207 in
every window tested is attributable to transaction costs from this
turnover gap, not to the regime-floor's allocation trade-off alone. This
does not change the overall verdict, but it means: (a) the true
allocation-only edge of this mechanism is somewhat better than the
after-cost numbers in addenda #2/#3 suggest, and (b) if this candidate is
ever revisited, a wider no-trade band (loosening past 0.5%) or a lower
tilt-update frequency should be tried before concluding on economics,
since turnover -- not the regime floor -- is doing a lot of the damage.

### Verdict, final for this session

**Still do not promote.** All four validation-checklist items are now
addressed for this candidate for the first time: (1) walk-forward
expanding via 2017-2019 OOS, (2) walk-forward rolling via 8 independent
folds, (3) crisis-independence via the 2017/2018/2019 split above
(direction holds, magnitude is crisis-concentrated), (4) cost sensitivity
via the multiplier sweep above (real, material cost sensitivity unlike
a2118). The regime-floor fix from addendum #2 is confirmed robust and
mechanically sound for its narrow purpose (MaxDD never worse than a207).
The candidate's overall economics remain a genuine trade-off, not a clear
win or a clear loss, and two structural issues now identified (the
2019-2023 conservatism cost from addendum #3, and the turnover/cost drag
from this addendum) would need to be addressed -- not just tuned around --
before this could be reconsidered for promotion.

### Files (07-24 addendum #4)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `cost_multiplier` param to `evaluate()`, applied identically to
both baseline and continuous cost legs; `--cost-multiplier` CLI flag;
`cost_multiplier` in output JSON). No production files modified. No new
committed result JSON (sweep and crisis-split runs done via inline
`python3 -c` calling `evaluate()` directly).

---

## 2026-07-25 addendum #5: wider no-trade band tested and rejected; a real floating-point boundary bug found and fixed (two files)

Picks up addendum #4's one remaining open thread: "a wider no-trade band
... should be tried before concluding on economics, since turnover -- not
the regime floor -- is doing a lot of the damage." Swept
`no_trade_band in {0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10}`, floor on,
VIX-only weights, `cost_multiplier=1.0`, across the three windows already
used in addenda #2-4 (2024-2026 tuning, 2020 COVID, and the worst rolling
fold 2020-06..2022-06 from addendum #3). Raw per-band results:
`results/a2119_no_trade_band_sweep_20260725.json`.

### Bug found first: `_apply_no_trade_band`'s trigger condition had a floating-point boundary defect

The initial sweep run showed the 2020 COVID window's regime-floor
protection (max_drawdown delta, exact parity at 0.00pp for every band from
addendum #2 onward) breaking at `band=0.10`: `max_drawdown` delta went to
**-2.05pp**, the first time any band value had broken the floor's core
guarantee. Traced directly: a207's regime flipped on 2020-02-18 (golden1 ->
defensive), moving the floored `0050.TW` target from 0.5 to exactly 0.4 --
a clean 0.10 drift. `_apply_no_trade_band`'s trigger was
`abs(target_val - last_executed) >= band`; in floating point,
`abs(0.4 - 0.5) == 0.09999999999999998`, which is **not** `>= 0.10`. The
trade silently never executed for the rest of the window tested (verified
day-by-day: `0050.TW` stayed frozen at 0.5 from 2020-02-17 through at least
2020-04-01, versus correctly dropping to 0.4 on 2020-02-18 at every other
band value including the adjacent 0.08). This is a real code defect, not
an economic property of wide bands -- a207's regime-implied weights move in
clean round-number increments (the discrete regime table), so any band
that happens to exactly equal a real drift magnitude can silently freeze
that ticker for the rest of the run. Fixed in both copies of this helper
that exist in the codebase (they are separate, not shared): this script's
`_apply_no_trade_band` and the sibling copy in
`evaluate_a2118_live_overlay_backtest_gap.py` (the script promoted to
"CANONICAL TOOLING" by
[[project_finrlx_citation_rule_adopted_20260724]] / the 2026-07-23
validation checklist's item 5) -- both now use `>= band - 1e-9`. Re-ran the
2020 window post-fix: `max_drawdown` delta at `band=0.10` returns to
**0.00pp** (parity restored, matches every other band). Also re-ran the
citation-rule script's actual cited comparison (2025-01-02..2026-07-23,
`no_trade_band=0.005`, the config actually used for the headline
comparison) with the fix applied vs. a scratch pre-fix copy, byte-identical
both ways (`annual=0.6195975568751402/0.5261766519820348`,
`sharpe=2.152050530300578/2.215695059938392` baseline/overlay) -- **the
citation-rule's already-cited numbers are unaffected**, because 0.005 never
happens to exactly equal a continuous NCF-panel-driven drift in this real
data the way 0.10 exactly equaled a discrete a207 regime-table jump. (The
memory note for that comparison cites 52.69%/2.2459 for the overlay leg,
slightly different from the 52.62%/2.2157 reproduced here -- that drift is
from the DB/panel files having been refreshed since 07-24, unrelated to
this bug or fix.)

### Economic conclusion, once the bug no longer confounds the comparison

With the floor's protection confirmed band-width-robust (0.00pp MaxDD delta
holds at every band from 0.005 through 0.10 in the 2020 window), the actual
question addendum #4 raised -- does a wider band recover meaningful
after-cost economics -- has a clean answer: **no.**

| Window | Metric | band=0.005 | 0.01 | 0.02 | 0.03 | 0.05 | 0.08 | 0.10 |
|---|---|---|---|---|---|---|---|---|
| 2024-2026 tuning | Ann.Δ | -5.41% | -5.78% | -6.07% | -6.85% | -7.01% | -9.38% | -14.25% |
| | rebalances / cost | 208/$85,410 | 181/$83,282 | 147/$77,266 | 127/$70,836 | 86/$57,196 | 73/$42,889 | 48/$31,069 |
| 2020 COVID | Ann.Δ | -3.49% | -3.57% | -3.86% | -3.96% | -3.74% | -3.85% | -10.09% |
| | MaxDD Δ | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp (post-fix) |
| | rebalances / cost | 45/$25,898 | 40/$25,731 | 37/$25,424 | 34/$25,193 | 30/$24,281 | 27/$23,737 | 26/$19,053 |
| Worst rolling fold (2020-06..2022-06) | Ann.Δ | -1.40% | -1.43% | -1.44% | -1.64% | **-1.24%** | -1.90% | -5.09% |
| | rebalances / cost | 116/$69,790 | 105/$69,425 | 95/$66,909 | 90/$65,458 | 72/$60,139 | 60/$52,202 | 51/$37,540 |

Cost drops substantially and monotonically as the band widens (in the
tuning window, 208->48 rebalances, $85k->$31k, a ~64% cost reduction).
**But the after-cost annual-return delta gets worse, not better, as the
band widens** in 2 of 3 windows (tuning window: monotonically worse,
-5.41% -> -14.25%; 2020 COVID: roughly flat-to-worse through band=0.08,
then sharply worse at 0.10 even with the floor intact -- the wide band
still costs real return by lagging *other*, sub-0.10 target moves, just
without breaking the crash-day drawdown guarantee specifically). The one
partial exception is the worst rolling fold, where `band=0.05` is a mild
local improvement over `band=0.005` (-1.24% vs -1.40%) before degrading
again at 0.08/0.10 -- not a clean monotonic trend, and not enough of an
improvement across the other two windows to act on. **The turnover
reduction from a wider band does not translate into better net economics
here**: the execution lag a wider band introduces (holding a stale weight
while the true target keeps moving) costs more in missed repricing than it
saves in avoided commission/slippage, the same qualitative finding as the
07-23 pre-floor, pre-regime-floor no-trade-band sweep in the "Implementation
notes" section above, now confirmed to still hold with the regime floor
active and across three separate windows including a real crash.

### Verdict: this specific avenue is closed; two items from addendum #4 remain genuinely open

**Still do not promote** -- no change to the overall verdict. Addendum #4's
"wider no-trade band" suggestion has now been tested and rejected as a fix
for the turnover/cost drag: it trades transaction-cost savings for a larger
same-or-greater loss in captured return, so it does not change the
candidate's economics for the better. What addendum #4 raised but this
addendum did not test: **a lower tilt-update frequency** (e.g. recomputing/
executing the continuous tilt weekly instead of daily) is mechanically
different from a no-trade band -- it would need its own implementation,
not just a parameter sweep on the existing script -- and remains open for
whoever picks this candidate up next. The 2019-2023 structural conservatism
drag identified in addendum #3 is also still unaddressed. Per this
document's running tally: checklist items 1-4 are done (addenda #2-4);
the regime-floor mechanism itself is now further hardened (the fp bug fix
applies fleet-wide to both no-trade-band implementations in the codebase,
not just this candidate); the candidate's core economic trade-off
(cost/conservatism drag vs. tail-risk protection) is unchanged and remains
a genuine trade-off, not a clear win.

### Files (07-25 addendum #5)

Modified:
- `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
  (`_apply_no_trade_band` trigger condition: `>= band` -> `>= band - 1e-9`,
  with an explanatory docstring)
- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py` (same fix,
  same reason, in its own independent copy of the helper -- this is the
  citation-rule "CANONICAL TOOLING" script, so the fix was applied there
  too even though the real cited numbers are confirmed unaffected)

New: `results/a2119_no_trade_band_sweep_20260725.json` (all 21
window x band combinations, floor on, post-fix -- the source for the table
above). No production files modified.

---

## 2026-07-25 addendum #6: lower tilt-update frequency tested and rejected -- same verdict as the no-trade band

Closes addendum #5's one remaining thread from addendum #4: "a lower
tilt-update frequency should be tried." Added `tilt_update_freq_days` to
`build_defensive_tilt()` -- recompute the raw VIX-driven `defensive_tilt`
signal only every N trading days, holding it flat between updates (e.g.
`freq=5` = weekly), rather than delaying *execution* of an already-computed
target the way the no-trade band does. Deliberately left the regime floor
untouched by this: `build_continuous_targets` still applies
`_apply_regime_floor` every single day against a207's actual daily regime,
independent of how stale the tilt itself is, and `fast_recovery_active`
still checks the raw daily signal (it is a safety override, not the base
signal) -- so this tests a genuinely different mechanism than addendum #5,
not a relabeled version of it. Swept `freq in {1, 2, 3, 5, 10, 20}`,
`no_trade_band=0.005` (current default), floor on, same three windows.
Raw results: `results/a2119_tilt_update_freq_sweep_20260725.json`.

| Window | Metric | freq=1 (daily) | 2 | 3 | 5 | 10 | 20 |
|---|---|---|---|---|---|---|---|
| 2024-2026 tuning | Ann.Δ | -5.41% | -7.94% | -9.09% | -9.68% | -10.30% | -12.03% |
| | rebalances / cost | 208/$85,410 | 122/$61,517 | 88/$52,758 | 54/$36,900 | 32/$24,949 | 19/$19,498 |
| 2020 COVID | Ann.Δ | -3.49% | -7.30% | -6.73% | -7.34% | -6.28% | -6.22% |
| | MaxDD Δ | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp |
| | rebalances / cost | 45/$25,898 | 27/$21,088 | 20/$16,432 | 16/$14,600 | 11/$9,242 | 8/$9,157 |
| Worst rolling fold (2020-06..2022-06) | Ann.Δ | -1.40% | **-0.91%** | -3.76% | -2.88% | -3.81% | -4.67% |
| | MaxDD Δ | +3.06pp | +2.72pp | +1.54pp | +1.90pp | +1.80pp | +1.09pp |
| | rebalances / cost | 116/$69,790 | 76/$57,448 | 60/$53,999 | 46/$41,906 | 32/$36,292 | 27/$30,688 |

Same qualitative result as addendum #5's band sweep, via a mechanically
different lever: turnover/cost drops substantially and monotonically as
update frequency decreases (tuning window 208->19 rebalances,
$85k->$19.5k), but **annual-return delta gets worse, not better, in every
window except one marginal exception** (worst rolling fold at `freq=2`:
-0.91% vs -1.40% at daily, the same kind of single-point non-monotonic dip
seen at `band=0.05` in addendum #5, and just as unreliable -- it does not
hold at `freq=3` immediately adjacent, let alone in the other two windows).
2020 COVID is the sharpest case: even `freq=2` (tilt stale by at most one
day) roughly doubles the annual-return drag (-7.30% vs -3.49%) versus
daily updates, confirming the VIX-tilt component's own responsiveness --
not just the regime floor's -- matters during a fast crash, even though
the floor's MaxDD guarantee itself holds at every frequency tested (0.00pp
throughout the 2020 window, non-negative in every fold of the worst rolling
window too, confirming the floor's daily a207-regime check is genuinely
decoupled from tilt staleness, as designed).

**Conclusion: both of addendum #4's open turnover-reduction ideas are now
closed, with the same verdict.** Neither a wider no-trade band (addendum
#5) nor a lower tilt-update frequency (this addendum) recovers better
after-cost economics -- both trade real transaction-cost savings for a
larger-or-equal loss in captured return, because this candidate's turnover
is substantively tied to genuine signal responsiveness (VIX moves that
matter, not noise), not execution overhead that can be filtered away
cheaply. The 6-50x turnover-vs-a207 finding from addendum #4 is not a
free-lunch inefficiency to tune away; it is priced into the mechanism's
current form. **Still do not promote.** The two structural issues that
remain genuinely open for this candidate are unchanged from addendum #5:
the 2019-2023 conservatism drag (addendum #3) and, now more firmly
established, that the turnover/cost drag itself is not fixable by damping
either execution (band) or signal-update cadence (frequency) without
giving up more than is saved -- a real redesign of the signal itself (e.g.
a genuinely lower-frequency-native construction, not a post-hoc damping of
a daily signal) would be needed if this is ever revisited, not a parameter
sweep.

### Files (07-25 addendum #6)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `tilt_update_freq_days` param to `build_defensive_tilt()`, applied
before the fast-recovery override so the safety check still reads the raw
daily signal; threaded through `evaluate()`, `--tilt-update-freq-days` CLI
flag, and the output JSON). No production files modified.

New: `results/a2119_tilt_update_freq_sweep_20260725.json` (all 18
window x frequency combinations -- the source for the table above).

---

## 2026-07-25 addendum #7: growth-crowding penalty (arXiv:2605.20636v2's third, previously-untested component) -- IC is real but backtest is a clean net negative

Closes the one item left open from the original six-paper review
(`GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`'s
arXiv:2605.20636v2 section): the paper's **growth-crowding penalty**
("penalize when a trend has run far and VIX is complacently low") was
noted as philosophically opposite to a207/a2118's own `ma_gap_bull_
threshold` logic (which is now effectively disabled at 0.40 -- see
`ncf.py`'s module docstring: NCF was empirically found *more* reliable in
extended bull markets, not less, the opposite conclusion from "extended
trend = crowded = risk") but was never actually tested against real data.
This addendum builds and tests it.

### Signal construction

Added `growth_crowding` to `build_defensive_tilt()`: 126-trading-day
trailing relative return of the risk-on leg (`0050.TW`) over the defensive
leg (`00679B.TWO`, the actual bond ETF in this candidate's own defensive
basket), z-scored over the same 756-day rolling window as every other
component. Higher value = growth has outrun defensive further over the
past ~6 months = more "crowded" per the paper's framing. New helper
`_load_local_close_series` (queries the local `ohlcv` table, not the
yfinance-backed `external_market_ohlcv` table `_load_external_series`
reads from, since `00679B.TWO` is Taiwan-listed). Added as `w5_crowding`
(default 0.0, matching the existing convention that unvalidated weights
start at zero). **Bug caught and fixed while wiring this up**: `evaluate()`
had no `weights` parameter at all -- `build_defensive_tilt`'s `weights`
argument defaults to the module-level `DEFAULT_WEIGHTS` object bound at
*function-definition* time (a standard Python late-binding-default
gotcha), so an initial sweep that monkeypatched the module attribute
between calls silently produced byte-identical results for every blend
tested (caught immediately -- all 15 rows in the first sweep run were
identical to 6 decimal places, an unmissable tell). Fixed by adding a real
`weights: dict[str, float] | None = None` parameter to `evaluate()`,
threaded through to `build_defensive_tilt` and into the output JSON's
`weights_used` field (which had the same bug, silently always reporting
`DEFAULT_WEIGHTS` regardless of what was actually used).

### IC check (same methodology as the 07-23 four-component check)

Spearman IC of `growth_crowding` against 0050's forward 5d/20d return and
forward-20d worst intraday-to-close drawdown, 2024-01-02..2026-07-23:

| Metric | IC | p-value | Verdict |
|---|---|---|---|
| fwd5d | -0.096 | 0.019 | correct sign, significant |
| fwd20d | -0.032 | 0.448 | correct sign, not significant |
| fwd20d maxDD | -0.077 | 0.063 | correct sign, borderline |

Unlike `rate_stress`/`tsmc_crowding` (both wrong-signed in the 07-23
check), `growth_crowding` is **correctly signed on all three metrics** --
weaker than `vix_stress` (-0.106/-0.189/-0.274) but a real, if modest,
standalone signal, not noise. This is the first genuinely positive result
for any of this candidate's non-VIX components.

### Backtest: blended into the tilt, it makes things worse in every window that matters

Swept `w5_crowding in {0.0, 0.5, 1.0}` combined with `w3_vix in {1.0, 0.5,
0.0}` (five blends: VIX-only baseline, VIX+half-crowding, VIX+full-
crowding, half-VIX+crowding, crowding-only), floor on, `no_trade_band=
0.005`, across the same three windows. Raw results:
`results/a2119_growth_crowding_penalty_sweep_20260725.json`.

| Window | Metric | VIX-only | +0.5 crowd | +1.0 crowd | 0.5vix+1.0crowd | crowd-only |
|---|---|---|---|---|---|---|
| 2024-2026 tuning | Ann.Δ | -5.41% | -8.63% | -11.65% | -11.90% | -13.70% |
| | Sharpe Δ | +0.440 | **+0.489** | +0.446 | +0.433 | +0.249 |
| 2020 COVID | Ann.Δ | -3.49% | -5.24% | -6.96% | -10.54% | -12.44% |
| | Sharpe Δ | -0.064 | -0.124 | -0.191 | -0.359 | -0.472 |
| Worst rolling fold | Ann.Δ | -1.40% | -4.50% | -5.44% | -6.28% | -6.23% |
| | Sharpe Δ | +0.096 | -0.082 | -0.116 | -0.154 | -0.186 |

Annual-return delta gets monotonically worse as crowding weight increases
in **all three windows, with no exception**. Sharpe delta has exactly one
local positive blip -- the tuning window at `w5=0.5` (+0.489 vs +0.440
VIX-only) -- but that single improvement costs 3.2pp of extra annual-return
drag in the same window, and does not appear in either of the other two
windows: 2020 COVID and the worst rolling fold are both monotonically
worse on Sharpe too, starting from the very first crowding weight tested.
MaxDD delta stays non-negative in 2020 COVID (0.00pp at every blend, the
regime floor working as designed regardless of tilt composition) and
mostly non-negative in the worst rolling fold, so the floor's core
guarantee is unaffected by this signal -- but that guarantee was never in
question; the question was whether the crowding *tilt itself* helps, and
on both risk-adjusted return and raw return it does not.

**Why the IC-positive signal fails once backtested**: `growth_crowding` is
backward-looking over 126 trading days (~6 months), the same lagging-
signal problem `vix_stress` alone doesn't have as acutely (VIX reprices
same-day; a 126-day trailing return ratio does not). The 2020 COVID result
is the clearest illustration: the trend that "ran far" heading into
February 2020 wasn't extreme by this measure (2019 was a comparatively
calm grind-up, not a blow-off top), so the signal didn't add early warning
-- but it very plausibly stayed elevated well into the V-shaped recovery
(growth still "outran" defensive on a 126-day lookback for months after
the trough), adding drag during the recovery instead of protection during
the crash. This is a variant of the same "stuck defensive after the fact"
failure pattern the fast-recovery-override investigation (07-24 addendum
#1) diagnosed for the base VIX tilt, but here it comes from the signal's
inherent lookback length rather than the crash-and-recover shape VIX
itself follows.

### Verdict: closes the last open item from the six-paper review

**Growth-crowding penalty does not transfer usefully to this candidate or
this market.** The standalone IC is real (unlike `rate_stress`/
`tsmc_crowding`), which is itself worth recording -- this is not the same
kind of finding as those two wrong-signed components -- but a real,
correctly-signed IC is not sufficient for a component to help a blended
timing signal: its lag structure interacts badly with the specific shape
of the 2020 crash-and-V-recovery, and every window tested shows the same
net-negative pattern once actually backtested. `w5_crowding` stays at its
0.0 default; `DEFAULT_WEIGHTS` is not changed by this addendum. This also
closes the item flagged as "worth a future debate" in the original
2026-07-23 review of arXiv:2605.20636v2 -- the debate is now resolved by
evidence rather than left open: a207/a2118's existing "don't fight the
trend" posture (now effectively a no-op via the disabled `ma_gap_bull_
threshold`, per Finding 3's dormancy result) is not contradicted or
improved on by importing the paper's opposite "penalize the trend"
framing. **Still do not promote A21.19; no change to its current VIX-only
configuration.**

### Files (07-25 addendum #7)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `growth_crowding` component + `_load_local_close_series` helper to
`build_defensive_tilt()`; `w5_crowding` key added to `DEFAULT_WEIGHTS`
(0.0); added a real `weights` parameter to `evaluate()`, fixing the
late-binding-default bug that made the module-level `DEFAULT_WEIGHTS`
un-overridable and the output JSON's `weights_used` field inert).

New: `results/a2119_growth_crowding_penalty_sweep_20260725.json` (all 15
window x blend combinations -- the source for the table above). No
production files modified.

---

## 2026-07-25 addendum #8: credit_stress (HYG-SHY) -- the first genuinely promising new component this session, still not yet fully validated

Follow-up to `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`'s
review of arXiv:2607.06117v1 ("Relief-Gated Relative Rotation for QQQ-DIA
Allocation"), which flagged that its `credit_relief`/`credit_stress`
construction (HYG minus SHY relative return) is real, ordinary yfinance
data -- unlike the BAA/10Y or HY OAS series this project confirmed it has
no source for back on 2026-07-23. Data fetched today:
`scripts/fetch/fetch_cross_market_ohlcv.py --tickers HYG,SHY --start
2015-01-01 --end 2026-07-25` (2906 rows each, both now in
`external_market_ohlcv` with `provider='yfinance'`).

### Construction and IC check (per the new checklist item 6, run before any backtest)

Added `credit_stress` to `build_defensive_tilt()`: 21-day HYG-SHY relative
return (matching RGRR's own construction), negated (so positive =
deteriorating credit = more defensive, matching this script's sign
convention for every other component), z-scored. Added as `w6_credit` in
`DEFAULT_WEIGHTS` (default 0.0). IC check (same methodology as the
`growth_crowding` and original four-component checks, 2024-01-02..
2026-07-23):

| Metric | IC | p-value | Verdict |
|---|---|---|---|
| fwd5d | -0.044 | 0.282 | correct sign, not significant |
| fwd20d | -0.105 | 0.012 | correct sign, significant |
| fwd20d maxDD | -0.180 | 0.000 | correct sign, highly significant |

This is the **strongest standalone IC of any non-VIX component tested in
this candidate's history** -- stronger than `growth_crowding`
(-0.096/-0.032/-0.077) and `drawdown_severity` (-0.004/-0.042/-0.152),
though still weaker than `vix_stress` itself (-0.106/-0.189/-0.274).

### Backtest: genuinely mixed, but a real positive pattern in 3 of 4 windows when added as a modest complement to VIX (not a replacement)

Swept `w6_credit in {0.0, 0.5, 1.0}` combined with `w3_vix in {1.0, 0.5,
0.0}` (five blends, same structure as addendum #7's crowding sweep),
floor on, `no_trade_band=0.005`, across the three standing windows plus a
fourth added specifically for this check (2018 trade war, full calendar
year -- the fourth window from addendum #2's original "Results by window"
table, not yet used in addenda #5-7). Raw results:
`results/a2119_credit_stress_hyg_shy_sweep_20260725.json`.

| Window | Metric | VIX-only | +0.5 credit | +1.0 credit | 0.5vix+1.0credit | credit-only |
|---|---|---|---|---|---|---|
| 2024-2026 tuning | Ann.Δ | -5.41% | -5.58% | -6.27% | -5.79% | -7.35% |
| | Sharpe Δ | +0.440 | +0.426 | +0.390 | +0.353 | +0.258 |
| 2020 COVID | Ann.Δ | -3.49% | **-3.25%** | **-2.91%** | **-2.25%** | -2.55% |
| | Sharpe Δ | -0.064 | -0.051 | -0.036 | **-0.023** | -0.060 |
| Worst rolling fold | Ann.Δ | -1.40% | **-1.30%** | **-1.20%** | **-0.66%** | **-0.51%** |
| | Sharpe Δ | +0.096 | +0.110 | +0.130 | +0.176 | **+0.201** |
| 2018 trade war | Ann.Δ | +5.25% | **+5.32%** | **+5.40%** | +4.43% | +0.14% |
| | Sharpe Δ | +0.353 | +0.358 | +0.365 | +0.286 | -0.040 |

**Two distinct patterns, not one.** In 2020 COVID and the worst rolling
fold, every metric improves **monotonically** as `w6_credit` increases,
with `credit_only` at or near the best point in both windows -- credit
stress alone tracks these two stress episodes better than VIX alone does.
In the 2018 trade war window, the pattern is different: `vix1.0_credit1.0`
(credit added **on top of** full VIX weight) is the best point, but
reducing VIX weight in favor of credit (`vix0.5_credit1.0`) or using
credit alone clearly hurts (`credit_only` collapses to near-zero annual
return delta and goes Sharpe-negative). The 2024-2026 tuning window shows
a real, consistent cost at every blend -- the same pattern `vix_stress`
itself already has there (this is the well-established "2025-2026 is a
single, low-volatility bull regime" finding recurring again, not new
information).

**The configuration that holds up best across all four windows is
`w3_vix=1.0` plus a modest additive `w6_credit` (0.5-1.0), not any blend
that reduces VIX's own weight.** At `vix1.0_credit1.0`: 3 of 4 windows
improve on both annual-return and Sharpe delta (2020 COVID, worst rolling
fold, 2018 trade war), only the tuning window costs more than the
VIX-only baseline already does. This is the **first component tested in
this candidate's entire history (base four terms, `growth_crowding`, now
`credit_stress`) to show a genuinely positive, multi-window pattern when
added to the existing base rather than a uniformly negative or purely
single-window-noisy one.**

### What this does and does not establish

This clears the new checklist item 6 bar (real standalone IC, plus
backtest improvement in >=2 of the multi-window checks) at the
`vix1.0_credit{0.5,1.0}` configuration specifically -- unlike
`growth_crowding`, which failed item 6 outright. **It does not clear the
full six-item validation checklist yet**: no walk-forward-rolling folds
run specifically with credit included (only the four fixed windows
above), no dedicated crisis-independence split isolating whether the 2020
COVID improvement depends on the specific March 2020 credit freeze versus
holding across calmer sub-periods, and no cost-sensitivity sweep for this
specific addition. `w6_credit` stays at its 0.0 default -- **this is not
promoted to A21.19's default configuration in this addendum**, only
flagged as the most promising lead this session has produced, worth the
remaining checklist items if pursued further.

### Files (07-25 addendum #8)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `credit_stress` component, sourced from `HYG`/`SHY` via the
existing `_load_external_series` helper; `w6_credit` key added to
`DEFAULT_WEIGHTS` (0.0)).

New data (via `scripts/fetch/fetch_cross_market_ohlcv.py`, not a script
change): `HYG`/`SHY` daily closes in `external_market_ohlcv`,
2015-01-02..2026-07-24.

New: `results/a2119_credit_stress_hyg_shy_sweep_20260725.json` (20 window
x blend combinations -- the source for the table above). No production
files modified.

---

## 2026-07-25 addendum #9: completing the full validation checklist for credit_stress -- three of four items pass cleanly, one surfaces a real methodological limitation

Closes the remaining checklist items flagged as outstanding at the end of
addendum #8. Compares `vix_only` (`DEFAULT_WEIGHTS` as shipped) against
`vix1.0_credit1.0` (full VIX weight plus credit added on top, the best-
performing blend from addendum #8) throughout.

### Item 1: walk-forward expanding (2017-2019 OOS)

| Config | Ann.Δ | Sharpe Δ | MaxDD Δ |
|---|---|---|---|
| vix_only | +0.99% | +0.463 | +6.01pp |
| vix1.0_credit1.0 | **+1.38%** | **+0.519** | **+6.98pp** |

All three metrics improve. Matches addendum #2's original number for
`vix_only` exactly (+0.99%/+0.463/+6.01pp), confirming this is the same
window used throughout this candidate's history. **Pass.**

### Item 2: walk-forward rolling (8 independent folds, same as addendum #3)

| Fold | Ann.Δ vix→credit | Sharpe Δ vix→credit | MaxDD Δ vix→credit |
|---|---|---|---|
| 2017-06..2019-06 | +1.70%→**+1.87%** | +0.268→**+0.293** | +5.18pp→**+6.10pp** |
| 2018-06..2020-06 | +4.53%→**+5.50%** | +0.446→**+0.535** | +0.24pp→0.03pp |
| 2019-06..2021-06 | -6.16%→**-5.36%** | -0.072→**-0.055** | +0.25pp→0.10pp |
| 2020-06..2022-06 | -1.40%→**-1.20%** | +0.096→**+0.130** | +3.06pp→**+4.57pp** |
| 2021-06..2023-06 | +0.92%→**+1.50%** | +0.072→**+0.125** | +1.50pp→+1.55pp |
| 2022-06..2024-06 | -3.65%→-4.64% | -0.083→-0.125 | 0.00pp→0.00pp |
| 2023-06..2025-06 | -3.46%→-5.15% | +0.082→-0.036 | +6.90pp→+5.11pp |
| 2024-06..2026-06 | -10.52%→**-10.05%** | +0.026→**+0.055** | 0.00pp→0.00pp |

**6 of 8 folds improve annual return and Sharpe simultaneously**
(2017-06..2019-06, 2018-06..2020-06, 2019-06..2021-06, 2020-06..2022-06,
2021-06..2023-06, 2024-06..2026-06); only 2 folds worsen on both
(2022-06..2024-06, 2023-06..2025-06) -- both fall inside the same
2022-2025 span already identified in addendum #3 as the period where
a207 itself ran conservative for extended stretches and the regime floor
gives up the most return regardless of tilt composition; this is a
known, explained cost region, not new information. Raw results:
`results/a2119_credit_stress_walkforward_expanding_rolling_20260725.json`.
**Pass** (75% fold agreement, consistent between the two metrics per
fold -- a real pattern, not coin-flip noise).

### Item 3: crisis-independence -- passes on the valid check, and surfaces a genuine measurement limitation on the other

**2017/2018/2019 split of the OOS window** (valid -- full calendar years,
well beyond any warmup requirement):

| Sub-window | Ann.Δ vix→credit | Sharpe Δ vix→credit |
|---|---|---|
| 2017 only | -1.33%→**-1.71% (worse)** | +0.034→**+0.017 (worse)** |
| 2018 only | +5.25%→+5.40% | +0.353→+0.365 |
| 2019 only | +1.14%→**+3.19%** | +0.665→**+0.900** |
| Full 2017-2019 | +0.99%→+1.38% | +0.463→+0.519 |

2 of 3 years positive (2018, 2019), 1 negative (2017) -- meets
arXiv:2607.06117v1's own "positive in at least 2 of 3 screen periods"
admission bar (the same bar just written into checklist item 6). Most of
the full-window magnitude comes from 2019, similar to how addendum #4
found the regime-floor's own 2018/2019 split concentrated magnitude in
2018 -- a recurring, not new, pattern in this candidate's evidence.
**Pass.**

**2020 sub-window decomposition attempt (pre-crash calm, crash-only,
post-crash recovery) -- methodologically invalid, not a real finding
either way.** The pre-crash (`2020-01-02..2020-02-19`, 28 rows) and
crash-only (`2020-02-19..2020-03-31`, 28 rows) sub-windows both returned
**byte-identical baseline and continuous metrics** -- not just similar,
identical to every decimal in `final_value`, `sharpe_ratio`, every field.
Traced directly: `_zscore()` (the helper every raw state variable in
`build_defensive_tilt` runs through) uses `min_periods=60`; any
`evaluate()` call whose *own* requested window is under ~60 trading days
has essentially no in-window history to standardize against, so every
z-scored component (`vix_stress`, `credit_stress`, all of them) is forced
to its `.fillna(0.0)` fallback for virtually the entire window --
`defensive_tilt` degenerates to `tanh(relu(0))=0` regardless of which
weights are configured, so `vix_only` and `credit`-added configs cannot
differ at all in a sub-60-trading-day window, independent of any real
economic mechanism. This is a genuine limitation of this script's
cold-start design (each `evaluate()` call restandardizes from its own
requested start, not from a longer external history), not evidence about
whether credit specifically helps or fails to help during the acute March
2020 crash. The longer post-crash-recovery sub-window (`2020-04-01..
2020-12-31`, 189 rows, well past the warmup floor) *does* produce a real,
non-degenerate result -- and it is negative (`vix_only` ann_d=-6.20% ->
`credit` ann_d=**-9.15%, worse**; sharpe_d +0.020 -> **-0.072, worse**).
This does **not** mechanically contradict addendum #8's full-2020-window
positive result (`vix_only` -3.49% -> `credit` -2.91%, better): each
`evaluate()` call is an independent cold start over its own requested
window, not a slice of one continuous trajectory, so sub-window results
do not additively decompose the full-window result the way they would in
a true continuous simulation -- a sub-window test cannot be used to
explain *away* a full-window finding, only to add its own, separately-
scoped evidence. Taken on its own terms, the recovery-sub-window result is
a real negative data point about credit's behavior specifically in that
sub-period, and is consistent with the same category of lag-driven
"cost during the recovery, not the crash" pattern found for
`growth_crowding` in addendum #7 -- worth remembering if this candidate
is revisited, even though it doesn't overturn the full-window comparison.
**Partial**: the calendar-year split passes; the sub-year crash-isolation
attempt is inconclusive by construction and should not be re-attempted
with this script's current sub-60-day cold-start behavior without first
extending `evaluate()` to accept pre-window warmup history. Raw results
(including the degenerate rows, kept for the record):
`results/a2119_credit_stress_crisis_independence_20260725.json`.

### Item 4: cost-sensitivity sweep

`cost_multiplier in {1.0, 0.5, 0.1, 0.0}`, `vix_only` vs
`vix1.0_credit1.0`, on 2020 COVID and the worst rolling fold:

| Window | Metric | @1.0 | @0.5 | @0.1 | @0.0 |
|---|---|---|---|---|---|
| 2020 COVID | vix_only Ann.Δ | -3.49% | -2.37% | -1.46% | -1.24% |
| | credit Ann.Δ | **-2.91%** | **-1.68%** | **-0.68%** | **-0.43%** |
| | credit advantage | +0.58pp | +0.69pp | +0.78pp | +0.81pp |
| Worst rolling fold | vix_only Ann.Δ | -1.40% | -0.55% | +0.14% | +0.31% |
| | credit Ann.Δ | **-1.20%** | **-0.34%** | **+0.37%** | **+0.54%** |
| | credit advantage | +0.20pp | +0.21pp | +0.23pp | +0.23pp |

**Credit's advantage over `vix_only` holds at every cost level tested in
both windows, including `cost_multiplier=0.0`** -- this rules out "it just
turns over less/more and the cost assumption happens to favor it" as an
explanation. In the 2020 COVID window credit actually uses *fewer*
rebalances than `vix_only` (42 vs 45) while still winning at every cost
level, including zero cost -- the advantage is a real allocation-timing
effect, not a turnover-cost artifact in either direction. **Pass.** Raw
results: `results/a2119_credit_stress_cost_sensitivity_20260725.json`.

### Overall verdict: 3 of 4 items pass cleanly, item 3 is partial (with the invalid half explained, not ignored) -- the strongest evidence any component has produced for this candidate, still not promoted

Summary: item 1 pass, item 2 pass (6/8 folds), item 3 partial (calendar-
year split passes; sub-year crash-isolation attempt invalid by
construction, not failed), item 4 pass. No other component tested in
A21.19's history (base four terms, `growth_crowding`) has cleared this
many checklist items this cleanly. **Still not promoted to
`DEFAULT_WEIGHTS`** -- this project's standing discipline
([[feedback_strategy_promotion_caution]] in Claude's persistent memory:
high Sharpe alone does not justify promotion) treats even strong evidence
like this as a basis for a explicit human decision, not an automatic
default-config change, especially given: (a) the real, unresolved
question of whether `credit_stress`'s edge specifically during acute
crashes (as opposed to the recovery afterward, where it costs) can ever
be cleanly isolated with this script's current cold-start design; (b) A21.19
as a whole is still shadow-only and not itself promoted, so no individual
component should jump ahead of the candidate's own status. **Recommendation
for the user**: this is now a specific, well-evidenced decision point --
either set `w6_credit=1.0` as A21.19's new shadow-default configuration
(still shadow, not live, but the config future addenda would build from),
or leave it flagged at 0.0 pending the sub-60-day cold-start limitation
being addressed first. Left to the user's decision, not acted on
unilaterally.

### Files (07-25 addendum #9)

No script changes -- this addendum only ran `evaluate()` with existing
parameters across new windows. New result files: `results/
a2119_credit_stress_walkforward_expanding_rolling_20260725.json`,
`results/a2119_credit_stress_crisis_independence_20260725.json`,
`results/a2119_credit_stress_cost_sensitivity_20260725.json`. No
production files modified.

---

## 2026-07-25 addendum #10: fixing the sub-60-day cold-start limitation surfaces a much bigger, humbling finding -- addendum #8/#9's "strongest evidence" was itself confounded, and the effect isn't specific to credit_stress

User asked to pursue both remaining threads from addendum #9's summary:
(a) the `_zscore` sub-60-day cold-start limitation, and (b) more
backtests generally. Fixing (a) properly required, and produced, far more
than a fix to the 2020 sub-window edge case -- it revised this session's
overall confidence in `credit_stress`, and surfaced a methodological issue
that predates today and applies to every prior addendum's numbers, not
just credit_stress's.

### The fix: real pre-window warmup history for external-series components

Added `_extend_index_with_warmup()` and a `warmup_days` parameter to
`build_defensive_tilt()`/`evaluate()` (**default 0**, deliberately --
see below for why the default could not simply become 756). When
`warmup_days > 0`, `vix_stress`/`credit_stress`/`rate_stress` (the
components sourced purely from external series, not from `frame` itself)
are z-scored against real trading history fetched from before the
requested window's own start (sourced from `^VIX`'s date range, then
sliced back to the requested window before use) instead of restandardizing
from a blank slate at the window's own first row.
`drawdown_severity`/`growth_crowding`/`tsmc_crowding` remain frame-bound
(they depend on `frame["drawdown"]`/`frame["0050_close"]`, which only
`run_a2118()` itself could extend -- a bigger, deliberately out-of-scope
change today) and do not benefit from this fix; today's tests all use
`w1_drawdown=w5_crowding=w4_tsmc=0`, so this doesn't affect the specific
`credit_stress` question.

### First check: the mechanistic question addendum #9 actually asked (does credit help specifically during the acute crash) now has a clean, definitive answer -- and it isn't about credit at all

Re-ran the 2020 sub-windows with `warmup_days=756`. The pre-crash and
post-recovery sub-windows are no longer degenerate (non-zero, distinct
tilt statistics), but the crash-only sub-window (`2020-02-19..2020-03-31`)
is **still exactly byte-identical between `vix_only` and any credit blend
-- even though `defensive_tilt` itself is now correctly hot (mean 0.87-0.95,
clearly maximally defensive, not the old degenerate 0.0)**. Confirmed why:
`regime_floor_active_days` for this specific sub-window is **28/28 -- the
floor is 100% binding every single day of the acute crash**, because
a207's own price-reactive regime was already at its own maximum
defensiveness throughout. This is a clean, mechanistic, non-artifact
finding, not inconclusive: **no tilt signal (VIX, credit, or any future
addition) can possibly help or hurt during a crash severe enough to make
a207's own regime floor fully bind for the whole episode** -- the floor
already captures 100% of the available protection by that point, with zero
marginal room for the tilt composition to matter. Raw results:
`results/a2119_credit_stress_warmup_extension_2020_20260725.json`.

### Second, much bigger check: does the "3 of 4 windows improve" headline finding from addendum #8 survive real warmup? No -- it drops to a much weaker, genuinely mixed 3-of-5, with both crisis windows flipping negative

Before trusting `credit_stress`'s overall verdict, re-ran all five main
comparison windows (2024-2026 tuning, 2020 full year, worst rolling fold,
2018 trade war, 2017-2019 OOS) at both `warmup_days=0` (addendum #8/#9's
implicit setting throughout) and `warmup_days=756`, `vix_only` vs
`vix1.0_credit1.0`:

| Window | `warmup=0`: credit vs vix_only | `warmup=756`: credit vs vix_only | Direction |
|---|---|---|---|
| 2024-2026 tuning | worse (ann -5.41%→-6.27%, sharpe +0.440→+0.390) | **better** (ann -8.73%→-8.12%, sharpe +0.390→+0.404) | **flips** |
| 2020 full year | better (ann -3.49%→-2.91%, sharpe -0.064→-0.036) | **worse** (ann -5.63%→-6.09%, sharpe -0.139→-0.201) | **flips** |
| Worst rolling fold | better (ann -1.40%→-1.20%, sharpe +0.096→+0.130) | better, smaller margin (ann -2.26%→-2.14%, sharpe +0.028→+0.030) | holds, weaker |
| 2018 trade war | better (ann +5.25%→+5.40%, sharpe +0.353→+0.365) | **worse** (ann +3.59%→+3.31%, sharpe +0.168→+0.137) | **flips** |
| 2017-2019 OOS | better (ann +0.99%→+1.38%, sharpe +0.463→+0.519) | better, stronger (ann +1.54%→+2.57%, sharpe +0.559→+0.672) | holds, stronger |

**3 of 5 windows still favor credit (tuning, worst rolling fold,
2017-2019 OOS), but 2 of 5 flip from favoring credit to hurting it --
and both flips are the two genuine crisis windows (2018 trade war, 2020
COVID), the ones that matter most for evaluating a defensive signal.**
This is a materially weaker and more ambiguous picture than addendum #8's
"3 of 4 windows improve... the first component to show a genuinely
positive, multi-window pattern" framing, and than addendum #9's "strongest
evidence any component has produced for this candidate" conclusion. Both
of those conclusions were accurate *given the implicit `warmup_days=0`
methodology used throughout*, but that methodology itself has a real,
newly-understood bias. Raw results:
`results/a2119_credit_stress_warmup_main_windows_20260725.json`.

### Why the default could not simply become `warmup_days=756`, and why this affects more than credit_stress

The obvious fix -- just default to `warmup_days=756` going forward -- was
tried and reverted immediately: re-running the plain `vix_only` 2024-2026
baseline (no credit at all) with `warmup_days=756` moved its own numbers
from the established `ann_d=-5.41%, sharpe_d=+0.440` (addendum #2 onward)
to `ann_d=-8.73%, sharpe_d=+0.390` -- a large, real difference driven
entirely by `vix_stress`'s own cold-start maturity, with `credit_stress`
not even involved. **This means every fixed-window backtest run for this
candidate since addendum #2 (07-24) -- every VIX-only headline number
quoted throughout this entire document, not just today's credit_stress
work -- has implicitly measured "defensive_tilt turns on cold at the
window's own first row," not "defensive_tilt as it would behave inside a
continuously-running strategy that always has real trailing history."**
Because `baseline_targets` (a207 alone) does not depend on
`build_defensive_tilt()` at all, this bias applies asymmetrically to the
continuous side of every metric delta ever reported for this candidate --
it does not cancel out. `warmup_days` therefore defaults to **0**, not
756: changing the default now would silently invalidate every existing
number's comparability across this document's ten addenda, which is a
worse outcome than documenting the limitation and leaving it opt-in.
Future serious evaluation of this candidate (not just `credit_stress`)
should treat `warmup_days=756` as the more realistic setting and
`warmup_days=0` as the (now known-biased, but internally self-consistent
across this document's own history) convention used so far.

### Verdict, revised down from addendum #9

**`credit_stress` is not a clean win once evaluated with realistic
warmup -- it is genuinely mixed, and its two failures are exactly the
crisis windows a defensive candidate is supposed to help in.** This
downgrades it from addendum #9's "strongest evidence any component has
produced... a specific, well-evidenced decision point" to: a real,
non-trivial signal (the earlier IC check and the cost-sensitivity
robustness both still stand on their own terms, independent of this
warmup question), but **not** a component that should be promoted to
`w6_credit=1.0` on today's evidence. `w6_credit` stays at 0.0.
**Recommended next step for whoever continues this candidate**: any
further evaluation of `credit_stress` (or any other component) should be
run at `warmup_days=756`, not the historical default of 0, given what
this addendum found. A larger, separate task -- extending `run_a2118()`
itself to accept pre-window warmup so `drawdown_severity`/`growth_crowding`
benefit too, and potentially re-examining whether the base `vix_stress`
default itself would look different under `warmup_days=756` across this
candidate's other established windows -- is flagged but not started today.

### Files (07-25 addendum #10)

Modified: `scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py`
(added `_extend_index_with_warmup()` helper; `warmup_days` parameter
threaded through `build_defensive_tilt()`, `evaluate()`, output JSON, and
a new `--warmup-days` CLI flag, default 0 throughout to preserve every
prior addendum's numbers exactly -- verified via re-running the 2024-2026
`vix_only` default config, byte-identical to addendum #2's original
numbers).

New: `results/a2119_credit_stress_warmup_extension_2020_20260725.json`
(2020 sub-windows, warmup 0 vs 756), `results/
a2119_credit_stress_warmup_main_windows_20260725.json` (all 5 main
windows, warmup 0 vs 756, credit vs vix_only -- the source for the table
above). No production files modified.

---

## 2026-07-25 addendum #11: re-baselining `vix_only` and the regime floor's core claim under warmup=756 -- good news, the foundational result survives

Follow-up to addendum #10's biggest open item: the cold-start bias found
there applies to every fixed-window number in this document, not just
`credit_stress`, including the single most load-bearing claim in this
candidate's history -- addendum #2/#3's finding that the regime floor
makes `max_drawdown` delta non-negative (never worse than a207) in 8 of 8
rolling folds, versus only 3 of 8 without it. Re-ran `vix_only`, both
`apply_regime_floor` settings, at both `warmup_days=0` and `756`, across
all 8 rolling folds plus the 2017-2019 OOS, 2018 trade war, 2020 COVID,
and 2024-2026 tuning windows (48 `evaluate()` calls total). Raw results:
`results/a2119_vix_only_baseline_warmup_recheck_20260725.json`.

### The core claim survives cleanly

| Fold | MaxDD Δ, floor on, warmup=0 | MaxDD Δ, floor on, warmup=756 | MaxDD Δ, floor off, warmup=0 | MaxDD Δ, floor off, warmup=756 |
|---|---|---|---|---|
| 2017-06..2019-06 | +5.18pp | +6.17pp | +4.66pp | +5.60pp |
| 2018-06..2020-06 | +0.24pp | +0.36pp | -3.88pp | -3.92pp |
| 2019-06..2021-06 | +0.25pp | +0.36pp | -4.52pp | -3.95pp |
| 2020-06..2022-06 | +3.06pp | +2.20pp | +3.86pp | +3.71pp |
| 2021-06..2023-06 | +1.50pp | +1.49pp | -3.49pp | -3.23pp |
| 2022-06..2024-06 | 0.00pp | 0.00pp | -5.27pp | -4.22pp |
| 2023-06..2025-06 | +6.90pp | +7.35pp | +0.19pp | +0.78pp |
| 2024-06..2026-06 | 0.00pp | **+4.91pp** | -2.81pp | -1.57pp |

**8 of 8 folds are still non-negative with the floor on, at both warmup
settings -- the exact same fold-by-fold pattern as addendum #3's original
finding, several folds even showing a larger positive margin under
warmup=756 (2024-06..2026-06 improves from an exact 0.00pp to +4.91pp).**
Floor-off is unchanged too: still only 3 of 8 folds non-negative
(2017-06..2019-06, 2020-06..2022-06, 2023-06..2025-06) at both warmup
settings, the identical set of folds either way. **The foundational
decision to turn the regime floor on by default is not an artifact of the
cold-start bias -- it is confirmed independently under the corrected
methodology.**

The one small crack: the special `covid_2020` full calendar-year window
(not one of the 8 rolling folds, the window addendum #2 originally
highlighted) shows `maxdd_d=-0.14pp` with the floor on at `warmup_days=
756` -- technically negative, versus the clean 0.00pp addendum #2 reported
at `warmup_days=0`. This is negligible in context: floor-off in the same
window is `-4.42pp` at `warmup_days=756` (matching the original -9.35pp
problem in spirit, just smaller in magnitude under the corrected
methodology), so the floor still closes the overwhelming majority of the
gap; it just no longer closes it to *exactly* zero in this one specific
full-year framing. The 8-fold rolling result, which is the more rigorous
test, is unaffected by this.

### Corrected `vix_only` headline numbers (annual return / Sharpe deltas, floor on)

| Window | `warmup=0` Ann.Δ / Sharpe Δ | `warmup=756` Ann.Δ / Sharpe Δ |
|---|---|---|
| 2017-06..2019-06 | +1.70% / +0.268 | +2.71% / +0.417 |
| 2018-06..2020-06 | +4.53% / +0.446 | +3.35% / +0.399 |
| 2019-06..2021-06 | -6.16% / -0.072 | -3.03% / +0.115 |
| 2020-06..2022-06 | -1.40% / +0.096 | -2.26% / +0.028 |
| 2021-06..2023-06 | +0.92% / +0.072 | +0.41% / +0.027 |
| 2022-06..2024-06 | -3.65% / -0.083 | -2.24% / -0.002 |
| 2023-06..2025-06 | -3.46% / +0.082 | -1.24% / +0.219 |
| 2024-06..2026-06 | -10.52% / +0.026 | -11.63% / +0.248 |
| 2017-2019 OOS | +0.99% / +0.463 | +1.54% / +0.559 |
| 2018 trade war | +5.25% / +0.353 | +3.59% / +0.168 |
| 2020 COVID | -3.49% / -0.064 | -5.63% / -0.139 |
| 2024-2026 tuning | -5.41% / +0.440 | -8.73% / +0.390 |

No consistent direction of bias (some windows get better under warmup,
some worse) -- this is not a simple "the old numbers were all too
optimistic/pessimistic" correction, it's a real change in what the
z-scored `vix_stress` signal was actually measuring at the start of each
window. Sharpe deltas move toward *more positive* in most folds (6 of 8),
interestingly -- the floor's risk-adjusted benefit looks, if anything,
modestly understated by the `warmup_days=0` convention used throughout
this document so far, even though individual annual-return numbers moved
in both directions.

### Verdict

**Good news dominates**: this candidate's single most important
validated claim (the regime floor's MaxDD-never-worse property) is
robust to the methodological correction, confirmed independently rather
than merely re-asserted. The one crack found (a small, full-year-only,
-0.14pp deviation in the 2020 COVID special window) does not change the
practical conclusion. `credit_stress`'s genuinely weaker, mixed
`warmup_days=756` picture from addendum #10 stands as reported -- this
addendum does not revise that finding, it independently re-validates the
*other*, more foundational claim it was checked against. **A21.19's
overall verdict is unchanged: do not promote.** But confidence in the
regime-floor mechanism itself (as opposed to any specific tilt
component) is, if anything, now higher than before this session started,
having survived its most rigorous test yet.

### Files (07-25 addendum #11)

No script changes. New: `results/
a2119_vix_only_baseline_warmup_recheck_20260725.json` (48 rows: 12
windows x 2 warmup settings x 2 floor settings -- the source for both
tables above). No production files modified.

---

## 2026-07-25 addendum #12: credit_stress's full checklist, redone at warmup=756 -- final verdict is more cautious than addendum #10's "genuinely mixed 3-of-5"

Closes the loop addendum #10 left open: only 5 of the original checklist's
windows had been re-tested with credit at `warmup_days=756`. Re-ran the
full 8-fold rolling set (item 2), the 2017/2018/2019 crisis split (item 3),
and the cost-sensitivity sweep (item 4) -- all with credit -- at
`warmup_days=756`, matching addendum #9's original scope exactly. Raw
results: `results/a2119_credit_stress_warmup756_full_checklist_20260725.json`.

### Item 2: 8 rolling folds -- weakens further, from 6/8 to 4/8 clean wins

| Fold | Ann.Δ credit vs vix_only | Sharpe Δ credit vs vix_only | Verdict |
|---|---|---|---|
| 2017-06..2019-06 | +2.71%→+3.57% | +0.417→+0.514 | both better |
| 2018-06..2020-06 | +3.35%→+4.54% | +0.399→+0.498 | both better |
| 2019-06..2021-06 | -3.03%→-2.88% | +0.115→+0.101 | **mixed** (ann better, sharpe worse) |
| 2020-06..2022-06 | -2.26%→-2.14% | +0.028→+0.030 | both better (small) |
| 2021-06..2023-06 | +0.41%→+0.64% | +0.027→+0.047 | both better |
| 2022-06..2024-06 | -2.24%→-3.06% | -0.002→-0.035 | both worse |
| 2023-06..2025-06 | -1.24%→-3.28% | +0.219→+0.074 | both worse |
| 2024-06..2026-06 | -11.63%→-11.08% | +0.248→+0.233 | **mixed** (ann better, sharpe worse) |

**4 of 8 folds clean-improve (both metrics), 2 of 8 clean-worsen, 2 of 8
mixed** -- down from addendum #9's original 6-of-8 clean-improve at
`warmup_days=0`. Two folds that were clean wins before (2019-06..2021-06,
2024-06..2026-06) are now ambiguous rather than clearly positive.

### Item 3: crisis-independence -- still "2 of 3 positive," but which year is the outlier changes

| Sub-window | Ann.Δ credit vs vix_only, `warmup=756` | Sharpe Δ | vs. the `warmup=0` result |
|---|---|---|---|
| 2017 only | -0.37%→**-0.21% (better)** | +0.110→**+0.156 (better)** | **flips from worse to better** |
| 2018 only | +3.59%→**+3.31% (worse)** | +0.168→**+0.137 (worse)** | already known to flip (addendum #10) |
| 2019 only | +0.31%→**+3.74% (much better)** | +0.813→**+1.119 (much better)** | holds, stronger |

Still 2 of 3 years positive (meets the same bar as before), but **2017
and 2018 have swapped roles** -- originally 2017 was the lone negative
year and 2018/2019 were positive; now 2018 is the lone negative year and
2017/2019 are positive. The "which single year explains the pattern"
question doesn't have a stable answer across the warmup correction, which
is itself informative: the apparent crisis-independence wasn't as robust
as addendum #9's original framing suggested.

### Item 4: cost-sensitivity -- robust within each window, but now genuinely opposite-signed between the two crisis-adjacent windows

| Window | Metric | @1.0 | @0.5 | @0.1 | @0.0 |
|---|---|---|---|---|---|
| 2020 COVID | vix_only Ann.Δ | -5.63% | -5.03% | -4.54% | -4.42% |
| | credit Ann.Δ | **-6.09% (worse)** | **-5.29% (worse)** | **-4.63% (worse)** | **-4.47% (worse)** |
| Worst rolling fold | vix_only Ann.Δ | -2.26% | -1.75% | -1.34% | -1.24% |
| | credit Ann.Δ | **-2.14% (better)** | **-1.53% (better)** | **-1.03% (better)** | **-0.91% (better)** |

Credit is **worse at every cost level in 2020 COVID** (a clean reversal
from addendum #9's original finding, where it was better at every cost
level there) and **still better at every cost level in the worst rolling
fold** (holds). Both windows individually remain internally consistent
(the direction doesn't flip as cost varies within a window -- the
robustness property itself survives), but the two windows now point in
opposite directions from each other, and 2020 COVID is the one that
flipped.

### Consolidated final picture across the entire corrected checklist

Putting addendum #10's 5-window check together with this addendum's
items 2-4, at `warmup_days=756`: **credit_stress helps in calmer,
grinding, or recovery-adjacent periods (2017, 2019, the 2021-2023 fold,
the worst-rolling-fold which is mostly 2020-2022 recovery/2022 bear
market rather than the acute crash itself, 2024-2026 tuning on an
annual-return basis) and hurts in both of the two genuine crisis episodes
actually tested (2018 trade war, 2020 COVID) -- consistently across every
cost assumption in the 2020 case.** This is a materially more cautious
characterization than either addendum #9's "strongest evidence... a
specific, well-evidenced decision point" or even addendum #10's
"genuinely mixed 3-of-5" -- a component whose entire purpose is downside
protection showing its clearest, most cost-robust cracks specifically in
the two real crisis windows is a real concern, not a neutral wash.

### Final verdict

**`credit_stress` is not promoted, and should not be characterized as a
promising near-term lead going forward.** Its standalone IC remains real
(unaffected by the warmup question, since that was computed directly on
the signal, not through a backtest), which is worth remembering if the
signal construction itself is ever revisited (e.g. a shorter lookback, or
combined differently with the regime floor) -- but as configured and
tested today, its portfolio-level case is weaker than a fair reading of
addendum #8/#9 suggested, specifically because it is weakest exactly
where a defensive signal needs to be strongest. `w6_credit` stays at its
0.0 default. This closes out today's `credit_stress` investigation;
further work on it would need a different construction, not more
parameter sweeping at the current one.

### Files (07-25 addendum #12)

No script changes. New: `results/
a2119_credit_stress_warmup756_full_checklist_20260725.json` (38 rows:
8 rolling folds + 3 crisis-split years + 2 cost-sensitivity windows x 4
cost levels, all credit vs vix_only at warmup_days=756 -- the source for
all three tables above). No production files modified.
