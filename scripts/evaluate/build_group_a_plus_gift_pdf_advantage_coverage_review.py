#!/usr/bin/env python3
"""Review how arXiv 2606.08450 GIFT advantages map into GroupA+ artifacts.

The review is intentionally governance-only. It never trains a model, never
changes target weights, and never promotes a GIFT-derived component to live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = Path("/mnt/c/Users/isaac/Downloads/2606.08450.pdf")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/gift_pdf_advantage_coverage_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/gift_pdf_advantage_coverage/history"
LATEST_DIR = PROJECT_ROOT / "report/group_a_plus/latest"


ADVANTAGES: list[dict[str, Any]] = [
    {
        "id": "constrained_llm_not_trade_decision",
        "paper_keywords": ["Rather than using the LLM to make trading decisions", "no further LLM queries"],
        "expected_artifacts": [
            "llm_state_reward_interface_catalog.json",
            "llm_state_reward_interface_proposal_validation_review.json",
        ],
        "policy": "LLM may propose state/reward interfaces only; no direct actions or target weights.",
    },
    {
        "id": "factor_guided_state_enhancement",
        "paper_keywords": ["Factor-guided State Enhancement", "momentum", "volatility", "downside risk", "liquidity"],
        "expected_artifacts": [
            "llm_state_reward_interface_catalog.json",
            "llm_state_reward_interface_offline_smoke_review.json",
            "llm_state_reward_interface_feature_stability_review.json",
            "llm_state_reward_interface_multi_ticker_smoke_review.json",
        ],
        "policy": "Allowed feature primitives are append-only, bounded, and point-in-time guarded.",
    },
    {
        "id": "risk_rule_reward_shaping",
        "paper_keywords": ["Risk-rule-guided Reward Shaping", "transaction costs", "drawdown", "turnover"],
        "expected_artifacts": [
            "llm_state_reward_interface_frozen_manifest.json",
            "llm_state_reward_interface_frozen_panel_review.json",
            "llm_state_reward_interface_frozen_panel_baseline_shadow_backtest.json",
            "llm_state_reward_interface_downside_tail_decay_param_sweep.json",
        ],
        "policy": "Reward terms are evaluated offline and cannot emit executable targets.",
    },
    {
        "id": "diagnostic_guided_refinement",
        "paper_keywords": ["Diagnostic-guided Refinement", "PPO rollout diagnostics", "revise candidate interfaces"],
        "expected_artifacts": [
            "llm_state_reward_interface_diagnostic_refinement_review.json",
            "llm_state_reward_alignment_remediation_review.json",
            "llm_state_reward_research_shadow_blocker_triage.json",
        ],
        "policy": "DGR is approximated with offline diagnostics; PPO training remains blocked without signed approval.",
    },
    {
        "id": "freeze_before_oos_eval",
        "paper_keywords": ["fixes the selected state-reward interface before evaluation", "test time"],
        "expected_artifacts": [
            "llm_state_reward_interface_frozen_manifest.json",
            "llm_state_reward_interface_frozen_panel.parquet",
            "llm_state_reward_interface_frozen_panel_walk_forward_audit.json",
        ],
        "policy": "Interfaces are frozen before OOS review; test-time LLM updates are rejected.",
    },
    {
        "id": "rolling_window_and_regime_coverage",
        "paper_keywords": ["rolling-window experiments", "diverse market regimes", "portfolio scenarios"],
        "expected_artifacts": [
            "llm_state_reward_interface_windowed_stability_review.json",
            "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review.json",
            "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit.json",
        ],
        "policy": "Coverage is research-only and feeds manual review, not live allocation.",
    },
    {
        "id": "human_and_signed_governance",
        "paper_keywords": ["constraining open-ended generation", "financial knowledge"],
        "expected_artifacts": [
            "llm_state_reward_human_exception_record_draft.json",
            "llm_state_reward_human_exception_approval_record_schema.json",
            "llm_state_reward_human_exception_signed_approval_record_TEMPLATE.json",
            "llm_state_reward_human_exception_signed_approval_validation.json",
            "llm_state_reward_manual_approval_readiness_review.json",
        ],
        "policy": "Signed human approval is mandatory before any training queue or promotion path.",
    },
    {
        "id": "deployment_consistency_blocks_live_promotion",
        "paper_keywords": ["evaluation", "risk-adjusted portfolio performance"],
        "expected_artifacts": [
            "research_shadow_decision_snapshot.json",
            "deployment_consistency_review.json",
            "daily_status.json",
        ],
        "policy": "Research availability never overrides deployment consistency or live-trading guards.",
    },
]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pdf_info(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    text_chunks = []
    for page in reader.pages[:6]:
        text_chunks.append(page.extract_text() or "")
    text = "\n".join(text_chunks)
    normalized_text = " ".join(text.split())
    metadata = reader.metadata or {}
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": _sha256(path),
        "pages": len(reader.pages),
        "title": str(metadata.get("/Title") or ""),
        "arxiv_id": str(metadata.get("/arXivID") or ""),
        "doi": str(metadata.get("/DOI") or ""),
        "first_pages_text_available": bool(text.strip()),
        "first_pages_text_sample_chars": len(text),
        "keyword_hits": {
            "FSE": "Factor-guided State Enhancement" in normalized_text,
            "RRS": "Risk-rule-guided Reward Shaping" in normalized_text,
            "DGR": "Diagnostic-guided Refinement" in normalized_text,
            "no_llm_trade_decisions": "Rather than using the LLM to make trading decisions" in normalized_text,
            "freeze_before_test": "no further LLM queries" in normalized_text or "test time" in normalized_text,
        },
    }


def _artifact_status(name: str) -> dict[str, Any]:
    path = LATEST_DIR / name
    payload = _load_json(path) if path.suffix == ".json" else {}
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "exists": path.exists(),
        "sha256": _sha256(path),
        "status": payload.get("status"),
        "decision": payload.get("decision") if isinstance(payload.get("decision"), dict) else None,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else None,
    }


def _implemented_level(artifacts: list[dict[str, Any]]) -> str:
    exists_count = sum(1 for item in artifacts if item["exists"])
    if exists_count == len(artifacts):
        return "implemented_as_research_shadow_or_governance"
    if exists_count:
        return "partially_implemented"
    return "missing"


def _decision_bool(payload: dict[str, Any], key: str) -> bool:
    decision = payload.get("decision")
    return bool(isinstance(decision, dict) and decision.get(key) is True)


def build_review(*, pdf_path: Path = DEFAULT_PDF, as_of: str = "2026-07-22") -> dict[str, Any]:
    pdf = _pdf_info(pdf_path)
    coverage = []
    for advantage in ADVANTAGES:
        artifacts = [_artifact_status(name) for name in advantage["expected_artifacts"]]
        coverage.append(
            {
                **advantage,
                "artifact_coverage": _implemented_level(artifacts),
                "artifacts": artifacts,
            }
        )

    signed_validation = _load_json(LATEST_DIR / "llm_state_reward_human_exception_signed_approval_validation.json")
    manual_readiness = _load_json(LATEST_DIR / "llm_state_reward_manual_approval_readiness_review.json")
    research_shadow = _load_json(LATEST_DIR / "research_shadow_decision_snapshot.json")
    deployment = _load_json(LATEST_DIR / "deployment_consistency_review.json")

    implemented = sum(
        1
        for item in coverage
        if item["artifact_coverage"] == "implemented_as_research_shadow_or_governance"
    )
    partial = sum(1 for item in coverage if item["artifact_coverage"] == "partially_implemented")
    missing = sum(1 for item in coverage if item["artifact_coverage"] == "missing")

    blockers = []
    if not _decision_bool(signed_validation, "signed_approval_record_valid"):
        blockers.append("missing_or_invalid_signed_human_exception_approval_record")
    if not _decision_bool(signed_validation, "human_exception_approved"):
        blockers.append("human_exception_not_approved")
    if research_shadow.get("status") == "blocked":
        blockers.append("research_shadow_decision_snapshot_blocked")
    if deployment.get("status") == "blocked":
        blockers.append("deployment_consistency_review_blocked")
    if not _decision_bool(manual_readiness, "manual_approval_to_queue_training_allowed"):
        blockers.append("manual_approval_does_not_allow_training_queue")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_gift_pdf_advantage_coverage_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "live_blocked_research_coverage_available" if not missing else "partial_coverage_live_blocked",
        "source_paper": pdf,
        "summary": {
            "advantages_reviewed": len(coverage),
            "implemented_as_research_shadow_or_governance": implemented,
            "partially_implemented": partial,
            "missing": missing,
            "all_advantages_have_artifacts": missing == 0,
            "live_strategy_updated_from_gift": False,
            "golden1_0531_changed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
        },
        "coverage": coverage,
        "live_blockers": blockers,
        "decision": {
            "pdf_advantages_covered_for_research_review": missing == 0,
            "manual_review_required": True,
            "shadow_training_request_allowed": False,
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


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"gift_pdf_advantage_coverage_review_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(review["as_of"])).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--as-of", default="2026-07-22")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    review = build_review(pdf_path=Path(args.pdf), as_of=args.as_of)
    write_review(
        review,
        Path(args.output),
        Path(args.history_dir) if args.history_dir else None,
    )
    print(f"GIFT PDF advantage coverage review: {Path(args.output).resolve()}")
    print(json.dumps(review["summary"], ensure_ascii=False, indent=2))
    if review["live_blockers"]:
        print(json.dumps({"live_blockers": review["live_blockers"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
