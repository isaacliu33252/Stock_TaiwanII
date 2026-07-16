#!/usr/bin/env python3
"""Portfolio-level shadow for H20 bearish + tail/reward-risk gate.

Read-only research.  This tests whether the episode-level candidate

    prob_up_h20 < 0.33 and tail_reward_risk_score_h20 < -0.30

adds value when implemented as an A21.18-style golden1 overlay, holding the
de-risked basket until prob_up_h5 >= 0.55.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import (  # noqa: E402
    DEFENSIVE_BASKETS,
    _load_total_return_prices,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (  # noqa: E402
    DEFAULT_DECISION_POINTER,
    _load,
    _load_policy_signal,
    _normalize,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.a2111 import _resolve_golden_signal_path  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402


DEFAULT_OUTPUT = Path("results/a2118_h20_tail_score_shadow_20260713.json")
DEFAULT_CSV = Path("results/a2118_h20_tail_score_shadow_20260713.csv")
DEFAULT_WINDOW_CSV = Path("results/a2118_h20_tail_score_shadow_windows_20260713.csv")
PANELS = {
    "oos_2017_2019": Path("results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
    "panel_2025_2026": Path("results/ncf_00631l_panel_latest_20260707.csv"),
}
CRASH_WINDOWS = {
    "trade_war_2018_full": ("2018-01-02", "2018-12-31"),
    "trade_war_2018_q4": ("2018-10-01", "2018-12-31"),
    "tariff_shock_2025": ("2025-03-17", "2025-04-30"),
    "late_bull_pullback_2025": ("2025-08-01", "2025-10-31"),
    "q1_2026_correction": ("2026-01-02", "2026-04-30"),
}
CONFIDENCE_GATES: tuple[float | None, ...] = (None, 0.30, 0.45, 0.55)
SHADOW_REGIME_PREFIX = "h20_tail_score_shadow"


def _custom_derisk_weights(
    golden_weights: dict[str, float],
    *,
    destination: str,
    intensity: float,
) -> dict[str, float]:
    weights = dict(golden_weights)
    shift = float(weights.get("00631L.TW", 0.0)) * float(intensity)
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) - shift
    if destination == "cash":
        weights["cash"] = float(weights.get("cash", 0.0)) + shift
    else:
        weights[destination] = float(weights.get(destination, 0.0)) + shift
    return _normalize(weights)


def _build_weights_by_regime(
    *,
    destination: str,
    intensity: float,
) -> tuple[dict[str, dict[str, float]], str]:
    policy_signal, _policy_signal_path = _load_policy_signal(DEFAULT_DECISION_POINTER)
    golden_signal = _load(_resolve_golden_signal_path())
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))
    regime = f"{SHADOW_REGIME_PREFIX}_{destination.replace('.', '').lower()}_{int(intensity * 100)}"
    return {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
        regime: _custom_derisk_weights(
            golden_weights,
            destination=destination,
            intensity=intensity,
        ),
    }, regime


def _load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    panel.index = pd.to_datetime(panel.index).normalize()
    return panel


def _apply_shadow_regime(
    base_regime: pd.Series,
    panel: pd.DataFrame,
    shadow_regime: str,
    *,
    h20_max: float,
    tail_score_max: float,
    confidence_min: float | None,
    h5_reentry_min: float,
) -> tuple[pd.Series, dict[str, Any]]:
    modified = base_regime.copy().astype(str)
    in_shadow = False
    events: list[dict[str, Any]] = []
    hold_days: list[str] = []

    for dt in modified.index:
        if str(base_regime.loc[dt]) != "golden1":
            in_shadow = False
            continue
        if dt not in panel.index:
            continue
        row = panel.loc[dt]
        h20 = row.get("prob_up_h20")
        h5 = row.get("prob_up_h5")
        confidence = row.get("confidence")
        tail_score = row.get("tail_reward_risk_score_h20")
        if pd.isna(h20) or pd.isna(tail_score):
            continue
        confidence_ok = (
            confidence_min is None
            or (pd.notna(confidence) and float(confidence) >= confidence_min)
        )
        is_entry = confidence_ok and float(h20) < h20_max and float(tail_score) < tail_score_max
        if not in_shadow and is_entry:
            in_shadow = True
            modified.loc[dt] = shadow_regime
            events.append(
                {
                    "date": str(dt.date()),
                    "prob_up_h20": round(float(h20), 4),
                    "prob_up_h5": round(float(h5), 4) if pd.notna(h5) else None,
                    "confidence": round(float(confidence), 4) if pd.notna(confidence) else None,
                    "tail_reward_risk_score_h20": round(float(tail_score), 4),
                }
            )
            continue
        if not in_shadow:
            continue
        if pd.notna(h5) and float(h5) >= h5_reentry_min:
            in_shadow = False
            continue
        modified.loc[dt] = shadow_regime
        hold_days.append(str(dt.date()))

    return modified, {
        "entry_events": events,
        "entry_event_count": len(events),
        "hold_days": hold_days,
        "total_shadow_days": len(events) + len(hold_days),
    }


def _window_metrics(values: pd.Series) -> dict[str, Any]:
    values = values.dropna().astype(float)
    if len(values) < 2:
        return {
            "rows": int(len(values)),
            "return": None,
            "max_drawdown": None,
            "worst_5d_return": None,
            "worst_20d_return": None,
            "expected_tail_loss_5pct": None,
            "time_under_water_days": None,
        }
    daily = values.pct_change().dropna()
    var_5pct = daily.quantile(0.05) if len(daily) else None
    tail = daily[daily <= var_5pct] if var_5pct is not None else pd.Series(dtype=float)
    underwater = values < values.cummax()
    return {
        "rows": int(len(values)),
        "return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
        "worst_5d_return": (
            float(values.pct_change(5).dropna().min())
            if len(values.pct_change(5).dropna())
            else None
        ),
        "worst_20d_return": (
            float(values.pct_change(20).dropna().min())
            if len(values.pct_change(20).dropna())
            else None
        ),
        "expected_tail_loss_5pct": float(tail.mean()) if len(tail) else None,
        "time_under_water_days": int(underwater.sum()),
    }


def _window_scorecard(
    baseline_curve: pd.Series,
    candidate_curve: pd.Series,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        common = baseline_curve.index.intersection(candidate_curve.index)
        idx = common[(common >= start_ts) & (common <= end_ts)]
        if len(idx) < 2:
            continue
        base = _window_metrics(baseline_curve.reindex(idx))
        cand = _window_metrics(candidate_curve.reindex(idx))
        out[name] = {
            "start": str(idx.min().date()),
            "end": str(idx.max().date()),
            "baseline": base,
            "candidate": cand,
            "delta": {
                "return": (
                    float(cand["return"] - base["return"])
                    if cand["return"] is not None and base["return"] is not None
                    else None
                ),
                "max_drawdown": (
                    float(cand["max_drawdown"] - base["max_drawdown"])
                    if cand["max_drawdown"] is not None and base["max_drawdown"] is not None
                    else None
                ),
                "worst_5d_return": (
                    float(cand["worst_5d_return"] - base["worst_5d_return"])
                    if cand["worst_5d_return"] is not None and base["worst_5d_return"] is not None
                    else None
                ),
                "worst_20d_return": (
                    float(cand["worst_20d_return"] - base["worst_20d_return"])
                    if cand["worst_20d_return"] is not None and base["worst_20d_return"] is not None
                    else None
                ),
                "expected_tail_loss_5pct": (
                    float(cand["expected_tail_loss_5pct"] - base["expected_tail_loss_5pct"])
                    if cand["expected_tail_loss_5pct"] is not None
                    and base["expected_tail_loss_5pct"] is not None
                    else None
                ),
                "time_under_water_days": (
                    int(cand["time_under_water_days"] - base["time_under_water_days"])
                    if cand["time_under_water_days"] is not None
                    and base["time_under_water_days"] is not None
                    else None
                ),
            },
        }
    return out


def _run_variant(
    *,
    panel_name: str,
    panel_path: Path,
    destination: str,
    intensity: float,
    confidence_min: float | None,
    initial_value: float,
    db_path: Path,
    h20_max: float,
    tail_score_max: float,
    h5_reentry_min: float,
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    start = str(panel.index.min().date())
    end = str(panel.index.max().date())
    baseline_report, baseline_frame = run_a2118(
        start,
        end,
        initial_value,
        db_path,
        ncf_panel_631l_path=None,
        chip_data_fallback_max_stale_days=10,
        risk_score_lookback_days=5,
        momentum_fast_exit_min=0.10,
        momentum_fast_exit_ma_gap_min=-0.08,
        exclude_zero_volume_rows=False,
    )
    weights_by_regime, shadow_regime = _build_weights_by_regime(
        destination=destination,
        intensity=intensity,
    )
    base_regime = baseline_frame["execution_regime"].astype(str)
    shadow_regime_series, overlay_info = _apply_shadow_regime(
        base_regime,
        panel,
        shadow_regime,
        h20_max=h20_max,
        tail_score_max=tail_score_max,
        confidence_min=confidence_min,
        h5_reentry_min=h5_reentry_min,
    )
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, baseline_frame.index)
    curve, sim_result = _simulate_costed_curve(
        total_return_prices,
        shadow_regime_series,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    metrics = _metrics(curve, initial_value)
    baseline_metrics = _metrics(baseline_frame["portfolio_value"], initial_value)
    window_scorecard = _window_scorecard(baseline_frame["portfolio_value"], curve)
    return {
        "panel": panel_name,
        "panel_path": str(panel_path),
        "start": start,
        "end": end,
        "destination": destination,
        "intensity": float(intensity),
        "confidence_min": confidence_min,
        "shadow_regime": shadow_regime,
        "params": {
            "h20_max": float(h20_max),
            "tail_score_max": float(tail_score_max),
            "confidence_min": confidence_min,
            "h5_reentry_min": float(h5_reentry_min),
        },
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "delta": {
            "final_value": float(metrics["final_value"] - baseline_metrics["final_value"]),
            "total_return": float(metrics["total_return"] - baseline_metrics["total_return"]),
            "sharpe_ratio": float(metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "transaction_cost": float(sim_result["transaction_cost"] - baseline_report["execution"]["transaction_cost"]),
            "rebalance_count": int(sim_result["rebalance_count"] - baseline_report["execution"]["rebalance_count"]),
        },
        "overlay": overlay_info,
        "simulation": sim_result,
        "dividend_coverage": dividend_coverage,
        "crash_window_scorecard": window_scorecard,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    for panel_name, panel_path in PANELS.items():
        for destination in ("cash", "00679B.TWO"):
            for intensity in (0.5, 1.0):
                for confidence_min in CONFIDENCE_GATES:
                    result = _run_variant(
                        panel_name=panel_name,
                        panel_path=panel_path,
                        destination=destination,
                        intensity=intensity,
                        confidence_min=confidence_min,
                        initial_value=args.initial_value,
                        db_path=Path(args.db),
                        h20_max=args.h20_max,
                        tail_score_max=args.tail_score_max,
                        h5_reentry_min=args.h5_reentry_min,
                    )
                    variants.append(result)
                    rows.append(
                        {
                            "panel": panel_name,
                            "destination": destination,
                            "intensity": intensity,
                            "confidence_min": confidence_min,
                            "entry_events": result["overlay"]["entry_event_count"],
                            "shadow_days": result["overlay"]["total_shadow_days"],
                            "final_value_delta": result["delta"]["final_value"],
                            "total_return_delta": result["delta"]["total_return"],
                            "sharpe_delta": result["delta"]["sharpe_ratio"],
                            "max_drawdown_delta": result["delta"]["max_drawdown"],
                            "transaction_cost_delta": result["delta"]["transaction_cost"],
                            "rebalance_count_delta": result["delta"]["rebalance_count"],
                        }
                    )
                    for window_name, score in result["crash_window_scorecard"].items():
                        delta = score["delta"]
                        window_rows.append(
                            {
                                "panel": panel_name,
                                "destination": destination,
                                "intensity": intensity,
                                "confidence_min": confidence_min,
                                "window": window_name,
                                "start": score["start"],
                                "end": score["end"],
                                "return_delta": delta["return"],
                                "max_drawdown_delta": delta["max_drawdown"],
                                "worst_5d_return_delta": delta["worst_5d_return"],
                                "worst_20d_return_delta": delta["worst_20d_return"],
                                "etl_5pct_delta": delta["expected_tail_loss_5pct"],
                                "time_under_water_days_delta": delta["time_under_water_days"],
                                "candidate_return": score["candidate"]["return"],
                                "baseline_return": score["baseline"]["return"],
                                "candidate_max_drawdown": score["candidate"]["max_drawdown"],
                                "baseline_max_drawdown": score["baseline"]["max_drawdown"],
                            }
                        )
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    window_csv_path = Path(args.window_csv)
    window_csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(window_rows).to_csv(window_csv_path, index=False, encoding="utf-8-sig")
    return {
        "schema_version": 1,
        "report_type": "a2118_h20_tail_score_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "method": (
            "A21.18-style golden1-only shadow: enter when prob_up_h20 < h20_max "
            "and tail_reward_risk_score_h20 < tail_score_max; optional predefined confidence gates; "
            "hold until prob_up_h5 >= h5_reentry_min."
        ),
        "confidence_gates": list(CONFIDENCE_GATES),
        "variants": variants,
        "csv": str(csv_path),
        "window_csv": str(window_csv_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--h20-max", type=float, default=0.33)
    parser.add_argument("--tail-score-max", type=float, default=-0.30)
    parser.add_argument("--h5-reentry-min", type=float, default=0.55)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--window-csv", default=str(DEFAULT_WINDOW_CSV))
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
    print(Path(args.csv).resolve())


if __name__ == "__main__":
    main()
