from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_moira_policy_critic_shadow import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_policy_critic_report_from_files(tmp_path: Path) -> None:
    credit = _write(tmp_path / "credit.json", {"as_of": "2026-08-07", "primary_attribution": "data_freshness_error"})
    execution = _write(
        tmp_path / "execution.json",
        {"as_of": "2026-08-07", "quality_score": 0.4, "blockers": ["source_fresh_enough"], "warnings": []},
    )
    thesis = _write(tmp_path / "thesis.json", {"as_of": "2026-08-07", "thesis_class": "maintain_unlevered_beta_preferred"})

    report = build_report(credit_path=credit, execution_path=execution, thesis_path=thesis, as_of="2026-08-07")

    assert report["as_of"] == "2026-08-07"
    assert report["proposal_count"] == 1
    assert report["proposals"][0]["proposal_id"] == "freshness_first_review_gate"
    assert report["sources"]["hierarchical_credit_review"] == str(credit)
    assert report["decision"]["creates_orders"] is False


def test_write_policy_critic_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "critic.json"
    history = tmp_path / "history"
    log = tmp_path / "critic.jsonl"
    report = {
        "as_of": "2026-08-07",
        "status": "research_proposals_available",
        "proposal_count": 1,
        "proposals": [{"proposal_id": "x"}],
        "blocking_reasons": [],
        "warning_reasons": [],
        "inputs_summary": {},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "moira_policy_critic_shadow_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["proposal_ids"] == ["x"]
