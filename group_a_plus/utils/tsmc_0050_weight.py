"""Single source of truth for the assumed TSMC (2330) weight within 0050.

Fable audit (2026-07-08, #9): this constant was previously duplicated
separately in group_a_plus/operations/daily_signal.py and ncf_2330.py (same
value, no shared source, free to drift apart). daily_signal.py's ex-TSMC
proxy (`(ret_0050 - w*ret_2330)/(1-w)`) amplifies any bias in `w` by about
1/(1-w) (~2.4x at w=0.5831), feeding directly into the
tsmc_weak_manual_review/narrow_lead alerts and signal_alignment's TSMC vote.

2026-07-10 calibration: fetched real published weight from Yuanta's official
0050 holdings page (https://www.yuantaetfs.com/product/detail/0050/ratio),
dated 2026-07-09 on the source page: TSMC = 58.31%. Updated the constant from
the prior uncalibrated 0.55 guess to 0.5831 and set AS_OF accordingly.

Before using the published figure, tried estimating the weight empirically
via OLS regression of 0050 daily returns on 2330 (external_market_ohlcv)
daily returns -- this came out to 0.74-0.83 across 60/120/252/504-day
windows, badly overstating the true weight (58.31%). Rejected: the naive
single-stock regression coefficient is confounded by the broad market factor
-- other large 0050 constituents (MediaTek, Hon Hai, ...) also move with
2330 via shared market/semiconductor-sector beta, inflating the estimated
beta well above the true portfolio weight. Do not reuse this regression
approach for recalibration; use the official disclosed holdings weight.

TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS=180 still applies: recheck the
Yuanta page (or another disclosed-holdings source) after 180 days rather
than assuming this value stays current indefinitely.
"""

from __future__ import annotations

from datetime import date

TSMC_0050_WEIGHT_ASSUMPTION = 0.5831
TSMC_0050_WEIGHT_ASSUMPTION_AS_OF: str | None = "2026-07-10"
TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS = 180


def tsmc_0050_weight_assumption_is_stale(*, today: date | None = None) -> bool:
    if TSMC_0050_WEIGHT_ASSUMPTION_AS_OF is None:
        return True
    as_of = date.fromisoformat(TSMC_0050_WEIGHT_ASSUMPTION_AS_OF)
    today = today or date.today()
    return (today - as_of).days > TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS
