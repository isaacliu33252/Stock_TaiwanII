from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate.build_group_a_plus_2602_24037_scr_readiness_review import (
    build_review,
    render_markdown,
    write_review,
)
from scripts.evaluate.sweep_group_a_plus_2602_24037_scr_readiness_robustness import (
    build_sweep,
    render_markdown as render_sweep_markdown,
    write_sweep,
)
from scripts.evaluate.evaluate_group_a_plus_2602_24037_scr_readiness_window_split import (
    build_window_split,
    render_markdown as render_window_split_markdown,
    write_outputs as write_window_split_outputs,
)
from scripts.evaluate.build_group_a_plus_2602_24037_scr_scenario_stress_score import (
    build_score,
    render_markdown as render_score_markdown,
    write_score,
)


def _seed_db(path: Path) -> None:
    idx = pd.bdate_range("2023-01-02", periods=260)
    prices = {"0050.TW": 100.0, "00631L.TW": 100.0, "00632R.TW": 100.0, "00679B.TWO": 100.0}
    rows = []
    for i, dt in enumerate(idx):
        shock = i % 25 == 0
        base_ret = -0.025 if shock else 0.001 + ((i % 7) - 3) * 0.0005
        rets = {
            "0050.TW": base_ret,
            "00631L.TW": base_ret * 1.9,
            "00632R.TW": -base_ret * 0.9,
            "00679B.TWO": -0.002 if shock else 0.0002,
        }
        for ticker, ret in rets.items():
            prices[ticker] *= 1.0 + ret
            rows.append({"dt": str(dt.date()), "ticker": ticker, "close": prices[ticker]})
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE ohlcv (dt DATE, ticker VARCHAR, close DOUBLE)")
        con.register("rows", pd.DataFrame(rows))
        con.execute("INSERT INTO ohlcv SELECT * FROM rows")
    finally:
        con.close()


def _seed_live_signal(path: Path) -> None:
    payload = {
        "data": {
            "target_weights": {
                "0050.TW": 0.47,
                "00631L.TW": 0.10,
                "00632R.TW": 0.16,
                "00679B.TWO": 0.0,
                "cash": 0.27,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_scr_readiness_review_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2602.24037.pdf"
    live = tmp_path / "live_signal.json"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)
    _seed_live_signal(live)

    review = build_review(
        pdf_path=pdf,
        db_path=db,
        live_signal_path=live,
        start="2023-01-02",
        end="2023-12-29",
        eval_start="2023-08-01",
        min_history=80,
        k_neighbors=10,
        gap_limit=0.05,
    )

    assert review["report_type"] == "group_a_plus_2602_24037_scr_readiness_review"
    assert review["status"] == "available_for_shadow_review"
    assert review["summary"]["oos_days"] > 0
    assert review["decision"]["best_import"] == "scr_readiness_and_mismatch_guard_only"
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["model_training_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["decision"]["allow_00632r_open"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True

    markdown = render_markdown(review)
    assert "SCR Readiness Review" in markdown
    assert "Scenario-To-Real Audit" in markdown


def test_scr_readiness_review_blocks_missing_inputs(tmp_path: Path) -> None:
    review = build_review(
        pdf_path=tmp_path / "missing.pdf",
        db_path=tmp_path / "missing.db",
        live_signal_path=tmp_path / "missing_live.json",
        end="2026-08-28",
        min_history=80,
    )

    assert review["status"] == "blocked_for_live_promotion"
    assert "source_pdf_missing" in review["blocking_reasons"]
    assert "stock_database_missing" in review["blocking_reasons"]
    assert review["decision"]["ppo_training_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_write_scr_readiness_review_outputs(tmp_path: Path) -> None:
    review = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_review",
        "parameters": {"end": "2026-08-28"},
        "summary": {
            "oos_days": 10,
            "mean_abs_scenario_real_gap": 0.01,
            "median_abs_scenario_real_gap": 0.01,
            "p90_abs_scenario_real_gap": 0.02,
            "mean_scenario_variance": 0.0001,
            "beta_cf_from_bias_variance_proxy": 0.5,
            "scenario_real_gap_gate_passed": True,
        },
        "decision": {},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_review(review, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert "SCR Readiness Review" in output_md.read_text(encoding="utf-8")
    assert (history / "2602_24037_scr_readiness_review_20260828.json").exists()


def test_scr_readiness_robustness_sweep_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2602.24037.pdf"
    live = tmp_path / "live_signal.json"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)
    _seed_live_signal(live)

    payload = build_sweep(
        pdf_path=pdf,
        db_path=db,
        live_signal_path=live,
        start="2023-01-02",
        end="2023-12-29",
        eval_starts=("2023-07-03", "2023-08-01"),
        min_histories=(80,),
        k_neighbors_values=(5, 10),
        gap_limit=0.05,
    )

    assert payload["report_type"] == "group_a_plus_2602_24037_scr_readiness_robustness"
    assert payload["summary"]["total_runs"] == 4
    assert payload["summary"]["valid_runs"] == 4
    assert payload["decision"]["scr_shadow_training_allowed_by_this_sweep"] is False
    assert payload["decision"]["ppo_training_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["keep_golden1_0531_unchanged"] is True

    markdown = render_sweep_markdown(payload)
    assert "SCR Readiness Robustness" in markdown
    assert "Beta cf range" in markdown


def test_write_scr_readiness_robustness_sweep_outputs(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_review",
        "summary": {
            "total_runs": 1,
            "valid_runs": 1,
            "gap_gate_pass_runs": 1,
            "beta_moderate_runs": 0,
            "mean_gap_min": 0.01,
            "mean_gap_max": 0.01,
            "beta_cf_min": 0.8,
            "beta_cf_max": 0.8,
            "gap_readiness_robust": True,
            "beta_cf_moderate_robust": False,
        },
        "rows": [],
        "decision": {"promote_to_live": False},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_sweep(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert "SCR Readiness Robustness" in output_md.read_text(encoding="utf-8")
    assert (history / "2602_24037_scr_readiness_robustness_20260828.json").exists()


def test_scr_readiness_window_split_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2602.24037.pdf"
    live = tmp_path / "live_signal.json"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)
    _seed_live_signal(live)

    payload = build_window_split(
        pdf_path=pdf,
        db_path=db,
        live_signal_path=live,
        data_start="2023-01-02",
        end="2023-12-29",
        windows=(
            ("first", "2023-07-03", "2023-09-29"),
            ("second", "2023-10-02", "2023-12-15"),
        ),
        min_history=80,
        k_neighbors=10,
        gap_limit=0.05,
    )

    assert payload["report_type"] == "group_a_plus_2602_24037_scr_readiness_window_split"
    assert payload["status"] == "available_for_shadow_review"
    assert payload["summary"]["valid_windows"] == 2
    assert payload["decision"]["scr_shadow_training_allowed_by_this_window_split"] is False
    assert payload["decision"]["ppo_training_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["keep_golden1_0531_unchanged"] is True

    markdown = render_window_split_markdown(payload)
    assert "SCR Readiness Window Split" in markdown
    assert "Stress gap readiness passed" in markdown


def test_write_scr_readiness_window_split_outputs(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_review",
        "parameters": {"end": "2026-08-28"},
        "summary": {
            "valid_windows": 1,
            "gap_gate_pass_windows": 1,
            "beta_moderate_windows": 0,
            "mean_gap_min": 0.01,
            "mean_gap_max": 0.01,
            "beta_cf_min": 0.8,
            "beta_cf_max": 0.8,
            "stress_gap_readiness_passed": True,
            "stress_beta_cf_moderate_passed": False,
        },
        "rows": [],
        "decision": {"promote_to_live": False},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_window_split_outputs(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert "SCR Readiness Window Split" in output_md.read_text(encoding="utf-8")
    assert (history / "2602_24037_scr_readiness_window_split_20260828.json").exists()


def test_scr_scenario_stress_score_is_shadow_only(tmp_path: Path) -> None:
    db = tmp_path / "stock.db"
    pdf = tmp_path / "2602.24037.pdf"
    live = tmp_path / "live_signal.json"
    pdf.write_bytes(b"%PDF")
    _seed_db(db)
    _seed_live_signal(live)

    payload = build_score(
        pdf_path=pdf,
        db_path=db,
        live_signal_path=live,
        start="2023-01-02",
        end="2023-12-29",
        min_history=80,
        k_neighbors=10,
        warning_es_threshold=-0.05,
    )

    assert payload["report_type"] == "group_a_plus_2602_24037_scr_scenario_stress_score"
    assert payload["status"] == "available_for_shadow_monitoring"
    assert payload["summary"]["scenario_count"] > 0
    assert payload["decision"]["best_import"] == "latest_scr_scenario_downside_stress_score_only"
    assert payload["decision"]["creates_orders"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["auto_rebalance_allowed"] is False
    assert payload["decision"]["scr_shadow_training_allowed_by_this_score"] is False
    assert payload["decision"]["ppo_training_allowed"] is False
    assert payload["decision"]["model_training_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert payload["decision"]["keep_golden1_0531_unchanged"] is True

    markdown = render_score_markdown(payload)
    assert "SCR Scenario Stress Score" in markdown
    assert "Downside warning active" in markdown


def test_write_scr_scenario_stress_score_outputs(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-30T00:00:00",
        "status": "available_for_shadow_monitoring",
        "parameters": {"end": "2026-08-28"},
        "scenario_context": {"as_of": "2026-08-28"},
        "summary": {
            "scenario_count": 10,
            "mean_next_return": 0.001,
            "median_next_return": 0.001,
            "p10_next_return": -0.01,
            "var_next_return": -0.02,
            "es_next_return": -0.03,
            "probability_loss": 0.4,
            "downside_warning_active": True,
        },
        "decision": {"promote_to_live": False},
    }
    output = tmp_path / "latest.json"
    output_md = tmp_path / "latest.md"
    history = tmp_path / "history"

    write_score(payload, output, output_md, history)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert "SCR Scenario Stress Score" in output_md.read_text(encoding="utf-8")
    assert (history / "2602_24037_scr_scenario_stress_score_20260828.json").exists()
