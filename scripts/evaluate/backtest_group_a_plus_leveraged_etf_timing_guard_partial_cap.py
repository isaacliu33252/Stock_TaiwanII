#!/usr/bin/env python3
"""Fable 00631L direction #9 (2026-08-22): partial-cap variant of the 2604.27287
leveraged ETF timing guard.

GROUP_A_PLUS_20260821_LEVERAGED_ETF_ANOMALY_2604_27287_FINAL_HANDOFF.md tested
only a full 00631L-to-0050 shift (100% of guarded-day 00631L weight moved to
0050) under three warning policies; every variant was `do_not_promote_keep_shadow`
in every window except a single-window pass for `00631l_only`. That handoff's
own "Final Recommendation" section explicitly names "partial cap instead of
full 00631L-to-0050 shift" as one of the few conditions under which reopening
promotion work would be justified -- the hypothesis being that the full shift's
biggest failure mode (losing money in `active_2025_2026`, a strong-bull window,
because the warning fires on real but ultimately-mean-reverting covariance
noise and the guard then fully abandons 00631L's leverage for the whole
persistence window) might be avoidable if the guard only trims exposure rather
than eliminating it, since a partial cap costs less when the warning is a false
positive and still gives some protection when it is not.

This is a research-only promotion check, structured identically to
backtest_group_a_plus_leveraged_etf_timing_guard.py (that script is imported
from, not modified) with one added dimension: cap_fraction, the fraction of
00631L's regime weight moved to 0050 on a guarded day (1.0 reproduces the
already-tested full shift as a sanity check; this script also tries 0.25,
0.5, 0.75). Uses the already-refined negative_covariance_and_large_drag
warning policy with persistence_days=3 -- the best-performing trigger found in
the prior handoff's refinement sweep -- rather than re-sweeping the trigger
policy again (avoids re-tuning two dimensions on the same fixed window; see
feedback_overfitting_fixed_window_tuning memory).
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
from backtest_group_a_plus_policy_signal import _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.integrations.leveraged_etf_timing_anomaly import TimingAnomalyThresholds  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402
from scripts.evaluate.backtest_group_a_plus_leveraged_etf_timing_guard import (  # noqa: E402
    WINDOWS,
    _build_timing_warnings,
    _delta,
    _promoted,
    _resolve_end,
    _resolve_end_from_db,
    _weights_by_regime,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_guard_partial_cap_2604_27287.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_leveraged_etf_timing_guard_partial_cap_2604_27287.csv"
DEFAULT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "leveraged_etf_timing_guard_partial_cap_2604_27287.md"

CAP_FRACTIONS = (0.25, 0.5, 0.75, 1.0)


def _cap_00631l_to_0050(weights: dict[str, float], *, cap_fraction: float) -> dict[str, float]:
    out = dict(weights)
    total = float(out.get("00631L.TW", 0.0) or 0.0)
    amount = total * float(cap_fraction)
    out["00631L.TW"] = total - amount
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + amount
    return _normalize(out)


def _extended_weight_map(weights: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out = dict(weights)
    for regime, base in weights.items():
        for cap_fraction in CAP_FRACTIONS:
            out[f"{regime}__timing_guard_cap{cap_fraction}"] = _cap_00631l_to_0050(base, cap_fraction=cap_fraction)
    return out


def _variant_regimes(base_regimes: pd.Series, warnings: pd.DataFrame, *, cap_fraction: float) -> pd.Series:
    prev_warning = warnings.shift(1, fill_value=False).reindex(base_regimes.index, fill_value=False).astype(bool)
    out = base_regimes.astype(str).copy()
    for dt, regime in base_regimes.astype(str).items():
        if bool(prev_warning.loc[dt, "00631L.TW"]):
            out.loc[dt] = f"{regime}__timing_guard_cap{cap_fraction}"
    return out


def run_window(
    *,
    db_path: Path,
    label: str,
    start: str,
    end: str,
    initial_value: float,
    thresholds: TimingAnomalyThresholds,
    rolling_window: int,
    warning_policy: str,
    persistence_days: int,
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
    for cap_fraction in CAP_FRACTIONS:
        regimes = _variant_regimes(frame["execution_regime"].astype(str), warnings, cap_fraction=cap_fraction)
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
        curves[f"timing_guard_cap{cap_fraction}"] = curve.to_numpy()
        variants[str(cap_fraction)] = {
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
        "warning_count_00631l": int(warnings["00631L.TW"].sum()),
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
    for cap_fraction in CAP_FRACTIONS:
        key = str(cap_fraction)
        deltas = [item["variant_results"][key]["delta_vs_baseline"] for item in window_reports]
        promotion_ready_windows = [
            item["window"] for item in window_reports if item["variant_results"][key]["promotion_ready"]
        ]
        variant_summary[key] = {
            "promotion_ready_window_count": len(promotion_ready_windows),
            "promotion_ready_windows": promotion_ready_windows,
            "average_delta_final_value": float(sum(d["final_value"] for d in deltas) / len(deltas)),
            "average_delta_sharpe": float(sum(d["sharpe_ratio"] for d in deltas) / len(deltas)),
            "worst_delta_max_drawdown": float(min(d["max_drawdown"] for d in deltas)),
            "worst_delta_final_value": float(min(d["final_value"] for d in deltas)),
        }
    best_cap = max(variant_summary, key=lambda key: variant_summary[key]["average_delta_final_value"])
    decision = "do_not_promote_keep_shadow"
    if variant_summary[best_cap]["promotion_ready_window_count"] == len(window_reports):
        decision = "eligible_for_manual_review_not_auto_promote"

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_leveraged_etf_timing_guard_partial_cap_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2604.27287v1 A Levered ETF Anomaly Explained (direction #9 follow-up)",
        "policy": "research_only_no_weight_change",
        "decision": decision,
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "inputs": {
            "initial_value": float(args.initial_value),
            "rolling_window": int(args.rolling_window),
            "warning_policy": str(args.warning_policy),
            "persistence_days": int(args.persistence_days),
            "cap_fractions_tested": list(CAP_FRACTIONS),
            "thresholds": thresholds.__dict__,
            "windows": [{"label": label, "start": start, "end": end} for label, start, end in WINDOWS],
        },
        "variant_summary": variant_summary,
        "best_cap_fraction_by_average_final_value_delta": best_cap,
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
        "# Leveraged ETF Timing Guard Partial-Cap Backtest",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source: `{report['research_source']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']}`",
        "",
        "## Variant Summary (cap_fraction = fraction of 00631L weight moved to 0050 on a guarded day)",
    ]
    for cap_fraction, summary in report["variant_summary"].items():
        lines.extend(
            [
                "",
                f"### cap_fraction={cap_fraction}",
                "",
                f"- Promotion-ready windows: `{summary['promotion_ready_window_count']}`",
                f"- Average delta final value: `{summary['average_delta_final_value']:.2f}`",
                f"- Worst delta final value: `{summary['worst_delta_final_value']:.2f}`",
                f"- Average delta Sharpe: `{summary['average_delta_sharpe']:.4f}`",
                f"- Worst delta max drawdown: `{summary['worst_delta_max_drawdown']:.4f}`",
            ]
        )
    lines.extend(["", "## Window Results"])
    for item in report["window_reports"]:
        lines.extend(["", f"### {item['window']}", ""])
        for cap_fraction, detail in item["variant_results"].items():
            delta = detail["delta_vs_baseline"]
            lines.append(
                f"- `cap={cap_fraction}`: final `{delta['final_value']:.2f}`, Sharpe `{delta['sharpe_ratio']:.4f}`, "
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
    parser.add_argument("--warning-policy", default="negative_covariance_and_large_drag")
    parser.add_argument("--persistence-days", type=int, default=3)
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
    for cap_fraction, summary in report["variant_summary"].items():
        print(
            f"  cap={cap_fraction}: promotion_ready_windows={summary['promotion_ready_window_count']}/4 "
            f"avg_final_delta={summary['average_delta_final_value']:.2f} "
            f"worst_final_delta={summary['worst_delta_final_value']:.2f}"
        )


if __name__ == "__main__":
    main()
