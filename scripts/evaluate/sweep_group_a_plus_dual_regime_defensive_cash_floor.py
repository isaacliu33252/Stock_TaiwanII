#!/usr/bin/env python3
"""Research-only dual-regime defensive cash-floor sweep for GroupA+ latest."""

from __future__ import annotations

import argparse
import json
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
from backtest_group_a_plus_policy_signal import _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.latest import run_latest
from scripts.evaluate.sweep_group_a_plus_conditional_defensive_cash_floor import (
    _clean_metric_delta,
    _raise_cash_floor,
)


CRASH_REGIME_PREFIX = "shadow_dual_cash_floor_crash"
SLOW_REGIME_PREFIX = "shadow_dual_cash_floor_slow"


@dataclass(frozen=True)
class DualCashFloorVariant:
    name: str
    crash_cash_floor: float
    slow_cash_floor: float
    crash_ma_gap_max: float
    crash_drawdown_max: float
    crash_total_risk_min: int
    crash_tail_risk_min: int
    slow_ma_gap_max: float
    slow_drawdown_max: float
    slow_total_risk_min: int
    slow_tail_risk_min: int
    slow_vol_ratio_min: float


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(frame.get(column, default), errors="coerce").fillna(default)


def _dual_masks(frame: pd.DataFrame, variant: DualCashFloorVariant) -> tuple[pd.Series, pd.Series]:
    regime = frame["execution_regime"].astype(str)
    ma_gap = _numeric(frame, "ma_gap")
    exit_momentum = _numeric(frame, "exit_momentum")
    drawdown = _numeric(frame, "drawdown")
    total_risk = _numeric(frame, "total_risk_score").astype(int)
    tail_risk = _numeric(frame, "tail_risk_score").astype(int)
    vol_ratio = _numeric(frame, "realized_vol_ratio_20_60", 1.0)

    defensive = regime == "group_a_plus_defensive"
    weak_momentum = exit_momentum <= 0.0
    # Codex 2026-08-14: crash has priority. Slow-bear is only a lower-floor
    # overlay for non-crash defensive days; this remains research-only.
    crash = (
        defensive
        & weak_momentum
        & (ma_gap <= variant.crash_ma_gap_max)
        & (
            (drawdown <= variant.crash_drawdown_max)
            | (total_risk >= int(variant.crash_total_risk_min))
            | (tail_risk >= int(variant.crash_tail_risk_min))
        )
    )
    slow = (
        defensive
        & weak_momentum
        & ~crash
        & (ma_gap <= variant.slow_ma_gap_max)
        & (vol_ratio >= variant.slow_vol_ratio_min)
        & (
            (drawdown <= variant.slow_drawdown_max)
            | (total_risk >= int(variant.slow_total_risk_min))
            | (tail_risk >= int(variant.slow_tail_risk_min))
        )
    )
    return crash, slow


def _with_dual_regime(frame: pd.DataFrame, variant: DualCashFloorVariant) -> tuple[pd.Series, dict[str, int]]:
    crash, slow = _dual_masks(frame, variant)
    regimes = frame["execution_regime"].astype(str).copy()
    regimes.loc[slow] = f"{SLOW_REGIME_PREFIX}_{variant.name}"
    regimes.loc[crash] = f"{CRASH_REGIME_PREFIX}_{variant.name}"
    return regimes, {
        "crash_active_days": int(crash.sum()),
        "slow_active_days": int(slow.sum()),
        "total_active_days": int((crash | slow).sum()),
    }


def _variant_grid() -> list[DualCashFloorVariant]:
    variants: list[DualCashFloorVariant] = []
    for crash_floor in (0.50, 0.55, 0.60):
        for slow_floor in (0.35, 0.40, 0.45, 0.50):
            for slow_ma_gap_max in (0.0, -0.02):
                for slow_drawdown_max in (-0.05, -0.08, -0.11):
                    for slow_total_risk_min in (4, 6, 8):
                        for slow_tail_risk_min in (1, 2, 99):
                            for slow_vol_ratio_min in (0.0, 0.8, 1.0):
                                name = (
                                    f"cr{int(crash_floor * 100)}"
                                    f"_sl{int(slow_floor * 100)}"
                                    f"_smg{int(abs(slow_ma_gap_max) * 1000):03d}"
                                    f"_sdd{int(abs(slow_drawdown_max) * 100):02d}"
                                    f"_str{slow_total_risk_min}_stl{slow_tail_risk_min}"
                                    f"_sv{int(slow_vol_ratio_min * 100):03d}"
                                )
                                variants.append(
                                    DualCashFloorVariant(
                                        name=name,
                                        crash_cash_floor=crash_floor,
                                        slow_cash_floor=slow_floor,
                                        crash_ma_gap_max=-0.05,
                                        crash_drawdown_max=-0.05,
                                        crash_total_risk_min=4,
                                        crash_tail_risk_min=1,
                                        slow_ma_gap_max=slow_ma_gap_max,
                                        slow_drawdown_max=slow_drawdown_max,
                                        slow_total_risk_min=slow_total_risk_min,
                                        slow_tail_risk_min=slow_tail_risk_min,
                                        slow_vol_ratio_min=slow_vol_ratio_min,
                                    )
                                )
    return variants


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
        crash_regime = f"{CRASH_REGIME_PREFIX}_{variant.name}"
        slow_regime = f"{SLOW_REGIME_PREFIX}_{variant.name}"
        candidate_weights[crash_regime] = _raise_cash_floor(defensive_weights, variant.crash_cash_floor)
        candidate_weights[slow_regime] = _raise_cash_floor(defensive_weights, variant.slow_cash_floor)
        regimes, activity = _with_dual_regime(frame, variant)
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
            **activity,
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
        out["shadow_crash_active"] = regimes == crash_regime
        out["shadow_slow_active"] = regimes == slow_regime
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
        "experiment": "group_a_plus_dual_regime_defensive_cash_floor_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "implementation_note": (
            "Codex 2026-08-14: research-only dual cash-floor shadow. Crash "
            "activation has priority over slow-bear activation. No live "
            "target weights, execution plans, or manifests are written."
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
        "rules": {
            "crash_priority": True,
            "crash": {
                "ma_gap_max": -0.05,
                "exit_momentum_max": 0.0,
                "drawdown_max": -0.05,
                "total_risk_min": 4,
                "tail_risk_min": 1,
            },
            "slow": "sweep over slower/broader defensive conditions excluding crash-active days, including a realized_vol_ratio_20_60 floor",
        },
        "cost_assumptions": costs,
        "dividend_coverage": dividend_coverage,
        "base_weights": base_weights,
        "variant_count": len(rows),
        "formal_upgrade_pass_count": sum(1 for row in rows if row["formal_upgrade_pass"]),
        "best": best,
        "rows": rows,
        "promotion_ready": False,
        "promotion_block_reason": "single-window research shadow; require common multi-window validation",
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
    parser.add_argument("--output-prefix", default="results/group_a_plus_dual_regime_defensive_cash_floor_shadow")
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
        f"crash_days={best['crash_active_days']} slow_days={best['slow_active_days']}"
    )
    print(f"Formal pass count: {report['formal_upgrade_pass_count']} / {report['variant_count']}")


if __name__ == "__main__":
    main()
