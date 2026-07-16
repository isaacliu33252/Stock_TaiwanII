#!/usr/bin/env python3
"""Evaluate A21.20 LETF compounding candidates on rolling windows.

Research-only.  This checks whether the preferred tuned threshold is broadly
stable across rolling windows rather than relying on a few fixed event windows.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.leveraged_compounding_regime import CompoundingRegimeThresholds
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import evaluate_window
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import PANEL_2017_2019, PANEL_2025_2026


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_compounding_rolling_windows_20260715.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "00631l_compounding_rolling_windows_20260715.csv"


ROBUST_THRESHOLDS = CompoundingRegimeThresholds(
    ar1_trend_min=0.05,
    ar1_revert_max=-0.15,
    variance_ratio_trend_min=1.02,
    variance_ratio_revert_max=0.98,
    trend_persistence_min=0.60,
    trend_persistence_revert_max=0.55,
    reversal_speed_revert_min=0.55,
    reversal_speed_trend_max=0.45,
    drawdown_recovery_revert_min=0.50,
    trend_score_min=4,
    mean_reversion_score_min=5,
)

PREFERRED_THRESHOLDS = CompoundingRegimeThresholds(
    ar1_trend_min=0.00,
    ar1_revert_max=-0.15,
    variance_ratio_trend_min=1.02,
    variance_ratio_revert_max=0.98,
    trend_persistence_min=0.50,
    trend_persistence_revert_max=0.55,
    reversal_speed_revert_min=0.55,
    reversal_speed_trend_max=0.50,
    drawdown_recovery_revert_min=0.50,
    trend_score_min=3,
    mean_reversion_score_min=5,
)


def _resolve_end_date(db_path: Path, requested_end: str) -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = '00631L.TW'").fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise RuntimeError("No OHLCV rows for 00631L.TW")
    return str(max_dt)[:10]


def _trading_dates(db_path: Path, start: str, end: str) -> list[str]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT dt
            FROM ohlcv
            WHERE ticker = '00631L.TW' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [start, end],
        ).fetchall()
    finally:
        con.close()
    return [str(row[0])[:10] for row in rows]


def build_rolling_windows(
    dates: list[str],
    *,
    window_days: int,
    step_days: int,
    max_windows: int | None = None,
) -> list[tuple[str, str, str, str, str]]:
    windows: list[tuple[str, str, str, str, str]] = []
    if window_days <= 1 or step_days <= 0:
        raise ValueError("window_days must be > 1 and step_days must be > 0")
    for idx in range(0, max(len(dates) - window_days + 1, 0), step_days):
        start = dates[idx]
        end = dates[idx + window_days - 1]
        panel = PANEL_2017_2019 if start < "2020-01-01" else PANEL_2025_2026
        label = f"roll_{start}_{end}"
        windows.append((label, start, end, panel, "rolling_window"))
    if max_windows is not None and max_windows > 0 and len(windows) > max_windows:
        return windows[-max_windows:]
    return windows


def _delta(window: dict[str, Any], key: str) -> float:
    return float((window.get("delta_vs_baseline") or {}).get(key, 0.0) or 0.0)


def _metrics(window: dict[str, Any]) -> dict[str, Any]:
    guarded = window.get("mean_reversion_no_add") if isinstance(window.get("mean_reversion_no_add"), dict) else {}
    return guarded.get("metrics") if isinstance(guarded.get("metrics"), dict) else {}


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "positive_count": 0, "positive_rate": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "positive_rate": sum(value > 0.0 for value in values) / len(values),
        "median": float(statistics.median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def evaluate_rolling_windows(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    preferred_thresholds = CompoundingRegimeThresholds(
        ar1_trend_min=float(args.preferred_ar1_trend_min),
        ar1_revert_max=-0.15,
        variance_ratio_trend_min=1.02,
        variance_ratio_revert_max=0.98,
        trend_persistence_min=float(args.preferred_trend_persistence_min),
        trend_persistence_revert_max=0.55,
        reversal_speed_revert_min=0.55,
        reversal_speed_trend_max=float(args.preferred_reversal_speed_trend_max),
        drawdown_recovery_revert_min=0.50,
        trend_score_min=int(args.preferred_trend_score_min),
        mean_reversion_score_min=5,
    )
    end = _resolve_end_date(db_path, args.end)
    dates = _trading_dates(db_path, args.start, end)
    windows = build_rolling_windows(
        dates,
        window_days=int(args.window_days),
        step_days=int(args.step_days),
        max_windows=(None if int(args.max_windows) <= 0 else int(args.max_windows)),
    )
    rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for label, start, win_end, panel, kind in windows:
        print(f"Evaluating {label}")
        robust = evaluate_window(
            label=label,
            start=start,
            end=win_end,
            panel=panel,
            kind=kind,
            db_path=db_path,
            initial_value=float(args.initial_value),
            thresholds=ROBUST_THRESHOLDS,
            baseline_add_fraction=float(args.baseline_add_fraction),
            mean_reversion_add_fraction=float(args.mean_reversion_add_fraction),
            trend_persistent_add_fraction=float(args.trend_persistent_add_fraction),
            weak_trend_edge_gate=str(args.weak_trend_edge_gate),
            weak_trend_add_fraction=float(args.weak_trend_add_fraction),
            ce_filter="none",
            transaction_cost_bps=float(args.transaction_cost_bps),
        )
        preferred = evaluate_window(
            label=label,
            start=start,
            end=win_end,
            panel=panel,
            kind=kind,
            db_path=db_path,
            initial_value=float(args.initial_value),
            thresholds=preferred_thresholds,
            baseline_add_fraction=float(args.baseline_add_fraction),
            mean_reversion_add_fraction=float(args.mean_reversion_add_fraction),
            trend_persistent_add_fraction=float(args.trend_persistent_add_fraction),
            weak_trend_edge_gate=str(args.weak_trend_edge_gate),
            weak_trend_add_fraction=float(args.weak_trend_add_fraction),
            ce_filter="none",
            transaction_cost_bps=float(args.transaction_cost_bps),
        )
        robust_final = _delta(robust, "final_value")
        preferred_final = _delta(preferred, "final_value")
        robust_mdd = _delta(robust, "max_drawdown")
        preferred_mdd = _delta(preferred, "max_drawdown")
        row = {
            "label": label,
            "start": start,
            "end": win_end,
            "panel": panel,
            "transaction_cost_bps": float(args.transaction_cost_bps),
            "robust_delta_final_value": robust_final,
            "preferred_delta_final_value": preferred_final,
            "incremental_delta_final_value": preferred_final - robust_final,
            "robust_delta_sharpe": _delta(robust, "sharpe_ratio"),
            "preferred_delta_sharpe": _delta(preferred, "sharpe_ratio"),
            "incremental_delta_sharpe": _delta(preferred, "sharpe_ratio") - _delta(robust, "sharpe_ratio"),
            "robust_delta_max_drawdown": robust_mdd,
            "preferred_delta_max_drawdown": preferred_mdd,
            "incremental_delta_max_drawdown": preferred_mdd - robust_mdd,
            "robust_event_days": int((robust.get("mean_reversion_no_add") or {}).get("event_days", 0) or 0),
            "preferred_event_days": int((preferred.get("mean_reversion_no_add") or {}).get("event_days", 0) or 0),
            "robust_final_value": float(_metrics(robust).get("final_value", 0.0) or 0.0),
            "preferred_final_value": float(_metrics(preferred).get("final_value", 0.0) or 0.0),
        }
        rows.append(row)
        reports.append({"robust": robust, "preferred": preferred})

    preferred_values = [float(row["preferred_delta_final_value"]) for row in rows]
    incremental_values = [float(row["incremental_delta_final_value"]) for row in rows]
    preferred_mdd_values = [float(row["preferred_delta_max_drawdown"]) for row in rows]
    payload = {
        "schema_version": 1,
        "experiment": "00631l_compounding_rolling_windows",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "window_days": int(args.window_days),
        "step_days": int(args.step_days),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "candidate": (
            f"preferred_score{preferred_thresholds.trend_score_min}"
            f"_ar{preferred_thresholds.ar1_trend_min:g}"
            f"_persist{preferred_thresholds.trend_persistence_min:g}"
            f"_rev{preferred_thresholds.reversal_speed_trend_max:g}"
            f"_base{float(args.baseline_add_fraction):g}"
            f"_mr{float(args.mean_reversion_add_fraction):g}"
            f"_trend{float(args.trend_persistent_add_fraction):g}"
            "_vs_robust_score4_ar05_persist60_rev45"
        ),
        "add_speed": {
            "baseline_add_fraction": float(args.baseline_add_fraction),
            "mean_reversion_add_fraction": float(args.mean_reversion_add_fraction),
            "trend_persistent_add_fraction": float(args.trend_persistent_add_fraction),
            "weak_trend_edge_gate": str(args.weak_trend_edge_gate),
            "weak_trend_add_fraction": float(args.weak_trend_add_fraction),
        },
        "preferred_thresholds": {
            "trend_score_min": preferred_thresholds.trend_score_min,
            "ar1_trend_min": preferred_thresholds.ar1_trend_min,
            "trend_persistence_min": preferred_thresholds.trend_persistence_min,
            "reversal_speed_trend_max": preferred_thresholds.reversal_speed_trend_max,
        },
        "summary": {
            "windows": len(rows),
            "preferred_delta_final_value": _summary(preferred_values),
            "incremental_delta_final_value": _summary(incremental_values),
            "preferred_delta_max_drawdown": _summary(preferred_mdd_values),
            "pass": bool(
                rows
                and _summary(preferred_values)["positive_rate"] >= float(args.min_positive_rate)
                and float(_summary(preferred_values)["median"] or 0.0) > 0.0
                and float(_summary(preferred_values)["min"] or 0.0) > float(args.worst_delta_floor)
            ),
            "pass_rule": (
                f"preferred positive_rate >= {float(args.min_positive_rate):.2f}, "
                "preferred median > 0, "
                f"preferred worst delta > {float(args.worst_delta_floor):.2f}"
            ),
        },
        "rows": rows,
        "reports": reports if bool(args.include_reports) else [],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--window-days", type=int, default=252)
    parser.add_argument("--step-days", type=int, default=63)
    parser.add_argument("--max-windows", type=int, default=0, help="0 means no cap; otherwise keep the most recent N windows")
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--baseline-add-fraction", type=float, default=0.40)
    parser.add_argument("--mean-reversion-add-fraction", type=float, default=0.00)
    parser.add_argument("--trend-persistent-add-fraction", type=float, default=1.00)
    parser.add_argument(
        "--weak-trend-edge-gate",
        choices=("none", "trend_score_eq_min", "relative_momentum_nonpositive", "ce20_negative", "any"),
        default="none",
    )
    parser.add_argument("--weak-trend-add-fraction", type=float, default=0.90)
    parser.add_argument("--preferred-trend-score-min", type=int, default=PREFERRED_THRESHOLDS.trend_score_min)
    parser.add_argument("--preferred-ar1-trend-min", type=float, default=PREFERRED_THRESHOLDS.ar1_trend_min)
    parser.add_argument("--preferred-trend-persistence-min", type=float, default=PREFERRED_THRESHOLDS.trend_persistence_min)
    parser.add_argument("--preferred-reversal-speed-trend-max", type=float, default=PREFERRED_THRESHOLDS.reversal_speed_trend_max)
    parser.add_argument("--min-positive-rate", type=float, default=0.65)
    parser.add_argument("--worst-delta-floor", type=float, default=-2500.0)
    parser.add_argument("--include-reports", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    payload = evaluate_rolling_windows(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if payload["rows"]:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(payload["rows"][0].keys()))
            writer.writeheader()
            writer.writerows(payload["rows"])
    print(f"Saved: {output}")
    print(f"CSV: {csv_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
