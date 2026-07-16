#!/usr/bin/env python3
"""A21.19 REENTRY_REGRET_GATE shadow evaluator.

Research-only wrapper around the existing A21.18 decision-focused regret
evaluator.  A21.19 deliberately removes automatic de-risking actions and keeps
only KEEP / NO_ADD / REENTER:

KEEP    = maintain A21.18 stateful shadow allocation
NO_ADD  = block incremental 00631L additions without cutting existing exposure
REENTER = move a defensive shadow allocation back toward A21.18
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _build_action_labels, _targets_from_report
from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    PANEL_2025_2026,
    _parse_windows,
    _resolve,
    evaluate_window,
)
from tw_output_standard import OutputStandardizer, write_standard_output


A2119_ACTIONS = ("KEEP", "NO_ADD", "REENTER")
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2119_reentry_regret_gate_shadow_latest.json"


def _event_study_for_window(
    *,
    label: str,
    start: str,
    end: str,
    panel_path: str | None,
    db_path: Path,
    initial_value: float,
    horizon: int,
    lambda_mdd: float,
    gamma_turnover: float,
    eta_missed_rebound: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=panel_path,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    prices, _coverage = _load_total_return_prices(db_path, frame.index)
    target_weights = _targets_from_report(frame, report)
    labels = _build_action_labels(
        prices,
        target_weights,
        horizon=horizon,
        lambda_mdd=lambda_mdd,
        gamma_turnover=gamma_turnover,
        eta_missed_rebound=eta_missed_rebound,
        cap10=0.10,
        actions=A2119_ACTIONS,
    )
    w = target_weights["00631L.TW"].astype(float)
    delta = w.diff().fillna(0.0)
    regimes = frame["execution_regime"].astype(str) if "execution_regime" in frame else frame["regime"].astype(str)
    prior_regime = regimes.shift(1).fillna(regimes)
    events: list[dict[str, Any]] = []
    for dt in target_weights.index:
        event_types: list[str] = []
        if float(delta.loc[dt]) > 1e-10:
            event_types.append("00631l_target_increase")
        if prior_regime.loc[dt] != regimes.loc[dt]:
            event_types.append(f"regime_transition:{prior_regime.loc[dt]}->{regimes.loc[dt]}")
        if not event_types:
            continue
        realized = labels.loc[dt].to_dict() if dt in labels.index else {}
        no_add_regret = realized.get("NO_ADD")
        reenter_regret = realized.get("REENTER")
        events.append(
            {
                "date": str(dt.date()),
                "event_types": event_types,
                "execution_regime": regimes.loc[dt],
                "prior_execution_regime": prior_regime.loc[dt],
                "a2118_00631l_weight": float(w.loc[dt]),
                "prior_a2118_00631l_weight": float(w.shift(1).fillna(w).loc[dt]),
                "delta_00631l_weight": float(delta.loc[dt]),
                "realized_regret": {
                    "NO_ADD": float(no_add_regret) if no_add_regret is not None else None,
                    "REENTER": float(reenter_regret) if reenter_regret is not None else None,
                },
                "no_add_would_help": bool(no_add_regret is not None and float(no_add_regret) > 0.0),
                "no_add_would_hurt": bool(no_add_regret is not None and float(no_add_regret) < 0.0),
            }
        )
    no_add_values = [
        float(event["realized_regret"]["NO_ADD"])
        for event in events
        if event["realized_regret"].get("NO_ADD") is not None
    ]
    return {
        "label": label,
        "window": {"start": start, "end": resolved_end},
        "event_count": len(events),
        "events": events,
        "summary": {
            "00631l_increase_events": sum("00631l_target_increase" in event["event_types"] for event in events),
            "regime_transition_events": sum(
                any(str(item).startswith("regime_transition:") for item in event["event_types"]) for event in events
            ),
            "no_add_help_count": sum(event["no_add_would_help"] for event in events),
            "no_add_hurt_count": sum(event["no_add_would_hurt"] for event in events),
            "mean_no_add_realized_regret": sum(no_add_values) / len(no_add_values) if no_add_values else None,
            "positive_no_add_realized_regret_rate": (
                sum(value > 0.0 for value in no_add_values) / len(no_add_values) if no_add_values else None
            ),
        },
    }


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "windows": 0,
            "triple_pass_windows": 0,
            "candidate_non_keep_days": 0,
            "action_counts": {},
        }
    action_counts: dict[str, int] = {}
    candidate_non_keep_days = 0
    reliability_candidates = 0
    reliability_accepted = 0
    triple_pass = 0

    def _num(value: Any, default: float = -1.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    for item in results:
        for action, count in (item.get("action_counts") or {}).items():
            action_counts[str(action)] = action_counts.get(str(action), 0) + int(count)
        candidate_non_keep_days += int(item.get("non_keep_days", 0) or 0)
        reliability = item.get("selective_reliability") or {}
        reliability_candidates += int(reliability.get("candidate_non_keep_days", 0) or 0)
        reliability_accepted += int(reliability.get("accepted_non_keep_days", 0) or 0)
        delta = item.get("delta_vs_baseline") or {}
        if (
            _num(delta.get("delta_final_value")) >= 0.0
            and _num(delta.get("delta_sharpe_ratio")) >= 0.0
            and _num(delta.get("delta_max_drawdown")) >= 0.0
        ):
            triple_pass += 1
    return {
        "windows": len(results),
        "triple_pass_windows": triple_pass,
        "all_windows_triple_pass": triple_pass == len(results),
        "candidate_non_keep_days": candidate_non_keep_days,
        "action_counts": action_counts,
        "selective_reliability_candidates": reliability_candidates,
        "selective_reliability_accepted": reliability_accepted,
        "selective_reliability_acceptance_rate": (
            reliability_accepted / reliability_candidates if reliability_candidates else None
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    windows = _parse_windows(args.windows)
    results = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            panel_path=panel,
            initial_value=float(args.initial_value),
            horizon=int(args.horizon),
            min_train_days=int(args.min_train_days),
            train_window_days=int(args.train_window_days),
            edge_threshold=float(args.edge_threshold),
            regret_clip=float(args.regret_clip),
            adjustment_fraction=float(args.adjustment_fraction),
            turnover_cap=float(args.turnover_cap),
            lambda_mdd=float(args.lambda_mdd),
            gamma_turnover=float(args.gamma_turnover),
            eta_missed_rebound=float(args.eta_missed_rebound),
            cap10=0.10,
            ridge_alpha=float(args.ridge_alpha),
            stateful_actions=True,
            reenter_edge_threshold=float(args.reenter_edge_threshold),
            require_panel_signal=bool(args.require_panel_signal),
            selective_reliability=True,
            reliability_max_error_percentile=float(args.reliability_max_error_percentile),
            reliability_min_train_days=int(args.reliability_min_train_days),
            actions=A2119_ACTIONS,
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
        for label, start, end, panel, bucket in windows
    ]
    event_studies = [
        _event_study_for_window(
            label=label,
            start=start,
            end=end,
            panel_path=panel,
            db_path=db_path,
            initial_value=float(args.initial_value),
            horizon=int(args.horizon),
            lambda_mdd=float(args.lambda_mdd),
            gamma_turnover=float(args.gamma_turnover),
            eta_missed_rebound=float(args.eta_missed_rebound),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
        for label, start, end, panel, _bucket in windows
    ]
    return {
        "report_type": "a2119_reentry_regret_gate_shadow",
        "strategy_id": "A21.19_REENTRY_REGRET_GATE",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "architecture": [
            "A21.18 base strategy",
            "LETF trend / mean-reversion regime",
            "H20 crash diagnostic",
            "Trough / rebound nowcast",
            "Action-regret model",
            "Selective reliability gate",
            "KEEP / NO_ADD / REENTER",
        ],
        "policy": {
            "actions": list(A2119_ACTIONS),
            "auto_deleverage_overlay": False,
            "cap_actions_enabled": False,
            "NO_ADD": "prohibit incremental 00631L additions without selling existing exposure",
            "REENTER": "restore toward A21.18 when stateful shadow allocation is below A21.18",
            "KEEP": "maintain A21.18/stateful shadow allocation",
            "production_effect": "none",
        },
        "method": {
            "target": "action_regret = Utility(action) - Utility(KEEP)",
            "utility": {
                "horizon": int(args.horizon),
                "lambda_mdd": float(args.lambda_mdd),
                "gamma_turnover": float(args.gamma_turnover),
                "eta_missed_rebound": float(args.eta_missed_rebound),
            },
            "stabilizers": {
                "stateful_actions": True,
                "selective_reliability": True,
                "edge_threshold": float(args.edge_threshold),
                "reenter_edge_threshold": float(args.reenter_edge_threshold),
                "regret_clip": float(args.regret_clip),
                "adjustment_fraction": float(args.adjustment_fraction),
                "turnover_cap": float(args.turnover_cap),
                "reliability_max_error_percentile": float(args.reliability_max_error_percentile),
                "reliability_min_train_days": int(args.reliability_min_train_days),
                "require_panel_signal": bool(args.require_panel_signal),
            },
            "model": {
                "type": "rolling_ridge_linear_per_action",
                "min_train_days": int(args.min_train_days),
                "train_window_days": int(args.train_window_days),
                "ridge_alpha": float(args.ridge_alpha),
            },
        },
        "summary": _summarize_results(results),
        "event_study_summary": {
            "windows": len(event_studies),
            "event_count": sum(int(item.get("event_count", 0) or 0) for item in event_studies),
            "00631l_increase_events": sum(
                int((item.get("summary") or {}).get("00631l_increase_events", 0) or 0)
                for item in event_studies
            ),
            "no_add_help_count": sum(
                int((item.get("summary") or {}).get("no_add_help_count", 0) or 0)
                for item in event_studies
            ),
            "no_add_hurt_count": sum(
                int((item.get("summary") or {}).get("no_add_hurt_count", 0) or 0)
                for item in event_studies
            ),
        },
        "promotion_assessment": {
            "decision": "shadow_only_first_pass",
            "promote_to_live": False,
            "reason": (
                "First pass removes CAP/de-risk actions and evaluates only KEEP/NO_ADD/REENTER. "
                "Require multi-window improvement before any live advisory integration."
            ),
        },
        "windows": results,
        "event_studies": event_studies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--min-train-days", type=int, default=120)
    parser.add_argument("--train-window-days", type=int, default=420)
    parser.add_argument("--edge-threshold", type=float, default=0.002)
    parser.add_argument("--reenter-edge-threshold", type=float, default=-0.0005)
    parser.add_argument("--regret-clip", type=float, default=0.03)
    parser.add_argument("--adjustment-fraction", type=float, default=0.40)
    parser.add_argument("--turnover-cap", type=float, default=0.10)
    parser.add_argument("--lambda-mdd", type=float, default=0.35)
    parser.add_argument("--gamma-turnover", type=float, default=0.015)
    parser.add_argument("--eta-missed-rebound", type=float, default=0.30)
    parser.add_argument("--ridge-alpha", type=float, default=10.0)
    parser.add_argument("--require-panel-signal", action="store_true")
    parser.add_argument("--reliability-max-error-percentile", type=float, default=0.70)
    parser.add_argument("--reliability-min-train-days", type=int, default=60)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument(
        "--windows",
        default=f"active_2025_2026:2025-01-02:latest:{PANEL_2025_2026}:tuning_window",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(args)
    std = OutputStandardizer("evaluate_a2119_reentry_regret_gate")
    write_standard_output(std.success(report, run_id=datetime.now().strftime("%Y%m%d_%H%M%S")), args.output)
    print(f"A21.19 reentry regret gate shadow: {_resolve(args.output)}")


if __name__ == "__main__":
    main()
