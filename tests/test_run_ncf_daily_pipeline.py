from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import duckdb


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
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert list(commands) == [
        "refresh_group_data",
        "refresh_taifex",
        "refresh_institutional",
        "refresh_margin",
        "refresh_market_margin",
        "refresh_derivative_institutional",
        "refresh_shareholding",
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
    ]
    assert commands["refresh_group_data"][-1] == "--force"
    assert any(item.endswith("results/ohlcv_freshness_20260627.json") for item in commands["ohlcv_freshness"])
    assert any(item.endswith("results/ncf_00631l_latest_20260627.json") for item in commands["ncf_00631l"])
    assert any(item.endswith("results/ncf_00632r_panel_latest_20260627.csv") for item in commands["ncf_00632r"])
    assert any(item.endswith("results/ncf_advisory_panel_latest_20260627.csv") for item in commands["advisory_panel"])


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
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=True,
        refresh_external_cache=False,
        db="/nonexistent/path/stock_data.db",
    )

    commands = module.build_commands(args)

    assert list(commands) == [
        "ohlcv_freshness",
        "ncf_00631l",
        "ncf_00632r",
        "advisory_panel",
        "factor_lens",
        "daily_signal",
    ]
    assert "--no-external-features" in commands["ncf_00631l"]
    assert "--no-external-features" in commands["ncf_00632r"]


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
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=True,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
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
        ohlcv_target_date="auto",
        max_ohlcv_lag_days=3,
        fail_on_ohlcv_warning=False,
        train_start_00631l="2020-01-01",
        train_start_00632r="2015-01-01",
        val_start="2025-01-02",
        val_end="latest",
        no_external_features=False,
        refresh_external_cache=False,
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
