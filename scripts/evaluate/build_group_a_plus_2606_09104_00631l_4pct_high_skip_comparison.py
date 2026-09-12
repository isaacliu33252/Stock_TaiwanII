#!/usr/bin/env python3
"""Compare all-state, skip-HIGH, and EXTREME-only 00631L 4% shadow policies."""

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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_high_skip_comparison.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_high_skip_comparison/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _policy_rows(
    *,
    returns: pd.DataFrame,
    states: pd.DataFrame,
    horizon: int,
    policy_name: str,
) -> list[dict[str, Any]]:
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    micro = _portfolio_return(returns, {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66})
    rows: list[dict[str, Any]] = []
    for idx, date in enumerate(states.index):
        state = states.loc[date, "risk_aversion_state"]
        if policy_name == "all_state_4pct":
            active = True
        elif policy_name == "skip_high_4pct":
            active = state != "HIGH"
        elif policy_name == "extreme_only_4pct":
            active = state == "EXTREME"
        else:
            raise ValueError(f"unknown policy: {policy_name}")
        g = _future_compound(guarded, idx, horizon)
        m = _future_compound(micro, idx, horizon)
        gm = _future_mdd(guarded, idx, horizon)
        mm = _future_mdd(micro, idx, horizon)
        ge = _future_es(guarded, idx, horizon)
        me = _future_es(micro, idx, horizon)
        if any(value is None for value in (g, m, gm, mm, ge, me)):
            continue
        p_ret = m if active else g
        p_mdd = mm if active else gm
        p_es = me if active else ge
        rows.append(
            {
                "date": str(pd.Timestamp(date).date()),
                "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
                "risk_aversion_state": state,
                "policy_active": active,
                "guarded_20d_return": g,
                "micro_20d_return": p_ret,
                "micro_minus_guarded_20d": p_ret - g,
                "guarded_mdd_20d": gm,
                "micro_mdd_20d": p_mdd,
                "guarded_es_20d": ge,
                "micro_es_20d": p_es,
                "reasons": states.loc[date, "reasons"],
            }
        )
    return rows


def _policy_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    active = frame[frame["policy_active"]] if not frame.empty else frame
    return {
        "all_event_summary": _summary(frame),
        "active_event_summary": _summary(active),
        "active_event_count": int(len(active)),
    }


def build_comparison(
    *,
    db_path: Path = DB_PATH,
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
        blockers.append("insufficient_history_for_high_skip_comparison")

    reviews: dict[str, dict[str, Any]] = {}
    latest_state: dict[str, Any] = {}
    state_counts: dict[str, int] = {}
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
        for policy in ("all_state_4pct", "skip_high_4pct", "extreme_only_4pct"):
            reviews[policy] = _policy_review(_policy_rows(returns=returns, states=states, horizon=horizon, policy_name=policy))
    def score(review: dict[str, Any]) -> tuple[float, float]:
        summary = review.get("all_event_summary", {})
        return (
            float(summary.get("mean_micro_minus_guarded_20d") or -999.0),
            float(summary.get("mean_es_extra_loss") or -999.0),
        )
    best_by_return = max(reviews, key=lambda name: score(reviews[name])[0], default=None) if reviews else None
    best_by_tail = max(reviews, key=lambda name: score(reviews[name])[1], default=None) if reviews else None
    skip = reviews.get("skip_high_4pct", {}).get("all_event_summary", {})
    all_state = reviews.get("all_state_4pct", {}).get("all_event_summary", {})
    skip_improves_tail = bool((skip.get("mean_es_extra_loss") or -999.0) > (all_state.get("mean_es_extra_loss") or 0.0))
    skip_reduces_return = bool((skip.get("mean_micro_minus_guarded_20d") or 0.0) < (all_state.get("mean_micro_minus_guarded_20d") or 0.0))
    if skip_reduces_return and not blockers:
        warnings.append("skip_high_reduces_mean_excess_return_vs_all_state")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_high_skip_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "fixed_shadow_policy_comparison_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "skip_high_vs_all_state_micro_add_comparison",
            "not_imported": ["live_weight_change", "auto_rebalance", "unconstrained_BLED_optimizer"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
            "guarded_weights": {"0050.TW": 0.3, "cash": 0.7},
        },
        "coverage": {"return_observations": int(len(returns)), "state_counts": state_counts},
        "latest_state": latest_state,
        "policy_reviews": reviews,
        "best_policy_by_mean_excess_return": best_by_return,
        "best_policy_by_tail_extra_es": best_by_tail,
        "decision": {
            "skip_high_improves_tail_vs_all_state": skip_improves_tail,
            "skip_high_reduces_return_vs_all_state": skip_reduces_return,
            "prefer_skip_high_for_tail_control": skip_improves_tail,
            "allow_00631l_micro_add_from_comparison": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Comparison is shadow-only; no policy can authorize live exposure without separate promotion gates.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_comparison(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_high_skip_comparison_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_comparison(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
    )
    write_comparison(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
