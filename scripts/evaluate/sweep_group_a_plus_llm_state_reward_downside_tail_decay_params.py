#!/usr/bin/env python3
"""Sweep v2 GIFT downside/tail reward parameters.

This is a proxy diagnostic sweep only. It does not train PPO, output actions,
target weights, or live rebalance decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_diagnostic_refinement import (  # noqa: E402
    _alignment_grade,
    _downside_alignment_semantic,
    _mean,
    _safe_corr,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
    DEFAULT_DB,
    _feature_frame,
    _load_ohlcv_from_db,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_downside_tail_decay_param_sweep.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_downside_tail_decay_param_sweep/history"
DEFAULT_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _score_frame(frame: pd.DataFrame, *, forward_horizon: int, min_rows: int) -> dict[str, Any]:
    close = pd.to_numeric(frame["close"], errors="coerce")
    future_return = close.shift(-forward_horizon) / close - 1.0
    future_downside = future_return.clip(upper=0.0).abs()
    reward = pd.to_numeric(frame["reward_proxy"], errors="coerce")
    finite_reward = reward.replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "return_alignment": _safe_corr(reward, future_return, min_rows=min_rows),
        "downside_alignment": _safe_corr(reward, future_downside, min_rows=min_rows),
        "reward_snr": _finite(abs(finite_reward.mean()) / finite_reward.std(ddof=0))
        if len(finite_reward) and finite_reward.std(ddof=0) > 0
        else None,
        "finite_reward_ratio": float(len(finite_reward) / len(frame)) if len(frame) else 0.0,
    }


def _score_params(
    frames: dict[str, pd.DataFrame],
    *,
    drawdown_weight: float,
    volatility_weight: float,
    tail_decay_weight: float,
    volatility_scale: float,
    tail_decay_scale: float,
    forward_horizon: int,
    min_rows: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for ticker, df in frames.items():
        frame = _feature_frame(
            df,
            proposal_id=DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
            downside_drawdown_weight=drawdown_weight,
            downside_volatility_weight=volatility_weight,
            downside_tail_decay_weight=tail_decay_weight,
            volatility_penalty_scale=volatility_scale,
            tail_decay_scale=tail_decay_scale,
        )
        score = _score_frame(frame, forward_horizon=forward_horizon, min_rows=min_rows)
        rows.append({"ticker": ticker, **score})

    return_alignment = _mean([row["return_alignment"] for row in rows])
    downside_alignment = _mean([row["downside_alignment"] for row in rows])
    reward_snr = _mean([row["reward_snr"] for row in rows])
    finite_reward_min_ratio = min((row["finite_reward_ratio"] for row in rows), default=None)
    downside_gate = _alignment_grade(
        downside_alignment,
        unavailable_reason="reward_future_downside_alignment_unavailable",
    )
    downside_semantic = _downside_alignment_semantic(downside_alignment)
    queue_allowed = downside_gate["grade"] == "green" and downside_semantic["risk_sensitive_useful"]
    return {
        "params": {
            "drawdown_weight": drawdown_weight,
            "volatility_weight": volatility_weight,
            "tail_decay_weight": tail_decay_weight,
            "volatility_scale": volatility_scale,
            "tail_decay_scale": tail_decay_scale,
        },
        "ticker_scores": rows,
        "mean_return_alignment": return_alignment,
        "mean_downside_alignment": downside_alignment,
        "mean_reward_snr": reward_snr,
        "finite_reward_min_ratio": finite_reward_min_ratio,
        "downside_grade": downside_gate["grade"],
        "downside_abs_alignment": downside_gate["abs_alignment"],
        "downside_direction": downside_semantic["direction"],
        "risk_sensitive_useful": downside_semantic["risk_sensitive_useful"],
        "ppo_training_queue_candidate": queue_allowed,
        "rank_score": (
            (downside_gate["abs_alignment"] or 0.0)
            + 0.01 * (reward_snr or 0.0)
            - (0.10 if not queue_allowed else 0.0)
        ),
    }


def build_review(
    *,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    start: str = "2016-01-01",
    forward_horizon: int = 5,
    min_rows: int = 120,
    drawdown_weights: list[float] | None = None,
    volatility_weights: list[float] | None = None,
    tail_decay_weights: list[float] | None = None,
    volatility_scales: list[float] | None = None,
    tail_decay_scales: list[float] | None = None,
    top_n: int = 15,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    selected_tickers = tickers or list(DEFAULT_TICKERS)
    blockers: list[str] = []
    if not db_path.exists():
        blockers.append("missing_duckdb")
    frames = {
        ticker: _load_ohlcv_from_db(db_path, ticker=ticker, start=start)
        for ticker in selected_tickers
    } if db_path.exists() else {}
    missing = [ticker for ticker, frame in frames.items() if frame.empty]
    if missing:
        blockers.append(f"missing_ohlcv_data:{','.join(missing)}")
    frames = {ticker: frame for ticker, frame in frames.items() if not frame.empty}

    grid = list(
        product(
            drawdown_weights or [0.3, 0.5, 0.7],
            volatility_weights or [0.1, 0.3, 0.5],
            tail_decay_weights or [0.1, 0.2, 0.4],
            volatility_scales or [2.0, 3.0, 4.0],
            tail_decay_scales or [4.0, 6.0, 8.0],
        )
    )
    rows = [
        _score_params(
            frames,
            drawdown_weight=dw,
            volatility_weight=vw,
            tail_decay_weight=tw,
            volatility_scale=vs,
            tail_decay_scale=ts,
            forward_horizon=forward_horizon,
            min_rows=min_rows,
        )
        for dw, vw, tw, vs, ts in grid
    ] if not blockers else []
    ranked = sorted(rows, key=lambda row: row["rank_score"], reverse=True)
    green = [row for row in ranked if row["ppo_training_queue_candidate"]]
    best = ranked[0] if ranked else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_downside_tail_decay_param_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "parameter_sweep_only_no_model_training_no_live_action",
        "inputs": {
            "db": str(db_path),
            "tickers": selected_tickers,
            "start": start,
            "forward_horizon": forward_horizon,
            "min_rows": min_rows,
            "proposal_id": DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
            "grid_size": len(grid),
        },
        "summary": {
            "evaluated_count": len(rows),
            "green_candidate_count": len(green),
            "best_params": best["params"] if best else None,
            "best_downside_alignment": best["mean_downside_alignment"] if best else None,
            "best_downside_grade": best["downside_grade"] if best else None,
            "best_reward_snr": best["mean_reward_snr"] if best else None,
            "best_rank_score": best["rank_score"] if best else None,
        },
        "top_candidates": ranked[:top_n],
        "blocking_reasons": blockers,
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "best_candidate_for_next_offline_experiment": bool(best and best["ppo_training_queue_candidate"]),
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_downside_tail_decay_param_sweep_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--forward-horizon", type=int, default=5)
    parser.add_argument("--min-rows", type=int, default=120)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        start=args.start,
        forward_horizon=args.forward_horizon,
        min_rows=args.min_rows,
        top_n=args.top_n,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward downside/tail param sweep: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "evaluated_count": review["summary"]["evaluated_count"],
                "green_candidate_count": review["summary"]["green_candidate_count"],
                "best_params": review["summary"]["best_params"],
                "best_downside_alignment": review["summary"]["best_downside_alignment"],
                "best_downside_grade": review["summary"]["best_downside_grade"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
