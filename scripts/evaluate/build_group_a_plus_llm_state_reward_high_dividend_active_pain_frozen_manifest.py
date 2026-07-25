#!/usr/bin/env python3
"""Freeze the high-dividend active-pain GIFT redesign for offline review."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_DGR = LATEST / "llm_state_reward_interface_high_dividend_active_pain_dgr_review.json"
DEFAULT_SMOKE = LATEST / "llm_state_reward_interface_high_dividend_active_pain_offline_smoke.json"
DEFAULT_OUTPUT = LATEST / "llm_state_reward_interface_high_dividend_active_pain_frozen_manifest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_frozen_manifest/history"
PROPOSAL_ID = "gift_research_high_dividend_active_pain_v1"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(
    *,
    dgr_path: Path = DEFAULT_DGR,
    smoke_path: Path = DEFAULT_SMOKE,
    freeze_id: str = "group_a_plus_gift_high_dividend_active_pain_v3_tuned_20260721",
    as_of: str = "2026-07-21",
) -> dict[str, Any]:
    dgr = _load(dgr_path)
    smoke = _load(smoke_path)
    blockers: list[str] = []
    if not dgr:
        blockers.append("missing_high_dividend_active_pain_dgr")
    elif dgr.get("status") != "available_for_manual_offline_review":
        blockers.append(f"dgr_not_available:{dgr.get('status')}")
    if not smoke:
        blockers.append("missing_high_dividend_active_pain_offline_smoke")
    elif smoke.get("status") != "available_for_manual_offline_review":
        blockers.append(f"offline_smoke_not_available:{smoke.get('status')}")
    if (dgr.get("decision") or {}).get("high_dividend_active_pain_dgr_passed") is not True:
        blockers.append("dgr_not_green")
    if (smoke.get("decision") or {}).get("high_dividend_active_pain_offline_smoke_passed") is not True:
        blockers.append("offline_smoke_not_passed")
    if smoke.get("proposal_id") != PROPOSAL_ID or dgr.get("proposal_id") != PROPOSAL_ID:
        blockers.append("proposal_id_mismatch")

    params = {
        "active_penalty_scale": float((smoke.get("inputs") or {}).get("active_penalty_scale", 20.0)),
        "drawdown_scale": float((smoke.get("inputs") or {}).get("drawdown_scale", 1.0)),
        "return_pain_scale": float((smoke.get("inputs") or {}).get("return_pain_scale", 4.0)),
        "concentration_scale": float((smoke.get("inputs") or {}).get("concentration_scale", 0.1)),
    }
    freeze_payload = {
        "freeze_id": freeze_id,
        "proposal_id": PROPOSAL_ID,
        "selected_label": "v3_high_dividend_active_pain_tuned",
        "state_columns": [
            "active_bucket_weight",
            "active_bucket_return_contribution",
            "active_bucket_drawdown_depth",
            "reward_signal_concentration_hhi",
            "high_dividend_active_pain",
            "drawdown_depth",
            "realized_volatility",
        ],
        "reward_columns": [
            "active_bucket_drawdown_penalty",
            "original_reward_proxy",
            "redesigned_reward_proxy",
        ],
        "reward_params": params,
        "reward_alignment_objective": "future_high_dividend_active_pain_alignment",
        "objective_alignment": (dgr.get("summary") or {}).get(
            "redesigned_reward_alignment_to_future_high_dividend_active_pain"
        ),
        "objective_abs_alignment": abs(
            float((dgr.get("summary") or {}).get("redesigned_reward_alignment_to_future_high_dividend_active_pain") or 0.0)
        ),
        "mean_reward_snr": (dgr.get("summary") or {}).get("reward_snr_abs_mean_over_std"),
        "offline_smoke_summary": (smoke.get("summary") or {}).get("high_dividend_active_pain_offline_smoke"),
        "source_hashes": {
            "dgr_review": {"path": str(dgr_path), "sha256": _sha256_file(dgr_path), "exists": dgr_path.exists()},
            "offline_smoke": {"path": str(smoke_path), "sha256": _sha256_file(smoke_path), "exists": smoke_path.exists()},
        },
    }
    frozen_hash = hashlib.sha256(
        json.dumps(freeze_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_frozen_manifest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "frozen_for_manual_offline_review",
        "policy": "frozen_v3_interface_manifest_only_no_model_training_no_live_action",
        "freeze": freeze_payload | {"frozen_manifest_sha256": frozen_hash},
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "frozen_for_manual_offline_review": not blockers,
            "offline_walk_forward_panel_export_allowed": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_frozen_manifest_{stamp}.json"


def write_manifest(manifest: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, manifest.get("as_of")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-21")
    parser.add_argument("--dgr", default=str(DEFAULT_DGR))
    parser.add_argument("--smoke", default=str(DEFAULT_SMOKE))
    parser.add_argument("--freeze-id", default="group_a_plus_gift_high_dividend_active_pain_v3_tuned_20260721")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    manifest = build_manifest(
        dgr_path=_resolve(args.dgr),
        smoke_path=_resolve(args.smoke),
        freeze_id=args.freeze_id,
        as_of=args.as_of,
    )
    write_manifest(manifest, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain frozen manifest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "freeze_id": manifest["freeze"]["freeze_id"],
                "frozen_manifest_sha256": manifest["freeze"]["frozen_manifest_sha256"],
                "promote_to_live": manifest["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
