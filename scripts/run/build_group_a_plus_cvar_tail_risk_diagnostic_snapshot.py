#!/usr/bin/env python3
"""Refresh the CVaR/tail-risk diagnostic snapshot for regular human review.

Research-only, pure logging step -- see
scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py (inspired by
2607.03082v1) for the full diagnostic. That evaluator already produces
everything of transferable value from the paper (VaR/ES/Hill/POT-GPD tail
diagnostics, STARR ranking); the CVaR-min/tangency optimizer part is not
promotable (min_cvar degenerates to 100% cash, tangency_cvar sacrifices most
of 00631L's upside for a modest drawdown improvement). Until this snapshot
was added, that evaluator only ran as a one-off manual invocation with a
hardcoded --end date, so report/group_a_plus/latest/ never had a current
tail-risk diagnostic for periodic review (Fable independent review,
2026-07-17: "CVaR診斷表沒有排進任何定期review節奏").

This script re-runs the same evaluator with --end resolved to the latest
available OHLCV date, writes the full report to results/ (date-stamped, same
convention as the evaluator's own CLI), and overwrites a compact "latest"
pointer at report/group_a_plus/latest/cvar_tail_risk_diagnostic.json so a
human reviewing that directory always sees a current snapshot. Never changes
target weights, execution guards, or the live signal.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py (see BEST_EFFORT_STEP_NAMES there).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import build_report  # noqa: E402

DEFAULT_START = "2025-01-02"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "cvar_tail_risk_diagnostic.json"


def _compact_latest(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("strategy_summary", {})
    tail_probe = (summary.get("00631l_only") or {}).get("summary", {})
    return {
        "report_type": report.get("report_type"),
        "status": report.get("status"),
        "policy": report.get("policy"),
        "generated_at": report.get("generated_at"),
        "source_paper": report.get("source_paper"),
        "window": report.get("window"),
        "ranking_by_starr95": report.get("ranking_by_starr95"),
        "00631l_only_tail_diagnostics": {
            "var_loss_95": tail_probe.get("var_loss_95"),
            "var_loss_99": tail_probe.get("var_loss_99"),
            "expected_shortfall_loss_95": tail_probe.get("expected_shortfall_loss_95"),
            "expected_shortfall_loss_99": tail_probe.get("expected_shortfall_loss_99"),
            "expected_tail_gain_95": tail_probe.get("expected_tail_gain_95"),
            "expected_tail_gain_99": tail_probe.get("expected_tail_gain_99"),
            "max_drawdown": tail_probe.get("max_drawdown"),
            "starr_95": tail_probe.get("starr_95"),
            "rachev_95_95": tail_probe.get("rachev_95_95"),
            "rachev_99_99": tail_probe.get("rachev_99_99"),
            "hill_95": tail_probe.get("hill_95"),
            "hill_99": tail_probe.get("hill_99"),
            "pot_gpd_95": tail_probe.get("pot_gpd_95"),
            "pot_gpd_99": tail_probe.get("pot_gpd_99"),
        },
        "promotion_decision": report.get("promotion_decision"),
        "interpretation": report.get("interpretation"),
        "full_report_output": report.get("_full_report_output"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default="latest")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "results"))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_PATH))
    args = parser.parse_args()

    db_path = Path(args.db)
    end = _resolve_end_date(db_path, args.end)
    stamp = end.replace("-", "")

    report, frame, allocations = build_report(
        db_path=db_path,
        start=args.start,
        end=end,
        warmup_days=900,
        lookback=252,
        min_lookback=126,
        rebalance_every=21,
        cost_bps=10.0,
        grid_step=0.05,
        max_00631l=0.20,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    full_output = output_dir / f"cvar_tail_risk_diagnostic_shadow_{stamp}.json"
    frame.to_csv(full_output.with_name(full_output.stem + "_returns.csv"), encoding="utf-8-sig")
    allocations.to_csv(full_output.with_name(full_output.stem + "_allocations.csv"), index=False, encoding="utf-8-sig")
    report["_full_report_output"] = str(full_output)
    full_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    latest_output = Path(args.latest_output)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.write_text(
        json.dumps(_compact_latest(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Full report: {full_output}")
    print(f"Latest snapshot: {latest_output}")


if __name__ == "__main__":
    main()
