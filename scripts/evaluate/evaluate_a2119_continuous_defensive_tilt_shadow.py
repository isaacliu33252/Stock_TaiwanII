#!/usr/bin/env python3
"""Shadow-evaluate A21.19: a continuous defensive-tilt alternative to a207's
discrete golden1/defensive/recovery regime switch.

Research-only. Does not touch the active strategy, latest pointer, live
signal, or execution plan.

User-proposed design (2026-07-23 session, following up on the
arXiv:2605.20636v2 continuous-timing-signal review -- see
GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md's final
subsection, which explicitly did NOT recommend importing continuous-score
allocation as a strategy change, only as a validation-methodology idea.
This script is the user's own follow-up proposal to actually test it as a
bounded shadow candidate, which is a different and better-controlled
experiment than a blanket import: it stays inside a2118's own already-used
weight endpoints, is shadow-only, and gets a no-trade band.):

  risk_score = w1*drawdown_severity + w2*rate_stress + w3*vix_stress
               + w4*tsmc_crowding
  defensive_tilt = tanh(relu(risk_score))
  raw_target = golden1_weights + tilt * (defensive_adj_weights - golden1_weights)
  target weights = regime_floor(raw_target, a207_regime_implied_weights)

2026-07-24 redesign (see GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_
HANDOFF_20260724.md's root-cause section): the original mechanism fully
replaced a207's own discrete regime decision -- `build_continuous_targets`
never read `frame["execution_regime"]` at all, so a slow-to-react VIX-only
tilt stayed at full golden1 exposure throughout the entire 2020-02-18..
2020-03-27 COVID crash descent while a207's own price-reactive switch had
already, correctly, gone defensive. Fixed by `_apply_regime_floor`: each
day, the continuous blend is capped to never be more risk-on, ticker by
ticker, than whatever a207's own regime-implied weights already are that
day (min on risk-on tickers, max on defensive tickers, then renormalize).
a207's regime is now a floor the continuous tilt can only add
defensiveness on top of, never override in the risk-on direction. Pass
--no-regime-floor to reproduce the old (regime-blind) behavior.

Deviation from the user's original 5-term sketch: `credit_stress` is
dropped. This project has no real credit-spread data source (no BAA/10Y,
no HY/IG OAS -- confirmed by grep across scripts/fetch/*.py) for Taiwan or
US markets; fabricating a proxy would violate this project's real-data-only
convention. If credit data is ever added, w5 can be reinstated.

`defensive_adj_weights` is not a made-up endpoint -- it's the real
production `bond30_cash30` defensive basket
(backtest_group_a_plus_defensive_basket.py: 0050=40%, 00679B=30%, cash=30%,
00631L=0%) with exactly one deliberate change: 00631L's floor is raised
from 0% to 10%, per the user's explicit request to soften the current
regime switch's hard cutoff to zero. `golden1_weights` is read live from
each day's actual `report["base_weights"]["golden1"]` (from run_a2118),
not hardcoded.

Component signals (all real, fetched data -- no fabricated series):
  drawdown_severity = clip(-frame["drawdown"], 0, None), z-scored
  rate_stress        = z(21d change in ^TNX, external_market_ohlcv)
  vix_stress         = z(252d percentile rank of ^VIX close)
  tsmc_crowding      = z(2330.TW 5d return - ex-TSMC-proxy 5d return of 0050),
                        mirrors daily_signal.py::_tsmc_0050_health_snapshot's
                        existing ex-TSMC decomposition, vectorized here
                        instead of called per-day for backtest speed.

w1..w4 default to equal weight (0.25 each) -- NOT tuned. Per the
2026-07-23 validation checklist (GROUP_A_PLUS_SIGNAL_VALIDATION_
CHECKLIST_20260723.md), this script reports the main aligned window,
walk-forward-expanding OOS (2017-2019 backfill panel window), and a
5-crisis independence check is a documented follow-up, not yet run here --
see the checklist's item 3 for how to extend this script with it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    _simulate_daily_target_weights,
    _targets_from_report,
)

PANEL_00631L = "results/ncf_00631l_panel_latest_20260716.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2119_continuous_defensive_tilt_shadow_latest.json"
# 2026-07-24: VIX-only, per the 07-23 IC check (GROUP_A_PLUS_A2119_CONTINUOUS_
# DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md) -- only vix_stress had the
# correct sign and by far the strongest IC over the tested windows;
# rate_stress and tsmc_crowding were sign-flipped in this sample, so equal
# weighting was diluting the one real signal. This was the config actually
# used for the by-window results table in that handoff, but had previously
# only been run via ad hoc overrides, never persisted here -- fixed so the
# default reproduces what was actually validated.
DEFAULT_WEIGHTS = {
    "w1_drawdown": 0.0,
    "w2_rate": 0.0,
    "w3_vix": 1.0,
    "w4_tsmc": 0.0,
    "w5_crowding": 0.0,
    "w6_credit": 0.0,
}
MIN_00631L_FLOOR = 0.10  # deliberate deviation from bond30_cash30's 0.0 floor, per user request
RISK_ON_TICKERS = ("0050.TW", "00631L.TW")  # higher weight = more risk-on
DEFENSIVE_TICKERS = ("00632R.TW", "00679B.TWO", "cash")  # higher weight = more defensive


def _zscore(s: pd.Series, window: int = 756) -> pd.Series:
    mean = s.rolling(window, min_periods=60).mean()
    std = s.rolling(window, min_periods=60).std()
    return ((s - mean) / std.replace(0.0, np.nan)).fillna(0.0)


def _load_external_series(db_path: Path, ticker: str, index: pd.DatetimeIndex) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close FROM external_market_ohlcv
            WHERE provider = 'yfinance' AND ticker = ? AND close IS NOT NULL
            ORDER BY dt
            """,
            [ticker],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    s = rows.set_index("dt")["close"].reindex(index).ffill()
    return s


def _load_local_close_series(db_path: Path, ticker: str, index: pd.DatetimeIndex) -> pd.Series:
    """Same source table as backtest_group_a_plus_defensive_basket.py's
    _load_total_return_prices (local `ohlcv`, not the US-ticker
    `external_market_ohlcv` table _load_external_series reads from) -- for
    Taiwan-listed tickers like 00679B.TWO that aren't in the yfinance
    external table.
    """
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND close IS NOT NULL ORDER BY dt",
            [ticker],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].reindex(index).ffill()


def _extend_index_with_warmup(idx: pd.DatetimeIndex, db_path: Path, warmup_days: int) -> pd.DatetimeIndex:
    """2026-07-25 (addendum #9/#10): prepend up to `warmup_days` real trading
    dates before idx[0], sourced from ^VIX's own date range (the same table
    _load_external_series reads from, and the ticker with the longest history
    of anything this script uses). Addendum #9 found that any `evaluate()`
    call whose own requested window is shorter than `_zscore`'s
    `min_periods=60` cannot show any tilt divergence at all -- every
    external-series-derived z-scored component (vix_stress, credit_stress,
    rate_stress) degenerates to its `.fillna(0.0)` fallback for virtually the
    whole window, since there is no in-window history to standardize
    against. This does not fix `drawdown_severity`/`growth_crowding`/
    `tsmc_crowding` (they depend on `frame["drawdown"]`/`frame["0050_close"]`,
    which are bounded by whatever window `run_a2118()` itself was called
    with -- extending those would require re-running run_a2118 over a longer
    window too, a bigger change deliberately out of scope here) -- it only
    warms up the components sourced purely from external series
    (`_load_external_series`/`_load_local_close_series`), which is
    sufficient for the vix_stress/credit_stress investigation this was built
    for.
    """
    if warmup_days <= 0:
        return idx
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT dt FROM external_market_ohlcv
            WHERE provider = 'yfinance' AND ticker = '^VIX' AND dt < ?
            ORDER BY dt DESC LIMIT ?
            """,
            [str(idx[0].date()), warmup_days],
        ).fetchdf()
    finally:
        con.close()
    warmup_dates = pd.DatetimeIndex(pd.to_datetime(rows["dt"])).sort_values()
    return warmup_dates.union(idx)


def build_defensive_tilt(
    frame: pd.DataFrame,
    db_path: Path,
    *,
    weights: dict[str, float] = DEFAULT_WEIGHTS,
    fast_recovery_momentum_min: float | None = None,
    fast_recovery_ma_gap_min: float | None = None,
    fast_recovery_hold_days: int = 0,
    tilt_update_freq_days: int = 1,
    warmup_days: int = 0,
) -> pd.DataFrame:
    """warmup_days (2026-07-25): see `_extend_index_with_warmup`'s docstring.
    **Default 0 (no warmup extension) to exactly preserve every prior
    addendum's numbers** -- every existing z-scored component was, and by
    default still is, computed expanding-from-the-window's-own-start (so
    even long windows were never using a full mature 756-day lookback
    unless the window itself exceeded ~756 trading days; changing this
    silently would have shifted every previously-reported number, not just
    short/degenerate ones -- confirmed by testing warmup_days=756 against
    the established 2024-2026 baseline: ann_d moved from -5.41% to -8.73%,
    i.e. a real, non-trivial difference, not a no-op for already-long
    windows). Pass warmup_days=756 (matching `_zscore`'s own rolling
    window) explicitly and only when specifically testing whether a short
    sub-window's result changes once given genuine pre-window history --
    the exact addendum #9 question -- and always compare it against a
    warmup_days=0 run of the *same* window as the relevant baseline, not
    against a different window's warmup_days=0 result.

    tilt_update_freq_days (2026-07-25): addendum #4/#5's other open
    thread (GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_
    20260724.md) -- unlike the no-trade band (which delays *execution* of
    the already-computed target, including the regime floor's effect, and
    was tested and rejected in addendum #5), this reduces how often the raw
    VIX-driven `defensive_tilt` signal itself is recomputed, holding it flat
    between updates (e.g. every 5 trading days = weekly). The regime floor
    in `build_continuous_targets` is applied separately, per day, directly
    against a207's own daily regime -- so crash-day protection is preserved
    regardless of how stale the tilt itself is; only the discretionary,
    VIX-chasing part of the turnover should be reduced. `fast_recovery`
    checks the raw signal every day regardless of this setting, since it is
    itself a safety override, not the base signal. Default 1 (no change,
    daily) preserves prior behavior.

    fast_recovery_momentum_min/fast_recovery_ma_gap_min (2026-07-24):
    mirrors backtest_group_a_plus_switch_policy.py's momentum_fast_exit_min /
    momentum_fast_exit_ma_gap_min (the 2020 COVID switch-rule fix). Added
    after the 2020 backtest showed defensive_tilt losing on every metric
    (see GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_
    20260724.md) -- the hypothesis was that VIX stays elevated well after a
    V-shaped price recovery has already started, so a pure-VIX tilt gets
    stuck defensive too long.

    2026-07-24 correction: a single-day override (matching a207's discrete
    regime, which flips state once and stays flipped) does nothing for a
    continuous signal -- confirmed empirically: even when the single-day
    override fired on 2020-03-26, the VIX-driven risk_score simply pushed
    defensive_tilt right back up the next day, and 2020's backtest metrics
    were unchanged to the last decimal. `fast_recovery_hold_days` adds the
    missing persistence: once the momentum/ma_gap co-condition fires on day
    D, defensive_tilt is forced to 0 for D through D+hold_days-1 inclusive
    (a rolling forward-fill of the trigger flag), not just day D. Default 0
    preserves the old (single-day, effectively inert) behavior.
    """
    idx = frame.index
    calc_idx = _extend_index_with_warmup(idx, db_path, warmup_days)
    drawdown_severity = _zscore(frame["drawdown"].clip(upper=0.0) * -1.0)

    tnx = _load_external_series(db_path, "^TNX", calc_idx)
    rate_stress = _zscore(tnx.diff(21)).reindex(idx)

    vix = _load_external_series(db_path, "^VIX", calc_idx)
    vix_percentile = vix.rolling(252, min_periods=60).rank(pct=True)
    vix_stress = _zscore(vix_percentile.fillna(0.5)).reindex(idx)

    tsm = _load_external_series(db_path, "2330.TW", idx)
    close_0050 = frame["0050_close"] if "0050_close" in frame.columns else None
    tsmc_crowding = pd.Series(0.0, index=idx)
    if close_0050 is not None:
        ret_2330_5d = tsm.pct_change(5)
        ret_0050_5d = close_0050.pct_change(5)
        tsmc_weight_assumption = 0.30
        ex_tsmc_proxy_5d = (ret_0050_5d - tsmc_weight_assumption * ret_2330_5d) / (1.0 - tsmc_weight_assumption)
        tsmc_crowding = _zscore((ret_2330_5d - ex_tsmc_proxy_5d).fillna(0.0))

    # 2026-07-25: growth-crowding penalty, testing arXiv:2605.20636v2's
    # "penalize when a trend has run far and VIX is complacently low"
    # component -- GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md
    # flagged this as "noted, not acted on" and philosophically opposite to
    # a207/a2118's own ma_gap_bull_threshold logic (see ncf.py's module
    # docstring: that threshold is now effectively disabled at 0.40 because
    # NCF was empirically found MORE reliable in extended bull markets, not
    # less -- the opposite conclusion from "extended trend = crowded = risk").
    # Faithful reconstruction: 126-trading-day trailing relative return of
    # the risk-on leg (0050.TW) over the defensive leg (00679B.TWO, the bond
    # ETF actually used in the defensive_adj basket below), z-scored. Higher
    # = growth has outrun defensive further = more "crowded" per the paper's
    # framing.
    close_00679b = _load_local_close_series(db_path, "00679B.TWO", idx)
    if close_0050 is not None:
        rel_outperf_126d = close_0050.pct_change(126) - close_00679b.pct_change(126)
        growth_crowding = _zscore(rel_outperf_126d.fillna(0.0))
    else:
        growth_crowding = pd.Series(0.0, index=idx)

    # 2026-07-25: credit_stress, testing arXiv:2607.06117v1's ("Relief-Gated
    # Relative Rotation for QQQ-DIA Allocation") HYG-SHY credit-relief
    # construction -- this project's own credit_stress term was previously
    # dropped (see the module-level history above and
    # GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md's
    # original 07-23 section) for lack of a real BAA/10Y or HY OAS data
    # source. HYG (high-yield corporate bond ETF) minus SHY (1-3yr Treasury
    # ETF) 21-day relative return is real, ordinary yfinance data (fetched
    # 2026-07-25 via scripts/fetch/fetch_cross_market_ohlcv.py --tickers
    # HYG,SHY) and is the paper's actual credit-relief/credit-stress
    # construction. `credit_relief` = rising HYG-vs-SHY = improving credit
    # appetite = risk-on; this component uses `credit_stress` (its negative)
    # so the sign convention matches every other term here (positive =
    # more defensive contribution).
    hyg = _load_external_series(db_path, "HYG", calc_idx)
    shy = _load_external_series(db_path, "SHY", calc_idx)
    credit_relief_raw = hyg.pct_change(21) - shy.pct_change(21)
    credit_stress = _zscore((-credit_relief_raw).fillna(0.0)).reindex(idx)

    risk_score = (
        weights["w1_drawdown"] * drawdown_severity
        + weights["w2_rate"] * rate_stress
        + weights["w3_vix"] * vix_stress
        + weights["w4_tsmc"] * tsmc_crowding
        + weights.get("w5_crowding", 0.0) * growth_crowding
        + weights.get("w6_credit", 0.0) * credit_stress
    )
    # 2026-07-23 design fix: NOT 0.5*(1+tanh(risk_score)). Z-scored inputs are
    # mean-zero over their own rolling history by construction, so a score
    # centered at 0.5 spends ~half its time "defensive-leaning" regardless of
    # actual market regime -- correct for the source paper's symmetric G-vs-D
    # style-rotation problem (a genuine 50/50 prior), wrong for a207's
    # asymmetric regime problem (golden1/risk-on is the normal state most of
    # the time; defensive is a rare event). tanh(relu(risk_score)) floors at
    # 0 (golden1-like) in calm conditions and only rises toward 1 (defensive)
    # when the combined signal is genuinely elevated above its own baseline.
    defensive_tilt = np.tanh(risk_score.clip(lower=0.0))

    if tilt_update_freq_days > 1:
        update_mask = pd.Series(np.arange(len(idx)) % tilt_update_freq_days == 0, index=idx)
        defensive_tilt = defensive_tilt.where(update_mask).ffill().fillna(defensive_tilt.iloc[0])

    fast_recovery_active = pd.Series(False, index=idx)
    if fast_recovery_momentum_min is not None and "exit_momentum" in frame.columns:
        momentum_ok = frame["exit_momentum"] >= fast_recovery_momentum_min
        if fast_recovery_ma_gap_min is not None and "ma_gap" in frame.columns:
            ma_gap_ok = frame["ma_gap"] >= fast_recovery_ma_gap_min
        else:
            ma_gap_ok = pd.Series(True, index=idx)
        trigger_day = (momentum_ok & ma_gap_ok).reindex(idx).fillna(False)
        if fast_recovery_hold_days > 0:
            # A standard backward-looking rolling max is what we want here:
            # for day d, "was there a trigger in [d-hold+1, d]?" is exactly
            # "propagate today's trigger hold_days-1 days into the future"
            # when read across consecutive days. (An earlier version of this
            # used a reversed rolling window intending the same thing and
            # got the direction backwards -- propagated into the past
            # instead. Verified via direct inspection around 2020-03-26.)
            fast_recovery_active = trigger_day.rolling(fast_recovery_hold_days, min_periods=1).max().astype(bool)
        else:
            fast_recovery_active = trigger_day
        defensive_tilt = defensive_tilt.where(~fast_recovery_active, 0.0)

    return pd.DataFrame(
        {
            "drawdown_severity": drawdown_severity,
            "rate_stress": rate_stress,
            "vix_stress": vix_stress,
            "tsmc_crowding": tsmc_crowding,
            "growth_crowding": growth_crowding,
            "credit_stress": credit_stress,
            "risk_score": risk_score,
            "fast_recovery_active": fast_recovery_active,
            "defensive_tilt": defensive_tilt,
        },
        index=idx,
    )


def _apply_no_trade_band(targets: pd.DataFrame, ticker: str, band: float) -> pd.DataFrame:
    """2026-07-25: the trigger condition uses `band - 1e-9` rather than a bare
    `>= band` to avoid a real floating-point boundary bug found while
    sweeping wider bands on the 2020 COVID window -- a207's regime-implied
    weights move in clean round-number increments (e.g. 0050.TW 0.5->0.4 on
    the 02-18 regime flip), so a band exactly equal to a real drift magnitude
    (band=0.10 against a 0.5->0.4 move) computed `abs(0.4-0.5)
    ==0.09999999999999998 < 0.10` and silently never executed the trade for
    the rest of the window it was tested on -- the regime-floor's entire
    protective effect for that ticker was lost for a reason unrelated to the
    band's intended economic trade-off. See
    GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md's
    2026-07-25 addendum.
    """
    if band <= 0.0:
        return targets
    out = targets.copy()
    last_executed = None
    for dt in out.index:
        target_val = float(out.loc[dt, ticker])
        if last_executed is None or abs(target_val - last_executed) >= band - 1e-9:
            last_executed = target_val
        else:
            drift = target_val - last_executed
            out.loc[dt, ticker] = last_executed
            if "cash" in out.columns:
                out.loc[dt, "cash"] = float(out.loc[dt, "cash"]) + drift
    return out


def _apply_regime_floor(row: dict[str, float], a207_row: dict[str, float]) -> dict[str, float]:
    """2026-07-24 redesign (see GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_
    SHADOW_HANDOFF_20260724.md's root-cause section): `build_continuous_targets`
    used to ignore `frame["execution_regime"]` entirely, so a VIX-only tilt
    could keep the portfolio at full golden1 exposure while a207's own
    discrete regime had already, correctly, gone defensive (this is exactly
    what happened throughout the 2020-02-18..2020-03-27 COVID crash).

    Fix: never let the continuous blend be *more* risk-on than whatever
    a207's own regime-implied weights already are for that day, per ticker
    -- take the more conservative (more defensive) of the two on each
    risk-on ticker (min) and each defensive ticker (max), then renormalize.
    This makes a207's discrete regime a floor the continuous mechanism can
    add defensiveness on top of, but never override in the risk-on
    direction -- it cannot fix a207 being too conservative, only stop the
    continuous tilt from being blind to a207 being defensive.
    """
    out = dict(row)
    for ticker in RISK_ON_TICKERS:
        out[ticker] = min(float(row.get(ticker, 0.0)), float(a207_row.get(ticker, 0.0)))
    for ticker in DEFENSIVE_TICKERS:
        out[ticker] = max(float(row.get(ticker, 0.0)), float(a207_row.get(ticker, 0.0)))
    total = sum(out.values())
    if total > 0:
        out = {key: value / total for key, value in out.items()}
    return out


def build_continuous_targets(
    frame: pd.DataFrame,
    tilt_frame: pd.DataFrame,
    report: dict[str, Any],
    a207_weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    golden1 = {key: float(value) for key, value in report["base_weights"]["golden1"].items()}
    defensive_adj = dict(_normalize(DEFENSIVE_BASKETS["bond30_cash30"]))
    freed_from_cash = MIN_00631L_FLOOR - float(defensive_adj.get("00631L.TW", 0.0))
    defensive_adj["00631L.TW"] = MIN_00631L_FLOOR
    defensive_adj["cash"] = float(defensive_adj.get("cash", 0.0)) - freed_from_cash

    rows: list[dict[str, float]] = []
    floor_active: list[bool] = []
    for dt in frame.index:
        tilt = float(tilt_frame.loc[dt, "defensive_tilt"]) if dt in tilt_frame.index else 0.0
        row = {
            key: golden1.get(key, 0.0) + tilt * (defensive_adj.get(key, 0.0) - golden1.get(key, 0.0))
            for key in (*TICKERS, "cash")
        }
        if a207_weights is not None and dt in a207_weights.index:
            a207_row = {key: float(a207_weights.loc[dt, key]) for key in (*TICKERS, "cash")}
            floored_row = _apply_regime_floor(row, a207_row)
            floor_active.append(
                any(abs(floored_row[key] - row[key]) > 1e-9 for key in (*TICKERS, "cash"))
            )
            row = floored_row
        else:
            floor_active.append(False)
        rows.append(row)
    result = pd.DataFrame(rows, index=frame.index)
    result.attrs["regime_floor_active_days"] = int(sum(floor_active))
    return result


def evaluate(
    *,
    start: str,
    end: str,
    initial_value: float,
    db_path: Path,
    no_trade_band: float,
    fast_recovery_momentum_min: float | None = None,
    fast_recovery_ma_gap_min: float | None = None,
    fast_recovery_hold_days: int = 0,
    apply_regime_floor: bool = True,
    cost_multiplier: float = 1.0,
    tilt_update_freq_days: int = 1,
    weights: dict[str, float] | None = None,
    warmup_days: int = 0,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=str(PROJECT_ROOT / PANEL_00631L),
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    total_return_prices, _dividend_coverage = _load_total_return_prices(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report)

    tilt_frame = build_defensive_tilt(
        frame,
        db_path,
        weights=weights if weights is not None else DEFAULT_WEIGHTS,
        fast_recovery_momentum_min=fast_recovery_momentum_min,
        fast_recovery_ma_gap_min=fast_recovery_ma_gap_min,
        fast_recovery_hold_days=fast_recovery_hold_days,
        tilt_update_freq_days=tilt_update_freq_days,
        warmup_days=warmup_days,
    )
    continuous_targets = build_continuous_targets(
        frame,
        tilt_frame,
        report,
        a207_weights=baseline_targets if apply_regime_floor else None,
    )
    continuous_targets_banded = _apply_no_trade_band(continuous_targets, "00631L.TW", no_trade_band)
    continuous_targets_banded = _apply_no_trade_band(continuous_targets_banded, "0050.TW", no_trade_band)
    continuous_targets_banded = _apply_no_trade_band(continuous_targets_banded, "00679B.TWO", no_trade_band)

    commission_rate = 0.001425 * cost_multiplier
    slippage_rate = 0.0005 * cost_multiplier
    equity_etf_sell_tax = 0.001 * cost_multiplier
    baseline_curve, baseline_execution = _simulate_daily_target_weights(
        total_return_prices, baseline_targets, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax
    )
    continuous_curve, continuous_execution = _simulate_daily_target_weights(
        total_return_prices,
        continuous_targets_banded,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    continuous_metrics = _metrics(continuous_curve, initial_value)

    return {
        "schema_version": 1,
        "experiment": "a2119_continuous_defensive_tilt_shadow",
        "research_only": True,
        "production_effect": "none",
        "context": "User-proposed 2026-07-23 follow-up to the arXiv:2605.20636v2 review: bounded continuous alternative to a207's discrete golden1/defensive/recovery switch, staying within a2118's own already-used weight endpoints (golden1 vs bond30_cash30 with 00631L floor raised 0%->10%). credit_stress term dropped (no real data source); w1-w4 are equal-weight, NOT tuned -- this is a first-pass mechanism check, not a promotion candidate.",
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "no_trade_band": no_trade_band,
        "weights_used": weights if weights is not None else DEFAULT_WEIGHTS,
        "min_00631l_floor": MIN_00631L_FLOOR,
        "apply_regime_floor": apply_regime_floor,
        "regime_floor_active_days": int(continuous_targets.attrs.get("regime_floor_active_days", 0)),
        "cost_multiplier": cost_multiplier,
        "tilt_update_freq_days": tilt_update_freq_days,
        "warmup_days": warmup_days,
        "baseline_metrics": baseline_metrics,
        "continuous_metrics": continuous_metrics,
        "metric_deltas": {
            key: round(float(continuous_metrics[key]) - float(baseline_metrics[key]), 6)
            for key in ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
            if key in baseline_metrics and key in continuous_metrics
        },
        "baseline_execution": baseline_execution,
        "continuous_execution": continuous_execution,
        "defensive_tilt_stats": {
            "mean": float(tilt_frame["defensive_tilt"].mean()),
            "std": float(tilt_frame["defensive_tilt"].std()),
            "min": float(tilt_frame["defensive_tilt"].min()),
            "max": float(tilt_frame["defensive_tilt"].max()),
            "days_above_0.5": int((tilt_frame["defensive_tilt"] > 0.5).sum()),
            "fast_recovery_override_days": int(tilt_frame["fast_recovery_active"].sum()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--no-trade-band", type=float, default=0.005)
    parser.add_argument(
        "--fast-recovery-momentum-min",
        type=float,
        default=None,
        help="Mirrors momentum_fast_exit_min: force defensive_tilt to 0 once exit_momentum clears this. Default None (disabled).",
    )
    parser.add_argument(
        "--fast-recovery-ma-gap-min",
        type=float,
        default=None,
        help="Mirrors momentum_fast_exit_ma_gap_min: required co-condition for the fast-recovery override.",
    )
    parser.add_argument(
        "--no-regime-floor",
        action="store_true",
        help=(
            "Disable the 2026-07-24 regime-floor fix (never let the continuous "
            "tilt be more risk-on than a207's own discrete regime that day). "
            "Off by default so the fix is on; pass this flag to reproduce the "
            "old regime-blind behavior for comparison."
        ),
    )
    parser.add_argument(
        "--cost-multiplier",
        type=float,
        default=1.0,
        help="Scales commission/slippage/tax rates equally on both legs. 1.0 = current real assumptions.",
    )
    parser.add_argument(
        "--tilt-update-freq-days",
        type=int,
        default=1,
        help="Recompute defensive_tilt only every N trading days, holding flat between updates (1 = daily, no change). The regime floor still applies daily regardless.",
    )
    parser.add_argument(
        "--warmup-days",
        type=int,
        default=0,
        help="Trading days of pre-window history to fetch for external-series z-scores (vix_stress/credit_stress/rate_stress). Default 0 = exactly reproduces every pre-addendum-#10 result. Pass 756 (matching _zscore's own window) only when specifically testing a short sub-window's result with genuine warmup.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    end = args.end
    if end == "latest":
        end = pd.Timestamp.now().strftime("%Y-%m-%d")

    result = evaluate(
        start=args.start,
        end=end,
        initial_value=args.initial_value,
        db_path=Path(args.db),
        no_trade_band=args.no_trade_band,
        fast_recovery_momentum_min=args.fast_recovery_momentum_min,
        fast_recovery_ma_gap_min=args.fast_recovery_ma_gap_min,
        apply_regime_floor=not args.no_regime_floor,
        cost_multiplier=args.cost_multiplier,
        tilt_update_freq_days=args.tilt_update_freq_days,
        warmup_days=args.warmup_days,
    )
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Output: {Path(args.output).resolve()}")
    print(json.dumps(result["metric_deltas"], ensure_ascii=False, indent=2))
    print(json.dumps(result["defensive_tilt_stats"], ensure_ascii=False, indent=2))
    print(
        f"apply_regime_floor={result['apply_regime_floor']} "
        f"regime_floor_active_days={result['regime_floor_active_days']}"
    )


if __name__ == "__main__":
    main()
