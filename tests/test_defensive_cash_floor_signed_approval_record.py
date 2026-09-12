from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_defensive_cash_floor_signed_approval_record_template import (
    REQUIRED_ACKNOWLEDGEMENTS,
    build_template,
    write_template,
)
from scripts.evaluate.validate_group_a_plus_defensive_cash_floor_signed_approval_record import (
    build_validation,
    write_validation,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _promotion_review(path: Path) -> Path:
    return _write(
        path,
        {
            "status": "manual_signature_pending",
            "candidate": {
                "variant": "cash55_risk7_tail1",
                "cash_floor": 0.55,
                "total_risk_min": 7,
                "tail_risk_min": 1,
            },
            "decision": {
                "signed_review_ready": True,
                "manual_signature_valid": False,
                "target_weight_change_allowed": False,
            },
        },
    )


def _template(path: Path, promotion_path: Path) -> dict:
    return build_template(promotion_review_path=promotion_path, as_of="2026-08-07", target_signed_record_path=path)


def _signed(template_report: dict, **overrides: object) -> dict:
    record = dict(template_report["signed_approval_record_template"])
    record["reviewer"] = "manual_reviewer"
    record["reviewer_role"] = "research_governance"
    record["approved_at"] = "2026-08-07T09:00:00"
    record["expires_at"] = "2026-08-14T09:00:00"
    record["approved_actions"] = dict(record["approved_actions"])
    record["approved_actions"]["allow_guarded_candidate_target_output"] = True
    record["acknowledgements"] = {key: True for key in REQUIRED_ACKNOWLEDGEMENTS}
    record["notes"] = "manual approval for guarded candidate target output only"
    for key, value in overrides.items():
        record[key] = value
    return record


def test_template_is_ready_but_unsigned(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")

    report = build_template(promotion_review_path=promotion, as_of="2026-08-07")

    assert report["status"] == "unsigned_template_ready_for_manual_completion"
    assert report["decision"]["signed_approval_record_template_ready"] is True
    assert report["decision"]["manual_signature_valid"] is False
    assert report["decision"]["target_weight_change_allowed"] is False


def test_validator_accepts_valid_signed_record(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_report = _template(tmp_path / "signed.json", promotion)
    template_path = _write(tmp_path / "template.json", template_report)
    signed_path = _write(tmp_path / "signed.json", _signed(template_report))

    result = build_validation(template_path=template_path, signed_record_path=signed_path, as_of="2026-08-07")

    assert result["status"] == "valid_for_guarded_candidate_target_output"
    assert result["decision"]["manual_signature_valid"] is True
    assert result["decision"]["target_weight_change_allowed"] is True
    assert result["decision"]["auto_rebalance_allowed"] is False
    assert result["decision"]["allow_00631l_add"] is False


def test_validator_accepts_timezone_aware_signed_dates(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_report = _template(tmp_path / "signed.json", promotion)
    template_path = _write(tmp_path / "template.json", template_report)
    signed = _signed(
        template_report,
        approved_at="2026-08-07T09:00:00+08:00",
        expires_at="2026-08-14T09:00:00+08:00",
    )
    signed_path = _write(tmp_path / "signed.json", signed)

    result = build_validation(template_path=template_path, signed_record_path=signed_path, as_of="2026-08-07")

    assert result["status"] == "valid_for_guarded_candidate_target_output"
    assert result["decision"]["manual_signature_valid"] is True


def test_validator_blocks_missing_record(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_path = _write(tmp_path / "template.json", _template(tmp_path / "signed.json", promotion))

    result = build_validation(template_path=template_path, signed_record_path=tmp_path / "missing.json")

    assert result["status"] == "blocked"
    assert "missing_signed_approval_record" in result["blocking_reasons"]
    assert result["decision"]["manual_signature_valid"] is False


def test_validator_blocks_source_hash_mismatch(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_report = _template(tmp_path / "signed.json", promotion)
    template_path = _write(tmp_path / "template.json", template_report)
    signed = _signed(template_report, source_promotion_review_sha256="different")
    signed_path = _write(tmp_path / "signed.json", signed)

    result = build_validation(template_path=template_path, signed_record_path=signed_path)

    assert "signed_record_source_promotion_review_sha256_mismatch" in result["blocking_reasons"]
    assert result["decision"]["target_weight_change_allowed"] is False


def test_validator_blocks_missing_acknowledgement(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_report = _template(tmp_path / "signed.json", promotion)
    template_path = _write(tmp_path / "template.json", template_report)
    signed = _signed(template_report)
    signed["acknowledgements"]["year_2024_no_trigger_limitation_acknowledged"] = False
    signed_path = _write(tmp_path / "signed.json", signed)

    result = build_validation(template_path=template_path, signed_record_path=signed_path)

    assert (
        "signed_record_missing_acknowledgement:year_2024_no_trigger_limitation_acknowledged"
        in result["blocking_reasons"]
    )


def test_validator_blocks_forbidden_actions(tmp_path: Path) -> None:
    promotion = _promotion_review(tmp_path / "promotion.json")
    template_report = _template(tmp_path / "signed.json", promotion)
    template_path = _write(tmp_path / "template.json", template_report)
    signed = _signed(template_report)
    signed["approved_actions"]["allow_auto_rebalance"] = True
    signed["approved_actions"]["allow_00631l_add"] = True
    signed_path = _write(tmp_path / "signed.json", signed)

    result = build_validation(template_path=template_path, signed_record_path=signed_path)

    assert "signed_record_forbidden_action_not_false:allow_auto_rebalance" in result["blocking_reasons"]
    assert "signed_record_forbidden_action_not_false:allow_00631l_add" in result["blocking_reasons"]


def test_write_template_and_validation_write_history(tmp_path: Path) -> None:
    template = {"as_of": "2026-08-07"}
    validation = {"as_of": "2026-08-07"}

    write_template(template, tmp_path / "latest" / "template.json", tmp_path / "template_history")
    write_validation(validation, tmp_path / "latest" / "validation.json", tmp_path / "validation_history")

    assert (tmp_path / "template_history" / "defensive_cash_floor_signed_approval_record_template_20260807.json").exists()
    assert (tmp_path / "validation_history" / "defensive_cash_floor_signed_approval_validation_20260807.json").exists()
