from scripts.evaluate.build_group_a_plusplus_2609_04917_turnover_bridge_shadow import build_bridge


def test_bridge_caps_turnover_and_disallows_leveraged_add() -> None:
    plan = {
        "requested_as_of_date": "2026-09-09",
        "actual_data_date": "2026-09-07",
        "current_total_assets": 1000.0,
        "current_holdings": {"BOND": 10, "LEV": 0, "DEF": 0},
        "target_shares": {"BOND": 0, "LEV": 10, "DEF": 10},
        "current_prices": {"BOND": 40.0, "LEV": 10.0, "DEF": 10.0},
    }

    report = build_bridge(execution_plan=plan, max_turnover=0.50, disallow_add={"LEV"})

    assert report["status"] == "shadow_bridge_available_for_manual_review"
    assert report["bridge_target_shares"]["BOND"] == 0
    assert report["bridge_target_shares"]["LEV"] == 0
    assert report["bridge_target_shares"]["DEF"] == 10
    assert report["computed"]["full_target_turnover"] == 0.6
    assert report["computed"]["bridge_turnover"] == 0.5
    assert report["decision"]["execution_allowed"] is False
    assert any(row["reason"] == "leveraged_add_disallowed" for row in report["skipped_trade_plan"])


def test_bridge_partial_fills_when_budget_is_tight() -> None:
    plan = {
        "actual_data_date": "2026-09-07",
        "current_total_assets": 1000.0,
        "current_holdings": {"BOND": 10, "DEF": 0},
        "target_shares": {"BOND": 0, "DEF": 20},
        "current_prices": {"BOND": 40.0, "DEF": 10.0},
    }

    report = build_bridge(execution_plan=plan, max_turnover=0.45, disallow_add=set())

    assert report["bridge_target_shares"]["BOND"] == 0
    assert report["bridge_target_shares"]["DEF"] == 5
    assert report["computed"]["bridge_turnover"] == 0.45
    assert any(row["reason"] == "partially_filled_by_turnover_cap" for row in report["skipped_trade_plan"])


def test_bridge_blocks_missing_inputs() -> None:
    report = build_bridge(execution_plan={}, max_turnover=0.50, disallow_add=set())

    assert report["status"] == "blocked"
    assert "current_holdings_missing" in report["blocking_reasons"]
    assert "current_total_assets_missing" in report["blocking_reasons"]
