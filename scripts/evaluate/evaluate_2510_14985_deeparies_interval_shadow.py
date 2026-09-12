#!/usr/bin/env python3
"""DeepAries-lite adaptive interval shadow for GroupA+.

Research-only review for arXiv:2510.14985v1. This script tests the paper's
most importable idea for GroupA+: adaptive rebalancing/review intervals from
the action set {1, 5, 20}. It does not train PPO, does not alter a2118 or
golden1_0531, and does not write live signals, execution plans, or orders.
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_adaptive_review_interval_shadow import (  # noqa: E402
    DD_THRESHOLD,
    ENTRY_MA_GAP,
    EXIT_MA_GAP,
    _count_regime_flips,
    _delayed_and_avoided_transitions,
    _simulate_targets,
    _targets_from_report,
)

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/2510_14985_deeparies_interval_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2510_14985_deeparies_interval_shadow.md"
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "tuning_window", None),
    ("active_2025_2026", "2025-01-02", "latest", "recent_oos", None),
    (
        "backfill_2020_covid",
        "2020-01-02",
        "2020-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2020_20260716.csv",
    ),
    (
        "backfill_2021_may_correction",
        "2021-01-04",
        "2021-12-30",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2021_20260726.csv",
    ),
    (
        "backfill_2022_rate_hike",
        "2022-01-03",
        "2022-10-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    ),
    (
        "backfill_2024_aug_unwind",
        "2024-01-02",
        "2024-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2024_20260726.csv",
    ),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_windows(raw_windows: list[str]) -> list[tuple[str, str, str, str, str | None]]:
    if not raw_windows:
        return DEFAULT_WINDOWS
    parsed: list[tuple[str, str, str, str, str | None]] = []
    for raw in raw_windows:
        parts = [part.strip() for part in raw.split(":")]
        if len(parts) not in {3, 4, 5}:
            raise ValueError("--window must be label:start:end[:bucket[:ncf_panel_631l_path]]")
        label, start, end = parts[:3]
        bucket = parts[3] if len(parts) >= 4 else "custom"
        panel_path = parts[4] if len(parts) == 5 and parts[4] else None
        parsed.append((label, start, end, bucket, panel_path))
    return parsed


def _fixed_interval_targets(
    baseline_targets: pd.DataFrame,
    *,
    interval_days: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, float]] = []
    log: list[dict[str, Any]] = []
    last_weights: dict[str, float] | None = None
    next_review_i = 0
    for i, dt in enumerate(baseline_targets.index):
        if i >= next_review_i:
            last_weights = baseline_targets.loc[dt].to_dict()
            next_review_i = i + interval_days
            log.append({"date": str(dt.date()), "interval_days": int(interval_days), "reason": f"fixed_{interval_days}d"})
        rows.append(dict(last_weights or baseline_targets.loc[dt].to_dict()))
    return pd.DataFrame(rows, index=baseline_targets.index), log


def _deeparies_lite_interval(
    row: pd.Series,
    *,
    crash_dd_buffer: float,
    tail_risk_score_min: float,
    total_risk_score_min: float,
    near_ma_gap_buffer: float,
    near_dd_buffer: float,
    defensive_interval: int,
    stable_golden_interval: int,
) -> tuple[int, str]:
    """Causal heuristic mapping a2118 state to DeepAries-like {1, 5, 20}.

    The paper learns this mapping with PPO+iTransformer. Here we only test
    whether the action-space concept is useful for GroupA+ without adding a new
    live model.
    """

    regime = str(row.get("execution_regime", "golden1"))
    ma_gap = float(row.get("ma_gap", 0.0) or 0.0)
    drawdown = float(row.get("drawdown", 0.0) or 0.0)
    tail_risk_score = float(row.get("tail_risk_score", 0.0) or 0.0)
    total_risk_score = float(row.get("total_risk_score", 0.0) or 0.0)

    crash_like = (
        drawdown <= DD_THRESHOLD + crash_dd_buffer
        or tail_risk_score >= tail_risk_score_min
        or total_risk_score >= total_risk_score_min
    )
    near_switch = (
        abs(ma_gap - ENTRY_MA_GAP) <= near_ma_gap_buffer
        or abs(ma_gap - EXIT_MA_GAP) <= near_ma_gap_buffer
        or drawdown <= DD_THRESHOLD + near_dd_buffer
    )
    if regime == "group_a_plus_recovery" or crash_like or near_switch:
        return 1, "risk_or_threshold_daily"
    if regime == "group_a_plus_defensive":
        return defensive_interval, f"defensive_{defensive_interval}d"
    return stable_golden_interval, f"stable_golden1_{stable_golden_interval}d"


def _adaptive_interval_targets(
    frame: pd.DataFrame,
    baseline_targets: pd.DataFrame,
    *,
    interval_params: dict[str, Any],
    choppy_fail_safe: bool = False,
    choppy_lookback: int = 20,
    choppy_flip_min: int = 2,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, float]] = []
    log: list[dict[str, Any]] = []
    last_weights: dict[str, float] | None = None
    next_review_i = 0
    for i, dt in enumerate(frame.index):
        if i >= next_review_i:
            last_weights = baseline_targets.loc[dt].to_dict()
            interval, reason = _deeparies_lite_interval(frame.loc[dt], **interval_params)
            if choppy_fail_safe and i > 0:
                start = max(0, i - choppy_lookback)
                recent_regime = frame.iloc[start : i + 1]["execution_regime"].astype(str)
                flip_count = int((recent_regime != recent_regime.shift(1)).sum() - 1)
                if flip_count >= choppy_flip_min:
                    interval, reason = 1, f"choppy_regime_flip_daily_{flip_count}"
            next_review_i = i + interval
            log.append({"date": str(dt.date()), "interval_days": int(interval), "reason": reason})
        rows.append(dict(last_weights or baseline_targets.loc[dt].to_dict()))
    return pd.DataFrame(rows, index=frame.index), log


def _interval_counts(log: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in log:
        key = str(item["interval_days"])
        out[key] = out.get(key, 0) + 1
    return out


def _evaluate_targets(
    *,
    name: str,
    prices: pd.DataFrame,
    frame: pd.DataFrame,
    baseline_targets: pd.DataFrame,
    candidate_targets: pd.DataFrame,
    review_log: list[dict[str, Any]],
    baseline_metrics: dict[str, Any],
    baseline_execution: dict[str, Any],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    curve, execution = _simulate_targets(
        prices,
        candidate_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    metrics = _metrics(curve, initial_value)
    transitions = _delayed_and_avoided_transitions(frame, baseline_targets, candidate_targets)
    return {
        "name": name,
        "review_count": int(len(review_log)),
        "review_interval_usage": _interval_counts(review_log),
        "metrics": metrics,
        "execution": execution,
        "delta_vs_daily": {
            "final_value": float(metrics["final_value"] - baseline_metrics["final_value"]),
            "sharpe_ratio": float(metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "transaction_cost": float(execution["transaction_cost"] - baseline_execution["transaction_cost"]),
            "turnover_value": float(execution["turnover_value"] - baseline_execution["turnover_value"]),
            "rebalance_count": int(execution["rebalance_count"] - baseline_execution["rebalance_count"]),
        },
        "transitions": transitions,
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    ncf_panel_631l_path: str | None,
    interval_params: dict[str, Any],
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
        ncf_panel_631l_path=ncf_panel_631l_path,
    )
    prices, coverage = _load_total_return_prices(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report).reindex(prices.index).ffill()
    frame_aligned = frame.reindex(prices.index).ffill()

    daily_curve, daily_execution = _simulate_targets(
        prices,
        baseline_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    daily_metrics = _metrics(daily_curve, initial_value)

    candidates: list[dict[str, Any]] = []
    for interval in (5, 20):
        targets, log = _fixed_interval_targets(baseline_targets, interval_days=interval)
        candidates.append(
            _evaluate_targets(
                name=f"fixed_{interval}d",
                prices=prices,
                frame=frame_aligned,
                baseline_targets=baseline_targets,
                candidate_targets=targets,
                review_log=log,
                baseline_metrics=daily_metrics,
                baseline_execution=daily_execution,
                initial_value=initial_value,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
            )
        )
    adaptive_targets, adaptive_log = _adaptive_interval_targets(
        frame_aligned,
        baseline_targets,
        interval_params=interval_params,
    )
    candidates.append(
        _evaluate_targets(
            name="deeparies_lite_adaptive_1_5_20",
            prices=prices,
            frame=frame_aligned,
            baseline_targets=baseline_targets,
            candidate_targets=adaptive_targets,
            review_log=adaptive_log,
            baseline_metrics=daily_metrics,
            baseline_execution=daily_execution,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    )
    choppy_targets, choppy_log = _adaptive_interval_targets(
        frame_aligned,
        baseline_targets,
        interval_params=interval_params,
        choppy_fail_safe=True,
    )
    candidates.append(
        _evaluate_targets(
            name="deeparies_lite_adaptive_choppy_1_5_20",
            prices=prices,
            frame=frame_aligned,
            baseline_targets=baseline_targets,
            candidate_targets=choppy_targets,
            review_log=choppy_log,
            baseline_metrics=daily_metrics,
            baseline_execution=daily_execution,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    )
    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "daily_baseline": {"metrics": daily_metrics, "execution": daily_execution},
        "candidates": candidates,
        "regime_flip_count": _count_regime_flips(frame_aligned["execution_regime"]),
        "dividend_coverage": coverage,
    }


def _candidate_pass(item: dict[str, Any]) -> bool:
    delta = item["delta_vs_daily"]
    return bool(
        delta["final_value"] >= 0.0
        and delta["sharpe_ratio"] >= 0.0
        and delta["max_drawdown"] >= 0.0
        and delta["transaction_cost"] <= 0.0
        and delta["turnover_value"] <= 0.0
    )


def _has_nonzero_delta(row: dict[str, Any], *, eps: float = 1e-9) -> bool:
    delta = row["delta_vs_daily"]
    return any(abs(float(delta[key])) > eps for key in ("final_value", "sharpe_ratio", "max_drawdown", "transaction_cost", "turnover_value"))


def _summarize(
    windows: list[dict[str, Any]],
    *,
    min_total_cost_saving: float,
    min_total_turnover_reduction: float,
    min_nonzero_delta_windows: int,
) -> dict[str, Any]:
    method_names = sorted({candidate["name"] for window in windows for candidate in window["candidates"]})
    by_method: dict[str, Any] = {}
    for name in method_names:
        rows = [candidate for window in windows for candidate in window["candidates"] if candidate["name"] == name]
        total_cost_delta = float(sum(row["delta_vs_daily"]["transaction_cost"] for row in rows))
        total_turnover_delta = float(sum(row["delta_vs_daily"]["turnover_value"] for row in rows))
        nonzero_delta_windows = int(sum(_has_nonzero_delta(row) for row in rows))
        legacy_pass_windows = int(sum(_candidate_pass(row) for row in rows))
        by_method[name] = {
            "pass_windows": legacy_pass_windows,
            "window_count": int(len(rows)),
            "total_final_value_delta": float(sum(row["delta_vs_daily"]["final_value"] for row in rows)),
            "total_transaction_cost_delta": total_cost_delta,
            "total_turnover_delta": total_turnover_delta,
            "nonzero_delta_windows": nonzero_delta_windows,
            "strict_nontrivial_ready": bool(
                legacy_pass_windows == len(rows)
                and -total_cost_delta >= min_total_cost_saving
                and -total_turnover_delta >= min_total_turnover_reduction
                and nonzero_delta_windows >= min_nonzero_delta_windows
            ),
        }
    best_name = max(method_names, key=lambda name: (by_method[name]["pass_windows"], by_method[name]["total_final_value_delta"])) if method_names else None
    best = by_method.get(best_name, {})
    legacy_gate_ready = bool(best and best["pass_windows"] == len(windows) and best["total_final_value_delta"] >= 0.0)
    strict_ready = bool(best and best.get("strict_nontrivial_ready", False))
    return {
        "window_count": int(len(windows)),
        "by_method": by_method,
        "best_method_by_pass_then_final_delta": best_name,
        "legacy_gate_promotion_ready": legacy_gate_ready,
        "promotion_ready": strict_ready,
        "strict_nontrivial_gate": {
            "min_total_cost_saving": float(min_total_cost_saving),
            "min_total_turnover_reduction": float(min_total_turnover_reduction),
            "min_nonzero_delta_windows": int(min_nonzero_delta_windows),
        },
        "decision": "research_only_not_promoted",
        "reason": "DeepAries full PPO+iTransformer is not imported; interval-only shadow must pass all windows and show nontrivial cost/turnover benefit before any live integration.",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    interval_params = {
        "crash_dd_buffer": float(args.crash_dd_buffer),
        "tail_risk_score_min": float(args.tail_risk_score_min),
        "total_risk_score_min": float(args.total_risk_score_min),
        "near_ma_gap_buffer": float(args.near_ma_gap_buffer),
        "near_dd_buffer": float(args.near_dd_buffer),
        "defensive_interval": int(args.defensive_interval),
        "stable_golden_interval": int(args.stable_golden_interval),
    }
    windows = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            initial_value=float(args.initial_value),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            ncf_panel_631l_path=panel_path,
            interval_params=interval_params,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "schema_version": 1,
        "report_type": "2510_14985_deeparies_interval_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2510.14985v1 DeepAries: Adaptive Rebalancing Interval Selection for Enhanced Portfolio Selection",
        "policy": "research_only_no_groupa_plus_live_change",
        "action_space_tested": sorted({1, int(args.defensive_interval), int(args.stable_golden_interval)}),
        "interval_params": interval_params,
        "scope": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_a2118_decision_rule": False,
            "creates_orders": False,
        },
        "summary": _summarize(
            windows,
            min_total_cost_saving=float(args.min_total_cost_saving),
            min_total_turnover_reduction=float(args.min_total_turnover_reduction),
            min_nonzero_delta_windows=int(args.min_nonzero_delta_windows),
        ),
        "windows": windows,
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2510.14985v1 DeepAries-Lite Interval Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Action space tested: `{report['action_space_tested']}`",
        f"- Interval params: `{report['interval_params']}`",
        f"- Strict nontrivial gate: `{report['summary']['strict_nontrivial_gate']}`",
        "",
        "## Summary By Method",
        "",
        "| Method | Pass Windows | Nonzero Windows | Strict Ready | Total Final Delta | Total Cost Delta | Total Turnover Delta |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in report["summary"]["by_method"].items():
        lines.append(
            f"| {name} | {item['pass_windows']}/{item['window_count']} | "
            f"{item['nonzero_delta_windows']}/{item['window_count']} | `{item['strict_nontrivial_ready']}` | "
            f"{item['total_final_value_delta']:.2f} | {item['total_transaction_cost_delta']:.2f} | "
            f"{item['total_turnover_delta']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Window Details",
            "",
            "| Window | Method | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Reviews | Usage | Pass |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for window in report["windows"]:
        for candidate in window["candidates"]:
            delta = candidate["delta_vs_daily"]
            lines.append(
                f"| {window['label']} | {candidate['name']} | {delta['final_value']:.2f} | "
                f"{delta['sharpe_ratio']:.4f} | {delta['max_drawdown']:.4f} | "
                f"{delta['transaction_cost']:.2f} | {delta['turnover_value']:.2f} | "
                f"{candidate['review_count']} | `{candidate['review_interval_usage']}` | {_candidate_pass(candidate)} |"
            )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Legacy all-window no-worse gate: `{report['summary']['legacy_gate_promotion_ready']}`",
            f"- Promotion ready: `{report['summary']['promotion_ready']}`",
            "- Recommended use: `research_only`",
            "- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--window", action="append", default=[])
    parser.add_argument("--crash-dd-buffer", type=float, default=0.03)
    parser.add_argument("--tail-risk-score-min", type=float, default=5.0)
    parser.add_argument("--total-risk-score-min", type=float, default=8.0)
    parser.add_argument("--near-ma-gap-buffer", type=float, default=0.015)
    parser.add_argument("--near-dd-buffer", type=float, default=0.05)
    parser.add_argument("--defensive-interval", type=int, default=5)
    parser.add_argument("--stable-golden-interval", type=int, default=20)
    parser.add_argument("--min-total-cost-saving", type=float, default=1000.0)
    parser.add_argument("--min-total-turnover-reduction", type=float, default=100000.0)
    parser.add_argument("--min-nonzero-delta-windows", type=int, default=2)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(
        json.dumps(
            {
                "promotion_ready": report["summary"]["promotion_ready"],
                "best_method": report["summary"]["best_method_by_pass_then_final_delta"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
