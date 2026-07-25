from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_llm_state_reward_shadow_training_request_package import (
    build_package,
    write_package,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _design(path: Path) -> Path:
    return _write(
        path,
        {
            "decision": {
                "shadow_model_design_allowed": True,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
            "design": {
                "design_id": "unit_design",
                "freeze_id": "unit_freeze",
                "frozen_manifest_sha256": "a" * 64,
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "selected_label": "v2_tuned_downside_tail_decay",
                "eligible_tickers": ["0050.TW", "0056.TW"],
                "excluded_tickers": ["00631L.TW", "00632R.TW"],
                "state_columns": ["downside_deviation", "realized_volatility"],
                "reward_columns": ["reward_proxy"],
                "allowed_shadow_model_family": "tabular_or_sequence_shadow_model_design_only",
                "allowed_training_label": "future_return_or_downside_proxy_for_offline_design",
                "hard_constraints": {
                    "no_live_signal_output": True,
                    "no_target_weight_output": True,
                    "no_auto_rebalance": True,
                    "no_00631l_add": True,
                    "no_00632r_open": True,
                },
            },
        },
    )


def _readiness(path: Path, *, ready: bool = True) -> Path:
    return _write(
        path,
        {
            "decision": {
                "shadow_training_ready": ready,
                "shadow_training_request_allowed": False,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
            "training_design_boundary": {
                "design_id": "unit_design",
                "freeze_id": "unit_freeze",
                "frozen_manifest_sha256": "a" * 64,
                "proposal_id": "gift_research_downside_vol_letf_tail_decay_v1",
                "selected_label": "v2_tuned_downside_tail_decay",
                "eligible_tickers": ["0050.TW", "0056.TW"],
                "excluded_tickers": ["00631L.TW", "00632R.TW"],
                "state_columns": ["downside_deviation", "realized_volatility"],
                "reward_columns": ["reward_proxy"],
                "allowed_shadow_model_family": "tabular_or_sequence_shadow_model_design_only",
                "allowed_training_label": "future_return_or_downside_proxy_for_offline_design",
                "hard_constraints": {
                    "no_live_signal_output": True,
                    "no_target_weight_output": True,
                    "no_auto_rebalance": True,
                    "no_00631l_add": True,
                    "no_00632r_open": True,
                },
            },
        },
    )


def _regime(path: Path, *, candidate: dict | None = None) -> Path:
    return _write(
        path,
        {
            "summary": {
                "recommended_candidate": candidate
                if candidate is not None
                else {
                    "regime_rule": "trend_above_train_median",
                    "high_score": 1.03,
                    "cost_bps": 5.0,
                }
            },
            "decision": {
                "regime_filter_resolves_5bps_warning": candidate is not None or True,
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def _research(path: Path) -> Path:
    return _write(
        path,
        {
            "status": "blocked",
            "summary": {"llm_state_reward_shadow_training_ready": True},
            "blocking_reasons": ["some_existing_gate_blocked"],
            "decision": {
                "model_training_allowed": False,
                "ppo_training_allowed": False,
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        },
    )


def test_build_package_ready_for_manual_review_but_no_training_or_live(tmp_path: Path) -> None:
    package = build_package(
        design_review_path=_design(tmp_path / "design.json"),
        training_readiness_path=_readiness(tmp_path / "readiness.json"),
        regime_filtered_micro_tilt_path=_regime(tmp_path / "regime.json"),
        research_shadow_path=_research(tmp_path / "research.json"),
        as_of="2026-07-21",
    )

    assert package["report_type"] == "group_a_plus_llm_state_reward_shadow_training_request_package"
    assert package["status"] == "available_for_manual_review"
    assert package["summary"]["package_ready_for_manual_review"] is True
    assert package["summary"]["recommended_regime_rule"] == "trend_above_train_median"
    assert package["summary"]["research_shadow_status"] == "blocked"
    assert package["request_boundary"]["freeze_id"] == "unit_freeze"
    assert package["request_boundary"]["validation_plan"]["regime_filter_required"] is True
    assert package["request_boundary"]["hard_constraints"]["separate_training_approval_required"] is True
    assert package["decision"]["shadow_training_request_allowed"] is False
    assert package["decision"]["model_training_allowed"] is False
    assert package["decision"]["ppo_training_allowed"] is False
    assert package["decision"]["outputs_target_weights"] is False
    assert package["decision"]["promote_to_live"] is False
    assert package["decision"]["allow_00631l_add"] is False
    assert package["decision"]["allow_00632r_open"] is False


def test_build_package_blocks_without_regime_candidate(tmp_path: Path) -> None:
    package = build_package(
        design_review_path=_design(tmp_path / "design.json"),
        training_readiness_path=_readiness(tmp_path / "readiness.json"),
        regime_filtered_micro_tilt_path=_regime(tmp_path / "regime.json", candidate=None),
        research_shadow_path=_research(tmp_path / "research.json"),
        as_of="2026-07-21",
    )

    assert package["status"] == "available_for_manual_review"

    regime_path = tmp_path / "regime.json"
    payload = json.loads(regime_path.read_text(encoding="utf-8"))
    payload["summary"]["recommended_candidate"] = None
    regime_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    package = build_package(
        design_review_path=tmp_path / "design.json",
        training_readiness_path=tmp_path / "readiness.json",
        regime_filtered_micro_tilt_path=regime_path,
        research_shadow_path=tmp_path / "research.json",
        as_of="2026-07-21",
    )

    assert package["status"] == "blocked"
    assert "missing_regime_filter_recommended_candidate" in package["blocking_reasons"]
    assert package["decision"]["model_training_allowed"] is False
    assert package["decision"]["promote_to_live"] is False


def test_write_package_writes_latest_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "package.json"
    history = tmp_path / "history"
    package = {
        "report_type": "group_a_plus_llm_state_reward_shadow_training_request_package",
        "as_of": "2026-07-21",
    }

    write_package(package, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == package
    history_file = history / "llm_state_reward_shadow_training_request_package_20260721.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == package
