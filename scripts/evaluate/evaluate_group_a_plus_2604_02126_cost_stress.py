#!/usr/bin/env python3
"""Transaction-cost stress test for 2604.02126 robust hedge variants."""

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
    _load_close_panel,
    _resolve,
)
from scripts.evaluate.evaluate_group_a_plus_2604_02126_forecast_variants import _forecast, _safe_div


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_cost_stress.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_cost_stress.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_02126_cost_stress/history"


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_models(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _max_drawdown(log_returns: pd.Series) -> float | None:
    clean = log_returns.dropna()
    if clean.empty:
        return None
    wealth = np.exp(clean.cumsum())
    drawdown = wealth / wealth.cummax() - 1.0
    return _finite(drawdown.min())


def _perf(log_returns: pd.Series) -> dict[str, Any]:
    clean = log_returns.dropna()
    if clean.empty:
        return {"count": 0, "total_log_return": None, "annualized_sharpe": None, "max_drawdown": None}
    std = clean.std(ddof=0)
    return {
        "count": int(clean.shape[0]),
        "total_log_return": _finite(clean.sum()),
        "mean_daily_log_return": _finite(clean.mean()),
        "annualized_volatility": _finite(std * np.sqrt(252.0)),
        "annualized_sharpe": _finite(clean.mean() / std * np.sqrt(252.0)) if std and abs(std) > 1e-12 else None,
        "max_drawdown": _max_drawdown(clean),
    }


def _ratios(
    returns: pd.DataFrame,
    *,
    asset_ticker: str,
    hedge_ticker: str,
    model: str,
    window: int,
    uncertainty_window: int,
    cap: float,
) -> dict[str, pd.Series]:
    asset = returns[asset_ticker]
    hedge = returns[hedge_ticker]
    rv = hedge.pow(2)
    rcov = asset * hedge
    var_forecast = _forecast(rv, window, model)
    cov_forecast = _forecast(rcov, window, model)
    theta_var = (rv - var_forecast).rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)
    theta_cov = (rcov - cov_forecast).rolling(uncertainty_window).std(ddof=0).shift(1).clip(lower=0.0)
    standard = _safe_div(cov_forecast, var_forecast)
    robust = _safe_div(cov_forecast, var_forecast + theta_var)
    full_box = np.sign(cov_forecast) * (cov_forecast.abs() - theta_cov).clip(lower=0.0)
    full_box = _safe_div(full_box, var_forecast + theta_var)
    return {
        "standard": standard.clip(lower=-cap, upper=0.0),
        "robust_variance_only": robust.clip(lower=-cap, upper=0.0),
        "robust_full_box": full_box.clip(lower=-cap, upper=0.0),
    }


def _net_returns(asset: pd.Series, hedge: pd.Series, ratio: pd.Series, cost_bps: float) -> pd.Series:
    exposure = (-ratio).clip(lower=0.0)
    gross = asset - ratio * hedge
    cost = exposure.diff().abs().fillna(0.0) * (cost_bps / 10000.0)
    return gross - cost


def _evaluate_cost_row(
    returns: pd.DataFrame,
    *,
    asset_ticker: str,
    hedge_ticker: str,
    model: str,
    window: int,
    uncertainty_window: int,
    cap: float,
    cost_bps: float,
) -> dict[str, Any]:
    ratio_map = _ratios(
        returns,
        asset_ticker=asset_ticker,
        hedge_ticker=hedge_ticker,
        model=model,
        window=window,
        uncertainty_window=uncertainty_window,
        cap=cap,
    )
    asset = returns[asset_ticker]
    hedge = returns[hedge_ticker]
    method_perf = {
        name: _perf(_net_returns(asset, hedge, ratio, cost_bps))
        for name, ratio in ratio_map.items()
    }
    standard = method_perf["standard"]
    robust = method_perf["robust_variance_only"]
    robust_minus_standard = {
        "total_log_return": _finite((robust.get("total_log_return") or 0.0) - (standard.get("total_log_return") or 0.0)),
        "annualized_sharpe": _finite((robust.get("annualized_sharpe") or 0.0) - (standard.get("annualized_sharpe") or 0.0)),
        "max_drawdown": _finite((robust.get("max_drawdown") or 0.0) - (standard.get("max_drawdown") or 0.0)),
    }
    passes_cost_filter = (
        robust_minus_standard["total_log_return"] is not None
        and robust_minus_standard["total_log_return"] >= 0.0
        and robust_minus_standard["annualized_sharpe"] is not None
        and robust_minus_standard["annualized_sharpe"] >= 0.0
        and robust_minus_standard["max_drawdown"] is not None
        and robust_minus_standard["max_drawdown"] >= 0.0
    )
    return {
        "model": model,
        "cost_bps": cost_bps,
        "window": window,
        "uncertainty_window": uncertainty_window,
        "max_hedge_weight": cap,
        "methods": method_perf,
        "robust_minus_standard": robust_minus_standard,
        "passes_cost_filter": passes_cost_filter,
    }


def build_cost_stress(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = "2026-08-28",
    start: str = "2020-01-01",
    asset_ticker: str = "0050.TW",
    hedge_ticker: str = "00632R.TW",
    models: list[str] | None = None,
    cost_bps_values: list[float] | None = None,
    window: int = 126,
    uncertainty_window: int = 126,
    cap: float = 0.30,
) -> dict[str, Any]:
    model_values = models or ["rolling_mean", "ar1", "har_lite"]
    cost_values = cost_bps_values or [0.0, 5.0, 10.0, 20.0, 50.0]
    panel = _load_close_panel(db_path, tickers=[asset_ticker, hedge_ticker], start=start, as_of=as_of)
    close = panel[[asset_ticker, hedge_ticker]].dropna() if all(ticker in panel.columns for ticker in [asset_ticker, hedge_ticker]) else pd.DataFrame()
    returns = np.log(close / close.shift(1)).dropna() if not close.empty else pd.DataFrame(columns=[asset_ticker, hedge_ticker])
    rows = [
        _evaluate_cost_row(
            returns,
            asset_ticker=asset_ticker,
            hedge_ticker=hedge_ticker,
            model=model,
            window=window,
            uncertainty_window=uncertainty_window,
            cap=cap,
            cost_bps=cost_bps,
        )
        for model in model_values
        for cost_bps in cost_values
        if not returns.empty
    ]
    eligible = [row for row in rows if row["passes_cost_filter"]]
    blockers = [
        "research_only_transaction_cost_stress",
        "letf_readiness_blocks_00632r_open",
        "live_hedge_policy_not_validated_for_robust_ratio",
        "daily_close_proxy_not_high_frequency_realized_covariance",
    ]
    if not eligible:
        blockers.append("no_cost_scenario_passed_robust_vs_standard_filter")
    if not rows:
        blockers.append("missing_required_ohlcv")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_02126_cost_stress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": str(close.index.max()) if not close.empty else None,
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "Hedging market risk and uncertainty via a robust portfolio approach",
            "imported_concept": "transaction-cost stress for robust hedge turnover and net performance",
        },
        "policy": "research_only_cost_stress_no_00632r_open_no_weight_change",
        "status": "blocked_for_live_promotion",
        "data": {
            "db_path": str(db_path),
            "start": start,
            "asset_ticker": asset_ticker,
            "hedge_ticker": hedge_ticker,
            "return_type": "daily_log_return_from_close",
        },
        "grid": {
            "models": model_values,
            "cost_bps_values": cost_values,
            "window": window,
            "uncertainty_window": uncertainty_window,
            "max_hedge_weight": cap,
            "scenario_count": len(rows),
        },
        "rows": rows,
        "eligible_scenario_count": len(eligible),
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "cost_stress_complete": bool(rows),
            "cost_stress_passed": bool(eligible),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "letf_tracking_error_effective_fee_readiness": str(DEFAULT_LETF_READINESS),
            "latest_strategy_preview": str(DEFAULT_LATEST_STRATEGY),
        },
    }


def _fmt(value: Any, digits: int = 6) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2604.02126 Cost Stress",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"As of: `{report.get('as_of')}`",
        f"Status: `{report.get('status')}`",
        "",
        "## Decision",
        "",
        "- Do not change live target weights.",
        "- Do not open or increase `00632R.TW`.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Rows",
        "",
        "| model | cost bps | robust-standard return | robust-standard sharpe | robust-standard mdd | pass |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows", []):
        delta = row.get("robust_minus_standard") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("model")),
                    _fmt(row.get("cost_bps"), 1),
                    _fmt(delta.get("total_log_return")),
                    _fmt(delta.get("annualized_sharpe")),
                    _fmt(delta.get("max_drawdown")),
                    str(row.get("passes_cost_filter")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{reason}`" for reason in report.get("blocking_reasons", []))
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"2604_02126_cost_stress_{stamp}.json"


def write_report(
    report: dict[str, Any],
    output_path: Path,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, report.get("as_of")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default="2026-08-28")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--models", default="rolling_mean,ar1,har_lite")
    parser.add_argument("--cost-bps", default="0,5,10,20,50")
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--uncertainty-window", type=int, default=126)
    parser.add_argument("--cap", type=float, default=0.30)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_cost_stress(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        start=args.start,
        models=_parse_models(args.models),
        cost_bps_values=_parse_floats(args.cost_bps),
        window=args.window,
        uncertainty_window=args.uncertainty_window,
        cap=args.cap,
    )
    output_md = None if not args.output_md else _resolve(args.output_md)
    write_report(report, _resolve(args.output), output_md, None if args.no_history else _resolve(args.history_dir))
    print(f"2604.02126 cost stress: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "scenario_count": report["grid"]["scenario_count"],
                "eligible_scenario_count": report["eligible_scenario_count"],
                "cost_stress_passed": report["decision"]["cost_stress_passed"],
                "allow_00632r_open": report["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
