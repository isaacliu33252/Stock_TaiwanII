#!/usr/bin/env python3
"""Build a manual guide for completing the GIFT signed approval record.

This guide is informational only. It does not create a signed approval record,
does not approve training, and does not change live GroupA+ strategy state.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
DEFAULT_TEMPLATE = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_record_TEMPLATE.json"
DEFAULT_CHECKLIST = LATEST_DIR / "gift_signed_approval_checklist_review.json"
DEFAULT_VALIDATION = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_validation.json"
DEFAULT_DEPLOYMENT = LATEST_DIR / "deployment_consistency_review.json"
DEFAULT_TARGET_SIGNED_RECORD = LATEST_DIR / "llm_state_reward_human_exception_signed_approval_record.json"
DEFAULT_OUTPUT_JSON = LATEST_DIR / "gift_signed_approval_manual_completion_guide.json"
DEFAULT_OUTPUT_MD = LATEST_DIR / "gift_signed_approval_manual_completion_guide.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/gift_signed_approval_manual_completion_guide/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _template_payload(template_review: dict[str, Any]) -> dict[str, Any]:
    value = template_review.get("signed_approval_record_template")
    return value if isinstance(value, dict) else {}


def _source(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def _markdown(guide: dict[str, Any]) -> str:
    summary = guide["summary"]
    fields = guide["manual_fields"]
    paths = guide["paths"]
    deployment = guide["deployment_snapshot"]
    lines = [
        "# GIFT Signed Approval Manual Completion Guide",
        "",
        f"- Status: `{guide['status']}`",
        f"- As of: `{guide['as_of']}`",
        f"- Template: `{paths['template']}`",
        f"- Formal signed record target: `{paths['target_signed_record']}`",
        f"- Validator output: `{paths['validation']}`",
        "",
        "## Current State",
        "",
        f"- Manual completion ready: `{summary['manual_completion_ready']}`",
        f"- Signed record exists: `{summary['signed_record_exists']}`",
        f"- Signed record valid: `{summary['signed_approval_record_valid']}`",
        f"- Human exception approved: `{summary['human_exception_approved']}`",
        f"- Broker actionable latest strategy: `{deployment.get('broker_actionable')}`",
        f"- Deployment status: `{deployment.get('status')}`",
        "",
        "## Fields A Human May Fill",
        "",
    ]
    for item in fields["identity_and_dates"]:
        lines.append(f"- `{item}`")
    lines.extend(
        [
            f"- `{fields['single_allowed_true_action']}` may be set to `true` only for non-PPO offline shadow queue review.",
            "",
            "## Acknowledgements Required True",
            "",
        ]
    )
    for item in fields["acknowledgements_required_true"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Must Remain False", ""])
    for item in fields["approved_actions_required_false"]:
        lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            "## Hard Safety Notes",
            "",
            "- This guide does not create or approve the formal signed record.",
            "- `golden1_0531` must remain unchanged.",
            "- `00631L.TW` and `00632R.TW` remain excluded from the GIFT approval scope.",
            "- Training, PPO, live signal output, target weight output, auto rebalance, and live strategy change remain disallowed.",
            "",
        ]
    )
    return "\n".join(lines)


def build_guide(
    *,
    template_path: Path = DEFAULT_TEMPLATE,
    checklist_path: Path = DEFAULT_CHECKLIST,
    validation_path: Path = DEFAULT_VALIDATION,
    deployment_path: Path = DEFAULT_DEPLOYMENT,
    target_signed_record_path: Path = DEFAULT_TARGET_SIGNED_RECORD,
    as_of: str = "2026-07-23",
) -> dict[str, Any]:
    template_review = _load(template_path)
    checklist = _load(checklist_path)
    validation = _load(validation_path)
    deployment = _load(deployment_path)

    template = _template_payload(template_review)
    approved_actions = _dict_value(template, "approved_actions")
    acknowledgements = _dict_value(template, "acknowledgements")
    scope = _dict_value(template, "approval_scope")
    checklist_summary = _dict_value(checklist, "summary")
    validation_summary = _dict_value(validation, "summary")
    deployment_decision = _dict_value(deployment, "decision")
    deployment_computed = _dict_value(deployment, "computed")

    single_allowed_true_action = "approved_actions.allow_non_ppo_offline_shadow_training_queue_review"
    approved_actions_required_false = [
        f"approved_actions.{key}"
        for key, value in sorted(approved_actions.items())
        if key != "allow_non_ppo_offline_shadow_training_queue_review" and value is False
    ]
    status = (
        "ready_for_human_completion"
        if checklist_summary.get("manual_completion_ready") is True
        and validation_summary.get("signed_approval_record_valid") is not True
        else "review_required"
    )

    guide = {
        "schema_version": 1,
        "report_type": "group_a_plus_gift_signed_approval_manual_completion_guide",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": status,
        "policy": "manual_guide_only_no_approval_no_training_no_live_action",
        "paths": {
            "template": str(template_path),
            "checklist": str(checklist_path),
            "validation": str(validation_path),
            "deployment_consistency_review": str(deployment_path),
            "target_signed_record": str(target_signed_record_path),
        },
        "sources": {
            "template": _source(template_path),
            "checklist": _source(checklist_path),
            "validation": _source(validation_path),
            "deployment_consistency_review": _source(deployment_path),
            "target_signed_record": _source(target_signed_record_path),
        },
        "summary": {
            "manual_completion_ready": checklist_summary.get("manual_completion_ready"),
            "manual_completion_pending": checklist_summary.get("manual_completion_pending"),
            "signed_record_exists": checklist_summary.get("signed_record_exists"),
            "signed_approval_record_valid": validation_summary.get("signed_approval_record_valid"),
            "human_exception_approved": validation_summary.get("human_exception_approved"),
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "manual_fields": {
            "identity_and_dates": ["reviewer", "reviewer_role", "approved_at", "expires_at"],
            "single_allowed_true_action": single_allowed_true_action,
            "acknowledgements_required_true": sorted(acknowledgements.keys()),
            "approved_actions_required_false": approved_actions_required_false,
        },
        "scope_snapshot": {
            "record_id": template.get("record_id"),
            "source_draft_sha256": template.get("source_draft_sha256"),
            "approval_scope": scope,
            "excluded_tickers": scope.get("excluded_tickers") or [],
        },
        "deployment_snapshot": {
            "status": deployment.get("status"),
            "broker_actionable": deployment_decision.get("broker_actionable"),
            "blocking_reasons": deployment.get("blocking_reasons") or [],
            "warning_reasons": deployment.get("warning_reasons") or [],
            "target_weights": deployment_computed.get("target_weights") or {},
            "execution_target_shares": deployment_computed.get("execution_target_shares") or {},
        },
        "decision": {
            "creates_signed_record": False,
            "signed_approval_record_valid": False,
            "human_exception_approved": False,
            "non_ppo_shadow_queue_review_allowed": False,
            "training_queue_allowed": False,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    return guide


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"gift_signed_approval_manual_completion_guide_{as_of.replace('-', '')}.json"


def write_outputs(
    guide: dict[str, Any],
    *,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_md: Path = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(guide), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(guide["as_of"])).write_text(
            json.dumps(guide, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--checklist", default=str(DEFAULT_CHECKLIST))
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--deployment", default=str(DEFAULT_DEPLOYMENT))
    parser.add_argument("--target-signed-record", default=str(DEFAULT_TARGET_SIGNED_RECORD))
    parser.add_argument("--as-of", default="2026-07-23")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    guide = build_guide(
        template_path=_resolve(args.template),
        checklist_path=_resolve(args.checklist),
        validation_path=_resolve(args.validation),
        deployment_path=_resolve(args.deployment),
        target_signed_record_path=_resolve(args.target_signed_record),
        as_of=args.as_of,
    )
    write_outputs(
        guide,
        output_json=_resolve(args.output_json),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"GIFT signed approval manual completion guide: {_resolve(args.output_json)}")
    print(
        json.dumps(
            {
                "status": guide["status"],
                "manual_completion_ready": guide["summary"]["manual_completion_ready"],
                "signed_record_exists": guide["summary"]["signed_record_exists"],
                "signed_approval_record_valid": guide["summary"]["signed_approval_record_valid"],
                "creates_signed_record": guide["decision"]["creates_signed_record"],
                "training_queue_allowed": guide["decision"]["training_queue_allowed"],
                "keep_golden1_0531_unchanged": guide["decision"]["keep_golden1_0531_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
