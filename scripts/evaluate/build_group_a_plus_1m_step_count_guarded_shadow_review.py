#!/usr/bin/env python3
"""Build a guarded review for GroupA+ PPO step-count ablation results."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_100K = PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260814_231928.json"
DEFAULT_500K = PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260814_224346.json"
DEFAULT_1M = PROJECT_ROOT / "results/group_a_backtest_20250101_20260814_20260815_002023.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ppo_1m_step_count_guarded_shadow_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ppo_1m_step_count_guarded_shadow_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ppo_step_count_guarded_shadow_review/history"
INVERSE_TICKER = "00632R.TW"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["group_a"]["result"]
    return {
        "path": str(path),
        "model_name": payload["group_a"].get("model_name"),
        "timesteps": int(payload.get("timesteps") or 0),
        "train_start": payload.get("train_start"),
        "train_end": payload.get("train_end"),
        "backtest_start": result.get("backtest_start"),
        "backtest_end": result.get("backtest_end"),
        "result": result,
    }


def _metrics(item: dict[str, Any]) -> dict[str, Any]:
    result = item["result"]
    rl = result.get("rl_metrics") or {}
    return {
        "model_name": item.get("model_name"),
        "timesteps": item.get("timesteps"),
        "final_value": float(result.get("final_value", 0.0) or 0.0),
        "total_return": float(rl.get("total_return", 0.0) or 0.0),
        "annual_return": float(rl.get("annual_return", 0.0) or 0.0),
        "sharpe": float(rl.get("sharpe", 0.0) or 0.0),
        "max_drawdown": float(rl.get("max_drawdown", 0.0) or 0.0),
        "volatility": float(rl.get("volatility", 0.0) or 0.0),
        "num_trades": int(result.get("num_trades", 0) or 0),
        "fees_paid_estimate": float(result.get("fees_paid_estimate", 0.0) or 0.0),
        "pva_sigmoid_count": int(result.get("pva_sigmoid_count", 0) or 0),
        "dca_total_contributions": float(result.get("dca_total_contributions", 0.0) or 0.0),
    }


def _curve(item: dict[str, Any]) -> pd.Series:
    result = item["result"]
    equity = [float(v) for v in result.get("equity_curve", [])]
    sjm_dates = [str(row["date"]) for row in result.get("sjm_state_history", [])]
    dates = sjm_dates + [str(result.get("backtest_end"))]
    if len(dates) != len(equity):
        raise ValueError(f"Cannot align curve for {item.get('model_name')}: {len(dates)} dates vs {len(equity)} values")
    return pd.Series(equity, index=pd.to_datetime(dates), dtype=float).sort_index()


def _period_return(curve: pd.Series, start: str, end: str) -> float | None:
    window = curve.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def _quarter_returns(curve: pd.Series) -> dict[str, float]:
    out: dict[str, float] = {}
    for period, window in curve.groupby(curve.index.to_period("Q")):
        if len(window) >= 2:
            out[str(period)] = float(window.iloc[-1] / window.iloc[0] - 1.0)
    return out


def _inverse_exposure(item: dict[str, Any]) -> dict[str, Any]:
    result = item["result"]
    pva = list(result.get("pva_sigmoid_history") or [])
    forced = list(result.get("inverse_forced_exit_history") or [])
    pva_weights = [
        float((row.get("target_weights") or {}).get(INVERSE_TICKER, 0.0) or 0.0)
        for row in pva
        if isinstance(row, dict)
    ]
    pva_touch_dates = [
        str(row.get("date"))
        for row in pva
        if float((row.get("target_weights") or {}).get(INVERSE_TICKER, 0.0) or 0.0) > 1e-12
    ]
    forced_weights = [
        float(row.get("current_inverse_weight", 0.0) or 0.0)
        for row in forced
        if isinstance(row, dict)
    ]
    forced_dates = [str(row.get("date")) for row in forced if isinstance(row, dict)]
    return {
        "inverse_ticker": INVERSE_TICKER,
        "pva_logged_touch_count": len(pva_touch_dates),
        "pva_logged_first_touch_date": pva_touch_dates[0] if pva_touch_dates else None,
        "pva_logged_last_touch_date": pva_touch_dates[-1] if pva_touch_dates else None,
        "pva_logged_max_target_weight": max(pva_weights or [0.0]),
        "forced_exit_count": int((result.get("inverse_hedge_config") or {}).get("forced_exit_count", len(forced)) or 0),
        "forced_exit_dates": forced_dates,
        "max_forced_exit_current_weight": max(forced_weights or [0.0]),
        "complete_daily_exposure_log_available": False,
        "governance_status": "blocked" if pva_touch_dates or forced_dates else "not_blocked_by_saved_logs",
    }


def _overfit_risk(
    *,
    metrics: dict[str, dict[str, Any]],
    deltas: dict[str, dict[str, float]],
    q3_2026: dict[str, float | None],
    issue_window: dict[str, float | None],
    inverse: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    delta = deltas["1m_minus_100k"]
    full_window_helpful = (
        float(delta["final_value"]) > 0.0
        and float(delta["sharpe"]) > 0.0
    )
    q3_weaker = (
        q3_2026.get("1m") is not None
        and q3_2026.get("100k") is not None
        and float(q3_2026["1m"]) < float(q3_2026["100k"])
    )
    issue_weaker = (
        issue_window.get("1m") is not None
        and issue_window.get("100k") is not None
        and float(issue_window["1m"]) < float(issue_window["100k"])
    )
    volatility_higher = float(delta["volatility"]) > 0.0
    fees_higher = float(delta["fees_paid_estimate"]) > 0.0
    inverse_blocked = inverse["1m"]["governance_status"] == "blocked"
    incomplete_exposure_log = not bool(inverse["1m"]["complete_daily_exposure_log_available"])
    signals = {
        "full_window_final_and_sharpe_improved": full_window_helpful,
        "q3_2026_weaker_than_100k": q3_weaker,
        "issue_window_weaker_than_100k": issue_weaker,
        "volatility_higher_than_100k": volatility_higher,
        "fees_higher_than_100k": fees_higher,
        "saved_logs_include_00632r_exposure": inverse_blocked,
        "complete_daily_exposure_log_missing": incomplete_exposure_log,
    }
    risk_score = sum(
        1
        for key, value in signals.items()
        if key != "full_window_final_and_sharpe_improved" and value
    )
    if full_window_helpful and risk_score >= 4:
        label = "high_overfit_risk"
    elif full_window_helpful and risk_score >= 2:
        label = "moderate_overfit_risk"
    elif full_window_helpful:
        label = "low_overfit_risk_but_unproven"
    else:
        label = "not_a_useful_candidate"
    return {
        "label": label,
        "risk_score": risk_score,
        "signals": signals,
        "interpretation": (
            "1M improves the full-window aggregate but deteriorates several "
            "out-of-window-like risk checks, so treat the improvement as "
            "window-specific until multi-window and zero-00632R evidence exists."
            if label in {"high_overfit_risk", "moderate_overfit_risk"}
            else "Current saved evidence does not prove robust generalization."
        ),
        "production_implication": "do_not_replace_latest",
    }


def build_report(
    *,
    path_100k: Path,
    path_500k: Path,
    path_1m: Path,
    as_of: str,
) -> dict[str, Any]:
    items = {
        "100k": _load_result(path_100k),
        "500k": _load_result(path_500k),
        "1m": _load_result(path_1m),
    }
    curves = {name: _curve(item) for name, item in items.items()}
    metrics = {name: _metrics(item) for name, item in items.items()}
    quarter_returns = {name: _quarter_returns(curve) for name, curve in curves.items()}
    inverse = {name: _inverse_exposure(item) for name, item in items.items()}

    m100 = metrics["100k"]
    m1m = metrics["1m"]
    deltas = {
        "1m_minus_100k": {
            "final_value": m1m["final_value"] - m100["final_value"],
            "sharpe": m1m["sharpe"] - m100["sharpe"],
            "max_drawdown": m1m["max_drawdown"] - m100["max_drawdown"],
            "volatility": m1m["volatility"] - m100["volatility"],
            "fees_paid_estimate": m1m["fees_paid_estimate"] - m100["fees_paid_estimate"],
        }
    }
    issue_window = {
        name: _period_return(curve, "2026-08-04", "2026-08-14")
        for name, curve in curves.items()
    }
    q3_2026 = {name: quarter_returns[name].get("2026Q3") for name in quarter_returns}
    overfit_risk = _overfit_risk(
        metrics=metrics,
        deltas=deltas,
        q3_2026=q3_2026,
        issue_window=issue_window,
        inverse=inverse,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if inverse["1m"]["governance_status"] == "blocked":
        blockers.append("1m_saved_logs_include_00632r_exposure")
    if q3_2026["1m"] is not None and q3_2026["100k"] is not None and q3_2026["1m"] < q3_2026["100k"]:
        blockers.append("1m_underperforms_100k_in_2026q3_downturn_proxy")
    if deltas["1m_minus_100k"]["volatility"] > 0:
        warnings.append("1m_volatility_above_100k")
    if not inverse["1m"]["complete_daily_exposure_log_available"]:
        warnings.append("complete_daily_00632r_exposure_log_missing")

    decision = "keep_1m_shadow_only"
    if not blockers and m1m["final_value"] > m100["final_value"] and m1m["sharpe"] >= m100["sharpe"]:
        decision = "candidate_for_multi_window_shadow"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ppo_1m_step_count_guarded_shadow_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_latest_replacement" if blockers else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "inputs": {name: item["path"] for name, item in items.items()},
        "overall_metrics": metrics,
        "deltas": deltas,
        "quarter_returns": quarter_returns,
        "focus_windows": {
            "2026Q3": q3_2026,
            "2026_08_04_to_2026_08_14": issue_window,
        },
        "inverse_etf_governance": inverse,
        "overfit_risk": overfit_risk,
        "decision": {
            "decision": decision,
            "one_m_training_steps_helpful": m1m["final_value"] > m100["final_value"] and m1m["sharpe"] > m100["sharpe"],
            "replace_latest": False,
            "tune_latest": False,
            "promote_1m_to_production": False,
            "blocking_reasons": blockers,
            "warning_reasons": [*warnings, f"overfit_risk:{overfit_risk['label']}"],
            "required_next_evidence": [
                "multi_window_oos_replay",
                "complete_daily_target_weight_log",
                "zero_00632r_or_signed_manual_inverse_etf_review",
                "2026q3_downturn_resilience_improvement",
            ],
        },
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def _write_md(report: dict[str, Any], path: Path) -> None:
    metrics = report["overall_metrics"]
    delta = report["deltas"]["1m_minus_100k"]
    decision = report["decision"]
    focus = report["focus_windows"]
    inverse = report["inverse_etf_governance"]
    overfit = report["overfit_risk"]
    lines = [
        "# GroupA+ PPO 1M Step Count Guarded Shadow Review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Overall Metrics",
        "",
        "| Steps | Final value | Sharpe | MDD | Vol | Trades | Fees |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("100k", "500k", "1m"):
        row = metrics[name]
        lines.append(
            f"| {name} | {row['final_value']:,.2f} | {row['sharpe']:.3f} | "
            f"{row['max_drawdown']:.2%} | {row['volatility']:.2%} | "
            f"{row['num_trades']} | {row['fees_paid_estimate']:,.2f} |"
        )
    lines.extend(
        [
            "",
            "## 1M Delta Vs 100k",
            "",
            f"- Final value: `{delta['final_value']:,.2f}`",
            f"- Sharpe: `{delta['sharpe']:.4f}`",
            f"- MDD: `{delta['max_drawdown']:.2%}`",
            f"- Volatility: `{delta['volatility']:.2%}`",
            f"- Fees: `{delta['fees_paid_estimate']:,.2f}`",
            "",
            "## Focus Windows",
            "",
            f"- 2026Q3 100k: `{_pct(focus['2026Q3']['100k'])}`",
            f"- 2026Q3 500k: `{_pct(focus['2026Q3']['500k'])}`",
            f"- 2026Q3 1M: `{_pct(focus['2026Q3']['1m'])}`",
            f"- 2026-08-04 to 2026-08-14 100k: `{_pct(focus['2026_08_04_to_2026_08_14']['100k'])}`",
            f"- 2026-08-04 to 2026-08-14 500k: `{_pct(focus['2026_08_04_to_2026_08_14']['500k'])}`",
            f"- 2026-08-04 to 2026-08-14 1M: `{_pct(focus['2026_08_04_to_2026_08_14']['1m'])}`",
            "",
            "## 00632R Governance",
            "",
        ]
    )
    for name in ("100k", "500k", "1m"):
        row = inverse[name]
        lines.append(
            f"- {name}: status `{row['governance_status']}`, "
            f"PVA touch count `{row['pva_logged_touch_count']}`, "
            f"PVA max target `{row['pva_logged_max_target_weight']:.4f}`, "
            f"forced exits `{row['forced_exit_count']}`"
        )
    lines.extend(
        [
            "",
            "## Overfit Risk",
            "",
            f"- Label: `{overfit['label']}`",
            f"- Risk score: `{overfit['risk_score']}`",
            f"- Signals: `{overfit['signals']}`",
            f"- Interpretation: `{overfit['interpretation']}`",
            "",
            "## Decision",
            "",
            f"- 1M helpful on full-window final value / Sharpe: `{decision['one_m_training_steps_helpful']}`",
            f"- Replace latest: `{decision['replace_latest']}`",
            f"- Tune latest: `{decision['tune_latest']}`",
            f"- Promote 1M to production: `{decision['promote_1m_to_production']}`",
            f"- Blocking reasons: `{decision['blocking_reasons']}`",
            f"- Warning reasons: `{decision['warning_reasons']}`",
            "",
            "No latest strategy, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(report["as_of"]).replace("-", "")
        (history_dir / f"ppo_1m_step_count_guarded_shadow_review_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-100k", default=str(DEFAULT_100K))
    parser.add_argument("--backtest-500k", default=str(DEFAULT_500K))
    parser.add_argument("--backtest-1m", default=str(DEFAULT_1M))
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        path_100k=_resolve(args.backtest_100k),
        path_500k=_resolve(args.backtest_500k),
        path_1m=_resolve(args.backtest_1m),
        as_of=str(args.as_of),
    )
    write_report(
        report,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"]["decision"],
                "one_m_training_steps_helpful": report["decision"]["one_m_training_steps_helpful"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
