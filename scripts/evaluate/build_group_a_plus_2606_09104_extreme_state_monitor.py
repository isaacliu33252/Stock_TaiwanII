#!/usr/bin/env python3
"""Build the 2606.09104 EXTREME-state monitor for staged 00631L review."""

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
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    CORE_TICKERS,
    _build_state_frame,
    _load_close,
)
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_staged_ladder_readiness import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_LADDER_OUTPUT,
)
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_extreme_state_monitor.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_extreme_state_monitor/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _row_payload(date: pd.Timestamp, row: pd.Series) -> dict[str, Any]:
    return {
        "date": str(pd.Timestamp(date).date()),
        "risk_aversion_score": int(row["risk_aversion_score"]),
        "risk_aversion_state": str(row["risk_aversion_state"]),
        "reasons": list(row.get("reasons") or []),
    }


def _last_extreme_review(states: pd.DataFrame) -> dict[str, Any]:
    if states.empty:
        return {
            "last_extreme": None,
            "calendar_days_since_last_extreme": None,
            "trading_days_since_last_extreme": None,
            "last_extreme_run": None,
            "recent_extreme_tail": [],
        }
    latest_date = pd.Timestamp(states.index[-1])
    extreme = states[states["risk_aversion_state"] == "EXTREME"]
    if extreme.empty:
        return {
            "last_extreme": None,
            "calendar_days_since_last_extreme": None,
            "trading_days_since_last_extreme": None,
            "last_extreme_run": None,
            "recent_extreme_tail": [],
        }
    last_date = pd.Timestamp(extreme.index[-1])
    loc = int(states.index.get_loc(last_date))
    start_loc = loc
    while start_loc > 0 and states.iloc[start_loc - 1]["risk_aversion_state"] == "EXTREME":
        start_loc -= 1
    end_loc = loc
    while end_loc + 1 < len(states) and states.iloc[end_loc + 1]["risk_aversion_state"] == "EXTREME":
        end_loc += 1
    return {
        "last_extreme": _row_payload(last_date, states.loc[last_date]),
        "calendar_days_since_last_extreme": int((latest_date.date() - last_date.date()).days),
        "trading_days_since_last_extreme": int(len(states.loc[(states.index > last_date) & (states.index <= latest_date)])),
        "last_extreme_run": {
            "start_date": str(pd.Timestamp(states.index[start_loc]).date()),
            "end_date": str(pd.Timestamp(states.index[end_loc]).date()),
            "trading_days": int(end_loc - start_loc + 1),
        },
        "recent_extreme_tail": [
            _row_payload(pd.Timestamp(idx), row) for idx, row in extreme.tail(10).iterrows()
        ],
    }


def build_monitor(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    lookback: int = 252,
    ladder_path: Path = DEFAULT_LADDER_OUTPUT,
) -> dict[str, Any]:
    blockers: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        states = pd.DataFrame()
    else:
        close = _load_close(db_path, CORE_TICKERS, start, str(end_resolved)).ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([float("inf"), float("-inf")], pd.NA).dropna(how="all")
        states = _build_state_frame(returns, lookback=lookback) if not returns.empty else pd.DataFrame()
    if states.empty:
        blockers.append("risk_aversion_state_frame_missing")
    latest_state = _row_payload(pd.Timestamp(states.index[-1]), states.iloc[-1]) if not states.empty else {}
    extreme_review = _last_extreme_review(states)
    ladder = _load_json(_resolve(ladder_path))
    ladder_decision = ladder.get("decision") if isinstance(ladder.get("decision"), dict) else {}
    ladder_blockers = ladder.get("blocking_reasons") if isinstance(ladder.get("blocking_reasons"), list) else []
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_extreme_state_monitor",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "imported_concept": "extreme_state_monitor_for_staged_00631l_review",
        },
        "latest_state": latest_state,
        "extreme_history": extreme_review,
        "staged_ladder_status": {
            "report_available": bool(ladder),
            "status": ladder.get("status"),
            "any_stage_ready_if_extreme": ladder_decision.get("any_stage_ready_if_extreme"),
            "best_stage_cap_if_extreme": ladder_decision.get("best_stage_cap_if_extreme"),
            "latest_state_allows_stage": ladder_decision.get("latest_state_allows_stage"),
            "blocking_reasons": ladder_blockers,
        },
        "decision": {
            "extreme_active_today": latest_state.get("risk_aversion_state") == "EXTREME",
            "review_staged_00631l_today": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "summary": "Monitor only: staged 00631L review requires EXTREME plus separate manual approval.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_monitor(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_extreme_state_monitor_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--ladder", default=str(DEFAULT_LADDER_OUTPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_monitor(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        lookback=args.lookback,
        ladder_path=_resolve(args.ladder),
    )
    write_monitor(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
