"""Lightweight Alphalens-inspired factor diagnostics for GroupA+.

This module intentionally avoids importing the legacy Alphalens package.  It
implements the small subset we need for production research gates: forward
returns, IC, IC IR, IC decay, quantile forward returns, cumulative quantile
returns, rank autocorrelation, event studies, and a conservative IC gate.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def forward_returns(
    prices: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> pd.DataFrame:
    """Compute forward returns for wide price data.

    Returns a DataFrame with MultiIndex columns: (asset, fwd_ret_<h>d).
    """
    prices = prices.sort_index().astype(float)
    frames: list[pd.DataFrame] = []
    for horizon in horizons:
        ret = prices.shift(-horizon) / prices - 1.0
        ret.columns = pd.MultiIndex.from_product(
            [ret.columns, [f"fwd_ret_{horizon}d"]],
            names=["asset", "horizon"],
        )
        frames.append(ret)
    return pd.concat(frames, axis=1).sort_index(axis=1)


def make_single_asset_factor_data(
    factor: pd.Series,
    price: pd.Series,
    *,
    asset: str,
    horizons: tuple[int, ...] = (1, 5, 20),
    quantiles: int = 5,
) -> pd.DataFrame:
    """Build an Alphalens-like DataFrame for one asset over time."""
    factor = factor.dropna().sort_index().astype(float)
    price = price.sort_index().astype(float)
    frame = pd.DataFrame({"factor": factor})
    aligned_price = price.reindex(frame.index.union(price.index)).sort_index().ffill().reindex(frame.index)
    for horizon in horizons:
        frame[f"fwd_ret_{horizon}d"] = (aligned_price.shift(-horizon) / aligned_price - 1.0).values
    frame["factor_quantile"] = quantize_series(frame["factor"], quantiles=quantiles)
    frame["asset"] = asset
    frame.index.name = "date"
    return frame.set_index("asset", append=True)


def quantize_series(values: pd.Series, *, quantiles: int = 5) -> pd.Series:
    """Quantize a Series, degrading gracefully when duplicate edges exist."""
    values = values.astype(float)
    nonnull = values.dropna()
    out = pd.Series(np.nan, index=values.index, dtype=float)
    if nonnull.empty:
        return out
    try:
        q = pd.qcut(nonnull, quantiles, labels=False, duplicates="drop") + 1
    except ValueError:
        ranks = nonnull.rank(method="first")
        q = pd.qcut(ranks, min(quantiles, len(nonnull)), labels=False, duplicates="drop") + 1
    out.loc[q.index] = q.astype(float)
    return out


def time_series_information_coefficient(
    factor_data: pd.DataFrame,
    *,
    method: str = "spearman",
) -> pd.Series:
    """Compute IC over time for each forward-return horizon."""
    cols = [col for col in factor_data.columns if str(col).startswith("fwd_ret_")]
    out: dict[str, float] = {}
    for col in cols:
        paired = factor_data[["factor", col]].dropna()
        out[col] = float(paired["factor"].corr(paired[col], method=method)) if len(paired) >= 3 else np.nan
    return pd.Series(out, name=f"{method}_ic")


def rolling_time_series_ic(
    factor_data: pd.DataFrame,
    *,
    window: int = 63,
    method: str = "spearman",
) -> pd.DataFrame:
    """Rolling time-series IC for each horizon."""
    cols = [col for col in factor_data.columns if str(col).startswith("fwd_ret_")]
    factor = factor_data["factor"].droplevel("asset") if isinstance(factor_data.index, pd.MultiIndex) else factor_data["factor"]
    result = pd.DataFrame(index=factor.index)
    for col in cols:
        returns = factor_data[col]
        if isinstance(returns.index, pd.MultiIndex):
            returns = returns.droplevel("asset")
        if method == "spearman":
            result[col] = factor.rank(method="average").rolling(window).corr(
                returns.rank(method="average")
            )
        else:
            result[col] = factor.rolling(window).corr(returns)
    return result


def mean_return_by_quantile(factor_data: pd.DataFrame) -> pd.DataFrame:
    """Mean forward returns by factor quantile."""
    cols = [col for col in factor_data.columns if str(col).startswith("fwd_ret_")]
    clean = factor_data.dropna(subset=["factor_quantile"])
    if clean.empty:
        return pd.DataFrame(columns=cols)
    return clean.groupby("factor_quantile")[cols].mean()


def quantile_spread(
    mean_quantile_returns: pd.DataFrame,
    *,
    upper_quantile: int | None = None,
    lower_quantile: int | None = None,
) -> pd.Series:
    """Compute upper-minus-lower quantile mean forward return spread."""
    if mean_quantile_returns.empty:
        return pd.Series(dtype=float)
    idx = mean_quantile_returns.index.astype(float)
    upper = float(upper_quantile) if upper_quantile is not None else float(idx.max())
    lower = float(lower_quantile) if lower_quantile is not None else float(idx.min())
    return (mean_quantile_returns.loc[upper] - mean_quantile_returns.loc[lower]).rename("quantile_spread")


def rank_autocorrelation(factor_data: pd.DataFrame, *, period: int = 1) -> float:
    """Autocorrelation of factor ranks over time."""
    factor = factor_data["factor"]
    if isinstance(factor.index, pd.MultiIndex):
        factor = factor.droplevel("asset")
    ranks = factor.rank(method="average")
    return float(ranks.corr(ranks.shift(period), method="spearman"))


def ic_information_ratio(
    factor_data: pd.DataFrame,
    *,
    window: int = 63,
    method: str = "spearman",
) -> dict[str, float]:
    """ICIR = mean(rolling IC) / std(rolling IC) for each horizon.

    A value above 0.5 is generally considered a useful signal.
    """
    rolling = rolling_time_series_ic(factor_data, window=window, method=method)
    out: dict[str, float] = {}
    for col in rolling.columns:
        series = rolling[col].dropna()
        if len(series) >= 4 and series.std() > 0:
            out[col] = float(series.mean() / series.std())
        else:
            out[col] = np.nan
    return out


def ic_decay(
    factor: pd.Series,
    price: pd.Series,
    *,
    max_lag: int = 20,
    method: str = "spearman",
) -> dict[str, float | None]:
    """IC at each lag 1..max_lag, showing how quickly the signal fades."""
    factor = factor.dropna().sort_index().astype(float)
    price = price.sort_index().astype(float)
    aligned = price.reindex(factor.index.union(price.index)).sort_index().ffill().reindex(factor.index)
    out: dict[str, float | None] = {}
    for lag in range(1, max_lag + 1):
        fwd = aligned.shift(-lag) / aligned - 1.0
        paired = pd.DataFrame({"factor": factor, "fwd": fwd}).dropna()
        if len(paired) >= 3:
            out[f"{lag}d"] = float(paired["factor"].corr(paired["fwd"], method=method))
        else:
            out[f"{lag}d"] = None
    return out


def cumulative_quantile_returns(
    factor_data: pd.DataFrame,
    *,
    horizon: str = "fwd_ret_1d",
) -> pd.DataFrame:
    """Cumulative compounded returns per quantile over time.

    Returns a DataFrame indexed by date with one column per quantile bucket.
    Used to check whether the Q5-Q1 spread compounds monotonically over time.
    """
    clean = factor_data.dropna(subset=["factor_quantile", horizon]).copy()
    if clean.empty:
        return pd.DataFrame()
    if isinstance(clean.index, pd.MultiIndex):
        clean = clean.droplevel("asset")
    pivot = clean.pivot_table(index=clean.index, columns="factor_quantile", values=horizon, aggfunc="mean")
    return (1.0 + pivot).cumprod() - 1.0


def factor_passes_gate(
    summary: dict[str, Any],
    *,
    min_ic_1d: float = 0.0,
    min_ic_5d: float = 0.0,
    min_spread_5d: float = 0.0,
    min_icir_5d: float | None = None,
) -> dict[str, Any]:
    """Conservative IC gate for enabling a new NCF-based trading rule.

    Uses ``rolling_ic_recent_mean`` (last 20 values of the rolling IC series)
    as the primary signal-health check, NOT the full-period static IC.
    Full-period IC is always positive by construction; recent rolling IC
    actually detects live regime degradation.

    20d IC is intentionally excluded from pass/fail — it is advisory only
    (the factor is a short-term signal; 20d predictions are unreliable).

    Returns a dict with ``passed`` (bool), per-criterion ``checks``, and
    an ``ic_20d_warning`` flag.
    """
    # Prefer recent rolling IC; fall back to full-period static IC if absent.
    recent = summary.get("rolling_ic_recent_mean", {})
    ic_static = summary.get("ic", {})
    spread = summary.get("quantile_spread", {})
    icir = summary.get("ic_ir", {})

    def _recent(col: str) -> float:
        v = recent.get(col)
        if v is not None:
            return float(v)
        return float(ic_static.get(col) or 0.0)

    checks: dict[str, bool] = {
        "recent_ic_1d_positive": _recent("fwd_ret_1d") > min_ic_1d,
        "recent_ic_5d_positive": _recent("fwd_ret_5d") > min_ic_5d,
        "spread_5d_positive": (spread.get("fwd_ret_5d") or 0.0) > min_spread_5d,
    }
    if min_icir_5d is not None:
        checks["icir_5d_threshold"] = (icir.get("fwd_ret_5d") or 0.0) > min_icir_5d

    ic_20d_recent = _recent("fwd_ret_20d")
    ic_20d_warning = ic_20d_recent <= 0.0

    return {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "ic_20d_warning": ic_20d_warning,
        "ic_20d_recent_mean": round(ic_20d_recent, 4),
    }


def event_study_forward_returns(
    events: pd.Series,
    price: pd.Series,
    *,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> dict[str, Any]:
    """Summarize forward returns after boolean events."""
    events = events.astype(bool).sort_index()
    price = price.sort_index().astype(float)
    aligned = price.reindex(events.index.union(price.index)).sort_index().ffill().reindex(events.index)
    event_dates = events[events].index
    payload: dict[str, Any] = {"event_count": int(len(event_dates)), "horizons": {}}
    for horizon in horizons:
        fwd = aligned.shift(-horizon) / aligned - 1.0
        event_rets = fwd.reindex(event_dates).dropna()
        payload["horizons"][f"{horizon}d"] = {
            "count": int(len(event_rets)),
            "mean_return": float(event_rets.mean()) if len(event_rets) else None,
            "median_return": float(event_rets.median()) if len(event_rets) else None,
            "hit_rate_positive": float((event_rets > 0.0).mean()) if len(event_rets) else None,
        }
    return payload


def summarize_factor(
    factor_data: pd.DataFrame,
    *,
    rolling_window: int = 63,
) -> dict[str, Any]:
    """Build a compact JSON-serializable factor diagnostic summary."""
    ic = time_series_information_coefficient(factor_data)
    mean_q = mean_return_by_quantile(factor_data)
    spread = quantile_spread(mean_q)
    rolling_ic = rolling_time_series_ic(factor_data, window=rolling_window)
    rolling_last = {
        col: values.dropna().iloc[-1]
        for col, values in rolling_ic.items()
        if not values.dropna().empty
    }
    icir = ic_information_ratio(factor_data, window=rolling_window)

    fwd_cols = [col for col in factor_data.columns if str(col).startswith("fwd_ret_")]
    cum_q_final: dict[str, dict[str, float]] = {}
    for col in fwd_cols:
        cumret = cumulative_quantile_returns(factor_data, horizon=col)
        if not cumret.empty:
            cum_q_final[col] = {
                str(int(q)): round(float(cumret[q].dropna().iloc[-1]), 6)
                for q in cumret.columns
                if not cumret[q].dropna().empty
            }

    # Recent rolling IC mean: last 20 values of the rolling IC series.
    # This reflects current signal health, unlike the full-period ic_dict.
    recent_n = 20
    rolling_ic_recent_mean: dict[str, float | None] = {}
    for col, values in rolling_ic.items():
        tail = values.dropna().iloc[-recent_n:]
        rolling_ic_recent_mean[col] = float(tail.mean()) if len(tail) >= 5 else None

    ic_dict = {key: (None if pd.isna(value) else float(value)) for key, value in ic.items()}
    spread_dict = {key: (None if pd.isna(value) else float(value)) for key, value in spread.items()}
    icir_dict = {key: (None if pd.isna(value) else float(value)) for key, value in icir.items()}
    gate = factor_passes_gate({"ic": ic_dict, "quantile_spread": spread_dict,
                               "ic_ir": icir_dict,
                               "rolling_ic_recent_mean": rolling_ic_recent_mean})

    return {
        "rows": int(len(factor_data)),
        "ic": ic_dict,
        "ic_ir": icir_dict,
        "mean_return_by_quantile": {
            str(int(idx)): {col: float(value) for col, value in row.items() if pd.notna(value)}
            for idx, row in mean_q.iterrows()
        },
        "quantile_spread": spread_dict,
        "quantile_cumret_final": cum_q_final,
        "rank_autocorrelation_1d": rank_autocorrelation(factor_data, period=1),
        "rolling_ic_last": {
            key: (None if pd.isna(value) else float(value))
            for key, value in rolling_last.items()
        },
        "rolling_ic_recent_mean": rolling_ic_recent_mean,
        "rolling_window": int(rolling_window),
        "gate": gate,
    }
