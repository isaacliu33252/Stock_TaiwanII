#!/usr/bin/env python3
"""Sweep TSI no-add thresholds and confirmation modes.

Research-only wrapper around evaluate_group_a_plus_tsi_no_add_shadow.py. It
does not change live weights or execution guards.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_group_a_plus_crash_detector_overlap import DEFAULT_MARKET_STATE_FRAME, DEFAULT_NCF_PANEL
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _parse_windows, _resolve, build_report


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_no_add_sweep.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_no_add_sweep.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_no_add_sweep/history"
DEFAULT_THRESHOLDS = (0.75, 0.80, 0.85, 0.90, 0.95)
DEFAULT_ALERT_MODES = ("tsi_only", "tsi_and_existing_any", "tsi_and_blocking")
DEFAULT_GUARD_ADD_FRACTIONS = (0.0, 0.25, 0.50)


def _float_list(raw: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in raw.split(",") if item.strip())


def _str_list(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _combo_summary(report: dict[str, Any]) -> dict[str, Any]:
    totals = report.get("totals") or {}
    return {
        "threshold": report.get("tsi_threshold"),
        "alert_mode": report.get("alert_mode"),
        "guard_add_fraction": report.get("guard_add_fraction"),
        "tsi_alert_days": totals.get("tsi_alert_days"),
        "blocked_days": totals.get("blocked_days"),
        "delta_final_value_sum": totals.get("delta_final_value_sum"),
        "delta_sharpe_sum": totals.get("delta_sharpe_sum"),
        "delta_max_drawdown_sum": totals.get("delta_max_drawdown_sum"),
        "positive_final_value_windows": totals.get("positive_final_value_windows"),
        "non_worse_drawdown_windows": totals.get("non_worse_drawdown_windows"),
        "blocking_reasons": report.get("blocking_reasons") or [],
    }


def build_sweep(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    thresholds: tuple[float, ...],
    alert_modes: tuple[str, ...],
    guard_add_fractions: tuple[float, ...],
    initial_value: float,
    transaction_cost_bps: float,
    warmup_days: int,
    market_state_frame: Path,
    ncf_panel: Path,
    h20_max: float,
    mdd_min: float,
) -> dict[str, Any]:
    reports = []
    for add_fraction in guard_add_fractions:
        for mode in alert_modes:
            for threshold in thresholds:
                print(f"Evaluating threshold={threshold:.2f} mode={mode} add_fraction={add_fraction:.2f}")
                report = build_report(
                    db_path=db_path,
                    windows=windows,
                    initial_value=initial_value,
                    threshold=threshold,
                    transaction_cost_bps=transaction_cost_bps,
                    warmup_days=warmup_days,
                    market_state_frame=market_state_frame,
                    ncf_panel=ncf_panel,
                    h20_max=h20_max,
                    mdd_min=mdd_min,
                    alert_mode=mode,
                    guard_add_fraction=add_fraction,
                )
                reports.append(report)
    summaries = [_combo_summary(report) for report in reports]
    best_by_final_value = max(summaries, key=lambda item: float(item.get("delta_final_value_sum") or 0.0), default=None)
    best_by_drawdown = max(summaries, key=lambda item: float(item.get("delta_max_drawdown_sum") or 0.0), default=None)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_no_add_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "thresholds": list(thresholds),
        "alert_modes": list(alert_modes),
        "guard_add_fractions": list(guard_add_fractions),
        "summaries": summaries,
        "best_by_final_value": best_by_final_value,
        "best_by_drawdown": best_by_drawdown,
        "reports": reports,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    rows = []
    for item in payload.get("summaries") or []:
        rows.append(
            "| {thr:.2f} | {mode} | {add_fraction:.2f} | {alerts} | {blocked} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} |".format(
                thr=float(item.get("threshold") or 0.0),
                mode=item.get("alert_mode"),
                add_fraction=float(item.get("guard_add_fraction") or 0.0),
                alerts=int(item.get("tsi_alert_days") or 0),
                blocked=int(item.get("blocked_days") or 0),
                dfv=float(item.get("delta_final_value_sum") or 0.0),
                dsharpe=float(item.get("delta_sharpe_sum") or 0.0),
                dmdd=float(item.get("delta_max_drawdown_sum") or 0.0),
            )
        )
    best_final = payload.get("best_by_final_value") or {}
    best_dd = payload.get("best_by_drawdown") or {}
    return """# GroupA+ TSI No-Add Sweep

- status: `research_only`
- production_effect: `{production_effect}`
- promotion_allowed: `{promotion}`
- best_by_final_value: `{best_final_mode}` @ `{best_final_threshold}`, add_fraction `{best_final_add}`
- best_by_drawdown: `{best_dd_mode}` @ `{best_dd_threshold}`, add_fraction `{best_dd_add}`

| threshold | alert_mode | add_fraction | tsi_alert_days | event_days | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum |
|---:|---|---:|---:|---:|---:|---:|---:|
{rows}

## Governance

All variants remain shadow-only. None may change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
""".format(
        production_effect=payload.get("production_effect"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        best_final_mode=best_final.get("alert_mode"),
        best_final_threshold=best_final.get("threshold"),
        best_final_add=best_final.get("guard_add_fraction"),
        best_dd_mode=best_dd.get("alert_mode"),
        best_dd_threshold=best_dd.get("threshold"),
        best_dd_add=best_dd.get("guard_add_fraction"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - | - | - |",
    )


def write_sweep(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"tsi_no_add_sweep_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default")
    parser.add_argument("--thresholds", default=",".join(str(item) for item in DEFAULT_THRESHOLDS))
    parser.add_argument("--alert-modes", default=",".join(DEFAULT_ALERT_MODES))
    parser.add_argument("--guard-add-fractions", default=",".join(str(item) for item in DEFAULT_GUARD_ADD_FRACTIONS))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--market-state-frame", default=str(DEFAULT_MARKET_STATE_FRAME))
    parser.add_argument("--ncf-panel", default=str(DEFAULT_NCF_PANEL))
    parser.add_argument("--h20-max", type=float, default=0.22)
    parser.add_argument("--mdd-min", type=float, default=0.85)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_sweep(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        thresholds=_float_list(args.thresholds),
        alert_modes=_str_list(args.alert_modes),
        guard_add_fractions=_float_list(args.guard_add_fractions),
        initial_value=float(args.initial_value),
        transaction_cost_bps=float(args.transaction_cost_bps),
        warmup_days=int(args.warmup_days),
        market_state_frame=_resolve(args.market_state_frame),
        ncf_panel=_resolve(args.ncf_panel),
        h20_max=float(args.h20_max),
        mdd_min=float(args.mdd_min),
    )
    write_sweep(
        payload,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"TSI no-add sweep: {_resolve(args.output)}")
    print(json.dumps({"best_by_final_value": payload["best_by_final_value"], "best_by_drawdown": payload["best_by_drawdown"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
