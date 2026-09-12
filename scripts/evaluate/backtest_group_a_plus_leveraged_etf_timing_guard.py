#!/usr/bin/env python3
"""Backtest the 2604.27287 leveraged ETF timing guard for GroupA+.

Research-only promotion check. It replays the latest strategy and applies
previous-day timing-anomaly warnings to next-day portfolio weights. It never
changes latest strategy, golden1_0531, signals, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.integrations.leveraged_etf_timing_anomaly import (  # noqa: E402
    TimingAnomalyThresholds,
    rolling_timing_anomaly,
)
from group_a_plus.runners.latest import run_latest  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.csv"
DEFAULT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "leveraged_etf_timing_guard_backtest_2604_27287.md"


WINDOWS = (
    ("full_2016_2026", "2016-01-04", "latest"),
    ("rate_hike_2022_2023", "2022-01-03", "2023-12-29"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
)


def _shift_00631l_to_0050(weights: dict[str, float]) -> dict[str, float]:
    out = dict(weights)
    amount = float(out.get("00631L.TW", 0.0) or 0.0)
    out["00631L.TW"] = 0.0
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + amount
    return _normalize(out)


def _shift_00632r_to_cash(weights: dict[str, float]) -> dict[str, float]:
    out = dict(weights)
    amount = float(out.get("00632R.TW", 0.0) or 0.0)
    out["00632R.TW"] = 0.0
    out["cash"] = float(out.get("cash", 0.0) or 0.0) + amount
    return _normalize(out)


def _guarded_weights(base: dict[str, float], *, guard_631l: bool, guard_632r: bool) -> dict[str, float]:
    out = dict(base)
    if guard_631l:
        out = _shift_00631l_to_0050(out)
    if guard_632r:
        out = _shift_00632r_to_cash(out)
    return _normalize(out)


def _weights_by_regime(latest_report: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = latest_report.get("base_weights") or latest_report.get("weights") or {}
    return {str(name): _normalize(dict(weights or {})) for name, weights in raw.items()}


def _build_timing_warnings(
    prices: pd.DataFrame,
    *,
    rolling_window: int,
    thresholds: TimingAnomalyThresholds,
    warning_policy: str = "any_warning",
    persistence_days: int = 1,
) -> pd.DataFrame:
    frames = []
    for asset, leverage in (("00631L.TW", 2.0), ("00632R.TW", -1.0)):
        rolling = rolling_timing_anomaly(
            prices[asset],
            prices["0050.TW"],
            target_leverage=leverage,
            window=rolling_window,
            thresholds=thresholds,
        )
        if rolling.empty:
            continue
        if warning_policy == "any_warning":
            warning = rolling["warnings"].map(bool)
        elif warning_policy == "negative_covariance":
            warning = pd.to_numeric(rolling["covariance_ratio_underlying_return"], errors="coerce") <= float(
                thresholds.negative_covariance_warning
            )
        elif warning_policy == "negative_covariance_and_large_drag":
            warning = (
                pd.to_numeric(rolling["covariance_ratio_underlying_return"], errors="coerce")
                <= float(thresholds.negative_covariance_warning)
            ) & (
                pd.to_numeric(rolling["volatility_drag_estimate"], errors="coerce")
                <= float(thresholds.volatility_drag_warning)
            )
        else:
            raise ValueError(f"unknown warning_policy={warning_policy!r}")
        if int(persistence_days) > 1:
            warning = (
                warning.astype(int)
                .rolling(int(persistence_days), min_periods=int(persistence_days))
                .sum()
                .ge(int(persistence_days))
            )
        warning = warning.fillna(False).astype(bool).rename(asset)
        frames.append(warning)
    if not frames:
        return pd.DataFrame(index=prices.index, columns=["00631L.TW", "00632R.TW"]).fillna(False)
    out = pd.concat(frames, axis=1).reindex(prices.index, fill_value=False)
    for asset in ("00631L.TW", "00632R.TW"):
        if asset not in out:
            out[asset] = False
    return out[["00631L.TW", "00632R.TW"]].astype(bool)


def _variant_regimes(
    base_regimes: pd.Series,
    warnings: pd.DataFrame,
    *,
    mode: str,
) -> pd.Series:
    prev_warning = warnings.shift(1, fill_value=False).reindex(base_regimes.index, fill_value=False).astype(bool)
    out = base_regimes.astype(str).copy()
    for dt, regime in base_regimes.astype(str).items():
        guard_631l = mode in {"00631l_only", "combined"} and bool(prev_warning.loc[dt, "00631L.TW"])
        guard_632r = mode in {"00632r_only", "combined"} and bool(prev_warning.loc[dt, "00632R.TW"])
        if guard_631l or guard_632r:
            out.loc[dt] = f"{regime}__timing_guard_{int(guard_631l)}_{int(guard_632r)}"
    return out


def _extended_weight_map(weights: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out = dict(weights)
    for regime, base in weights.items():
        for guard_631l in (False, True):
            for guard_632r in (False, True):
                if not guard_631l and not guard_632r:
                    continue
                out[f"{regime}__timing_guard_{int(guard_631l)}_{int(guard_632r)}"] = _guarded_weights(
                    base,
                    guard_631l=guard_631l,
                    guard_632r=guard_632r,
                )
    return out


def _delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown", "worst_20d_return")
    return {key: float(candidate[key] - baseline[key]) for key in keys}


def _promoted(delta: dict[str, float]) -> bool:
    return bool(
        delta["final_value"] > 0.0
        and delta["sharpe_ratio"] > 0.0
        and delta["sortino_ratio"] > 0.0
        and delta["max_drawdown"] >= 0.0
    )


def _resolve_end(requested_end: str, latest_frame: pd.DataFrame) -> str:
    if requested_end.lower() != "latest":
        return requested_end
    return pd.Timestamp(latest_frame.index.max()).strftime("%Y-%m-%d")


def _resolve_end_from_db(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if requested_end.lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if value is None:
        raise RuntimeError(f"No OHLCV rows for {ticker}")
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def run_window(
    *,
    db_path: Path,
    label: str,
    start: str,
    end: str,
    initial_value: float,
    thresholds: TimingAnomalyThresholds,
    rolling_window: int,
    warning_policy: str = "any_warning",
    persistence_days: int = 1,
) -> tuple[dict[str, Any], pd.DataFrame]:
    end_for_runner = _resolve_end_from_db(db_path, end)
    latest_report, frame = run_latest(start, end_for_runner, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    resolved_end = _resolve_end(end_for_runner, frame)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    weights = _weights_by_regime(latest_report)
    extended_weights = _extended_weight_map(weights)
    warnings = _build_timing_warnings(
        total_return_prices[["0050.TW", "00631L.TW", "00632R.TW"]],
        rolling_window=rolling_window,
        thresholds=thresholds,
        warning_policy=warning_policy,
        persistence_days=persistence_days,
    )

    baseline_curve, baseline_exec = _simulate_costed_curve(
        total_return_prices,
        frame["execution_regime"].astype(str),
        weights,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)

    curves = pd.DataFrame({"date": frame.index, "window": label, "baseline_latest": baseline_curve.to_numpy()})
    variants: dict[str, Any] = {}
    for mode in ("00631l_only", "00632r_only", "combined"):
        regimes = _variant_regimes(frame["execution_regime"].astype(str), warnings, mode=mode)
        curve, execution = _simulate_costed_curve(
            total_return_prices,
            regimes,
            extended_weights,
            initial_value,
            commission_rate=0.001425,
            slippage_rate=0.0005,
            equity_etf_sell_tax=0.001,
        )
        metrics = _metrics(curve, initial_value)
        delta = _delta(metrics, baseline_metrics)
        curves[f"timing_guard_{mode}"] = curve.to_numpy()
        variants[mode] = {
            "metrics": metrics,
            "delta_vs_baseline": delta,
            "promotion_ready": _promoted(delta),
            "changed_days": int((regimes != frame["execution_regime"].astype(str)).sum()),
            "execution": execution,
        }

    return {
        "window": label,
        "start": start,
        "end": resolved_end,
        "active_strategy_id": latest_report.get("active_strategy_id"),
        "baseline_metrics": baseline_metrics,
        "baseline_execution": baseline_exec,
        "variant_results": variants,
        "warning_counts": {
            "00631l": int(warnings["00631L.TW"].sum()),
            "00632r": int(warnings["00632R.TW"].sum()),
        },
        "warning_policy": warning_policy,
        "persistence_days": int(persistence_days),
        "dividend_coverage": dividend_coverage,
    }, curves


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], pd.DataFrame]:
    thresholds = TimingAnomalyThresholds(
        min_abs_underlying_return=float(args.min_abs_underlying_return),
        ratio_winsor_quantile=float(args.ratio_winsor_quantile),
        negative_covariance_warning=float(args.negative_covariance_warning),
        tracking_error_warning=float(args.tracking_error_warning),
        volatility_drag_warning=float(args.volatility_drag_warning),
    )
    window_reports = []
    curve_frames = []
    for label, start, end in WINDOWS:
        report, curves = run_window(
            db_path=Path(args.db),
            label=label,
            start=start,
            end=end,
            initial_value=float(args.initial_value),
            thresholds=thresholds,
            rolling_window=int(args.rolling_window),
            warning_policy=str(args.warning_policy),
            persistence_days=int(args.persistence_days),
        )
        window_reports.append(report)
        curve_frames.append(curves)

    variant_summary: dict[str, Any] = {}
    for mode in ("00631l_only", "00632r_only", "combined"):
        deltas = [item["variant_results"][mode]["delta_vs_baseline"] for item in window_reports]
        promotion_ready_windows = [item["window"] for item in window_reports if item["variant_results"][mode]["promotion_ready"]]
        variant_summary[mode] = {
            "promotion_ready_window_count": len(promotion_ready_windows),
            "promotion_ready_windows": promotion_ready_windows,
            "average_delta_final_value": float(sum(d["final_value"] for d in deltas) / len(deltas)),
            "average_delta_sharpe": float(sum(d["sharpe_ratio"] for d in deltas) / len(deltas)),
            "worst_delta_max_drawdown": float(min(d["max_drawdown"] for d in deltas)),
        }
    best_mode = max(variant_summary, key=lambda key: variant_summary[key]["average_delta_final_value"])
    decision = "do_not_promote_keep_shadow"
    if variant_summary[best_mode]["promotion_ready_window_count"] == len(window_reports):
        decision = "eligible_for_manual_review_not_auto_promote"

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_leveraged_etf_timing_guard_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2604.27287v1 A Levered ETF Anomaly Explained",
        "policy": "research_only_no_weight_change",
        "decision": decision,
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "inputs": {
            "initial_value": float(args.initial_value),
            "rolling_window": int(args.rolling_window),
            "warning_policy": str(args.warning_policy),
            "persistence_days": int(args.persistence_days),
            "thresholds": thresholds.__dict__,
            "windows": [{"label": label, "start": start, "end": end} for label, start, end in WINDOWS],
        },
        "variant_summary": variant_summary,
        "best_mode_by_average_final_value_delta": best_mode,
        "window_reports": window_reports,
        "promotion_requirements": [
            "candidate must improve final value, Sharpe, Sortino, and not worsen max drawdown in every window",
            "candidate must pass separate signed promotion review before any live wiring",
            "this shadow does not emit live target weights or execution orders",
        ],
    }
    return report, pd.concat(curve_frames, ignore_index=True)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Leveraged ETF Timing Guard Backtest",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source: `{report['research_source']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']}`",
        f"- Latest strategy changed: `{report['changes_latest_strategy']}`",
        "",
        "## Variant Summary",
    ]
    for mode, summary in report["variant_summary"].items():
        lines.extend(
            [
                "",
                f"### {mode}",
                "",
                f"- Promotion-ready windows: `{summary['promotion_ready_window_count']}`",
                f"- Average delta final value: `{summary['average_delta_final_value']:.2f}`",
                f"- Average delta Sharpe: `{summary['average_delta_sharpe']:.4f}`",
                f"- Worst delta max drawdown: `{summary['worst_delta_max_drawdown']:.4f}`",
            ]
        )
    lines.extend(["", "## Window Results"])
    for item in report["window_reports"]:
        lines.extend(["", f"### {item['window']}", ""])
        for mode, detail in item["variant_results"].items():
            delta = detail["delta_vs_baseline"]
            lines.append(
                f"- `{mode}`: final `{delta['final_value']:.2f}`, Sharpe `{delta['sharpe_ratio']:.4f}`, "
                f"Sortino `{delta['sortino_ratio']:.4f}`, MDD `{delta['max_drawdown']:.4f}`, "
                f"changed_days `{detail['changed_days']}`, promotion_ready `{detail['promotion_ready']}`"
            )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "Keep shadow unless every tested window improves final value, Sharpe, Sortino, and does not worsen max drawdown after costs.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--rolling-window", type=int, default=252)
    parser.add_argument(
        "--warning-policy",
        choices=("any_warning", "negative_covariance", "negative_covariance_and_large_drag"),
        default="any_warning",
    )
    parser.add_argument("--persistence-days", type=int, default=1)
    parser.add_argument("--min-abs-underlying-return", type=float, default=0.0005)
    parser.add_argument("--ratio-winsor-quantile", type=float, default=0.95)
    parser.add_argument("--negative-covariance-warning", type=float, default=-0.005)
    parser.add_argument("--tracking-error-warning", type=float, default=0.20)
    parser.add_argument("--volatility-drag-warning", type=float, default=-0.02)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    args = parser.parse_args()

    report, curves = build_report(args)
    output = Path(args.output)
    csv = Path(args.csv)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    curves.to_csv(csv, index=False, encoding="utf-8-sig")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Saved: {output}")
    print(f"CSV: {csv}")
    print(f"Markdown: {markdown}")
    print(f"Decision: {report['decision']}")


if __name__ == "__main__":
    main()
