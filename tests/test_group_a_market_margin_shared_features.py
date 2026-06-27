from unittest.mock import patch

import pandas as pd

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS,
    attach_group_a_market_margin_shared_features_db_first,
    payload_uses_group_a_market_margin_shared_features,
)


def test_attach_group_a_market_margin_shared_features_adds_columns():
    dates = pd.date_range("2026-05-01", periods=6, freq="B")
    stock_data = {
        "0050.TW": pd.DataFrame({"date": dates, "volume": [1_000_000] * 6}),
        "00631L.TW": pd.DataFrame({"date": dates, "volume": [1_500_000] * 6}),
        "00632R.TW": pd.DataFrame({"date": dates, "volume": [800_000] * 6}),
    }
    market_margin = pd.DataFrame(
        {
            "dt": dates,
            "ticker_count": [980, 982, 981, 979, 983, 984],
            "margin_buy": [2.1e8, 2.3e8, 2.0e8, 2.2e8, 2.4e8, 2.35e8],
            "margin_sell": [1.8e8, 1.9e8, 1.85e8, 1.88e8, 1.95e8, 1.9e8],
            "margin_repayment": [1.2e7, 1.1e7, 1.0e7, 1.3e7, 1.25e7, 1.15e7],
            "margin_limit": [3.2e10] * 6,
            "margin_balance": [9.2e9, 9.3e9, 9.35e9, 9.28e9, 9.4e9, 9.5e9],
            "margin_prev_balance": [9.15e9, 9.2e9, 9.3e9, 9.35e9, 9.28e9, 9.4e9],
            "offset_loan_short": [2.1e6, 2.0e6, 2.2e6, 2.3e6, 2.4e6, 2.35e6],
            "short_buy": [6.2e6, 6.0e6, 5.8e6, 6.4e6, 6.5e6, 6.3e6],
            "short_sell": [8.5e6, 8.3e6, 8.1e6, 8.7e6, 8.8e6, 8.6e6],
            "short_repayment": [4.0e5, 4.2e5, 3.8e5, 4.1e5, 4.0e5, 3.9e5],
            "short_limit": [1.8e10] * 6,
            "short_balance": [3.8e8, 3.85e8, 3.9e8, 3.88e8, 3.95e8, 4.0e8],
            "short_prev_balance": [3.75e8, 3.8e8, 3.85e8, 3.9e8, 3.88e8, 3.95e8],
        }
    )

    with patch(
        "train_dual_group_2024_2026.query_market_margin_data",
        return_value=market_margin.copy(),
    ):
        out = attach_group_a_market_margin_shared_features_db_first(
            stock_data,
            ["0050.TW", "00631L.TW", "00632R.TW"],
            "2026-05-01",
            "2026-05-31",
        )

    for ticker in ["0050.TW", "00631L.TW", "00632R.TW"]:
        for column in GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS:
            assert column in out[ticker].columns
            assert out[ticker][column].notna().all()


def test_payload_market_margin_shared_flag_defaults_false():
    assert not payload_uses_group_a_market_margin_shared_features({})
    assert not payload_uses_group_a_market_margin_shared_features(
        {"group_a_market_margin_shared_config": {"enabled": False}}
    )


def test_payload_market_margin_shared_flag_reads_payload_config():
    payload = {"group_a_market_margin_shared_config": {"enabled": True}}
    assert payload_uses_group_a_market_margin_shared_features(payload)


def test_payload_market_margin_shared_flag_reads_gate_config():
    payload = {"group_a_market_margin_gate_config": {"enabled": True}}
    assert payload_uses_group_a_market_margin_shared_features(payload)


def test_env_kwargs_from_payload_hides_gate_only_market_margin_cols():
    payload = {
        "group_a_profile": "default",
        "group_a": {
            "shared_feature_cols": list(GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS),
            "market_margin_shared_feature_cols": list(GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS),
        },
        "group_a_market_margin_shared_config": {
            "enabled": True,
            "observation_enabled": False,
        },
        "group_a_market_margin_gate_config": {
            "enabled": True,
        },
    }
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
    assert env_kwargs["market_margin_gate_enabled"] is True
    assert env_kwargs["hidden_shared_feature_cols"] == list(GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS)
    assert shared_feature_cols == list(GROUP_A_MARKET_MARGIN_SHARED_FEATURE_COLUMNS)
