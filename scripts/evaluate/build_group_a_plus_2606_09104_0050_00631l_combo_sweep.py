#!/usr/bin/env python3
"""Build a constrained 0050/00631L/cash combo sweep for 2606.09104 review.

This is a fixed candidate grid, not an optimizer. It tests whether small
00631L exposure is still useful when the 0050 base weight is also varied.
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
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import (  # noqa: E402
    _passes,
)
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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_0050_00631l_combo_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_0050_00631l_combo_sweep/history"
DEFAULT_0050_WEIGHTS = (0.25, 0.30, 0.35, 0.40)
DEFAULT_00631L_WEIGHTS = (0.025, 0.03, 0.04, 0.05)


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


def _candidate_events(
    *,
    returns: pd.DataFrame,
    states: pd.DataFrame,
    w_0050: float,
    w_00631l: float,
    horizon: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    combo = _portfolio_return(returns, {"0050.TW": w_0050, "00631L.TW": w_00631l, "cash": 1.0 - w_0050 - w_00631l})
    all_rows: list[dict[str, Any]] = []
    high_rows: list[dict[str, Any]] = []
    for idx, date in enumerate(states.index):
        g = _future_compound(guarded, idx, horizon)
        c = _future_compound(combo, idx, horizon)
        gm = _future_mdd(guarded, idx, horizon)
        cm = _future_mdd(combo, idx, horizon)
        ge = _future_es(guarded, idx, horizon)
        ce = _future_es(combo, idx, horizon)
        if any(value is None for value in (g, c, gm, cm, ge, ce)):
            continue
        row = {
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
        all_rows.append(row)
        if row["risk_aversion_state"] in {"HIGH", "EXTREME"}:
            high_rows.append(row)
    return all_rows, high_rows


def build_sweep(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    weights_0050: tuple[float, ...] = DEFAULT_0050_WEIGHTS,
    weights_00631l: tuple[float, ...] = DEFAULT_00631L_WEIGHTS,
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
        blockers.append("insufficient_history_for_combo_sweep")

    reviews: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    latest_state: dict[str, Any] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
        for w_0050 in weights_0050:
            for w_00631l in weights_00631l:
                cash = 1.0 - w_0050 - w_00631l
                if cash < 0.0:
                    continue
                all_rows, high_rows = _candidate_events(
                    returns=returns,
                    states=states,
                    w_0050=w_0050,
                    w_00631l=w_00631l,
                    horizon=horizon,
                )
                all_summary = _summary(pd.DataFrame(all_rows))
                high_summary = _summary(pd.DataFrame(high_rows))
                all_pass = _passes(
                    all_summary,
                    max_mdd_extra_loss=max_mdd_extra_loss,
                    max_es_extra_loss=max_es_extra_loss,
                    min_events=min_events,
                )
                high_pass = _passes(
                    high_summary,
                    max_mdd_extra_loss=max_mdd_extra_loss,
                    max_es_extra_loss=max_es_extra_loss,
                    min_events=min_events,
                )
                reviews.append(
                    {
                        "weights": {
                            "0050.TW": _float(w_0050, 4),
                            "00631L.TW": _float(w_00631l, 4),
                            "cash": _float(cash, 4),
                        },
                        "all_state_summary": all_summary,
                        "high_extreme_summary": high_summary,
                        "passes_all_state_gate": all_pass,
                        "passes_high_extreme_gate": high_pass,
                    }
                )
    passing_high = [row for row in reviews if row["passes_high_extreme_gate"]]
    best_passing = max(
        passing_high,
        key=lambda row: float(row["high_extreme_summary"].get("mean_micro_minus_guarded_20d") or -999.0),
        default=None,
    )
    if not best_passing and not blockers:
        warnings.append("no_combo_passes_high_extreme_gate")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_0050_00631l_combo_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "fixed_candidate_grid_shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "constrained_0050_00631l_cash_combo_sweep",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "weights_0050": list(weights_0050),
            "weights_00631l": list(weights_00631l),
            "min_events": min_events,
            "max_mdd_extra_loss": max_mdd_extra_loss,
            "max_es_extra_loss": max_es_extra_loss,
        },
        "coverage": {"return_observations": int(len(returns)), "state_counts": state_counts},
        "latest_state": latest_state,
        "combo_reviews": reviews,
        "best_passing_high_extreme_combo": best_passing,
        "decision": {
            "any_combo_passes_high_extreme_gate": bool(best_passing),
            "best_combo_for_promotion_review": best_passing.get("weights") if best_passing else None,
            "allow_combo_from_this_sweep": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Fixed combo sweep only; passing a shadow gate still requires separate promotion approval.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_sweep(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_0050_00631l_combo_sweep_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--weights-0050", default="0.25,0.30,0.35,0.40")
    parser.add_argument("--weights-00631l", default="0.025,0.03,0.04,0.05")
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_sweep(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        weights_0050=tuple(float(item.strip()) for item in args.weights_0050.split(",") if item.strip()),
        weights_00631l=tuple(float(item.strip()) for item in args.weights_00631l.split(",") if item.strip()),
        min_events=args.min_events,
    )
    write_sweep(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
