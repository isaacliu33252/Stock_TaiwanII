from __future__ import annotations

import json
from pathlib import Path

from scripts.run.run_group_a_plus_broker_export_reconciliation import run_broker_export_reconciliation


HEADER = "as_of_date,account_id_or_alias,ticker,shares,market_value,cash_balance,currency,source_file_name,export_generated_at\n"


def _write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def _valid_rows() -> list[str]:
    return [
        "2026-08-24,main,0050.TW,2794,290000,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        "2026-08-24,main,00631L.TW,500,17000,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        "2026-08-24,main,00632R.TW,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        "2026-08-24,main,00679B.TWO,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        "2026-08-24,main,00751B.TWO,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        "2026-08-24,main,cash,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
    ]


def test_invalid_export_stops_before_live_sample(tmp_path: Path) -> None:
    input_path = _write_csv(tmp_path / "broker.csv", [",,0050.TW,,,,,,\n"])
    live_sample = tmp_path / "live_sample.json"

    result = run_broker_export_reconciliation(
        input_path=input_path,
        staging_output=tmp_path / "staging.json",
        live_sample_output=live_sample,
        reconciliation_output=tmp_path / "reconciliation.json",
        apply=True,
    )

    assert result["status"] == "blocked_invalid_broker_export"
    assert result["applied_to_live_sample"] is False
    assert not live_sample.exists()


def test_valid_export_staging_does_not_apply(tmp_path: Path) -> None:
    input_path = _write_csv(tmp_path / "broker.csv", _valid_rows())
    live_sample = tmp_path / "live_sample.json"

    result = run_broker_export_reconciliation(
        input_path=input_path,
        staging_output=tmp_path / "staging.json",
        live_sample_output=live_sample,
        reconciliation_output=tmp_path / "reconciliation.json",
        apply=False,
    )

    assert result["status"] == "staging_ready_apply_required"
    assert result["applied_to_live_sample"] is False
    assert not live_sample.exists()
    assert "--apply" in result["next_commands"][0]


def test_apply_valid_export_writes_reconciled_review(tmp_path: Path) -> None:
    input_path = _write_csv(tmp_path / "broker.csv", _valid_rows())
    live_sample = tmp_path / "live_sample.json"
    reconciliation = tmp_path / "reconciliation.json"

    result = run_broker_export_reconciliation(
        input_path=input_path,
        staging_output=tmp_path / "staging.json",
        live_sample_output=live_sample,
        reconciliation_output=reconciliation,
        apply=True,
    )

    assert result["status"] == "reconciliation_ready"
    assert result["applied_to_live_sample"] is True
    assert result["reconciliation_status"] == "reconciled_for_manual_review"
    assert json.loads(live_sample.read_text(encoding="utf-8"))["authoritative_broker_export"] is True
    review = json.loads(reconciliation.read_text(encoding="utf-8"))
    assert review["blocking_reasons"] == []
    assert review["decision"]["can_generate_live_orders"] is True
