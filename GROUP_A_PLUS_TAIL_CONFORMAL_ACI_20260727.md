# Tail-Conformal ACI Enhancement (arXiv:2606.18199) — 2026-07-27

## Status

**Built, tested, calibration-quality OOS-validated -- but NOT recommended
for adoption yet, pending two further checks.** This is the fourth
paper-review thread in this same multi-day session (after 00631L<->0050
relative rotation, VIX relief-gate, and trough re-entry -- all of which
concluded "don't build/pursue further"). This one found a real,
measurable calibration gap in an *already-live, already-blocking*
production guard (Part 2), and built a small, additive, calibration-
quality-OOS-validated fix for it (Part 3). Added
`adaptive`/`aci_gamma`/`aci_min_alpha`/`aci_max_alpha` parameters to
`group_a_plus/integrations/tail_conformal.py`'s
`compute_tail_conformal_diagnostic()`, all **off by default** -- no
production behavior changed. 4 new tests, all passing; no regression in
the existing `execution_guard.py`-wired call path (which never passes
`adaptive=True`).

**However, Part 4 (the user's follow-up "導入?" / "adopt?" question)
found something that overrides a simple "yes, adopt it": the corrected,
full 2017-2026 blocking-frequency replay shows adaptive mode would push
block rates to 58% of 2020 and 100% of 2022 (vs static's 4.5% and 82.5%),
and separately found the *existing* static method already blocks 100% of
2023 -- both need real economic/historical verification before any
adoption decision. See Part 4 for the full reasoning and the explicit
"do not adopt now" recommendation.**

**Part 5 (2026-07-27, later same day) resolves the "most urgent open
follow-up" flagged at the end of Part 4: it was a framing error, not a
real production problem.** The 82.5%/100% 2022/2023 "block rate" numbers
could never have reflected real historical guard behavior -- `git log -S`
confirms `tail_conformal` was only wired into `daily_signal.py`/
`execution_guard.py` on **2026-07-16** (commit `88c7002`), so production
had no such guard at all in 2022/2023. More importantly, **even today**,
this guard has never functioned as a real automatic block: per the
2026-07-23 audit (`project_advisory_guard_auto_block_fix_20260723`),
`execution_plan.py`'s `--enforce-advisory-pre-trade-guards` defaults to
`False` -- both the volatility-gate guard and `tail_conformal`'s alert
(they share `apply_volatility_gate_pre_trade_guard`) are downgraded to
`flagged_advisory_only` with the full recommended target kept for manual
review, never silently auto-blocked. Confirmed directly against the live
`report/group_a_plus/latest/execution_plan.json`:
`"advisory_pre_trade_guards_enforced": false`, `"blocked_guard_names": []`.
**Nothing has ever been auto-blocked in real production** -- the
calibration-quality conclusion (adaptive closer to nominal exceedance in
most years) is unaffected and still holds; only the "should we be alarmed
about real historical blocking" question is resolved, and the answer is
no. See `project_tail_conformal_aci_20260727` (memory) for the full
resolution write-up; no new code was written for Part 5, pure
investigation.

## Origin

User proposed a new module `group_a_plus/integrations/conformal_tail_warning.py`
inspired by arXiv:2606.18199 ("Conformal Prediction Intervals with
Tail-Specific Guarantees"), describing it as "regime-weighted conformal
risk control" using "time-decay and regime-similarity calibration" to
produce one-sided VaR bounds, explicitly scoped warning-only (pause new
00631L adds / raise manual review / trigger trough_nowcast -- never
automatic de-risking, learning from today's earlier "already-failed
research line" pattern).

## Part 1: grounding (background research fork, read-only)

### 1a. The paper does not contain "regime-weighted" calibration

Read the full 52-page PDF (`/mnt/c/Users/isaac/Downloads/2606.18199v1.pdf`).
"Regime-weighted" / "time-decay + regime-similarity" is **not** the
paper's method -- it appears exactly once, in the Conclusion, as a
suggestion for *future work*, citing other authors (Tibshirani, Schmitt
2024) for someone else to eventually build. The user's framing described
a mechanism the paper's own authors say doesn't exist yet.

What the paper actually built: separate finite-sample-valid one-sided
conformal intervals per tail (a modified quantile conformity score),
intersected into a two-sided interval. Under exchangeability the guarantee
is finite-sample; under non-exchangeability (real financial time series),
validity is only asymptotic, achieved via **DtACI** (Dynamically-tuned
Adaptive Conformal Inference -- an online, multi-candidate-learning-rate
aggregation scheme with regret bounds, aggregating several parallel `gamma`
values via a Hedge-style weighting rather than a fixed rate). Financial
validation: SPY (2018-2025), TQQQ/XLE (2019-2021, covering COVID), base
model GARCH(1,1)-t. Finding: **GARCH VaR and classical two-sided conformal
prediction both show systematic undercoverage on the lower tail**; the
one-sided/tail-specific + DtACI combination achieves the closest alignment
to the nominal target.

### 1b. The proposed module already exists, and is already a blocking guard

`group_a_plus/integrations/tail_conformal.py` (203 lines, pre-existing)
already does exactly this: "Tail-specific conformal diagnostics for
GroupA+ crash warnings... warning-first." Computes lower-tail forward
return bounds and forward-drawdown probability for `00631L.TW` over 5d/10d
horizons via classical split-conformal (empirical quantile of rolling
residuals, bucketed by a 3-level risk regime -- "normal"/"elevated"/
"severe" -- with an all-buckets fallback if the matching bucket has too
few samples). **It is not diagnostic-only in production** -- it is one of
4 blocking pre-trade guards wired into `execution_guard.py`
(`GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md` item
#5), with reason codes `tail_conformal_blocks_new_00631l_exposure` /
`tail_conformal_no_00631l_add` already implementing exactly the "pause new
00631L adds" permission the user proposed as new.

**Verdict communicated to the user**: don't build a new module -- this
one already exists and already has more authority (blocking, not just
diagnostic) than the proposal assumed. The one genuinely new idea from the
paper (DtACI-style online adaptive calibration, replacing the existing
static rolling-window approach) would be a real, non-duplicative
enhancement *to the existing module*, worth checking whether it's
actually needed first.

## Part 2: confirming the gap is real (2020 replay)

`compute_tail_conformal_diagnostic()` depends only on real OHLCV price
history (no NCF panel dependency), so it can be replayed for any
historical date directly. Replayed every trading day of 2020 (COVID
crash) using the *existing* static calibration, comparing the predicted
lower-tail bound each day against the realized forward return:

```
h5:  n=233, nominal_alpha=0.10, empirical_exceedance_rate=0.1502
h10: n=233, nominal_alpha=0.10, empirical_exceedance_rate=0.1502
  MDD<=-8% (h5):  mean_predicted_prob=0.0528, realized_freq=0.0944  (~2x underestimate)
  MDD<=-8% (h10): mean_predicted_prob=0.1155, realized_freq=0.1760

By risk bucket (h5):
  elevated: n=41, exceedance=0.2683   <- worst, ~2.7x the 10% nominal target
  normal:   n=122, exceedance=0.1311
  severe:   n=70, exceedance=0.1143
```

This directly confirms the paper's core concern applies to this specific,
already-live module: real undercoverage, worst specifically in the
"elevated" bucket -- the regime-transition period where the rolling
calibration window hasn't yet absorbed the new (crisis) regime's residual
distribution. This is a genuine, quantified gap, not a hypothetical one.

## Part 3: building and tuning a single-rate ACI enhancement

### 3a. Implementation

Added `_walk_forward_aci_alpha()` -- online-adaptive miscoverage-level
tracking per the classical (Gibbs & Candès, 2021) ACI update:
`alpha_{t+1} = clip(alpha_t + gamma*(base_alpha - err_t), min_alpha,
max_alpha)`, where `err_t=1` if the previous day's lower bound was
breached. This is a **scoped, single-fixed-rate** version -- not the
paper's actual DtACI (which aggregates several candidate gammas via a
Hedge-style online-learning scheme); building that fuller multi-rate
aggregation was not attempted this pass, noted below under "not done."

Wired into `compute_tail_conformal_diagnostic()` via `adaptive: bool =
False` (default preserves prior behavior exactly), `aci_gamma`,
`aci_min_alpha` (0.02), `aci_max_alpha` (0.40). When enabled, replaces the
bucket-conditional calibration entirely for that call (ACI's whole point
is not needing an explicit regime label -- it self-adjusts from realized
miscoverage feedback).

### 3b. First attempt (`gamma=0.05`) made coverage *worse*

Replayed 2020 with `adaptive=True, aci_gamma=0.05`: h5 exceedance rose to
**16.31%** (worse than static's 15.02%); h10 rose to **19.31%** (worse
than static's 15.02%). Inspected the `effective_alpha` trajectory: it
swung between 0.02 and 0.255, well above the 0.10 nominal target for long
stretches. **Root cause**: with a fast learning rate, `alpha_t` drifts
upward substantially during the many calm (non-breach) days that
naturally dominate any period (breaches are ~10-15% of days by
definition), so by the time a real regime shift begins, `alpha_t` has
already drifted well above target -- making the interval *less*
conservative exactly when more conservatism is needed, and it takes
several breach-days to correct back down. This is precisely the
lag/instability problem the paper's actual DtACI (multi-rate aggregation)
exists to mitigate; a single fixed fast rate does not.

### 3c. Slower rates tested on the same 2020 window

```
gamma=0.05:  h5 exceedance=0.1631  (worse than static's 0.1502)
gamma=0.02:  h5 exceedance=0.1416  (slightly better)
gamma=0.01:  h5 exceedance=0.1288  (better)
gamma=0.005: h5 exceedance=0.1159  (best; mean_alpha=0.0705, std=0.0201)
```

By this point, four gamma values had been tried against the *same* 2020
window -- explicitly recognized as crossing this project's own
established threshold for requiring an out-of-sample check before
claiming improvement (see `feedback_overfitting_fixed_window_tuning`
memory entry: "more than 2-3 rounds of tuning against the same window(s)
requires an OOS check"). Rather than picking `gamma=0.005` and stopping,
proceeded to validate it against a genuinely different year.

### 3d. Out-of-sample validation (2018, not used to pick gamma)

```
                  2018 h5 exceedance   2018 h10 exceedance
static:                0.1447               0.1574
aci (gamma=0.005):     0.1404               0.1404
```

**Real, if modest, improvement on both horizons, on a year that played no
role in selecting `gamma`.** Neither method reaches the nominal 10% target
in either year (both still meaningfully undercover), but the adaptive
version is consistently closer, never worse, across two independent
years and both horizons tested. This is treated as a genuine (not
overfit) finding specifically *because* the gamma choice was locked in
before this check, and the check used a different year.

### 3e. Default changed, tests added

Set `aci_gamma` default to **0.005** (was 0.05, the untested first guess)
in the function signature, with the full reasoning (including the failed
faster-rate attempt) documented in the function's own docstring so a
future reader isn't tempted to "fix" it back toward a faster, more
intuitive-seeming rate. 4 new tests in
`tests/test_group_a_plus_tail_conformal.py`: adaptive-mode output shape
(`effective_alpha`/`calibration_scope` reported correctly), a synthetic
test confirming `_walk_forward_aci_alpha` genuinely tightens after a
forced run of breaches and relaxes afterward, and a warmup-defaults-to-
base-alpha check. `pytest tests/ -k "tail_conformal or execution_guard"`:
15/15 passing (4 new + 11 pre-existing, including all `execution_guard`
tests -- confirming the production call path, which never sets
`adaptive=True`, is unaffected).

## Part 4: user asked "導入?" (adopt into production?) -- one methodology bug caught before answering

Before recommending production adoption, tried to (a) extend validation
from 2 years (2018, 2020) to the full 2017-2026 sample, and (b) check the
actual *blocking-decision* frequency (not just calibration exceedance
rate) under static vs adaptive, since `tail_conformal` is a live blocking
guard and better raw calibration doesn't automatically mean better
blocking decisions.

### 4a. A real bug in the fast-path replay script (caught before trusting it)

Wrote a faster replay script that loaded `00631L.TW` close prices **once**
for the full 2009-2026 history to avoid repeated DB round-trips (the
per-day-call approach in Part 3 is slow: ~0.3-0.4s/call). This produced a
seemingly-clean 9-year table (aggregate: static h5 exceedance 11.18% ->
adaptive 10.65%; h10 11.90% -> 11.02%) and, separately, a blocking-frequency
comparison showing implausible numbers -- `2020: static_blocked_days=0`
(0.0%, despite 2020 being the COVID crash the calibration gap was found
in) and `2023: static_blocked_days=239` (100.0%, every single day of the
year).

100% block-rate for an entire year is not plausible for a live guard (it
would mean every 00631L addition was blocked all year, contradicting
other work done today confirming continued 00631L activity through 2023).
Spot-checked directly against the real function
(`compute_tail_conformal_diagnostic`) for `2020-03-20`: real output
`calibration_count=118`, `lower_tail_residual_quantile=0.091`,
`lower=-0.0806` (correctly triggers `TAIL_RISK_HIGH`); the fast-path
script's hand-rolled version of the same computation gave
`cal_resid count=231` (roughly double), `q_static=0.069`,
`lower=-0.0585` (does not trigger).

**Root cause**: `compute_tail_conformal_diagnostic` loads only
`actual_date - max(900, calibration_window*5)` days of history (~3.45
years) before each call -- i.e., production's own calibration pool is
deliberately bounded to roughly the trailing 3.5 years, not "all
available history." The fast-path script loaded the *entire* 2009-2026
series once and reused it for every test date, so its calibration pool
for a 2020 test date could reach back to 2016 or earlier (including the
2015-2016 China-market-crash "severe" days) -- a materially different,
larger calibration pool than production ever actually sees on any given
day. **This invalidates the 9-year aggregate table above and the
blocking-frequency numbers describing 0%/100% block rates -- neither was
computed the way production actually behaves.**

The Part 3 numbers (2018/2020 exceedance rates) remain valid -- those were
computed by calling the real function directly, per day, with no
shortcuts.

### 4b. Correct (slow) full re-run -- results

Re-ran the full 2017-2026 x (static, adaptive) x (exceedance rate,
blocking frequency) comparison calling `compute_tail_conformal_diagnostic`
directly for every day (matching production's actual bounded-lookback
behavior exactly, no shortcuts -- ~2 calls/day x ~2,200 days, background,
~20+ minutes). Results:

```
year        n     static_blocked   adaptive_blocked   agree   static_only  adaptive_only  | h5_exceed static/adapt  | h10_exceed static/adapt
2017      245     0  (0.0%)          0  (0.0%)        100.0%      0            0          | 0.045 / 0.110           | 0.057 / 0.127
2018      245    49  (20.0%)        51  (20.8%)         99.2%      0            2          | 0.139 / 0.135           | 0.151 / 0.135
2019      241    52  (21.6%)        76  (31.5%)         75.1%     18           42          | 0.054 / 0.066           | 0.066 / 0.083
2020      245    11  (4.5%)        142  (58.0%)         46.5%      0          131          | 0.143 / 0.110           | 0.143 / 0.118
2021      243    27  (11.1%)        95  (39.1%)         66.3%      7           75          | 0.160 / 0.115           | 0.148 / 0.132
2022      246   203  (82.5%)       246 (100.0%)         82.5%      0           43          | 0.138 / 0.106           | 0.183 / 0.114
2023      239   239 (100.0%)       104  (43.5%)         43.5%    135            0          | 0.013 / 0.084           | 0.004 / 0.079
2024      242    65  (26.9%)        99  (40.9%)         64.5%     26           60          | 0.128 / 0.128           | 0.124 / 0.140
2025_2026 377    74  (19.6%)       200  (53.1%)         66.6%      0          126          | 0.172 / 0.118           | 0.158 / 0.139
```

**The calibration-quality finding from Parts 2-3 holds up under the
corrected methodology**: adaptive is closer to the 10% nominal exceedance
target than static in the clear majority of year x horizon combinations
(especially 2020, 2021, 2022, 2023, 2025-2026), confirming that
conclusion was not an artifact of the earlier bug.

**But a new, more urgent finding emerged from the corrected blocking-
frequency numbers, and it changes the recommendation.** Both
configurations show extreme, possibly-alarming block rates in specific
years:
- `covid_2020`: static blocks only **4.5%** of days; adaptive blocks
  **58.0%** -- a massive absolute increase in how often new 00631L
  exposure would be blocked during the exact year this whole
  investigation centers on.
- `2022`: static already blocks **82.5%** of the year; adaptive pushes
  this to **100.0%** -- every single day.
- `2023`: static blocks **100.0%** of the entire year (`static_only=135`
  days where static blocks but adaptive doesn't) -- confirmed via the
  correct, no-shortcut methodology, so this is not the Part 4a artifact
  recurring; if this matches real historical guard behavior, it means
  the *existing, already-live* static method has been continuously
  blocking new 00631L exposure for an entire calendar year in this
  replay.

**Recommendation given to the user: do not adopt adaptive mode into
`execution_guard.py` now.** Two independent reasons:
1. Switching to adaptive would substantially *increase* absolute blocking
   frequency in exactly the years where blocking has the largest
   opportunity cost (a 58%-of-year block rate in 2020, 100% in 2022) --
   better raw probability calibration does not by itself establish that
   *more aggressive blocking* is the right trade-off; that requires a
   portfolio-level economic backtest (Sharpe/return/drawdown impact of
   the actual blocking decisions), which was not done this session.
2. The *existing* static method's own block rates in 2022 (82.5%) and
   2023 (100%) are surprising enough to need independent verification
   against real historical `execution_guard.py` decisions/logs before
   trusting anything built on top of it -- either this genuinely reflects
   how the live guard has behaved (a much larger, pre-existing, and more
   urgent issue than anything about ACI), or there is some other
   mechanism (override, different real-world inputs, a guard that is
   advisory rather than strictly enforced in some path) reconciling this
   with the fact that 00631L exposure changes did happen during those
   years per other work done today and in prior sessions. **This
   verification was not done this session** -- flagged as the single
   most important open follow-up from this entire thread, more urgent
   than the ACI adoption question itself.

## Part 5 (later, same day): resolving the "most important open follow-up"

Picked up the exact question Part 4 flagged as unresolved and most urgent:
does the existing static method really block 82.5% (2022) / 100% (2023) of
trading days in real production?

**Step 1 -- when was this guard actually wired into production?**

```bash
git log --follow --diff-filter=A -- group_a_plus/integrations/tail_conformal.py
git log -S "compute_tail_conformal_diagnostic" --oneline -- group_a_plus/operations/daily_signal.py
git log -S "_tail_conformal_alert" --oneline -- group_a_plus/operations/execution_guard.py
```

All three point to the same commit: `88c7002` ("Upload 2026-07-16 full
project state..."). **`tail_conformal` has been live in production for
11 days (2026-07-16 to today), not since 2022 or 2023.** The 82.5%/100%
numbers from Part 4b are a replay of today's diagnostic function against
historical price data -- a useful calibration-quality check, but they
cannot represent real historical guard decisions for years the guard did
not exist in.

**Step 2 -- but does the guard actually auto-block trades even today?**

Read `group_a_plus/operations/execution_guard.py` and
`group_a_plus/operations/execution_plan.py` directly.
`apply_volatility_gate_pre_trade_guard()` (`execution_guard.py:91-170`)
handles both the volatility-gate alert *and* the tail_conformal alert
through the same code path (`_tail_conformal_alert()` is checked inside
it, `execution_guard.py:31-43,110-118`) -- it only actually zeroes out a
buy (`status: "blocked"`, `blocked_trades: [...]`) when
`target_shares > current_shares` for `00631L.TW` on that specific day.

But per the 2026-07-23 audit
(`project_advisory_guard_auto_block_fix_20260723`, code at
`execution_plan.py:659-679`), when
`enforce_advisory_pre_trade_guards=False` (the CLI default --
`execution_plan.py:846-852`, `action="store_true", default=False`), both
this guard and the compounding-regime guard are downgraded before they
ever reach a real trade: `status` becomes `"flagged_advisory_only"`,
`blocked_trades` is cleared, and the *full* recommended target is kept for
manual review (`review_note: "Advisory only: full target kept for manual
review instead of being auto-blocked."`). The comment at
`execution_plan.py:660-662` explains why: "All orders are placed manually
(no automated execution exists yet), so these two guards were designed to
be a human-review prompt, not an automatic block."

Confirmed against the live production file, not just the code path:

```bash
python3 -c "
import json
d = json.load(open('report/group_a_plus/latest/execution_plan.json'))['data']
print(d['advisory_pre_trade_guards_enforced'])   # -> False
print(d['guard_impact_summary']['blocked_guard_names'])  # -> []
"
```

**Conclusion: the 82.5%/100% figures never represented, and could never
have represented, an actual blocked trade.** Two independent reasons
stack: (1) the guard did not exist in production in 2022/2023 at all, and
(2) even now that it exists, it has been advisory-only by explicit design
since 2026-07-23 -- nothing in this codebase currently auto-blocks a
00631L addition. This is *more* reassuring than Part 4's speculative "or
there is some other mechanism... reconciling this" note -- the mechanism
is real, documented, and intentional, not a guess.

**What is unaffected**: the calibration-quality finding (Part 3 -- adaptive
mode tracks the 10% nominal exceedance rate more closely than static in
most year x horizon combinations) stands unchanged. Only the "should we be
alarmed about real historical over-blocking" question is resolved, and the
answer is no. The adaptive-vs-static *adoption* decision (Part 4's actual
recommendation: don't adopt yet, pending a real portfolio-level economic
backtest of the blocking decisions) is unchanged by this -- Part 5 removes
a false alarm, it does not supply new evidence either for or against
adoption.

No code was changed in Part 5 -- pure investigation, read-only.

## What was NOT done

- **(Resolved 2026-07-27, Part 5 above -- retained here for history)**
  ~~Most important, highest-priority follow-up: independently verify
  whether the existing static method's 82.5% (2022) / 100% (2023) block
  rates match real historical `execution_guard.py` decisions/logs. Not
  done this session -- this is more urgent than the ACI adoption question
  itself, since it concerns *currently-live* production behavior, not a
  proposed change.~~
- **No portfolio-level economic backtest of the blocking decisions
  themselves** (Sharpe/return/drawdown impact of actually blocking on the
  static vs adaptive high-tail days) -- only calibration quality
  (exceedance rate vs nominal) and raw blocking frequency were measured.
  Needed before any adoption decision, per Part 4b.
- **Full DtACI (multi-candidate-gamma Hedge aggregation) was not built.**
  This is a single, fixed learning rate -- the paper's actual contribution
  is a scheme that runs several candidate gammas in parallel and
  aggregates them online, which should be more robust across different
  "speeds" of regime change than any single fixed rate can be (as directly
  demonstrated by 3b's failure at gamma=0.05 vs 3c-3d's success at
  0.005 -- a single rate that works for one regime-change speed may not
  for another). Building this fuller version is the natural next step if
  this line is pursued further.
- **Not wired into `execution_guard.py` with `adaptive=True`.** The
  existing blocking guard still uses the static calibration by default;
  switching it to adaptive mode is a real production behavior change and
  was left for the user to decide, not made unilaterally.
- **Per-bucket ACI was not attempted** -- the adaptive mode ignores the
  risk-bucket dimension entirely (by design, since ACI's premise is not
  needing an explicit regime label). Whether a hybrid (separate ACI state
  per bucket) would do even better was not tested.
- Only 00631L.TW / 5d+10d horizons were checked (matching the existing
  module's scope) -- no other tickers or horizons tested.
- The `min_alpha`/`max_alpha` clip bounds (0.02/0.40) were not tuned --
  kept at the first reasonable-seeming values; a tighter `max_alpha`
  might further reduce the drift-during-calm-periods problem that made
  `gamma=0.05` fail, but this wasn't explored to avoid a fifth round of
  same-window tuning.

## Reproduction commands

```bash
python3 -m pytest tests/test_group_a_plus_tail_conformal.py -q
python3 -m pytest tests/ -k "tail_conformal or execution_guard" -q

python3 -c "
import sys; sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from group_a_plus.integrations.tail_conformal import compute_tail_conformal_diagnostic, _load_close, _forward_return
from backtest_group_a_plus_switch_policy import DB_PATH

TICKER = '00631L.TW'
close = _load_close(DB_PATH, TICKER, pd.Timestamp('2009-01-01'), pd.Timestamp('2019-06-30'))
fwd_ret5 = _forward_return(close, 5)
test_dates = close.loc['2018-01-02':'2018-12-15'].index
for label, kw in (('static', dict(adaptive=False)), ('aci', dict(adaptive=True, aci_gamma=0.005))):
    rows = []
    for dt in test_dates:
        diag = compute_tail_conformal_diagnostic(db_path=Path(DB_PATH), actual_date=dt, ticker=TICKER, **kw)
        if diag.get('status') != 'ok':
            continue
        d = diag['diagnostics']['h5']
        rows.append({'lb': d['lower_tail_confidence_bound'], 'ret': fwd_ret5.get(dt)})
    df = pd.DataFrame(rows).dropna()
    print(label, (df['ret'] < df['lb']).mean())
"
```

**Full 2017-2026 x static/adaptive x (exceedance, blocking-frequency)
re-run (Part 4b)**: loop the same pattern as above over each of the 9
year windows already used throughout this session (2017_bull ..
2025_2026, see `GROUP_A_PLUS_TROUGH_REENTRY_2509_05922_REVIEW_AND_SAMPLE_EXPANSION_20260727.md`
for the exact date ranges), calling `compute_tail_conformal_diagnostic`
directly per day for both `adaptive=False` and `adaptive=True` (no
shortcuts -- see 4a for why a faster, single-load-then-reuse
reimplementation gives wrong numbers), and additionally comparing
`diag["state"] == "TAIL_RISK_HIGH"` between the two configurations per
day to get real blocking-frequency agreement/disagreement counts, not
just exceedance-rate quality.

## Files referenced

Modified this session:
- `group_a_plus/integrations/tail_conformal.py` -- added
  `_walk_forward_aci_alpha()`, and `adaptive`/`aci_gamma`/`aci_min_alpha`/
  `aci_max_alpha` parameters to `compute_tail_conformal_diagnostic()`.
  Additive, default off (`adaptive=False`), preserves all prior behavior.
- `tests/test_group_a_plus_tail_conformal.py` -- 4 new tests.

Read/analyzed, not modified:
- `group_a_plus/operations/execution_guard.py` (confirms tail_conformal is
  already a blocking guard, unaffected by this change)
- `/mnt/c/Users/isaac/Downloads/2606.18199v1.pdf` (the reviewed paper)
- `GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md` (item
  #5, documents tail_conformal's existing guard status)
