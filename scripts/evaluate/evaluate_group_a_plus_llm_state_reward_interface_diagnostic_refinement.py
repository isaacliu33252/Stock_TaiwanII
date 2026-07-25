#!/usr/bin/env python3
"""Diagnostic-refinement review for GIFT-style state/reward proxies.

This is the DGR-style layer from arXiv 2606.08450 adapted to GroupA+ governance:
it summarizes feature and reward diagnostics for offline review only. It never
trains PPO, outputs actions, target weights, or live rebalance decisions.
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

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_feature_stability import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_FEATURE_STABILITY,
    _finite_float,
    _load_feature_frames,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    ACCEPTED_PROPOSAL_ID,
    DOWNSIDE_TAIL_DECAY_PROPOSAL_ID,
    DEFAULT_DB,
    DEFAULT_VALIDATION,
    _accepted_proposals,
    _load_json,
    _proposal_columns,
    _resolve,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_windowed_stability import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_WINDOWED_STABILITY,
    DEFAULT_TICKERS,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_diagnostic_refinement_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_diagnostic_refinement/history"
DEFAULT_FORWARD_HORIZON = 5


def _alignment_grade(alignment: float | None, *, unavailable_reason: str) -> dict[str, Any]:
    if alignment is None:
        return {
            "grade": "unavailable",
            "abs_alignment": None,
            "ppo_training_queue_allowed": False,
            "reason": unavailable_reason,
        }
    abs_alignment = abs(float(alignment))
    if abs_alignment >= 0.05:
        grade = "green"
        reason = "alignment_clears_research_threshold"
    elif abs_alignment >= 0.02:
        grade = "yellow"
        reason = "alignment_requires_manual_review"
    else:
        grade = "red"
        reason = "alignment_too_weak_for_training_queue"
    return {
        "grade": grade,
        "abs_alignment": _finite_float(abs_alignment),
        "ppo_training_queue_allowed": grade == "green",
        "reason": reason,
    }


def _downside_alignment_semantic(alignment: float | None) -> dict[str, Any]:
    if alignment is None:
        return {
            "direction": "unavailable",
            "risk_sensitive_useful": False,
            "dangerous_direction": False,
            "explanation": "Downside alignment is unavailable.",
        }
    if alignment < 0:
        return {
            "direction": "negative_reward_vs_positive_downside",
            "risk_sensitive_useful": True,
            "dangerous_direction": False,
            "explanation": "Reward gets worse when future downside risk is larger.",
        }
    if alignment > 0:
        return {
            "direction": "positive_reward_vs_positive_downside",
            "risk_sensitive_useful": False,
            "dangerous_direction": True,
            "explanation": "Reward improves when future downside risk is larger.",
        }
    return {
        "direction": "zero_alignment",
        "risk_sensitive_useful": False,
        "dangerous_direction": False,
        "explanation": "Reward has no measured directional relationship to future downside.",
    }


def _overall_gate(
    *,
    proposal_id: str,
    return_gate: dict[str, Any],
    downside_gate: dict[str, Any],
    downside_semantic: dict[str, Any],
) -> dict[str, Any]:
    if proposal_id == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID:
        grade = downside_gate["grade"]
        queue_allowed = grade == "green" and downside_semantic["risk_sensitive_useful"]
        return {
            "objective": "future_downside_alignment",
            "grade": grade,
            "ppo_training_queue_allowed": queue_allowed,
            "reason": (
                "downside_objective_clears_threshold"
                if queue_allowed
                else f"downside_objective_{downside_gate['reason']}"
            ),
        }
    return {
        "objective": "future_return_alignment",
        "grade": return_gate["grade"],
        "ppo_training_queue_allowed": return_gate["ppo_training_queue_allowed"],
        "reason": f"return_objective_{return_gate['reason']}",
    }


def _safe_corr(left: pd.Series, right: pd.Series, *, min_rows: int) -> float | None:
    pair = pd.concat(
        [pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pair) < min_rows:
        return None
    if pair.iloc[:, 0].std(ddof=0) <= 0 or pair.iloc[:, 1].std(ddof=0) <= 0:
        return None
    return _finite_float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))


def _slope(series: pd.Series, *, min_rows: int) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(numeric) < min_rows:
        return None
    y = numeric.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    x_std = x.std()
    if x_std <= 0:
        return None
    slope = np.polyfit(x, y, 1)[0]
    return _finite_float(slope / (float(np.std(y)) + 1e-12))


def _mean(values: list[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return _finite_float(np.mean(finite)) if finite else None


def _ticker_diagnostics(
    ticker: str,
    frame: pd.DataFrame,
    *,
    forward_horizon: int,
    min_rows: int,
    proposal_id: str,
) -> dict[str, Any]:
    data = frame.copy().sort_values("date")
    close = pd.to_numeric(data["close"], errors="coerce")
    returns = close.pct_change()
    future_return = close.shift(-forward_horizon) / close - 1.0
    future_abs_return = future_return.abs()
    downside_future = future_return.clip(upper=0.0).abs()
    reward_proxy = pd.to_numeric(data["reward_proxy"], errors="coerce")
    reward_cumsum = reward_proxy.fillna(0.0).cumsum()

    if proposal_id == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID:
        feature_ic = {
            "downside_deviation_to_future_downside": _safe_corr(
                data["downside_deviation"], downside_future, min_rows=min_rows
            ),
            "realized_volatility_to_future_abs_return": _safe_corr(
                data["realized_volatility"], future_abs_return, min_rows=min_rows
            ),
            "drawdown_depth_to_future_downside": _safe_corr(
                data["drawdown_depth"], downside_future, min_rows=min_rows
            ),
            "ema_cross_strength_to_future_return": _safe_corr(
                data["ema_cross_strength"], future_return, min_rows=min_rows
            ),
        }
    else:
        feature_ic = {
            "relative_momentum_to_future_return": _safe_corr(
                data["relative_momentum"], future_return, min_rows=min_rows
            ),
            "realized_volatility_to_future_abs_return": _safe_corr(
                data["realized_volatility"], future_abs_return, min_rows=min_rows
            ),
            "drawdown_penalty_to_future_downside": _safe_corr(
                data["drawdown_penalty"], downside_future, min_rows=min_rows
            ),
        }

    finite_reward = reward_proxy.replace([np.inf, -np.inf], np.nan).dropna()
    reward_mean = _finite_float(finite_reward.mean()) if not finite_reward.empty else None
    reward_std = _finite_float(finite_reward.std(ddof=0)) if len(finite_reward) else None
    reward_snr = None
    if reward_mean is not None and reward_std is not None and reward_std > 0:
        reward_snr = abs(reward_mean) / reward_std

    reward_diagnostics = {
        "finite_count": int(len(finite_reward)),
        "finite_ratio": float(len(finite_reward) / len(data)) if len(data) else 0.0,
        "snr_abs_mean_over_std": _finite_float(reward_snr),
        "autocorrelation_lag1": _safe_corr(reward_proxy, reward_proxy.shift(1), min_rows=min_rows),
        "cumulative_reward_trend": _slope(reward_cumsum, min_rows=min_rows),
        "alignment_to_future_return": _safe_corr(reward_proxy, future_return, min_rows=min_rows),
        "alignment_to_future_downside": _safe_corr(reward_proxy, downside_future, min_rows=min_rows),
    }

    return {
        "ticker": ticker,
        "data_range": {
            "start": data["date"].min().date().isoformat(),
            "end": data["date"].max().date().isoformat(),
            "rows": int(len(data)),
        },
        "forward_horizon_days": forward_horizon,
        "feature_ic": feature_ic,
        "reward_diagnostics": reward_diagnostics,
        "market_context": {
            "mean_daily_return": _finite_float(returns.mean()),
            "daily_volatility": _finite_float(returns.std(ddof=0)),
            "latest_drawdown_penalty": _finite_float(data["drawdown_penalty"].iloc[-1]),
            "latest_reward_proxy": _finite_float(data["reward_proxy"].iloc[-1]),
        },
    }


def _aggregate(rows: list[dict[str, Any]], *, proposal_id: str) -> dict[str, Any]:
    feature_keys = list((_proposal_columns(proposal_id).get("feature_columns") or []))
    feature_ic_keys = sorted({key for row in rows for key in row.get("feature_ic", {})})
    reward_keys = [
        "snr_abs_mean_over_std",
        "autocorrelation_lag1",
        "cumulative_reward_trend",
        "alignment_to_future_return",
        "alignment_to_future_downside",
    ]
    return {
        "feature_ic_mean": {
            key: _mean([row["feature_ic"].get(key) for row in rows])
            for key in feature_ic_keys
        },
        "feature_columns": feature_keys,
        "reward_diagnostics_mean": {
            key: _mean([row["reward_diagnostics"].get(key) for row in rows])
            for key in reward_keys
        },
        "finite_reward_min_ratio": min(
            (row["reward_diagnostics"]["finite_ratio"] for row in rows),
            default=None,
        ),
    }


def build_review(
    *,
    validation_path: Path = DEFAULT_VALIDATION,
    feature_stability_path: Path = DEFAULT_FEATURE_STABILITY,
    windowed_stability_path: Path = DEFAULT_WINDOWED_STABILITY,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    start: str = "2016-01-01",
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
    min_rows: int = 120,
    min_reward_finite_ratio: float = 0.95,
    min_abs_alignment_warning: float = 0.02,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    downside_drawdown_weight: float = 0.50,
    downside_volatility_weight: float = 0.30,
    downside_tail_decay_weight: float = 0.20,
    volatility_penalty_scale: float = 3.0,
    tail_decay_scale: float = 4.0,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    selected_tickers = tickers or list(DEFAULT_TICKERS)
    validation = _load_json(validation_path)
    feature_stability = _load_json(feature_stability_path)
    windowed_stability = _load_json(windowed_stability_path)
    accepted_ids = _accepted_proposals(validation)

    blockers: list[str] = []
    warnings: list[str] = []
    if not validation:
        blockers.append("missing_proposal_validation_review")
    if proposal_id not in accepted_ids:
        blockers.append("accepted_sample_proposal_missing")
    if not feature_stability:
        blockers.append("missing_feature_stability_review")
    elif feature_stability.get("status") != "available_for_manual_offline_review":
        blockers.append(f"feature_stability_not_available:{feature_stability.get('status')}")
    if not windowed_stability:
        blockers.append("missing_windowed_stability_review")
    elif windowed_stability.get("status") != "available_for_manual_offline_review":
        blockers.append(f"windowed_stability_not_available:{windowed_stability.get('status')}")
    if not db_path.exists():
        blockers.append("missing_duckdb")

    frames = (
        _load_feature_frames(
            db_path,
            selected_tickers,
            start=start,
            proposal_id=proposal_id,
            downside_drawdown_weight=downside_drawdown_weight,
            downside_volatility_weight=downside_volatility_weight,
            downside_tail_decay_weight=downside_tail_decay_weight,
            volatility_penalty_scale=volatility_penalty_scale,
            tail_decay_scale=tail_decay_scale,
        )
        if db_path.exists()
        else {}
    )
    missing_tickers = [ticker for ticker in selected_tickers if ticker not in frames]
    if missing_tickers:
        blockers.append(f"missing_feature_frames:{','.join(missing_tickers)}")

    ticker_diagnostics = [
        _ticker_diagnostics(
            ticker,
            frames[ticker],
            forward_horizon=forward_horizon,
            min_rows=min_rows,
            proposal_id=proposal_id,
        )
        for ticker in selected_tickers
        if ticker in frames
    ]
    aggregate = _aggregate(ticker_diagnostics, proposal_id=proposal_id)

    finite_ratio = aggregate.get("finite_reward_min_ratio")
    if finite_ratio is not None and finite_ratio < min_reward_finite_ratio:
        blockers.append(f"low_reward_finite_ratio:{finite_ratio:.4f}")

    reward_means = aggregate.get("reward_diagnostics_mean", {})
    alignment = reward_means.get("alignment_to_future_return")
    return_alignment_gate = _alignment_grade(
        alignment,
        unavailable_reason="reward_future_return_alignment_unavailable",
    )
    if alignment is None:
        warnings.append("reward_future_return_alignment_unavailable")
    elif abs(alignment) < min_abs_alignment_warning:
        warnings.append(f"weak_reward_future_return_alignment:{alignment:.4f}")

    downside_alignment = reward_means.get("alignment_to_future_downside")
    downside_alignment_gate = _alignment_grade(
        downside_alignment,
        unavailable_reason="reward_future_downside_alignment_unavailable",
    )
    downside_semantic = _downside_alignment_semantic(downside_alignment)
    overall_gate = _overall_gate(
        proposal_id=proposal_id,
        return_gate=return_alignment_gate,
        downside_gate=downside_alignment_gate,
        downside_semantic=downside_semantic,
    )
    if downside_alignment is None:
        warnings.append("reward_future_downside_alignment_unavailable")
    elif proposal_id == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID and not downside_semantic["risk_sensitive_useful"]:
        warnings.append(f"downside_reward_direction_not_risk_sensitive:{downside_alignment:.4f}")

    inherited_warnings = []
    for payload, prefix in [
        (feature_stability, "feature_stability"),
        (windowed_stability, "windowed_stability"),
    ]:
        for reason in payload.get("warning_reasons") or []:
            inherited_warnings.append(f"{prefix}:{reason}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_diagnostic_refinement_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "diagnostic_refinement_review_only_no_model_training_no_live_action",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.08450.pdf",
            "arxiv": "2606.08450v1",
            "imported_component": "Diagnostic-guided Refinement proxy diagnostics",
        },
        "inputs": {
            "validation_review": str(validation_path),
            "feature_stability_review": str(feature_stability_path),
            "windowed_stability_review": str(windowed_stability_path),
            "db": str(db_path),
            "tickers": selected_tickers,
            "start": start,
            "forward_horizon": forward_horizon,
            "min_rows": min_rows,
            "min_reward_finite_ratio": min_reward_finite_ratio,
            "min_abs_alignment_warning": min_abs_alignment_warning,
            "accepted_proposal_id": proposal_id,
            "accepted_proposal_found": proposal_id in accepted_ids,
            "downside_tail_decay_params": {
                "drawdown_weight": downside_drawdown_weight,
                "volatility_weight": downside_volatility_weight,
                "tail_decay_weight": downside_tail_decay_weight,
                "volatility_scale": volatility_penalty_scale,
                "tail_decay_scale": tail_decay_scale,
            },
        },
        "summary": {
            "ticker_count": len(selected_tickers),
            "available_ticker_count": len(frames),
            "missing_tickers": missing_tickers,
            "finite_reward_min_ratio": aggregate.get("finite_reward_min_ratio"),
            "mean_reward_snr": reward_means.get("snr_abs_mean_over_std"),
            "mean_reward_autocorrelation_lag1": reward_means.get("autocorrelation_lag1"),
            "mean_reward_future_return_alignment": alignment,
            "mean_reward_future_downside_alignment": downside_alignment,
            "reward_alignment_grade": overall_gate["grade"],
            "reward_alignment_objective": overall_gate["objective"],
            "reward_alignment_abs": (
                downside_alignment_gate["abs_alignment"]
                if overall_gate["objective"] == "future_downside_alignment"
                else return_alignment_gate["abs_alignment"]
            ),
            "return_alignment_grade": return_alignment_gate["grade"],
            "return_alignment_abs": return_alignment_gate["abs_alignment"],
            "downside_alignment_grade": downside_alignment_gate["grade"],
            "downside_alignment_abs": downside_alignment_gate["abs_alignment"],
            "downside_alignment_direction": downside_semantic["direction"],
            "downside_alignment_risk_sensitive_useful": downside_semantic["risk_sensitive_useful"],
            "ppo_training_queue_allowed_by_alignment": overall_gate["ppo_training_queue_allowed"],
            "inherited_warning_count": len(inherited_warnings),
        },
        "ticker_diagnostics": ticker_diagnostics,
        "aggregate_diagnostics": aggregate,
        "diagnostic_gates": {
            "reward_future_return_alignment": return_alignment_gate,
            "reward_future_downside_alignment": downside_alignment_gate
            | {"semantic": downside_semantic},
            "overall_reward_alignment": overall_gate,
            "thresholds": {
                "green_min_abs_alignment": 0.05,
                "yellow_min_abs_alignment": 0.02,
                "red_below_abs_alignment": 0.02,
            },
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings + inherited_warnings)),
        "interpretation": [
            "These diagnostics approximate GIFT DGR feedback without training PPO or modifying the live strategy.",
            "Weak reward alignment is a research warning, not a live trading signal.",
            "Any future PPO experiment must freeze this interface before out-of-sample evaluation.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "diagnostic_refinement_ready_for_research_review": not blockers,
            "diagnostic_refinement_grade": overall_gate["grade"],
            "ppo_training_queue_allowed_by_dgr": not blockers and overall_gate["ppo_training_queue_allowed"],
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_diagnostic_refinement_{stamp}.json"


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
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--feature-stability", default=str(DEFAULT_FEATURE_STABILITY))
    parser.add_argument("--windowed-stability", default=str(DEFAULT_WINDOWED_STABILITY))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[], help="Ticker to include; default uses 0050/00631L/00632R.")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--forward-horizon", type=int, default=DEFAULT_FORWARD_HORIZON)
    parser.add_argument("--min-rows", type=int, default=120)
    parser.add_argument("--min-reward-finite-ratio", type=float, default=0.95)
    parser.add_argument("--min-abs-alignment-warning", type=float, default=0.02)
    parser.add_argument("--proposal-id", default=ACCEPTED_PROPOSAL_ID)
    parser.add_argument("--downside-drawdown-weight", type=float, default=0.50)
    parser.add_argument("--downside-volatility-weight", type=float, default=0.30)
    parser.add_argument("--downside-tail-decay-weight", type=float, default=0.20)
    parser.add_argument("--volatility-penalty-scale", type=float, default=3.0)
    parser.add_argument("--tail-decay-scale", type=float, default=4.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        validation_path=_resolve(args.validation),
        feature_stability_path=_resolve(args.feature_stability),
        windowed_stability_path=_resolve(args.windowed_stability),
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        start=args.start,
        forward_horizon=args.forward_horizon,
        min_rows=args.min_rows,
        min_reward_finite_ratio=args.min_reward_finite_ratio,
        min_abs_alignment_warning=args.min_abs_alignment_warning,
        proposal_id=args.proposal_id,
        downside_drawdown_weight=args.downside_drawdown_weight,
        downside_volatility_weight=args.downside_volatility_weight,
        downside_tail_decay_weight=args.downside_tail_decay_weight,
        volatility_penalty_scale=args.volatility_penalty_scale,
        tail_decay_scale=args.tail_decay_scale,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward diagnostic refinement review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "ticker_count": review["summary"]["ticker_count"],
                "available_ticker_count": review["summary"]["available_ticker_count"],
                "mean_reward_snr": review["summary"]["mean_reward_snr"],
                "mean_reward_future_return_alignment": review["summary"]["mean_reward_future_return_alignment"],
                "warning_count": len(review["warning_reasons"]),
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
