#!/usr/bin/env python3
"""Append today's trough+compounding override eligibility to a live shadow log.

Research-only, pure logging step -- see
group_a_plus/integrations/trough_override_eligibility_shadow.py for why this
exists. Recomputes a short recent a2118 window (default 90 calendar days)
ending "latest" so the eligibility check runs on the same simulate_override_policy
logic the historical backtest used, then logs whether today qualifies.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py.
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

from backtest_group_a_plus_policy_signal import TICKERS  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices  # noqa: E402
from group_a_plus.integrations.trough_override_eligibility_shadow import (  # noqa: E402
    append_shadow_log_row,
    build_shadow_log_row,
)
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment import COMMON_A2118_KW  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_shadow import build_trough_state_frame  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow import (  # noqa: E402
    _build_compounding_regime_series,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame  # noqa: E402

DEFAULT_LOG_PATH = PROJECT_ROOT / "results" / "group_a_plus_trough_override_eligibility_shadow_log.jsonl"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "trough_override_eligibility_shadow.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel", default=None, help="ncf_00631l panel CSV path; omit for panel-free regime.")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_PATH))
    args = parser.parse_args()

    db_path = Path(args.db)
    end = date.fromisoformat(args.end)
    resolved_end = _resolve_end_date(db_path, "latest")
    start = (end - timedelta(days=int(args.lookback_days))).isoformat()

    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=1_000_000.0,
        db=db_path,
        ncf_panel_631l_path=args.panel,
        **COMMON_A2118_KW,
    )
    prices = _load_prices(db_path, list(TICKERS), start, resolved_end).reindex(frame.index)
    chip = _load_chip_features(db_path, prices.index, start, resolved_end)
    gate_frame = _build_volatility_gate_frame(prices, chip).reindex(frame.index)
    trough_state = build_trough_state_frame(db_path=db_path, strategy_frame=frame)
    compounding_regime = _build_compounding_regime_series(prices)

    row = build_shadow_log_row(
        prices=prices,
        frame=frame,
        trough_state=trough_state,
        gate_frame=gate_frame,
        compounding_regime=compounding_regime,
        report=report,
    )

    appended = append_shadow_log_row(row, Path(args.log))

    latest_path = Path(args.latest_output)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"status={row.get('status')} date={row.get('date')} eligible={row.get('eligible')} appended={appended}")
    print(f"Log: {args.log}")
    print(f"Latest: {latest_path}")


if __name__ == "__main__":
    main()
