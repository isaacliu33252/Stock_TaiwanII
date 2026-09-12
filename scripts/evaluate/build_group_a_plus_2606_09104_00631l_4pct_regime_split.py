#!/usr/bin/env python3
"""Build regime-split diagnostics for the 2606.09104 00631L 4% candidate."""

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
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    _load_json,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_regime_split.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_regime_split/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _events(returns: pd.DataFrame, states: pd.DataFrame, *, horizon: int) -> list[dict[str, Any]]:
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    candidate = _portfolio_return(returns, {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66})
    rows: list[dict[str, Any]] = []
    for idx, date in enumerate(states.index):
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
                "date": str(pd.Timestamp(date).date()),
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


def _split_by_state(events: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        state: _summary(events[events["risk_aversion_state"] == state] if not events.empty else events)
        for state in ("LOW", "MEDIUM", "HIGH", "EXTREME")
    }


def _split_by_reason(events: pd.DataFrame, reasons: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for reason in reasons:
        if events.empty:
            subset = events
        else:
            subset = events[events["reasons"].apply(lambda raw: reason in raw if isinstance(raw, list) else False)]
        out[reason] = _summary(subset)
    return out


def build_split(
    *,
    db_path: Path = DB_PATH,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
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
        blockers.append("insufficient_history_for_regime_split")

    rows: list[dict[str, Any]] = []
    latest_state: dict[str, Any] = {}
    state_counts: dict[str, int] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        rows = _events(returns, states, horizon=horizon)
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
    events = pd.DataFrame(rows)
    state_split = _split_by_state(events)
    reason_split = _split_by_reason(
        events,
        (
            "0050_vol20_percentile_ge_85",
            "0050_drawdown63_le_minus_5pct",
            "0050_drawdown63_le_minus_8pct",
            "raw_target_tail_es95_at_least_3x_guarded",
            "defensive_diversification_failed",
        ),
    )
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    latest_context = {
        "strategy_id": live_signal.get("strategy_id"),
        "execution_regime": live_signal.get("execution_regime"),
        "market_state": live_signal.get("market_state"),
    }
    high = state_split.get("HIGH", {})
    extreme = state_split.get("EXTREME", {})
    high_extreme_value = bool(
        ((high.get("mean_micro_minus_guarded_20d") or 0.0) > 0 or (extreme.get("mean_micro_minus_guarded_20d") or 0.0) > 0)
        and ((high.get("hit_rate_micro_beats_guarded") or 0.0) >= 0.55 or (extreme.get("hit_rate_micro_beats_guarded") or 0.0) >= 0.55)
    )
    if not high_extreme_value and not blockers:
        warnings.append("no_clear_high_extreme_regime_value")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_regime_split",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "regime_split_shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "state_dependent_micro_add_review",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "guarded_weights": {"0050.TW": 0.3, "cash": 0.7},
            "candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
        },
        "coverage": {"return_observations": int(len(returns)), "event_count": int(len(rows)), "state_counts": state_counts},
        "latest_state": latest_state,
        "latest_a2118_context": latest_context,
        "state_split_summary": state_split,
        "reason_split_summary": reason_split,
        "events_tail": rows[-10:],
        "decision": {
            "high_extreme_regime_value_observed": high_extreme_value,
            "allow_00631l_micro_add_from_split": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Regime split diagnoses where the 4pct candidate works; it does not authorize live exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_split(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_regime_split_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_split(
        db_path=_resolve(args.db_path),
        forward_monitor_path=_resolve(args.forward_monitor),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
    )
    write_split(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
