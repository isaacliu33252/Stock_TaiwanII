#!/usr/bin/env python3
"""Evaluate 2604.02126 AR/HAR-style robust hedge forecast variants."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2604_02126_robust_hedge_review import (
    DEFAULT_DB,
    DEFAULT_LATEST_STRATEGY,
    DEFAULT_LETF_READINESS,
    SOURCE_PAPER,
    _finite,
    _hedge_effectiveness,
    _load_close_panel,
    _load_optional,
    _resolve,
    _series_summary,
    _strategy_weight,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_forecast_variants.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_forecast_variants.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_02126_forecast_variants/history"


def _rolling_mean_forecast(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean().shift(1)


def _ar1_forecast(series: pd.Series, window: int) -> pd.Series:
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for idx in range(window, len(values)):
        hist = values[idx - window : idx]
        if not np.isfinite(hist).all():
            continue
        y = hist[1:]
        x = hist[:-1]
        x_mean = x.mean()
        denom = float(np.square(x - x_mean).sum())
        if denom <= 1e-18:
            out[idx] = float(y.mean())
            continue
        phi = float(((x - x_mean) * (y - y.mean())).sum() / denom)
        alpha = float(y.mean() - phi * x_mean)
        out[idx] = alpha + phi * hist[-1]
    return pd.Series(out, index=series.index).clip(lower=0.0 if (series >= 0).all() else None)


def _har_lite_forecast(series: pd.Series, window: int) -> pd.Series:
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for idx in range(max(window, 23), len(values)):
        start = idx - window
        rows = []
        target = []
        for t in range(max(start + 22, 22), idx):
            lag1 = values[t - 1]
            lag5 = values[t - 5 : t].mean()
            lag22 = values[t - 22 : t].mean()
            y = values[t]
            if np.isfinite([lag1, lag5, lag22, y]).all():
                rows.append([1.0, lag1, lag5, lag22])
                target.append(y)
        if len(rows) < 12:
            continue
        beta, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(target), rcond=None)
        latest_x = np.asarray([1.0, values[idx - 1], values[idx - 5 : idx].mean(), values[idx - 22 : idx].mean()])
        if np.isfinite(latest_x).all():
            out[idx] = float(latest_x @ beta)
    return pd.Series(out, index=series.index).clip(lower=0.0 if (series >= 0).all() else None)


def _forecast(series: pd.Series, window: int, model: str) -> pd.Series:
    if model == "rolling_mean":
        return _rolling_mean_forecast(series, window)
    if model == "ar1":
        return _ar1_forecast(series, window)
    if model == "har_lite":
        return _har_lite_forecast(series, window)
    raise ValueError(f"Unknown forecast model: {model}")


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator.abs() > 1e-12)


def _evaluate_model(
    returns: pd.DataFrame,
    *,
    asset_ticker: str,
    hedge_ticker: str,
    model: str,
    window: int,
    uncertainty_window: int,
    cap: float,
    tail_quantile: float,
) -> dict[str, Any]:
    asset = returns[asset_ticker]
    hedge = returns[hedge_ticker]
    rv = hedge.pow(2)
    rcov = asset * hedge
    var_forecast = _forecast(rv, window, model)
    cov_forecast = _forecast(rcov, window, model)
    theta_var = (rv - var_forecast).rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)
    theta_cov = (rcov - cov_forecast).rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)

    standard_ratio = _safe_div(cov_forecast, var_forecast)
    robust_ratio = _safe_div(cov_forecast, var_forecast + theta_var)
    full_box_ratio = np.sign(cov_forecast) * (cov_forecast.abs() - theta_cov).clip(lower=0.0)
    full_box_ratio = _safe_div(full_box_ratio, var_forecast + theta_var)

    standard_exposure = (-standard_ratio).clip(lower=0.0, upper=cap)
    robust_exposure = (-robust_ratio).clip(lower=0.0, upper=cap)
    full_box_exposure = (-full_box_ratio).clip(lower=0.0, upper=cap)
    standard_hedged = asset - standard_ratio * hedge
    robust_hedged = asset - robust_ratio * hedge
    full_box_hedged = asset - full_box_ratio * hedge

    base_turnover = standard_exposure.diff().abs().dropna().mean()
    base_std = standard_exposure.dropna().std(ddof=0)
    robust_turnover = robust_exposure.diff().abs().dropna().mean()
    robust_std = robust_exposure.dropna().std(ddof=0)
    robust_eff = _hedge_effectiveness(asset, robust_hedged, tail_quantile=tail_quantile)
    standard_eff = _hedge_effectiveness(asset, standard_hedged, tail_quantile=tail_quantile)
    full_box_eff = _hedge_effectiveness(asset, full_box_hedged, tail_quantile=tail_quantile)
    common = pd.DataFrame(
        {
            "var_forecast": var_forecast,
            "cov_forecast": cov_forecast,
            "theta_var": theta_var,
            "standard_ratio": standard_ratio,
            "robust_ratio": robust_ratio,
        }
    ).dropna()

    robust_che = _finite(robust_eff.get("conditional_hedge_effectiveness"))
    standard_che = _finite(standard_eff.get("conditional_hedge_effectiveness"))
    turnover_delta = (
        _finite(1.0 - robust_turnover / base_turnover)
        if base_turnover is not None and abs(base_turnover) > 1e-12
        else None
    )
    std_delta = _finite(1.0 - robust_std / base_std) if base_std is not None and abs(base_std) > 1e-12 else None
    passes_shadow_filter = (
        turnover_delta is not None
        and turnover_delta >= 0.0
        and std_delta is not None
        and std_delta >= 0.0
        and robust_che is not None
        and standard_che is not None
        and robust_che >= standard_che
    )

    return {
        "model": model,
        "window": window,
        "uncertainty_window": uncertainty_window,
        "max_hedge_weight": cap,
        "observation_count": int(common.shape[0]),
        "data_start_after_warmup": str(common.index.min()) if not common.empty else None,
        "data_end_after_warmup": str(common.index.max()) if not common.empty else None,
        "forecast_summary": {
            "hedge_variance_forecast": _series_summary(var_forecast),
            "asset_hedge_covariance_forecast": _series_summary(cov_forecast),
            "hedge_variance_uncertainty_theta": _series_summary(theta_var),
            "covariance_uncertainty_theta": _series_summary(theta_cov),
        },
        "standard": {
            "latest_exposure": _finite(standard_exposure.dropna().iloc[-1]) if not standard_exposure.dropna().empty else None,
            "mean_abs_daily_turnover": _finite(base_turnover),
            "exposure_std": _finite(base_std),
            "effectiveness": standard_eff,
        },
        "robust_variance_only": {
            "latest_exposure": _finite(robust_exposure.dropna().iloc[-1]) if not robust_exposure.dropna().empty else None,
            "mean_abs_daily_turnover": _finite(robust_turnover),
            "exposure_std": _finite(robust_std),
            "turnover_reduction_vs_standard": turnover_delta,
            "exposure_std_reduction_vs_standard": std_delta,
            "effectiveness": robust_eff,
        },
        "robust_full_box": {
            "latest_exposure": _finite(full_box_exposure.dropna().iloc[-1]) if not full_box_exposure.dropna().empty else None,
            "zero_or_near_zero_exposure_rate": _finite((full_box_exposure.fillna(0.0) <= 1e-6).mean()),
            "effectiveness": full_box_eff,
        },
        "passes_shadow_filter": passes_shadow_filter,
    }


def build_forecast_variant_review(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    start: str = "2020-01-01",
    asset_ticker: str = "0050.TW",
    hedge_ticker: str = "00632R.TW",
    models: list[str] | None = None,
    window: int = 126,
    uncertainty_window: int = 126,
    cap: float = 0.30,
    tail_quantile: float = 0.25,
    letf_readiness_path: Path = DEFAULT_LETF_READINESS,
    latest_strategy_path: Path = DEFAULT_LATEST_STRATEGY,
) -> dict[str, Any]:
    model_values = models or ["rolling_mean", "ar1", "har_lite"]
    panel = _load_close_panel(db_path, tickers=[asset_ticker, hedge_ticker], start=start, as_of=as_of)
    close = panel[[asset_ticker, hedge_ticker]].dropna() if all(ticker in panel.columns for ticker in [asset_ticker, hedge_ticker]) else pd.DataFrame()
    returns = np.log(close / close.shift(1)).dropna() if not close.empty else pd.DataFrame(columns=[asset_ticker, hedge_ticker])
    results = [
        _evaluate_model(
            returns,
            asset_ticker=asset_ticker,
            hedge_ticker=hedge_ticker,
            model=model,
            window=window,
            uncertainty_window=uncertainty_window,
            cap=cap,
            tail_quantile=tail_quantile,
        )
        for model in model_values
        if not returns.empty
    ]
    eligible = [row for row in results if row["passes_shadow_filter"]]
    blockers = [
        "research_only_forecast_variant_review",
        "daily_close_proxy_not_high_frequency_realized_covariance",
        "letf_readiness_blocks_00632r_open",
        "live_hedge_policy_not_validated_for_robust_ratio",
        "transaction_cost_and_execution_slippage_not_revalidated",
    ]
    if not eligible:
        blockers.append("no_forecast_variant_passed_shadow_filter")
    if not results:
        blockers.append("missing_required_ohlcv")

    latest_strategy = _load_optional(latest_strategy_path)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_02126_forecast_variants",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": str(close.index.max()) if not close.empty else None,
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "Hedging market risk and uncertainty via a robust portfolio approach",
            "imported_concept": "AR/HAR-style volatility and covariance forecast variants for robust hedge sizing",
        },
        "policy": "research_only_forecast_variants_no_00632r_open_no_weight_change",
        "status": "blocked_for_live_promotion",
        "data": {
            "db_path": str(db_path),
            "start": start,
            "asset_ticker": asset_ticker,
            "hedge_ticker": hedge_ticker,
            "return_type": "daily_log_return_from_close",
        },
        "latest_strategy_context": {
            "path": str(latest_strategy_path),
            "latest_strategy_00632r_target_weight": _strategy_weight(latest_strategy, hedge_ticker),
        },
        "results": results,
        "eligible_variant_count": len(eligible),
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "forecast_variant_review_complete": bool(results),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "letf_tracking_error_effective_fee_readiness": str(letf_readiness_path),
            "latest_strategy_preview": str(latest_strategy_path),
        },
    }


def _fmt(value: Any, digits: int = 6) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# 2604.02126 Forecast Variant Review",
        "",
        f"Generated: `{review.get('generated_at')}`",
        f"As of: `{review.get('as_of')}`",
        f"Status: `{review.get('status')}`",
        "",
        "## Decision",
        "",
        "- Do not change live target weights.",
        "- Do not open or increase `00632R.TW`.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Variants",
        "",
        "| model | obs | robust latest | turnover delta | std delta | robust CHE | standard CHE | pass |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in review.get("results", []):
        robust = row.get("robust_variance_only") or {}
        standard = row.get("standard") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("model")),
                    str(row.get("observation_count")),
                    _fmt(robust.get("latest_exposure")),
                    _fmt(robust.get("turnover_reduction_vs_standard")),
                    _fmt(robust.get("exposure_std_reduction_vs_standard")),
                    _fmt((robust.get("effectiveness") or {}).get("conditional_hedge_effectiveness")),
                    _fmt((standard.get("effectiveness") or {}).get("conditional_hedge_effectiveness")),
                    str(row.get("passes_shadow_filter")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{reason}`" for reason in review.get("blocking_reasons", []))
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"2604_02126_forecast_variants_{stamp}.json"


def write_review(
    review: dict[str, Any],
    output_path: Path,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_markdown(review) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-08-28")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--models", default="rolling_mean,ar1,har_lite")
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--uncertainty-window", type=int, default=126)
    parser.add_argument("--cap", type=float, default=0.30)
    parser.add_argument("--letf-readiness", default=str(DEFAULT_LETF_READINESS))
    parser.add_argument("--latest-strategy", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_forecast_variant_review(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        start=args.start,
        models=[item.strip() for item in args.models.split(",") if item.strip()],
        window=args.window,
        uncertainty_window=args.uncertainty_window,
        cap=args.cap,
        letf_readiness_path=_resolve(args.letf_readiness),
        latest_strategy_path=_resolve(args.latest_strategy),
    )
    output_md = None if not args.output_md else _resolve(args.output_md)
    write_review(review, _resolve(args.output), output_md, None if args.no_history else _resolve(args.history_dir))
    print(f"2604.02126 forecast variant review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "eligible_variant_count": review["eligible_variant_count"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
                "models": [row["model"] for row in review["results"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
