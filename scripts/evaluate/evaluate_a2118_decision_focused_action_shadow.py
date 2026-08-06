#!/usr/bin/env python3
"""Shadow-evaluate decision-focused finite actions on top of A21.18.

Research-only. This script does not update the active strategy, latest pointer,
live signal, or execution plan.

Instead of predicting returns or drawdowns and hand-writing a rule, it labels a
small finite action set by downstream realized utility relative to KEEP, trains
an expanding-window predictor for each action's regret, and only deviates from
A21.18 when predicted regret clears a positive edge threshold.
"""

from __future__ import annotations

import argparse
import json
import math
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _load_panel, _resolve_end_date
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _metric_delta


PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_decision_focused_action_shadow_latest.json"
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]

DEFAULT_ACTIONS = ("KEEP", "NO_ADD", "CAP10", "REENTER", "REENTER_00631L_5", "REENTER_00631L_10")
FEATURE_COLUMNS = (
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "confidence",
    "ma_gap",
    "total_risk_score",
    "w_0050",
    "w_00631l",
    "ret_0050_5d",
    "ret_00631l_5d",
    "spread_00631l_0050_5d",
)

# Opt-in via --cross-asset-features. Reuses tickers already cached in
# external_market_ohlcv (no new download/pipeline dependency) plus TAIFEX
# foreign futures net OI -- proposed 2026-08-01 as candidate signal for the
# REENTER-starvation problem (see
# [[project_spo_dfl_action_value_already_closed_20260727]]: REENTER never
# wins the KEEP/NO_ADD/CAP10/REENTER regret-argmax on the existing feature
# set; the 2026-07-26/27 rule-based VIX relief-gate fix was tried and
# reversed by 2021 OOS. This is a data-driven alternative attempt, not a
# rule override -- ablate before trusting.
CROSS_ASSET_FEATURE_COLUMNS = (
    "us_tsm_adr_ret",
    "us_soxx_ret",
    "us_nvda_ret",
    "usdtwd_change",
    "tsmc_vs_0050_5d",
    "foreign_futures_net_oi_ratio",
    "dist_from_recent_low_60d",
    "drawdown_recovery_ratio",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _targets_from_report(frame: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for _dt, row in frame.iterrows():
        regime = str(row.get("execution_regime", "golden1"))
        weights = base_weights.get(regime, base_weights.get("group_a_plus_defensive", golden))
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def _cap_00631l_to_cash(weights: dict[str, float], cap: float) -> dict[str, float]:
    out = dict(weights)
    current = float(out.get("00631L.TW", 0.0) or 0.0)
    capped = min(current, float(cap))
    out["00631L.TW"] = capped
    out["cash"] = float(out.get("cash", 0.0) or 0.0) + max(current - capped, 0.0)
    return _normalize(out)


def _cap_00631l_to_0050(weights: dict[str, float], cap: float) -> dict[str, float]:
    out = dict(weights)
    current = float(out.get("00631L.TW", 0.0) or 0.0)
    capped = min(current, float(cap))
    out["00631L.TW"] = capped
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + max(current - capped, 0.0)
    return _normalize(out)


def _parse_reenter_00631l_step(action: str) -> float | None:
    prefix = "REENTER_00631L_"
    if not action.startswith(prefix):
        return None
    try:
        step = float(action.removeprefix(prefix)) / 100.0
    except ValueError as exc:
        raise ValueError(f"Unsupported action: {action}") from exc
    if step <= 0.0:
        raise ValueError(f"Unsupported action: {action}")
    return step


def _partial_reenter_00631l_label(
    baseline_weights: dict[str, float],
    *,
    prior_00631l_weight: float,
    step: float,
) -> dict[str, float]:
    """One-step label proxy for a stateful partial 00631L re-entry action."""

    out = dict(baseline_weights)
    keep_00631l = float(out.get("00631L.TW", 0.0) or 0.0)
    target_00631l = min(keep_00631l, max(0.0, float(prior_00631l_weight)) + float(step))
    excess = max(keep_00631l - target_00631l, 0.0)
    out["00631L.TW"] = target_00631l
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + excess
    return _normalize(out)


def _add_00631l_from_0050_then_cash(
    current: dict[str, float],
    *,
    target_00631l_weight: float,
) -> dict[str, float]:
    out = dict(current)
    current_00631l = float(out.get("00631L.TW", 0.0) or 0.0)
    add = max(float(target_00631l_weight) - current_00631l, 0.0)
    if add <= 0.0:
        return _normalize(out)

    from_0050 = min(add, float(out.get("0050.TW", 0.0) or 0.0))
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) - from_0050
    out["00631L.TW"] = current_00631l + from_0050
    remaining = add - from_0050
    if remaining > 0.0:
        from_cash = min(remaining, float(out.get("cash", 0.0) or 0.0))
        out["cash"] = float(out.get("cash", 0.0) or 0.0) - from_cash
        out["00631L.TW"] = float(out.get("00631L.TW", 0.0) or 0.0) + from_cash
    return _normalize(out)


def _apply_action(
    baseline_weights: dict[str, float],
    *,
    action: str,
    prior_00631l_weight: float,
    cap10: float = 0.10,
) -> dict[str, float]:
    """Map a finite action to target weights.

    KEEP and plain REENTER both use the A21.18 target in one-step labels.
    Step re-entry actions are a proxy for stateful deployment experiments where
    a prior guard left the live portfolio below A21.18.
    """

    if action == "KEEP":
        return _normalize(dict(baseline_weights))
    if action == "REENTER":
        return _normalize(dict(baseline_weights))
    reenter_step = _parse_reenter_00631l_step(action)
    if reenter_step is not None:
        return _partial_reenter_00631l_label(
            baseline_weights,
            prior_00631l_weight=prior_00631l_weight,
            step=reenter_step,
        )
    if action == "NO_ADD":
        return _cap_00631l_to_cash(baseline_weights, max(0.0, float(prior_00631l_weight)))
    if action.startswith("CAP") and action != "CAP10":
        try:
            cap = float(action.removeprefix("CAP")) / 100.0
        except ValueError as exc:
            raise ValueError(f"Unsupported action: {action}") from exc
        return _cap_00631l_to_0050(baseline_weights, cap)
    if action == "CAP10":
        return _cap_00631l_to_0050(baseline_weights, cap10)
    raise ValueError(f"Unsupported action: {action}")


def _portfolio_path_values(
    prices: pd.DataFrame,
    start_pos: int,
    weights: dict[str, float],
    horizon: int,
) -> np.ndarray:
    start = prices.iloc[start_pos]
    shares = {
        ticker: float(weights.get(ticker, 0.0) or 0.0) / max(float(start[ticker]), 1e-12)
        for ticker in TICKERS
    }
    cash = float(weights.get("cash", 0.0) or 0.0)
    vals: list[float] = []
    for offset in range(horizon + 1):
        row = prices.iloc[start_pos + offset]
        vals.append(cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS))
    return np.array(vals, dtype=float)


def _max_drawdown(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    peak = np.maximum.accumulate(values)
    dd = values / np.maximum(peak, 1e-12) - 1.0
    return float(abs(np.min(dd)))


def _utility(
    prices: pd.DataFrame,
    start_pos: int,
    *,
    action_weights: dict[str, float],
    keep_weights: dict[str, float],
    horizon: int,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
) -> dict[str, float]:
    action_values = _portfolio_path_values(prices, start_pos, action_weights, horizon)
    keep_values = _portfolio_path_values(prices, start_pos, keep_weights, horizon)
    action_turnover = sum(
        abs(float(action_weights.get(key, 0.0) or 0.0) - float(keep_weights.get(key, 0.0) or 0.0))
        for key in (*TICKERS, "cash")
    )
    action_mdd = _max_drawdown(action_values)
    keep_mdd = _max_drawdown(keep_values)
    missed_rebound = max(0.0, float(keep_values[-1] - action_values[-1]))
    utility = (
        math.log(max(float(action_values[-1]), 1e-12))
        - lambda_mdd * action_mdd
        - gamma_turnover * action_turnover
        - eta_missed_rebound * missed_rebound
    )
    keep_utility = math.log(max(float(keep_values[-1]), 1e-12)) - lambda_mdd * keep_mdd
    return {
        "utility": float(utility),
        "keep_utility": float(keep_utility),
        "action_regret": float(utility - keep_utility),
        "final_value": float(action_values[-1]),
        "keep_final_value": float(keep_values[-1]),
        "mdd": float(action_mdd),
        "keep_mdd": float(keep_mdd),
        "turnover": float(action_turnover),
        "missed_rebound": float(missed_rebound),
    }


def _build_features(
    frame: pd.DataFrame,
    panel: pd.DataFrame | None,
    target_weights: pd.DataFrame,
    prices: pd.DataFrame,
    cross_asset: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for dt, row in frame.iterrows():
        panel_row = panel.loc[dt] if panel is not None and dt in panel.index else pd.Series(dtype=float)
        price_pos = prices.index.get_loc(dt)
        if isinstance(price_pos, slice):
            price_pos = price_pos.start
        pos = int(price_pos)
        ret_0050_5d = 0.0
        ret_00631l_5d = 0.0
        if pos >= 5:
            ret_0050_5d = float(prices.iloc[pos]["0050.TW"] / prices.iloc[pos - 5]["0050.TW"] - 1.0)
            ret_00631l_5d = float(prices.iloc[pos]["00631L.TW"] / prices.iloc[pos - 5]["00631L.TW"] - 1.0)
        rows.append(
            {
                "prob_up_h1": float(panel_row.get("prob_up_h1", 0.5) or 0.5),
                "prob_up_h5": float(panel_row.get("prob_up_h5", 0.5) or 0.5),
                "prob_up_h20": float(panel_row.get("prob_up_h20", 0.5) or 0.5),
                "prob_fwd_mdd_gt5_h20": float(panel_row.get("prob_fwd_mdd_gt5_h20", 0.0) or 0.0),
                "prob_fwd_gain_gt5_h20": float(panel_row.get("prob_fwd_gain_gt5_h20", 0.5) or 0.5),
                "confidence": float(panel_row.get("confidence", 0.5) or 0.5),
                "ma_gap": float(row.get("ma_gap", 0.0) or 0.0),
                "total_risk_score": float(row.get("total_risk_score", 0.0) or 0.0),
                "w_0050": float(target_weights.loc[dt].get("0050.TW", 0.0) or 0.0),
                "w_00631l": float(target_weights.loc[dt].get("00631L.TW", 0.0) or 0.0),
                "ret_0050_5d": ret_0050_5d,
                "ret_00631l_5d": ret_00631l_5d,
                "spread_00631l_0050_5d": ret_00631l_5d - ret_0050_5d,
            }
        )
    features = pd.DataFrame(rows, index=frame.index)
    if cross_asset is not None:
        features = features.join(cross_asset.reindex(frame.index))
    return features.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _panel_signal_available(index: pd.DatetimeIndex, panel: pd.DataFrame | None) -> pd.Series:
    if panel is None:
        return pd.Series(False, index=index, dtype=bool)
    return pd.Series([dt in panel.index for dt in index], index=index, dtype=bool)


def _vix_relief_signal(
    index: pd.DatetimeIndex,
    vix_close: pd.Series,
    *,
    lookback_days: int = 20,
    relief_ratio: float = 0.85,
) -> pd.Series:
    """Rule-based relief gate: True when VIX has fallen meaningfully (to below
    `relief_ratio` of its own trailing peak) from a recent spike.

    `vix_close` must be indexed by calendar date (raw ^VIX close, not yet
    aligned to the trading calendar). Uses only data available as of the
    prior trading day (T-1, matching this codebase's existing convention for
    other US-market-derived features, e.g. `vix`/`vix_change`/`vix_ma20_ratio`
    in scripts/misc/ncf_00631l.py's EXT_FEATURES) -- no same-day lookahead.
    """
    aligned = vix_close.reindex(vix_close.index.union(index)).sort_index().ffill().reindex(index)
    vix_t1 = aligned.shift(1)
    trailing_peak = vix_t1.rolling(int(lookback_days), min_periods=5).max()
    relief = vix_t1 < float(relief_ratio) * trailing_peak
    return relief.fillna(False)


def _load_vix_close(db_path: Path) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            "SELECT dt, close FROM external_market_ohlcv WHERE ticker = '^VIX' ORDER BY dt"
        ).fetchdf()
    finally:
        con.close()
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame.set_index("dt")["close"].astype(float)


CROSS_ASSET_TICKERS = ("TSM", "SOXX", "NVDA", "TWD=X", "2330.TW")


def _load_cross_asset_market_close(db_path: Path) -> pd.DataFrame:
    """Pivot of cached external_market_ohlcv closes for CROSS_ASSET_TICKERS.

    All five tickers are already cached in this DB (verified back to at
    least 2014-01/03), so this reads existing cache only -- no download.
    """
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            "SELECT dt, ticker, close FROM external_market_ohlcv "
            "WHERE ticker IN (?, ?, ?, ?, ?) ORDER BY dt",
            list(CROSS_ASSET_TICKERS),
        ).fetchdf()
    finally:
        con.close()
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame.pivot(index="dt", columns="ticker", values="close").sort_index()


def _load_foreign_futures_net_ratio(db_path: Path) -> pd.Series:
    """TAIFEX foreign (外資及陸資) TX index futures net OI as a share of
    gross OI (long+short), so the signal is bounded roughly in [-1, 1]
    instead of a raw contract count that trends with market size over the
    multi-year OOS windows this evaluator uses."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            "SELECT dt, open_interest_net, open_interest_long, open_interest_short "
            "FROM taifex_futures_institutional "
            "WHERE contract_code = '臺股期貨' AND institution = '外資及陸資' "
            "ORDER BY dt"
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        return pd.Series(dtype=float)
    frame["dt"] = pd.to_datetime(frame["dt"])
    denom = (frame["open_interest_long"] + frame["open_interest_short"]).replace(0, np.nan)
    ratio = (frame["open_interest_net"] / denom).fillna(0.0)
    return pd.Series(ratio.to_numpy(dtype=float), index=frame["dt"]).sort_index()


def _drawdown_state_features(
    price: pd.Series,
    *,
    recent_low_lookback: int = 60,
    drawdown_lookback: int = 252,
) -> pd.DataFrame:
    """`dist_from_recent_low_60d`: % above the trailing recent_low_lookback-day
    low (0.0 = sitting at the low). `drawdown_recovery_ratio`: fraction of the
    trailing drawdown_lookback-day peak-to-trough range already recovered
    (0.0 = at the trough, 1.0 = back at/above the peak)."""
    roll_low_recent = price.rolling(int(recent_low_lookback), min_periods=5).min()
    dist_from_low = (price / roll_low_recent.replace(0, np.nan) - 1.0).fillna(0.0)
    roll_peak = price.rolling(int(drawdown_lookback), min_periods=20).max()
    roll_low = price.rolling(int(drawdown_lookback), min_periods=20).min()
    denom = (roll_peak - roll_low).replace(0, np.nan)
    recovery_ratio = ((price - roll_low) / denom).clip(lower=0.0, upper=1.0).fillna(0.0)
    return pd.DataFrame(
        {
            "dist_from_recent_low_60d": dist_from_low,
            "drawdown_recovery_ratio": recovery_ratio,
        },
        index=price.index,
    )


def _build_cross_asset_features(
    index: pd.DatetimeIndex,
    market_close: pd.DataFrame,
    foreign_futures_net_ratio: pd.Series,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Aligns cross-asset raw series onto `index` (the evaluation frame's
    trading dates). US-market and USD/TWD series use shift=1 (T-1, matching
    the same overnight-signal convention as scripts/misc/ncf_00631l.py's
    EXT_FEATURES); TSMC-vs-0050 is same-day (both close 1:30pm Taipei);
    foreign futures OI is shift=1 (published after prior close)."""
    union_index = market_close.index.union(index)
    aligned = market_close.reindex(union_index).sort_index().ffill().reindex(index)
    out = pd.DataFrame(index=index)
    for ticker, col in (("TSM", "us_tsm_adr_ret"), ("SOXX", "us_soxx_ret"), ("NVDA", "us_nvda_ret")):
        out[col] = aligned[ticker].pct_change().shift(1) if ticker in aligned.columns else 0.0
    out["usdtwd_change"] = (
        aligned["TWD=X"].pct_change().shift(1) if "TWD=X" in aligned.columns else 0.0
    )
    if "2330.TW" in aligned.columns and "0050.TW" in prices.columns:
        tsmc_close = market_close["2330.TW"].reindex(union_index).sort_index().ffill()
        et50_close = prices["0050.TW"].reindex(union_index).sort_index().ffill()
        tsmc_5d = tsmc_close.pct_change(5).reindex(index)
        et50_5d = et50_close.pct_change(5).reindex(index)
        out["tsmc_vs_0050_5d"] = (tsmc_5d - et50_5d)
    else:
        out["tsmc_vs_0050_5d"] = 0.0
    fut_union = foreign_futures_net_ratio.index.union(index) if not foreign_futures_net_ratio.empty else index
    fut_aligned = (
        foreign_futures_net_ratio.reindex(fut_union).sort_index().ffill().reindex(index).shift(1)
        if not foreign_futures_net_ratio.empty
        else pd.Series(0.0, index=index)
    )
    out["foreign_futures_net_oi_ratio"] = fut_aligned
    if "00631L.TW" in prices.columns:
        dd = _drawdown_state_features(prices["00631L.TW"].reindex(index))
        out = out.join(dd)
    else:
        out["dist_from_recent_low_60d"] = 0.0
        out["drawdown_recovery_ratio"] = 0.0
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _build_action_labels(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    horizon: int,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    cap10: float,
    actions: tuple[str, ...],
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for i, dt in enumerate(target_weights.index):
        if dt not in prices.index or prices.index.get_loc(dt) + horizon >= len(prices):
            continue
        pos = int(prices.index.get_loc(dt))
        keep = _normalize(target_weights.loc[dt].to_dict())
        prior_dt = target_weights.index[max(i - 1, 0)]
        prior_00631l = float(target_weights.loc[prior_dt].get("00631L.TW", 0.0) or 0.0)
        out: dict[str, float] = {}
        for action in actions:
            reenter_step = _parse_reenter_00631l_step(action)
            if reenter_step is not None:
                current = _cap_00631l_to_0050(
                    keep,
                    max(0.0, float(keep.get("00631L.TW", 0.0) or 0.0) - reenter_step),
                )
                action_weights = _add_00631l_from_0050_then_cash(
                    current,
                    target_00631l_weight=min(
                        float(keep.get("00631L.TW", 0.0) or 0.0),
                        float(current.get("00631L.TW", 0.0) or 0.0) + reenter_step,
                    ),
                )
                keep_weights = current
            else:
                action_weights = _apply_action(keep, action=action, prior_00631l_weight=prior_00631l, cap10=cap10)
                keep_weights = keep
            result = _utility(
                prices,
                pos,
                action_weights=action_weights,
                keep_weights=keep_weights,
                horizon=horizon,
                lambda_mdd=lambda_mdd,
                gamma_turnover=gamma_turnover,
                eta_missed_rebound=eta_missed_rebound,
            )
            out[action] = result["action_regret"]
        rows.append(out)
        index.append(dt)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


def _fit_predict_linear(
    train_x: pd.DataFrame,
    train_y: pd.Series,
    test_x: pd.Series,
    *,
    ridge_alpha: float,
) -> float:
    x = train_x.to_numpy(dtype=float)
    y = train_y.to_numpy(dtype=float)
    mask = np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if len(y) < 5:
        return 0.0
    if float(np.nanstd(y)) < 1e-12:
        return float(np.mean(y))
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-8] = 1.0
    xs = (x - mean) / std
    xt = (test_x.to_numpy(dtype=float) - mean) / std
    design = np.column_stack([np.ones(len(xs)), xs])
    penalty = np.eye(design.shape[1]) * float(ridge_alpha)
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    return float(np.r_[1.0, xt] @ beta)


def _predict_action_regrets(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    min_train_days: int,
    train_window_days: int,
    ridge_alpha: float,
    regret_clip: float,
    actions: tuple[str, ...] = DEFAULT_ACTIONS,
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for dt in features.index:
        past_idx = labels.index[labels.index < dt]
        if train_window_days > 0:
            past_idx = past_idx[-int(train_window_days):]
        if len(past_idx) < int(min_train_days):
            rows.append({action: 0.0 for action in actions})
            continue
        train_x = features.loc[past_idx, list(feature_columns)]
        test_x = features.loc[dt, list(feature_columns)]
        row: dict[str, float] = {}
        for action in actions:
            if action not in labels.columns:
                row[action] = 0.0
                continue
            pred = _fit_predict_linear(train_x, labels.loc[past_idx, action], test_x, ridge_alpha=ridge_alpha)
            row[action] = float(np.clip(pred, -float(regret_clip), float(regret_clip)))
        row["KEEP"] = 0.0
        rows.append(row)
    return pd.DataFrame(rows, index=features.index)


def _predict_action_error_percentiles(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    predicted_regrets: pd.DataFrame,
    *,
    min_train_days: int,
    train_window_days: int,
    ridge_alpha: float,
    actions: tuple[str, ...] = DEFAULT_ACTIONS,
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> pd.DataFrame:
    """Meta-model expected action-regret error percentile.

    This is a selective-prediction gate: it estimates whether the current
    action-value prediction sits in a high-error region, using only past
    out-of-sample prediction errors as labels. Lower is more reliable.
    """

    rows: list[dict[str, float]] = []
    for dt in features.index:
        past_idx = labels.index[(labels.index < dt) & (labels.index.isin(predicted_regrets.index))]
        if train_window_days > 0:
            past_idx = past_idx[-int(train_window_days):]
        row: dict[str, float] = {}
        if len(past_idx) < int(min_train_days):
            rows.append({action: 1.0 if action != "KEEP" else 0.0 for action in actions})
            continue
        train_x = features.loc[past_idx, list(feature_columns)]
        test_x = features.loc[dt, list(feature_columns)]
        for action in actions:
            if action == "KEEP":
                row[action] = 0.0
                continue
            if action not in labels.columns or action not in predicted_regrets.columns:
                row[action] = 1.0
                continue
            errors = (predicted_regrets.loc[past_idx, action] - labels.loc[past_idx, action]).abs()
            pred_error = max(
                0.0,
                _fit_predict_linear(train_x, errors, test_x, ridge_alpha=ridge_alpha),
            )
            row[action] = float(np.clip(np.mean(errors.to_numpy(dtype=float) <= pred_error), 0.0, 1.0))
        rows.append(row)
    return pd.DataFrame(rows, index=features.index)


def _build_calibration_pairs(
    labels: pd.DataFrame,
    predicted: pd.DataFrame,
    *,
    min_train_days: int,
    train_window_days: int,
    actions: tuple[str, ...] = DEFAULT_ACTIONS,
    features: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Long-format (date, action, predicted_regret, realized_regret) export.

    Reuses `predicted` (already expanding-window, out-of-sample per date --
    see `_predict_action_regrets`) and `labels` (realized utility-vs-KEEP
    regret, computed with full knowledge of the forward `horizon`) without
    recomputing either. Exists to let a downstream probability-calibration
    model (e.g. `ncf_decision_calibration.py`) train on every historically
    labeled (date, action) pair, not just the small number of days this
    evaluator's own regret-argmax happened to select as non-KEEP.

    A row is only included once this action has cleared the same
    `min_train_days`/`train_window_days` warm-up `_predict_action_regrets`
    itself requires -- otherwise `predicted` is a cold-start 0.0 default,
    not a real prediction, and should not be used to fit or judge a
    calibration.

    `features` (optional): when given, each row also carries that date's
    `total_risk_score` (already a `FEATURE_COLUMNS` entry) so a downstream
    calibration can be conditioned on a risk regime instead of pooling
    every date together -- see 2026-07-27's Phase 2 finding that a single
    global calibration does not transfer out-of-sample for CAP10.
    """

    rows: list[dict[str, Any]] = []
    for dt in predicted.index:
        if dt not in labels.index:
            continue
        past_idx = labels.index[labels.index < dt]
        if train_window_days > 0:
            past_idx = past_idx[-int(train_window_days):]
        if len(past_idx) < int(min_train_days):
            continue
        total_risk_score = None
        if features is not None and dt in features.index:
            total_risk_score = features.loc[dt].get("total_risk_score")
        for action in actions:
            if action == "KEEP":
                continue
            predicted_regret = predicted.loc[dt].get(action)
            realized_regret = labels.loc[dt].get(action)
            if predicted_regret is None or realized_regret is None:
                continue
            if not (math.isfinite(float(predicted_regret)) and math.isfinite(float(realized_regret))):
                continue
            row = {
                "date": str(dt.date()),
                "action": action,
                "predicted_regret": float(predicted_regret),
                "realized_regret": float(realized_regret),
            }
            if total_risk_score is not None:
                row["total_risk_score"] = float(total_risk_score)
            rows.append(row)
    return rows


def _apply_partial_and_turnover_cap(
    keep: dict[str, float],
    action_weights: dict[str, float],
    *,
    adjustment_fraction: float,
    turnover_cap: float,
) -> dict[str, float]:
    frac = min(max(float(adjustment_fraction), 0.0), 1.0)
    adjusted = {
        key: float(keep.get(key, 0.0) or 0.0) + frac * (float(action_weights.get(key, 0.0) or 0.0) - float(keep.get(key, 0.0) or 0.0))
        for key in (*TICKERS, "cash")
    }
    diff = sum(abs(adjusted[key] - float(keep.get(key, 0.0) or 0.0)) for key in (*TICKERS, "cash"))
    if turnover_cap > 0.0 and diff > float(turnover_cap):
        scale = float(turnover_cap) / max(diff, 1e-12)
        adjusted = {
            key: float(keep.get(key, 0.0) or 0.0) + scale * (adjusted[key] - float(keep.get(key, 0.0) or 0.0))
            for key in (*TICKERS, "cash")
        }
    return _normalize(adjusted)


def _select_actions(
    target_weights: pd.DataFrame,
    predicted_regrets: pd.DataFrame,
    *,
    edge_threshold: float,
    regret_clip: float,
    adjustment_fraction: float,
    turnover_cap: float,
    cap10: float,
    action_allowed: pd.Series | None = None,
    reliability_percentiles: pd.DataFrame | None = None,
    max_error_percentile: float = 1.0,
    actions: tuple[str, ...] = DEFAULT_ACTIONS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, float]] = []
    decisions: list[dict[str, Any]] = []
    for i, dt in enumerate(target_weights.index):
        keep = _normalize(target_weights.loc[dt].to_dict())
        allowed = True if action_allowed is None else bool(action_allowed.loc[dt])
        preds = {
            action: float(np.clip(predicted_regrets.loc[dt].get(action, 0.0), -float(regret_clip), float(regret_clip)))
            for action in actions
        }
        preds["KEEP"] = 0.0
        best = max(actions, key=lambda action: (preds[action], action == "KEEP"))
        reliability_percentile = None
        reliability_gate_pass = True
        if not allowed:
            best = "KEEP"
        if best != "KEEP" and preds[best] <= float(edge_threshold):
            best = "KEEP"
        candidate_before_reliability = best
        if best != "KEEP" and reliability_percentiles is not None:
            reliability_percentile = float(reliability_percentiles.loc[dt].get(best, 1.0))
            reliability_gate_pass = reliability_percentile <= float(max_error_percentile)
            if not reliability_gate_pass:
                best = "KEEP"
        prior_dt = target_weights.index[max(i - 1, 0)]
        prior_00631l = float(target_weights.loc[prior_dt].get("00631L.TW", 0.0) or 0.0)
        action_weights = _apply_action(keep, action=best, prior_00631l_weight=prior_00631l, cap10=cap10)
        action_diff = sum(
            abs(float(action_weights.get(key, 0.0) or 0.0) - float(keep.get(key, 0.0) or 0.0))
            for key in (*TICKERS, "cash")
        )
        if best != "KEEP" and action_diff < 1e-10:
            best = "KEEP"
            action_weights = keep
        final_weights = (
            action_weights
            if best == "KEEP" or best.startswith("REENTER")
            else _apply_partial_and_turnover_cap(
                keep,
                action_weights,
                adjustment_fraction=adjustment_fraction,
                turnover_cap=turnover_cap,
            )
        )
        rows.append({key: float(final_weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
        decisions.append(
            {
                "date": str(dt.date()),
                "action": best,
                "predicted_regret": preds[best],
                "predicted_regrets": preds,
                "candidate_action_before_reliability": candidate_before_reliability,
                "candidate_predicted_regret_before_reliability": preds.get(candidate_before_reliability, 0.0),
                "reliability_error_percentile": reliability_percentile,
                "reliability_gate_pass": bool(reliability_gate_pass),
                "base_00631l_weight": float(keep.get("00631L.TW", 0.0) or 0.0),
                "final_00631l_weight": float(final_weights.get("00631L.TW", 0.0) or 0.0),
                "action_allowed": bool(allowed),
            }
        )
    return pd.DataFrame(rows, index=target_weights.index), pd.DataFrame(decisions)


def _stateful_candidate_weights(
    keep: dict[str, float],
    current: dict[str, float],
    *,
    action: str,
    prior_a2118_00631l_weight: float,
    cap10: float,
    adjustment_fraction: float,
    turnover_cap: float,
) -> dict[str, float]:
    """Map an action to stateful shadow weights.

    In stateful mode, KEEP means keep the current shadow allocation instead of
    resetting to A21.18. REENTER is the explicit path back toward A21.18.
    """

    if action == "KEEP":
        return _normalize(dict(current))
    if action == "REENTER":
        return _apply_partial_and_turnover_cap(
            current,
            keep,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
    reenter_step = _parse_reenter_00631l_step(action)
    if reenter_step is not None:
        target_00631l = min(
            float(keep.get("00631L.TW", 0.0) or 0.0),
            float(current.get("00631L.TW", 0.0) or 0.0) + reenter_step,
        )
        partial_reenter = _add_00631l_from_0050_then_cash(
            current,
            target_00631l_weight=target_00631l,
        )
        return _apply_partial_and_turnover_cap(
            current,
            partial_reenter,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
    if action == "NO_ADD":
        capped = _cap_00631l_to_cash(keep, max(0.0, min(prior_a2118_00631l_weight, current.get("00631L.TW", 0.0))))
        return _apply_partial_and_turnover_cap(
            current,
            capped,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
    if action == "CAP10":
        capped = _cap_00631l_to_0050(keep, cap10)
        return _apply_partial_and_turnover_cap(
            current,
            capped,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
    if action.startswith("CAP"):
        try:
            cap = float(action.removeprefix("CAP")) / 100.0
        except ValueError as exc:
            raise ValueError(f"Unsupported action: {action}") from exc
        capped = _cap_00631l_to_0050(keep, cap)
        return _apply_partial_and_turnover_cap(
            current,
            capped,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
    raise ValueError(f"Unsupported action: {action}")


def _select_actions_stateful(
    target_weights: pd.DataFrame,
    predicted_regrets: pd.DataFrame,
    *,
    edge_threshold: float,
    regret_clip: float,
    adjustment_fraction: float,
    turnover_cap: float,
    cap10: float,
    reenter_edge_threshold: float,
    action_allowed: pd.Series | None = None,
    reliability_percentiles: pd.DataFrame | None = None,
    max_error_percentile: float = 1.0,
    actions: tuple[str, ...] = DEFAULT_ACTIONS,
    relief_signal: pd.Series | None = None,
    relief_min_holding_days: int = 0,
    relief_min_gap: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`relief_signal` (optional): a boolean series, indexed like target_weights,
    that hard-gates REENTER independently of the learned regret model -- when
    the shadow position is below the A21.18 target AND relief_signal is True
    that day, REENTER fires unconditionally (bypassing edge_threshold and the
    reliability filter). This exists because REENTER, left to compete
    symmetrically against KEEP/NO_ADD/CAP10 in the same regret-argmax, is
    starved of training data (it can only ever be sampled on the rare days a
    prior CAP/NO_ADD has already fired) and in practice never wins the argmax
    -- see GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md
    Part H for the empirical finding (REENTER fired 0/46 times across 7
    historical windows) this parameter is designed to fix.

    `relief_min_holding_days`: a cooldown, in trading days, enforced between
    consecutive relief-triggered REENTER steps. Without this, a multi-day
    turnover_cap-limited walk-back to the A21.18 target fires a real rebalance
    on every single eligible day for as long as the relief signal holds --
    empirically this roughly tripled/quadrupled rebalance_count and turnover
    in a first (uncapped) prototype. While in cooldown, the day falls through
    to the normal regret-argmax decision instead of being forced to REENTER
    (so CAP10 can still fire if genuinely warranted; the position otherwise
    just holds). Default 0 = no cooldown (fires every eligible day, matching
    the original, turnover-heavy prototype).

    `relief_min_gap`: minimum 00631L weight gap (A21.18 target minus current)
    required before the relief gate is allowed to fire at all. Without this,
    `is_below_a2118`'s 1e-10 epsilon means any sub-basis-point residual (left
    over after a prior partial re-entry step, or from ordinary daily A21.18
    target drift) counts as "below target" -- and in a long calm stretch,
    ordinary VIX noise satisfies `relief_signal` often enough that the gate
    fires repeatedly against an already-immaterial gap, paying transaction
    costs for a no-op rebalance. Empirically found responsible for real,
    unexplained underperformance in the two windows containing the current
    regime (`live_2024_2026`/`active_2025_2026`) even though CAP10 itself
    barely fired there. Default 0.0 = no minimum (matches prior behavior)."""
    rows: list[dict[str, float]] = []
    decisions: list[dict[str, Any]] = []
    overlay = {key: 0.0 for key in (*TICKERS, "cash")}
    days_since_relief_action = int(relief_min_holding_days)
    for i, dt in enumerate(target_weights.index):
        keep = _normalize(target_weights.loc[dt].to_dict())
        allowed = True if action_allowed is None else bool(action_allowed.loc[dt])
        current = _normalize(
            {
                key: max(float(keep.get(key, 0.0) or 0.0) + float(overlay.get(key, 0.0) or 0.0), 0.0)
                for key in (*TICKERS, "cash")
            }
        )
        preds = {
            action: float(np.clip(predicted_regrets.loc[dt].get(action, 0.0), -float(regret_clip), float(regret_clip)))
            for action in actions
        }
        preds["KEEP"] = 0.0
        prior_dt = target_weights.index[max(i - 1, 0)]
        prior_a2118_00631l = float(target_weights.loc[prior_dt].get("00631L.TW", 0.0) or 0.0)

        a2118_00631l_gap = float(keep.get("00631L.TW", 0.0) or 0.0) - float(current.get("00631L.TW", 0.0) or 0.0)
        is_below_a2118 = a2118_00631l_gap > 1e-10
        relief_triggered = bool(
            is_below_a2118
            and a2118_00631l_gap >= float(relief_min_gap)
            and relief_signal is not None
            and dt in relief_signal.index
            and bool(relief_signal.loc[dt])
            and days_since_relief_action >= int(relief_min_holding_days)
        )
        days_since_relief_action += 1
        eligible_actions = tuple(
            action for action in actions if is_below_a2118 or not action.startswith("REENTER")
        )
        best = max(eligible_actions, key=lambda action: (preds[action], action == "KEEP"))
        reliability_percentile = None
        reliability_gate_pass = True
        if not allowed:
            best = "KEEP"
            relief_triggered = False
        if relief_triggered:
            # Hard gate: bypasses edge_threshold/reliability entirely -- this
            # is a rule, not a learned regret comparison, so it does not
            # compete against KEEP's fixed 0.0 anchor the way the model-driven
            # path below does.
            best = "REENTER"
            days_since_relief_action = 0
        else:
            threshold = float(reenter_edge_threshold) if best.startswith("REENTER") and is_below_a2118 else float(edge_threshold)
            if best != "KEEP" and preds[best] <= threshold:
                best = "KEEP"
            if best.startswith("REENTER") and not is_below_a2118:
                best = "KEEP"
        if best.startswith("CAP"):
            cap = float(cap10)
            if best != "CAP10":
                try:
                    cap = float(best.removeprefix("CAP")) / 100.0
                except ValueError:
                    cap = float(cap10)
            if (
                float(keep.get("00631L.TW", 0.0) or 0.0) <= cap + 1e-10
                and float(current.get("00631L.TW", 0.0) or 0.0) <= cap + 1e-10
            ):
                best = "KEEP"
        if (
            best == "NO_ADD"
            and float(keep.get("00631L.TW", 0.0) or 0.0) <= float(prior_a2118_00631l) + 1e-10
        ):
            best = "KEEP"
        candidate_before_reliability = best
        if not relief_triggered and best != "KEEP" and reliability_percentiles is not None:
            reliability_percentile = float(reliability_percentiles.loc[dt].get(best, 1.0))
            reliability_gate_pass = reliability_percentile <= float(max_error_percentile)
            if not reliability_gate_pass:
                best = "KEEP"

        candidate = _stateful_candidate_weights(
            keep,
            current,
            action=best,
            prior_a2118_00631l_weight=prior_a2118_00631l,
            cap10=cap10,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
        )
        diff = sum(
            abs(float(candidate.get(key, 0.0) or 0.0) - float(current.get(key, 0.0) or 0.0))
            for key in (*TICKERS, "cash")
        )
        if best != "KEEP" and diff < 1e-10:
            best = "KEEP"
            candidate = _normalize(dict(current))
        current = candidate
        overlay = {
            key: float(current.get(key, 0.0) or 0.0) - float(keep.get(key, 0.0) or 0.0)
            for key in (*TICKERS, "cash")
        }
        rows.append({key: float(current.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
        decisions.append(
            {
                "date": str(dt.date()),
                "action": best,
                "predicted_regret": preds[best],
                "predicted_regrets": preds,
                "candidate_action_before_reliability": candidate_before_reliability,
                "candidate_predicted_regret_before_reliability": preds.get(candidate_before_reliability, 0.0),
                "reliability_error_percentile": reliability_percentile,
                "reliability_gate_pass": bool(reliability_gate_pass),
                "base_00631l_weight": float(keep.get("00631L.TW", 0.0) or 0.0),
                "final_00631l_weight": float(current.get("00631L.TW", 0.0) or 0.0),
                "below_a2118_before_action": bool(is_below_a2118),
                "action_allowed": bool(allowed),
                "relief_triggered": bool(relief_triggered),
            }
        )
    return pd.DataFrame(rows, index=target_weights.index), pd.DataFrame(decisions)


def _simulate_daily_target_weights(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = _normalize(target_weights.loc[dt].to_dict())
        next_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        if next_key != current_key:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: target_values.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = max(net_value - sum(target_values.values()), 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_key = next_key
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    panel_path: str | None,
    initial_value: float,
    horizon: int,
    min_train_days: int,
    train_window_days: int,
    edge_threshold: float,
    regret_clip: float,
    adjustment_fraction: float,
    turnover_cap: float,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    cap10: float,
    ridge_alpha: float,
    stateful_actions: bool,
    reenter_edge_threshold: float,
    require_panel_signal: bool,
    selective_reliability: bool,
    reliability_max_error_percentile: float,
    reliability_min_train_days: int,
    actions: tuple[str, ...],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    relief_gate: bool = False,
    relief_lookback_days: int = 20,
    relief_ratio: float = 0.85,
    relief_min_holding_days: int = 0,
    relief_min_gap: float = 0.0,
    vix_close: pd.Series | None = None,
    cross_asset_features: bool = False,
    cross_asset_market_close: pd.DataFrame | None = None,
    foreign_futures_net_ratio: pd.Series | None = None,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=panel_path,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    panel = _load_panel(panel_path)
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    target_weights = _targets_from_report(frame, report)
    target_00631l = target_weights["00631L.TW"].astype(float)
    target_00631l_support = {
        "max_weight": float(target_00631l.max()) if not target_00631l.empty else 0.0,
        "mean_weight": float(target_00631l.mean()) if not target_00631l.empty else 0.0,
        "p90_weight": float(target_00631l.quantile(0.90)) if not target_00631l.empty else 0.0,
        "positive_days": int((target_00631l > 1e-9).sum()),
        "gt_2pct_days": int((target_00631l > 0.02).sum()),
        "gt_5pct_days": int((target_00631l > 0.05).sum()),
        "gt_10pct_days": int((target_00631l > 0.10).sum()),
        "total_days": int(len(target_00631l)),
    }
    feature_columns = FEATURE_COLUMNS + CROSS_ASSET_FEATURE_COLUMNS if cross_asset_features else FEATURE_COLUMNS
    cross_asset = (
        _build_cross_asset_features(
            target_weights.index,
            cross_asset_market_close if cross_asset_market_close is not None else pd.DataFrame(),
            foreign_futures_net_ratio if foreign_futures_net_ratio is not None else pd.Series(dtype=float),
            prices,
        )
        if cross_asset_features
        else None
    )
    features = _build_features(frame, panel, target_weights, prices, cross_asset=cross_asset)
    action_allowed = _panel_signal_available(target_weights.index, panel) if require_panel_signal else None
    labels = _build_action_labels(
        prices,
        target_weights,
        horizon=horizon,
        lambda_mdd=lambda_mdd,
        gamma_turnover=gamma_turnover,
        eta_missed_rebound=eta_missed_rebound,
        cap10=cap10,
        actions=actions,
    )
    predicted = _predict_action_regrets(
        features,
        labels,
        min_train_days=min_train_days,
        train_window_days=train_window_days,
        ridge_alpha=ridge_alpha,
        regret_clip=regret_clip,
        actions=actions,
        feature_columns=feature_columns,
    )
    calibration_pairs = _build_calibration_pairs(
        labels,
        predicted,
        min_train_days=min_train_days,
        train_window_days=train_window_days,
        actions=actions,
        features=features,
    )
    reliability_percentiles = (
        _predict_action_error_percentiles(
            features,
            labels,
            predicted,
            min_train_days=reliability_min_train_days,
            train_window_days=train_window_days,
            ridge_alpha=ridge_alpha,
            actions=actions,
            feature_columns=feature_columns,
        )
        if selective_reliability
        else None
    )
    if stateful_actions:
        relief_signal = (
            _vix_relief_signal(
                target_weights.index,
                vix_close,
                lookback_days=relief_lookback_days,
                relief_ratio=relief_ratio,
            )
            if relief_gate and vix_close is not None
            else None
        )
        shadow_weights, decisions = _select_actions_stateful(
            target_weights,
            predicted,
            edge_threshold=edge_threshold,
            regret_clip=regret_clip,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
            cap10=cap10,
            reenter_edge_threshold=reenter_edge_threshold,
            action_allowed=action_allowed,
            reliability_percentiles=reliability_percentiles,
            max_error_percentile=reliability_max_error_percentile,
            actions=actions,
            relief_signal=relief_signal,
            relief_min_holding_days=int(relief_min_holding_days),
            relief_min_gap=float(relief_min_gap),
        )
    else:
        shadow_weights, decisions = _select_actions(
            target_weights,
            predicted,
            edge_threshold=edge_threshold,
            regret_clip=regret_clip,
            adjustment_fraction=adjustment_fraction,
            turnover_cap=turnover_cap,
            cap10=cap10,
            action_allowed=action_allowed,
            reliability_percentiles=reliability_percentiles,
            max_error_percentile=reliability_max_error_percentile,
            actions=actions,
        )
    baseline_curve, baseline_execution = _simulate_daily_target_weights(
        prices,
        target_weights,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    shadow_curve, shadow_execution = _simulate_daily_target_weights(
        prices,
        shadow_weights,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    shadow_metrics = _metrics(shadow_curve, initial_value)
    action_counts = decisions["action"].value_counts().to_dict() if not decisions.empty else {}
    non_keep = decisions[decisions["action"] != "KEEP"] if not decisions.empty else decisions
    realized_edge = {}
    if not labels.empty and not non_keep.empty:
        joined = non_keep.set_index(pd.to_datetime(non_keep["date"])).join(labels, how="left", rsuffix="_realized")
        values = []
        for _idx, row in joined.iterrows():
            value = float(row.get(row["action"], 0.0) or 0.0)
            if math.isfinite(value):
                values.append(value)
        realized_edge = {
            "mean_selected_realized_regret": float(np.mean(values)) if values else 0.0,
            "positive_selected_realized_regret_rate": float(np.mean([v > 0.0 for v in values])) if values else 0.0,
        }
    regret_prediction_quality: dict[str, Any] = {}
    if calibration_pairs:
        cal_df = pd.DataFrame(calibration_pairs)
        for action in actions:
            if action == "KEEP":
                continue
            sub = cal_df[cal_df["action"] == action]
            n = int(len(sub))
            corr = None
            if n >= 5 and float(sub["predicted_regret"].std()) > 1e-12 and float(sub["realized_regret"].std()) > 1e-12:
                corr = float(np.corrcoef(sub["predicted_regret"], sub["realized_regret"])[0, 1])
            regret_prediction_quality[action] = {
                "n": n,
                "oos_pred_vs_realized_corr": corr,
            }
    reliability_summary: dict[str, Any] = {
        "enabled": bool(selective_reliability),
        "max_error_percentile": float(reliability_max_error_percentile),
        "min_train_days": int(reliability_min_train_days),
    }
    if selective_reliability and not decisions.empty:
        candidate_non_keep = decisions[decisions["candidate_action_before_reliability"] != "KEEP"]
        rejected = candidate_non_keep[candidate_non_keep["action"] == "KEEP"]
        reliability_summary.update(
            {
                "candidate_non_keep_days": int(len(candidate_non_keep)),
                "accepted_non_keep_days": int(len(non_keep)),
                "rejected_to_keep_days": int(len(rejected)),
                "keep_rate": float((decisions["action"] == "KEEP").mean()),
                "acceptance_rate_among_candidates": float(len(non_keep) / len(candidate_non_keep))
                if len(candidate_non_keep)
                else None,
            }
        )
    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": end},
        "baseline_metrics": baseline_metrics,
        "shadow_metrics": shadow_metrics,
        "delta_vs_baseline": _metric_delta(shadow_metrics, baseline_metrics),
        "baseline_execution": baseline_execution,
        "shadow_execution": shadow_execution,
        "action_counts": {str(k): int(v) for k, v in action_counts.items()},
        "non_keep_days": int(len(non_keep)),
        "non_keep_decisions": non_keep.to_dict(orient="records"),
        "realized_selected_edge": realized_edge,
        "calibration_pairs": calibration_pairs,
        "regret_prediction_quality": regret_prediction_quality,
        "selective_reliability": reliability_summary,
        "recent_decisions": decisions.tail(20).to_dict(orient="records"),
        "label_rows": int(len(labels)),
        "feature_rows": int(len(features)),
        "dividend_coverage": dividend_coverage,
        "ncf_panel": panel_path,
        "stateful_actions": bool(stateful_actions),
        "require_panel_signal": bool(require_panel_signal),
        "panel_signal_days": int(action_allowed.sum()) if action_allowed is not None else None,
        "target_00631l_support": target_00631l_support,
        "relief_gate": {
            "enabled": bool(relief_gate),
            "lookback_days": int(relief_lookback_days),
            "relief_ratio": float(relief_ratio),
            "min_holding_days": int(relief_min_holding_days),
            "min_gap": float(relief_min_gap),
            "relief_triggered_days": int(decisions["relief_triggered"].sum())
            if not decisions.empty and "relief_triggered" in decisions.columns
            else 0,
        },
        "cross_asset_features": bool(cross_asset_features),
        "feature_columns": list(feature_columns),
    }


def _parse_windows(raw: str | None) -> list[tuple[str, str, str, str | None, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    out: list[tuple[str, str, str, str | None, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in (3, 4, 5):
            raise ValueError("--windows items must be label:start:end[:panel[:bucket]]")
        label, start, end = parts[:3]
        panel = parts[3] if len(parts) >= 4 and parts[3] else PANEL_2025_2026
        bucket = parts[4] if len(parts) >= 5 and parts[4] else "custom"
        out.append((label, start, end, panel, bucket))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--min-train-days", type=int, default=120)
    parser.add_argument("--train-window-days", type=int, default=420)
    parser.add_argument("--edge-threshold", type=float, default=0.002)
    parser.add_argument("--regret-clip", type=float, default=0.03)
    parser.add_argument("--adjustment-fraction", type=float, default=0.40)
    parser.add_argument("--turnover-cap", type=float, default=0.10)
    parser.add_argument("--lambda-mdd", type=float, default=0.35)
    parser.add_argument("--gamma-turnover", type=float, default=0.015)
    parser.add_argument("--eta-missed-rebound", type=float, default=0.30)
    parser.add_argument("--cap10", type=float, default=0.10)
    parser.add_argument("--actions", default=",".join(DEFAULT_ACTIONS))
    parser.add_argument("--ridge-alpha", type=float, default=10.0)
    parser.add_argument("--stateful-actions", action="store_true")
    parser.add_argument("--reenter-edge-threshold", type=float, default=-0.0005)
    parser.add_argument("--require-panel-signal", action="store_true")
    parser.add_argument("--selective-reliability", action="store_true")
    parser.add_argument("--reliability-max-error-percentile", type=float, default=0.70)
    parser.add_argument("--reliability-min-train-days", type=int, default=60)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--windows", default=None)
    parser.add_argument(
        "--relief-gate",
        action="store_true",
        help=(
            "Hard-gate REENTER on a rule-based VIX relief signal (VIX has "
            "fallen below --relief-ratio of its own trailing --relief-lookback-days "
            "peak) instead of only the learned regret-argmax, which in "
            "practice never selects REENTER (data-starved -- see "
            "GROUP_A_PLUS_H20_CALIBRATION_PANEL_DRIFT_GATE_DEADLOCK_HANDOFF_20260726.md "
            "Part H). Only affects --stateful-actions runs. Default off."
        ),
    )
    parser.add_argument("--relief-lookback-days", type=int, default=20)
    parser.add_argument("--relief-ratio", type=float, default=0.85)
    parser.add_argument(
        "--relief-min-holding-days",
        type=int,
        default=0,
        help=(
            "Cooldown (trading days) between consecutive relief-triggered "
            "REENTER steps. Default 0 (fires every eligible day -- the "
            "original, turnover-heavy prototype); set e.g. 5-10 to bound "
            "turnover from a multi-day walk-back."
        ),
    )
    parser.add_argument(
        "--relief-min-gap",
        type=float,
        default=0.0,
        help=(
            "Minimum 00631L weight gap (A21.18 target minus current) "
            "required before the relief gate is allowed to fire. Default 0.0 "
            "(fires against any residual gap, including sub-basis-point "
            "noise); set e.g. 0.01 to avoid no-op rebalances against an "
            "already-immaterial gap in calm periods."
        ),
    )
    parser.add_argument(
        "--cross-asset-features",
        action="store_true",
        help=(
            "Add cross-asset features (TSM ADR/SOXX/NVDA overnight returns, "
            "USD/TWD change, TSMC-vs-0050 5d spread, TAIFEX foreign futures "
            "net OI ratio, distance from recent low, drawdown recovery ratio) "
            "to the regret-prediction feature set. All series are read from "
            "cache already in the DB -- no download. Proposed to test whether "
            "these features carry information the existing feature set does "
            "not, ahead of the already-closed rule-based --relief-gate line. "
            "Default off (identical behavior to no flag)."
        ),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    actions = tuple(part.strip().upper() for part in str(args.actions).split(",") if part.strip())
    if "KEEP" not in actions:
        raise ValueError("--actions must include KEEP")

    db_path = _resolve(args.db)
    vix_close = _load_vix_close(db_path) if args.relief_gate else None
    cross_asset_market_close = (
        _load_cross_asset_market_close(db_path) if args.cross_asset_features else None
    )
    foreign_futures_net_ratio = (
        _load_foreign_futures_net_ratio(db_path) if args.cross_asset_features else None
    )
    results = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            panel_path=panel,
            initial_value=float(args.initial_value),
            horizon=int(args.horizon),
            min_train_days=int(args.min_train_days),
            train_window_days=int(args.train_window_days),
            edge_threshold=float(args.edge_threshold),
            regret_clip=float(args.regret_clip),
            adjustment_fraction=float(args.adjustment_fraction),
            turnover_cap=float(args.turnover_cap),
            lambda_mdd=float(args.lambda_mdd),
            gamma_turnover=float(args.gamma_turnover),
            eta_missed_rebound=float(args.eta_missed_rebound),
            cap10=float(args.cap10),
            ridge_alpha=float(args.ridge_alpha),
            stateful_actions=bool(args.stateful_actions),
            reenter_edge_threshold=float(args.reenter_edge_threshold),
            require_panel_signal=bool(args.require_panel_signal),
            selective_reliability=bool(args.selective_reliability),
            reliability_max_error_percentile=float(args.reliability_max_error_percentile),
            reliability_min_train_days=int(args.reliability_min_train_days),
            actions=actions,
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            relief_gate=bool(args.relief_gate),
            relief_lookback_days=int(args.relief_lookback_days),
            relief_ratio=float(args.relief_ratio),
            relief_min_holding_days=int(args.relief_min_holding_days),
            relief_min_gap=float(args.relief_min_gap),
            vix_close=vix_close,
            cross_asset_features=bool(args.cross_asset_features),
            cross_asset_market_close=cross_asset_market_close,
            foreign_futures_net_ratio=foreign_futures_net_ratio,
        )
        for label, start, end, panel, bucket in _parse_windows(args.windows)
    ]
    passed = [
        item
        for item in results
        if item["delta_vs_baseline"]["delta_final_value"] >= 0
        and item["delta_vs_baseline"]["delta_sharpe_ratio"] >= 0
        and item["delta_vs_baseline"]["delta_max_drawdown"] >= 0
    ]
    payload = {
        "report_type": "a2118_decision_focused_action_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "actions": list(actions),
            "target": "action_regret = Utility(action) - Utility(KEEP)",
            "utility": {
                "horizon": int(args.horizon),
                "lambda_mdd": float(args.lambda_mdd),
                "gamma_turnover": float(args.gamma_turnover),
                "eta_missed_rebound": float(args.eta_missed_rebound),
            },
            "stabilizers": {
                "regret_clip": float(args.regret_clip),
                "edge_threshold": float(args.edge_threshold),
                "adjustment_fraction": float(args.adjustment_fraction),
                "turnover_cap": float(args.turnover_cap),
                "finite_actions_only": True,
                "stateful_actions": bool(args.stateful_actions),
                "reenter_edge_threshold": float(args.reenter_edge_threshold),
                "require_panel_signal": bool(args.require_panel_signal),
                "selective_reliability": bool(args.selective_reliability),
                "reliability_max_error_percentile": float(args.reliability_max_error_percentile),
                "reliability_min_train_days": int(args.reliability_min_train_days),
                "relief_gate": bool(args.relief_gate),
                "relief_lookback_days": int(args.relief_lookback_days),
                "relief_ratio": float(args.relief_ratio),
                "relief_min_holding_days": int(args.relief_min_holding_days),
                "relief_min_gap": float(args.relief_min_gap),
            },
            "model": {
                "type": "expanding_ridge_linear_per_action",
                "min_train_days": int(args.min_train_days),
                "train_window_days": int(args.train_window_days),
                "ridge_alpha": float(args.ridge_alpha),
                "cross_asset_features": bool(args.cross_asset_features),
                "features": list(
                    FEATURE_COLUMNS + CROSS_ASSET_FEATURE_COLUMNS
                    if args.cross_asset_features
                    else FEATURE_COLUMNS
                ),
            },
        },
        "summary": {
            "windows": len(results),
            "triple_pass_windows": len(passed),
            "all_windows_triple_pass": len(passed) == len(results),
            "total_candidate_non_keep_days": int(
                sum(
                    (item.get("selective_reliability") or {}).get(
                        "candidate_non_keep_days",
                        item.get("non_keep_days", 0),
                    )
                    or 0
                    for item in results
                )
            ),
            "total_rejected_to_keep_days": int(
                sum((item.get("selective_reliability") or {}).get("rejected_to_keep_days", 0) or 0 for item in results)
            ),
        },
        "results": results,
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Triple-pass windows: {len(passed)}/{len(results)}")
    for item in results:
        delta = item["delta_vs_baseline"]
        print(
            f"{item['label']}: Δfinal={delta['delta_final_value']:,.0f}, "
            f"Δsharpe={delta['delta_sharpe_ratio']:.4f}, "
            f"ΔMDD={delta['delta_max_drawdown']:.4f}, "
            f"non_keep={item['non_keep_days']}, actions={item['action_counts']}"
        )
    if args.selective_reliability:
        print(
            "Selective reliability: "
            f"candidates={payload['summary']['total_candidate_non_keep_days']}, "
            f"rejected={payload['summary']['total_rejected_to_keep_days']}"
        )


if __name__ == "__main__":
    main()
