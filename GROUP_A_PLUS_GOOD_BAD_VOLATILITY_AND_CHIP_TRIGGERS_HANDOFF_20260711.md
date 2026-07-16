# Group A+ Good/Bad Volatility Paper + Chip-Trigger Directions — Handoff 2026-07-11

## Context

Follow-on session to `GROUP_A_PLUS_PAPER_IMPORTS_HANDOFF_20260711.md` (same
day, earlier: GNHAR + Wang & Yan downside-volatility papers, both closed
null) and `GROUP_A_PLUS_NCF_DOWNSIDE_SIGNAL_BOTH_CONFLICT_FIX_HANDOFF_20260711.md`
(unrelated production bug fix, same day). This document covers a third
paper (Bollerslev, Li, and Zhao (2019, JFQA), "Good Volatility, Bad
Volatility, and the Cross Section of Stock Returns") plus three follow-on
"chip/institutional-flow trigger" directions the user asked to explore after
that paper also came back null. **All research-only; nothing here changed
any production trading weight, alert, or decision rule.**

## Part 1: Bollerslev, Li, and Zhao (2019, JFQA) — feasibility assessment

User provided the PDF and asked whether the paper's approach ("good
volatility, bad volatility") could be implemented in Group A+.

**Paper's core measure**: relative signed jump (RSJ) = (RV+ - RV-) / RV,
where RV+/RV- are realized semivariances computed from **5-minute intraday**
prices within each day. At that sampling frequency the difference formally
isolates jump variation from continuous diffusion. Cross-sectionally sorting
~20,000 US stocks (1993-2013) into RSJ quintiles produces a highly
significant weekly return spread (value-weighted High-Low FFC4 alpha =
-28.80 bps/week, t=-5.77) -- high-RSJ stocks underperform, attributed to
investor overreaction to positive jumps.

**Assessed as infeasible to implement as designed**, for two independent
reasons:
1. **Hard data blocker**: this project's data layer (`FinRL/data/stock_db.py`)
   only ingests daily bars (`interval="1d"`). There is no intraday/tick
   ingestion anywhere in the codebase. The paper's jump-vs-diffusion
   separation is only mathematically valid at high sampling frequency; a
   daily-bar version is not RSJ, it is closer to the paper's own weaker
   comparison measure (realized skewness, RSK) which the paper shows is
   substantially less robust than RSJ and even flips sign once RSJ is
   controlled for.
2. **Structural mismatch**: the paper's effect is fundamentally
   cross-sectional (a stock's RSJ relative to ~20,000 peers in the same
   week). Group A+ holds a fixed small set of Taiwan ETFs
   (0050/00631L/00632R/00679B) as a single regime-timed portfolio -- there
   is no comparable cross-section to sort within.

Recommendation given to the user: don't build the paper as designed. User
then asked for a cheap daily-bar proxy test anyway ("好/壞波動度" framed
in plain language) -- see Part 2.

## Part 2: Daily-bar RSJ proxy — null (third paper this session in the same family)

Built `scripts/evaluate/evaluate_realized_semivariance_return_timing.py`:
`_realized_semivariance_asymmetry()` computes (RV+ - RV-)/RV over a rolling
5-trading-day window from **daily** returns (explicitly labeled a proxy, not
a replication -- see the module docstring's two caveats). Reuses
`_hac_ols_slope_tstat` from `evaluate_downside_vol_return_timing.py` (same
Newey-West/Bartlett-HAC test used for the Wang & Yan test earlier the same
day) to regress forward h-day return on the lagged proxy.

**Result on 0050.TW (2013-2026) and 00631L.TW (2015-2026): null, all 6
combinations p>0.20**, mostly wrong-signed (positive; paper's mechanism
predicts negative). This is the third independent test in this session's
"downside/asymmetric volatility predicts future returns" family to come back
null on these same two tickers (after Wang & Yan's downside-vol level test
and the GNHAR network-volatility forecast test). **Decision: this whole
family of hypothesis is closed** -- do not re-test with a different angle on
these tickers without a genuinely new reason.

Result files: `results/realized_semivariance_return_timing_0050_latest.json`,
`results/realized_semivariance_return_timing_00631l_latest.json`.

## Part 3: User's proposed trend+vol rule — recognized as A22 replay, redirected

User proposed: `bad_vol_high AND trend_weak -> de-risk`, `good_vol_high AND
trend_strong -> maintain/don't de-risk`. This is structurally the same shape
as `scripts/evaluate/evaluate_group_a_plus_a22_bad_vol_overlay.py`'s
A22_bad_vol_overlay research line (2026-07-10, 16 tuning stages, see
`GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md` and
memory `project_00631l_downside_risk_forecast_20260710.md`), just re-labeled
with "good/bad volatility" language instead of the generic GARCH-proxy
`vol_high` flag. Two pieces of directly relevant prior evidence were
surfaced before building anything new:

1. A22's own stage 13 ablation found re-introducing `vol_high` as a
   confirmation condition on top of a properly-tuned trend-persistence rule
   made results *worse* -- the champion configuration that actually won
   ended up with `vol_high` fully a no-op.
2. That same champion configuration (vol-independent) still **failed true
   out-of-sample validation** on the backfilled 2017-2019 NCF panel (three-
   year Δfv=-17,691, ΔSharpe=-0.058) -- proven overfitting to the 4 fixed
   tuning windows, not real edge.

Combined with Part 2's fresh null result (good/bad volatility asymmetry has
no standalone univariate predictive power on these tickers either), user
agreed to redirect to a different signal family instead of rebuilding this
already-twice-invalidated mechanism: chip/institutional-flow triggers.

## Part 4: Direction 1 — 0050-level foreign chip flow as an A22 bypass trigger (negative)

Extended `scripts/evaluate/evaluate_group_a_plus_a22_bad_vol_overlay.py`:

- `_chip_bad_series()`: flags extreme 0050 foreign net-selling (5d foreign
  flow, `foreign_0050_5d` from `backtest_group_a_plus_switch_policy.
  _load_chip_features`) in the bottom decile of its own trailing 252-day
  rolling distribution, `AND` negative (guards against the ~38% of days
  where the field is exactly 0.0 from data gaps/no-flow days).
- New CLI flag `--chip-bad-confirms-immediately`: mirrors the existing
  `--bad-vol-confirms-immediately` mechanism -- lets `chip_bad` bypass the
  `--bad-persistence-days` wait entirely, exactly like `vol_high` already
  can.

**Test**: champion config (`good_drawdown_min=-0.06`, `neutral_cap=0.15`
no-op, `bad_cap=bad_no_vol_cap=0.0`, `bad_persistence_days=8`) with and
without `--chip-bad-confirms-immediately`, across the 4 standard windows
(covid_2020/inflation_2022/live_2024_2026/active_2025_2026).

**Result: uniformly negative or flat.** All 4 windows' ΔSharpe and
Δfinal_value got worse or stayed flat with the chip bypass added; inflation_
2022 and active_2025_2026 degraded the most (inflation ΔSharpe -0.0183 ->
-0.0574; active ΔSharpe +0.0190 -> +0.0015). No window improved on both
metrics. Result: `results/a22_champion_plus_chip.json` vs
`results/a22_champion_baseline.json`.

## Part 5: Direction 2 — TSMC-specific foreign chip flow as the same bypass trigger (negative, worse than direction 1)

Motivation: 00631L's underlying (0050) is ~55-58% TSMC by weight, so
TSMC-specific foreign flow is a more targeted proxy for the position that
dominates 00631L's risk than the blended 0050-level flow in direction 1.

**Data discovery**: `institutional_data` DB table has zero rows for
`2330.TW` (only covers the ETF universe, 2020-2026). The needed history
exists instead in a long-running FinMind cache CSV,
`results/finmind_2330_institutional_buysell_cache.csv` (2012-05-02 to
2026-07-09, 15,343 rows) -- already used daily by
`scripts/report/build_ncf_2330_checklist.py`'s diagnostic-only
`chip_crowding` component, just never wired to actually move a weight.

Added to the same overlay script:
- `_load_tsmc_foreign_flow_5d()`: replicates `build_ncf_2330_checklist.py`'s
  `_chip_layer` foreign-flow calculation (Foreign_Investor +
  Foreign_Dealer_Self, 5-session rolling sum) across the full cached
  history instead of a single as-of snapshot.
- `_tsmc_chip_bad_series()`: same rolling-percentile design as
  `_chip_bad_series`, keyed on TSMC flow instead of 0050 flow.
- New CLI flag `--tsmc-chip-bad-confirms-immediately`.

**Result: also uniformly negative, and worse than direction 1 in the two
most recent windows.** active_2025_2026's ΔSharpe flipped from positive to
negative (+0.0190 -> -0.0145, a bigger swing than direction 1's -0.006);
live_2024_2026 Δfinal_value degraded further (-153,272 -> -184,237 vs
direction 1's -184,237... i.e. -163,767). Result:
`results/a22_champion_plus_tsmc_chip.json`.

**Convergent finding across directions 1+2 plus the pre-existing
`--bad-vol-confirms-immediately` mechanism**: three different trigger
signals (GARCH vol_high, 0050 chip flow, TSMC chip flow), all wired through
the same "confirms-immediately bypass persistence" architecture, all produce
the same negative pattern. This strongly suggests **the bypass mechanism
itself is the problem** (adds false positives during benign pullbacks,
regardless of which signal drives it), not any particular signal's quality.
Recommendation given to user: stop testing more signals through this same
bypass architecture.

## Part 6: Direction 3 — TXO foreign options positioning, standalone test (initially null, then a real data gap fix, then a promising-looking but ultimately non-robust result)

Per the convergent finding in Part 5, direction 3 was deliberately tested
*differently* -- not wired into the A22 bypass mechanism, but as a
standalone Newey-West/HAC return-timing regression (same style as Parts 1-2
and the earlier Wang & Yan test), to isolate whether the raw signal has any
predictive power at all, independent of how it might later be wired into a
rule.

Built `scripts/evaluate/evaluate_txo_foreign_positioning_return_timing.py`:
regresses forward h-day return (5/10/20) on lagged
`txo_foreign_put_call_net_oi` (foreign TXO put net OI - call net OI, i.e.
positive = net bearish options positioning) and its 5-day change, for
0050.TW and 00631L.TW.

### First pass: null, but badly underpowered

Initial run only covered `derivative_institutional_data`'s existing range,
**2025-01-02 to 2026-07-09 (~384 trading days, n≈340-355 after warm-up)** --
missing both crisis windows (2020, 2022) entirely, roughly an order of
magnitude less history than every other test this session. All 12
combinations (2 tickers x 3 horizons x 2 predictor variants) came back
p>0.10, but this null was explicitly flagged as low-confidence given the
sample size, not a real rejection.

### Data gap discovery and fix (permanent, independent of this hypothesis)

User asked "能加長資料?" (can the data be extended?). Probed the FinMind API
directly (`fetch_derivative_institutional`, already used by
`scripts/fetch/fetch_finmind_chip_data.py`) with small date-range test calls
and found **real coverage exists back to ~2018-06-05** -- the DB simply had
never been backfilled before whatever session first added this feature
around 2025-01-02; this was a fetch-history gap, not an API/data-source
limitation (probed down to 2005 and 2010, both empty; 2018-04 empty,
2018-07 had data -- binary search landed the actual boundary near
2018-06-05).

**Ran a real backfill**: `python3 scripts/fetch/fetch_finmind_chip_data.py
--start 2018-05-01 --end 2025-01-01 --datasets derivative_institutional
--futures-ids TX --option-ids TXO` -- wrote 14,445 new rows. Verified new
coverage: `derivative_institutional_data` now spans 2018-06-05 to
2026-07-09 (1990 trading days) for both TX futures and TXO options, all
three institutional-investor categories (外資/投信/自營商). **This is a
permanent data-completeness fix**, independent of whether the TXO-positioning
hypothesis below holds -- any future research needing TX/TXO institutional
flow history back to mid-2018 can use it directly.

### Second pass with extended data: significant at h=5 for both tickers

| Ticker | h | level p | Δ5d p |
|---|---|---:|---:|
| 0050.TW | 5 | **0.041** | **0.001** |
| 0050.TW | 10 | 0.111 | 0.066 |
| 0050.TW | 20 | 0.128 | 0.217 |
| 00631L.TW | 5 | **0.035** | **0.001** |
| 00631L.TW | 10 | 0.095 | 0.052 |
| 00631L.TW | 20 | 0.100 | 0.148 |

n≈1942-1957 across the 2018-06-05..2026-07-09 window. Both level and Δ5d
slopes negative and consistent across tickers: higher foreign bearish
options positioning (more puts relative to calls) predicts *lower*
subsequent returns, strongest at the shortest horizon (h=5) and decaying by
h=20 -- an economically sensible pattern for a short-lived hedging-flow
signal. This was, at this point, the first genuinely significant result
across the entire session's ~30+ hypothesis tests.

### Split-sample robustness check: fails, closed

Before treating this as actionable, split the 2018-06..2026-07 window in
half at 2022-06-21 and re-ran the h=5 HAC regression separately on each
half:

| Ticker | Period | level p | Δ5d p |
|---|---|---:|---:|
| 0050.TW | first half (2018-06..2022-06, includes covid crash + 2022 bear) | 0.047 | 0.001 |
| 0050.TW | second half (2022-06..2026-07, recent/live-relevant) | 0.649 | 0.524 |
| 00631L.TW | first half | 0.050 | 0.001 |
| 00631L.TW | second half | 0.373 | 0.655 |

**Significance is entirely concentrated in the first half and completely
absent in the second half** (all four second-half p-values >0.37). This
matches a pattern this project has hit repeatedly (GARCH/specialist routing,
A22's OOS failure): a small number of major crisis episodes inside a
backtest window can create apparent predictability through simple
crisis-co-movement, which is not the same as a stable, tradeable
relationship. The full-sample significance does not survive being split
away from the two crisis periods it happens to contain.

**Decision: closed, not actionable.** Do not build a trading rule from this.
The only durable output of this direction is the data backfill itself (see
above), not the hypothesis.

## Files touched this session (Parts 1-6, in addition to the separately-
documented NCF downside-signal fix)

**New modules/scripts:**
- `scripts/evaluate/evaluate_realized_semivariance_return_timing.py`
- `scripts/evaluate/evaluate_txo_foreign_positioning_return_timing.py`

**Modified (additive only):**
- `scripts/evaluate/evaluate_group_a_plus_a22_bad_vol_overlay.py` (+
  `_chip_bad_series`, `_load_tsmc_foreign_flow_5d`, `_tsmc_chip_bad_series`,
  `--chip-bad-confirms-immediately`, `--tsmc-chip-bad-confirms-immediately`
  and related window/percentile flags; existing champion-config behavior
  unchanged when the new flags are not passed)

**Database changes:**
- `derivative_institutional_data` backfilled from 2018-05-01 through
  2025-01-01 (14,445 rows), extending existing coverage back from
  2025-01-02 to 2018-06-05. Permanent, unrelated to any research conclusion
  above.

**New result artifacts:**
- `results/realized_semivariance_return_timing_0050_latest.json`
- `results/realized_semivariance_return_timing_00631l_latest.json`
- `results/a22_champion_baseline.json`
- `results/a22_champion_plus_chip.json`
- `results/a22_champion_plus_tsmc_chip.json`
- `results/a22_champion_reproduce_check.json`
- `results/txo_foreign_positioning_0050_latest.json` (final, extended-data version)
- `results/txo_foreign_positioning_00631l_latest.json` (final, extended-data version)

**Production impact: none.** Every change is either a research script or
research-only DB history that isn't consumed by any live signal/gate. The
A22 overlay script itself remains `research_only_no_lookahead` and is not
wired into `run_a2118`, `daily_signal.py`, or any other live path.

## What's open for the future

1. **Do not** re-test the "good/bad volatility asymmetry predicts returns"
   hypothesis on 0050/00631L again without a genuinely new angle -- three
   independent tests this session (Wang & Yan level, daily-RSJ-proxy,
   TXO options positioning full-sample) all either came back null or failed
   robustness. This is now a well-established closed line.
2. **Do not** wire more signals into the A22 overlay's
   `--*-confirms-immediately` bypass mechanism -- three different signals
   (vol_high, 0050 chip, TSMC chip) all produced the same negative pattern
   through this architecture. If chip/flow signals are revisited, they need
   a structurally different integration point, not this bypass.
3. The `derivative_institutional_data` backfill (2018-06 onward) is
   reusable infrastructure independent of this session's closed hypotheses
   -- any future TX/TXO institutional-flow research (e.g. as a feature in
   the ML race-classifier line, or a genuinely different hypothesis about
   options positioning) can use the extended history directly without
   re-fetching.
4. Direction 1 of the original three chip-direction proposals ("wire chip
   features into the A22 rule framework, not the ML classifier") is now
   fully tested and closed (Part 4). Directions 2 (TSMC-specific, Part 5)
   and 3 (TXO options, Part 6) are also closed. All three original
   candidate chip directions from this session are exhausted.

Related: `project_downside_vol_return_timing_20260711.md`,
`project_paper_imports_session_20260711.md`,
`project_00631l_downside_risk_forecast_20260710.md` (A22 origin + OOS
failure), `feedback_overfitting_fixed_window_tuning.md`.
