#!/usr/bin/env python3
"""Research sweep for adding ncf_2330 as a TSMC/0050 health overlay.

Read-only with respect to production strategy code. Writes one JSON report to
results/. The overlay tested here mirrors the live daily-signal guard:
trim 00631L only when TSMC weakness confirms 00631L's own NCF risk.
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize, _resolve  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics  # noqa: E402
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402


START = "2025-01-02"
END = "2026-07-02"
INITIAL_VALUE = 1_000_000.0
TSMC_WEIGHT_ASSUMPTION = 0.55

PANEL_2330 = PROJECT_ROOT / "results" / "ncf_2330_improved_panel_latest_20260703.csv"
PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
OUT = PROJECT_ROOT / "results" / "a2118_ncf_2330_tsmc_overlay_sweep_20260704.json"

TSMC_H20_MAX_VALUES = [0.45, 0.50, 0.55]
TSMC_TAIL_MIN_VALUES = [0.45, 0.50, 0.55]
L631_H20_MAX_VALUES = [0.40, 0.45, 0.50]
L631_TAIL_MIN_VALUES = [0.50, 0.55, 0.60]
TRIM_FRACTIONS = [0.15, 0.25, 0.35, 0.50]


def _load_panel(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index).normalize()
    keep = [
        "prob_up_h20",
        "prob_fwd_mdd_gt5_h20",
        "confidence",
        "tail_reward_risk_score_h20",
    ]
    cols = [col for col in keep if col in df.columns]
    return df[cols].rename(columns={col: f"{prefix}_{col}" for col in cols})


def _load_tsmc_close(db_path: Path, start: str, end: str) -> pd.Series:
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance'
              AND ticker = '2330.TW'
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    if df.empty:
        raise RuntimeError("Missing external_market_ohlcv rows for 2330.TW")
    out = df.set_index(pd.to_datetime(df["dt"]).dt.normalize())["close"].astype(float)
    return out[~out.index.duplicated()].sort_index()


def _build_signal_frame(db_path: Path, frame: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(frame.index).normalize()
    load_start = str((idx.min() - pd.Timedelta(days=80)).date())
    prices = _load_prices(_resolve(db_path), ["0050.TW", "00631L.TW"], load_start, str(idx.max().date()))
    tsmc = _load_tsmc_close(db_path, load_start, str(idx.max().date()))
    panel = _load_panel(PANEL_2330, "tsmc").join(_load_panel(PANEL_631L, "l631"), how="outer")
    signal = panel.reindex(idx).copy()
    signal["ret_2330_5d"] = tsmc.pct_change(5).reindex(idx)
    signal["ret_0050_5d"] = prices["0050.TW"].pct_change(5).reindex(idx)
    signal["ret_00631l_5d"] = prices["00631L.TW"].pct_change(5).reindex(idx)
    signal["ret_0050_ex_tsmc_5d"] = (
        signal["ret_0050_5d"] - TSMC_WEIGHT_ASSUMPTION * signal["ret_2330_5d"]
    ) / (1.0 - TSMC_WEIGHT_ASSUMPTION)
    signal["execution_regime"] = frame["execution_regime"].astype(str).reindex(idx)
    signal["portfolio_value"] = frame["portfolio_value"].astype(float).reindex(idx)
    return signal


def _trimmed_weights(golden_weights: dict[str, float], trim_fraction: float) -> dict[str, float]:
    weights = dict(golden_weights)
    shift = float(weights.get("00631L.TW", 0.0)) * float(trim_fraction)
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) - shift
    weights["cash"] = float(weights.get("cash", 0.0)) + shift
    return _normalize(weights)


def _trigger_mask(
    signal: pd.DataFrame,
    *,
    tsmc_h20_max: float,
    tsmc_tail_min: float,
    l631_h20_max: float,
    l631_tail_min: float,
) -> pd.Series:
    tsmc_model_weak = (
        (signal["tsmc_prob_up_h20"] < tsmc_h20_max)
        | (signal["tsmc_prob_fwd_mdd_gt5_h20"] >= tsmc_tail_min)
    )
    tsmc_price_weak = (
        (signal["ret_2330_5d"] <= -0.02)
        & (signal["ret_0050_ex_tsmc_5d"] <= 0.0)
    )
    l631_weak = (
        (signal["l631_prob_up_h20"] <= l631_h20_max)
        | (signal["l631_prob_fwd_mdd_gt5_h20"] >= l631_tail_min)
    )
    return (
        (signal["execution_regime"] == "golden1")
        & (tsmc_model_weak | tsmc_price_weak)
        & l631_weak
    ).fillna(False)


def _max_drawdown_from_entry(curve: pd.Series, dates: pd.DatetimeIndex, horizon: int = 20) -> float | None:
    values: list[float] = []
    for dt in dates:
        if dt not in curve.index:
            continue
        loc = curve.index.get_loc(dt)
        if isinstance(loc, slice):
            continue
        end = min(int(loc) + horizon, len(curve) - 1)
        segment = curve.iloc[int(loc): end + 1]
        if len(segment) > 1:
            values.append(float((segment / segment.iloc[0] - 1.0).min()))
    return min(values) if values else None


def _run_variant(
    *,
    signal: pd.DataFrame,
    total_return_prices: pd.DataFrame,
    base_regimes: pd.Series,
    base_weights: dict[str, dict[str, float]],
    initial_value: float,
    trim_fraction: float,
    tsmc_h20_max: float,
    tsmc_tail_min: float,
    l631_h20_max: float,
    l631_tail_min: float,
) -> dict[str, Any]:
    mask = _trigger_mask(
        signal,
        tsmc_h20_max=tsmc_h20_max,
        tsmc_tail_min=tsmc_tail_min,
        l631_h20_max=l631_h20_max,
        l631_tail_min=l631_tail_min,
    )
    regime_name = f"tsmc_trim_{trim_fraction:.2f}"
    regimes = base_regimes.copy()
    regimes.loc[mask] = regime_name
    weights_by_regime = dict(base_weights)
    weights_by_regime[regime_name] = _trimmed_weights(base_weights["golden1"], trim_fraction)
    curve, sim = _simulate_costed_curve(
        total_return_prices,
        regimes,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    metrics = _metrics(curve, initial_value)
    trigger_dates = pd.DatetimeIndex(mask[mask].index)
    return {
        "params": {
            "tsmc_h20_max": tsmc_h20_max,
            "tsmc_tail_min": tsmc_tail_min,
            "l631_h20_max": l631_h20_max,
            "l631_tail_min": l631_tail_min,
            "trim_fraction": trim_fraction,
        },
        "metrics": metrics,
        "execution": sim,
        "trigger_days": int(mask.sum()),
        "trigger_dates": [str(dt.date()) for dt in trigger_dates],
        "worst_20d_drawdown_after_trigger": _max_drawdown_from_entry(curve, trigger_dates),
    }


def _score_variant(item: dict[str, Any], baseline: dict[str, Any]) -> tuple[float, float, float, int]:
    metrics = item["metrics"]
    return (
        float(metrics["max_drawdown"]) - float(baseline["max_drawdown"]),
        float(metrics["final_value"]) - float(baseline["final_value"]),
        float(metrics["sharpe_ratio"]) - float(baseline["sharpe_ratio"]),
        -int(item["trigger_days"]),
    )


def main() -> None:
    report, frame = run_latest(START, END, INITIAL_VALUE, DB_PATH, DEFAULT_LATEST_STRATEGY)
    signal = _build_signal_frame(DB_PATH, frame)
    total_return_prices, dividend_coverage = _load_total_return_prices(DB_PATH, frame.index)
    total_return_prices = total_return_prices.reindex(frame.index).ffill()
    base_regimes = frame["execution_regime"].astype(str)
    base_weights = {
        key: dict(value)
        for key, value in (report.get("base_weights") or report.get("weights") or {}).items()
    }
    baseline_metrics = report["metrics"]
    baseline_execution = report["execution"]

    variants = []
    for tsmc_h20_max, tsmc_tail_min, l631_h20_max, l631_tail_min, trim_fraction in product(
        TSMC_H20_MAX_VALUES,
        TSMC_TAIL_MIN_VALUES,
        L631_H20_MAX_VALUES,
        L631_TAIL_MIN_VALUES,
        TRIM_FRACTIONS,
    ):
        variants.append(
            _run_variant(
                signal=signal,
                total_return_prices=total_return_prices,
                base_regimes=base_regimes,
                base_weights=base_weights,
                initial_value=INITIAL_VALUE,
                trim_fraction=trim_fraction,
                tsmc_h20_max=tsmc_h20_max,
                tsmc_tail_min=tsmc_tail_min,
                l631_h20_max=l631_h20_max,
                l631_tail_min=l631_tail_min,
            )
        )

    for item in variants:
        m = item["metrics"]
        item["delta_vs_baseline"] = {
            "final_value": float(m["final_value"]) - float(baseline_metrics["final_value"]),
            "sharpe_ratio": float(m["sharpe_ratio"]) - float(baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(m["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
            "transaction_cost": float(item["execution"]["transaction_cost"]) - float(baseline_execution["transaction_cost"]),
            "rebalance_count": int(item["execution"]["rebalance_count"]) - int(baseline_execution["rebalance_count"]),
        }

    variants_sorted = sorted(variants, key=lambda item: _score_variant(item, baseline_metrics), reverse=True)
    variants_by_final = sorted(
        variants,
        key=lambda item: item["delta_vs_baseline"]["final_value"],
        reverse=True,
    )
    variants_by_mdd = sorted(
        variants,
        key=lambda item: item["delta_vs_baseline"]["max_drawdown"],
        reverse=True,
    )
    variants_by_sharpe = sorted(
        variants,
        key=lambda item: item["delta_vs_baseline"]["sharpe_ratio"],
        reverse=True,
    )
    production_like = [
        item for item in variants
        if item["params"] == {
            "tsmc_h20_max": 0.50,
            "tsmc_tail_min": 0.50,
            "l631_h20_max": 0.45,
            "l631_tail_min": 0.50,
            "trim_fraction": 0.25,
        }
    ][0]

    result = {
        "experiment": "a2118_ncf_2330_tsmc_overlay_sweep",
        "window": {"start": START, "end": END, "rows": int(len(frame))},
        "baseline": {
            "metrics": baseline_metrics,
            "execution": baseline_execution,
            "strategy_id": report.get("active_strategy_id"),
            "today_regime": report.get("today_regime"),
        },
        "production_like_overlay": production_like,
        "summary": {
            "variants_with_final_value_improvement": int(
                sum(item["delta_vs_baseline"]["final_value"] > 0 for item in variants)
            ),
            "variants_with_mdd_improvement": int(
                sum(item["delta_vs_baseline"]["max_drawdown"] > 0 for item in variants)
            ),
            "variants_with_sharpe_improvement": int(
                sum(item["delta_vs_baseline"]["sharpe_ratio"] > 0 for item in variants)
            ),
            "best_by_final_value": variants_by_final[0],
            "best_by_max_drawdown": variants_by_mdd[0],
            "best_by_sharpe": variants_by_sharpe[0],
        },
        "top_by_mdd_then_value": variants_sorted[:15],
        "top_by_final_value": variants_by_final[:15],
        "top_by_sharpe": variants_by_sharpe[:15],
        "all_variants_count": len(variants),
        "sweep_space": {
            "tsmc_h20_max": TSMC_H20_MAX_VALUES,
            "tsmc_tail_min": TSMC_TAIL_MIN_VALUES,
            "l631_h20_max": L631_H20_MAX_VALUES,
            "l631_tail_min": L631_TAIL_MIN_VALUES,
            "trim_fraction": TRIM_FRACTIONS,
            "tsmc_price_weak_condition": "ret_2330_5d <= -0.02 and ret_0050_ex_tsmc_5d <= 0",
            "tsmc_weight_assumption": TSMC_WEIGHT_ASSUMPTION,
        },
        "inputs": {
            "panel_2330": str(PANEL_2330.relative_to(PROJECT_ROOT)),
            "panel_631l": str(PANEL_631L.relative_to(PROJECT_ROOT)),
            "manifest": str(DEFAULT_LATEST_STRATEGY.relative_to(PROJECT_ROOT)),
            "db": str(DB_PATH.relative_to(PROJECT_ROOT)),
        },
        "dividend_coverage": dividend_coverage,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({
        "saved": str(OUT),
        "baseline": baseline_metrics,
        "production_like": {
            "params": production_like["params"],
            "metrics": production_like["metrics"],
            "delta_vs_baseline": production_like["delta_vs_baseline"],
            "trigger_days": production_like["trigger_days"],
            "trigger_dates": production_like["trigger_dates"],
        },
        "top_5": [
            {
                "params": item["params"],
                "delta_vs_baseline": item["delta_vs_baseline"],
                "trigger_days": item["trigger_days"],
            }
            for item in variants_sorted[:5]
        ],
        "summary": {
            "variants_with_final_value_improvement": result["summary"]["variants_with_final_value_improvement"],
            "variants_with_mdd_improvement": result["summary"]["variants_with_mdd_improvement"],
            "variants_with_sharpe_improvement": result["summary"]["variants_with_sharpe_improvement"],
            "best_by_final_value": {
                "params": result["summary"]["best_by_final_value"]["params"],
                "delta_vs_baseline": result["summary"]["best_by_final_value"]["delta_vs_baseline"],
                "trigger_days": result["summary"]["best_by_final_value"]["trigger_days"],
            },
            "best_by_max_drawdown": {
                "params": result["summary"]["best_by_max_drawdown"]["params"],
                "delta_vs_baseline": result["summary"]["best_by_max_drawdown"]["delta_vs_baseline"],
                "trigger_days": result["summary"]["best_by_max_drawdown"]["trigger_days"],
            },
        },
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
