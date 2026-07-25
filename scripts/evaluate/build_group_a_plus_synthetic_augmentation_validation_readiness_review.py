#!/usr/bin/env python3
"""Build a research-only synthetic augmentation validation readiness review.

Inspired by arXiv 2604.14498. This checks whether synthetic/GMM/scenario
augmentation has passed the validation gates needed before it can influence
GroupA+ model promotion or target weights. It never changes target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINSTRESSTS = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_decision_snapshot.json"
DEFAULT_HMM_WJ = PROJECT_ROOT / "report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json"
DEFAULT_DYNAMIC_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json"
DEFAULT_DENSITY = PROJECT_ROOT / "report/group_a_plus/latest/density_head_tail_risk_advisory.json"
DEFAULT_VALIDATION_AUDIT = PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_audit.json"
DEFAULT_PROMOTION_GATE: Path | None = None
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/synthetic_augmentation_validation_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _promotion_status(promotion_gate: dict[str, Any]) -> str | None:
    return (
        promotion_gate.get("status")
        or promotion_gate.get("decision")
        or promotion_gate.get("promotion_decision")
        or promotion_gate.get("gate_status")
    )


def build_review(
    *,
    finstressts_path: Path,
    hmm_wj_path: Path,
    dynamic_cvar_path: Path,
    density_path: Path,
    validation_audit_path: Path,
    promotion_gate_path: Path | None,
) -> dict[str, Any]:
    finstressts = _load(finstressts_path)
    hmm_wj = _load(hmm_wj_path)
    dynamic_cvar = _load(dynamic_cvar_path)
    density = _load(density_path)
    validation_audit = _load(validation_audit_path)
    promotion_gate = _load(promotion_gate_path) if promotion_gate_path is not None else {}

    fin_decision = _decision(finstressts)
    hmm_decision = _decision(hmm_wj)
    dynamic_decision = _decision(dynamic_cvar)
    density_best = density.get("best_heads") or {}
    promotion_status = _promotion_status(promotion_gate)

    blockers: list[str] = []
    warnings: list[str] = []

    missing = [
        name
        for name, payload in {
            "finstressts_decision_snapshot": finstressts,
            "hmm_wj_synthetic_scenario_readiness_review": hmm_wj,
            "dynamic_cvar_tail_cost_readiness_review": dynamic_cvar,
            "density_head_tail_risk_advisory": density,
            "synthetic_augmentation_validation_audit": validation_audit,
        }.items()
        if not payload
    ]
    if missing:
        blockers.append("missing_required_inputs:" + ",".join(sorted(missing)))

    audit_method = validation_audit.get("method") or {}
    audit_summary = validation_audit.get("summary") or {}
    audit_decision = validation_audit.get("decision") or {}
    if audit_method.get("size_matched_null_augmentation_implemented") is not True:
        blockers.append("size_matched_null_augmentation_missing")
    if audit_method.get("block_permutation_test_implemented") is not True:
        blockers.append("block_permutation_test_missing")
    if audit_method.get("walk_forward_oos_panel_used") is not True:
        blockers.append("walk_forward_oos_synthetic_validation_missing")
    if audit_summary.get("validation_passed") is not True:
        blockers.append("synthetic_augmentation_validation_audit_failed")
    if audit_decision.get("directional_synthetic_alpha_allowed") is not True:
        blockers.append("directional_synthetic_alpha_default_blocked")

    if finstressts.get("status") == "blocked":
        blockers.append("finstressts_snapshot_blocked")
    if hmm_wj.get("status") == "blocked":
        blockers.append("hmm_wj_scenario_readiness_blocked")
    if hmm_decision.get("can_generate_scenarios_for_decision") is not True:
        blockers.append("scenario_generator_not_decision_ready")
    if dynamic_cvar.get("status") == "blocked":
        blockers.append("dynamic_cvar_tail_cost_readiness_blocked")
    if dynamic_decision.get("tail_cost_readiness_ready") is not True:
        blockers.append("tail_cost_readiness_not_ready")
    if density_best.get("gmm_status") == "unstable_across_windows_research_only":
        blockers.append("density_tail_model_unstable_research_only")
    if promotion_status and promotion_status not in {"passed", "ok", "approved"}:
        blockers.append(f"promotion_gate_{promotion_status}")
    if promotion_gate_path is None or not promotion_gate:
        warnings.append("promotion_gate_unavailable_optional")

    if fin_decision.get("allow_00631l_add") is True:
        warnings.append("finstressts_allows_00631l_add_unexpected_for_synthetic_gate")
    if density_best.get("recommended_research_baseline") != "gaussian_residual_head":
        warnings.append("density_head_recommended_baseline_changed")

    as_of = (
        dynamic_cvar.get("as_of")
        or hmm_wj.get("as_of")
        or _nested(finstressts, "summary", "as_of")
        or "2026-07-20"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_synthetic_augmentation_validation_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_synthetic_augmentation_validation_no_synthetic_alpha_no_weight_change",
        "status": "blocked" if blockers else "research_ready",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2604.14498.pdf",
            "title": "Improving Machine Learning Performance with Synthetic Augmentation",
            "imported_concepts": [
                "size_matched_null_augmentation_gate",
                "finite_sample_block_permutation_test",
                "task_type_restriction_for_synthetic_data",
                "rare_regime_metric_alignment",
            ],
            "not_imported": [
                "synthetic_directional_alpha",
                "bootstrap_copula_vae_diffusion_timegan_live_signals",
                "automatic_target_weight_change",
                "unvalidated_generator_promotion",
            ],
        },
        "component_readiness": {
            "finstressts": {
                "status": finstressts.get("status"),
                "allow_00631l_add": fin_decision.get("allow_00631l_add"),
            },
            "hmm_wj": {
                "status": hmm_wj.get("status"),
                "all_required_tickers_ready": _nested(hmm_wj, "data_readiness", "all_required_tickers_ready"),
                "can_generate_scenarios_for_decision": hmm_decision.get("can_generate_scenarios_for_decision"),
            },
            "dynamic_cvar_tail_cost": {
                "status": dynamic_cvar.get("status"),
                "tail_cost_readiness_ready": dynamic_decision.get("tail_cost_readiness_ready"),
                "dynamic_optimizer_ready": dynamic_decision.get("dynamic_optimizer_ready"),
            },
            "density_head_tail_risk": {
                "status": density.get("status"),
                "recommended_research_baseline": density_best.get("recommended_research_baseline"),
                "gmm_status": density_best.get("gmm_status"),
            },
            "promotion_gate": {
                "status": promotion_status,
                "raw_status": promotion_gate.get("status"),
                "decision": promotion_gate.get("decision"),
                "promotion_decision": promotion_gate.get("promotion_decision"),
            },
            "validation_audit": {
                "status": validation_audit.get("status"),
                "validation_passed": audit_summary.get("validation_passed"),
                "passed_task_count": audit_summary.get("passed_task_count"),
                "task_count": audit_summary.get("task_count"),
                "directional_synthetic_alpha_tested": audit_summary.get("directional_synthetic_alpha_tested"),
                "directional_validation_passed": audit_summary.get("directional_validation_passed"),
                "rare_validation_passed": audit_summary.get("rare_validation_passed"),
            },
        },
        "validation_readiness": {
            "size_matched_null_augmentation_implemented": bool(
                audit_method.get("size_matched_null_augmentation_implemented")
            ),
            "block_permutation_test_implemented": bool(audit_method.get("block_permutation_test_implemented")),
            "walk_forward_oos_synthetic_validation_passed": bool(audit_summary.get("validation_passed")),
            "directional_audit_tested": bool(audit_summary.get("directional_synthetic_alpha_tested")),
            "directional_audit_passed": bool(audit_summary.get("directional_validation_passed")),
            "rare_regime_audit_passed": bool(audit_summary.get("rare_validation_passed")),
            "rare_regime_metric_alignment_documented": True,
            "directional_synthetic_alpha_allowed": False,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Synthetic augmentation is validation-governance only. Directional synthetic alpha "
                "and generator promotion remain blocked until size-matched null augmentation, "
                "walk-forward OOS, and block permutation tests are implemented and passed."
            ),
            "synthetic_validation_ready": False,
            "directional_synthetic_alpha_allowed": False,
            "synthetic_generator_promotion_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "finstressts": str(finstressts_path),
            "hmm_wj": str(hmm_wj_path),
            "dynamic_cvar_tail_cost": str(dynamic_cvar_path),
            "density_head_tail_risk": str(density_path),
            "validation_audit": str(validation_audit_path),
            "promotion_gate": str(promotion_gate_path) if promotion_gate_path is not None else None,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("as_of")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finstressts", default=str(DEFAULT_FINSTRESSTS))
    parser.add_argument("--hmm-wj", default=str(DEFAULT_HMM_WJ))
    parser.add_argument("--dynamic-cvar", default=str(DEFAULT_DYNAMIC_CVAR))
    parser.add_argument("--density", default=str(DEFAULT_DENSITY))
    parser.add_argument("--validation-audit", default=str(DEFAULT_VALIDATION_AUDIT))
    parser.add_argument("--promotion-gate", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        finstressts_path=_resolve(args.finstressts),
        hmm_wj_path=_resolve(args.hmm_wj),
        dynamic_cvar_path=_resolve(args.dynamic_cvar),
        density_path=_resolve(args.density),
        validation_audit_path=_resolve(args.validation_audit),
        promotion_gate_path=_resolve(args.promotion_gate) if args.promotion_gate else None,
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output, history_dir)
    print(f"Synthetic augmentation validation readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "synthetic_validation_ready": review["decision"]["synthetic_validation_ready"],
                "directional_synthetic_alpha_allowed": review["decision"]["directional_synthetic_alpha_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
