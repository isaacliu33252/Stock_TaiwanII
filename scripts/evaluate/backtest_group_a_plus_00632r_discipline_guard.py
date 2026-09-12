#!/usr/bin/env python3
"""Backtest the GroupA+ 00632R discipline guard.

Compares the latest GroupA+ strategy against a guarded variant that maps every
00632R target weight to cash. This is a full daily strategy replay using the
existing latest runner and costed curve simulator; it does not change live
signals, target weights, execution plans, or golden baselines.
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00632r_discipline_guard_backtest.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/00632r_discipline_guard_backtest.md"
DEFAULT_CSV = PROJECT_ROOT / "results/00632r_discipline_guard_backtest_curves.csv"
DEFAULT_WINDOWS = (
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
    ("trade_record_period_20260501_20260904", "2026-05-01", "2026-09-04"),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _targets_from_report(frame: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for _dt, row in frame.iterrows():
        regime = str(row.get("execution_regime", "golden1"))
        weights = base_weights.get(regime, base_weights.get("group_a_plus_defensive", golden))
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def _weight_map_from_daily_weights(weights: pd.DataFrame, prefix: str) -> tuple[pd.Series, dict[str, dict[str, float]]]:
    regimes: list[str] = []
    mapping: dict[tuple[float, ...], str] = {}
    weights_by_regime: dict[str, dict[str, float]] = {}
    for _dt, row in weights.iterrows():
        normalized = _normalize({key: float(row.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
        key = tuple(round(normalized.get(ticker, 0.0), 10) for ticker in (*TICKERS, "cash"))
        regime = mapping.get(key)
        if regime is None:
            regime = f"{prefix}_{len(mapping)}"
            mapping[key] = regime
            weights_by_regime[regime] = normalized
        regimes.append(regime)
    return pd.Series(regimes, index=weights.index, dtype=str), weights_by_regime


def _guard_weights(weights: pd.DataFrame) -> pd.DataFrame:
    guarded = weights.copy()
    shifted = guarded["00632R.TW"].astype(float)
    guarded["00632R.TW"] = 0.0
    guarded["cash"] = guarded["cash"].astype(float) + shifted
    return guarded.apply(lambda row: pd.Series(_normalize(row.to_dict())), axis=1)


def _delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = (
        "final_value",
        "net_profit",
        "total_return",
        "annual_return",
        "volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "worst_20d_return",
        "total_cost",
        "num_rebalances",
    )
    return {key: float(candidate.get(key, 0.0) - baseline.get(key, 0.0)) for key in keys}


def _resolve_end(db_path: Path, requested_end: str) -> str:
    if requested_end.lower() != "latest":
        return requested_end
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = '0050.TW'").fetchone()[0]
    finally:
        con.close()
    if value is None:
        raise RuntimeError("No 0050.TW OHLCV data")
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def run_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    resolved_end = _resolve_end(db_path, end)
    latest_report, frame = run_latest(start, resolved_end, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    baseline_weights = _targets_from_report(frame, latest_report)
    guarded_weights = _guard_weights(baseline_weights)

    baseline_regimes, baseline_map = _weight_map_from_daily_weights(baseline_weights, "baseline")
    guarded_regimes, guarded_map = _weight_map_from_daily_weights(guarded_weights, "guarded")
    baseline_curve, baseline_execution = _simulate_costed_curve(
        prices,
        baseline_regimes,
        baseline_map,
        initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    guarded_curve, guarded_execution = _simulate_costed_curve(
        prices,
        guarded_regimes,
        guarded_map,
        initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    guarded_metrics = _metrics(guarded_curve, initial_value)
    baseline_metrics.update(
        {
            "num_rebalances": baseline_execution["rebalance_count"],
            "total_cost": baseline_execution["transaction_cost"],
            "turnover_value": baseline_execution["turnover_value"],
            "net_profit": baseline_metrics["final_value"] - initial_value,
        }
    )
    guarded_metrics.update(
        {
            "num_rebalances": guarded_execution["rebalance_count"],
            "total_cost": guarded_execution["transaction_cost"],
            "turnover_value": guarded_execution["turnover_value"],
            "net_profit": guarded_metrics["final_value"] - initial_value,
        }
    )
    positive_00632r = baseline_weights["00632R.TW"].astype(float) > 1e-12
    weight_stats = {
        "positive_00632r_days": int(positive_00632r.sum()),
        "total_days": int(len(baseline_weights)),
        "max_00632r_weight": float(baseline_weights["00632R.TW"].max()),
        "mean_00632r_weight": float(baseline_weights["00632R.TW"].mean()),
        "guard_changed_days": int((baseline_weights["00632R.TW"].astype(float) > 1e-12).sum()),
    }
    curves = pd.DataFrame(
        {
            "date": frame.index,
            "window": label,
            "baseline_latest": baseline_curve.to_numpy(),
            "00632r_zero_to_cash": guarded_curve.to_numpy(),
            "baseline_00632r_weight": baseline_weights["00632R.TW"].to_numpy(),
            "guarded_cash_weight": guarded_weights["cash"].to_numpy(),
        }
    )
    return {
        "window": label,
        "start": start,
        "end": resolved_end,
        "active_strategy_id": latest_report.get("active_strategy_id"),
        "baseline_metrics": baseline_metrics,
        "guarded_metrics": guarded_metrics,
        "delta_vs_baseline": _delta(guarded_metrics, baseline_metrics),
        "baseline_execution": baseline_execution,
        "guarded_execution": guarded_execution,
        "weight_stats": weight_stats,
        "dividend_coverage": dividend_coverage,
    }, curves


def _parse_windows(raw: str | None) -> tuple[tuple[str, str, str], ...]:
    if not raw:
        return DEFAULT_WINDOWS
    windows = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            raise ValueError("--windows items must be label:start:end")
        windows.append((parts[0], parts[1], parts[2]))
    return tuple(windows)


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], pd.DataFrame]:
    window_reports = []
    curve_frames = []
    for label, start, end in _parse_windows(args.windows):
        report, curves = run_window(
            label=label,
            start=start,
            end=end,
            db_path=_resolve(args.db),
            initial_value=float(args.initial_value),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
        window_reports.append(report)
        curve_frames.append(curves)
    deltas = [item["delta_vs_baseline"] for item in window_reports]
    summary = {
        "window_count": len(window_reports),
        "positive_delta_final_value_windows": int(sum(item["final_value"] > 0 for item in deltas)),
        "positive_delta_sharpe_windows": int(sum(item["sharpe_ratio"] > 0 for item in deltas)),
        "non_worse_max_drawdown_windows": int(sum(item["max_drawdown"] >= 0 for item in deltas)),
        "average_delta_final_value": float(sum(item["final_value"] for item in deltas) / len(deltas)),
        "average_delta_sharpe": float(sum(item["sharpe_ratio"] for item in deltas) / len(deltas)),
        "worst_delta_final_value": float(min(item["final_value"] for item in deltas)),
        "worst_delta_max_drawdown": float(min(item["max_drawdown"] for item in deltas)),
    }
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_00632r_discipline_guard_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_backtest_only_no_live_weight_change",
        "variant": "00632r_zero_to_cash",
        "cost_assumptions": {
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
        },
        "initial_value": float(args.initial_value),
        "summary": summary,
        "window_reports": window_reports,
        "decision": {
            "backtest_complete": True,
            "latest_strategy_change_allowed": False,
            "golden1_0531_change_allowed": False,
            "golden2_0830_change_allowed": False,
            "allow_00632r_dca": False,
            "allow_00632r_averaging_down": False,
            "allow_00632r_open": False,
            "summary": (
                "The guarded variant maps 00632R to cash for measurement. "
                "Promotion still requires governance review; this report only quantifies impact."
            ),
        },
    }
    return report, pd.concat(curve_frames, ignore_index=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 00632R Discipline Guard Backtest",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- policy: {report['policy']}",
        f"- variant: {report['variant']}",
        f"- initial_value: {report['initial_value']:.2f}",
        f"- windows: {summary['window_count']}",
        f"- positive_delta_final_value_windows: {summary['positive_delta_final_value_windows']}",
        f"- average_delta_final_value: {summary['average_delta_final_value']:.2f}",
        f"- average_delta_sharpe: {summary['average_delta_sharpe']:.4f}",
        "",
        "## Window Results",
    ]
    for item in report["window_reports"]:
        base = item["baseline_metrics"]
        guarded = item["guarded_metrics"]
        delta = item["delta_vs_baseline"]
        stats = item["weight_stats"]
        lines.extend(
            [
                "",
                f"### {item['window']}",
                "",
                f"- period: {item['start']} to {item['end']}",
                f"- 00632R positive days: {stats['positive_00632r_days']} / {stats['total_days']}",
                f"- max 00632R weight: {stats['max_00632r_weight']:.4f}",
                f"- baseline final: {base['final_value']:.2f}, return: {base['total_return']:.4%}, sharpe: {base['sharpe_ratio']:.4f}, mdd: {base['max_drawdown']:.4%}",
                f"- guarded final: {guarded['final_value']:.2f}, return: {guarded['total_return']:.4%}, sharpe: {guarded['sharpe_ratio']:.4f}, mdd: {guarded['max_drawdown']:.4%}",
                f"- delta final: {delta['final_value']:.2f}, delta return: {delta['total_return']:.4%}, delta sharpe: {delta['sharpe_ratio']:.4f}, delta mdd: {delta['max_drawdown']:.4%}",
            ]
        )
    lines.extend(["", "## Decision", report["decision"]["summary"], ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--windows", default=None)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report, curves = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    csv = _resolve(args.csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    csv.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    curves.to_csv(csv, index=False, encoding="utf-8-sig")
    print(f"00632R discipline guard backtest: {output}")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
