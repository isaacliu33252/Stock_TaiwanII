from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_synthetic_augmentation_validation_audit import build_audit, write_audit


def test_build_audit_runs_size_matched_null_block_permutation(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    rows = []
    for i in range(80):
        label = 1 if i % 4 == 0 else 0
        rows.append(
            {
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "prob_fwd_gain_gt5_h20": 0.9 if label else 0.1,
                "actual_fwd_gain_gt5_h20": label,
                "prob_fwd_mdd_gt5_h20": 0.2 + (0.01 * (i % 5)),
                "actual_fwd_mdd_gt5_h20": 1 if i % 5 == 0 else 0,
                "ensemble_prob_up": 0.85 if label else 0.15,
                "actual_up_h20": label,
                "is_live": False,
            }
        )
    pd.DataFrame(rows).to_csv(panel, index=False)

    audit = build_audit(panel_path=panel, n_permutations=50, block_size=4, seed=7, as_of="2026-07-20")

    assert audit["report_type"] == "group_a_plus_synthetic_augmentation_validation_audit"
    assert audit["method"]["size_matched_null_augmentation_implemented"] is True
    assert audit["method"]["block_permutation_test_implemented"] is True
    assert audit["as_of"] == "2026-07-20"
    assert audit["panel_coverage"]["row_count"] == 80
    assert len(audit["tasks"]) == 3
    assert audit["tasks"][0]["n_permutations"] == 50
    assert audit["tasks"][0]["block_permutation_p_value"] is not None
    assert audit["summary"]["directional_synthetic_alpha_tested"] is True
    assert audit["decision"]["allow_00631l_add"] is False


def test_build_audit_blocks_directional_when_label_missing(tmp_path: Path) -> None:
    panel = tmp_path / "panel.csv"
    pd.DataFrame(
        [
            {
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "prob_fwd_gain_gt5_h20": 0.7,
                "actual_fwd_gain_gt5_h20": 1 if i % 3 == 0 else 0,
                "prob_fwd_mdd_gt5_h20": 0.6,
                "actual_fwd_mdd_gt5_h20": 1 if i % 4 == 0 else 0,
                "ensemble_prob_up": 0.55,
                "is_live": False,
            }
            for i in range(80)
        ]
    ).to_csv(panel, index=False)

    audit = build_audit(panel_path=panel, n_permutations=20, block_size=4, seed=9)

    directional = audit["tasks"][0]
    assert directional["task"] == "directional_up_ensemble"
    assert directional["passed"] is False
    assert directional["skipped_reason"] == "missing_actual_up_horizon_label"
    assert audit["summary"]["directional_synthetic_alpha_tested"] is False
    assert audit["decision"]["directional_synthetic_alpha_allowed"] is False


def test_write_audit_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"
    history = tmp_path / "history"
    audit = {
        "report_type": "group_a_plus_synthetic_augmentation_validation_audit",
        "as_of": "2026-07-20",
    }

    write_audit(audit, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == audit
    assert json.loads((history / "20260720.json").read_text(encoding="utf-8")) == audit
