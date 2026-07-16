from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import duckdb
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run" / "run_ncf_daily_pipeline.py"
    spec = importlib.util.spec_from_file_location("_test_run_ncf_daily_pipeline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_commands_includes_refresh_ncf_and_advisory_steps() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=False,
        force_refresh=True,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=False,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert list(commands) == [
        "refresh_group_data",
        "refresh_taifex",
        "refresh_taifex_options",
        "refresh_institutional",
        "refresh_margin",
        "refresh_market_margin",
        "refresh_derivative_institutional",
        "refresh_securities_lending",
        "refresh_dealer_positions",
        "refresh_foreign_shareholding",
        "refresh_short_sale_balances",
        "refresh_day_trading",
        "refresh_soxx_options_iv",
        "refresh_cross_market_ohlcv",
        "refresh_2330_per",
        "refresh_shareholding",
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "ncf_signal_archive",
        "ncf_2330",
        "ncf_panel_manifest",
        "ncf_panel_drift",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
        "compounding_regime",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "dfl_advisory",
        "dfl_active_date_audit",
        "dfl_shadow_ensemble",
        "daily_status",
        "promotion_gate",
        "ncf_2330_checklist",
    ]
    assert commands["refresh_group_data"][-1] == "--force"
    assert commands["a2120_shadow_pipeline"][1] == "scripts/run/run_a2120_daily_shadow_pipeline.py"
    assert commands["a2120_shadow_pipeline"][commands["a2120_shadow_pipeline"].index("--date-stamp") + 1] == "20260627"
    assert "a2120_shadow_pipeline" in module.BEST_EFFORT_STEP_NAMES
    assert commands["recovery_boost_spillover_gate_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py"
    )
    assert commands["recovery_boost_spillover_gate_shadow_log"][
        commands["recovery_boost_spillover_gate_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "recovery_boost_spillover_gate_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert commands["trough_override_eligibility_shadow_log"][1] == (
        "scripts/run/build_group_a_plus_trough_override_eligibility_shadow_log.py"
    )
    assert commands["trough_override_eligibility_shadow_log"][
        commands["trough_override_eligibility_shadow_log"].index("--panel") + 1
    ].endswith("results/ncf_00631l_panel_latest_20260627.csv")
    assert "trough_override_eligibility_shadow_log" in module.BEST_EFFORT_STEP_NAMES
    assert any(item.endswith("results/ohlcv_freshness_20260627.json") for item in commands["ohlcv_freshness"])
    assert any(item.endswith("results/ncf_00631l_latest_20260627.json") for item in commands["ncf_00631l"])
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in commands["ncf_00632r"])
    assert "--full-panel" in commands["ncf_00631l"]
    assert "--full-panel" in commands["ncf_00632r"]
    assert "--full-panel" in commands["ncf_2330"]
    assert commands["ncf_2330"][commands["ncf_2330"].index("--feature-mode") + 1] == "after_close"
    assert any(item.endswith("results/ncf_2330_panel_latest_20260627.csv") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_panel_manifest_20260627.json") for item in commands["ncf_panel_manifest"])
    assert any(item.endswith("results/ncf_00631l_panel_latest_20260627.csv") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.json") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.csv") for item in commands["ncf_panel_drift"])
    assert any(item.endswith("results/ncf_panel_coverage_20260627.json") for item in commands["ncf_panel_coverage"])
    assert any(
        "ncf_2330_panel_latest_20260627.csv=external_market_ohlcv:yfinance:2330.TW" in item
        for item in commands["ncf_panel_coverage"]
    )
    assert any(item.endswith("results/ncf_advisory_panel_latest_20260627.csv") for item in commands["advisory_panel"])
    assert any(
        item.endswith("results/00631l_leveraged_compounding_regime_20260627.json")
        for item in commands["compounding_regime"]
    )
    assert any(
        item.endswith("results/00631l_leveraged_compounding_regime_20260627.csv")
        for item in commands["compounding_regime"]
    )
    assert commands["dfl_advisory"][1] == "scripts/run/build_a2118_dfl_advisory.py"
    assert "--input" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json"
    )
    assert "--selective-inputs" in commands["dfl_advisory"]
    selective_inputs = commands["dfl_advisory"][commands["dfl_advisory"].index("--selective-inputs") + 1]
    assert "p50=results/a2118_decision_focused_action_shadow_selective_p50_7win_20260714.json" in selective_inputs
    assert "p70=results/a2118_decision_focused_action_shadow_selective_p70_7win_20260714.json" in selective_inputs
    assert "--live-signal" in commands["dfl_advisory"]
    assert commands["dfl_advisory"][commands["dfl_advisory"].index("--live-signal") + 1].endswith(
        "results/group_a_plus_live_signal_v2_20260627.json"
    )
    assert commands["dfl_active_date_audit"][1] == "scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py"
    assert "--input" in commands["dfl_active_date_audit"]
    assert commands["dfl_active_date_audit"][commands["dfl_active_date_audit"].index("--input") + 1].endswith(
        "results/a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json"
    )
    assert any(
        item.endswith("results/a2118_dfl_active_date_audit_20260627.json")
        for item in commands["dfl_active_date_audit"]
    )
    assert commands["dfl_shadow_ensemble"][1] == "scripts/run/build_a2118_dfl_shadow_ensemble_log.py"
    assert "--advisory" in commands["dfl_shadow_ensemble"]
    assert commands["dfl_shadow_ensemble"][commands["dfl_shadow_ensemble"].index("--advisory") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_advisory.json"
    )
    assert "--log" in commands["dfl_shadow_ensemble"]
    assert commands["dfl_shadow_ensemble"][commands["dfl_shadow_ensemble"].index("--log") + 1].endswith(
        "results/a2118_dfl_shadow_ensemble_log.jsonl"
    )
    assert any(item.endswith("results/group_a_plus_daily_status_20260627") for item in commands["daily_status"])
    assert "--execution-plan" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--execution-plan") + 1].endswith(
        "report/group_a_plus/latest/execution_plan.json"
    )
    assert "--compounding-regime" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--compounding-regime") + 1].endswith(
        "results/00631l_leveraged_compounding_regime_20260627.json"
    )
    assert "--dfl-advisory" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-advisory") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_advisory.json"
    )
    assert "--dfl-shadow-ensemble" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-shadow-ensemble") + 1].endswith(
        "report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json"
    )
    assert "--dfl-active-date-audit" in commands["daily_status"]
    assert commands["daily_status"][commands["daily_status"].index("--dfl-active-date-audit") + 1].endswith(
        "results/a2118_dfl_active_date_audit_20260627.json"
    )
    assert any(item.endswith("results/group_a_plus_promotion_gate_20260627.json") for item in commands["promotion_gate"])
    assert any(item.endswith("results/ncf_panel_drift_active_vs_20260627.json") for item in commands["promotion_gate"])
    assert "--multi-window-gate" in commands["promotion_gate"]
    assert any(item.endswith("results/ncf_2330_checklist_20260627.json") for item in commands["ncf_2330_checklist"])
    assert commands["refresh_2330_per"][commands["refresh_2330_per"].index("--start") + 1] == "2023-06-27"


def test_build_commands_can_skip_refresh_and_disable_external_features() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert list(commands) == [
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "ncf_signal_archive",
        "ncf_2330",
        "ncf_panel_manifest",
        "ncf_panel_drift",
        "ncf_panel_coverage",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
        "compounding_regime",
        "a2120_shadow_pipeline",
        "recovery_boost_spillover_gate_shadow_log",
        "trough_override_eligibility_shadow_log",
        "dfl_advisory",
        "dfl_active_date_audit",
        "dfl_shadow_ensemble",
        "daily_status",
        "promotion_gate",
        "ncf_2330_checklist",
    ]
    assert "--no-external-features" in commands["ncf_00631l"]
    assert "--no-external-features" in commands["ncf_00632r"]
    assert "--no-external-features" in commands["ncf_2330"]


def test_build_commands_can_use_ncf_2330_pre_open_feature_mode() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260707",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-16",
        chip_end="2026-07-07",
        per_start="2023-07-07",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        train_start_2330="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        ncf_2330_feature_mode="pre_open",
        refresh_external_cache=False,
        checklist_external_start="2023-07-07",
        checklist_external_end="2026-07-08",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert commands["ncf_2330"][commands["ncf_2330"].index("--feature-mode") + 1] == "pre_open"


def test_build_commands_can_skip_promotion_gate() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        skip_promotion_gate=True,
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "promotion_gate" not in commands
    assert "ncf_panel_drift" in commands


def test_build_commands_can_override_promotion_drift_audit() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260627",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-06",
        chip_end="2026-06-27",
        per_start="2023-06-27",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        promotion_drift_audit="results/custom_drift.json",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "ncf_panel_drift" in commands
    assert commands["promotion_gate"][commands["promotion_gate"].index("--drift-audit") + 1] == "results/custom_drift.json"


def test_build_commands_can_pin_refresh_target_date_and_strict_mode() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260702",
        skip_refresh=False,
        force_refresh=True,
        refresh_target_date="2026-07-02",
        strict_refresh=True,
        skip_shareholding=False,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=True,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    refresh_cmd = commands["refresh_group_data"]
    assert "--target-date" in refresh_cmd
    assert refresh_cmd[refresh_cmd.index("--target-date") + 1] == "2026-07-02"
    assert "--strict" in refresh_cmd
    assert "--force" in refresh_cmd
    freshness_cmd = commands["ohlcv_freshness"]
    assert freshness_cmd[freshness_cmd.index("--target-date") + 1] == "2026-07-02"
    assert "--fail-on-warning" in freshness_cmd


def test_pipeline_db_path_falls_back_when_args_has_no_db() -> None:
    module = _load_module()
    args = argparse.Namespace(date_stamp="20260714")

    assert module._pipeline_db_path(args).name == "stock_data.db"


def test_build_commands_refresh_external_cache_includes_checklist_tickers() -> None:
    module = _load_module()
    args = argparse.Namespace(
        date_stamp="20260702",
        skip_refresh=True,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=True,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=True,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert "refresh_ncf_2330_checklist_external_cache" in commands
    refresh_cmd = commands["refresh_ncf_2330_checklist_external_cache"]
    assert "scripts/fetch/fetch_ncf_2330_checklist_external_cache.py" in refresh_cmd
    assert "--allow-download" in refresh_cmd
    assert refresh_cmd[refresh_cmd.index("--start") + 1] == "2023-07-02"
    assert refresh_cmd[refresh_cmd.index("--end") + 1] == "2026-07-03"


def _base_args(tmp_db: str, **overrides) -> argparse.Namespace:
    defaults = dict(
        date_stamp="20260702",
        skip_refresh=False,
        force_refresh=False,
        refresh_target_date="auto",
        strict_refresh=False,
        skip_shareholding=False,
        chip_start="2026-06-11",
        chip_end="2026-07-02",
        per_start="2023-07-02",
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        checklist_external_start="2023-07-02",
        checklist_external_end="2026-07-03",
        db=tmp_db,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_resolve_chip_start_falls_back_to_default_when_db_missing(tmp_path: Path) -> None:
    module = _load_module()
    missing_db = tmp_path / "does_not_exist.db"

    result = module._resolve_chip_start(missing_db, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_resolve_chip_start_extends_backward_when_gap_exceeds_default(tmp_path: Path) -> None:
    """The M8 scenario: pipeline was down for a month, default lookback
    (chip_start) only covers the last few weeks -- the resolved start must
    reach back to the day after the last known row, not leave the gap."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-05-01')")
    finally:
        con.close()

    # default_start (2026-06-11) is *after* the last known row (2026-05-01)
    # plus a month-long gap -- resolved start must move back to 2026-05-02.
    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-05-02"


def test_resolve_chip_start_does_not_narrow_when_table_is_fresh(tmp_path: Path) -> None:
    """A table fresher than the default lookback must not narrow the
    window -- still use the default trailing window (harmless, covers
    late-arriving upstream revisions)."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-07-01')")
    finally:
        con.close()

    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_resolve_chip_start_handles_missing_table(tmp_path: Path) -> None:
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE some_other_table (x INT)")
    finally:
        con.close()

    result = module._resolve_chip_start(db_path, ["institutional_data"], "2026-06-11")

    assert result == "2026-06-11"


def test_build_commands_extends_chip_start_for_stale_table_only(tmp_path: Path) -> None:
    """Each of the 4 chip-data commands gets its own resolved start based
    on its own table's freshness -- a gap in one table doesn't affect the
    others."""
    module = _load_module()
    db_path = tmp_path / "stock_data.db"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE institutional_data (ticker VARCHAR, dt DATE)")
        con.execute("CREATE TABLE derivative_institutional_data (product_id VARCHAR, dt DATE)")
        # institutional_data has a real gap; derivative_institutional_data is fresh.
        con.execute("INSERT INTO institutional_data VALUES ('0050.TW', '2026-05-01')")
        con.execute("INSERT INTO derivative_institutional_data VALUES ('TX', '2026-07-01')")
    finally:
        con.close()

    args = _base_args(str(db_path), chip_start="2026-06-11", chip_end="2026-07-02")
    commands = module.build_commands(args)

    institutional_cmd = commands["refresh_institutional"]
    derivative_cmd = commands["refresh_derivative_institutional"]
    assert institutional_cmd[institutional_cmd.index("--start") + 1] == "2026-05-02"
    assert derivative_cmd[derivative_cmd.index("--start") + 1] == "2026-06-11"


def test_run_pipeline_commands_continues_past_best_effort_step_failure(tmp_path: Path, monkeypatch) -> None:
    """Fable audit (2026-07-08, #2): a transient failure in a best-effort
    refresh step must not stop the whole run -- the NCF/signal steps below
    can still proceed against already-fetched or cached data."""
    module = _load_module()
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)

    def fake_run(cmd, *, dry_run, env_extra=None, log_fh=None):
        if cmd[0] == "refresh_taifex":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(module, "_run", fake_run)
    commands = {
        "refresh_group_data": ["refresh_group_data"],
        "refresh_taifex": ["refresh_taifex"],
        "ncf_00631l": ["ncf_00631l"],
    }

    completed = module.run_pipeline_commands(
        commands,
        date_stamp="20260709",
        dry_run=False,
        refresh_external_cache=False,
        log_path=tmp_path / "logs" / "daily.log",
    )

    assert completed == ["refresh_group_data", "ncf_00631l"]
    assert not (tmp_path / "ncf_daily_pipeline_20260709.json").exists()


def test_run_pipeline_commands_writes_partial_manifest_and_notifies_on_critical_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """A critical (non-refresh) step's failure must halt the run, but not
    silently -- it should record which step failed for
    collect_pipeline_health() to see, and push a direct notification since
    daily_signal/alert_state never got to run."""
    module = _load_module()
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)
    notified: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        module,
        "_notify_pipeline_failure",
        lambda date_stamp, name, error: notified.append((date_stamp, name, error)),
    )

    def fake_run(cmd, *, dry_run, env_extra=None, log_fh=None):
        if cmd[0] == "ncf_00631l":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(module, "_run", fake_run)
    commands = {
        "refresh_group_data": ["refresh_group_data"],
        "ncf_00631l": ["ncf_00631l"],
        "daily_signal": ["daily_signal"],
    }

    with pytest.raises(subprocess.CalledProcessError):
        module.run_pipeline_commands(
            commands,
            date_stamp="20260709",
            dry_run=False,
            refresh_external_cache=False,
            log_path=tmp_path / "logs" / "daily.log",
        )

    assert notified == [("20260709", "ncf_00631l", notified[0][2])]
    manifest = json.loads((tmp_path / "ncf_daily_pipeline_20260709.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["failed_step"] == "ncf_00631l"
    assert manifest["completed_steps"] == ["refresh_group_data"]
