#!/usr/bin/env python3
"""Fable 00631L direction #10 (2026-08-22): letf_quadratic_bound.py as a
backward-looking risk-budget sizing guard, not a forecast.

Context: GROUP_A_PLUS_20260810_2301_03186_QUADRATIC_BOUND_REGIME_CROSSCHECK_
HANDOFF.md already used arXiv:2301.03186's certified quadratic (m1,m2) bound
as a FORWARD crosscheck of the leveraged_compounding_regime.py classifier
(does the classifier's TREND_PERSISTENT/MEAN_REVERTING label predict which
way *future* (m1,m2) will move) and found no robust lift after correcting for
pseudo-replication. That is a genuinely different question from this one.
Because leveraged-ETF cumulative log-return depends only on the aggregate
(m1,m2) of the realized daily-return multiset -- not path order (see that
handoff's section 2 for the summation-is-order-invariant proof) -- trying to
forecast *future* (m1,m2) from *past path shape* is mathematically unrelated
to the realized value itself. But using the *already-realized* trailing
window's own (m1,m2) as a same-scale estimate of near-term future (m1,m2) is
a standard, much more defensible assumption (volatility persistence /
clustering is a well-documented stylized fact, unlike path-shape
persistence) -- and that prior handoff's own "未完成事項" (postscript) section
9 explicitly flagged this exact "certified bound as a backward-looking
risk-budget/stress-test tool" framing as the one residual, not-yet-tried use
of the module. This script is that test.

Guard rule: using ONLY the trailing `--window` days of realized 0050 daily
log-returns (shifted by 1 day, no same-day lookahead), compute:
  - the certified quadratic lower bound on 00631L's n-day cumulative
    log-return the paper's Theorem 1/Remark 2 formula implies for that
    (m1,m2) pair (leverage=2.0, y0=Taiwan's daily +-10% limit, matching the
    y0 anchor already used in the 2026-08-10 crosscheck for consistency);
  - the trivial 1x reference (n * m1, i.e. what holding 0050 outright would
    have returned over the same realized window).
The guard fires when the certified 2x floor is BELOW the 1x reference --
i.e. the paper's own worst-case guarantee for 00631L, given the volatility
level actually just realized, does not clear simply holding 0050 -- and
shifts 00631L's regime weight to 0050 for that day (reusing the cap_fraction
mechanic from backtest_group_a_plus_leveraged_etf_timing_guard_partial_cap.py,
tested at cap_fraction=1.0 only here since this is a new, previously-untested
trigger and stacking an untested cap-size sweep on top of an untested trigger
risks conflating which dimension is doing the work).

Research-only. Never touches latest strategy, golden1_0531, signals,
execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.integrations.letf_quadratic_bound import (  # noqa: E402
    remark2_lower_bound_coeffs,
    quadratic_lower_bound_log_return,
)
from group_a_plus.runners.latest import run_latest  # noqa: E402
from scripts.evaluate.backtest_group_a_plus_leveraged_etf_timing_guard import (  # noqa: E402
    WINDOWS,
    _resolve_end,
    _resolve_end_from_db,
    _weights_by_regime,
    _delta,
    _promoted,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_quadratic_bound_risk_budget_guard_2301_03186.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_quadratic_bound_risk_budget_guard_2301_03186.csv"
DEFAULT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "quadratic_bound_risk_budget_guard_2301_03186.md"

DEFAULT_ROLLING_WINDOW = 60
LEVERAGE = 2.0
TW_DAILY_LIMIT_Y0 = math.log(1.0 - 0.10)


def _shift_00631l_to_0050(weights: dict[str, float]) -> dict[str, float]:
    out = dict(weights)
    amount = float(out.get("00631L.TW", 0.0) or 0.0)
    out["00631L.TW"] = 0.0
    out["0050.TW"] = float(out.get("0050.TW", 0.0) or 0.0) + amount
    return _normalize(out)


def _extended_weight_map(weights: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    out = dict(weights)
    for regime, base in weights.items():
        out[f"{regime}__qbound_guard"] = _shift_00631l_to_0050(base)
    return out


def _load_0050_logret(db_path: Path) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = '0050.TW' ORDER BY dt").fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.set_index("dt")["close"].astype(float)
    return np.log(close).diff().dropna()


def _build_qbound_warning(index: pd.DatetimeIndex, logret: pd.Series, *, window: int) -> pd.Series:
    m1 = logret.rolling(window).mean()
    m2 = (logret**2).rolling(window).mean()
    coeffs = remark2_lower_bound_coeffs(LEVERAGE, TW_DAILY_LIMIT_Y0)
    bound = pd.Series(
        [
            quadratic_lower_bound_log_return(a, b, window, coeffs) if pd.notna(a) and pd.notna(b) else float("nan")
            for a, b in zip(m1, m2)
        ],
        index=logret.index,
    )
    reference_1x = window * m1
    warning = (bound < reference_1x).fillna(False).astype(bool)
    # previous-day only: today's guard decision uses information available
    # through yesterday's close, no same-day lookahead
    warning = warning.shift(1, fill_value=False).reindex(index, method="ffill").fillna(False).astype(bool)
    return warning


def _variant_regimes(base_regimes: pd.Series, warning: pd.Series) -> pd.Series:
    out = base_regimes.astype(str).copy()
    aligned = warning.reindex(base_regimes.index, fill_value=False).astype(bool)
    for dt, regime in base_regimes.astype(str).items():
        if bool(aligned.loc[dt]):
            out.loc[dt] = f"{regime}__qbound_guard"
    return out


def run_window(
    *,
    db_path: Path,
    label: str,
    start: str,
    end: str,
    initial_value: float,
    rolling_window: int,
    logret: pd.Series,
) -> tuple[dict[str, Any], pd.DataFrame]:
    end_for_runner = _resolve_end_from_db(db_path, end)
    latest_report, frame = run_latest(start, end_for_runner, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    resolved_end = _resolve_end(end_for_runner, frame)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    weights = _weights_by_regime(latest_report)
    extended_weights = _extended_weight_map(weights)
    warning = _build_qbound_warning(frame.index, logret, window=rolling_window)

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

    regimes = _variant_regimes(frame["execution_regime"].astype(str), warning)
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

    curves = pd.DataFrame(
        {
            "date": frame.index,
            "window": label,
            "baseline_latest": baseline_curve.to_numpy(),
            "qbound_guard": curve.to_numpy(),
        }
    )

    return {
        "window": label,
        "start": start,
        "end": resolved_end,
        "active_strategy_id": latest_report.get("active_strategy_id"),
        "baseline_metrics": baseline_metrics,
        "baseline_execution": baseline_exec,
        "guard_metrics": metrics,
        "delta_vs_baseline": delta,
        "promotion_ready": _promoted(delta),
        "changed_days": int((regimes != frame["execution_regime"].astype(str)).sum()),
        "warning_days": int(warning.reindex(frame.index, fill_value=False).sum()),
        "execution": execution,
        "dividend_coverage": dividend_coverage,
    }, curves


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], pd.DataFrame]:
    db_path = Path(args.db)
    logret = _load_0050_logret(db_path)
    window_reports = []
    curve_frames = []
    for label, start, end in WINDOWS:
        report, curves = run_window(
            db_path=db_path,
            label=label,
            start=start,
            end=end,
            initial_value=float(args.initial_value),
            rolling_window=int(args.rolling_window),
            logret=logret,
        )
        window_reports.append(report)
        curve_frames.append(curves)

    deltas = [item["delta_vs_baseline"] for item in window_reports]
    promotion_ready_windows = [item["window"] for item in window_reports if item["promotion_ready"]]
    summary = {
        "promotion_ready_window_count": len(promotion_ready_windows),
        "promotion_ready_windows": promotion_ready_windows,
        "average_delta_final_value": float(sum(d["final_value"] for d in deltas) / len(deltas)),
        "average_delta_sharpe": float(sum(d["sharpe_ratio"] for d in deltas) / len(deltas)),
        "worst_delta_final_value": float(min(d["final_value"] for d in deltas)),
        "worst_delta_max_drawdown": float(min(d["max_drawdown"] for d in deltas)),
    }
    decision = "do_not_promote_keep_shadow"
    if summary["promotion_ready_window_count"] == len(window_reports):
        decision = "eligible_for_manual_review_not_auto_promote"

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_quadratic_bound_risk_budget_guard_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2301.03186 (Fable 00631L direction #10, backward-looking risk-budget use, not the already-refuted forward regime-forecast use)",
        "policy": "research_only_no_weight_change",
        "decision": decision,
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "inputs": {
            "initial_value": float(args.initial_value),
            "rolling_window": int(args.rolling_window),
            "leverage": LEVERAGE,
            "y0_daily_limit": TW_DAILY_LIMIT_Y0,
            "windows": [{"label": label, "start": start, "end": end} for label, start, end in WINDOWS],
        },
        "summary": summary,
        "window_reports": window_reports,
        "promotion_requirements": [
            "candidate must improve final value, Sharpe, Sortino, and not worsen max drawdown in every window",
            "candidate must pass separate signed promotion review before any live wiring",
            "this shadow does not emit live target weights or execution orders",
        ],
    }
    return report, pd.concat(curve_frames, ignore_index=True)


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Quadratic Bound Risk-Budget Guard Backtest",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source: `{report['research_source']}`",
        f"- Decision: `{report['decision']}`",
        "",
        "## Summary",
        "",
        f"- Promotion-ready windows: `{s['promotion_ready_window_count']}`",
        f"- Average delta final value: `{s['average_delta_final_value']:.2f}`",
        f"- Worst delta final value: `{s['worst_delta_final_value']:.2f}`",
        f"- Average delta Sharpe: `{s['average_delta_sharpe']:.4f}`",
        f"- Worst delta max drawdown: `{s['worst_delta_max_drawdown']:.4f}`",
        "",
        "## Window Results",
    ]
    for item in report["window_reports"]:
        d = item["delta_vs_baseline"]
        lines.append(
            f"- `{item['window']}`: final `{d['final_value']:.2f}`, Sharpe `{d['sharpe_ratio']:.4f}`, "
            f"Sortino `{d['sortino_ratio']:.4f}`, MDD `{d['max_drawdown']:.4f}`, "
            f"warning_days `{item['warning_days']}`, changed_days `{item['changed_days']}`, "
            f"promotion_ready `{item['promotion_ready']}`"
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
    parser.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_WINDOW)
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
    print(f"Decision: {report['decision']}")
    for item in report["window_reports"]:
        d = item["delta_vs_baseline"]
        print(
            f"  {item['window']}: warning_days={item['warning_days']} delta_final={d['final_value']:.2f} "
            f"delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f} "
            f"promotion_ready={item['promotion_ready']}"
        )


if __name__ == "__main__":
    main()
