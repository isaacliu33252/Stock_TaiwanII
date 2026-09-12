#!/usr/bin/env python3
"""Backtest GroupA++ 00713 cash sleeve with a historical NCF panel gate.

Research-only evaluator. It replays the latest a2118 regime frame, then compares
fixed 00713 cash sleeves against a panel-gated 00713 sleeve. The gate only moves
between 00713.TW and cash; it never changes 0050.TW or 00631L.TW exposure.
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
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest  # noqa: E402
from group_a_plus.integrations.ncf import ncf_00713_cash_sleeve_decision  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00713_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/group_a_plusplus_00713_ncf_gate_backtest.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/group_a_plusplus_00713_ncf_gate_backtest.md"
DEFAULT_CSV = PROJECT_ROOT / "results/group_a_plusplus_00713_ncf_gate_backtest_curves.csv"
DEFAULT_WINDOWS = (
    ("ncf_panel_2025_2026", "2025-01-02", "latest"),
    ("trade_record_period_20260501_20260904", "2026-05-01", "2026-09-04"),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


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


def _runner_params(sleeve_weight: float, panel_path: Path | None) -> dict[str, Any]:
    manifest = resolve_latest(DEFAULT_LATEST_STRATEGY)
    params = dict((manifest.get("active_strategy") or {}).get("runner_params") or {})
    params.pop("exclude_zero_volume_rows", None)
    params["group_a_plusplus_00713_cash_sleeve_weight"] = float(sleeve_weight)
    params["group_a_plusplus_00713_ncf_enabled"] = False
    params["ncf_00713_path"] = None
    if panel_path is not None:
        params["ncf_panel_631l_path"] = str(panel_path)
    return params


def _targets_from_report(frame: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for _dt, row in frame.iterrows():
        regime = str(row.get("execution_regime", "golden1"))
        weights = base_weights.get(regime, base_weights.get("group_a_plus_defensive", golden))
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def _resize_00713_cash_sleeve(weights: dict[str, float], target_weight: float) -> dict[str, float]:
    out = dict(weights)
    current = max(float(out.get("00713.TW", 0.0) or 0.0), 0.0)
    target = min(max(float(target_weight), 0.0), 1.0)
    if target < current:
        out["00713.TW"] = target
        out["cash"] = max(float(out.get("cash", 0.0) or 0.0), 0.0) + (current - target)
    elif target > current:
        available_cash = max(float(out.get("cash", 0.0) or 0.0), 0.0)
        shift = min(target - current, available_cash)
        out["00713.TW"] = current + shift
        out["cash"] = available_cash - shift
    return _normalize(out)


def _panel_row_signal(row: pd.Series, signal_date: pd.Timestamp) -> dict[str, Any]:
    return {
        "ticker": "00713.TW",
        "date": str(signal_date.date()),
        "direction": str(row.get("direction", "UP")),
        "calibrated_prob_up": float(row.get("ensemble_prob_up", 0.5)),
        "confidence": float(row.get("confidence", row.get("prob_magnitude", 0.0)) or 0.0),
        "prob_fwd_mdd_gt5_h20": (
            float(row["prob_fwd_mdd_gt5_h20"])
            if pd.notna(row.get("prob_fwd_mdd_gt5_h20"))
            else None
        ),
        "prob_fwd_gain_gt5_h20": (
            float(row["prob_fwd_gain_gt5_h20"])
            if pd.notna(row.get("prob_fwd_gain_gt5_h20"))
            else None
        ),
    }


def _apply_panel_gate(
    weights: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    base_weight: float,
    signal_delay_days: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    shifted = panel.shift(int(signal_delay_days))
    rows: list[dict[str, float]] = []
    decisions: list[dict[str, Any]] = []
    for dt, weight_row in weights.iterrows():
        source = shifted.reindex([dt]).iloc[0] if dt in shifted.index else pd.Series(dtype=object)
        if source.empty or pd.isna(source.get("ensemble_prob_up")):
            decision = ncf_00713_cash_sleeve_decision(
                None,
                actual_date=str(pd.Timestamp(dt).date()),
                base_weight=base_weight,
                enabled=True,
            )
            decision["applied_to_date"] = str(pd.Timestamp(dt).date())
        else:
            source_date = panel.index[panel.index.get_loc(dt) - int(signal_delay_days)]
            signal = _panel_row_signal(source, pd.Timestamp(source_date))
            decision = ncf_00713_cash_sleeve_decision(
                signal,
                actual_date=signal["date"],
                base_weight=base_weight,
                enabled=True,
            )
            decision["applied_to_date"] = str(pd.Timestamp(dt).date())
        decisions.append(decision)
        rows.append(_resize_00713_cash_sleeve(weight_row.to_dict(), float(decision["effective_weight"])))
    gated = pd.DataFrame(rows, index=weights.index)
    scales = pd.Series([float(item["scale"]) for item in decisions], index=weights.index)
    reasons = pd.Series([str(item["reason"]) for item in decisions], index=weights.index)
    stats = {
        "total_days": int(len(weights)),
        "signal_delay_days": int(signal_delay_days),
        "scale_1_days": int((scales == 1.0).sum()),
        "scale_0_5_days": int((scales == 0.5).sum()),
        "scale_0_days": int((scales == 0.0).sum()),
        "mean_effective_00713_weight": float(gated["00713.TW"].mean()),
        "max_effective_00713_weight": float(gated["00713.TW"].max()),
        "changed_days": int((gated["00713.TW"].round(10) != weights["00713.TW"].round(10)).sum()),
        "reason_counts": reasons.value_counts().to_dict(),
    }
    return gated, stats


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


def _simulate(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    prefix: str,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    regimes, mapping = _weight_map_from_daily_weights(weights, prefix)
    curve, execution = _simulate_costed_curve(
        prices,
        regimes,
        mapping,
        initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    metrics = _metrics(curve, initial_value)
    metrics.update(
        {
            "net_profit": float(metrics["final_value"] - initial_value),
            "num_rebalances": int(execution["rebalance_count"]),
            "total_cost": float(execution["transaction_cost"]),
            "turnover_value": float(execution["turnover_value"]),
        }
    )
    return curve, metrics


def _delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = (
        "final_value",
        "net_profit",
        "total_return",
        "annual_return",
        "volatility",
        "sharpe_ratio",
        "max_drawdown",
        "total_cost",
        "num_rebalances",
    )
    return {key: float(candidate.get(key, 0.0) - baseline.get(key, 0.0)) for key in keys}


def run_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    panel_00713_path: Path,
    initial_value: float,
    signal_delay_days: int,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    resolved_end = _resolve_end(db_path, end)
    panel = pd.read_csv(panel_00713_path, index_col="date", parse_dates=True)
    panel.index = pd.to_datetime(panel.index).normalize()
    panel = panel.sort_index()

    variants: dict[str, dict[str, Any]] = {}
    curves: dict[str, pd.Series] = {}
    weights_store: dict[str, pd.DataFrame] = {}
    gate_stats: dict[str, Any] | None = None
    base_frame: pd.DataFrame | None = None

    for sleeve in (0.0, 0.05, 0.10):
        params = _runner_params(sleeve, None)
        report, frame = run_a2118(start, resolved_end, initial_value, db_path, **params)
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index).normalize()
        prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
        weights = _targets_from_report(frame, report)
        name = f"fixed_{int(sleeve * 100):02d}pct"
        curve, metrics = _simulate(
            prices,
            weights,
            prefix=name,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        variants[name] = metrics
        curves[name] = curve
        weights_store[name] = weights
        base_frame = frame

    assert base_frame is not None
    prices, dividend_coverage = _load_total_return_prices(db_path, base_frame.index)
    gated_weights, gate_stats = _apply_panel_gate(
        weights_store["fixed_10pct"],
        panel,
        base_weight=0.10,
        signal_delay_days=signal_delay_days,
    )
    gated_curve, gated_metrics = _simulate(
        prices,
        gated_weights,
        prefix="gated_10pct",
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    variants["gated_10pct_delay1"] = gated_metrics
    curves["gated_10pct_delay1"] = gated_curve
    weights_store["gated_10pct_delay1"] = gated_weights

    curve_frame = pd.DataFrame({"date": base_frame.index, "window": label})
    for name, curve in curves.items():
        curve_frame[name] = curve.to_numpy()
    curve_frame["fixed_10pct_00713_weight"] = weights_store["fixed_10pct"]["00713.TW"].to_numpy()
    curve_frame["gated_10pct_00713_weight"] = gated_weights["00713.TW"].to_numpy()
    curve_frame["gated_10pct_cash_weight"] = gated_weights["cash"].to_numpy()

    baseline = variants["fixed_10pct"]
    return {
        "window": label,
        "start": start,
        "end": resolved_end,
        "panel_00713_path": str(panel_00713_path),
        "panel_00713_first_date": str(panel.index.min().date()),
        "panel_00713_last_date": str(panel.index.max().date()),
        "metrics": variants,
        "delta_vs_fixed_10pct": _delta(variants["gated_10pct_delay1"], baseline),
        "delta_fixed_10pct_vs_fixed_05pct": _delta(variants["fixed_10pct"], variants["fixed_05pct"]),
        "delta_fixed_05pct_vs_fixed_00pct": _delta(variants["fixed_05pct"], variants["fixed_00pct"]),
        "gate_stats": gate_stats,
        "dividend_coverage": dividend_coverage,
    }, curve_frame


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
    reports = []
    curve_frames = []
    for label, start, end in _parse_windows(args.windows):
        report, curves = run_window(
            label=label,
            start=start,
            end=end,
            db_path=_resolve(args.db),
            panel_00713_path=_resolve(args.panel_00713),
            initial_value=float(args.initial_value),
            signal_delay_days=int(args.signal_delay_days),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
        reports.append(report)
        curve_frames.append(curves)
    deltas = [item["delta_vs_fixed_10pct"] for item in reports]
    summary = {
        "window_count": len(reports),
        "gated_beats_fixed_10pct_final_value_windows": int(sum(item["final_value"] > 0 for item in deltas)),
        "gated_beats_fixed_10pct_sharpe_windows": int(sum(item["sharpe_ratio"] > 0 for item in deltas)),
        "gated_non_worse_mdd_windows": int(sum(item["max_drawdown"] >= 0 for item in deltas)),
        "average_delta_final_value_vs_fixed_10pct": float(sum(item["final_value"] for item in deltas) / len(deltas)),
        "average_delta_sharpe_vs_fixed_10pct": float(sum(item["sharpe_ratio"] for item in deltas) / len(deltas)),
        "worst_delta_final_value_vs_fixed_10pct": float(min(item["final_value"] for item in deltas)),
        "worst_delta_max_drawdown_vs_fixed_10pct": float(min(item["max_drawdown"] for item in deltas)),
    }
    report = {
        "schema_version": 1,
        "report_type": "group_a_plusplus_00713_ncf_gate_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_backtest_only_no_live_weight_change",
        "method": "Replay latest a2118 execution regimes; compare fixed sleeves to delayed historical NCF_00713 panel gate.",
        "initial_value": float(args.initial_value),
        "signal_delay_days": int(args.signal_delay_days),
        "cost_assumptions": {
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
        },
        "summary": summary,
        "window_reports": reports,
        "decision": {
            "backtest_complete": True,
            "promote_ncf_00713_historical_gate": False,
            "reason": "Requires review of multi-window deltas; this script is an evaluator only.",
        },
    }
    return report, pd.concat(curve_frames, ignore_index=True)


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# GroupA++ 00713 NCF Gate Backtest",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Signal delay days: `{report['signal_delay_days']}`",
        f"- Windows: `{report['summary']['window_count']}`",
        f"- Gated beats fixed 10% final-value windows: `{report['summary']['gated_beats_fixed_10pct_final_value_windows']}`",
        f"- Gated beats fixed 10% Sharpe windows: `{report['summary']['gated_beats_fixed_10pct_sharpe_windows']}`",
        f"- Gated non-worse MDD windows: `{report['summary']['gated_non_worse_mdd_windows']}`",
        f"- Average delta final value vs fixed 10%: `{report['summary']['average_delta_final_value_vs_fixed_10pct']:.2f}`",
        "",
        "## Windows",
        "",
    ]
    for item in report["window_reports"]:
        metrics = item["metrics"]
        delta = item["delta_vs_fixed_10pct"]
        gate = item["gate_stats"]
        lines.extend(
            [
                f"### {item['window']}",
                "",
                f"- Range: `{item['start']}` to `{item['end']}`",
                f"- Fixed 0% final: `{metrics['fixed_00pct']['final_value']:.2f}`",
                f"- Fixed 5% final: `{metrics['fixed_05pct']['final_value']:.2f}`",
                f"- Fixed 10% final: `{metrics['fixed_10pct']['final_value']:.2f}`",
                f"- Gated 10% final: `{metrics['gated_10pct_delay1']['final_value']:.2f}`",
                f"- Gated delta vs fixed 10% final: `{delta['final_value']:.2f}`",
                f"- Gated delta vs fixed 10% Sharpe: `{delta['sharpe_ratio']:.4f}`",
                f"- Gated delta vs fixed 10% MDD: `{delta['max_drawdown']:.4f}`",
                f"- Gate changed days: `{gate['changed_days']}` / `{gate['total_days']}`",
                f"- Mean effective 00713 weight: `{gate['mean_effective_00713_weight']:.4f}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-00713", default=str(DEFAULT_PANEL))
    parser.add_argument("--windows", default=None, help="Comma-separated label:start:end list")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--signal-delay-days", type=int, default=1)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--curves-output", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report, curves = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown_output)
    curves_output = _resolve(args.curves_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, markdown)
    curves_output.parent.mkdir(parents=True, exist_ok=True)
    curves.to_csv(curves_output, index=False, encoding="utf-8-sig")
    print(f"JSON: {output.resolve()}")
    print(f"Markdown: {markdown.resolve()}")
    print(f"Curves: {curves_output.resolve()}")


if __name__ == "__main__":
    main()
