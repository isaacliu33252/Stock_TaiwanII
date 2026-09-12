#!/usr/bin/env python3
"""Build a weekly shadow monitor for the 2606.09104 00631L 4% candidate.

The monitored candidate is fixed at 0050 30%, 00631L 4%, cash 66%, compared
with the guarded 0050 30%, cash 70% target. This is monitoring only and never
authorizes live weight changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_forward_shadow import (  # noqa: E402
    _future_es,
    _summary,
)
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    CORE_TICKERS,
    _build_state_frame,
    _future_compound,
    _future_mdd,
    _load_close,
    _portfolio_return,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_weekly_shadow_monitor.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_weekly_shadow_monitor/history"
GUARDED_WEIGHTS = {"0050.TW": 0.30, "cash": 0.70}
CANDIDATE_WEIGHTS = {"0050.TW": 0.30, "00631L.TW": 0.04, "cash": 0.66}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _weekly_state_dates(states: pd.DataFrame) -> list[pd.Timestamp]:
    if states.empty:
        return []
    frame = states.copy()
    frame["_week"] = frame.index.to_series().dt.to_period("W-FRI")
    return [pd.Timestamp(idx) for idx in frame.groupby("_week", sort=True).tail(1).index]


def _events(
    *,
    returns: pd.DataFrame,
    states: pd.DataFrame,
    horizon: int,
) -> list[dict[str, Any]]:
    guarded = _portfolio_return(returns, GUARDED_WEIGHTS)
    candidate = _portfolio_return(returns, CANDIDATE_WEIGHTS)
    rows: list[dict[str, Any]] = []
    for date in _weekly_state_dates(states):
        idx = returns.index.get_loc(date)
        g = _future_compound(guarded, idx, horizon)
        c = _future_compound(candidate, idx, horizon)
        gm = _future_mdd(guarded, idx, horizon)
        cm = _future_mdd(candidate, idx, horizon)
        ge = _future_es(guarded, idx, horizon)
        ce = _future_es(candidate, idx, horizon)
        if any(value is None for value in (g, c, gm, cm, ge, ce)):
            continue
        rows.append(
            {
                "date": str(date.date()),
                "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
                "risk_aversion_state": states.loc[date, "risk_aversion_state"],
                "guarded_20d_return": g,
                "micro_20d_return": c,
                "micro_minus_guarded_20d": c - g,
                "guarded_mdd_20d": gm,
                "micro_mdd_20d": cm,
                "guarded_es_20d": ge,
                "micro_es_20d": ce,
                "reasons": states.loc[date, "reasons"],
            }
        )
    return rows


def build_monitor(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    min_weekly_events: int = 20,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, CORE_TICKERS, start, str(end_resolved)).ffill(limit=3)
    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
    else:
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if len(returns) < lookback + horizon + 60:
        blockers.append("insufficient_history_for_weekly_monitor")

    rows: list[dict[str, Any]] = []
    latest_state: dict[str, Any] = {}
    state_counts: dict[str, int] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        rows = _events(returns=returns, states=states, horizon=horizon)
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
        if len(rows) < min_weekly_events:
            blockers.append("insufficient_weekly_shadow_events")

    events = pd.DataFrame(rows)
    high_events = events[events["risk_aversion_state"].isin(["HIGH", "EXTREME"])] if not events.empty else events
    all_summary = _summary(events)
    high_summary = _summary(high_events)
    latest_closed_event = rows[-1] if rows else {}
    if not blockers and (high_summary.get("mean_micro_minus_guarded_20d") or 0.0) <= 0.0:
        warnings.append("weekly_high_extreme_mean_value_non_positive")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_weekly_shadow_monitor",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "weekly_shadow_monitor_only_no_live_weight_change",
        "production_effect": "none",
        "status": "blocked" if blockers else "available_for_weekly_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "weekly_constrained_micro_add_shadow_monitor",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "sampling": "last_trading_day_each_W-FRI_week",
            "guarded_weights": GUARDED_WEIGHTS,
            "candidate_weights": CANDIDATE_WEIGHTS,
            "min_weekly_events": min_weekly_events,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "weekly_event_count": int(len(rows)),
            "state_counts": state_counts,
        },
        "latest_state": latest_state,
        "latest_closed_weekly_event": latest_closed_event,
        "weekly_all_state_summary": all_summary,
        "weekly_high_extreme_summary": high_summary,
        "weekly_events_tail": rows[-12:],
        "decision": {
            "candidate_id": "0050_30_00631l_4_cash_66",
            "keep_weekly_shadow_monitor": not bool(blockers),
            "allow_00631l_micro_add_from_monitor": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Weekly monitor tracks the 4pct 00631L candidate only; promotion requires a separate gate and reliable current holdings.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_monitor(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_weekly_shadow_monitor_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-weekly-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_monitor(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        min_weekly_events=args.min_weekly_events,
    )
    write_monitor(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
