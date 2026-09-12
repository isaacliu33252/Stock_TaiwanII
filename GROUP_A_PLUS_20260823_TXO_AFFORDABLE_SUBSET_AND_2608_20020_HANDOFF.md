# GroupA+ 2026-08-23 Handoff: TXO Put Overlay Affordable-Subset Realism Check + arXiv:2608.20020 Review

## Status

Two independent pieces of work, both closed with no production code
changed.

1. **TXO put overlay affordable-subset check** (direct follow-up to
   `2607_00883_txo_put_overlay_pilot_positive_20260819`): `closed_negative`.
   The already-validated overlay's positive result does not survive
   Group A+'s real NAV once fractional contract sizing is replaced with
   real integer TXO contracts.
2. **arXiv:2608.20020** ("The Reconfiguration Premium"): `closed_negative`,
   desk-review only, no backtest run. The paper's own pre-registered
   results rule out the one application Group A+ would need.

---

## Part 1: TXO Put Overlay — Affordable-Subset Realism Check

### Background

`2607_00883_txo_put_overlay_pilot_positive_20260819` is the single
cleanest positive result in the entire research registry: a TXO
(TAIEX index option) 10%-OTM put, rolled every 21 trading days, sized at
1.5%/year of NAV, layered on top of Group A+'s real switch strategy,
passed a full 5-layer robustness validation (single window, 7-year
independent breakdown, premium-budget sensitivity grid, transaction-cost
impact, basis-risk quantification). Full detail:
`GROUP_A_PLUS_20260819_2607_00883_TXO_PUT_OVERLAY_HANDOFF.md`.

That handoff's own Section 12 flagged an unresolved granularity problem:
50 of 77 historical rolls (2020-01-02 to 2026-08-18) round to **0**
theoretical TXO contracts against Group A+'s real NAV ($1,478,056) and
the validated 1.5%/year premium budget, because TAIEX's absolute index
level rose from 12,000-18,000 (2020-2021) to 43,000+ (2026), inflating
point-denominated TXO premiums (NT$50/point/contract) faster than NAV has
grown. The original 5-layer validation's return series was built with a
**fractional premium-budget convention**
(`ret_per_premium * q` in `evaluate_2607_00883_txo_put_overlay_shadow.py`)
that implicitly assumes any fractional slice of a contract can be bought
— an assumption that never surfaces as wrong until real NAV and the real
NT$50/point multiplier are applied.

The user confirmed (`繼續.`) pursuing two follow-ups after this was first
surfaced:
1. Extract the 27/77 "affordable" (>=1 contract) rolls and check whether
   the overlay still helps when realistically constrained to only those.
2. Test whether a cheaper (further-OTM) strike raises the affordable-roll
   fraction enough to matter.

### Method

New script:
`scripts/evaluate/build_txo_put_overlay_affordable_subset_2607_00883.py`.
Reuses `build_txo_put_return_per_premium`, `scale_to_premium_budget`,
`perf_stats`, `ANNUAL_PREMIUM_BUDGET`, `ROLL_EVERY`, `DB_PATH` from
`evaluate_2607_00883_txo_put_overlay_shadow.py` unmodified. Adds a local
`build_price_df_with_roll_dt()` (the upstream function's internal
price_df, with `price`/`bid`/`ask` columns retained — the upstream
function only returns the `roll_dt` column — and the OTM fraction
parameterized so the same code path serves the cheaper-strike test).

For each of the 77 rolls:
- `P0` = entry premium in TAIEX points (first day of the roll window).
- `per_roll_budget_dollars = REAL_NAV * ANNUAL_PREMIUM_BUDGET / (252/ROLL_EVERY)`.
- `theoretical_contracts_exact = per_roll_budget_dollars / (P0 * 50)`.
- `contracts = floor(theoretical_contracts_exact)`; `affordable = contracts >= 1`.

Built a **realistic** hybrid return series: `contracts * 50 * dprice / NAV`
per day, i.e. actual integer-contract dollar P&L as a fraction of NAV,
contributing exactly **0** on unaffordable rolls (skip the hedge, hold
switch-only for that window). Round-trip transaction cost applied only on
rolls actually traded (not on skipped ones, avoiding a cost-double-
counting error). Compared against `switch_alone` and the original
fractional (unrealistic) hybrid.

### Results — affordable-subset realism

```
total rolls=77  affordable(>=1 contract)=27 (35.1%)  unaffordable=50 (64.9%)

switch_alone                     sharpe=1.231  mdd=-30.782%
hybrid_fractional_unrealistic    sharpe=1.257  mdd=-29.784%   <- original (backtest-only) result
hybrid_realistic_gross           sharpe=1.226  mdd=-30.784%
hybrid_realistic_costed          sharpe=1.223  mdd=-30.786%   <- real integer-contract result
```

The realistic (integer-contract) hybrid is **statistically indistinguishable
from switch_alone** (actually a hair worse), while the fractional
convention had shown a genuine improvement. MDD is essentially identical
to switch_alone — no drawdown protection survives the granularity
constraint at real NAV.

Mean premium-dollar coverage ratio (realistic $ actually deployable /
fractional $ the original backtest assumed) is only **27.7%** across all
77 rolls, and even restricted to the 35% of rolls that ARE affordable,
coverage is only **78.9%** (integer-floor rounding loss persists even
when >=1 contract can be bought).

Per-year affordable-roll %:

| year | affordable / total | % |
|---|---|---|
| 2020 | 4/12 | 33.3% |
| 2021 | 9/12 | 75.0% |
| 2022 | 0/11 | **0.0%** |
| 2023 | 11/12 | 91.7% |
| 2024 | 3/11 | 27.3% |
| 2025 | 0/12 | **0.0%** |
| 2026 (through Aug) | 0/7 | **0.0%** |

The two most recent full years — the ones closest to today's actual
deployment scenario — have **zero** affordable rolls.

Episode-level check (ad-hoc, run directly against the saved series, not
saved as a standalone script) confirms this is decisive, not just a
full-window-average artifact:

```
covid_crash_2020:      switch=-22.23%  hybrid_frac=-21.38%  hybrid_realistic=-22.03%
tariff_shock_2025_04:  switch=-4.23%   hybrid_frac=-3.73%   hybrid_realistic=-4.23%  (identical to no-overlay)
bear_2022_full_year:   switch=-20.95%  hybrid_frac=-20.14%  hybrid_realistic=-20.98%
```

The 2025 tariff-shock episode is the sharpest demonstration: the realistic
hybrid's cumulative return is **exactly identical** to switch_alone
(-4.23% both) because 2025 had 0/12 affordable rolls all year — the
overlay contributed literally nothing to a real, recent crisis. COVID
2020 retains partial (not full) benefit since that year was 33%
affordable.

### Results — cheaper-strike sensitivity (2607.00883's own Section 12
"possible way out" option 3, previously unverified)

Reran the same affordability check at 85%/80%/75%-of-spot strikes
(vs. the validated 90%, i.e. progressively further OTM / cheaper
premium):

| strike (% of spot) | mean P0 (pts) | affordable rolls |
|---|---|---|
| 90% (validated design) | 105.4 | 27/77 (35.1%) |
| 85% | 52.5 | 48/77 (62.3%) |
| 80% | 32.6 | 64/77 (83.1%) |
| 75% | 28.2 | 66/77 (85.7%) |

Moving from 10%-OTM to 15%-OTM roughly **doubles** the affordable-roll
fraction — the granularity problem is technically solvable by going
further OTM at the current NAV.

**Important caveat**: only affordability was checked here. The 15-20%-OTM
strike's own hedge quality / risk-return properties were **not**
re-validated — a deeper-OTM put triggers later and protects less than the
validated 10%-OTM design; it is a materially different hedge, and
re-running the full 5-layer validation at a new strike depth was out of
scope for this follow-up.

### Conclusion

`closed_negative` for "the validated 10%-OTM TXO put overlay at Group A+'s
current real NAV." The granularity problem doesn't just shrink the
original positive result — it essentially eliminates it, and does so
specifically in the two years closest to real deployment (2025, 2026: 0%
affordable). If this direction is revisited, the next step is re-running
the full 5-layer validation at a 15-20%-OTM strike (not assuming it
carries over from the 10%-OTM result), since only the affordability side
was checked in this pass.

### Files

- New: `scripts/evaluate/build_txo_put_overlay_affordable_subset_2607_00883.py`
- New: `results/txo_put_overlay_affordable_subset_2607_00883.csv` (per-roll
  affordability detail)
- No production code touched.

### Registry / memory

- `group_a_plus/research_semantic_registry.json`:
  `2607_00883_txo_put_overlay_affordable_subset_realism_check`
- Memory: `project_txo_put_overlay_affordable_subset_20260823.md`

### Where this sits in the broader options-hedging investigation thread

This is the fourth of four independent lines of investigation this
session/segment, all converging on the same root cause:

1. `project_0050_options_liquidity_20260823` — 0050's own options market
   (NY/NYO) has adequate granularity but liquidity too poor to support a
   systematic rolled strategy (32.8% quote availability, median 58.8%
   bid-ask spread on the 5-15%-OTM strikes the strategy would actually
   use).
2. `project_2009_09713_letf_options_arbitrage_20260823` — 00631L/00632R
   have no options market at all (confirmed against TAIFEX's official
   underlying list).
3. `project_2607_27188_txo_rnd_tail_risk_20260823` — TXO-derived
   risk-neutral-density tail risk is wrong-signed as a risk-off trigger
   (+0.254 correlation with forward returns, should be negative).
4. **This document** — TXO's own put-overlay granularity, even though the
   underlying mechanism is validated and TXO is the most liquid option
   product available, breaks down at Group A+'s current NAV scale.

**Conclusion across all four**: Group A+'s current ~NT$1.5M NAV is
mismatched with the granularity/liquidity requirements of every option
instrument checked in the Taiwan market this session. This is a scale
problem, not a mechanism problem — none of the four negative results
argue against the underlying hedging logic, only against executing it at
the current NAV. Meaningful NAV growth, or finding a hedging instrument
not bound by this scale constraint, are the two paths that could reopen
this line.

---

## Part 2: arXiv:2608.20020 Review — "The Reconfiguration Premium"

### Paper

Carvalho, "The Reconfiguration Premium: Co-movement Structure as an
Unspanned Dimension of the Variance Risk Premium" (2026-08-21). Not a
strategy paper — an asset-pricing attribution paper.

### Core method

Measures the rate at which the S&P 500 correlation matrix's
**subdominant** eigenspace (a 3-dimensional subspace spanning modes 2-4,
i.e. explicitly excluding the leading "market mode") rotates between
consecutive 12-month rolling windows, on a 379x430-name monthly panel
(1994-2025). The rotation is quantified as the mean squared sine of the
three principal (Grassmannian) angles between consecutive windows'
subspaces — a measure of how much the market's implicit classification of
"which firms move together" has been rewritten, independent of how much
correlation there is overall.

Finds this rotation rate ("REC") couples to the log variance risk premium
(VIX² vs 12-month equal-weight realized vol²) at `t = +5.40`, is nearly
orthogonal to every level measure of correlation/volatility (max
correlation 0.32 with VIX), and is at most 6.7% spanned by the traded
implied-correlation surface (COR1M/COR3M/DSPX) — a genuinely new, currently
untraded state variable. Mechanism is "prepayment": implied variance rises
on impact when rotation accelerates, realized volatility follows 2-3
quarters later, simulated-null-cleared at every forecast horizon 1-9
months.

Two of the paper's three **pre-registered boundaries**, reported by the
paper itself as closed-negative results:
- **No timing alpha**: three functional forms of scaling exposure to a
  short-variance position by the rotation index (linear tilt, step tilt,
  top-quartile-only) all underperform the unconditional position at equal
  volatility (paired `t = -0.81, -0.94, -2.23`).
- **No crash protection**: the worst 5% of months for a short-variance
  position carry a mean standardized rotation reading of **-0.47** (below
  average), and the index does not track the 2008-2009 crisis
  proportionally at all — its own largest readings fall in ordinary
  months (March 2022, October 2018, etc.), not crisis months.

### Applicability assessment (desk review only — no backtest run)

Two independent reasons were sufficient to close this without
implementation:

1. **Structural mismatch.** The entire method requires a broad
   cross-section (hundreds of names) whose pairwise co-movement
   *classification* can meaningfully rotate — "which firms the market
   currently treats as moving together" is undefined for Group A+'s
   actual trading universe (a handful of ETFs: 0050/00631L/00632R plus a
   small defensive basket). Porting the method would require building an
   entirely separate, large Taiwan-equity cross-sectional correlation
   pipeline (e.g. TAIEX/0050 constituents) whose rotation would describe
   **Taiwan sector rotation**, not anything about the ETFs Group A+
   actually holds — a large new data-infrastructure commitment for a
   feature only indirectly related to Group A+'s positions.
2. **Self-disqualifying boundaries.** Even granting the structural
   mismatch could somehow be bridged, the paper's own pre-registered
   results rule out exactly the two properties Group A+ would need from
   such a feature: a regime-switch/risk-off trigger needs timing alpha
   and/or crash protection, and the paper explicitly demonstrates neither
   exists for this state variable, tested under three functional forms
   on the author's own real data. This is not "untested for this
   application" — it is "tested by the source paper and found not to
   work for this exact application."

### Conclusion

`closed_negative`, no implementation. This distinguishes a genuine
methodological lesson from the session's broader pattern
(`feedback_verify_every_paper_independently`): "verify independently"
means don't blindly reuse a *different* paper's rejection heuristic
against a *new* paper's *different* proposed application (as was
correctly done for 2607.27188 against the 2607.29220 precedent) — it does
not mean re-running a backtest the source paper's own authors already ran
and reported negative, on the exact same question, when the underlying
mechanism (broad-cross-section eigenvector rotation) has no analog in
Group A+'s asset universe to begin with.

### Files

No new script, no production code touched (desk-review only).

### Registry / memory

- `group_a_plus/research_semantic_registry.json`:
  `2608_20020_reconfiguration_premium_correlation_rotation`
- Memory: `project_2608_20020_reconfiguration_premium_20260823.md`
