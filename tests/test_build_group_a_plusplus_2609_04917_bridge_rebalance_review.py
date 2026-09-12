from scripts.evaluate.build_group_a_plusplus_2609_04917_bridge_rebalance_review import build_review


def test_bridge_ready_for_human_review_when_date_aligned_and_no_leveraged_add() -> None:
    report = build_review(
        live_signal={"requested_as_of_date": "2026-09-09", "actual_data_date": "2026-09-07"},
        bridge_plan={
            "status": "shadow_bridge_available_for_manual_review",
            "actual_data_date": "2026-09-07",
            "current_holdings": {"00631L.TW": 0},
            "target_shares": {"00631L.TW": 0},
            "computed": {"bridge_turnover": 0.499},
            "execution_allowed": False,
        },
        heterogeneous_vol={
            "advisory": {
                "active": True,
                "suggested_review": "avoid_adding_00631l_until_manual_review",
            }
        },
    )

    assert report["status"] == "ready_for_human_rebalance_review"
    assert report["decision"]["manual_review_required"] is True
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["blocking_reasons"] == []


def test_bridge_blocks_when_hetero_blocks_and_bridge_adds_00631l() -> None:
    report = build_review(
        live_signal={"actual_data_date": "2026-09-07"},
        bridge_plan={
            "status": "shadow_bridge_available_for_manual_review",
            "actual_data_date": "2026-09-07",
            "current_holdings": {"00631L.TW": 0},
            "target_shares": {"00631L.TW": 10},
            "computed": {"bridge_turnover": 0.10},
        },
        heterogeneous_vol={
            "advisory": {
                "active": True,
                "suggested_review": "avoid_adding_00631l_until_manual_review",
            }
        },
    )

    assert report["status"] == "blocked"
    assert "heterogeneous_vol_blocks_00631l_add_and_bridge_adds_00631l" in report["blocking_reasons"]


def test_bridge_blocks_when_date_not_aligned() -> None:
    report = build_review(
        live_signal={"actual_data_date": "2026-09-07"},
        bridge_plan={
            "status": "shadow_bridge_available_for_manual_review",
            "actual_data_date": "2026-09-06",
            "current_holdings": {},
            "target_shares": {},
            "computed": {"bridge_turnover": 0.10},
        },
        heterogeneous_vol={},
    )

    assert report["status"] == "blocked"
    assert "bridge_plan_date_not_aligned_with_live_signal" in report["blocking_reasons"]
