#!/usr/bin/env python3
"""Research-only conditional defensive cash-floor sweep for GroupA+ latest."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.latest import run_latest


VARIANT_REGIME_PREFIX = "shadow_defensive_cash_floor"


@dataclass(frozen=True)
class CashFloorVariant:
    name: str
    cash_floor: float
    ma_gap_max: float
    exit_momentum_max: float
    drawdown_max: float
    total_risk_min: int
    tail_risk_min: int


def _raise_cash_floor(weights: dict[str, float], cash_floor: float) -> dict[str, float]:
    base = _normalize(weights)
    current_cash = float(base.get("cash", 0.0) or 0.0)
    if current_cash >= cash_floor:
        return base
    risky_total = sum(float(base.get(ticker, 0.0) or 0.0) for ticker in TICKERS)
    if risky_total <= 0.0:
        return {**{ticker: 0.0 for ticker in TICKERS}, "cash": 1.0}
    raise_by = min(float(cash_floor) - current_cash, risky_total)
    scale = max((risky_total - raise_by) / risky_total, 0.0)
    adjusted = {ticker: float(base.get(ticker, 0.0) or 0.0) * scale for ticker in TICKERS}
    adjusted["cash"] = current_cash + raise_by
    return _normalize(adjusted)


def _activation_mask(frame: pd.DataFrame, variant: CashFloorVariant) -> pd.Series:
    regime = frame["execution_regime"].astype(str)
    ma_gap = pd.to_numeric(frame.get("ma_gap", 0.0), errors="coerce").fillna(0.0)
    exit_momentum = pd.to_numeric(frame.get("exit_momentum", 0.0), errors="coerce").fillna(0.0)
    drawdown = pd.to_numeric(frame.get("drawdown", 0.0), errors="coerce").fillna(0.0)
    total_risk = pd.to_numeric(frame.get("total_risk_score", 0), errors="coerce").fillna(0).astype(int)
    tail_risk = pd.to_numeric(frame.get("tail_risk_score", 0), errors="coerce").fillna(0).astype(int)

    # Codex 2026-08-14: keep this as a conditional shadow. It may only fire
    # inside the already-defensive latest regime and only while price action
    # is still weak; it must not create new live target weights.
    downtrend = (ma_gap <= variant.ma_gap_max) & (exit_momentum <= variant.exit_momentum_max)
    risk_confirmed = (
        (drawdown <= variant.drawdown_max)
        | (total_risk >= int(variant.total_risk_min))
        | (tail_risk >= int(variant.tail_risk_min))
    )
    return (regime == "group_a_plus_defensive") & downtrend & risk_confirmed


def _with_variant_regime(frame: pd.DataFrame, variant: CashFloorVariant) -> tuple[pd.Series, int, list[dict[str, Any]]]:
    mask = _activation_mask(frame, variant)
    regimes = frame["execution_regime"].astype(str).copy()
    variant_regime = f"{VARIANT_REGIME_PREFIX}_{variant.name}"
    regimes.loc[mask] = variant_regime
    transitions: list[dict[str, Any]] = []
    prior = False
    for dt, active in mask.items():
        active_bool = bool(active)
        if active_bool != prior:
            transitions.append({"date": str(pd.Timestamp(dt).date()), "action": "enter" if active_bool else "exit"})
        prior = active_bool
    if prior:
        transitions.append({"date": str(pd.Timestamp(mask.index[-1]).date()), "action": "open_at_window_end"})
    return regimes, int(mask.sum()), transitions


def _variant_grid() -> list[CashFloorVariant]:
    variants: list[CashFloorVariant] = []
    for cash_floor in (0.40, 0.45, 0.50, 0.55):
        for ma_gap_max in (0.00, -0.02, -0.05):
            for drawdown_max in (-0.05, -0.08, -0.11):
                for total_risk_min in (4, 6, 8):
                    for tail_risk_min in (1, 2, 99):
                        name = (
                            f"cf{int(cash_floor * 100)}"
                            f"_mg{int(abs(ma_gap_max) * 1000):03d}"
                            f"_dd{int(abs(drawdown_max) * 100):02d}"
                            f"_tr{total_risk_min}_tl{tail_risk_min}"
                        )
                        variants.append(
                            CashFloorVariant(
                                name=name,
                                cash_floor=cash_floor,
                                ma_gap_max=ma_gap_max,
                                exit_momentum_max=0.0,
                                drawdown_max=drawdown_max,
                                total_risk_min=total_risk_min,
                                tail_risk_min=tail_risk_min,
                            )
                        )
    return variants


def _clean_metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "delta_final": float(candidate["final_value"] - baseline["final_value"]),
        "delta_total_return": float(candidate["total_return"] - baseline["total_return"]),
        "delta_sharpe": float(candidate["sharpe_ratio"] - baseline["sharpe_ratio"]),
        "delta_sortino": float(candidate.get("sortino_ratio", 0.0) - baseline.get("sortino_ratio", 0.0)),
        "delta_mdd": float(candidate["max_drawdown"] - baseline["max_drawdown"]),
    }


def build_sweep_report(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    output_prefix: Path | None = None,
    top_n_frames: int = 1,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    latest_report, latest_frame = run_latest(start, end, initial_value, db)
    frame = latest_frame.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    base_weights = {name: _normalize(weights) for name, weights in dict(latest_report["base_weights"]).items()}
    costs = dict(latest_report["cost_assumptions"])
    total_return_prices, dividend_coverage = _load_total_return_prices(db, frame.index)

    baseline_curve, baseline_execution = _simulate_costed_curve(
        total_return_prices,
        frame["execution_regime"].astype(str),
        base_weights,
        initial_value,
        float(costs["commission_rate"]),
        float(costs["slippage_rate"]),
        float(costs["equity_etf_sell_tax"]),
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    defensive_weights = base_weights["group_a_plus_defensive"]
    for variant in _variant_grid():
        candidate_weights = dict(base_weights)
        variant_regime = f"{VARIANT_REGIME_PREFIX}_{variant.name}"
        candidate_weights[variant_regime] = _raise_cash_floor(defensive_weights, variant.cash_floor)
        regimes, active_days, transitions = _with_variant_regime(frame, variant)
        curve, execution = _simulate_costed_curve(
            total_return_prices,
            regimes,
            candidate_weights,
            initial_value,
            float(costs["commission_rate"]),
            float(costs["slippage_rate"]),
            float(costs["equity_etf_sell_tax"]),
        )
        metrics = _metrics(curve, initial_value)
        deltas = _clean_metric_delta(metrics, baseline_metrics)
        row = {
            "variant": variant.name,
            **asdict(variant),
            **metrics,
            **deltas,
            **{f"execution_{k}": v for k, v in execution.items()},
            "active_days": active_days,
            "transition_count": len(transitions),
            "formal_upgrade_pass": bool(
                deltas["delta_final"] >= -1e-9
                and deltas["delta_sortino"] >= -1e-9
                and deltas["delta_mdd"] >= -1e-9
            ),
        }
        rows.append(row)
        out = frame.copy()
        out["shadow_execution_regime"] = regimes
        out["shadow_portfolio_value"] = curve
        out["shadow_active"] = regimes == variant_regime
        frames[variant.name] = out

    ranked = sorted(
        rows,
        key=lambda row: (
            row["formal_upgrade_pass"],
            row["delta_final"],
            row["delta_sortino"],
            row["delta_mdd"],
            -row["execution_transaction_cost"],
        ),
        reverse=True,
    )
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_conditional_defensive_cash_floor_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "implementation_note": (
            "Codex 2026-08-14: research-only shadow. Raises cash only inside "
            "group_a_plus_defensive when downtrend/risk conditions are active; "
            "does not write live target weights or strategy manifest."
        ),
        "window": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": str(frame.index[0].date()),
            "actual_end": str(frame.index[-1].date()),
            "rows": int(len(frame)),
        },
        "baseline": {
            "metrics": baseline_metrics,
            "execution": baseline_execution,
            "defensive_days": int((frame["execution_regime"].astype(str) == "group_a_plus_defensive").sum()),
        },
        "cost_assumptions": costs,
        "dividend_coverage": dividend_coverage,
        "base_weights": base_weights,
        "variant_count": len(rows),
        "formal_upgrade_pass_count": sum(1 for row in rows if row["formal_upgrade_pass"]),
        "best": best,
        "rows": rows,
        "promotion_ready": False,
        "promotion_block_reason": (
            "single-window research shadow; require multi-window positive final/sortino/MDD "
            "and no recent-period drag before live integration"
        ),
    }
    if output_prefix is not None:
        prefix = output_prefix if output_prefix.is_absolute() else PROJECT_ROOT / output_prefix
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(rows).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
        for name in [row["variant"] for row in ranked[: max(int(top_n_frames), 0)]]:
            frames[name].to_csv(prefix.with_name(f"{prefix.name}_{name}_frame.csv"), encoding="utf-8-sig")
    return report, frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01-03")
    parser.add_argument("--end", default="2022-12-30")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-prefix", default="results/group_a_plus_conditional_defensive_cash_floor_shadow")
    parser.add_argument("--top-n-frames", type=int, default=1)
    args = parser.parse_args()

    report, _frames = build_sweep_report(
        args.start,
        args.end,
        args.initial_value,
        Path(args.db),
        Path(args.output_prefix),
        args.top_n_frames,
    )
    best = report["best"]
    print(f"JSON: {(PROJECT_ROOT / args.output_prefix).with_suffix('.json')}")
    print(
        "Best: "
        f"{best['variant']} final_delta={best['delta_final']:.2f} "
        f"sortino_delta={best['delta_sortino']:.4f} mdd_delta={best['delta_mdd']:.4f} "
        f"active_days={best['active_days']}"
    )
    print(f"Formal pass count: {report['formal_upgrade_pass_count']} / {report['variant_count']}")


if __name__ == "__main__":
    main()
