from __future__ import annotations

from scripts.evaluate.build_a2118_seed_averaging_live_inference_snapshot import (
    _holdings_state,
    average_probabilities,
    build_snapshot_from_probabilities,
)


def test_average_probabilities_uses_seed_mean_argmax() -> None:
    action, avg, argmaxes = average_probabilities(
        {
            42: [0.1, 0.7, 0.2],
            43: [0.2, 0.4, 0.4],
            44: [0.6, 0.2, 0.2],
        }
    )

    assert action == 1
    assert [round(value, 4) for value in avg] == [0.3, 0.4333, 0.2667]
    assert argmaxes == {42: 1, 43: 1, 44: 0}


def test_build_snapshot_from_probabilities_is_shadow_only() -> None:
    result = build_snapshot_from_probabilities(
        as_of="2026-08-24",
        tickers=["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"],
        profile_name="default",
        action_schema=None,
        seed_probabilities={
            42: [0.1, 0.7, 0.2, 0.0, 0.0],
            43: [0.2, 0.6, 0.2, 0.0, 0.0],
            44: [0.1, 0.8, 0.1, 0.0, 0.0],
        },
        model_prefix="experiment_finegrained_baseline_seed",
        model_paths={42: "seed42.zip", 43: "seed43.zip", 44: "seed44.zip"},
        panel_rows=1200,
        observation_date="2026-08-24",
        state_basis="authoritative_holdings_snapshot_state",
        portfolio_state={"cash_balance": 100000.0},
    )

    assert result["as_of"] == "2026-08-24"
    assert result["preferred_ensemble"] == "42+43+44"
    assert result["action_index"] == 1
    assert result["policy"] == "shadow_only_no_live_weight_change"
    assert result["live_execution_effect"] == "none"
    assert result["state_basis"] == "authoritative_holdings_snapshot_state"
    assert result["portfolio_state"]["cash_balance"] == 100000.0


def test_holdings_state_uses_authoritative_snapshot_when_date_matches() -> None:
    state_basis, state = _holdings_state(
        {
            "as_of": "2026-08-24",
            "cash_balance": 1000.0,
            "holdings": {"0050.TW": 10, "00631L.TW": 5},
        },
        as_of="2026-08-24",
        tickers=["0050.TW", "00631L.TW"],
        prices=__import__("numpy").asarray([100.0, 40.0]),
    )

    assert state_basis == "authoritative_holdings_snapshot_state"
    assert state["total_assets"] == 2200.0
    assert round(state["weights"]["0050.TW"], 4) == 0.4545
    assert round(state["cash_weight"], 4) == 0.4545


def test_holdings_state_reverts_to_reset_when_date_mismatches() -> None:
    state_basis, state = _holdings_state(
        {"as_of": "2026-08-21", "cash_balance": 1000.0, "holdings": {"0050.TW": 10}},
        as_of="2026-08-24",
        tickers=["0050.TW"],
        prices=__import__("numpy").asarray([100.0]),
    )

    assert state_basis == "reset_position_state_holdings_snapshot_date_mismatch"
    assert state["holdings_snapshot_as_of"] == "2026-08-21"
