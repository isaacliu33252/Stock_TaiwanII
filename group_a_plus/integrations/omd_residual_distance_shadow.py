"""OMD-inspired residual-distance crowding diagnostics for GroupA+.

This is a small, shadow-only adaptation of arXiv:2607.27461. It does not
implement the paper's S&P 500 rank-chain portfolio. It only computes residual
correlation distances for the small GroupA+ ETF basket, where the full
cross-sectional OMD portfolio is not statistically appropriate.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
EQUITY_ANCHOR = "0050.TW"


def _float_or_none(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _safe_corr(frame: pd.DataFrame) -> pd.DataFrame:
    corr = frame.corr()
    corr = corr.reindex(index=frame.columns, columns=frame.columns)
    values = np.nan_to_num(corr.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    values = (values + values.T) / 2.0
    np.fill_diagonal(values, 1.0)
    return pd.DataFrame(values, index=frame.columns, columns=frame.columns)


def _arccos_distance(corr: pd.DataFrame) -> pd.DataFrame:
    values = np.clip(corr.to_numpy(dtype=float), -1.0, 1.0)
    distance = np.arccos(values)
    np.fill_diagonal(distance, 0.0)
    return pd.DataFrame(distance, index=corr.index, columns=corr.columns)


def _offdiag_values(matrix: pd.DataFrame) -> list[float]:
    if matrix.shape[0] < 2:
        return []
    mask = ~np.eye(matrix.shape[0], dtype=bool)
    values = matrix.to_numpy(dtype=float)[mask]
    return [float(value) for value in values if np.isfinite(value)]


def _pair_key(left: str, right: str) -> str:
    return f"{left}|{right}"


def _pairwise_payload(corr: pd.DataFrame, distance: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    cols = list(corr.columns)
    for i, left in enumerate(cols):
        for right in cols[i + 1 :]:
            out[_pair_key(left, right)] = {
                "corr": _float_or_none(corr.loc[left, right]),
                "distance": _float_or_none(distance.loc[left, right]),
            }
    return out


def _residualize_against_market(returns: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | None]]:
    market = returns.mean(axis=1)
    market_var = float(np.var(market.to_numpy(dtype=float)))
    betas: dict[str, float | None] = {}
    residuals = pd.DataFrame(index=returns.index)
    if market_var <= 1e-12:
        for ticker in returns.columns:
            betas[ticker] = None
            residuals[ticker] = returns[ticker] - returns[ticker].mean()
        return residuals, betas
    x = market.to_numpy(dtype=float)
    x_centered = x - float(np.mean(x))
    for ticker in returns.columns:
        y = returns[ticker].to_numpy(dtype=float)
        y_centered = y - float(np.mean(y))
        beta = float(np.dot(x_centered, y_centered) / np.dot(x_centered, x_centered))
        alpha = float(np.mean(y) - beta * np.mean(x))
        residuals[ticker] = y - alpha - beta * x
        betas[ticker] = _float_or_none(beta)
    return residuals, betas


def _percentile_rank(history: list[float], latest: float | None, *, higher_is_riskier: bool) -> float | None:
    if latest is None or not history:
        return None
    values = np.asarray([value for value in history if np.isfinite(value)], dtype=float)
    if values.size == 0:
        return None
    if higher_is_riskier:
        return float(np.mean(values <= latest))
    return float(np.mean(values >= latest))


def _latest_distance_state(
    *,
    mean_distance: float | None,
    low_distance_risk_percentile: float | None,
    min_distance: float | None,
    anchor_pair_distance: float | None,
) -> tuple[str, bool, list[str]]:
    reasons = [
        f"mean_pairwise_residual_distance={mean_distance:.4f}" if mean_distance is not None else "mean_pairwise_residual_distance=NA",
        (
            f"low_distance_risk_percentile={low_distance_risk_percentile:.4f}"
            if low_distance_risk_percentile is not None
            else "low_distance_risk_percentile=NA"
        ),
        f"min_pairwise_residual_distance={min_distance:.4f}" if min_distance is not None else "min_pairwise_residual_distance=NA",
        (
            f"0050_00631l_residual_distance={anchor_pair_distance:.4f}"
            if anchor_pair_distance is not None
            else "0050_00631l_residual_distance=NA"
        ),
    ]
    if mean_distance is None or low_distance_risk_percentile is None:
        return "unavailable", False, reasons
    if low_distance_risk_percentile >= 0.90 or (anchor_pair_distance is not None and anchor_pair_distance <= 0.35):
        return "crowding_high", True, reasons
    if low_distance_risk_percentile >= 0.75:
        return "crowding_watch", True, reasons
    return "normal", False, reasons


def build_omd_residual_distance_shadow(
    close: pd.DataFrame,
    *,
    as_of: str | None = None,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    window: int = 126,
    analysis_lookback: int = 504,
    min_history: int = 126,
) -> dict[str, Any]:
    """Build the latest residual-distance shadow payload from a close panel."""

    blockers: list[str] = []
    warnings: list[str] = [
        "research_only_no_live_weight_change",
        "not_full_omd_portfolio_rank_chain",
        "small_etf_universe_diagnostic_only",
    ]
    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
    else:
        close = close.copy()
        close.index = pd.to_datetime(close.index)
        requested = [ticker for ticker in tickers if ticker in close.columns]
        missing = sorted(set(tickers) - set(requested))
        if missing:
            warnings.append("requested_tickers_missing_from_price_panel")
        close = close[requested].sort_index().ffill(limit=3)
        if as_of:
            close = close.loc[close.index <= pd.Timestamp(as_of)]
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
        returns = returns.tail(analysis_lookback)
        usable = [ticker for ticker in returns.columns if int(returns[ticker].notna().sum()) >= min_history]
        returns = returns[usable].fillna(0.0) if usable else pd.DataFrame()

    if returns.empty:
        blockers.append("return_panel_missing")
    if len(returns.columns) < 3:
        blockers.append("insufficient_group_a_plus_ticker_breadth")
    if len(returns) < window:
        blockers.append("insufficient_rolling_window_history")

    snapshots = [] if blockers else build_omd_residual_distance_snapshots(returns, window=window)

    if not snapshots:
        blockers.append("residual_distance_scores_unavailable")
        latest: dict[str, Any] = {}
        low_distance_risk_percentile = None
        state, manual_review, state_reasons = "unavailable", False, ["residual_distance_scores_unavailable"]
    else:
        latest = snapshots[-1]
        history_mean_distances = [
            float(item["mean_pairwise_residual_distance"])
            for item in snapshots
            if item.get("mean_pairwise_residual_distance") is not None
        ]
        low_distance_risk_percentile = _percentile_rank(
            history_mean_distances,
            latest.get("mean_pairwise_residual_distance"),
            higher_is_riskier=False,
        )
        state, manual_review, state_reasons = _latest_distance_state(
            mean_distance=latest.get("mean_pairwise_residual_distance"),
            low_distance_risk_percentile=low_distance_risk_percentile,
            min_distance=latest.get("min_pairwise_residual_distance"),
            anchor_pair_distance=(latest.get("anchor_pair") or {}).get("0050_00631l_residual_distance"),
        )
        if manual_review:
            warnings.append(f"omd_residual_distance_state:{state}")

    actual_data_end = str(returns.index.max().date()) if not returns.empty else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_omd_residual_distance_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": actual_data_end,
        "status": "blocked" if blockers else "available_for_shadow_review",
        "policy": "shadow_only_no_target_weight_change",
        "source_paper": {
            "arxiv": "2607.27461",
            "title": "Are Three Matrices All You Need To Beat the Market? Observable Matrix Dynamics for Portfolio Optimization",
            "implemented_as": "residual_distance_crowding_shadow_not_full_omd_portfolio",
        },
        "method": {
            "paper_equivalent": False,
            "window_trading_days": window,
            "analysis_lookback": analysis_lookback,
            "min_history": min_history,
            "market_mode_removed": "equal_weight_group_a_plus_return_proxy_ols_residual",
            "distance_metric": "arccos_clipped_correlation",
            "rebalance_frequency": "none_diagnostic_only",
        },
        "coverage": {
            "requested_tickers": list(tickers),
            "usable_tickers": list(returns.columns) if not returns.empty else [],
            "usable_ticker_count": int(len(returns.columns)) if not returns.empty else 0,
            "return_observations": int(len(returns)) if not returns.empty else 0,
            "snapshot_count": int(len(snapshots)),
        },
        "latest": {
            **latest,
            "low_distance_risk_percentile": _float_or_none(low_distance_risk_percentile),
            "state": state,
            "manual_review_required": manual_review,
            "state_reasons": state_reasons,
        },
        "recent_snapshots": snapshots[-10:],
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "available_for_shadow_review": bool(snapshots) and not blockers,
            "paper_equivalent": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "direction_trade_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_latest_strategy_unchanged": True,
        },
    }


def prepare_omd_close_returns(
    close: pd.DataFrame,
    *,
    as_of: str | None = None,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    analysis_lookback: int | None = 504,
    min_history: int = 126,
) -> tuple[pd.DataFrame, list[str]]:
    if close.empty:
        return pd.DataFrame(), []
    close = close.copy()
    close.index = pd.to_datetime(close.index)
    requested = [ticker for ticker in tickers if ticker in close.columns]
    close = close[requested].sort_index().ffill(limit=3)
    if as_of:
        close = close.loc[close.index <= pd.Timestamp(as_of)]
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if analysis_lookback is not None:
        returns = returns.tail(int(analysis_lookback))
    usable = [ticker for ticker in returns.columns if int(returns[ticker].notna().sum()) >= min_history]
    returns = returns[usable].fillna(0.0) if usable else pd.DataFrame()
    return returns, usable


def build_omd_residual_distance_snapshots(returns: pd.DataFrame, *, window: int = 126) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    if returns.empty or len(returns.columns) < 2 or len(returns) < window:
        return snapshots
    for end_idx in range(window, len(returns) + 1):
        frame = returns.iloc[end_idx - window : end_idx].copy()
        residuals, market_betas = _residualize_against_market(frame)
        raw_corr = _safe_corr(frame)
        raw_distance = _arccos_distance(raw_corr)
        residual_corr = _safe_corr(residuals)
        residual_distance = _arccos_distance(residual_corr)
        residual_values = _offdiag_values(residual_distance)
        raw_values = _offdiag_values(raw_distance)
        latest_dt = str(frame.index[-1].date())
        anchor_pair = _pair_key("0050.TW", "00631L.TW")
        residual_pairs = _pairwise_payload(residual_corr, residual_distance)
        raw_pairs = _pairwise_payload(raw_corr, raw_distance)
        snapshots.append(
            {
                "dt": latest_dt,
                "ticker_count": int(len(frame.columns)),
                "window_observations": int(len(frame)),
                "mean_pairwise_raw_distance": _float_or_none(np.mean(raw_values) if raw_values else None),
                "mean_pairwise_residual_distance": _float_or_none(np.mean(residual_values) if residual_values else None),
                "min_pairwise_residual_distance": _float_or_none(np.min(residual_values) if residual_values else None),
                "max_pairwise_residual_distance": _float_or_none(np.max(residual_values) if residual_values else None),
                "market_proxy_betas": market_betas,
                "anchor_pair": {
                    "0050_00631l_raw_corr": raw_pairs.get(anchor_pair, {}).get("corr"),
                    "0050_00631l_raw_distance": raw_pairs.get(anchor_pair, {}).get("distance"),
                    "0050_00631l_residual_corr": residual_pairs.get(anchor_pair, {}).get("corr"),
                    "0050_00631l_residual_distance": residual_pairs.get(anchor_pair, {}).get("distance"),
                },
                "pairwise_raw": raw_pairs,
                "pairwise_residual": residual_pairs,
            }
        )
    return snapshots


def build_omd_residual_distance_score_frame(
    close: pd.DataFrame,
    *,
    as_of: str | None = None,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    window: int = 126,
    analysis_lookback: int | None = None,
    min_history: int = 126,
    baseline_lookback: int = 252,
) -> pd.DataFrame:
    returns, _usable = prepare_omd_close_returns(
        close,
        as_of=as_of,
        tickers=tickers,
        analysis_lookback=analysis_lookback,
        min_history=min_history,
    )
    snapshots = build_omd_residual_distance_snapshots(returns, window=window)
    if not snapshots:
        return pd.DataFrame()
    frame = pd.DataFrame(snapshots)
    frame["dt"] = pd.to_datetime(frame["dt"])
    risk_percentiles: list[float | None] = []
    states: list[str] = []
    manual_reviews: list[bool] = []
    state_reasons: list[list[str]] = []
    for idx, row in frame.iterrows():
        base = frame.iloc[max(0, idx - baseline_lookback + 1) : idx + 1]
        mean_history = [
            float(value)
            for value in base["mean_pairwise_residual_distance"].tolist()
            if value is not None and np.isfinite(float(value))
        ]
        risk_percentile = _percentile_rank(
            mean_history,
            row.get("mean_pairwise_residual_distance"),
            higher_is_riskier=False,
        )
        state, manual_review, reasons = _latest_distance_state(
            mean_distance=row.get("mean_pairwise_residual_distance"),
            low_distance_risk_percentile=risk_percentile,
            min_distance=row.get("min_pairwise_residual_distance"),
            anchor_pair_distance=(row.get("anchor_pair") or {}).get("0050_00631l_residual_distance"),
        )
        risk_percentiles.append(_float_or_none(risk_percentile))
        states.append(state)
        manual_reviews.append(manual_review)
        state_reasons.append(reasons)
    frame["low_distance_risk_percentile"] = risk_percentiles
    frame["state"] = states
    frame["manual_review_required"] = manual_reviews
    frame["state_reasons"] = state_reasons
    return frame


def append_omd_residual_distance_shadow_log(log_path: Path, payload: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "generated_at": payload.get("generated_at"),
        "as_of": payload.get("as_of"),
        "actual_data_end": payload.get("actual_data_end"),
        "status": payload.get("status"),
        "policy": payload.get("policy"),
        "latest": payload.get("latest"),
        "decision": payload.get("decision"),
        "blocking_reasons": payload.get("blocking_reasons"),
        "warning_reasons": payload.get("warning_reasons"),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
