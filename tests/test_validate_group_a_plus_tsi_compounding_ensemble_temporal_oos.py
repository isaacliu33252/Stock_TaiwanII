from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.validate_group_a_plus_tsi_compounding_ensemble_temporal_oos import (
    _parse_folds,
    build_temporal_oos_validation,
    write_report,
)


def _window(label: str, final_value: float, mdd: float = 0.0) -> dict:
    return {
        "label": label,
        "ensemble_delta_vs_compounding": {
            "final_value": final_value,
            "sharpe_ratio": final_value / 1000.0,
            "max_drawdown": mdd,
        },
    }


def test_parse_folds_splits_train_and_holdout_labels() -> None:
    folds = _parse_folds("f1:a,b|c,d")

    assert folds == [{"name": "f1", "train_labels": ["a", "b"], "holdout_labels": ["c", "d"]}]


def test_temporal_oos_selects_train_best_and_passes_holdout() -> None:
    sweep = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_sweep",
        "combo_windows": [
            {
                "threshold": 0.75,
                "tsi_trend_cap": 0.0,
                "windows": [_window("train", 100.0), _window("holdout", 50.0)],
            },
            {
                "threshold": 0.9,
                "tsi_trend_cap": 0.5,
                "windows": [_window("train", 10.0), _window("holdout", 500.0)],
            },
        ],
    }

    report = build_temporal_oos_validation(sweep, [{"name": "fold", "train_labels": ["train"], "holdout_labels": ["holdout"]}])

    assert report["folds"][0]["selected_by_train"]["threshold"] == 0.75
    assert report["folds"][0]["temporal_oos_passed"] is True
    assert report["decision"]["temporal_oos_passed"] is True


def test_temporal_oos_blocks_failed_holdout() -> None:
    sweep = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_sweep",
        "combo_windows": [
            {
                "threshold": 0.75,
                "tsi_trend_cap": 0.0,
                "windows": [_window("train", 100.0), _window("holdout", -5.0)],
            }
        ],
    }

    report = build_temporal_oos_validation(sweep, [{"name": "fold", "train_labels": ["train"], "holdout_labels": ["holdout"]}])

    assert report["folds"][0]["temporal_oos_passed"] is False
    assert "temporal_oos_fold_failed:fold" in report["blocking_reasons"]


def test_write_report_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    payload = {
        "report_type": "group_a_plus_tsi_compounding_ensemble_temporal_oos",
        "folds": [],
        "blocking_reasons": ["research_only_no_live_weight_change"],
        "decision": {"temporal_oos_passed": True, "promotion_allowed": False},
    }
    output = tmp_path / "latest" / "temporal.json"
    output_md = tmp_path / "latest" / "temporal.md"
    history = tmp_path / "history"

    write_report(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_tsi_compounding_ensemble_temporal_oos"
    assert "TSI Compounding Ensemble Temporal OOS" in output_md.read_text(encoding="utf-8")
    assert list(history.glob("tsi_compounding_ensemble_temporal_oos_*.json"))
