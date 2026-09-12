# Group A+ review: 2602.03903 regime-weighted conformal VaR

## Source

- File: `C:/Users/isaac/Downloads/2602.03903.pdf`
- Title: `Taming Tail Risk in Financial Markets: Conformal Calibration for Nonstationary Portfolio VaR`
- Version in PDF text: arXiv `2602.03903v3`, dated 2026-08-03

## Paper takeaway

The paper proposes regime-weighted conformal calibration (RWC) for one-sided
VaR. It wraps any base quantile forecaster with an additive safety buffer from
past forecast errors. The weights combine:

- exponential time decay, giving time-weighted conformal calibration (TWC);
- regime similarity using simple market features, primarily realized volatility
  and mean absolute return;
- effective sample size diagnostics, with fallback to TWC when localization is
  too concentrated.

The most relevant point for Group A+ is not a new alpha signal. It is better
calibration of tail-risk warnings under nonstationarity, especially when stress
conditions arrive before a slow base model has adapted.

## Fit with current Group A+

Group A+ already has `group_a_plus/integrations/tail_conformal.py`, which
estimates lower-tail 5d/10d bounds for `00631L.TW` and uses warning-only policy
metadata. A previous ACI enhancement added online adaptive alpha, but it is off
by default and still needs stronger promotion evidence.

2602.03903 is therefore a direct upgrade candidate for that existing guard:

- keep the one-sided lower-tail objective;
- replace hard risk-bucket-only calibration with TWC/RWC shadow calibration;
- report effective sample size and localization reliability;
- compare realized exceedance rates before any production promotion.

## Imported

Implemented a review-only shadow module:

- `group_a_plus/integrations/regime_weighted_tail_conformal.py`
- `scripts/evaluate/build_group_a_plus_regime_weighted_tail_conformal_shadow.py`
- `tests/test_group_a_plus_regime_weighted_tail_conformal.py`

The shadow report writes to:

- `report/group_a_plus/latest/regime_weighted_tail_conformal_shadow.json`
- `report/group_a_plus/regime_weighted_tail_conformal_shadow/history/`

Policy is explicitly `shadow_only_no_weight_change`. The module does not create
orders, block trades, alter target weights, or replace the live tail conformal
guard.

## Not imported

Do not directly import the paper's CRSP U.S. equity results, Basel-style
threshold interpretation, or benchmark ranking into Taiwan ETF trading rules.
Those are validation context, not a Group A+ allocation rule.

Do not promote RWC as live just because it is theoretically appealing. The
kernel can over-localize and reduce effective calibration sample size. For
Group A+, the first usable gate is whether a walk-forward replay shows lower
or more stable 00631L lower-tail exceedance than the current static/ACI
implementation without excessive false warnings.

## Recommendation

Use this as a shadow calibration challenger for the existing tail conformal
diagnostic. The next step is a walk-forward comparison over 2018, 2020, 2022,
and 2024-2026:

- current static bucket conformal;
- existing ACI mode with `gamma=0.005`;
- new TWC fallback;
- new RWC when effective sample size is sufficient.

Promotion should require regime-stratified exceedance improvement, not just a
single lower average breach rate.

## 2026-08-07 walk-forward follow-up

Added:

- `scripts/evaluate/evaluate_group_a_plus_regime_weighted_tail_conformal_walk_forward.py`
- `report/group_a_plus/latest/regime_weighted_tail_conformal_walk_forward.json`

The first 80-date sample showed RWC improving over the current static bucket
baseline but not clearly dominating ACI. I then optimized the replay path to
load `00631L.TW` once and reconstruct the static/ACI/TWC/RWC lower-tail bounds
from precomputed rolling forecasts and residuals.

Completed full replay:

- years: 2018, 2020, 2022, 2024, 2025, 2026;
- trading dates: 1,355;
- nominal alpha: 10%;
- replay mode: `fast_vectorized_single_close_load`.

Full replay breach rates:

- existing static bucket: h5 15.06%, h10 15.79%;
- existing ACI gamma 0.005: h5 12.32%, h10 12.84%;
- paper 2602 TWC: h5 12.47%, h10 13.21%;
- paper 2602 RWC: h5 11.59%, h10 12.47%.

Interpretation: RWC is a real calibration improvement over the static bucket
baseline and modestly improves over ACI in this full replay, especially h5.
However, RWC also raises warning frequency materially: h5 `tail_high_rate`
27.23% and h10 46.05%, versus static h5 3.91% / h10 22.73% and ACI h5 29.59% /
h10 53.43%. This is acceptable for shadow diagnostics, but not enough by itself
to promote a live guard. The remaining question is economic warning cost:
whether fewer breaches justify more frequent `00631L` add-pauses.

## 2026-08-07 warning-cost follow-up

Extended `regime_weighted_tail_conformal_walk_forward.json` with
`warning_cost`, comparing forward outcomes when each method is `tail_high`
versus normal.

Full replay warning-cost highlights:

- paper 2602 RWC h5: warning rows 369 / 1,355; severe MDD <= -8% rate 11.38%
  during warnings vs 9.13% outside warnings, lift +2.25 percentage points;
- paper 2602 RWC h10: warning rows 624 / 1,355; severe MDD <= -8% rate 20.35%
  during warnings vs 19.97% outside warnings, lift only +0.38 percentage
  points;
- RWC warning windows still had positive average forward return: h5 +1.40%,
  h10 +1.76%.

Interpretation: RWC improves conformal calibration, but the warning-cost test
does not yet show strong enough economic selectivity to justify live promotion
as a `00631L` add-pause guard. Its best current use remains shadow validation
and regime-localization diagnostics.

## 2026-08-08 parameter tuning follow-up

Added:

- `scripts/evaluate/sweep_group_a_plus_regime_weighted_tail_conformal_params.py`
- `report/group_a_plus/latest/regime_weighted_tail_conformal_param_sweep.json`
- `report/group_a_plus/regime_weighted_tail_conformal_param_sweep/history/`

The full 18-combination grid was too slow for full-history replay, so the
workflow is:

1. broad 18-combination sample sweep over 120 dates;
2. full-history validation of the best sampled candidate.

The 120-date sample sweep selected:

- half-life: 252;
- bandwidth: 1.5;
- min effective sample size: 60.

Full-history validation of this lower-noise candidate:

- h5 breach rate 12.55%, tail_high_rate 14.02%;
- h10 breach rate 12.92%, tail_high_rate 33.06%;
- h5 severe MDD lift +2.14 percentage points;
- h10 severe MDD lift -1.42 percentage points;
- h10 warning return spread +2.97 percentage points, meaning warning windows
  had better, not worse, average forward return.

Comparison to default RWC (`half_life=126`, `bandwidth=1.0`, ESS 60):

- default RWC has better calibration: h5 11.59%, h10 12.47%;
- tuned candidate has much lower warning frequency: h5 14.02% vs 27.23%,
  h10 33.06% vs 46.05%;
- tuned candidate loses too much h10 warning selectivity.

Tuning conclusion: do not replace default RWC. Keep default RWC as the
calibration challenger. The tuned 252/1.5/60 setting can be kept only as a
lower-noise shadow variant, useful if the next trade-level backtest shows
default RWC pauses too many profitable add windows.

## 2026-08-08 intermediate tuning follow-up

Because 252/1.5/60 reduced warning frequency but hurt h10 warning quality, I
validated three intermediate full-history candidates:

- 126/1.25/60;
- 168/1.25/60;
- 210/1.25/60.

Full-history comparison:

- default 126/1.0/60: best calibration, h5 11.59%, h10 12.47%, but high warning
  frequency h5 27.23%, h10 46.05%;
- 126/1.25/60: h5 11.81%, h10 12.55%, warning frequency h5 27.38%, h10 44.13%,
  and best severe-MDD selectivity in this set: h5 lift +3.29 points, h10 lift
  +1.05 points;
- 168/1.25/60: lower warnings h5 21.25%, h10 41.62%, but h10 severe-MDD lift
  turns negative;
- 210/1.25/60 and 252/1.5/60: quieter, but increasingly weaker h10
  selectivity.

Updated tuning recommendation:

- if the priority is pure VaR calibration: keep default 126/1.0/60;
- if the priority is warning selectivity for severe MDD: keep 126/1.25/60 as
  the best balanced challenger;
- if the priority is low warning frequency: keep 252/1.5/60 as lower-noise
  shadow only.

None of these should be promoted live before trade-level testing.

## 2026-08-08 no-add trade-level shadow

Added:

- `scripts/evaluate/backtest_group_a_plus_rwc_no_add_shadow.py`
- `report/group_a_plus/latest/rwc_no_add_shadow_backtest.json`
- `report/group_a_plus/rwc_no_add_shadow_backtest/history/`

This test assumes each `tail_high` day would otherwise add TWD 100,000 of
`00631L.TW`, then measures the event-level benefit of pausing that add:

`pause_benefit = -100000 * forward_return`.

Positive benefit means the pause avoided a loss. Negative benefit means the
pause missed a gain. This is still shadow/event-level; it does not model
overlapping capital constraints or actual daily add attempts.

Full-history no-add result:

- default 126/1.0/60: combined h5+h10 pause benefit -1,613,044;
- balanced 126/1.25/60: combined h5+h10 pause benefit -1,797,798;
- low-noise 252/1.5/60: combined h5+h10 pause benefit -1,738,719.

Across candidates, paused rows missed gains more often than they avoided
losses. Default RWC missed gains on 59.94% of h10 paused rows and 60.70% of h5
paused rows.

Trade-level conclusion: do not promote RWC as a live `00631L` no-add guard.
RWC is useful as a VaR calibration diagnostic and research overlay, but in this
event-level no-add model it would have paused too many profitable windows.
