from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import os
import shutil
import time
from collections import namedtuple

from group_a_plus.operations.ops_health import (
    build_ops_health,
    collect_external_data_freshness,
    collect_pipeline_health,
    collect_system_resources,
    collect_tsmc_weight_assumption_health,
)


def _today_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_live_signal() -> str:
    return json.dumps(
        {
            "success": True,
            "data": {
                "tbrain_shadow": {"status": "available"},
                "finbert_sentiment": {"status": "ok"},
                "factor_lens_gate": {"status": "available"},
            },
        }
    )


def _live_signal_with_volatility_gate(strategy_id: str = "a2118", actual_data_date: str = "2026-07-09") -> str:
    return json.dumps(
        {
            "success": True,
            "data": {
                "strategy_id": strategy_id,
                "actual_data_date": actual_data_date,
                "signal_alerts": [
                    {
                        "type": "volatility_gate_high_vol",
                        "metadata": {
                            "allow_00631l_add": False,
                            "trade_policy": "advisory_no_auto_weight_change",
                        },
                    }
                ],
                "tbrain_shadow": {"status": "available"},
                "finbert_sentiment": {"status": "ok"},
                "factor_lens_gate": {"status": "available"},
            },
        }
    )


def _execution_plan_with_guard(strategy_id: str = "a2118", actual_data_date: str = "2026-07-09") -> str:
    return json.dumps(
        {
            "success": True,
            "data": {
                "strategy_id": strategy_id,
                "actual_data_date": actual_data_date,
                "pre_trade_guard": {
                    "status": "blocked",
                    "ticker": "00631L.TW",
                    "allow_00631l_add": False,
                    "policy": "advisory_no_auto_weight_change",
                },
            },
        }
    )


def test_ops_health_reports_no_active_allocation_impact(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "logs/daily.log", "ok\n")
    _write(tmp_path / "run_daily.bat", "echo daily\n")
    _write(tmp_path / "run_fetch.bat", "echo fetch\n")
    _write(tmp_path / "task_scheduler_setup.xml", "<Task />\n")
    _write(tmp_path / "results/ncf_00631l_latest_20260630.json", "{}")
    _write(tmp_path / "results/ncf_00632r_latest_20260630.json", "{}")
    _write(tmp_path / "results/group_a_plus_factor_lens_20260630.json", "{}")
    _write(tmp_path / "results/alphagen_lite_feature_pool_latest_20260701.json", "{}")
    _write(tmp_path / "results/alphagen_lite_shadow_latest_20260701.json", "{}")
    stamp = _today_stamp()
    _write(
        tmp_path / f"results/ncf_daily_pipeline_{stamp}.json",
        json.dumps(
            {
                "date_stamp": stamp,
                "outputs": {
                    "live_signal": "report/group_a_plus/latest/live_signal.json",
                    "factor_lens": "results/group_a_plus_factor_lens_20260630.json",
                },
                "signals": {"00631L": {"direction": "DOWN"}},
            }
        ),
    )

    report = build_ops_health(tmp_path)

    assert report["active_allocation_impact"] == "none"
    assert report["status"] in {"ok", "warning"}
    assert report["artifact_health"]["missing_required"] == []
    assert report["pipeline_health"]["date_stamp"] == stamp
    assert report["module_health"]["modules"]["finbert_sentiment"]["status"] == "ok"


def test_ops_health_errors_when_required_artifacts_are_missing(tmp_path: Path) -> None:
    (tmp_path / "results").mkdir(parents=True)
    (tmp_path / "report/group_a_plus/latest").mkdir(parents=True)

    report = build_ops_health(tmp_path)

    assert report["status"] == "error"
    assert "artifact_health" in report["errors"]
    assert "live_signal" in report["artifact_health"]["missing_required"]


def test_artifact_health_resolves_ncf_panel_path_from_strategy_json(tmp_path: Path) -> None:
    """2026-07-07 Fable audit: REQUIRED_ARTIFACTS previously hardcoded the
    panel filename to a stale snapshot (20260630) while production had moved
    to a newer panel -- the health check was silently watching the wrong
    file. It must now track whatever strategy.json's
    active_strategy.runner_params.ncf_panel_631l_path currently points to."""
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(
        tmp_path / "report/group_a_plus/latest/strategy.json",
        json.dumps(
            {
                "active_strategy": {
                    "runner_params": {
                        "ncf_panel_631l_path": "results/ncf_00631l_panel_latest_20260707.csv",
                    }
                }
            }
        ),
    )
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260707.csv", "date,value\n")

    report = build_ops_health(tmp_path)

    panel_check = next(item for item in report["artifact_health"]["required"] if item["label"] == "ncf_00631l_panel")
    assert panel_check["relative_path"] == "results/ncf_00631l_panel_latest_20260707.csv"
    assert panel_check["status"] == "ok"
    assert report["artifact_health"]["missing_required"] == []


_DiskUsage = namedtuple("_DiskUsage", ["total", "used", "free"])


def test_disk_free_below_2pct_is_error(tmp_path: Path, monkeypatch) -> None:
    """2026-07-07 Fable audit: disk was status_policy=informational_only
    (never gated status) while results/ grows unbounded every pipeline run
    and the live disk was found at 1.3% free -- a full disk mid-write can
    corrupt the duckdb file the unattended 23:00 pipeline writes to."""
    monkeypatch.setattr(shutil, "disk_usage", lambda _root: _DiskUsage(total=100, used=99, free=1))

    result = collect_system_resources(tmp_path)

    assert result["disk"]["status_policy"] == "warn_below_5pct_error_below_2pct"
    assert "disk_free_below_2pct" in result["errors"]
    assert result["status"] == "error"


def test_disk_free_below_5pct_is_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _root: _DiskUsage(total=100, used=96, free=4))

    result = collect_system_resources(tmp_path)

    assert "disk_free_below_5pct" in result["warnings"]
    assert result["status"] == "warning"


def test_execution_plan_stale_relative_to_live_signal_is_warning(tmp_path: Path) -> None:
    """2026-07-07 Fable audit: execution_plan.json can't be safely
    auto-regenerated (needs a manually-updated cash/holdings workbook), so
    the check is staleness-detection only -- it must warn, not silently
    report "ok" via existence alone, when live_signal.json has moved on
    without a matching execution_plan.json refresh."""
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    plan_path = tmp_path / "report/group_a_plus/latest/execution_plan.json"
    _write(plan_path, "{}")
    old_time = time.time() - 10 * 86400
    os.utime(plan_path, (old_time, old_time))
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())

    report = build_ops_health(tmp_path)

    assert report["artifact_health"]["execution_plan_freshness"]["status"] == "stale"
    assert report["artifact_health"]["execution_plan_freshness"]["lag_days"] > 3
    assert "execution_plan_stale" in report["artifact_health"]["missing_optional"]


def test_golden_signal_stale_is_a_visible_warning(tmp_path: Path, monkeypatch) -> None:
    """2026-07-12/13 audit: generate_dual_group_signal.py (Group A's
    golden1 signal, a2118's golden1-regime base weight input) is not
    scheduled by run_ncf_daily_pipeline.py/run_daily.bat/run_fetch.bat and
    had no freshness check anywhere -- a real incident found live_signal.json
    silently using an already-3-days-stale snapshot. This must surface as a
    visible warning, not silent "ok via existence alone"."""
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    golden_path = tmp_path / "results/signal_group_a_20260101_000000.json"
    _write(golden_path, "{}")
    old_time = time.time() - 10 * 86400
    os.utime(golden_path, (old_time, old_time))
    from group_a_plus import runners

    monkeypatch.setattr(runners.a2111, "_resolve_golden_signal_path", lambda: golden_path)

    report = build_ops_health(tmp_path)

    assert report["artifact_health"]["golden_signal_freshness"]["status"] == "stale"
    assert report["artifact_health"]["golden_signal_freshness"]["lag_days"] > 3
    assert "golden_signal_stale" in report["artifact_health"]["missing_optional"]


def test_golden_signal_fresh_is_not_flagged(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    golden_path = tmp_path / "results/signal_group_a_20260101_000000.json"
    _write(golden_path, "{}")
    from group_a_plus import runners

    monkeypatch.setattr(runners.a2111, "_resolve_golden_signal_path", lambda: golden_path)

    report = build_ops_health(tmp_path)

    assert report["artifact_health"]["golden_signal_freshness"]["status"] == "fresh"
    assert "golden_signal_stale" not in report["artifact_health"]["missing_optional"]


def test_group_a_plus_decision_signal_stale_is_a_visible_warning(tmp_path: Path) -> None:
    """Same gap as golden1 above, found in the same audit: decision.json ->
    group_a_plus_policy_signal_*.json feeds a2118's current_defensive
    (used only by the group_a_plus_recovery regime), is not scheduled, and
    had no freshness check. Narrower blast radius than golden1 (only
    matters during a crash-recovery transition), hence the longer default
    tolerance (14 days) -- this fixture is 20 days stale to exceed it."""
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(
        tmp_path / "report/group_a_plus/latest/decision.json",
        json.dumps({"signal_json": "results/group_a_plus_policy_signal_20260101.json"}),
    )
    signal_path = tmp_path / "results/group_a_plus_policy_signal_20260101.json"
    _write(signal_path, "{}")
    old_time = time.time() - 20 * 86400
    os.utime(signal_path, (old_time, old_time))

    report = build_ops_health(tmp_path)

    assert report["artifact_health"]["group_a_plus_decision_signal_freshness"]["status"] == "stale"
    assert report["artifact_health"]["group_a_plus_decision_signal_freshness"]["lag_days"] > 14
    assert "group_a_plus_decision_signal_stale" in report["artifact_health"]["missing_optional"]


def test_volatility_gate_active_requires_aligned_execution_plan_guard(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _live_signal_with_volatility_gate())
    _write(
        tmp_path / "report/group_a_plus/latest/execution_plan.json",
        _execution_plan_with_guard(actual_data_date="2026-07-08"),
    )

    report = build_ops_health(tmp_path)

    guard = report["artifact_health"]["volatility_gate_execution_guard"]
    assert guard["volatility_gate_active"] is True
    assert guard["execution_plan_aligned"] is False
    assert "volatility_gate_active_execution_plan_unaligned" in report["artifact_health"]["missing_optional"]


def test_volatility_gate_active_with_aligned_guard_is_ok(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _live_signal_with_volatility_gate())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", _execution_plan_with_guard())

    report = build_ops_health(tmp_path)

    guard = report["artifact_health"]["volatility_gate_execution_guard"]
    assert guard["status"] == "ok"
    assert guard["execution_plan_aligned"] is True
    assert guard["allow_00631l_add"] is False
    assert "volatility_gate_active_execution_plan_unaligned" not in report["artifact_health"]["missing_optional"]


def test_dfl_advisory_missing_is_visible_warning(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(
        tmp_path / "report/group_a_plus/latest/live_signal.json",
        json.dumps({"success": True, "data": {"actual_data_date": "2026-07-09"}}),
    )
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")

    report = build_ops_health(tmp_path)

    dfl = report["artifact_health"]["dfl_advisory"]
    assert dfl["status"] == "warning"
    assert "dfl_advisory_missing" in report["artifact_health"]["missing_optional"]


def test_dfl_advisory_aligned_is_ok(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(
        tmp_path / "report/group_a_plus/latest/live_signal.json",
        json.dumps({"success": True, "data": {"actual_data_date": "2026-07-09"}}),
    )
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(
        tmp_path / "report/group_a_plus/latest/a2118_dfl_advisory.json",
        json.dumps(
            {
                "status": "available",
                "as_of": "2026-07-09",
                "action": "KEEP",
                "advisory_active": False,
                "policy": "advisory_only_no_auto_weight_change",
            }
        ),
    )

    report = build_ops_health(tmp_path)

    dfl = report["artifact_health"]["dfl_advisory"]
    assert dfl["status"] == "ok"
    assert dfl["aligned"] is True
    assert dfl["action"] == "KEEP"
    assert "dfl_advisory_missing" not in report["artifact_health"]["missing_optional"]
    assert "dfl_advisory_unaligned" not in report["artifact_health"]["missing_optional"]


def test_dfl_advisory_unaligned_is_visible_warning(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(
        tmp_path / "report/group_a_plus/latest/live_signal.json",
        json.dumps({"success": True, "data": {"actual_data_date": "2026-07-09"}}),
    )
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(
        tmp_path / "report/group_a_plus/latest/a2118_dfl_advisory.json",
        json.dumps({"status": "available", "as_of": "2026-07-08", "action": "KEEP"}),
    )

    report = build_ops_health(tmp_path)

    dfl = report["artifact_health"]["dfl_advisory"]
    assert dfl["status"] == "warning"
    assert dfl["aligned"] is False
    assert "dfl_advisory_unaligned" in report["artifact_health"]["missing_optional"]


def test_dfl_active_date_audit_missing_is_visible_warning(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")

    report = build_ops_health(tmp_path)

    audit = report["artifact_health"]["dfl_active_date_audit"]
    assert audit["status"] == "warning"
    assert audit["exists"] is False
    assert "dfl_active_date_audit_missing" in report["artifact_health"]["missing_optional"]


def test_dfl_active_date_audit_shadow_only_pass_is_ok(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(
        tmp_path / "results/a2118_dfl_active_date_audit_20260714.json",
        json.dumps(
            {
                "status": "research_only",
                "conclusion": "passes_replay_audit_with_warnings_shadow_only",
                "assumptions": {"policy": "shadow_only_no_auto_weight_change"},
                "summary": {
                    "active_days": 7,
                    "all_checks_pass": True,
                    "warning_days": 3,
                    "existing_guard_overlap_days": 0,
                    "total_estimated_cost_bps": 8.0749,
                },
            }
        ),
    )

    report = build_ops_health(tmp_path)

    audit = report["artifact_health"]["dfl_active_date_audit"]
    assert audit["status"] == "ok"
    assert audit["conclusion"] == "passes_replay_audit_with_warnings_shadow_only"
    assert audit["policy"] == "shadow_only_no_auto_weight_change"
    assert audit["active_days"] == 7
    assert "dfl_active_date_audit_missing" not in report["artifact_health"]["missing_optional"]
    assert "dfl_active_date_audit_hard_checks_not_passing" not in report["artifact_health"]["missing_optional"]


def test_dfl_active_date_audit_failed_checks_are_visible_warning(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(
        tmp_path / "results/a2118_dfl_active_date_audit_latest.json",
        json.dumps(
            {
                "status": "research_only",
                "conclusion": "review_required_shadow_only",
                "assumptions": {"policy": "shadow_only_no_auto_weight_change"},
                "summary": {"active_days": 7, "all_checks_pass": False},
            }
        ),
    )

    report = build_ops_health(tmp_path)

    audit = report["artifact_health"]["dfl_active_date_audit"]
    assert audit["status"] == "warning"
    assert audit["all_checks_pass"] is False
    assert "dfl_active_date_audit_hard_checks_not_passing" in report["artifact_health"]["missing_optional"]


def test_external_data_freshness_missing_report_is_warning(tmp_path: Path) -> None:
    result = collect_external_data_freshness(tmp_path)
    assert result["status"] == "warning"
    assert result["warnings"] == ["ohlcv_freshness_report_missing"]


def test_external_data_freshness_surfaces_external_staleness_as_error(tmp_path: Path) -> None:
    _write(
        tmp_path / "results/ohlcv_freshness_20260707.json",
        json.dumps(
            {
                "overall_status": "error",
                "target_date": "2026-07-07",
                "error_tickers": [],
                "warning_tickers": [],
                "external_error_tickers": ["^GSPC", "^TNX"],
            }
        ),
    )

    result = collect_external_data_freshness(tmp_path)

    assert result["status"] == "error"
    assert result["external_error_tickers"] == ["^GSPC", "^TNX"]


def test_pipeline_health_flags_stale_manifest_as_error(tmp_path: Path) -> None:
    """Fable audit (2026-07-08, #2): collect_pipeline_health previously only
    checked whether *a* manifest existed via glob, never whether its
    date_stamp was actually today's -- a pipeline that silently stopped
    producing new manifests kept reporting "ok" off of an old manifest."""
    old_stamp = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y%m%d")
    _write(
        tmp_path / f"results/ncf_daily_pipeline_{old_stamp}.json",
        json.dumps({"date_stamp": old_stamp, "outputs": {}, "signals": {}}),
    )

    result = collect_pipeline_health(tmp_path)

    assert result["status"] == "error"
    assert "pipeline_manifest_stale" in result["errors"]


def test_pipeline_health_flags_failed_run_manifest_as_error(tmp_path: Path) -> None:
    """A critical step's partial-manifest-on-crash (status="failed") must not
    be read as a healthy run just because the file itself parses."""
    stamp = _today_stamp()
    _write(
        tmp_path / f"results/ncf_daily_pipeline_{stamp}.json",
        json.dumps(
            {
                "date_stamp": stamp,
                "status": "failed",
                "failed_step": "ncf_00631l",
                "error": "boom",
                "completed_steps": ["refresh_group_data"],
            }
        ),
    )

    result = collect_pipeline_health(tmp_path)

    assert result["status"] == "error"
    assert "pipeline_run_failed" in result["errors"]


def test_tsmc_weight_assumption_health_reports_ok_after_calibration() -> None:
    """2026-07-10 calibration: TSMC_0050_WEIGHT_ASSUMPTION_AS_OF is now set
    (fetched from Yuanta's official 0050 holdings page), so within
    TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS this must report "ok", not warn
    on an uncalibrated assumption."""
    result = collect_tsmc_weight_assumption_health()

    assert result["status"] == "ok"
    assert result["warnings"] == []
    assert result["weight_assumption"] == 0.5831
    assert result["as_of"] == "2026-07-10"


def test_tsmc_weight_assumption_is_stale_past_max_age() -> None:
    """Fable audit (2026-07-08, #9): the staleness check must still catch a
    calibration date that has aged past TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS,
    even though the assumption is now calibrated (not None)."""
    from datetime import date

    from group_a_plus.utils.tsmc_0050_weight import (
        TSMC_0050_WEIGHT_ASSUMPTION_AS_OF,
        tsmc_0050_weight_assumption_is_stale,
    )

    as_of = date.fromisoformat(TSMC_0050_WEIGHT_ASSUMPTION_AS_OF)
    far_future = as_of + timedelta(days=181)
    assert tsmc_0050_weight_assumption_is_stale(today=far_future) is True

    near_future = as_of + timedelta(days=30)
    assert tsmc_0050_weight_assumption_is_stale(today=near_future) is False


def test_ops_health_overall_status_reflects_external_freshness_error(tmp_path: Path) -> None:
    _write(tmp_path / "report/group_a_plus/latest/strategy.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/live_signal.json", _minimal_live_signal())
    _write(tmp_path / "report/group_a_plus/latest/execution_plan.json", "{}")
    _write(tmp_path / "report/group_a_plus/latest/strategy_env_health.json", "{}")
    _write(tmp_path / "results/ncf_00631l_panel_latest_20260630.csv", "date,value\n")
    _write(
        tmp_path / "results/ohlcv_freshness_20260707.json",
        json.dumps({"overall_status": "error", "external_error_tickers": ["2330.TW"]}),
    )

    report = build_ops_health(tmp_path)

    assert report["external_data_freshness"]["status"] == "error"
    assert "external_data_freshness" in report["errors"]
    assert report["status"] == "error"
