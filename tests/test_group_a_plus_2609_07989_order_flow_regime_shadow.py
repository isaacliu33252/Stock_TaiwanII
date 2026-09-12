from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from group_a_plus.integrations.order_flow_regime_shadow import (
    append_order_flow_regime_shadow_log,
    build_order_flow_regime_shadow,
    build_order_flow_regime_shadow_from_csv,
)
from scripts.run.build_group_a_plus_2609_07989_order_flow_regime_shadow import render_markdown


def _signed_flow() -> pd.DataFrame:
    rows = []
    ts = pd.Timestamp("2026-09-12 09:00")
    for i in range(32):
        rows.append(
            {
                "timestamp": ts + pd.Timedelta(minutes=30 * i),
                "ticker": "00631L.TW",
                "signed_volume": -12000 if i == 31 else 100 + (i % 3) * 10,
            }
        )
        rows.append(
            {
                "timestamp": ts + pd.Timedelta(minutes=30 * i),
                "ticker": "0050.TW",
                "signed_volume": 80 + (i % 2) * 5,
            }
        )
    return pd.DataFrame(rows)


def test_order_flow_regime_shadow_flags_signed_flow_break_without_live_change() -> None:
    payload = build_order_flow_regime_shadow(
        _signed_flow(),
        tickers=("00631L.TW", "0050.TW"),
        bucket="30min",
        window=12,
        z_threshold=2.0,
    )

    assert payload["status"] == "available"
    assert payload["policy"] == "execution_advisory_shadow_only"
    assert payload["advisory_state"] == "execution_caution"
    assert payload["stress_tickers"] == ["00631L.TW"]
    assert payload["by_ticker"]["00631L.TW"]["high_stress_execution_reference"] is True
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["latest_strategy_change_allowed"] is False
    assert payload["decision"]["golden2_0830_change_allowed"] is False


def test_order_flow_regime_shadow_rejects_daily_ohlcv_proxy_shape() -> None:
    payload = build_order_flow_regime_shadow(
        pd.DataFrame(
            {
                "dt": ["2026-09-12"],
                "ticker": ["00631L.TW"],
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100],
                "volume": [1_000_000],
            }
        )
    )

    assert payload["status"] == "unavailable"
    assert "missing required signed-flow columns" in payload["reason"]
    assert payload["decision"]["live_weight_change_allowed"] is False


def test_order_flow_regime_shadow_from_missing_csv_is_unavailable(tmp_path: Path) -> None:
    payload = build_order_flow_regime_shadow_from_csv(tmp_path / "missing.csv")

    assert payload["status"] == "unavailable"
    assert payload["reason"] == "missing_signed_flow_csv"
    assert payload["decision"]["creates_orders"] is False


def test_order_flow_regime_shadow_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "shadow.jsonl"
    payload = build_order_flow_regime_shadow(
        _signed_flow(),
        tickers=("00631L.TW",),
        bucket="30min",
        window=12,
        z_threshold=2.0,
    )

    append_order_flow_regime_shadow_log(log, payload)
    append_order_flow_regime_shadow_log(log, payload | {"advisory_state": "updated"})

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["advisory_state"] == "updated"


def test_order_flow_regime_shadow_markdown_states_no_live_impact() -> None:
    payload = build_order_flow_regime_shadow(
        _signed_flow(),
        tickers=("00631L.TW",),
        bucket="30min",
        window=12,
        z_threshold=2.0,
    )
    payload["input_path"] = "/tmp/signed_flow.csv"
    payload["generated_at"] = "2026-09-12T00:00:00+00:00"

    markdown = render_markdown(payload)

    assert "# 2609.07989 Order-Flow Regime Shadow" in markdown
    assert "execution_advisory_shadow_only" in markdown
    assert "Daily OHLCV proxies are intentionally rejected" in markdown
    assert "cannot change latest strategy target weights" in markdown
