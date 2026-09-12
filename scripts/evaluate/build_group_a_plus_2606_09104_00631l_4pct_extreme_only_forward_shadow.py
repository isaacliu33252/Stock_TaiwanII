#!/usr/bin/env python3
"""Build an EXTREME-only forward shadow for the 2606.09104 00631L 4% candidate.

At decision date t, this shadow policy uses 0050 30% / 00631L 4% / cash 66%
only when the transparent risk-aversion state is EXTREME. All other states use
the guarded 0050 30% / cash 70% target. It never changes live weights.
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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_extreme_only_forward_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_extreme_only_forward_shadow/history"


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


def _events(
    *,
    returns: pd.DataFrame,
    states: pd.DataFrame,
    horizon: int,
) -> list[dict[str, Any]]:
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    micro = _portfolio_return(returns, {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66})
    rows: list[dict[str, Any]] = []
    for idx, date in enumerate(states.index):
        g = _future_compound(guarded, idx, horizon)
        m = _future_compound(micro, idx, horizon)
        gm = _future_mdd(guarded, idx, horizon)
        mm = _future_mdd(micro, idx, horizon)
        ge = _future_es(guarded, idx, horizon)
        me = _future_es(micro, idx, horizon)
        if any(value is None for value in (g, m, gm, mm, ge, me)):
            continue
        state = states.loc[date, "risk_aversion_state"]
        active = state == "EXTREME"
        shadow_return = m if active else g
        shadow_mdd = mm if active else gm
        shadow_es = me if active else ge
        rows.append(
            {
                "date": str(pd.Timestamp(date).date()),
                "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
                "risk_aversion_state": state,
                "extreme_only_active": active,
                "guarded_20d_return": g,
                "micro_20d_return": shadow_return,
                "micro_minus_guarded_20d": shadow_return - g,
                "guarded_mdd_20d": gm,
                "micro_mdd_20d": shadow_mdd,
                "guarded_es_20d": ge,
                "micro_es_20d": shadow_es,
                "reasons": states.loc[date, "reasons"],
                "all_state_4pct_20d_return": m,
                "all_state_4pct_minus_guarded_20d": m - g,
            }
        )
    return rows


def _compare_all_state(events: pd.DataFrame) -> dict[str, Any]:
    if events.empty:
        return {
            "event_count": 0,
            "mean_all_state_4pct_minus_guarded_20d": None,
            "hit_rate_all_state_4pct_beats_guarded": None,
        }
    return {
        "event_count": int(len(events)),
        "mean_all_state_4pct_minus_guarded_20d": _float(events["all_state_4pct_minus_guarded_20d"].mean()),
        "hit_rate_all_state_4pct_beats_guarded": _float(float((events["all_state_4pct_minus_guarded_20d"] > 0).mean())),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    min_extreme_events: int = 50,
    max_extreme_es_extra_loss: float = -0.0025,
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
        blockers.append("insufficient_history_for_extreme_only_forward_shadow")

    rows: list[dict[str, Any]] = []
    latest_state: dict[str, Any] = {}
    state_counts: dict[str, int] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        rows = _events(returns=returns, states=states, horizon=horizon)
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
    events = pd.DataFrame(rows)
    active_events = events[events["extreme_only_active"]] if not events.empty else events
    all_summary = _summary(events)
    active_summary = _summary(active_events)
    all_state_compare = _compare_all_state(events)
    if active_summary.get("event_count", 0) < min_extreme_events and not blockers:
        blockers.append("insufficient_extreme_events")
    extreme_only_has_value = bool(
        not blockers
        and (active_summary.get("mean_micro_minus_guarded_20d") or 0.0) > 0.0
        and (active_summary.get("hit_rate_micro_beats_guarded") or 0.0) >= 0.55
        and (active_summary.get("mean_es_extra_loss") or -999.0) >= max_extreme_es_extra_loss
    )
    if not extreme_only_has_value and not blockers:
        warnings.append("extreme_only_shadow_value_not_promotable")
    latest_active = latest_state.get("risk_aversion_state") == "EXTREME"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "extreme_only_forward_shadow_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "extreme_only_micro_add_shadow_policy",
            "not_imported": ["live_weight_change", "auto_rebalance", "unconstrained_BLED_optimizer"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "guarded_weights": {"0050.TW": 0.3, "cash": 0.7},
            "extreme_only_candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
            "activation_rule": "decision_date_risk_aversion_state == EXTREME",
            "min_extreme_events": min_extreme_events,
            "max_extreme_es_extra_loss": max_extreme_es_extra_loss,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "event_count": int(len(rows)),
            "active_extreme_event_count": int(len(active_events)),
            "state_counts": state_counts,
        },
        "latest_state": latest_state,
        "latest_candidate_active": latest_active,
        "extreme_only_all_event_summary": all_summary,
        "extreme_only_active_event_summary": active_summary,
        "all_state_4pct_reference_summary": all_state_compare,
        "active_events_tail": rows[-10:],
        "decision": {
            "extreme_only_has_historical_value": extreme_only_has_value,
            "candidate_active_today": latest_active,
            "allow_00631l_micro_add_from_extreme_only_shadow": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "EXTREME-only 4pct micro-add is a shadow policy only; it cannot authorize live exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_extreme_only_forward_shadow_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--min-extreme-events", type=int, default=50)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        min_extreme_events=args.min_extreme_events,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
