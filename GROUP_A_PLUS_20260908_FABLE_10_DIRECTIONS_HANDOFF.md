# GroupA++ Fable 10-Directions Profitability Research — Handoff — 2026-09-08 (updated 2026-09-09)

## Status

**Research complete, nothing promoted.** Per user instruction "fable 針對最新策略,提岀10
改善獲利的方向" followed by "一件一件試試" (try them one by one), Fable proposed 10
directions to improve GroupA++ profitability; all 10 were tested empirically
(direction 2 explicitly skipped — see below). **Zero directions are ready for
production.** One (direction 6) has a genuinely promising signal but could not
be validated to production-grade rigor due to a real infrastructure gap
discovered this session (see H3 section below).

**2026-09-09 update**: per user request "3,5 做完" (finish 3 and 5), both were
pushed to a genuine forward-tested conclusion rather than left at "promising."
Both now resolve negative — see the "Direction 3/5 Follow-Up" section below.
**As of this update, every one of the 10 original directions is closed: 8
closed_negative/inert, 1 (#8) inconclusive due to a methodology gap, and 1
(#6) blocked by a repo infrastructure gap. This entire research line has no
further open threads unless new data or a new signal source becomes
available (see "What Would Actually Close the Gap" below).**

## Results Summary

| # | Direction | Verdict |
|---|---|---|
| 1 | Downside-classifier probability blended into PVA leverage_scale | **closed_negative** — classifier itself has weak AUC; blending made results monotonically worse across 8 weight combinations |
| 2 | ACI calibration of the same downside classifier | **skipped** — builds on the same weak classifier that failed in #1, not worth testing separately |
| 3 | 00713-vs-0050 relative strength as a regime signal | **closed_negative (as of 2026-09-09 follow-up)** — IC = -0.082 to -0.113 (p<0.001) is real, but 13 rule variants (shorter lookback, non-linear/threshold scaling, AND-gate) all fail: any parameter tuned for a fast crash (covid_2020) fails a slow bear (inflation_2022) and vice versa — a signal-design ceiling, not a calibration problem |
| 4 | AND-gate combining PVA + direction-3's signal | **neutral / basically inert** — gate only fires 12.5% of the time; MDD "improvement" is mostly an artifact of near-zero activation, and inflation_2022 was the worst-performing window of all three variants tested |
| 5 | Optimize defensive-basket re-entry (exit) timing | **closed_negative (as of 2026-09-09 follow-up)** — forward-testing looser exit rules across full history confirms the false-signal cost the original retrospective analysis couldn't see: earlier re-entry helps in clean V-recoveries but worsens `inflation_2022` MDD by 6.2pp. Only a near-zero-upside variant (ma_gap guard alone) has no downside — not worth pursuing standalone. |
| 6 | No-trade band on high-frequency PVA-driven rebalancing | **directionally plausible, not production-validated** — see dedicated section below |
| 7 | 0050 quarterly index-reconstitution price effect | **closed_negative** — 70 events (2009-2026), pre/post excess returns indistinguishable from noise (p=0.996, p=0.515); rules are public and the market is efficient enough that there's nothing to harvest |
| 8 | Walk-forward robustness of the 2020 COVID switch-rule fix | **inconclusive, initial version had a real bug — see dedicated section below** |
| 9 | NCF institutional-flow signal applied directly to 0050 core weights | **closed_negative — base-rate artifact** — H20 horizon looked strong (AUC 0.753) until checklist item 8's base-rate decomposition showed it was just reading the sample's 73.5%-up-day skew; true down-day accuracy was 30.4% (worse than random) |
| 10 | Symmetric (uncapped) volatility targeting on 00631L | **closed_negative** — production's existing `vol_scale` is already capped at 1.0 (never levers up) for good reason: adding a symmetric version hit its 1.5x ceiling on 2019-12-02, right before the COVID crash — the textbook vol-targeting blow-up, reproduced empirically. Sharpe and MDD both worsened in all 4 windows tested. |

## Direction 3/5 Follow-Up (2026-09-09) — Both Now Closed Negative

### Direction 3: 13 rule variants tried, none deployable — root cause is the signal, not the rule

Tested (a) shorter lookbacks (5d/10d instead of 20d — IC gets *weaker*, not
stronger, monotonically: -0.113 → -0.089 → -0.055; the "faster reaction"
hypothesis was wrong), (b)/(c) 9 non-linear/convex/pure-threshold scaling
variants, and (d) an AND-gate with a simplified drawdown-stress proxy. Every
single variant showed the same pattern with no exceptions: **whatever
parameter set performs well in covid_2020 (a fast V-shaped crash) performs
worse in inflation_2022 (a slow grinding bear), and vice versa.** The two
calm windows (live_2024_2026, active_2025_2026) lose money in nearly every
variant tested (often 6-figure TWD) from the drag of partial de-risking that
mostly doesn't pay off. **Root cause: this signal's response to a fast crash
and a slow bear market point in opposite directions — no single rule design
can serve both.** Not a calibration problem; a signal-design ceiling. Further
work on this line would require an independent signal that first
distinguishes "fast crash" vs. "slow bear" regimes — a new research
direction, not a continuation of #3. Memory:
`project_fable_direction3_followup_still_no_rule_20260909.md`.

### Direction 5: forward-test confirms the missing whipsaw cost is real

The original retrospective analysis (11/11 known-recovery events favored
earlier re-entry) explicitly flagged that it never tested false-signal cost.
This follow-up forward-tested concrete looser-exit rule variants across full
history using the real production switch rule (`a2111._build_switch_rule()`)
and real defensive basket. Result: **the missing cost shows up exactly where
expected.** Lowering `momentum_fast_exit_min` from 0.10 to 0.05 gains in the
clean V-recovery windows (covid_2020, live_2024_2026, active_2025_2026:
+NT$31k to +NT$232k) but worsens `inflation_2022`'s MDD from -24.33% to
-30.53% (a 6.2pp cost) — inflation_2022 is the one standard window that's a
genuine grinding bear rather than a clean crash-and-recover, exactly the
whipsaw scenario the original analysis couldn't see. Only one variant
(loosening the `ma_gap` guard alone, momentum threshold untouched) has zero
downside across all 4 windows, but its upside is under 0.5% final-value
improvement — not worth a standalone promotion push. Memory:
`project_fable_direction5_followup_mixed_collapses_in_whipsaw_20260909.md`.

Both follow-ups reinforce the same meta-lesson as directions 6 and 8:
**retrospective/proxy analysis in this project systematically looks cleaner
than a genuine forward-test across full history** — the third and fourth
instances of this pattern in a single research round.

## Two Methodology Findings That Matter More Than Any Single Direction

### Direction 8: a forked test used the wrong switch rule (caught and corrected)

The first-pass test imported `group_a_plus.runners.a207.A207_RULE` — an
unrelated research baseline (`ma_window=75`, `enter_ma_gap=-0.0175`,
`exit_ma_gap=0.02`) — instead of a2118's actual production rule,
`group_a_plus.runners.a2111._build_switch_rule()` (`ma_window=100`,
`enter_ma_gap=0.003`, `exit_ma_gap=0.010`). It also used a simplified
defensive basket (`{0050:40%, cash:60%}`) instead of production's real
`bond30_cash30` (`{0050:40%, 00679B.TWO:30%, cash:30%}`). This was caught
specifically because the result directly contradicted a precise, previously
documented fact from `GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md`
(that the pre-fix rule *never* triggered defensive during 2020-02-15..04-15) —
a concrete claim worth cross-checking before accepting a new finding that
overturns established, gate-validated production history.

Re-running with the correct rule and basket reproduced the same qualitative
pattern (2020 full-calendar-year framing is mildly negative for the fix,
2022 is positive, 2025 never triggered), so the original *direction* of the
finding survived the correction. But the corrected re-run's absolute numbers
still don't match the original 2020-fix handoff's validated figures (~NT$1.3M
vs. the handoff's NT$1.98M for the same nominal window), most likely because
this session's re-test used a static 50/20/30 golden1 approximation instead
of the real PPO-driven daily-drifting golden1 weights the original validation
used. **Verdict: inconclusive.** The 2020 fix should not be treated as
disproven, but "2020 fix = robust, crisis-general improvement" should also
not be treated as a settled fact anymore — a fully faithful re-test (real
`run_a2118()`, not a proxy) is the only way to close this out.

### Direction 6: a2118's own backtest engine has a structural blind spot (H3)

The original proxy test (recomputing PVA `leverage_scale` fresh from
historical price/vol data, applied to a static golden1 basket) found 89% of
days trigger some rebalancing and 85% of those moves are noise-sized
(<0.5pp) — a real, measurable cost-drag pattern — and that a no-trade band
improved final value/Sharpe monotonically across 4 windows without worsening
crisis-window MDD.

Attempting to re-validate this through a2118's actual `run_a2118()` pipeline
(real switch rule, NCF gates, 00713 sleeve, production `runner_params`)
produced band=0% and band=3% results that were **bit-identical in all 4
windows** — because a2118's backtest replay resolves golden1 from a single
static newest-mtime `signal_group_a_*.json` snapshot for the entire window
(the pre-existing "H3" limitation documented in `a2111.py`'s docstring and
`GROUP_A_PLUS_FABLE5_AUDIT_A214_REVERT_HANDOFF_20260702.md`), so it never
exhibits the day-to-day PVA drift the band is meant to filter. This is not
evidence the band doesn't help — it's evidence **a2118's backtest replay
cannot test this class of question at all**, regardless of the band width.

I checked whether the repo has enough historical daily golden1-signal
snapshots to properly close this gap: `results/signal_group_a_YYYYMMDD_*.json`
exists for 61 distinct trading days, but only from 2026-05-18 through
2026-09-07 — a recent, calm 4-month slice with zero coverage of either real
crisis window (covid_2020, inflation_2022) that mattered most for the MDD
question. **Not enough to validate the crisis-robustness claim.** Could
support a narrow "does the band cut cost during a normal recent stretch"
check, but not the risk question that actually matters.

**Bottom line on direction 6**: the original proxy result is the best
evidence available and is directionally consistent with production's own
execution-layer design (it already has a 0.5pp `min_weight_deviation` band —
this direction only asked whether it should be examined/widened). But it has
not been, and currently cannot be, validated to the same standard as the
2020 fix's original promotion-gate process. **Do not promote based on
current evidence.**

## What Would Actually Close the Gap (Not Done This Session)

1. Start persisting a genuine daily history of golden1 signal weights (not
   just the newest-mtime snapshot) so any future signal-level hypothesis can
   be backtested against real historical daily variation instead of a static
   snapshot or a hand-rolled proxy reconstruction.
2. Re-run direction 8's comparison through the real `run_a2118()` end-to-end
   (not a proxy) with real daily-drifting golden1 weights, to get numbers
   that are actually comparable to the original 2020-fix handoff's validated
   figures.
3. If direction 6 is still worth pursuing once (1) exists, re-test the band
   against real historical daily snapshots covering at least one genuine
   crisis window.

None of this is scheduled — flagging it as the natural next step if this
line of research continues.

## Files From This Round (all read-only research; nothing in production changed)

- `scripts/misc/test_downside_proba_pva_blend_20260908.py` (direction 1)
- `scripts/misc/test_00713_relstrength_signal_20260908.py` (direction 3)
- `scripts/misc/test_pva_00713_and_gate_20260908.py` (direction 4)
- (direction 5: inline analysis via `scripts/misc/test_reentry_timing_regret_20260908.py`)
- `scripts/misc/test_no_trade_band_20260908.py` (direction 6, original proxy)
- `scripts/misc/test_no_trade_band_a2118_faithful_20260908.py` +
  `results/no_trade_band_a2118_faithful_{covid_2020,inflation_2022,live_2024_2026,active_2025_2026}_20260908.json`
  (direction 6, a2118-faithful re-test)
- (direction 7: inline analysis, no new script)
- `scripts/misc/test_a207_2020fix_stability_20260908.py` (direction 8, original — uses the
  wrong switch rule, kept only for reference; corrected re-test was done ad hoc in
  a scratchpad, not committed to the repo)
- (direction 9: inline analysis on existing `results/ncf_0050_panel_latest_20260903.csv`)
- `scripts/misc/test_vol_targeting_20260908.py` (direction 10)
- `scripts/misc/test_00713_relstrength_rule_variants_20260909.py` +
  `results/fable_direction3_rule_variants_20260909.json` +
  `results/fable_direction3_and_gate_variants_20260909.json`
  (direction 3, 2026-09-09 follow-up — 13 rule variants)
- `scripts/misc/test_reentry_earlier_exit_forward_test_20260909.py` +
  `results/reentry_earlier_exit_forward_test_20260909.json`
  (direction 5, 2026-09-09 follow-up — full-history forward test)

Memory: `project_fable_10_directions_groupa_plusplus_20260907.md` (master
list) plus one `project_fable_directionN_*_20260908.md` file per direction,
plus `project_fable_direction3_followup_still_no_rule_20260909.md` and
`project_fable_direction5_followup_mixed_collapses_in_whipsaw_20260909.md`
for the follow-ups, all indexed in `MEMORY.md`.

## Independent Audit + Confirmation Experiments (2026-09-08, second pass)

An independent code-level audit of this round (not just re-reading the prose
above) found two real gaps and, while fixing one of them, surfaced a third
issue that changes how direction 5 should be read. All three were then
closed with committed, re-runnable experiments rather than left as findings.

### Audit finding A: direction 5's original "11/11" script never existed in the repo

The claim that started the whole direction-5 thread (11/11 known-recovery
events show positive regret for a 5-day-earlier re-entry) cited
`scripts/misc/test_reentry_timing_regret_20260908.py` as its source. That
file does not exist anywhere in the repo (confirmed via a full-repo
search) -- the claim was unreproducible as committed.

**Rebuilt and confirmed** in `scripts/misc/test_reentry_timing_regret_rebuild_20260908.py`
(`results/reentry_timing_regret_rebuild_20260908.json`): re-running the real
production switch rule across the full available history (2017-09-19
onward, bounded by 00713.TW's listing date) finds 10 switch_to_golden
re-entry events (not exactly 11 -- a minor, expected discrepancy from
reconstructing a lost script rather than a bug), and the same directional
pattern holds: **9/10 to 10/10 events show positive regret** across every
shift tested (1/3/5/10 trading days earlier). The original qualitative claim
is independently confirmed, not fabricated.

### Audit finding B: both the rebuild and the committed 2026-09-09 follow-up used a superseded defensive basket

While rebuilding finding A's script, cross-checking `DEFENSIVE_BASKETS`
against `group_a_plus/runners/a2118.py` found that **production's defensive
basket has been `bond0_cash60` (0050 40% / cash 60%) since the 2026-08-18
promotion** (00679B removed -- see a2118.py line ~838). The committed
`test_reentry_earlier_exit_forward_test_20260909.py` -- the script the
direction-5 "closed_negative" verdict and its "-24.33% to -30.53% MDD" number
are based on -- used `bond30_cash30` (0050 40% / 00679B 30% / cash 30%),
which has not been production's basket for three weeks before this script
was written.

**Re-ran with the corrected basket** in
`scripts/misc/test_reentry_earlier_exit_forward_test_basket_correction_20260908.py`
(`results/reentry_earlier_exit_forward_test_basket_correction_20260908.json`).
Result: the `lower_momentum_threshold_0.05` variant's inflation_2022 problem
does not go away -- it gets **worse** under the correct basket (MDD
-17.97%->-27.81%, a 9.84pp cost and a final-value *loss* of -66,670, vs the
stale-basket run's 6.2pp/gain-elsewhere tradeoff). The closed_negative
verdict for that specific variant is reconfirmed, more strongly, under the
correct basket.

### New finding surfaced while re-running: `lower_momentum_threshold_0.07` looks clean and was never highlighted

The same corrected re-run shows a second, previously-untested-in-the-prose
variant, `momentum_fast_exit_min=0.07` (vs production's 0.10), with:
- **inflation_2022: zero cost** -- Δfinal_value=0, ΔMDD=0.00pp in both the
  stale-basket run (results/reentry_earlier_exit_forward_test_20260909.json)
  and the corrected-basket run. The false-signal in inflation_2022 apparently
  has exit_momentum strictly between 0.05 and 0.07, so 0.07 never fires on
  it while 0.05 does.
- **covid_2020: zero effect** either way.
- **live_2024_2026 / active_2025_2026: +6% to +8.6% final-value gain**,
  larger than the ma_gap-guard variant the original handoff called "the only
  zero-downside variant" (which gained <0.5%).

This was sitting in the already-committed 09-09 result JSON the whole time;
the handoff prose just never surfaced it because it focused on the 0.05
variant's failure. **This is not confirmed as promotable** -- it was one of
only two threshold values tested (0.05, 0.07), so landing just above a
single historical false signal's exact momentum value is exactly the kind of
result [[feedback_overfitting_fixed_window_tuning]] warns about; it needs a
proper threshold sweep (not two hand-picked points) and should not be treated
as validated. But it should not have been implicitly dismissed either --
flagging as a real open thread for direction 5, contradicting this
document's earlier "every one of the 10 original directions is closed"
framing above.

### Audit finding C: direction 8's "corrected" numbers had zero committed evidence -- now fixed

The original direction-8 script used the wrong switch rule (A207_RULE
instead of a2111's) and a simplified basket; a "corrected" re-run was
described in `project_fable_direction8_a207_2020fix_not_robust_20260908.md`
but that memory file itself says it was only run in a scratchpad, never
committed -- so there was no independently-checkable evidence for it.

**Closed via `scripts/misc/test_a207_2020fix_stability_a2118_faithful_20260908.py`**
(`results/a207_2020fix_stability_a2118_faithful_20260908.json`), which calls
`group_a_plus.runners.a2118.run_a2118()` directly (not a hand-rolled proxy),
toggling only the three 2020-fix parameters between disabled (pre-fix) and
production values (post-fix), with the real switch rule and the real
(current, bond0_cash60) basket automatically correct because they're
hardcoded in `run_a2118()` itself. Result closely matches the scratchpad's
uncommitted numbers:
- 2020 full year: POST-fix final -15,829 vs PRE-fix (scratchpad: -23,259),
  MDD worsens 1.01pp (scratchpad: 1.49pp) -- same direction, similar
  magnitude.
- 2022 full year: POST-fix final +12,532 (scratchpad: +13,182), MDD worsens
  0.63pp (scratchpad: 0.75pp) -- both effectively reproduce the scratchpad
  almost exactly.
- 2025: delta=0 both times (never triggered).

**This is now committed, real evidence, not a restated scratchpad claim.**
The qualitative direction-8 finding ("2020 full-calendar-year framing is
mildly negative for the 2020 fix, 2022 is positive, 2025 untested") is
confirmed via the real production runner. The remaining caveat from the
original memory file still applies unchanged: `run_a2118()`'s own backtest
replay still resolves golden1 via the H3-documented static newest-mtime
snapshot rather than true historical daily-drifting weights, so this still
cannot be compared apples-to-apples to the original 2020-fix handoff's
NT$1.98M figure -- that specific gap requires the infrastructure fix
described in "What Would Actually Close the Gap" above, not just a faithful
rule/basket.

Memory: `project_fable_direction5_and_8_audit_confirmation_20260908.md`.

## Production State

Unchanged by this entire research round. The only real production change
this week remains the earlier, separately-decided GroupA++ 00713 cash-sleeve
weight bump (10%→12%), documented in
`GROUP_A_PLUS_PLUS_00713_HANDOFF_20260905.md` /
`GROUP_A_PLUS_20260906_SESSION_HANDOFF.md`.
