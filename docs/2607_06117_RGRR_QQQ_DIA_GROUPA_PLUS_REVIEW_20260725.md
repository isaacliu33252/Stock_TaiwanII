# Review: "Relief-Gated Relative Rotation for QQQ-DIA Allocation" (arXiv:2607.06117v1) vs. Group A+

**Reviewed**: 2026-07-25. **Source**: `C:\Users\isaac\Downloads\2607.06117v1.pdf`
(Zheli Xiong, 31 pages, code at
`github.com/shaun19920309/Relief-Gated-Relative-Rotation-for-QQQ-DIA-Allocation`).

## What the paper is

RGRR (Relief-Gated Relative Rotation) is a two-ETF rotation rule between
QQQ (Nasdaq-100) and DIA (Dow Jones). It never touches cash, bonds, or
leverage -- the only decision is the QQQ-vs-DIA weight split. It explicitly
identifies itself as a sequel to the same author's "prior growth-defensive
timing and cash-overlay allocation studies [Xiong(2026a), Xiong(2026b)]" --
almost certainly the same lineage as arXiv:2605.20636v2 ("Continuous
Timing Signals for Growth-Defensive Style Allocation"), the paper this
project already tested exhaustively as the A21.19 shadow candidate (see
`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`).
Same author, same methodological toolkit (HAC-screened states, fixed
signal universe, tanh-mapped continuous weight, walk-forward validation),
applied to a different pair.

**Mechanism**: 1 main effect (`rate_relief`) + 9 second-order interactions
+ 2 third-order interactions, globally screened once via horizon-specific
HAC regressions (t >= 2.0) and 0.95 correlation de-duplication, then held
fixed. Rolling OOS (756-day train, 63-day test blocks) re-selects only the
combination weights (lambdas) on the already-admitted signal groups, never
the signal universe itself. Score maps to weight via
`w = 0.5 + 0.50*tanh(Z(score)/0.75)`, then one-day-lagged and EWMA-smoothed
(`eta=0.05`).

**Results**: Sharpe beats both 100% QQQ and 50/50 QQQ-DIA in every tested
OOS window (2018/2020/2022 starts, plus a 2008-start robustness check).
CAGR beats 50/50 in every window but beats 100% QQQ only in the 2022
window (QQQ is a very strong unconditional benchmark in this sample, so
the paper is explicit that this is "a risk-adjusted relative-allocation
claim, not an unconditional QQQ-replacement claim"). Turnover is
354%-506% annualized -- the paper's own stated main weakness.

## Applicability to Group A+ / a2118

**Not directly importable as a strategy or signal set** -- same root cause
as most non-RL papers reviewed this project (`ma_gap_bull_threshold`
suppression note, `growth_crowding` addendum, etc.): **asset-universe
mismatch**. RGRR's own paper is explicit that "both assets are equity
ETFs. The strategy does not move to cash, bonds, or leverage." Group A+'s
actual action space (0050/00631L/00679B/00632R/cash -- unlevered, 2x
leveraged, bond, inverse, and cash) is a fundamentally different problem
than rotating between two unlevered growth/value equity sleeves. There is
no QQQ-DIA-shaped pair inside Group A+'s book to apply this rule to
literally.

Two genuinely portable takeaways survive the asset-mismatch filter,
however -- both about *method*, not about the trading rule itself.

### 1. The incremental-OOS-admission rule for higher-order interactions -- directly confirms and formalizes something this project found ad hoc just hours ago

RGRR's core methodological contribution is a **second gate specifically
for higher-order (interaction) terms**: passing the global HAC screen is
necessary but not sufficient. A third-order term must *also*: (a) improve
rolling OOS Sharpe versus the simpler main+second-order base, averaged
across the screen windows; (b) have a positive Sharpe delta in at least
2 of 3 screen periods; (c) survive economic-family de-duplication under a
hard complexity cap (max 5 terms). Table 24/25 in the paper show this
matters a lot: **many candidate interactions have large absolute HAC
t-statistics (some > 5 or 7) but *negative* incremental OOS Sharpe once
the simpler base is already present** -- statistically real, portfolio-
harmful.

This is not a hypothetical concern for this project. It is the *exact*
failure mode `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_
HANDOFF_20260724.md`'s 2026-07-25 addendum #7 found a few hours before
this review, by hand, via an ad hoc sweep: `growth_crowding` had a
correctly-signed, statistically real standalone IC (unlike this project's
own earlier-rejected `rate_stress`/`tsmc_crowding`), yet blending it into
the tilt made backtest Sharpe/return **worse** in every window that
matters once the simpler VIX-only base was already present. RGRR's
protocol is a formal, named version of the same discipline applied
retroactively today by hand.

**Recommendation**: add this as an explicit rule to
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` -- something like:
*"a new signal or interaction term that clears its own standalone
statistical/IC screen must still be tested for incremental improvement
against the existing base configuration, in backtest, across multiple
windows, before being added to a live weight -- a real standalone
signal can still make a blended timing rule worse."* This is pure
process, zero implementation risk, and would have let today's
`growth_crowding` result be predicted/required rather than discovered by
running a sweep. Not yet added to the checklist file -- flagged here for
the user to confirm before editing that file, since it's a standing
process document other future sessions will be bound by.

### 2. HYG-SHY as a genuinely fetchable, real credit-relief/credit-stress proxy -- unblocks a previously-closed door

`build_defensive_tilt()`'s own docstring (in
`evaluate_a2119_continuous_defensive_tilt_shadow.py`) explicitly dropped a
`credit_stress` term because "this project has no real BAA/10Y, HY OAS, or
Taiwan-equivalent credit-spread data source (confirmed by grep across
`scripts/fetch/*.py`)." RGRR's `credit_relief`/`credit_stress` states are
built from **`HYG` (high-yield corporate bond ETF) minus `SHY` (1-3yr
Treasury ETF) 21-day relative return** -- two ordinary, liquid, US-listed
ETFs, not a proprietary spread feed. This is real, fetchable data this
project doesn't currently have but easily could: **checked the local DB
(`FinRL/data/stock_data.db`, `external_market_ohlcv` table) -- HYG and SHY
are not present today**, but `scripts/fetch/fetch_cross_market_ohlcv.py`
already has the exact pipeline needed (`DEFAULT_TICKERS = ["^VIX", "SOXX",
"QQQ", "^TWII", "TSM", "TWD=X"]`, yfinance-backed, `--tickers` CLI flag to
add more) -- adding HYG/SHY would be `--tickers ^VIX,SOXX,QQQ,^TWII,TSM,
TWD=X,HYG,SHY` (or a dedicated backfill run), not new pipeline
engineering.

**This directly reopened the door the A21.19 docstring closed for
`credit_stress`.** Tested same-day (user said "繼續" after this review was
delivered): `scripts/fetch/fetch_cross_market_ohlcv.py --tickers HYG,SHY`
backfilled both to `external_market_ohlcv` (2015-01-02..2026-07-24). IC
check (2024-01-02..2026-07-23): fwd20d-maxDD IC=-0.180, p<0.0001 -- the
strongest standalone IC of any non-VIX component tested in this
candidate's history. Backtest (per takeaway #1's incremental-admission
rule, now checklist item 6): blended as a modest additive term on top of
full VIX weight, it improves annual-return and Sharpe delta in 3 of 4
windows tested (2020 COVID, worst rolling fold, 2018 trade war), the first
genuinely positive multi-window result this candidate has produced from
any non-VIX component. **Not yet promoted** -- doesn't clear the full
six-item checklist yet (no walk-forward-rolling, crisis-independence
split, or cost-sensitivity sweep specific to this term). Full detail:
`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`'s
2026-07-25 addendum #8.

### Everything else in the paper: not applicable, same reasons already established in this project

- The turnover finding (354%-506% annualized, "the main practical
  weakness") is a clean cross-validation of this project's own repeated
  finding (A21.19's 6-50x-a207 turnover, addenda #5/#6's rejected
  band/frequency damping attempts) that continuous, interaction-driven
  timing signals reliably generate turnover that erodes much of their
  edge -- not new information, but independent confirmation from a
  different asset pair and a different author's methodology.
- The paper's own honesty about limits (no White Reality Check/Hansen
  SPA/Deflated Sharpe Ratio yet; "a research prototype, not a final
  production anomaly claim") matches how this project has treated the
  whole Xiong lineage so far -- disciplined but explicitly bounded
  evidence, not a result to import on faith.
- `rel_mom126`/`rel_reversal` (QQQ-vs-DIA-specific relative-momentum and
  relative-drawdown states) have no analogue in Group A+'s single-country,
  mostly-single-underlying (TAIEX/0050-tracking) book -- there is no
  second growth sleeve to rotate against.

## Verdict

**No direct strategy import** (confirmed asset-universe mismatch, same
pattern as every non-RL paper reviewed this project to date). **Three
real, actionable process/data/mechanism takeaways, all acted on**: (1)
the incremental-OOS-admission rule for new interaction/signal terms was
added as item 6 to `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`;
(2) HYG/SHY were fetched and a real `credit_stress` signal was built and
tested extensively in A21.19 (see
`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`'s
addenda #8-16 for the full arc -- initial results looked strong, but a
significant methodological correction (a z-score cold-start bias,
addendum #10) walked the verdict back to genuinely mixed, and a follow-on
AND-gate interaction-term variant of the same idea (addenda #13-15)
ultimately traced its own best-looking result to the same class of bias;
net result: not promoted, but a rich methodological trail for whoever
continues this candidate); (3) the paper's correlation-de-duplication
screening step (0.95 threshold) was ported to Group A+'s own NCF feature
pipeline, which had no equivalent layer -- see
`GROUP_A_PLUS_NCF_CORRELATION_DEDUP_HANDOFF_20260725.md` (found and fixed
a real redundant-feature pair, `close_ma200_ratio`/`close_ma200_dist` at
correlation 1.000, opt-in and off by default pending an AUC-impact check).
No production pipeline behavior changed by any of the three -- (1) is
process-only, (2) never left shadow-only A21.19, (3) is opt-in and not
wired into the daily pipeline's actual invocation.
