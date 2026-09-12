from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2604_11335_tail_dependence_trend_review import (
    build_review,
    render_markdown,
    write_review,
)
from scripts.evaluate.sweep_group_a_plus_2604_11335_tail_dependence_trend_robustness import (
    build_sweep,
    render_markdown as render_robustness_markdown,
    write_sweep,
)
from scripts.evaluate.evaluate_group_a_plus_2604_11335_tail_dependence_window_split import (
    build_window_split,
    render_markdown as render_window_split_markdown,
)
from scripts.evaluate.evaluate_group_a_plus_2604_11335_00679b_tail_break_alert import (
    build_alert,
    render_markdown as render_tail_break_markdown,
    write_outputs as write_tail_break_outputs,
)


def _seed_db(path: Path) -> None:
    idx = pd.bdate_range("2025-01-01", periods=120)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00632R.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(idx):
        base_ret = -0.03 if i % 8 == 0 else 0.002
        asset_rets = {
            "0050.TW": base_ret,
            "00631L.TW": -0.06 if base_ret < 0 else 0.004,
            "00632R.TW": 0.03 if base_ret < 0 else -0.002,
            "00679B.TWO": -0.01 if i > 90 and base_ret < 0 else 0.0005,
        }
        for ticker, ret in asset_rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _seed_db_with_00679b_tail_break(path: Path) -> None:
    idx = pd.bdate_range("2025-01-01", periods=180)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00632R.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(idx):
        base_ret = -0.03 if i % 8 == 0 else 0.002
        if i >= 115 and base_ret < 0:
            bond_ret = -0.025
        elif i < 115 and i % 4 == 2:
            bond_ret = -0.025
        else:
            bond_ret = 0.0005
        asset_rets = {
            "0050.TW": base_ret,
            "00631L.TW": -0.06 if base_ret < 0 else 0.004,
            "00632R.TW": 0.03 if base_ret < 0 else -0.002,
            "00679B.TWO": bond_ret,
        }
        for ticker, ret in asset_rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def test_tail_dependence_trend_review_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2604.11335.pdf"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)

    review = build_review(
        pdf_path=pdf,
        db_path=db,
        start="2025-01-01",
        end="2025-06-30",
        window=40,
        alpha=0.20,
        high_tail_dependence_threshold=0.60,
    )

    assert review["report_type"] == "group_a_plus_2604_11335_tail_dependence_trend_review"
    assert review["status"] == "available_for_shadow_monitoring"
    assert review["decision"]["best_import"] == "shadow_tail_dependence_trend_diagnostic_only"
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add_from_tail_dependence"] is False
    assert review["decision"]["allow_00632r_open_from_tail_dependence"] is False
    assert "00631l_lower_tail_dependence_high_vs_0050" in review["warning_reasons"]


def test_tail_dependence_trend_review_blocks_missing_inputs(tmp_path: Path) -> None:
    review = build_review(
        pdf_path=tmp_path / "missing.pdf",
        db_path=tmp_path / "missing.db",
        end="2026-08-28",
        window=40,
    )

    assert review["status"] == "blocked"
    assert "source_pdf_missing" in review["blocking_reasons"]
    assert "stock_database_missing" in review["blocking_reasons"]
    assert review["decision"]["target_weight_change_allowed"] is False


def test_render_and_write_tail_dependence_trend_review(tmp_path: Path) -> None:
    review = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_monitoring",
        "latest": {"pairs": [{"asset": "00631L.TW", "lower_tail_dependence_proxy": 1.0, "co_exceedance_days": 8, "linear_correlation": 0.9}]},
        "trend_summary": {
            "00631L.TW": {
                "latest_lower_tail_dependence_proxy": 1.0,
                "long_run_mean": 0.9,
                "recent_minus_prior": 0.1,
                "linear_trend_per_snapshot": 0.001,
            }
        },
        "alerts": {"high_latest_assets": ["00631L.TW"], "recent_tail_dependence_rising_assets": []},
        "warning_reasons": ["00631l_lower_tail_dependence_high_vs_0050"],
        "parameters": {"end": "2026-08-28"},
    }

    markdown = render_markdown(review)
    assert "2604.11335 Tail Dependence Trend Review" in markdown
    assert "00631L.TW" in markdown

    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"
    write_review(review, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert "Trend Summary" in output_md.read_text(encoding="utf-8")
    assert (history / "2604_11335_tail_dependence_trend_review_20260828.json").exists()


def test_tail_dependence_trend_robustness_sweep(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2604.11335.pdf"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)

    payload = build_sweep(
        pdf_path=pdf,
        db_path=db,
        start="2025-01-01",
        end="2025-06-30",
        alphas=(0.10, 0.20),
        windows=(40, 60),
        high_tail_dependence_threshold=0.60,
    )

    assert payload["report_type"] == "group_a_plus_2604_11335_tail_dependence_trend_robustness"
    assert payload["summary"]["valid_runs"] == 4
    assert payload["summary"]["high_00631l_runs"] == 4
    assert payload["summary"]["00631l_high_tail_dependence_robust"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00632r_open_from_tail_dependence"] is False

    markdown = render_robustness_markdown(payload)
    assert "Tail Dependence Trend Robustness" in markdown
    assert "Robust high `00631L.TW` tail dependence: `True`" in markdown


def test_write_tail_dependence_trend_robustness_sweep(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_monitoring",
        "summary": {
            "valid_runs": 1,
            "high_00631l_runs": 1,
            "00631l_high_tail_dependence_robust": True,
            "00631l_recent_rising_robust": False,
        },
        "decision": {"promote_to_live": False},
        "rows": [],
        "parameters": {"end": "2026-08-28"},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_sweep(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert "Robustness" in output_md.read_text(encoding="utf-8")
    assert (history / "2604_11335_tail_dependence_trend_robustness_20260828.json").exists()


def test_tail_dependence_window_split_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db(db)

    payload = build_window_split(
        db_path=db,
        alpha=0.20,
        high_tail_dependence_threshold=0.60,
        windows=(
            ("first", "2025-01-01", "2025-03-31"),
            ("second", "2025-04-01", "2025-06-30"),
        ),
    )

    assert payload["report_type"] == "group_a_plus_2604_11335_tail_dependence_window_split"
    assert payload["status"] == "available_for_shadow_monitoring"
    assert payload["summary"]["valid_windows"] == 2
    assert payload["summary"]["00631l_high_tail_dependence_all_windows"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00632r_open_from_tail_dependence"] is False

    markdown = render_window_split_markdown(payload)
    assert "Tail Dependence Window Split" in markdown
    assert "00631L.TW" in markdown


def test_00679b_tail_break_alert_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    _seed_db_with_00679b_tail_break(db)

    payload = build_alert(
        db_path=db,
        start="2025-01-01",
        end="2025-09-30",
        window=40,
        alpha=0.10,
        recent_snapshots=20,
        elevated_threshold=0.30,
        break_delta_threshold=0.20,
    )

    assert payload["report_type"] == "group_a_plus_2604_11335_00679b_tail_break_alert"
    assert payload["status"] == "available_for_shadow_monitoring"
    assert payload["summary"]["break_alert"] is True
    assert payload["decision"]["tail_break_alert_active"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00679b_add_from_tail_dependence"] is False
    assert "00679b_tail_dependence_break_alert" in payload["warning_reasons"]

    markdown = render_tail_break_markdown(payload)
    assert "00679B Tail-Dependence Break Alert" in markdown
    assert "Shadow diagnostic only" in markdown


def test_write_00679b_tail_break_alert_outputs(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_monitoring",
        "parameters": {"end": "2026-08-28", "asset": "00679B.TWO", "base": "0050.TW"},
        "summary": {
            "latest_lower_tail_dependence_proxy": 0.1,
            "baseline_mean": 0.1,
            "recent_mean": 0.1,
            "latest_minus_baseline": 0.0,
            "recent_minus_baseline": 0.0,
        },
        "decision": {"tail_break_alert_active": False},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_tail_break_outputs(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert "00679B Tail-Dependence Break Alert" in output_md.read_text(encoding="utf-8")
    assert (history / "2604_11335_00679b_tail_break_alert_20260828.json").exists()
