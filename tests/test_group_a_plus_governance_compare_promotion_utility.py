from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.governance.compare import compare_candidates


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_promotion_utility_defaults_to_final_value_delta_only(tmp_path: Path) -> None:
    """2026-08-01: lambda_starr/lambda_es default to 0.0 so promotion_utility is a
    no-op advisory field until someone deliberately calibrates non-zero weights --
    same posture as w6_credit and --use-calibration-model elsewhere in this repo."""
    baseline = _write_json(
        tmp_path / "baseline.json",
        {
            "metrics": {
                "final_value": 100.0,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.20,
                "starr_95": 0.4,
                "expected_shortfall_loss_95": 0.08,
            }
        },
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "tail_risk_candidate",
            "rows": [
                {
                    "variant": "candidate_a",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.1,
                    "max_drawdown": -0.19,
                    "override_days": 2,
                    "starr_95": 0.5,
                    "expected_shortfall_loss_95": 0.10,
                }
            ],
        },
    )

    report = compare_candidates(baseline, [candidate])
    row = report["rows"][0]

    assert row["promotion_utility"] == row["delta_final"]
    assert row["promotion_utility_equals_final_value_delta"] is True
    assert row["promotion_utility_components_used"] == ["final_value_delta"]
    # deltas are still reported for observation even though the weights are 0.0
    assert row["promotion_utility_starr_delta"] is not None
    assert row["promotion_utility_expected_shortfall_delta"] is not None


def test_promotion_utility_with_nonzero_weights_combines_starr_and_es(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {
            "metrics": {
                "final_value": 100.0,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.20,
                "starr_95": 0.4,
                "expected_shortfall_loss_95": 0.08,
                "transaction_cost": 1.0,
            }
        },
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "tail_risk_candidate",
            "rows": [
                {
                    "variant": "candidate_b",
                    "final_value": 110.0,
                    "sharpe_ratio": 1.1,
                    "max_drawdown": -0.19,
                    "override_days": 2,
                    "starr_95": 0.5,
                    "expected_shortfall_loss_95": 0.12,
                    "transaction_cost": 1.5,
                }
            ],
        },
    )

    report = compare_candidates(
        baseline, [candidate], tail_risk_lambda_starr=2.0, tail_risk_lambda_es=3.0
    )
    row = report["rows"][0]

    final_value_delta = 110.0 - 100.0
    starr_delta = 0.5 - 0.4
    es_delta = 0.12 - 0.08
    transaction_cost_delta = 1.5 - 1.0
    expected = final_value_delta + 2.0 * starr_delta - 3.0 * max(0.0, es_delta) - transaction_cost_delta

    assert row["promotion_utility"] == expected
    assert row["promotion_utility_equals_final_value_delta"] is False
    assert set(row["promotion_utility_components_used"]) == {
        "final_value_delta",
        "starr_delta",
        "expected_shortfall_delta",
        "transaction_cost_delta",
    }


def test_promotion_utility_es_improvement_is_not_penalized(tmp_path: Path) -> None:
    """A candidate with LOWER expected shortfall than baseline (an improvement)
    must not be penalized -- only max(0, es_delta) enters the formula."""
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20, "expected_shortfall_loss_95": 0.10}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "tail_risk_candidate",
            "rows": [
                {
                    "variant": "safer_candidate",
                    "final_value": 105.0,
                    "sharpe_ratio": 1.05,
                    "max_drawdown": -0.19,
                    "override_days": 2,
                    "expected_shortfall_loss_95": 0.05,
                }
            ],
        },
    )

    report = compare_candidates(baseline, [candidate], tail_risk_lambda_es=5.0)
    row = report["rows"][0]

    assert row["promotion_utility"] == 5.0  # final_value_delta only, ES term clipped to 0
    assert row["promotion_utility_expected_shortfall_delta"] == -0.05


def test_promotion_utility_missing_metrics_are_reported_as_none(tmp_path: Path) -> None:
    baseline = _write_json(
        tmp_path / "baseline.json",
        {"metrics": {"final_value": 100.0, "sharpe_ratio": 1.0, "max_drawdown": -0.20}},
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "experiment": "no_tail_metrics",
            "rows": [
                {
                    "variant": "plain_candidate",
                    "final_value": 101.0,
                    "sharpe_ratio": 1.0,
                    "max_drawdown": -0.20,
                    "override_days": 1,
                }
            ],
        },
    )

    report = compare_candidates(baseline, [candidate], tail_risk_lambda_starr=1.0, tail_risk_lambda_es=1.0)
    row = report["rows"][0]

    assert row["promotion_utility_starr_delta"] is None
    assert row["promotion_utility_expected_shortfall_delta"] is None
    assert row["promotion_utility_transaction_cost_delta"] is None
    assert row["promotion_utility"] == row["delta_final"]
    assert row["tail_risk_metrics"]["starr_95"] is None
