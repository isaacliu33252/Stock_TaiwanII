from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_2605_20636_continuous_timing_review import (
    build_review,
    render_markdown,
    write_review,
)
from scripts.evaluate.evaluate_a2119_continuous_defensive_tilt_shadow import build_continuous_targets
from scripts.evaluate.evaluate_group_a_plus_2605_20636_taiwan_etf_sensitivity import (
    ENDPOINTS,
    WINDOWS,
    build_sensitivity,
)
from scripts.evaluate.sweep_group_a_plus_2605_20636_taiwan_etf_friction_controls import (
    build_sweep,
    render_markdown as render_friction_markdown,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_review_imports_process_only_and_blocks_live_weights(tmp_path: Path) -> None:
    pdf = tmp_path / "2605.20636.pdf"
    pdf.write_bytes(b"%PDF")
    latest = _write_json(
        tmp_path / "latest.json",
        {
            "data": {
                "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
                "requested_as_of_date": "2026-08-31",
                "actual_data_date": "2026-08-28",
                "target_weights": {"0050.TW": 0.47, "00631L.TW": 0.1, "00632R.TW": 0.16, "cash": 0.27},
            }
        },
    )
    checklist = _write(tmp_path / "checklist.md", "Continuous Timing Signals for Growth-Defensive Style Allocation")
    handoff = _write(tmp_path / "handoff.md", "final verdict: do not promote")
    script = _write(tmp_path / "shadow.py", "# shadow")

    review = build_review(
        pdf_path=pdf,
        latest_strategy_path=latest,
        checklist_path=checklist,
        a2119_handoff_path=handoff,
        a2119_script_path=script,
        as_of="2026-08-28",
    )

    assert review["report_type"] == "group_a_plus_2605_20636_continuous_timing_review"
    assert review["status"] == "blocked_for_live_promotion"
    assert review["assessment"]["best_import"] == "validation_checklist_only"
    assert review["assessment"]["strategy_logic_importable"] is False
    assert review["decision"]["process_checklist_already_imported"] is True
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert review["latest_strategy_context"]["target_weights"]["00632R.TW"] == 0.16
    assert review["experiment_scope_decision"]["groupa_plus_importability_complete"] is True
    assert review["experiment_scope_decision"]["full_paper_replication_complete"] is False
    assert review["experiment_scope_decision"]["full_paper_replication_required_for_strategy_decision"] is False


def test_review_records_missing_supporting_artifacts(tmp_path: Path) -> None:
    review = build_review(
        pdf_path=tmp_path / "missing.pdf",
        latest_strategy_path=tmp_path / "missing_latest.json",
        checklist_path=tmp_path / "missing_checklist.md",
        a2119_handoff_path=tmp_path / "missing_handoff.md",
        a2119_script_path=tmp_path / "missing_script.py",
    )

    assert "validation_checklist_not_found" in review["blocking_reasons"]
    assert "a2119_shadow_script_not_found" in review["blocking_reasons"]
    assert "a2119_final_rejection_not_confirmed" in review["blocking_reasons"]
    assert review["decision"]["process_checklist_already_imported"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_render_markdown_contains_decision() -> None:
    review = {
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "latest_strategy_context": {"target_weights": {"0050.TW": 0.47}},
        "decision": {
            "process_checklist_already_imported": True,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "blocking_reasons": ["research_only_review_no_target_weight_change"],
    }

    markdown = render_markdown(review)

    assert "2605.20636 Continuous Timing Review" in markdown
    assert "Do not import the continuous smooth-score allocation" in markdown
    assert "GroupA+ importability experiments: `complete`" in markdown
    assert "`0050.TW`: `0.470000`" in markdown


def test_write_review_writes_latest_markdown_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "review.json"
    output_md = tmp_path / "latest" / "review.md"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_2605_20636_continuous_timing_review",
        "generated_at": "2026-08-29T00:00:00",
        "as_of": "2026-08-28",
        "status": "blocked_for_live_promotion",
        "latest_strategy_context": {"target_weights": {}},
        "decision": {},
        "blocking_reasons": [],
    }

    write_review(review, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert "2605.20636 Continuous Timing Review" in output_md.read_text(encoding="utf-8")
    history_file = history / "2605_20636_continuous_timing_review_20260828.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review


def test_a2119_continuous_targets_accept_custom_defensive_endpoint() -> None:
    dates = pd.bdate_range("2026-01-01", periods=2)
    frame = pd.DataFrame(index=dates)
    tilt_frame = pd.DataFrame({"defensive_tilt": [1.0, 1.0]}, index=dates)
    report = {
        "base_weights": {
            "golden1": {
                "0050.TW": 0.70,
                "00631L.TW": 0.10,
                "00632R.TW": 0.0,
                "00679B.TWO": 0.0,
                "cash": 0.20,
            }
        }
    }

    targets = build_continuous_targets(
        frame,
        tilt_frame,
        report,
        defensive_endpoint={"0050.TW": 0.40, "cash": 0.60},
    )

    assert targets.loc[dates[0], "0050.TW"] == 0.40
    assert targets.loc[dates[0], "00631L.TW"] == 0.0
    assert targets.loc[dates[0], "00679B.TWO"] == 0.0
    assert targets.loc[dates[0], "cash"] == 0.60


def test_taiwan_etf_sensitivity_summarizes_endpoint_results(monkeypatch) -> None:
    def fake_evaluate(**kwargs):
        endpoint = kwargs["defensive_endpoint_name"]
        bonus = {"0050_cash": 100.0, "0050_00679b_cash": -50.0, "0050_00631l_cash": 10.0}[endpoint]
        return {
            "metric_deltas": {
                "final_value": bonus,
                "annual_return": 0.01 if bonus > 0 else -0.01,
                "sharpe_ratio": 0.02 if bonus > 0 else -0.02,
                "sortino_ratio": 0.0,
                "max_drawdown": 0.0 if bonus > 0 else -0.01,
            },
            "baseline_execution": {"turnover": 1.0},
            "continuous_execution": {"turnover": 0.8 if endpoint == "0050_cash" else 1.2},
        }

    monkeypatch.setattr(
        "scripts.evaluate.evaluate_group_a_plus_2605_20636_taiwan_etf_sensitivity.evaluate",
        fake_evaluate,
    )

    payload = build_sensitivity(windows=WINDOWS[:2], endpoints=ENDPOINTS)

    assert payload["decision"]["taiwan_etf_backtest_useful"] is True
    assert payload["best_endpoint"] == "0050_cash"
    assert payload["endpoint_summary"]["0050_cash"]["triple_pass_windows"] == 2
    assert payload["decision"]["target_weight_change_allowed"] is False


def test_friction_control_sweep_blocks_when_best_combo_not_all_window_pass(monkeypatch) -> None:
    def fake_evaluate(**kwargs):
        band = kwargs["no_trade_band"]
        freq = kwargs["tilt_update_freq_days"]
        good_combo = band == 0.02 and freq == 5
        positive = good_combo and kwargs["start"] >= "2022-01-01"
        return {
            "no_trade_band": band,
            "tilt_update_freq_days": freq,
            "metric_deltas": {
                "final_value": 100.0 if positive else -10.0,
                "annual_return": 0.01 if positive else -0.01,
                "sharpe_ratio": 0.02 if positive else -0.02,
                "sortino_ratio": 0.0,
                "max_drawdown": 0.0 if positive else -0.01,
            },
            "baseline_execution": {"turnover_value": 1_000_000, "rebalance_count": 1},
            "continuous_execution": {"turnover_value": 900_000, "rebalance_count": 2},
            "parameters": {"initial_value": 1_000_000.0},
        }

    monkeypatch.setattr(
        "scripts.evaluate.sweep_group_a_plus_2605_20636_taiwan_etf_friction_controls.evaluate",
        fake_evaluate,
    )

    payload = build_sweep(
        windows=(WINDOWS[0], WINDOWS[2]),
        no_trade_bands=(0.005, 0.02),
        tilt_update_freq_days=(1, 5),
    )

    assert payload["best_combo"] == "band0.02_freq5"
    assert payload["combo_summary"]["band0.02_freq5"]["triple_pass_windows"] == 1
    assert payload["failure_diagnosis"]["positive_final_value_windows"] == ["rate_hike_2022"]
    assert "full-history/COVID/2022" in payload["failure_diagnosis"]["primary_reason"]
    assert payload["decision"]["promote_to_live"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False

    markdown = render_friction_markdown(payload)
    assert "Best Combo Window Rows" in markdown
    assert "Failure Diagnosis" in markdown
    assert "| rate_hike_2022 |" in markdown
