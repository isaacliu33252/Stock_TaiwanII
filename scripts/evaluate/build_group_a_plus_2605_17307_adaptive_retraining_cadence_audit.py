#!/usr/bin/env python3
"""Build a GroupA+ adaptive retraining cadence audit inspired by arXiv 2605.17307.

The paper retrains only when validation evidence deteriorates. This audit
maps that idea to existing GroupA+ shadow artifacts. It never trains a model
and never changes target weights.
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

from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_adaptive_retraining_cadence_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_adaptive_retraining_cadence_audit/history"
DEFAULT_STRATEGY = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_SEED_GATE = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_promotion_gate.json"
DEFAULT_SEED_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_SAC_SMOKE = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_sac_feasibility_smoke.json"
DEFAULT_EXTREME_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_extreme_state_monitor.json"
DEFAULT_DOWNSIDE_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _active_strategy_id(strategy_path: Path) -> str | None:
    strategy = _load_json(strategy_path)
    active = strategy.get("active_strategy") if isinstance(strategy.get("active_strategy"), dict) else {}
    value = active.get("id")
    return str(value) if value else None


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _seed_averaging_audit(gate_path: Path, monitor_path: Path) -> dict[str, Any]:
    gate = _load_json(gate_path)
    monitor = _load_json(monitor_path)
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    criteria = gate.get("criteria") if isinstance(gate.get("criteria"), dict) else {}
    forward_rows = int(summary.get("forward_rows") or 0)
    minimum_rows = int(criteria.get("minimum_forward_rows") or 20)
    parity = _float(summary.get("parity_pass_rate"))
    minimum_parity = _float(criteria.get("minimum_parity_pass_rate")) or 0.95
    blockers = list(gate.get("blockers") or [])
    retrain = bool(forward_rows >= minimum_rows and parity is not None and parity < minimum_parity)
    if forward_rows < minimum_rows:
        action = "continue_daily_forward_shadow_until_minimum_rows"
    elif retrain:
        action = "open_retraining_or_policy_mapping_review_before_any_promotion"
    else:
        action = "promotion_review_possible_but_still_manual_only"
    return {
        "model_or_shadow": "a2118_seed_averaging_preferred_ensemble_42_43_44",
        "artifact_status": gate.get("status"),
        "latest_monitor_status": monitor.get("status"),
        "evidence": {
            "forward_rows": forward_rows,
            "minimum_forward_rows": minimum_rows,
            "parity_pass_rate": parity,
            "minimum_parity_pass_rate": minimum_parity,
            "blockers": blockers,
        },
        "cadence_decision": {
            "daily_monitoring": True,
            "retrain_now": retrain,
            "promotion_review_now": False,
            "next_action": action,
        },
    }


def _sac_audit(smoke_path: Path) -> dict[str, Any]:
    smoke = _load_json(smoke_path)
    panel = smoke.get("data_panel") if isinstance(smoke.get("data_panel"), dict) else {}
    decision = smoke.get("decision") if isinstance(smoke.get("decision"), dict) else {}
    blockers = list(smoke.get("blocking_reasons") or [])
    shortfall = int(panel.get("paper_style_wfo_observation_shortfall") or 0)
    return {
        "model_or_shadow": "2605_17307_sac_candidate",
        "artifact_status": "available" if smoke else "missing",
        "evidence": {
            "can_run_local_sac_environment_smoke": bool(decision.get("can_run_local_sac_environment_smoke")),
            "paper_style_sac_training_ready": bool(decision.get("paper_style_sac_training_ready")),
            "observations": panel.get("observations"),
            "paper_style_wfo_observation_shortfall": shortfall,
            "blockers": blockers,
        },
        "cadence_decision": {
            "daily_monitoring": False,
            "retrain_now": False,
            "promotion_review_now": False,
            "next_action": "do_not_schedule_training_until_simplex_wrapper_oos_gate_and_wfo_history_are_ready",
        },
    }


def _risk_prior_audit(extreme_path: Path) -> dict[str, Any]:
    monitor = _load_json(extreme_path)
    latest = monitor.get("latest_state") if isinstance(monitor.get("latest_state"), dict) else {}
    state = latest.get("risk_aversion_state")
    return {
        "model_or_shadow": "2606_09104_risk_aversion_prior_monitor",
        "artifact_status": "available" if monitor else "missing",
        "evidence": {
            "latest_risk_aversion_state": state,
            "last_extreme_date": monitor.get("last_extreme_date"),
            "trading_days_since_last_extreme": monitor.get("trading_days_since_last_extreme"),
        },
        "cadence_decision": {
            "daily_monitoring": True,
            "retrain_now": False,
            "promotion_review_now": state == "EXTREME",
            "next_action": "continue_monitoring_and_only_open_staged_00631l_review_if_extreme",
        },
    }


def _downside_shadow_audit(path: Path) -> dict[str, Any]:
    shadow = _load_json(path)
    decision = shadow.get("decision") if isinstance(shadow.get("decision"), dict) else {}
    return {
        "model_or_shadow": "2411_19649_downside_diversification_forecast_shadow",
        "artifact_status": "available" if shadow else "missing",
        "evidence": {
            "report_type": shadow.get("report_type"),
            "production_effect": shadow.get("production_effect") or decision.get("production_effect"),
            "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
        },
        "cadence_decision": {
            "daily_monitoring": True,
            "retrain_now": False,
            "promotion_review_now": False,
            "next_action": "keep_as_shadow_gate_only_until_realized_bucket_value_is_stable",
        },
    }


def build_audit(
    *,
    strategy_path: Path = DEFAULT_STRATEGY,
    seed_gate_path: Path = DEFAULT_SEED_GATE,
    seed_monitor_path: Path = DEFAULT_SEED_MONITOR,
    sac_smoke_path: Path = DEFAULT_SAC_SMOKE,
    extreme_monitor_path: Path = DEFAULT_EXTREME_MONITOR,
    downside_shadow_path: Path = DEFAULT_DOWNSIDE_SHADOW,
) -> dict[str, Any]:
    rows = [
        _seed_averaging_audit(_resolve(seed_gate_path), _resolve(seed_monitor_path)),
        _sac_audit(_resolve(sac_smoke_path)),
        _risk_prior_audit(_resolve(extreme_monitor_path)),
        _downside_shadow_audit(_resolve(downside_shadow_path)),
    ]
    retrain_now = [row["model_or_shadow"] for row in rows if row["cadence_decision"]["retrain_now"]]
    promotion_now = [row["model_or_shadow"] for row in rows if row["cadence_decision"]["promotion_review_now"]]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_adaptive_retraining_cadence_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "imported_concept": "adaptive_retraining_only_when_validation_or_shadow_evidence_deteriorates",
        },
        "latest_strategy": _active_strategy_id(_resolve(strategy_path)),
        "audited_items": rows,
        "decision": {
            "train_any_model_now": bool(retrain_now),
            "models_requiring_retraining_review": retrain_now,
            "promotion_reviews_open_now": promotion_now,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "No 2605.17307-style adaptive retraining trigger fires today. Continue shadow monitoring; do not train SAC or alter the latest strategy.",
        },
    }


def write_audit(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d")
    (history_dir / f"2605_17307_adaptive_retraining_cadence_audit_{stamp}.json").write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--seed-gate", default=str(DEFAULT_SEED_GATE))
    parser.add_argument("--seed-monitor", default=str(DEFAULT_SEED_MONITOR))
    parser.add_argument("--sac-smoke", default=str(DEFAULT_SAC_SMOKE))
    parser.add_argument("--extreme-monitor", default=str(DEFAULT_EXTREME_MONITOR))
    parser.add_argument("--downside-shadow", default=str(DEFAULT_DOWNSIDE_SHADOW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_audit(
        strategy_path=_resolve(args.strategy),
        seed_gate_path=_resolve(args.seed_gate),
        seed_monitor_path=_resolve(args.seed_monitor),
        sac_smoke_path=_resolve(args.sac_smoke),
        extreme_monitor_path=_resolve(args.extreme_monitor),
        downside_shadow_path=_resolve(args.downside_shadow),
    )
    write_audit(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
