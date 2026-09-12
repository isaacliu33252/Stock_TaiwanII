from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_relative_exposure_thesis_shadow import build_report, write_report


def test_build_relative_exposure_report_from_wrapped_signal(tmp_path: Path) -> None:
    live = tmp_path / "live.json"
    live.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    "actual_data_date": "2026-08-07",
                    "execution_allowed": False,
                    "execution_regime": "golden1",
                    "target_weights": {"0050.TW": 0.3, "00632R.TW": 0.27, "cash": 0.43},
                    "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report(live_signal_path=live)

    assert report["as_of"] == "2026-08-07"
    assert report["thesis_class"] == "short_term_inverse_hedge_review_only"
    assert report["decision"]["auto_rebalance_allowed"] is False


def test_write_relative_exposure_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "relative.json"
    history = tmp_path / "history"
    log = tmp_path / "relative.jsonl"
    report = {
        "as_of": "2026-08-07",
        "thesis_class": "maintain_unlevered_beta_preferred",
        "thesis_quality_score": 0.55,
        "reason_codes": [],
        "supporting_evidence": [],
        "blocking_evidence": [],
        "inputs": {},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "relative_exposure_thesis_shadow_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
