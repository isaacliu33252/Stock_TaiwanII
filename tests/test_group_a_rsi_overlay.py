from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import PortfolioEnv, _align_panel


TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _panel(rsi: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-05-29")],
            "0050.TW_open": [100.0],
            "0050.TW_close": [100.0],
            "0050.TW_dividends": [0.0],
            "00631L.TW_open": [20.0],
            "00631L.TW_close": [20.0],
            "00631L.TW_dividends": [0.0],
            "00632R.TW_open": [10.0],
            "00632R.TW_close": [10.0],
            "00632R.TW_dividends": [0.0],
            "0050_rsi_14": [rsi],
        }
    )


def test_env_kwargs_from_payload_enables_rsi_overlay():
    payload = {
        "group_a_profile": "default",
        "group_a": {},
        "group_a_rsi_overlay_config": {
            "enabled": True,
            "oversold_threshold": 32.0,
            "overbought_threshold": 68.0,
            "oversold_0050_boost": 0.12,
            "overbought_leverage_scale": 0.40,
        },
    }
    env_kwargs, _ = _env_kwargs_from_payload(payload, "group_a")
    assert env_kwargs["rsi_overlay_enabled"] is True
    assert env_kwargs["rsi_overlay_oversold_threshold"] == 32.0
    assert env_kwargs["rsi_overlay_overbought_threshold"] == 68.0
    assert env_kwargs["rsi_overlay_oversold_0050_boost"] == 0.12
    assert env_kwargs["rsi_overlay_overbought_leverage_scale"] == 0.40


@pytest.mark.skip(reason="RSI overlay not integrated into A21.11 active strategy")
def test_rsi_overlay_oversold_uses_cash_to_boost_0050():
    env = PortfolioEnv(_panel(25.0), TICKERS, rsi_overlay_enabled=True)
    weights, details = env._apply_rsi_overlay(np.array([0.50, 0.20, 0.0]), allow_overlay=True)
    assert np.allclose(weights, [0.60, 0.20, 0.0])
    assert details["reason"] == "rsi_oversold_0050_boost"


@pytest.mark.skip(reason="RSI overlay not integrated into A21.11 active strategy")
def test_rsi_overlay_overbought_reduces_leverage_to_cash():
    env = PortfolioEnv(_panel(75.0), TICKERS, rsi_overlay_enabled=True)
    weights, details = env._apply_rsi_overlay(np.array([0.50, 0.20, 0.0]), allow_overlay=True)
    assert np.allclose(weights, [0.50, 0.10, 0.0])
    assert details["reason"] == "rsi_overbought_leverage_scale"


@pytest.mark.skip(reason="RSI overlay not integrated into A21.11 active strategy")
def test_rsi_overlay_does_not_override_risk_gate():
    env = PortfolioEnv(_panel(25.0), TICKERS, rsi_overlay_enabled=True)
    weights, details = env._apply_rsi_overlay(np.array([0.70, 0.0, 0.30]), allow_overlay=False)
    assert np.allclose(weights, [0.70, 0.0, 0.30])
    assert details["active"] is False


@pytest.mark.skip(reason="RSI overlay not integrated into A21.11 active strategy")
def test_align_panel_calculates_0050_rsi_without_adding_it_to_ppo_observation():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    stock_data = {}
    for ticker in TICKERS:
        close = np.linspace(100.0, 119.0, len(dates))
        stock_data[ticker] = pd.DataFrame(
            {
                "date": dates,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": np.full(len(dates), 1000.0),
                "dividends": np.zeros(len(dates)),
            }
        )
    panel = _align_panel(stock_data, TICKERS, "2026-01-01", "2026-01-20")
    assert panel["0050_rsi_14"].iloc[-1] > 99.0
    env = PortfolioEnv(panel, TICKERS, rsi_overlay_enabled=True)
    assert "0050_rsi_14" not in env.feature_cols
