#!/usr/bin/env python3
"""Evaluate CTBC-style debounce for the GroupA++ 00713 NCF sleeve gate.

Research-only. It compares the existing delayed 00713 NCF gate against 2-of-3
and 3-of-3 confirmation variants. It never changes live target weights,
strategy manifests, golden artifacts, NCF gates, or orders.
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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402
from scripts.evaluate import backtest_group_a_plusplus_00713_ncf_gate as base_00713  # noqa: E402


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00713_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_debounce_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_debounce_shadow.md"
DEFAULT_CSV = PROJECT_ROOT / "results/2509_02986_ctbc_00713_debounce_shadow_curves.csv"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _confirm(mask: pd.Series, mode: str) -> pd.Series:
    raw = mask.fillna(False).astype(bool)
    if mode == "raw":
        return raw
    if mode == "2of3":
        return raw.rolling(3, min_periods=3).sum().fillna(0).astype(int) >= 2
    if mode == "3of3":
        return raw.rolling(3, min_periods=3).sum().fillna(0).astype(int) >= 3
    raise ValueError(f"unknown mode: {mode}")


def _apply_debounce(
    fixed_weights: pd.DataFrame,
    raw_gated_weights: pd.DataFrame,
    *,
    mode: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    event = raw_gated_weights["00713.TW"].astype(float) < fixed_weights["00713.TW"].astype(float) - 1e-10
    confirmed = _confirm(event, mode)
    rows = []
    for dt in fixed_weights.index:
        rows.append((raw_gated_weights if bool(confirmed.loc[dt]) else fixed_weights).loc[dt].to_dict())
    out = pd.DataFrame(rows, index=fixed_weights.index)
    return out, {
        "mode": mode,
        "raw_event_days": int(event.sum()),
        "confirmed_event_days": int(confirmed.sum()),
        "changed_days": int((out["00713.TW"].round(10) != fixed_weights["00713.TW"].round(10)).sum()),
        "mean_effective_00713_weight": float(out["00713.TW"].mean()),
        "min_effective_00713_weight": float(out["00713.TW"].min()),
        "max_effective_00713_weight": float(out["00713.TW"].max()),
    }


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
    resolved_end = base_00713._resolve_end(db_path, end)
    panel = pd.read_csv(panel_00713_path, index_col="date", parse_dates=True)
    panel.index = pd.to_datetime(panel.index).normalize()
    panel = panel.sort_index()

    params = base_00713._runner_params(0.10, None)
    report, frame = run_a2118(start, resolved_end, initial_value, db_path, **params)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    prices, dividend_coverage = base_00713._load_total_return_prices(db_path, frame.index)
    fixed_weights = base_00713._targets_from_report(frame, report)
    raw_weights, raw_stats = base_00713._apply_panel_gate(
        fixed_weights,
        panel,
        base_weight=0.10,
        signal_delay_days=signal_delay_days,
    )

    curves: dict[str, pd.Series] = {}
    metrics: dict[str, dict[str, Any]] = {}
    gate_stats: dict[str, dict[str, Any]] = {"raw": raw_stats}

    for name, weights in {"fixed_10pct": fixed_weights, "raw_gate": raw_weights}.items():
        curve, item_metrics = base_00713._simulate(
            prices,
            weights,
            prefix=f"{label}_{name}",
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        curves[name] = curve
        metrics[name] = item_metrics

    for mode in ("2of3", "3of3"):
        debounced, stats = _apply_debounce(fixed_weights, raw_weights, mode=mode)
        curve, item_metrics = base_00713._simulate(
            prices,
            debounced,
            prefix=f"{label}_{mode}",
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        curves[f"debounce_{mode}"] = curve
        metrics[f"debounce_{mode}"] = item_metrics
        gate_stats[mode] = stats

    curve_frame = pd.DataFrame({"date": frame.index, "window": label})
    for name, curve in curves.items():
        curve_frame[name] = curve.to_numpy()
    curve_frame["fixed_10pct_00713_weight"] = fixed_weights["00713.TW"].to_numpy()
    curve_frame["raw_gate_00713_weight"] = raw_weights["00713.TW"].to_numpy()

    deltas = {
        name: base_00713._delta(item, metrics["fixed_10pct"])
        for name, item in metrics.items()
        if name != "fixed_10pct"
    }
    return {
        "window": label,
        "start": start,
        "end": resolved_end,
        "panel_00713_path": str(panel_00713_path),
        "metrics": metrics,
        "delta_vs_fixed_10pct": deltas,
        "gate_stats": gate_stats,
        "dividend_coverage": dividend_coverage,
    }, curve_frame


def _parse_windows(raw: str | None) -> tuple[tuple[str, str, str], ...]:
    return base_00713._parse_windows(raw)


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], pd.DataFrame]:
    reports = []
    curves = []
    for label, start, end in _parse_windows(args.windows):
        report, curve = run_window(
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
        curves.append(curve)

    variants = ("raw_gate", "debounce_2of3", "debounce_3of3")
    summary = {}
    for variant in variants:
        deltas = [item["delta_vs_fixed_10pct"][variant] for item in reports]
        summary[variant] = {
            "beats_fixed_final_value_windows": int(sum(delta["final_value"] > 0 for delta in deltas)),
            "beats_fixed_sharpe_windows": int(sum(delta["sharpe_ratio"] > 0 for delta in deltas)),
            "non_worse_mdd_windows": int(sum(delta["max_drawdown"] >= 0 for delta in deltas)),
            "average_delta_final_value": float(sum(delta["final_value"] for delta in deltas) / len(deltas)),
            "average_delta_sharpe": float(sum(delta["sharpe_ratio"] for delta in deltas) / len(deltas)),
            "worst_delta_final_value": float(min(delta["final_value"] for delta in deltas)),
        }

    best = max(summary, key=lambda name: (summary[name]["beats_fixed_final_value_windows"], summary[name]["average_delta_final_value"]))
    strict_pass = bool(
        summary[best]["beats_fixed_final_value_windows"] == len(reports)
        and summary[best]["beats_fixed_sharpe_windows"] == len(reports)
        and summary[best]["non_worse_mdd_windows"] == len(reports)
    )
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_2509_02986_ctbc_00713_debounce_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2509.02986",
            "transferred_idea": "sliding_window_trigger_debounce_for_00713_sleeve",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "changes_ncf_live_gate": False,
        "initial_value": float(args.initial_value),
        "signal_delay_days": int(args.signal_delay_days),
        "summary": summary,
        "window_reports": reports,
        "decision": {
            "promotion_allowed": False,
            "decision": "do_not_promote_keep_shadow",
            "best_variant": best,
            "strict_debounce_gate_passed": strict_pass,
            "reason": "00713 debounce must beat fixed 10% on final value and Sharpe with non-worse MDD across all windows before promotion.",
        },
    }
    return report, pd.concat(curves, ignore_index=True)


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2509.02986 CTBC 00713 Debounce Shadow",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Best variant: `{report['decision']['best_variant']}`",
        f"- Strict debounce gate passed: `{report['decision']['strict_debounce_gate_passed']}`",
        "",
        "## Summary",
        "",
        "| variant | FV wins | Sharpe wins | non-worse MDD | avg dFV | avg dSharpe | worst dFV |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in report["summary"].items():
        lines.append(
            f"| `{name}` | {item['beats_fixed_final_value_windows']} | {item['beats_fixed_sharpe_windows']} | "
            f"{item['non_worse_mdd_windows']} | {item['average_delta_final_value']:.2f} | "
            f"{item['average_delta_sharpe']:.4f} | {item['worst_delta_final_value']:.2f} |"
        )
    lines.extend(["", "## Windows", ""])
    for item in report["window_reports"]:
        lines.extend([f"### {item['window']}", ""])
        for variant, delta in item["delta_vs_fixed_10pct"].items():
            lines.append(
                f"- `{variant}` dFV=`{delta['final_value']:.2f}` "
                f"dSharpe=`{delta['sharpe_ratio']:.4f}` dMDD=`{delta['max_drawdown']:.4f}`"
            )
        lines.append("")
    lines.extend(
        [
            "## Conclusion",
            "",
            "CTBC 00713 debounce remains shadow-only and does not change the current fixed 10% sleeve policy.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-00713", default=str(DEFAULT_PANEL))
    parser.add_argument("--windows", default=None)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--signal-delay-days", type=int, default=1)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--curves-output", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report, curves = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    curves_output = _resolve(args.curves_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    curves_output.parent.mkdir(parents=True, exist_ok=True)
    curves.to_csv(curves_output, index=False, encoding="utf-8-sig")
    print(f"best_variant={report['decision']['best_variant']}")
    print(f"strict_debounce_gate_passed={report['decision']['strict_debounce_gate_passed']}")
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")
    print(f"Curves: {curves_output}")


if __name__ == "__main__":
    main()
