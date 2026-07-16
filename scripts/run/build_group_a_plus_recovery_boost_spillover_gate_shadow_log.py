#!/usr/bin/env python3
"""Append today's recovery-boost spillover-gate state to a live shadow log.

Research-only, pure logging step -- see
group_a_plus/integrations/recovery_boost_spillover_gate_shadow.py for why this
exists: the historical five-crisis fold data cannot test this gate at all
(close-only proxy folds, missing tickers), and even the real 2017-2026 windows
never had a recovery episode coincide with a spillover spike. This starts
accumulating real daily observations instead of waiting on data that does not
exist. Never changes target weights, execution guards, or the latest live
signal.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py (see BEST_EFFORT_STEP_NAMES there).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.recovery_boost_spillover_gate_shadow import (  # noqa: E402
    append_shadow_log_row,
    build_shadow_log_row,
)
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_recovery_boost_spillover_gate import _load_ohlcv  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment import COMMON_A2118_KW  # noqa: E402
from group_a_plus.integrations.network_volatility_spillover_shadow import DEFAULT_TICKERS  # noqa: E402

DEFAULT_LOG_PATH = PROJECT_ROOT / "results" / "group_a_plus_recovery_boost_spillover_gate_shadow_log.jsonl"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "recovery_boost_spillover_gate_shadow.json"


def build_row(
    *,
    db_path: Path,
    panel: str | None,
    regime_lookback_days: int,
    ohlcv_lookback_days: int,
    end: date,
    max_age_days: float,
    max_systemic_percentile: float,
    max_target_in_percentile: float,
) -> dict:
    resolved_end = _resolve_end_date(db_path, "latest")
    regime_start = (end - timedelta(days=regime_lookback_days)).isoformat()
    report, frame = run_a2118(
        start=regime_start,
        end=resolved_end,
        initial_value=1_000_000.0,
        db=db_path,
        ncf_panel_631l_path=panel,
        **COMMON_A2118_KW,
    )
    execution_regime = frame["execution_regime"].astype(str)

    ohlcv_start = (end - timedelta(days=ohlcv_lookback_days)).isoformat()
    ohlcv = _load_ohlcv(db_path, DEFAULT_TICKERS, ohlcv_start, resolved_end)

    return build_shadow_log_row(
        execution_regime=execution_regime,
        ohlcv=ohlcv,
        max_age_days=max_age_days,
        max_systemic_percentile=max_systemic_percentile,
        max_target_in_percentile=max_target_in_percentile,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel", default=None, help="ncf_00631l panel CSV path for today's execution_regime; omit for the panel-free historical regime.")
    parser.add_argument("--regime-lookback-days", type=int, default=90)
    parser.add_argument("--ohlcv-lookback-days", type=int, default=600)
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--max-age-days", type=float, default=20)
    parser.add_argument("--max-systemic-percentile", type=float, default=0.80)
    parser.add_argument("--max-target-in-percentile", type=float, default=0.80)
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_PATH))
    args = parser.parse_args()

    row = build_row(
        db_path=Path(args.db),
        panel=args.panel,
        regime_lookback_days=int(args.regime_lookback_days),
        ohlcv_lookback_days=int(args.ohlcv_lookback_days),
        end=date.fromisoformat(args.end),
        max_age_days=args.max_age_days,
        max_systemic_percentile=args.max_systemic_percentile,
        max_target_in_percentile=args.max_target_in_percentile,
    )

    appended = append_shadow_log_row(row, Path(args.log))

    latest_path = Path(args.latest_output)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"status={row.get('status')} date={row.get('date')} boost_allowed={row.get('boost_allowed')} appended={appended}")
    print(f"Log: {args.log}")
    print(f"Latest: {latest_path}")


if __name__ == "__main__":
    main()
