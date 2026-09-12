from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_daily_semantic_context_summary import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_daily_semantic_context_report_from_files(tmp_path: Path) -> None:
    live = _write(
        tmp_path / "live.json",
        {"success": True, "data": {"actual_data_date": "2026-08-07", "execution_allowed": False}},
    )
    empty = _write(tmp_path / "empty.json", {})

    report = build_report(
        live_signal_path=live,
        signal_alignment_path=empty,
        risk_mechanism_path=empty,
        watchlist_news_path=empty,
        credit_path=empty,
        execution_path=empty,
        thesis_path=empty,
        critic_path=empty,
        as_of="2026-08-07",
    )

    assert report["as_of"] == "2026-08-07"
    assert "execution_guard_false" in report["compressed_takeaways"]["hard_blockers"]
    assert report["sources"]["live_signal"] == str(live)
    assert report["decision"]["creates_orders"] is False


def test_write_daily_semantic_context_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "summary.json"
    history = tmp_path / "history"
    log = tmp_path / "summary.jsonl"
    report = {
        "as_of": "2026-08-07",
        "market_context": {},
        "moira_shadow_context": {},
        "compressed_takeaways": {"hard_blockers": []},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "daily_semantic_context_summary_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
