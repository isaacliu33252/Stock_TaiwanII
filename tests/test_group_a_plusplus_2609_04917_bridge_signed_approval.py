import json
from pathlib import Path

from scripts.evaluate.build_group_a_plusplus_2609_04917_bridge_signed_approval_template import build_template
from scripts.evaluate.validate_group_a_plusplus_2609_04917_bridge_signed_approval import build_validation


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_template_ready_but_does_not_grant_approval(tmp_path: Path) -> None:
    packet = _write(
        tmp_path / "packet.json",
        {
            "decision": {"manual_review_packet_ready": True, "approval_granted": False},
            "candidate": {"actual_data_date": "2026-09-07", "max_turnover_cap": 0.465},
            "trade_preview": [{"ticker": "00679B.TWO", "side": "sell"}],
        },
    )

    report = build_template(packet_path=packet, target_signed_record_path=tmp_path / "signed.json", as_of="2026-09-09")

    assert report["status"] == "unsigned_template_ready_for_manual_completion"
    assert report["decision"]["signed_approval_record_template_ready"] is True
    assert report["decision"]["manual_execution_review_allowed"] is False
    assert report["decision"]["live_promotion_allowed"] is False
    template = report["signed_approval_record_template"]
    assert template["approved_actions"]["allow_manual_execution_review_for_trade_preview"] is False
    assert template["approved_actions"]["allow_00631l_add"] is False


def test_validation_blocks_missing_signed_record(tmp_path: Path) -> None:
    packet = _write(
        tmp_path / "packet.json",
        {"decision": {"manual_review_packet_ready": True, "approval_granted": False}, "candidate": {}, "trade_preview": []},
    )
    template_report = build_template(
        packet_path=packet,
        target_signed_record_path=tmp_path / "signed.json",
        as_of="2026-09-09",
    )
    template = _write(tmp_path / "template.json", template_report)

    review = build_validation(template_path=template, signed_record_path=tmp_path / "missing.json", as_of="2026-09-09")

    assert review["status"] == "blocked"
    assert "missing_bridge_signed_approval_record" in review["blocking_reasons"]
    assert review["decision"]["live_execution_allowed"] is False


def test_validation_accepts_signed_record_for_manual_review_only(tmp_path: Path) -> None:
    packet = _write(
        tmp_path / "packet.json",
        {
            "decision": {"manual_review_packet_ready": True, "approval_granted": False},
            "candidate": {"actual_data_date": "2026-09-07", "max_turnover_cap": 0.465},
            "trade_preview": [{"ticker": "00679B.TWO", "side": "sell"}],
        },
    )
    template_report = build_template(
        packet_path=packet,
        target_signed_record_path=tmp_path / "signed.json",
        as_of="2026-09-09",
    )
    template = _write(tmp_path / "template.json", template_report)
    signed = dict(template_report["signed_approval_record_template"])
    signed["reviewer"] = "manual_reviewer"
    signed["reviewer_role"] = "owner"
    signed["approved_at"] = "2026-09-09T12:00:00"
    signed["expires_at"] = "2026-09-10T12:00:00"
    signed["approved_actions"] = dict(signed["approved_actions"])
    signed["approved_actions"]["allow_manual_execution_review_for_trade_preview"] = True
    signed["acknowledgements"] = {key: True for key in signed["acknowledgements"]}
    signed_record = _write(tmp_path / "signed.json", signed)

    review = build_validation(template_path=template, signed_record_path=signed_record, as_of="2026-09-09")

    assert review["status"] == "valid_for_manual_execution_review_only"
    assert review["decision"]["manual_execution_review_allowed"] is True
    assert review["decision"]["live_execution_allowed"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
