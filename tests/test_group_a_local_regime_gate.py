from __future__ import annotations

import pandas as pd

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    GROUP_A_LOCAL_REGIME_SHARED_FEATURE_COLUMNS,
    PortfolioEnv,
)


def test_env_kwargs_from_payload_hides_local_regime_shared_cols():
    payload = {
        "group_a_profile": "default",
        "group_a": {
            "shared_feature_cols": list(GROUP_A_LOCAL_REGIME_SHARED_FEATURE_COLUMNS),
        },
        "group_a_local_regime_gate_config": {
            "enabled": True,
            "shared_columns": list(GROUP_A_LOCAL_REGIME_SHARED_FEATURE_COLUMNS),
            "risk_off_template": "0050_only",
            "severe_template": "0050_70_00632R_30",
        },
    }
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    assert env_kwargs["local_regime_gate_enabled"] is True
    assert env_kwargs["hidden_shared_feature_cols"] == list(GROUP_A_LOCAL_REGIME_SHARED_FEATURE_COLUMNS)
    assert shared_feature_cols == list(GROUP_A_LOCAL_REGIME_SHARED_FEATURE_COLUMNS)


def test_local_regime_snapshot_enters_severe_mode():
    panel = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-05-25")],
            "0050.TW_open": [100.0],
            "0050.TW_close": [92.0],
            "0050.TW_dividends": [0.0],
            "00631L.TW_open": [20.0],
            "00631L.TW_close": [18.0],
            "00631L.TW_dividends": [0.0],
            "00632R.TW_open": [10.0],
            "00632R.TW_close": [11.2],
            "00632R.TW_dividends": [0.0],
            "0050_close_ma60_ratio": [0.95],
            "0050.TW_close_ma120_ratio": [0.97],
            "0050_drawdown_20": [-0.12],
            "0050_drawdown_60": [-0.18],
            "0050.TW_momentum_21": [-0.09],
            "0050.TW_momentum_63": [-0.14],
            "0050_volatility_20_z": [1.8],
            "twse_index_return_5d_raw": [-0.09],
            "market_volatility_raw": [0.03],
        }
    )
    env = PortfolioEnv(
        panel,
        ["0050.TW", "00631L.TW", "00632R.TW"],
        local_regime_gate_enabled=True,
    )
    env.reset()
    snapshot = env._local_regime_snapshot()
    assert snapshot["severe"] is True
    assert snapshot["risk_off"] is True
    assert snapshot["state"] == "severe"
