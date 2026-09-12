from scripts.evaluate.build_group_a_plus_ppo_runtime_compression_review import build_review


def test_ppo_runtime_compression_review_blocks_strategy_changes() -> None:
    payload = build_review(as_of="2026-08-21")

    assert payload["status"] == "blocked"
    assert payload["decision"]["compression_work_allowed"] is False
    assert payload["decision"]["latency_measurement_allowed"] is True
    assert payload["decision"]["replace_last_ppo_allowed"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert "runtime_bottleneck_not_demonstrated" in payload["blocking_reasons"]
