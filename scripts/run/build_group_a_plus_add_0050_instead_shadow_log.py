#!/usr/bin/env python3
"""Append today's ADD_0050_INSTEAD TSMC concentration-divergence guard state
to a live shadow log.

Research-only, pure logging step -- see
group_a_plus/integrations/add_0050_instead_shadow_log.py for why this
exists: the historical backtest only found 3 trigger events in 6+ years,
too sparse to validate the guard. This starts accumulating real daily
observations instead. Never changes target weights, execution guards, or
the latest live signal.

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
from group_a_plus.integrations.add_0050_instead_shadow_log import (  # noqa: E402
    append_shadow_log_row,
    build_shadow_log_row,
)
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_add_0050_instead_of_00631l_shadow import (  # noqa: E402
    _load_narrow_lead_series,
    _targets_from_report,
)

DEFAULT_LOG_PATH = PROJECT_ROOT / "results" / "group_a_plus_add_0050_instead_shadow_log.jsonl"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "add_0050_instead_shadow.json"


def build_row(*, db_path: Path, panel: str | None, regime_lookback_days: int, end: str) -> dict:
    resolved_end = _resolve_end_date(db_path, end)
    regime_start = (date.fromisoformat(resolved_end) - timedelta(days=regime_lookback_days)).isoformat()
    report, frame = run_a2118(
        start=regime_start,
        end=resolved_end,
        initial_value=1_000_000.0,
        db=db_path,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
        ncf_panel_631l_path=panel,
    )
    target_weights = _targets_from_report(frame, report)
    narrow_lead = _load_narrow_lead_series(db_path, frame.index)
    return build_shadow_log_row(target_weights=target_weights, narrow_lead=narrow_lead)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel", default=None, help="ncf_00631l panel CSV path for today's execution_regime; omit for the panel-free historical regime.")
    parser.add_argument("--regime-lookback-days", type=int, default=90)
    parser.add_argument("--end", default="latest")
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_PATH))
    args = parser.parse_args()

    row = build_row(
        db_path=Path(args.db),
        panel=args.panel,
        regime_lookback_days=int(args.regime_lookback_days),
        end=args.end,
    )

    appended = append_shadow_log_row(row, Path(args.log))

    latest_path = Path(args.latest_output)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"status={row.get('status')} date={row.get('date')} would_trigger={row.get('would_trigger_add_0050_instead')} appended={appended}")
    print(f"Log: {args.log}")
    print(f"Latest: {latest_path}")


if __name__ == "__main__":
    main()
