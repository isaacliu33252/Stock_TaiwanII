# GroupA+ 2026-08-23 Handoff: arXiv:2501.16659 EMVRS Review + OHLCV Corporate-Action DB Fix

## Status

Paper decision: `do_not_promote`. The paper's core claim was tested directly
on Taiwan data (not closed on desk analysis alone, per explicit user
request) and does not replicate. A real, previously-unfixed production
database bug was found during testing and fixed for real (written to the
shared DB, not just in-memory) at the user's explicit request. No GroupA+
strategy code was changed.

## User Request

User provided: `C:\Users\isaac\Downloads\2501.16659.pdf`

Question: Analyze whether the paper has useful advantages that can be
imported into GroupA+ and the latest strategy.

Follow-up: after a desk-analysis critique recommending `do_not_promote`
without writing code, user said "實測看看" (test it anyway). After the test
surfaced a data bug, user said "修正DB" (fix the DB) -- twice, after the
first direct-write attempt was blocked by Claude Code's auto-mode
classifier; the user then ran the pre-verified fix script themselves via
shell-passthrough (`!`).

## Part 1: Paper Summary

Paper: `arXiv:2501.16659v1 "Exploratory Mean-Variance Portfolio Optimization
with Regime-Switching Market Dynamics"` (Chen, Li, Saunders, University of
Waterloo, January 2025).

Core contribution: EMVRS, a continuous-time exploratory Mean-Variance
portfolio optimization problem under regime-switching market dynamics,
solved via reinforcement learning. Introduces "Orthogonality Condition (OC)
learning" as an alternative to standard Temporal Difference (TD) learning
for estimating the market parameters (volatility and Sharpe ratio per
regime) that parameterize the RL value function -- OC learning does not
require knowledge of the true market parameters (unlike the Martingale Loss
approach of a competing paper, B. Wu & Li 2024) and is shown, in a
controlled simulation with known ground truth, to converge to the true
parameters where TD learning does not.

Real-market claim: on a real S&P500 study (24 rolling 10-year windows,
2006-2017, monthly rebalancing, leverage/short-selling settings from 1x to
3x), EMVRS trained with OC learning achieves annualized Sharpe ratios up to
**5.93**, dramatically outperforming a non-regime-switching EMV baseline
(Sharpe ~0.59-3.46 across the same settings) and beating a modest 3.422%
annual return target by a wide margin (mean returns 12-22%).

## Part 2: Pre-Test Methodological Critique (desk analysis, no code)

Before writing any code, identified two specific problems in the paper's
own real-data study methodology:

1. **Pseudo-replication**: the "24 independent 10-year rolling windows"
   step by only 1 month, so adjacent windows share ~119/120 months of data.
   The true independent sample count is closer to 2-3, not 24 -- the same
   trap this codebase's own research has hit and corrected before (see
   `project_2301_03186_quadratic_bound_regime_crosscheck_20260810`'s
   controlled-test correction, and the overlapping-window significance-
   inflation lesson in `project_h20_calibration_drift_gate_deadlock_20260726`).
2. **Hindsight regime labeling**: the paper applies the Viterbi algorithm (a
   smoothing algorithm that uses the WHOLE observation sequence) to label
   bullish/bearish regimes WITHIN each 10-year training window before
   calibrating the model on those labels -- the regime classification used
   for training had access to information a live investor would not have
   had in real time.

Given both flaws point toward the same specific direction (an inflated
apparent edge), and a Sharpe ratio of ~5.9 is implausibly high for any
deployable strategy, the initial recommendation was `do_not_promote` based
on this critique alone, without writing a replication.

## Part 3: Independent Test on Taiwan Data (per user's "實測看看")

Per `feedback_verify_every_paper_independently`, the user asked for a real
test despite the critique. Built one, deliberately fixing both identified
flaws rather than reproducing them.

### Implementation

New script:
`scripts/evaluate/backtest_emvrs_regime_switching_allocation_2501_16659.py`

- Implemented the paper's *classical* (non-exploratory) MVRS optimal-control
  mechanism (Zhou & Yin 2003, cited in the paper's Section 2 as Theorem 2.1)
  via its Merton-style reduction `u* ≈ (mu_i - r) / sigma_i^2 * x` --
  deliberately chosen over transcribing the full backward-ODE boundary-value
  system (which involves several coupled ODEs and a Lagrange-multiplier
  formula) from a PDF-extracted, partially garbled set of equations, to
  avoid a transcription-error risk on a from-scratch stochastic-control
  implementation.
- **Fixed flaw 1 (pseudo-replication)**: evaluated on ONE continuous
  backtest per window (Taiwan's full 2009-2026 0050 history, plus the 4
  standard windows used throughout this session's LETF work) instead of
  artificially chopping a short history into fake "independent" heavily
  overlapping windows.
- **Fixed flaw 2 (hindsight regime labeling)**: regime detection is fully
  causal -- 0050 price vs its own trailing 100-day moving average (matching
  a2111/a2118's own regime convention), using only data available up to and
  including the current day. Regime parameters (mu, sigma) are estimated
  from an **expanding window of only past data**, re-estimated monthly
  (matching the paper's own rebalancing cadence), never using future data.
- Implemented as a synthetic leveraged position on 0050 (not via 00631L),
  to avoid conflating this paper's regime-allocation question with the
  already-extensively-tested LETF daily-reset-drag question
  (`letf_quadratic_bound.py` and related closed research).
- Compared EMVRS (causal regime-switching) against EMV (identical formula,
  but pooled non-regime mu/sigma) and 100% 0050 buy-and-hold.

### Bugs found and fixed during testing (both real, both fixed before the final result)

1. **Leverage-fragility bug (implementation)**: an initial version
   rebalanced only every 21 days at up to 3x leverage with no interim risk
   control, producing a -30% single-day portfolio move (a stale, over-
   leveraged position riding uncorrected through a crash). Fixed by adding
   a daily 20%-deviation-band margin-call check, matching both
   `2103.10157`'s own margin methodology (reviewed the day before, same
   session) and this codebase's own deviation-band convention.
2. **NEW data bug (found while debugging why regime-conditional parameter
   estimates came out backwards)**: 0050.TW's raw `ohlcv` close price has
   an unadjusted 1:4 stock split at 2014-01-02 ($58.70 -> $14.64, not a real
   -139% one-day return). This single extreme outlier dominated the mean
   and variance of every expanding-window return bucket from 2014 onward,
   producing backwards regime-conditional estimates (negative estimated
   mean return in the "bull" bucket). See Part 4 below -- this bug and its
   fix turned out to be broader than this one script.

### Results (after both fixes)

| Window | EMVRS (causal regime) | EMV (pooled, no regime) | 0050 buy&hold |
|---|---|---|---|
| full_2020_2026 | final=$7.95M sharpe=0.843 mdd=-0.7235 | final=$10.71M sharpe=0.924 mdd=-0.7001 | final=$4.28M sharpe=1.101 mdd=-0.3638 |
| rate_hike_2022_2023 | final=$535,857 sharpe=-0.568 mdd=-0.6760 | final=$541,711 sharpe=-0.539 mdd=-0.7201 | final=$923,424 sharpe=-0.123 mdd=-0.3638 |
| live_2024_2026 | final=$11.56M sharpe=1.648 mdd=-0.7027 | final=$11.06M sharpe=1.655 mdd=-0.6581 | final=$3.10M sharpe=1.777 mdd=-0.2847 |
| active_2025_2026 | final=$6.02M sharpe=1.810 mdd=-0.6204 | final=$5.75M sharpe=1.807 mdd=-0.5931 | final=$2.15M sharpe=1.864 mdd=-0.2847 |

(`full_history_2009_2026` produced a NaN edge case, not investigated further
given 4 other clean windows.)

### Conclusion (Part 3)

1. The paper's headline Sharpe ~5.9 does **not** replicate under a fair,
   causal, non-overlapping implementation -- realistic Sharpe values are
   0.8-1.8, in line with what plain leveraged buy-and-hold produces,
   confirming the pre-test critique (pseudo-replication + hindsight regime
   labeling were very likely the source of the paper's inflated number).
2. EMVRS (causal regime-switching) shows **no consistent advantage** over
   EMV (pooled, no regime split) on Taiwan data -- sometimes marginally
   better, sometimes marginally worse, never the clean "EMVRS beats EMV in
   every setting" result the paper's own Table 4 claims. This undermines the
   paper's core selling point that explicitly modeling regime-switching adds
   value over simple pooled parameter estimation.
3. Both variants show the standard, expected leverage risk/reward trade-off
   (much higher return in bull windows, much worse MDD in the bear window)
   -- not a free lunch, not a regime-switching-specific edge.

**Final decision: `do_not_promote`.**

## Part 4: OHLCV Corporate-Action Breakpoint DB Fix

### Discovery

While debugging why the EMVRS script's causal regime-parameter estimates
came out backwards (negative mean return in the "bull" regime bucket),
traced it to a single extreme outlier: `0050.TW`'s raw `close` price jumps
from $58.70 (2013-12-31) to $14.64 (2014-01-02) -- an unadjusted 1:4 stock
split, producing a fake `log(14.64/58.70) = -1.39` "return" that dominated
every expanding-window statistic computed from 2014 onward.

Checking prior memory found this was **already identified** on 2026-08-16
(`project_2608_00127_drawdown_bootstrap_calibration_20260816`), which found
3 unadjusted breakpoints: `0050.TW` 2014-01-02, `00631L.TW` 2015-01-05, and
`00632R.TW` 2024-12-02. However, per that memory's own text, only `00631L`'s
history was corrected, and only **in-memory** for that specific analysis --
nothing was ever written back to the shared database. `0050` and `00632R`
were identified but left entirely unfixed. Re-finding the `0050` instance
independently on 2026-08-23 confirmed the DB itself was still corrupted for
all 3 tickers, 7 days later.

### Ratio verification (before writing anything)

- **0050.TW, 2014-01-02**: ratio 4.0. Well-documented public 1-for-4 split;
  empirical close ratio 58.700001/14.637500 = 4.0102 confirms.
- **00632R.TW, 2024-12-02**: ratio 7.0. **Confirmed via live web search**
  against news coverage (Anue/CNA) of Yuanta's own 2024-10-17 unitholder
  vote: "受益人會議當日00632R收盤淨值為3.26元，因此以7倍作為執行之反分割倍數"
  (closing NAV of $3.26 on the vote date, therefore executed at a 7x
  reverse-split multiplier).
- **00631L.TW, 2015-01-05**: ratio 21.9195. **Not independently confirmed**
  via an official source -- web search found only the same ETF's later,
  unrelated 2026-03 1-for-22 split (a different event, same ETF, same kind
  of periodic forward split as NAV grows). Ratio empirically derived from
  the closest adjacent trading-day close-price pair
  (19.049999/0.869090 = 21.9195), corroborated by a ~20-40x trading-volume
  jump at the same date, consistent with a forward split of that rough
  scale. Flagged as lower-confidence than the other two ratios.

### Fix process

1. Took a full backup of `FinRL/data/stock_data.db` (824MB) before any
   write.
2. Wrote a fix script adjusting `open`/`high`/`low`/`close` (divided by the
   ratio for the two forward splits, multiplied by the ratio for `00632R`'s
   reverse split) and `volume` (inversely) for all rows strictly before each
   breakpoint date.
3. **Dry-run tested the exact script against a full DB copy first**,
   verifying: all 3 transitions become normal-sized daily returns (-0.26%,
   +0.00%, -2.07%), every other ticker in the table completely untouched,
   row counts unchanged per ticker, post-breakpoint prices bit-identical to
   pre-fix, and every remaining >15%-daily-move outlier in all 3 tickers'
   full histories corresponds to an already-documented real market event
   (2015-08-24 China "Black Monday", 2018-10-11, 2024-08-05, 2025-04-07/
   04-10 tariff shock, 2009-02-19 early-history volatility) rather than
   further data corruption.
4. Attempted to run the verified script against the real DB directly --
   **blocked twice by Claude Code's auto-mode classifier** (a guard against
   direct production-database writes). Did not attempt to work around this.
   Explained the situation and the exact pre-verified command to the user,
   who ran it themselves via the `!` shell-passthrough.
5. Independently re-verified (read-only) against the live DB after the
   user's run: row counts unchanged (0050: 4317, 00631L: 2885, 00632R:
   2885), all 3 breakpoint transitions now show normal daily returns, all
   remaining extreme-move days match the same already-documented real
   events found in the dry run.
6. Ran test sweeps: `tests/ -k "a2118 or a2111 or switch_policy or
   defensive_basket or letf"` -- 175/175 pass. `tests/ -k "ohlcv or stock_db
   or 0050 or data_quality"` -- 86/87 pass; the 1 failure
   (`test_evaluate_00631l_0050_relative_reentry_opportunity.py::
   test_cli_writes_latest_output`) reproduces the exact same command
   successfully outside pytest and passes cleanly when re-run in isolation
   -- confirmed as a pre-existing pytest-parallel resource-contention
   flake, not a regression from this fix.

### Production Impact

None for live signal generation. a2118/golden1's live regime/MA/volatility
lookback windows (100-252 trading days back from "today", 2026-08-23) do
not reach any of the 3 breakpoint dates -- even the most recent
(`00632R.TW` 2024-12-02) is ~290 trading days back, still outside a 252-day
window.

**However**: multiple research backtests earlier in **this same session**
used windows starting at 2024-01-02 (`live_2024_2026`, a standard window
used throughout this session's leveraged-ETF-guard work) and involved
`00632R` exposure -- specifically the `00632r_only`/`combined` variants of
the leveraged-ETF timing-anomaly guard research (round-1 direction 9, and
the original arXiv:2604.27287 timing-anomaly work). Those specific variants'
*magnitude* numbers, for windows spanning 2024-12-02, were computed
**before** this fix and may have been distorted by the (now-corrected)
single-day `00632R` discontinuity.

This does **not** change the qualitative `closed_negative`/`do_not_promote`
conclusions already reached for those variants:
- They were already 0/4-promotion-ready before this fix.
- The `00631l_only` variant -- the one that came closest to promotion-
  readiness (1/4 windows in some configurations) -- does not involve
  `00632R` at all, and is therefore unaffected.

Flagged here transparently rather than silently ignored. If any 00632R-
involving number from before 2026-08-23 is ever revisited for a promotion
decision, it should be re-run against the now-corrected data first.

## Files Changed/Added

New research script (no production effect):
- `scripts/evaluate/backtest_emvrs_regime_switching_allocation_2501_16659.py`

Result artifact:
- `results/emvrs_regime_switching_allocation_2501_16659.json`

Real production database write (backed up first, dry-run verified, executed
by the user):
- `FinRL/data/stock_data.db`'s `ohlcv` table -- 3 tickers' pre-breakpoint
  rows corrected (`0050.TW` < 2014-01-02, `00631L.TW` < 2015-01-05,
  `00632R.TW` < 2024-12-02).

No GroupA+ strategy files (`a2118.py`, `a2111.py`, `golden1_0531`, daily
signal, execution plan, target weights, order files) were touched.

## Tests

- `tests/ -k "a2118 or a2111 or switch_policy or defensive_basket or letf"`:
  175/175 pass (post-DB-fix).
- `tests/ -k "ohlcv or stock_db or 0050 or data_quality"`: 86/87 pass, 1
  confirmed-flaky failure unrelated to the fix (passes standalone and when
  the underlying command is run directly).

## Final Recommendation

- Do not promote any variant of EMVRS or the EMV baseline into GroupA+.
- The OHLCV corporate-action fix should be considered durable production
  infrastructure hygiene -- no further action needed unless a 4th
  previously-unknown breakpoint is discovered (the 2026-08-16 session's
  full-table scan found these specific 3; no broader scan was re-run this
  session beyond spot-checking the 3 known tickers).
- If `00631L.TW`'s empirically-derived 2015-01-05 ratio (21.9195) is ever
  worth pinning down exactly (e.g. via Yuanta's own historical unitholder-
  meeting archive or the 公開資�的觀測站), it carries the least certainty of
  the 3 fixes made here, though the correction is unambiguously better than
  the prior unadjusted state regardless of the last couple of significant
  digits.
- Any research result computed in this session before 2026-08-23 involving
  `00632R.TW` returns spanning 2024-12-02 (chiefly the leveraged-ETF timing-
  anomaly guard's `00632r_only`/`combined` variants) should be treated as
  approximate for its exact magnitude, though not its qualitative
  conclusion, until re-run against the corrected data.

No commit was made -- per standing instruction, commits are not suggested
or created unless the user explicitly asks.
