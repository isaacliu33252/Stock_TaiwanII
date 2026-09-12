#!/usr/bin/env python3
"""Build a constrained 2606.09104 BLED allocation review for GroupA+.

This is not an optimizer. It scores fixed A21.18-compatible candidate targets
with historical mean return and Student-t adjusted ES95. It forbids shorting and
large simultaneous leveraged/inverse offsets, and never changes live weights.
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
from scripts.evaluate.build_group_a_plus_2606_09104_bled_tail_adjustment_review import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    DEFAULT_LIVE_SNAPSHOT,
    DEFAULT_TICKERS,
    _load_close,
    _load_json,
    _portfolio_returns,
    _tail_factor,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_constrained_bled_allocation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_constrained_bled_allocation_review/history"


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


def _weights(payload: Any) -> dict[str, float]:
    src = payload if isinstance(payload, dict) else {}
    return {key: float(src.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]}


def _candidate_targets(live_snapshot: dict[str, Any], forward_monitor: dict[str, Any]) -> list[dict[str, Any]]:
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    current = _weights(portfolio.get("weights"))
    if "cash_weight" in portfolio:
        current["cash"] = float(portfolio.get("cash_weight") or 0.0)
    guarded = _weights(live_signal.get("target_weights"))
    raw = _weights(live_snapshot.get("target_weights_for_action"))
    candidates = [
        {"target_name": "current_live_weights", "weights": current, "constraint": "observed_current"},
        {"target_name": "guarded_live_target", "weights": guarded, "constraint": "a2118_guarded"},
        {"target_name": "raw_a2118_seed_ensemble_target", "weights": raw, "constraint": "raw_review_only"},
        {"target_name": "candidate_0050_only_100", "weights": _weights({"0050.TW": 1.0}), "constraint": "no_00631l"},
        {
            "target_name": "candidate_00631l_cap_5pct",
            "weights": _weights({"0050.TW": 0.70, "00631L.TW": 0.05, "cash": 0.25}),
            "constraint": "00631l_capped_5pct",
        },
        {
            "target_name": "candidate_guarded_plus_00631l_5pct",
            "weights": _weights({"0050.TW": 0.30, "00631L.TW": 0.05, "cash": 0.65}),
            "constraint": "00631l_capped_5pct",
        },
    ]
    return [row for row in candidates if sum(abs(v) for v in row["weights"].values()) > 0]


def _review_candidate(name: str, weights: dict[str, float], constraint: str, returns: pd.DataFrame) -> dict[str, Any]:
    port = _portfolio_returns(returns, weights)
    var95 = float(port.quantile(0.05))
    es95 = float(port[port <= var95].mean())
    mean = float(port.mean())
    ann_return = float((1.0 + mean) ** 252 - 1.0)
    ann_vol = float(port.std(ddof=0) * np.sqrt(252.0))
    starr = ann_return / abs(es95 * 252.0) if es95 < 0 else np.nan
    # BL-lite review score: reward return, penalize downside tail and risky gross.
    gross_risky = sum(abs(float(weights.get(t, 0.0) or 0.0)) for t in DEFAULT_TICKERS)
    score = ann_return - 6.0 * abs(es95) - 0.03 * gross_risky
    blocked: list[str] = []
    if float(weights.get("00631L.TW", 0.0) or 0.0) > 0.05 and constraint != "raw_review_only":
        blocked.append("00631l_above_5pct_cap")
    if float(weights.get("00631L.TW", 0.0) or 0.0) > 0 and float(weights.get("00632R.TW", 0.0) or 0.0) > 0:
        blocked.append("simultaneous_00631l_00632r_forbidden")
    if any(float(v) < -1e-12 for v in weights.values()):
        blocked.append("short_weight_forbidden")
    return {
        "target_name": name,
        "constraint": constraint,
        "weights": weights,
        "gross_risky_weight": _float(gross_risky),
        "annualized_return": _float(ann_return),
        "annualized_vol": _float(ann_vol),
        "daily_var95": _float(var95),
        "daily_es95": _float(es95),
        "starr_like": _float(starr),
        "constrained_bled_lite_score": _float(score),
        "blocked_by_constraints": bool(blocked),
        "blocking_reasons": blocked,
    }


def build_review(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    lookback_days: int = 756,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, DEFAULT_TICKERS, start, str(end_resolved)).ffill(limit=3)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).tail(lookback_days) if not close.empty else pd.DataFrame()
    if returns.empty:
        blockers.append("price_panel_missing")
    if len(returns) < 252:
        blockers.append("insufficient_review_history")
    candidates = _candidate_targets(live_snapshot, forward_monitor)
    if not candidates:
        blockers.append("candidate_targets_missing")
    reviews: list[dict[str, Any]] = []
    tail_factors: dict[str, Any] = {}
    if not blockers:
        tail_factors = {ticker: _tail_factor(returns[ticker]) for ticker in DEFAULT_TICKERS}
        reviews = [
            _review_candidate(row["target_name"], row["weights"], row["constraint"], returns)
            for row in candidates
        ]
    eligible = [row for row in reviews if not row["blocked_by_constraints"]]
    best = max(eligible, key=lambda row: float(row["constrained_bled_lite_score"] or -999.0), default=None)
    guarded = next((row for row in reviews if row["target_name"] == "guarded_live_target"), None)
    best_is_guarded = bool(best and guarded and best["target_name"] == guarded["target_name"])
    if best and best["target_name"] != "guarded_live_target":
        warnings.append("best_constrained_candidate_is_not_guarded_target_review_only")
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_constrained_bled_allocation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_fixed_candidates_no_optimizer_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "constrained_elliptical_black_litterman_candidate_review",
            "not_imported": ["unconstrained_BL_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "guardrails": {
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "short_selling_allowed": False,
            "max_00631l_candidate_weight": 0.05,
            "forbid_simultaneous_00631l_00632r_offset": True,
        },
        "parameters": {"start": start, "end": str(end_resolved), "lookback_days": lookback_days},
        "latest_a2118_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "target_weights": live_signal.get("target_weights"),
            "market_state": live_signal.get("market_state"),
        },
        "asset_tail_factors": tail_factors,
        "candidate_reviews": sorted(
            reviews,
            key=lambda row: float(row["constrained_bled_lite_score"] or -999.0),
            reverse=True,
        ),
        "best_eligible_candidate": best,
        "decision": {
            "best_candidate_is_guarded_target": best_is_guarded,
            "promote_constrained_candidate_to_live": False,
            "allow_00631l_add_from_this_review": False,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Fixed constrained candidate review only; no candidate can change live weights without separate promotion gates.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_review(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_constrained_bled_allocation_review_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--lookback-days", type=int, default=756)
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_review(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        lookback_days=args.lookback_days,
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
    )
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
