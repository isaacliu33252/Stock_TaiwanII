#!/usr/bin/env python3
"""Build a 2606.09104 00631L 5% micro-add forward shadow for GroupA+.

Compare guarded 0050/cash with a fixed capped 00631L micro-add candidate over
future 20-day windows, especially during transparent HIGH/EXTREME risk-aversion
states. This is shadow-only and cannot authorize trades.
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
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    CORE_TICKERS,
    _build_state_frame,
    _float,
    _future_compound,
    _future_mdd,
    _load_close,
    _portfolio_return,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_micro_add_forward_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_micro_add_forward_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _future_es(port: pd.Series, idx: int, horizon: int) -> float | None:
    future = port.iloc[idx + 1 : idx + 1 + horizon]
    if len(future) < horizon:
        return None
    var = float(future.quantile(0.05))
    return float(future[future <= var].mean())


def _summary(events: pd.DataFrame) -> dict[str, Any]:
    if events.empty:
        return {
            "event_count": 0,
            "mean_micro_minus_guarded_20d": None,
            "hit_rate_micro_beats_guarded": None,
            "mean_micro_mdd_20d": None,
            "mean_guarded_mdd_20d": None,
            "mean_mdd_extra_loss": None,
            "mean_micro_es_20d": None,
            "mean_guarded_es_20d": None,
            "mean_es_extra_loss": None,
        }
    return {
        "event_count": int(len(events)),
        "mean_micro_minus_guarded_20d": _float(events["micro_minus_guarded_20d"].mean()),
        "hit_rate_micro_beats_guarded": _float(float((events["micro_minus_guarded_20d"] > 0).mean())),
        "mean_micro_20d_return": _float(events["micro_20d_return"].mean()),
        "mean_guarded_20d_return": _float(events["guarded_20d_return"].mean()),
        "mean_micro_mdd_20d": _float(events["micro_mdd_20d"].mean()),
        "mean_guarded_mdd_20d": _float(events["guarded_mdd_20d"].mean()),
        "mean_mdd_extra_loss": _float((events["micro_mdd_20d"] - events["guarded_mdd_20d"]).mean()),
        "mean_micro_es_20d": _float(events["micro_es_20d"].mean()),
        "mean_guarded_es_20d": _float(events["guarded_es_20d"].mean()),
        "mean_es_extra_loss": _float((events["micro_es_20d"] - events["guarded_es_20d"]).mean()),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    min_events: int = 20,
    max_mdd_extra_loss: float = -0.01,
    max_es_extra_loss: float = -0.0025,
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
        blockers.append("insufficient_history_for_micro_add_forward_shadow")

    all_rows: list[dict[str, Any]] = []
    high_rows: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    latest_state: dict[str, Any] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
        micro = _portfolio_return(returns, {"0050.TW": 0.3, "00631L.TW": 0.05, "cash": 0.65})
        for idx, date in enumerate(states.index):
            g = _future_compound(guarded, idx, horizon)
            m = _future_compound(micro, idx, horizon)
            gm = _future_mdd(guarded, idx, horizon)
            mm = _future_mdd(micro, idx, horizon)
            ge = _future_es(guarded, idx, horizon)
            me = _future_es(micro, idx, horizon)
            if any(value is None for value in (g, m, gm, mm, ge, me)):
                continue
            row = {
                "date": str(pd.Timestamp(date).date()),
                "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
                "risk_aversion_state": states.loc[date, "risk_aversion_state"],
                "guarded_20d_return": g,
                "micro_20d_return": m,
                "micro_minus_guarded_20d": m - g,
                "guarded_mdd_20d": gm,
                "micro_mdd_20d": mm,
                "guarded_es_20d": ge,
                "micro_es_20d": me,
                "reasons": states.loc[date, "reasons"],
            }
            all_rows.append(row)
            if row["risk_aversion_state"] in {"HIGH", "EXTREME"}:
                high_rows.append(row)
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }

    all_summary = _summary(pd.DataFrame(all_rows))
    high_summary = _summary(pd.DataFrame(high_rows))
    if high_summary["event_count"] < min_events and not blockers:
        blockers.append("insufficient_high_extreme_micro_add_events")
    high_has_value = bool(
        not blockers
        and (high_summary.get("mean_micro_minus_guarded_20d") or 0.0) > 0
        and (high_summary.get("hit_rate_micro_beats_guarded") or 0.0) >= 0.55
        and (high_summary.get("mean_mdd_extra_loss") or 0.0) >= max_mdd_extra_loss
        and (high_summary.get("mean_es_extra_loss") or 0.0) >= max_es_extra_loss
    )
    all_has_value = bool(
        not blockers
        and (all_summary.get("mean_micro_minus_guarded_20d") or 0.0) > 0
        and (all_summary.get("hit_rate_micro_beats_guarded") or 0.0) >= 0.55
    )
    if not high_has_value and not blockers:
        warnings.append("micro_add_high_extreme_forward_value_not_promotable")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_micro_add_forward_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "constrained_micro_add_candidate_forward_validation",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "min_events": min_events,
            "guarded_weights": {"0050.TW": 0.3, "cash": 0.7},
            "micro_add_weights": {"0050.TW": 0.3, "00631L.TW": 0.05, "cash": 0.65},
            "max_mdd_extra_loss": max_mdd_extra_loss,
            "max_es_extra_loss": max_es_extra_loss,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "state_counts": state_counts,
        },
        "latest_state": latest_state,
        "all_state_event_summary": all_summary,
        "high_extreme_event_summary": high_summary,
        "sample_high_extreme_events_tail": high_rows[-10:],
        "decision": {
            "micro_add_has_all_state_forward_value": all_has_value,
            "micro_add_has_high_extreme_forward_value": high_has_value,
            "allow_00631l_micro_add_from_this_shadow": False,
            "advance_to_promotion_gate": high_has_value,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "00631L 5pct micro-add is forward-tested as a fixed shadow candidate only; it cannot authorize trades.",
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
    (history_dir / f"2606_09104_00631l_micro_add_forward_shadow_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--min-events", type=int, default=20)
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
        min_events=args.min_events,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
