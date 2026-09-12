#!/usr/bin/env python3
"""Build a PTQ calibration readiness review for GroupA+.

This is a research/governance artifact based on arXiv:2608.12259. It does not
quantize a model and does not authorize target-weight changes. It records the
minimum evidence required before any low-precision neural model can be wired
into GroupA+ latest-strategy inference.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF_PATH = Path("/mnt/c/Users/isaac/Downloads/2608.12259.pdf")
DEFAULT_PTQ_EVAL = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_eval.json"
DEFAULT_ROBUSTNESS = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_robustness_sweep.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_readiness_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/ptq_calibration_readiness_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/ptq_calibration_readiness/history"

MAX_W8A8_DAMAGE_PCT = 0.03
MAX_W4_WEIGHT_ONLY_DAMAGE_PCT = 0.05
MAX_W4A4_DAMAGE_PCT = 0.05
MAX_OUT_OF_ENVELOPE_RATE = 0.10


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _damage_pct(metric: float | None, quantized_metric: float | None) -> float | None:
    if metric is None or quantized_metric is None or metric == 0:
        return None
    return max(0.0, (metric - quantized_metric) / abs(metric))


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def build_review(
    *,
    as_of: str,
    pdf_path: Path = DEFAULT_PDF_PATH,
    ptq_eval_path: Path = DEFAULT_PTQ_EVAL,
    robustness_path: Path = DEFAULT_ROBUSTNESS,
) -> dict[str, Any]:
    ptq_eval = _load_json(ptq_eval_path)
    robustness = _load_json(robustness_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not pdf_path.exists():
        warnings.append("source_pdf_not_found_local")

    if not ptq_eval:
        blockers.append("missing_ptq_calibration_eval")

    model_name = ptq_eval.get("model_name")
    quantization_applicability = (
        ptq_eval.get("quantization_applicability")
        if isinstance(ptq_eval.get("quantization_applicability"), dict)
        else {}
    )
    full_precision_metric = _float_or_none(ptq_eval.get("full_precision_metric"))
    calibration_period = ptq_eval.get("calibration_period")
    test_period = ptq_eval.get("test_period")
    activation_method = ptq_eval.get("activation_calibration_method")
    fallback_precision = ptq_eval.get("fallback_precision")
    out_of_envelope_rate = _float_or_none(ptq_eval.get("out_of_envelope_rate"))

    if ptq_eval:
        if quantization_applicability.get("torch_ptq_applicable") is False:
            blockers.append("torch_ptq_not_applicable_for_current_model_framework")
        if quantization_applicability.get("live_deployment_backend_validated") is False:
            warnings.append("live_quantized_backend_not_validated")
        if not model_name:
            blockers.append("missing_model_name")
        if full_precision_metric is None:
            blockers.append("missing_full_precision_metric")
        if not calibration_period:
            blockers.append("missing_calibration_period")
        if not test_period:
            blockers.append("missing_test_period")
        if not activation_method:
            blockers.append("missing_activation_calibration_method")
        if not fallback_precision:
            blockers.append("missing_fallback_precision")
        if out_of_envelope_rate is None:
            blockers.append("missing_out_of_envelope_rate")
        elif out_of_envelope_rate > MAX_OUT_OF_ENVELOPE_RATE:
            blockers.append("calibration_envelope_exceeded_too_often")

    quantized_results = ptq_eval.get("quantized_results") if isinstance(ptq_eval.get("quantized_results"), dict) else {}
    precision_checks: dict[str, dict[str, Any]] = {}
    thresholds = {
        "W8A8": MAX_W8A8_DAMAGE_PCT,
        "W4_weight_only": MAX_W4_WEIGHT_ONLY_DAMAGE_PCT,
        "W4A4": MAX_W4A4_DAMAGE_PCT,
    }

    for precision, max_damage in thresholds.items():
        result = quantized_results.get(precision) if isinstance(quantized_results, dict) else None
        metric = _float_or_none(_nested(result or {}, "metric"))
        damage = _float_or_none(_nested(result or {}, "damage_pct_of_fp32_signal"))
        if damage is None:
            damage = _damage_pct(full_precision_metric, metric)
        has_percentile_sweep = bool(_nested(result or {}, "percentile_sweep_tested"))
        layerwise_review = bool(_nested(result or {}, "layerwise_exception_reviewed"))

        status = "missing"
        reasons: list[str] = []
        if result is None:
            reasons.append(f"missing_{precision}_result")
        elif metric is None:
            reasons.append(f"missing_{precision}_metric")
        elif damage is None:
            reasons.append(f"missing_{precision}_damage_pct")
        elif damage > max_damage:
            reasons.append(f"{precision}_damage_exceeds_threshold")
        else:
            status = "passed"

        if precision == "W4A4":
            if not has_percentile_sweep:
                reasons.append("W4A4_missing_percentile_sweep")
            if not layerwise_review:
                reasons.append("W4A4_missing_layerwise_exception_review")
            if activation_method == "abs_max":
                reasons.append("W4A4_abs_max_activation_calibration_not_allowed")
            if reasons:
                status = "blocked"
        elif reasons:
            status = "blocked"

        precision_checks[precision] = {
            "status": status,
            "metric": metric,
            "damage_pct_of_fp32_signal": damage,
            "max_allowed_damage_pct": max_damage,
            "percentile_sweep_tested": has_percentile_sweep,
            "layerwise_exception_reviewed": layerwise_review,
            "reasons": reasons,
        }
        blockers.extend(reasons)

    promotable_precisions = [
        precision for precision, check in precision_checks.items() if check["status"] == "passed"
    ]
    if not promotable_precisions:
        blockers.append("no_quantized_precision_passed_readiness_gate")

    robustness_summary: dict[str, Any] = {"path": str(robustness_path), "exists": bool(robustness)}
    if robustness:
        robustness_decision = robustness.get("decision") if isinstance(robustness.get("decision"), dict) else {}
        robustness_summary.update(
            {
                "report_type": robustness.get("report_type"),
                "fake_quant_research_passed": robustness_decision.get("fake_quant_research_passed"),
                "dynamic_quant_backend_smoke_available": robustness_decision.get(
                    "dynamic_quant_backend_smoke_available"
                ),
                "student_vs_original": robustness.get("student_vs_original"),
                "live_blocking_reasons": robustness_decision.get("live_blocking_reasons", []),
            }
        )
        if robustness_decision.get("fake_quant_research_passed") is not True:
            blockers.append("ptq_robustness_sweep_failed")
        for reason in robustness_decision.get("live_blocking_reasons", []):
            warnings.append(f"robustness_live_blocker:{reason}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ptq_calibration_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "research_ready",
        "policy": "research_governance_only_no_quantized_live_inference_no_weight_change",
        "source_paper": {
            "file": str(pdf_path),
            "title": "Calibration Bets on the Past: Post-Training Quantization for Financial Time-Series Forecasting",
            "arxiv": "2608.12259v1",
            "paper_date": "2026-08-12",
            "imported_concepts": [
                "activation_calibration_readiness_gate",
                "calibration_envelope_monitor",
                "prefer_w8a8_or_w4_weight_only_before_w4a4",
                "w4a4_requires_percentile_sweep",
                "layerwise_exception_review_for_sensitive_layers",
            ],
            "not_imported": [
                "ptq_as_alpha_signal",
                "automatic_target_weight_change",
                "abs_max_w4a4_default",
                "static_low_bit_activation_ranges_without_shift_monitor",
            ],
        },
        "inputs": {
            "source_pdf": _artifact(pdf_path),
            "ptq_eval": _artifact(ptq_eval_path),
        },
        "ptq_eval_summary": {
            "model_name": model_name,
            "model_framework": ptq_eval.get("model_framework"),
            "model_artifact_type": ptq_eval.get("model_artifact_type"),
            "torch_ptq_applicable": quantization_applicability.get("torch_ptq_applicable"),
            "full_precision_metric": full_precision_metric,
            "calibration_period": calibration_period,
            "test_period": test_period,
            "activation_calibration_method": activation_method,
            "fallback_precision": fallback_precision,
            "out_of_envelope_rate": out_of_envelope_rate,
            "max_out_of_envelope_rate": MAX_OUT_OF_ENVELOPE_RATE,
        },
        "robustness_summary": robustness_summary,
        "precision_checks": precision_checks,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "quantized_inference_allowed": False,
            "promotable_precisions_for_research_review": promotable_precisions,
            "w4a4_live_allowed": False,
            "requires_manual_approval_before_any_quantized_inference": True,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
            "keep_latest_strategy_weights_unchanged": True,
            "recommended_use": "deployment_readiness_gate_for_future_neural_model_quantization",
        },
    }


def _write_md(review: dict[str, Any], path: Path) -> None:
    checks = review["precision_checks"]
    lines = [
        "# 2608.12259 PTQ Calibration Readiness Review",
        "",
        f"- Generated: `{review['generated_at']}`",
        f"- Status: `{review['status']}`",
        f"- Policy: `{review['policy']}`",
        f"- Recommended use: `{review['decision']['recommended_use']}`",
        "",
        "## Decision",
        "",
        f"- Quantized inference allowed: `{review['decision']['quantized_inference_allowed']}`",
        f"- Promote to live: `{review['decision']['promote_to_live']}`",
        f"- Target weight change allowed: `{review['decision']['target_weight_change_allowed']}`",
        f"- Auto rebalance allowed: `{review['decision']['auto_rebalance_allowed']}`",
        f"- Keep latest strategy weights unchanged: `{review['decision']['keep_latest_strategy_weights_unchanged']}`",
        "",
        "## PTQ Evaluation Summary",
        "",
        f"- Model name: `{review['ptq_eval_summary']['model_name']}`",
        f"- Model framework: `{review['ptq_eval_summary']['model_framework']}`",
        f"- Model artifact type: `{review['ptq_eval_summary']['model_artifact_type']}`",
        f"- Torch PTQ applicable: `{review['ptq_eval_summary']['torch_ptq_applicable']}`",
        f"- Full precision metric: `{review['ptq_eval_summary']['full_precision_metric']}`",
        f"- Calibration period: `{review['ptq_eval_summary']['calibration_period']}`",
        f"- Test period: `{review['ptq_eval_summary']['test_period']}`",
        f"- Activation calibration: `{review['ptq_eval_summary']['activation_calibration_method']}`",
        f"- Out-of-envelope rate: `{review['ptq_eval_summary']['out_of_envelope_rate']}`",
        "",
        "## Precision Checks",
        "",
    ]
    for precision, check in checks.items():
        lines.extend(
            [
                f"### {precision}",
                "",
                f"- Status: `{check['status']}`",
                f"- Metric: `{check['metric']}`",
                f"- Damage pct of FP32 signal: `{check['damage_pct_of_fp32_signal']}`",
                f"- Max allowed damage pct: `{check['max_allowed_damage_pct']}`",
                f"- Percentile sweep tested: `{check['percentile_sweep_tested']}`",
                f"- Layerwise exception reviewed: `{check['layerwise_exception_reviewed']}`",
                "",
            ]
        )
    lines.extend(["## Blocking Reasons", ""])
    lines.extend(f"- `{reason}`" for reason in review["blocking_reasons"])
    robustness = review.get("robustness_summary") or {}
    lines.extend(
        [
            "",
            "## Robustness Summary",
            "",
            f"- Exists: `{robustness.get('exists')}`",
            f"- Fake-quant research passed: `{robustness.get('fake_quant_research_passed')}`",
            f"- Dynamic quant backend smoke available: `{robustness.get('dynamic_quant_backend_smoke_available')}`",
            f"- Student/original: `{(robustness.get('student_vs_original') or {}).get('ratio')}`",
        ]
    )
    lines.extend(["", "## Warning Reasons", ""])
    lines.extend(f"- `{reason}`" for reason in review["warning_reasons"])
    lines.extend(
        [
            "",
            "## Import Decision",
            "",
            "- Keep this as a future deployment gate only.",
            "- Do not change GroupA+ latest strategy or golden1_0531 weights.",
            "- Do not deploy W4A4 unless percentile calibration, envelope monitoring, and layerwise review all pass.",
            "- No live strategy, target weight, rebalance, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"ptq_calibration_readiness_review_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(review, output_md)
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review["as_of"])).write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--pdf", default=str(DEFAULT_PDF_PATH))
    parser.add_argument("--ptq-eval", default=str(DEFAULT_PTQ_EVAL))
    parser.add_argument("--robustness", default=str(DEFAULT_ROBUSTNESS))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    review = build_review(
        as_of=args.as_of,
        pdf_path=_resolve(args.pdf),
        ptq_eval_path=_resolve(args.ptq_eval),
        robustness_path=_resolve(args.robustness),
    )
    write_review(
        review,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"PTQ calibration readiness review: {_resolve(args.output_json)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "quantized_inference_allowed": review["decision"]["quantized_inference_allowed"],
                "promotable_precisions_for_research_review": review["decision"][
                    "promotable_precisions_for_research_review"
                ],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
