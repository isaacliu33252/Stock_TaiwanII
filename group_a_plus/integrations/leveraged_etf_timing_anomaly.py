"""Leveraged ETF timing-anomaly diagnostics.

Research-only utilities inspired by Bianchi and Goldberg (2026): realized
levered ETF returns can differ from a constant-leverage approximation because
the effective daily return ratio co-moves with the underlying return.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimingAnomalyThresholds:
    min_abs_underlying_return: float = 0.0005
    ratio_winsor_quantile: float = 0.95
    negative_covariance_warning: float = -0.005
    tracking_error_warning: float = 0.20
    volatility_drag_warning: float = -0.02


def _annualize_mean(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(daily_returns.mean() * periods_per_year)


def _annualize_vol(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(daily_returns.std(ddof=0) * np.sqrt(periods_per_year))


def approximate_geometric_return(arithmetic_return: float, volatility: float) -> float:
    return float((1.0 + arithmetic_return) * np.exp(-(volatility**2) / 2.0) - 1.0)


def effective_return_ratio(
    etf_returns: pd.Series,
    underlying_returns: pd.Series,
    *,
    min_abs_underlying_return: float = 0.0005,
) -> pd.Series:
    aligned = pd.concat(
        [etf_returns.astype(float).rename("etf"), underlying_returns.astype(float).rename("underlying")],
        axis=1,
    ).dropna()
    valid = aligned["underlying"].abs() >= float(min_abs_underlying_return)
    ratio = aligned.loc[valid, "etf"] / aligned.loc[valid, "underlying"]
    return ratio.replace([np.inf, -np.inf], np.nan).dropna()


def winsorize_ratio(ratio: pd.Series, quantile: float = 0.95) -> pd.Series:
    if ratio.empty:
        return ratio
    q = float(quantile)
    if not 0.5 < q <= 1.0:
        raise ValueError("quantile must be in (0.5, 1.0]")
    lower = ratio.quantile(1.0 - q)
    upper = ratio.quantile(q)
    return ratio.clip(lower=lower, upper=upper)


def summarize_timing_anomaly(
    etf_prices: pd.Series,
    underlying_prices: pd.Series,
    *,
    target_leverage: float,
    thresholds: TimingAnomalyThresholds = TimingAnomalyThresholds(),
    periods_per_year: int = 252,
) -> dict[str, Any]:
    prices = pd.concat(
        [etf_prices.astype(float).rename("etf"), underlying_prices.astype(float).rename("underlying")],
        axis=1,
    ).dropna()
    if len(prices) < 3:
        raise ValueError("at least three aligned price rows are required")
    returns = prices.pct_change(fill_method=None).dropna()
    if returns.empty:
        raise ValueError("no returns after pct_change")

    ratio_raw = effective_return_ratio(
        returns["etf"],
        returns["underlying"],
        min_abs_underlying_return=thresholds.min_abs_underlying_return,
    )
    if ratio_raw.empty:
        raise ValueError("no usable effective return ratios")
    ratio = winsorize_ratio(ratio_raw, thresholds.ratio_winsor_quantile)
    common = pd.concat([ratio.rename("ratio"), returns["underlying"].rename("underlying")], axis=1).dropna()
    covariance_daily = float(common["ratio"].cov(common["underlying"], ddof=0))
    covariance_annualized = covariance_daily * periods_per_year

    underlying_arith = _annualize_mean(returns["underlying"], periods_per_year)
    underlying_vol = _annualize_vol(returns["underlying"], periods_per_year)
    etf_arith = _annualize_mean(returns["etf"], periods_per_year)
    etf_vol = _annualize_vol(returns["etf"], periods_per_year)
    ideal_arith = float(target_leverage) * underlying_arith
    empirical_constant_arith = float(ratio.mean()) * underlying_arith
    arithmetic_gap_vs_ideal = etf_arith - ideal_arith
    arithmetic_gap_vs_empirical_constant = etf_arith - empirical_constant_arith

    ideal_geo = approximate_geometric_return(ideal_arith, abs(float(target_leverage)) * underlying_vol)
    empirical_constant_geo = approximate_geometric_return(
        empirical_constant_arith,
        abs(float(ratio.mean())) * underlying_vol,
    )
    empirical_geo = approximate_geometric_return(etf_arith, etf_vol)
    volatility_drag = empirical_geo - etf_arith

    warnings = []
    if covariance_annualized <= thresholds.negative_covariance_warning:
        warnings.append("negative_ratio_return_covariance")
    if abs(float(ratio.mean()) - float(target_leverage)) >= thresholds.tracking_error_warning:
        warnings.append("average_effective_leverage_away_from_target")
    if volatility_drag <= thresholds.volatility_drag_warning:
        warnings.append("large_volatility_drag")

    return {
        "rows": int(len(returns)),
        "ratio_rows": int(len(ratio)),
        "excluded_small_underlying_return_rows": int(len(returns) - len(ratio_raw)),
        "target_leverage": float(target_leverage),
        "average_effective_leverage": float(ratio.mean()),
        "effective_leverage_std": float(ratio.std(ddof=0)),
        "underlying_arithmetic_return": underlying_arith,
        "underlying_volatility": underlying_vol,
        "etf_arithmetic_return": etf_arith,
        "etf_volatility": etf_vol,
        "ideal_constant_leverage_arithmetic_return": ideal_arith,
        "empirical_constant_leverage_arithmetic_return": empirical_constant_arith,
        "covariance_ratio_underlying_return": covariance_annualized,
        "arithmetic_gap_vs_ideal": arithmetic_gap_vs_ideal,
        "arithmetic_gap_vs_empirical_constant": arithmetic_gap_vs_empirical_constant,
        "ideal_constant_leverage_geometric_estimate": ideal_geo,
        "empirical_constant_leverage_geometric_estimate": empirical_constant_geo,
        "empirical_geometric_estimate": empirical_geo,
        "volatility_drag_estimate": volatility_drag,
        "warnings": warnings,
    }


def rolling_timing_anomaly(
    etf_prices: pd.Series,
    underlying_prices: pd.Series,
    *,
    target_leverage: float,
    window: int,
    thresholds: TimingAnomalyThresholds = TimingAnomalyThresholds(),
) -> pd.DataFrame:
    prices = pd.concat(
        [etf_prices.astype(float).rename("etf"), underlying_prices.astype(float).rename("underlying")],
        axis=1,
    ).dropna()
    records: list[dict[str, Any]] = []
    for end_pos in range(window, len(prices) + 1):
        sample = prices.iloc[end_pos - window : end_pos]
        try:
            summary = summarize_timing_anomaly(
                sample["etf"],
                sample["underlying"],
                target_leverage=target_leverage,
                thresholds=thresholds,
            )
        except ValueError:
            continue
        summary["date"] = sample.index[-1]
        records.append(summary)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).set_index("date").sort_index()
