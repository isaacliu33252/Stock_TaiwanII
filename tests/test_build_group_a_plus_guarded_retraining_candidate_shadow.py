from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_guarded_retraining_candidate_shadow import build_report


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_guarded_shadow_blocks_inverse_candidate_before_retraining(tmp_path: Path) -> None:
    backtest = _write(
        tmp_path / "backtest.json",
        {
            "summary": {
                "promotion_gate": {
                    "decision": "retrain_candidate",
                    "rationale": "risk improved",
                    "best_return_variant": "GroupA+_plain",
                    "best_risk_variant": "GroupA+_inverse",
                    "variants": [
                        {
                            "variant": "GroupA+_inverse",
                            "retrain_candidate": True,
                            "return_upgrade_candidate": False,
                            "final_drag_pct": -0.1,
                            "sharpe_delta": -0.02,
                            "mdd_improvement": 0.03,
                            "volatility_reduction": 0.03,
                        }
                    ],
                }
            },
            "plus_details": {
                "GroupA+_inverse": {
                    "events": [
                        {
                            "date": "2026-08-04",
                            "target_weights_before_execution": {"00632R.TW": 0.05},
                            "executable_weights": {"00632R.TW": 0.05},
                            "target_report": {"inverse_control": {"enabled": True}},
                        }
                    ]
                }
            },
        },
    )
    inverse_gate = _write(tmp_path / "inverse_gate.json", {"status": "shadow_review", "guard": {"status": "inactive"}})

    report = build_report(backtest_path=backtest, inverse_gate_path=inverse_gate, as_of="2026-08-15")

    assert report["guarded_decision"]["decision"] == "blocked_by_inverse_etf_governance"
    assert report["guarded_decision"]["guarded_retrain_candidates"] == []
    assert report["guarded_decision"]["inverse_blocked_candidates"] == ["GroupA+_inverse"]
    assert report["candidates"][0]["guarded_retraining_allowed"] is False


def test_guarded_shadow_keeps_non_inverse_retrain_candidate(tmp_path: Path) -> None:
    backtest = _write(
        tmp_path / "backtest.json",
        {
            "summary": {
                "promotion_gate": {
                    "decision": "retrain_candidate",
                    "rationale": "risk improved",
                    "best_return_variant": "GroupA+_plain",
                    "best_risk_variant": "GroupA+_plain",
                    "variants": [
                        {
                            "variant": "GroupA+_plain",
                            "retrain_candidate": True,
                            "return_upgrade_candidate": False,
                            "final_drag_pct": -0.1,
                            "sharpe_delta": -0.02,
                            "mdd_improvement": 0.03,
                            "volatility_reduction": 0.03,
                        }
                    ],
                }
            },
            "plus_details": {
                "GroupA+_plain": {
                    "events": [
                        {
                            "date": "2026-08-04",
                            "target_weights_before_execution": {"00632R.TW": 0.0},
                            "executable_weights": {"00632R.TW": 0.0},
                            "target_report": {"inverse_control": {"enabled": False}},
                        }
                    ]
                }
            },
        },
    )
    inverse_gate = _write(tmp_path / "inverse_gate.json", {"status": "shadow_review", "guard": {"status": "inactive"}})

    report = build_report(backtest_path=backtest, inverse_gate_path=inverse_gate, as_of="2026-08-15")

    assert report["guarded_decision"]["decision"] == "guarded_retrain_candidate"
    assert report["guarded_decision"]["guarded_retrain_candidates"] == ["GroupA+_plain"]
    assert report["guarded_decision"]["inverse_blocked_candidates"] == []
