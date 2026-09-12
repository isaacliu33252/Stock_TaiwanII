from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate import build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness as module


def _write_panel(path: Path, *, rows: int = 40, separable: bool = True) -> None:
    data = []
    for idx in range(rows):
        positive = idx % 2 == 0
        prob = 0.8 if positive == separable else 0.2
        data.append(
            {
                "date": f"2026-01-{(idx % 28) + 1:02d}",
                "prob_fwd_mdd_gt5_h20": prob,
                "actual_fwd_mdd_gt5_h20": int(positive),
                "prob_fwd_gain_gt5_h20": prob,
                "actual_fwd_gain_gt5_h20": int(positive),
                "tail_reward_risk_score_h20": 0.1,
            }
        )
    pd.DataFrame(data).to_csv(path, index=False)


def test_build_report_is_shadow_only_even_when_aux_metrics_pass(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel)
    signal = tmp_path / "signal.json"
    policy_lift = tmp_path / "policy_lift.json"
    purged_wf = tmp_path / "purged_wf.json"
    churn_shadow = tmp_path / "churn_shadow.json"
    regime_decay = tmp_path / "regime_decay.json"
    blueprint = tmp_path / "blueprint.json"
    lifecycle = tmp_path / "lifecycle.json"
    delayed_credit = tmp_path / "delayed_credit.json"
    signal.write_text(
        json.dumps({"last_close_date": "2026-01-31", "data_freshness": {"status": "ok"}}),
        encoding="utf-8",
    )
    policy_lift.write_text(
        json.dumps(
            {
                "results": {
                    "net_derisk": {
                        "delta_vs_baseline": {
                            "final_value": 10.0,
                            "sharpe_ratio": 0.1,
                            "max_drawdown": 0.01,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    purged_wf.write_text(
        json.dumps({"summary": {"purged_walk_forward_policy_impact_passed": True, "best_score": "downside_score"}}),
        encoding="utf-8",
    )
    churn_shadow.write_text(
        json.dumps({"summary": {"multi_window_cost_turnover_passed": True, "decision": "shadow_passed_but_not_promoted"}}),
        encoding="utf-8",
    )
    regime_decay.write_text(
        json.dumps({"summary": {"temporal_regime_stability_passed": True, "decision": "shadow_passed_but_not_promoted"}}),
        encoding="utf-8",
    )
    blueprint.write_text(
        json.dumps({"training_allowed": False, "promotion_allowed": False, "decision": {"decision": "blocked"}}),
        encoding="utf-8",
    )
    lifecycle.write_text(
        json.dumps({"summary": {"head_lifecycle_passed": True, "decision": "shadow_passed_but_not_promoted"}}),
        encoding="utf-8",
    )
    delayed_credit.write_text(
        json.dumps({"summary": {"delayed_credit_passed": True, "decision": "shadow_passed_but_not_promoted"}}),
        encoding="utf-8",
    )

    report = module.build_report(
        [("00631L.TW", panel)],
        [("00631L.TW", signal)],
        policy_lift_path=policy_lift,
        purged_wf_path=purged_wf,
        churn_shadow_path=churn_shadow,
        regime_decay_path=regime_decay,
        candidate_bank_blueprint_path=blueprint,
        lifecycle_audit_path=lifecycle,
        delayed_credit_path=delayed_credit,
        min_resolved_rows=20,
        min_positive_rows=10,
        min_auc=0.55,
    )

    assert report["checks"]["existing_aux_heads_available"] is True
    assert report["checks"]["aux_head_standalone_quality_passed"] is True
    assert report["checks"]["quest_trader_retrained_for_group_a_plus"] is False
    assert report["checks"]["downstream_policy_lift_validated"] is True
    assert report["checks"]["purged_walk_forward_policy_impact_passed"] is True
    assert report["checks"]["multi_window_cost_turnover_passed"] is True
    assert report["checks"]["temporal_regime_stability_passed"] is True
    assert report["checks"]["auxiliary_head_lifecycle_passed"] is True
    assert report["checks"]["delayed_credit_alignment_passed"] is True
    assert report["checks"]["candidate_auxiliary_bank_blueprint_available"] is True
    assert report["decision"]["promotion_allowed"] is False
    assert report["changes_latest_strategy"] is False


def test_build_report_blocks_policy_lift_when_final_value_is_negative(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel)
    policy_lift = tmp_path / "policy_lift.json"
    purged_wf = tmp_path / "purged_wf.json"
    churn_shadow = tmp_path / "churn_shadow.json"
    regime_decay = tmp_path / "regime_decay.json"
    blueprint = tmp_path / "blueprint.json"
    lifecycle = tmp_path / "lifecycle.json"
    delayed_credit = tmp_path / "delayed_credit.json"
    policy_lift.write_text(
        json.dumps(
            {
                "results": {
                    "net_derisk": {
                        "delta_vs_baseline": {
                            "final_value": -100.0,
                            "sharpe_ratio": 0.2,
                            "max_drawdown": 0.03,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    purged_wf.write_text(
        json.dumps({"summary": {"purged_walk_forward_policy_impact_passed": False, "best_score": "net_derisk_score"}}),
        encoding="utf-8",
    )
    churn_shadow.write_text(
        json.dumps(
            {
                "summary": {
                    "multi_window_cost_turnover_passed": False,
                    "decision": "churn_cost_not_cleared",
                    "blockers": ["negative_delta_final_value_after_costs"],
                }
            }
        ),
        encoding="utf-8",
    )
    regime_decay.write_text(
        json.dumps(
            {
                "summary": {
                    "temporal_regime_stability_passed": False,
                    "decision": "temporal_regime_stability_not_cleared",
                    "blockers": ["unstable_auxiliary_task_slices"],
                }
            }
        ),
        encoding="utf-8",
    )
    blueprint.write_text(
        json.dumps({"training_allowed": False, "promotion_allowed": False, "decision": {"decision": "blocked"}}),
        encoding="utf-8",
    )
    lifecycle.write_text(
        json.dumps(
            {
                "summary": {
                    "head_lifecycle_passed": False,
                    "decision": "head_lifecycle_review_required",
                    "blockers": ["head_lifecycle_review_required"],
                }
            }
        ),
        encoding="utf-8",
    )
    delayed_credit.write_text(
        json.dumps(
            {
                "summary": {
                    "delayed_credit_passed": False,
                    "decision": "delayed_credit_alignment_not_cleared",
                    "blockers": ["delayed_credit_alignment_failed"],
                }
            }
        ),
        encoding="utf-8",
    )

    report = module.build_report(
        [("00631L.TW", panel)],
        [],
        policy_lift_path=policy_lift,
        purged_wf_path=purged_wf,
        churn_shadow_path=churn_shadow,
        regime_decay_path=regime_decay,
        candidate_bank_blueprint_path=blueprint,
        lifecycle_audit_path=lifecycle,
        delayed_credit_path=delayed_credit,
        min_resolved_rows=20,
        min_positive_rows=10,
        min_auc=0.55,
    )

    assert report["checks"]["downstream_policy_lift_validated"] is False
    assert report["policy_lift_shadow"]["best_variant"] == "net_derisk"
    assert report["policy_lift_shadow"]["variants"]["net_derisk"]["joint_pass"] is False
    assert "downstream_policy_lift_validated" in report["decision"]["blockers"]
    assert "purged_walk_forward_policy_impact_passed" in report["decision"]["blockers"]
    assert "multi_window_cost_turnover_passed" in report["decision"]["blockers"]
    assert "temporal_regime_stability_passed" in report["decision"]["blockers"]
    assert "auxiliary_head_lifecycle_passed" in report["decision"]["blockers"]
    assert "delayed_credit_alignment_passed" in report["decision"]["blockers"]


def test_build_report_blocks_weak_auxiliary_tasks_and_stale_signal(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel, separable=False)
    signal = tmp_path / "signal.json"
    signal.write_text(
        json.dumps({"last_close_date": "2026-01-31", "data_freshness": {"status": "degraded_stale"}}),
        encoding="utf-8",
    )

    report = module.build_report(
        [("00631L.TW", panel)],
        [("00631L.TW", signal)],
        min_resolved_rows=20,
        min_positive_rows=10,
        min_auc=0.55,
    )

    assert report["checks"]["aux_head_standalone_quality_passed"] is False
    assert report["checks"]["live_feature_freshness_ok"] is False
    assert "aux_head_standalone_quality_passed" in report["decision"]["blockers"]
    assert "live_feature_freshness_ok" in report["decision"]["blockers"]
    assert report["weak_tasks"]


def test_write_markdown_renders_panel_metrics(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    _write_panel(panel)
    report = module.build_report(
        [("0050.TW", panel)],
        [],
        min_resolved_rows=20,
        min_positive_rows=10,
        min_auc=0.55,
    )
    markdown = tmp_path / "review.md"

    module.write_markdown(report, markdown)

    text = markdown.read_text(encoding="utf-8")
    assert "2608.15841 Auxiliary Task Discovery Readiness" in text
    assert "0050.TW" in text
    assert "h20_forward_drawdown_gt5" in text
