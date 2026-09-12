import json
from pathlib import Path

from scripts.evaluate.build_group_a_plusplus_2609_04917_manual_review_packet import build_packet


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_packet_ready_does_not_grant_approval(tmp_path: Path) -> None:
    bridge = _write(
        tmp_path / "bridge.json",
        {
            "status": "shadow_bridge_available_for_manual_review",
            "actual_data_date": "2026-09-07",
            "limits": {"max_turnover": 0.465},
            "computed": {"bridge_turnover": 0.465},
            "bridge_trades": [{"ticker": "00679B.TWO", "side": "sell", "current_shares": 1, "target_shares": 0}],
        },
    )
    rebalance = _write(
        tmp_path / "rebalance.json",
        {
            "status": "ready_for_human_rebalance_review",
            "checks": {"bridge_adds_00631l": False},
        },
    )
    impact = _write(tmp_path / "impact.json", {"status": "blocked", "blocking_reasons": ["rebalance_review_disallows_auto_rebalance"]})
    joint = _write(tmp_path / "joint.json", {"status": "blocked", "blocking_reasons": ["execution_plan_disallows_execution"]})
    alpha = _write(tmp_path / "alpha.json", {"status": "blocked_for_live_promotion", "blocked_dimensions": ["risk_benchmark"]})

    packet = build_packet(
        bridge_path=bridge,
        rebalance_path=rebalance,
        market_impact_path=impact,
        joint_path=joint,
        alpha_path=alpha,
    )

    assert packet["status"] == "ready_for_manual_review_packet"
    assert packet["decision"]["manual_review_packet_ready"] is True
    assert packet["decision"]["approval_granted"] is False
    assert packet["decision"]["live_execution_allowed"] is False
    assert "joint:execution_plan_disallows_execution" in packet["unresolved_live_blockers"]


def test_packet_blocks_when_bridge_adds_00631l(tmp_path: Path) -> None:
    bridge = _write(tmp_path / "bridge.json", {"status": "shadow_bridge_available_for_manual_review"})
    rebalance = _write(
        tmp_path / "rebalance.json",
        {
            "status": "ready_for_human_rebalance_review",
            "checks": {"bridge_adds_00631l": True},
        },
    )
    empty = _write(tmp_path / "empty.json", {})

    packet = build_packet(
        bridge_path=bridge,
        rebalance_path=rebalance,
        market_impact_path=empty,
        joint_path=empty,
        alpha_path=empty,
    )

    assert packet["status"] == "blocked"
    assert packet["decision"]["manual_review_packet_ready"] is False
