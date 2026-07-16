# GroupA+ ncf_2330 H1 Tactical Overlay — Attempt #6 Handoff (2026-07-07)

## Scope

Direct follow-up to `GROUP_A_PLUS_NCF2330_SWITCHRULE_INTEGRATION_ATTEMPTS_HANDOFF_20260705.md`
(five independent, all-rejected attempts to give `ncf_2330` weight-level influence over
`a2118`) and `results/NCF_2330_LEADERSHIP_PROMOTION_HANDOFF_20260707.md` (same-day,
earlier: `TSMC_Leadership_Score` promoted into `ncf_2330` production, raising H1
direction `val_auc` from ~0.55 to ~0.76 on a strict 2025-2026 OOS split).

User's question this session: "ncf_2330 可以導入 GroupA+ 的最新策略?" (can ncf_2330 be
integrated into GroupA+'s current live strategy?), followed by "先試試H1" (try H1
first) after being told the five prior rejections all used H20 direction and/or 20d
tail-risk — never the H1 (1-day-ahead) signal, and that H1 was the metric that improved
dramatically in this week's promotion while H20/tail-risk moved much less.

This is a genuinely new angle, not a re-run: none of the five 2026-07-05 attempts (see
prior handoff) touched `prob_up_h1`.

## What GroupA+'s "latest strategy" is

`report/group_a_plus/latest/strategy.json` (read via
`group_a_plus.governance.latest.DEFAULT_LATEST_STRATEGY` /
`group_a_plus.runners.latest.run_latest`) currently points to `a2118`
(`group_a_plus/runners/a2118.py`) as the active strategy — confirmed via
`project_2020_switch_rule_fix_promotion_ready_20260706` memory and by reading
`a2118.py` directly. a2118 trades a `0050.TW` / `00631L.TW` / bond / cash basket with
an MA100-based regime switch plus an NCF-late-bull-hedge overlay (that overlay uses
`ncf_00631l`'s H20 signal — a different model from `ncf_2330`). `ncf_2330` itself
(the TSMC individual-stock model) has never driven a2118's weights; it only feeds
`group_a_plus/integrations/signal_alignment.py` and alert messages
(`daily_signal.py`) as advisory context.

## Overlay design tested

Trim `00631L.TW` into cash for a single day whenever, while a2118 is in its normal
`golden1` regime:

```
ncf_2330's prob_up_h1 < h1_prob_max   AND   confidence > confidence_min
```

This mirrors the existing `scripts/misc/a2118_ncf_2330_tsmc_overlay_sweep.py`
convention (same `_trimmed_weights` mechanic, same `_simulate_costed_curve` /
`_metrics` harness) but keys off the 1-day signal instead of the 20-day one.

Because H1 is a daily/high-frequency signal (not a rare regime flag like the late-bull
hedge, which fired only 4-5 times across the whole window), trigger-day counts and
transaction costs are reported prominently. a2118's own docstring already documents
that a continuous/frequent NCF-based overlay (A21.13) caused -18.5% drag historically
— this was the main risk going in.

## Script

New: `scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py` (read-only w.r.t.
production; writes only `results/a2118_ncf_2330_h1_tactical_overlay_sweep_20260707.json`).

Inputs:
- `results/ncf_2330_panel_latest_20260707.csv` (the finalized, post-promotion panel —
  `prob_up_h1`, `confidence`, `direction` columns, 2025-01-02 ~ 2026-07-02, 360 rows).
- a2118's actual regime/weight history via `run_latest`.

Initial sweep grid (48 combinations, later extended — see Addendum):
- `h1_prob_max` (predicts DOWN below this): `0.35, 0.40, 0.45`
- `confidence_min`: `0.15, 0.20, 0.25, 0.30`
- `trim_fraction`: `0.15, 0.25, 0.35, 0.50` (extended to add `0.65, 0.75, 1.00` in the
  Addendum below; the script's `TRIM_FRACTIONS` constant now reflects the extended
  7-value grid, 84 combinations total)

Panel distribution check before the sweep (`prob_up_h1` mean=0.526, std=0.200;
`confidence`≈`prob_magnitude`, mean=0.264, std=0.181; raw `direction` split
UP=285/DOWN=75 of 360 days): trigger-day counts across the grid range from 3 to 33
days (0.8%-9.2% of the window), confirming the threshold grid spans "very rare, tight
trigger" to "moderately frequent" without ever becoming the old A21.13-style "fires on
most days" failure mode.

## Result: 0/48 improve final value

Baseline (a2118, 2025-01-02~2026-07-02): `final_value=2,143,721`,
`sharpe_ratio=2.525`, `max_drawdown=-13.82%`.

- **0 of 48 variants improved `final_value`.** Every variant lost money vs baseline.
- **48 of 48 "improved" `max_drawdown`**, but only by 0.04-0.25 percentage points —
  noise-level, not a meaningful risk reduction.
- **0 of 48 improved both simultaneously.**

Best case (tightest grid point, `h1_prob_max=0.35, confidence_min=0.30,
trim_fraction=0.50`, only 3 trigger days): `final_value` delta = **-$80** (essentially
breakeven, still not positive), `max_drawdown` delta = **+0.114pp**, for 6 extra
rebalances (~$901 transaction cost).

Worst case (loosest grid point, `h1_prob_max=0.45, confidence_min=0.15,
trim_fraction=0.15`, 33 trigger days): `final_value` delta = **-$56,533 (-2.6%)**,
`max_drawdown` delta = **+0.088pp** — worse thresholds trigger more often, cost more,
and don't even buy proportionally more drawdown protection.

Distinct `max_drawdown` deltas across the whole 48-variant grid: `{0.0004, 0.0006,
0.0008, 0.0009, 0.0011, 0.0014, 0.0018, 0.0025}` — all sub-quarter-point, regardless of
how the thresholds are tuned.

## Why the AUC gain doesn't transfer

ncf_2330's H1 model got much better at predicting **TSMC's own next-day direction**
(`val_auc` 0.55→0.76). But the overlay needs that to translate into **00631L/TWII's
next-day return being different enough to justify a round-trip trade's transaction
cost** (commission 0.1425% + slippage 0.05% + sell tax 0.1% per this backtest's cost
model). "TSMC probably down tomorrow" does not reliably mean "TWII/00631L down by
enough tomorrow" — TSMC is a large but not sole index component, and even correctly
called down-days are often small relative to a single day's round-trip cost. This is a
distinct failure mode from the five 2026-07-05 attempts (which failed because their
*trigger detection itself* couldn't distinguish a real drawdown from a pullback that
later recovered) — here the direction call is genuinely much better, but a same-day
tactical trim is simply the wrong instrument for it: 1-day edges this size can't clear
a round-trip transaction-cost hurdle in a leveraged-ETF strategy that already
rebalances relatively rarely.

## Addendum 1: does a larger trim fraction clear the transaction-cost hurdle?

Follow-up question from the user: since transaction cost and avoided-loss both scale
with `trim_fraction`, does pushing `trim_fraction` higher (toward a full same-day exit)
eventually make the overlay profitable?

Extended `TRIM_FRACTIONS` to `[0.15, 0.25, 0.35, 0.50, 0.65, 0.75, 1.00]` (84 variants
total) and re-ran the same script/grid.

Result: **9 of 84 variants now improve `final_value`** (up from 0/48) — but all 9 reduce
to only **3 distinct underlying scenarios**, all keyed on the strictest confidence
threshold tested (`confidence_min=0.30`), which fires on only **3 of 360 trading days**
(`2025-02-07`, `2025-02-21`, `2025-08-19`; worst single-day return after a trigger:
-1.97%) regardless of which `h1_prob_max` (0.35/0.40/0.45) is paired with it:

| `trim_fraction` | net P&L vs baseline | transaction cost |
|---|---:|---:|
| 0.65 | +$2,361 (+0.11%) | $1,151 |
| 0.75 | +$3,988 (+0.19%) | $1,317 |
| 1.00 | +$8,059 (+0.38%) | $1,734 |

So yes — empirically, at the strictest threshold, a larger trim fraction's avoided loss
eventually outgrows the round-trip transaction cost, flipping the sign positive. But
this is **not evidence of a generalizable edge**: it rests on n=3 historical trigger
days. Loosening `confidence_min` to 0.15-0.25 (10-33 trigger days) while keeping
`trim_fraction=1.00` makes things *worse*, not proportionally better (`final_value`
deltas of -$5,439 to -$31,128) — so "bigger trim fraction always helps" is false in
general; it only appears to help in this one thin, high-conviction subsample, which is
the same "flat identical improvement across a tiny fixed set of days" pattern flagged
as statistically meaningless in Attempt 4 of the 2026-07-05 handoff. Conclusion is
unchanged: reject, insufficient sample to trust.

Updated result file: `results/a2118_ncf_2330_h1_tactical_overlay_sweep_20260707.json`
now contains all 84 variants (grid extended in-place, same filename).

## Addendum 2: multi-window validation (2020 COVID, 2022 inflation)

User's follow-up question: does the (thin, n=3) 2025-2026 result hold up across the
project's standard 5-window stress-test convention (`gfc_2008`, `china_fx_2015`,
`china_fx_2016_partial`, `covid_2020`, `inflation_2022` — see
`scripts/misc/stress_group_a_plus_multi_windows.py`)?

### Data availability check (before running anything)

Queried `FinRL/data/stock_data.db` directly:

| Table | Coverage | Blocks |
|---|---|---|
| `external_market_ohlcv` (2330.TW) | 2014-01-02 ~ latest | `gfc_2008` entirely (no TSMC price data before 2014) |
| `ohlcv` (00631L.TW) | 2015-01-05 ~ latest | `gfc_2008` entirely; a2118 cannot even be simulated pre-2015 (the instrument doesn't exist) |
| `ohlcv` (0050.TW) | 2009-01-02 ~ latest | `gfc_2008`'s 2007-2008 crash itself still uncovered |
| `institutional_data` / `margin_data` (chip flow) | 2020-01-02 ~ latest | `china_fx_2015`/`china_fx_2016_partial` entirely (no chip features at all, and insufficient pre-window training history even if price data existed); `covid_2020` has zero lead-in history (chip data starts exactly at window start) |
| `derivative_institutional_data` (TXO) / `foreign_shareholding_data` | 2025-01-02 ~ latest | every historical window (only exists for the current live period) |

Conclusion: **3 of 5 standard windows (`gfc_2008`, `china_fx_2015`,
`china_fx_2016_partial`) cannot be faithfully tested at all** — not a modeling
limitation, the underlying price/chip tables simply don't cover those dates (same root
cause repeatedly documented in `GROUP_A_PLUS_NCF2330_SWITCHRULE_INTEGRATION_ATTEMPTS_HANDOFF_20260705.md`
and the 2026-07-04 market_state arbitration handoff). Given a user choice between
skipping this line of testing entirely versus testing only the two feasible windows,
user chose to test `covid_2020` and `inflation_2022`.

### Method

For each window, retrained `ncf_2330` fresh (finalized/promoted feature set, same as
the official 2026-07-07 retrain) with `train_start=2015-01-01` and `val_start`/`val_end`
covering the target year, then ran the same `a2118_ncf_2330_h1_tactical_overlay_sweep.py`
grid (now parameterized with `--start/--end/--panel/--output/--window-label`, extended
from the earlier single-window version — see "Script parameterization" below) against
`run_latest` over the identical window.

```bash
.venv/bin/python ncf_2330.py --train-start 2015-01-01 --val-start 2020-01-02 --val-end 2020-12-31 \
  --output results/ncf_2330_covid_2020_window_20260707.json \
  --val-predictions-output results/ncf_2330_covid_2020_panel_20260707.csv \
  --full-panel --feature-mode after_close
# H1 val_auc = 0.7319 (close to the 2025-2026 official number of 0.7625 -- the
# leadership signal generalizes reasonably despite the chip-data cold start)

.venv/bin/python ncf_2330.py --train-start 2015-01-01 --val-start 2022-01-03 --val-end 2022-12-30 \
  --output results/ncf_2330_inflation_2022_window_20260707.json \
  --val-predictions-output results/ncf_2330_inflation_2022_panel_20260707.csv \
  --full-panel --feature-mode after_close
# H1 val_auc = 0.7236

.venv/bin/python scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py \
  --start 2020-01-02 --end 2020-12-31 --panel results/ncf_2330_covid_2020_panel_20260707.csv \
  --output results/a2118_ncf_2330_h1_tactical_overlay_sweep_covid_2020_20260707.json --window-label covid_2020

.venv/bin/python scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py \
  --start 2022-01-03 --end 2022-12-30 --panel results/ncf_2330_inflation_2022_panel_20260707.csv \
  --output results/a2118_ncf_2330_h1_tactical_overlay_sweep_inflation_2022_20260707.json --window-label inflation_2022
```

Note on a2118 + historical windows: `run_a2118`'s late-bull hedge overlay only
activates when a matching `ncf_00631l` panel row exists for that date
(`_load_ncf_panel`/`panel_631l`); the live panel only covers 2025-2026, so over the
2020/2022 windows it silently has zero coverage and the hedge never fires — `run_latest`
effectively reduces to the base MA100 regime-switch (A21.11-equivalent) for these two
historical runs, which is a clean, unconfounded baseline for testing the ncf_2330
overlay in isolation.

### Script parameterization

`scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py` was extended with
`argparse` (`--start`, `--end`, `--panel`, `--output`, `--window-label`), defaulting to
the original 2025-2026 values so the earlier invocation still reproduces identically
(verified: re-ran with no window args, got the same 9/84-improve, same top-5 list, same
numbers as the original run before this addendum).

### Result: sharply regime-dependent, not a consistent answer

| Window | a2118 baseline | H1 overlay result |
|---|---|---|
| `covid_2020` (V-shaped crash + fast recovery) | final=1,282,253, Sharpe=1.628, max_dd=-17.99% | **0/84 improve final_value.** Best case still -$6,742 (47 trigger days); every variant that fires meaningfully loses money. Higher volatility -> more frequent triggers -> more transaction cost without proportionally more captured protection. |
| `2025-2026` (mild bull, from the main handoff above) | final=2,143,721, Sharpe=2.525, max_dd=-13.82% | **9/84 improve**, but only from a thin n=3-trigger-day subsample (see Addendum 1) — not statistically trustworthy. |
| `inflation_2022` (grinding, persistent bear market) | final=809,134, **Sharpe=-1.071 (a2118 itself lost 19.1% this year)** | **82/84 improve final_value, 55/84 improve both final_value and max_drawdown.** Effect scales monotonically with `trim_fraction` (mean delta $4,713 at trim=0.15 up to $35,172 at trim=1.0). Best variant (`h1_prob_max=0.45, confidence_min=0.15, trim_fraction=1.00`, 65 trigger days): **+$58,017 (+7.2%), Sharpe +0.392, max_drawdown +3.25pp.** Only 2 of 84 variants (both at the weakest `trim_fraction=0.15`) are marginally negative (-$373 / -$766). |

### Why 2022 looks so different — and why that's not enough to promote

The 2022 result is internally coherent, not noise: a2118's own MA100-based regime
switch apparently stayed too long in `golden1` (bullish exposure) through a grinding,
persistent decline that year — that's *why* the baseline itself lost 19.1%. ncf_2330's
daily H1 signal, updating every day, can duck out of exposure faster than a2118's own
slower regime detector during exactly that kind of sustained downtrend, which is why
the benefit scales smoothly with how aggressively you trim (`trim_fraction=1.0`
wins outright) rather than concentrating in one lucky day the way the 2025-2026 result
did.

But this cuts the other way in `covid_2020`: the same "trim on a down-signal day"
mechanism, applied to a market that drops sharply then recovers just as sharply, means
frequently ducking out right before the rebound — the opposite regime, same mechanism,
opposite outcome. **The overlay is not learning "risk," it's amplifying whatever
autocorrelation currently exists in the return series** (helps in trending declines,
hurts in V-shaped reversals, roughly neutral when there's no persistent direction).
Nothing in the current signal (or in a2118) tells you in advance which of the two
regimes you are in — this is the exact same "early-stage correction vs. early-stage
crash are statistically indistinguishable with price/volatility-only signals" finding
already independently confirmed twice before (2026-07-04 market_state arbitration;
2026-07-05 SwitchRule override attempts). A third independent mechanism (this H1
overlay) landing on the same wall reinforces rather than merely repeats that
conclusion.

### Decision (updated)

**Still rejected for production**, now with stronger evidence: 3 tested windows produce
3 different verdicts (hurts / thin-and-untrustworthy / helps-a-lot) that flip based on
market regime character, and there is no available signal to know in advance which
regime is coming. Promoting on the strength of the 2022 result alone would be
promoting on 1 out of 3 windows, in the same "1 good year isn't enough" spirit the user
has flagged before ([[feedback_strategy_promotion_caution]]). `gfc_2008`,
`china_fx_2015`, and `china_fx_2016_partial` remain permanently untestable with this
project's current data — not a research gap that more sweeping will close.

If revisited again, the only new option that could change this conclusion is a genuine
new data dimension capable of distinguishing "grinding bear" from "V-shaped crash" in
advance (credit spreads, options-implied skew, cross-asset confirmation) — not another
parameter sweep of the same price-derived H1/H20/tail-risk signals over the same
handful of historical years.

### Files Produced This Addendum

- `results/ncf_2330_covid_2020_window_20260707.json` /
  `results/ncf_2330_covid_2020_panel_20260707.csv`
- `results/ncf_2330_inflation_2022_window_20260707.json` /
  `results/ncf_2330_inflation_2022_panel_20260707.csv`
- `results/a2118_ncf_2330_h1_tactical_overlay_sweep_covid_2020_20260707.json`
- `results/a2118_ncf_2330_h1_tactical_overlay_sweep_inflation_2022_20260707.json`
- `scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py` modified in place (added
  CLI args; default behavior unchanged and verified to reproduce the original
  2025-2026 result bit-for-bit)

## Decision (original, single-window; see "Decision (updated)" in Addendum 2 above for the final word)

**Rejected.** No production code changed. `ncf_2330` remains advisory-only in
`daily_signal.py` / `signal_alignment.py`, with zero effect on a2118's portfolio
weights — now confirmed correct after **six** independent rejected attempts to give it
weight-level influence (the five 2026-07-05 H20/tail-risk attempts, plus this H1
attempt).

If ncf_2330 is revisited for GroupA+ integration again, the two remaining angles not
yet tried are: (a) a *slower* aggregation of the H1 signal (e.g. a rolling N-day
majority-vote or smoothed probability, to reduce whipsaw versus a raw daily flag) — but
this starts to resemble the H20 signal already tested and rejected; or (b) treating the
signal purely as an advisory display item (already done) rather than continuing to
search for a weight-changing mechanism, since six independent designs across two very
different signal horizons have now failed to clear a2118's transaction-cost bar in this
window.

Addendum 2 (multi-window test across 2020/2022) does not overturn this — it produces a
regime-dependent split (helps in 2022, hurts in 2020) that is, if anything, a stronger
reason not to promote than this single 2025-2026 window alone was.

## Files Produced This Session

- `scripts/misc/a2118_ncf_2330_h1_tactical_overlay_sweep.py` (new, read-only sweep
  script)
- `results/a2118_ncf_2330_h1_tactical_overlay_sweep_20260707.json` (new, full 48-variant
  result set + baseline + top-10/top-5 rankings)

## No Production Changes

Only new research files were added (script + result JSON). No file under
`group_a_plus/`, `backtest_group_a_plus_switch_policy.py`, or
`report/group_a_plus/latest/*` was modified in this session.
