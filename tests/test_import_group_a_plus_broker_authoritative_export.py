from __future__ import annotations

from pathlib import Path

from scripts.evaluate.import_group_a_plus_broker_authoritative_export import build_authoritative_sample


HEADER = "as_of_date,account_id_or_alias,ticker,shares,market_value,cash_balance,currency,source_file_name,export_generated_at\n"


def _write(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def test_complete_broker_export_builds_authoritative_sample(tmp_path: Path) -> None:
    csv_path = _write(
        tmp_path / "broker.csv",
        [
            "2026-08-24,main,0050.TW,2794,290000,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
            "2026-08-24,main,00631L.TW,500,17000,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
            "2026-08-24,main,00632R.TW,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
            "2026-08-24,main,00679B.TWO,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
            "2026-08-24,main,00751B.TWO,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
            "2026-08-24,main,cash,0,0,100000,TWD,broker.csv,2026-08-24T15:00:00\n",
        ],
    )

    sample = build_authoritative_sample(csv_path)

    assert sample["status"] == "authoritative_sample_ready"
    assert sample["authoritative_broker_export"] is True
    assert sample["cash_balance"] == 100000.0
    assert sample["latest_positions"]["0050.TW"] == 2794
    assert sample["negative_positions"] == {}
    assert sample["decision"]["can_feed_reconciliation"] is True
    assert sample["decision"]["creates_orders"] is False


def test_incomplete_template_is_invalid_and_not_authoritative(tmp_path: Path) -> None:
    csv_path = _write(
        tmp_path / "template.csv",
        [
            ",,0050.TW,,,,,,\n",
            ",,00631L.TW,,,,,,\n",
        ],
    )

    sample = build_authoritative_sample(csv_path)

    assert sample["status"] == "invalid"
    assert sample["authoritative_broker_export"] is False
    assert "as_of_date_missing" in sample["errors"]
    assert "cash_balance_missing" in sample["errors"]
    assert "group_a_plus_tickers_missing" in sample["errors"]
    assert sample["decision"]["can_feed_reconciliation"] is False
