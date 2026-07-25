#!/usr/bin/env python3
"""Build a research-only FinStressTS mechanism readiness review for GroupA+.

This imports validation ideas from arXiv 2606.03184, not synthetic returns as
alpha: model claims should be stress-tested against mechanism-specific failure
modes before any optimizer or forecast head can affect live allocation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260720_estimate.json"
DEFAULT_REBALANCE_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_OPTION_STATE = PROJECT_ROOT / "report/group_a_plus/latest/option_state_coverage_review.json"
DEFAULT_ADVERSARIAL = PROJECT_ROOT / "report/group_a_plus/latest/adversarial_market_integrity_review.json"
DEFAULT_SCIPHYRL = PROJECT_ROOT / "report/group_a_plus/latest/sciphyrl_readiness_review.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_HETEROGENEOUS_VOL = PROJECT_ROOT / "report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json"
DEFAULT_DENSITY_HEAD = PROJECT_ROOT / "report/group_a_plus/latest/density_head_tail_risk_advisory.json"
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_readiness_review_20260720.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/finstressts_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _status(payload: dict[str, Any]) -> str | None:
    value = _unwrap(payload).get("status")
    return str(value) if value is not None else None


def _decision_bool(payload: dict[str, Any], key: str) -> bool | None:
    decision = _unwrap(payload).get("decision") or {}
    if key not in decision:
        return None
    return bool(decision[key])


def _source_present(payload: dict[str, Any]) -> bool:
    return bool(payload)


def _mechanism_rows(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cvar_status = _status(inputs["cvar"])
    density_status = _status(inputs["density_head"])
    option_status = _status(inputs["option_state"])
    adversarial_status = _status(inputs["adversarial"])
    market_impact_status = _status(inputs["market_impact"])
    sciphyrl_status = _status(inputs["sciphyrl"])

    return [
        {
            "mechanism": "volatility_clustering",
            "paper_case": "GARCH factor/idiosyncratic volatility clustering",
            "group_a_plus_coverage": [
                "heterogeneous_vol_regime_advisory",
                "cvar_tail_risk_diagnostic",
                "density_head_tail_risk_advisory",
            ],
            "coverage_state": "partial" if _source_present(inputs["heterogeneous_vol"]) else "missing",
            "notes": "Volatility advisory exists, but it remains advisory and is not an execution guard.",
        },
        {
            "mechanism": "multi_scale_persistence",
            "paper_case": "HAR-style multi-scale volatility persistence",
            "group_a_plus_coverage": [
                "NCF rolling panels",
                "multi-window promotion review",
                "sciphyrl explicit-cost readiness",
            ],
            "coverage_state": "partial" if sciphyrl_status else "missing",
            "notes": "Rolling windows exist, but no controlled HAR-style stress benchmark is promoted.",
        },
        {
            "mechanism": "heavy_tailed_shocks",
            "paper_case": "Student-t shocks and rare outliers",
            "group_a_plus_coverage": [
                "cvar_tail_risk_diagnostic",
                "density_head_tail_risk_advisory",
                "option_state_coverage_review",
            ],
            "coverage_state": "blocked" if option_status == "blocked" else "partial",
            "notes": f"Tail diagnostics are present, but option-state gate is {option_status or 'missing'}.",
        },
        {
            "mechanism": "regime_switching",
            "paper_case": "market-wide latent regime with structural breaks",
            "group_a_plus_coverage": [
                "bull_pullback_deep market state",
                "leveraged compounding regime",
                "heterogeneous volatility regime advisory",
            ],
            "coverage_state": "partial",
            "notes": "Regime labels are operational, but no synthetic counterfactual regime suite is promoted.",
        },
        {
            "mechanism": "self_exciting_jumps",
            "paper_case": "Hawkes-type clustered market jumps",
            "group_a_plus_coverage": [
                "crash_risk_alert",
                "adversarial_market_integrity_review",
                "market_impact_readiness_review",
            ],
            "coverage_state": "blocked" if adversarial_status == "blocked" or market_impact_status == "blocked" else "partial",
            "notes": (
                "Jump-cluster stress is only indirectly covered by crash/adversarial checks; "
                "no Hawkes-style validation set is live."
            ),
        },
        {
            "mechanism": "zero_inflated_sparse_jumps",
            "paper_case": "zero-inflated sparse jump arrivals",
            "group_a_plus_coverage": [
                "adversarial sparse perturbation governance",
                "option_state_coverage_review",
                "manual rebalance review",
            ],
            "coverage_state": "blocked" if adversarial_status == "blocked" or option_status == "blocked" else "partial",
            "notes": "Sparse event sensitivity is a governance concern; feature coverage is still incomplete.",
        },
        {
            "mechanism": "forecast_architecture_bias",
            "paper_case": "linear/econometric models can beat larger Transformers under specific mechanisms",
            "group_a_plus_coverage": [
                "density-head promotion review",
                "multi-window promotion gate",
                "no single-model auto-execution",
            ],
            "coverage_state": "partial" if density_status else "missing",
            "notes": "Supports keeping simple baselines and multi-window evidence before model promotion.",
        },
        {
            "mechanism": "execution_under_stress",
            "paper_case": "counterfactual dirty data and data-efficiency learning curves",
            "group_a_plus_coverage": [
                "market_impact_readiness_review",
                "sciphyrl_readiness_review",
                "rebalance_review",
            ],
            "coverage_state": "blocked" if market_impact_status == "blocked" or sciphyrl_status == "blocked" else "partial",
            "notes": "Optimizer/execution readiness remains blocked under current 7/20 gates.",
        },
    ]


def build_review(
    *,
    live_signal_path: Path,
    rebalance_review_path: Path,
    option_state_path: Path,
    adversarial_path: Path,
    sciphyrl_path: Path,
    market_impact_path: Path,
    heterogeneous_vol_path: Path,
    density_head_path: Path,
    cvar_path: Path,
) -> dict[str, Any]:
    inputs = {
        "live": _unwrap(_load(live_signal_path)),
        "rebalance": _load(rebalance_review_path),
        "option_state": _load(option_state_path),
        "adversarial": _load(adversarial_path),
        "sciphyrl": _load(sciphyrl_path),
        "market_impact": _load(market_impact_path),
        "heterogeneous_vol": _load(heterogeneous_vol_path),
        "density_head": _load(density_head_path),
        "cvar": _load(cvar_path),
    }

    live = inputs["live"]
    rebalance = inputs["rebalance"]
    mechanism_rows = _mechanism_rows(inputs)

    blockers: list[str] = []
    warnings: list[str] = []
    if not live.get("execution_allowed"):
        blockers.append("live_signal_execution_not_allowed")
    if _decision_bool(rebalance, "target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")
    if _status(inputs["option_state"]) == "blocked":
        blockers.append("option_state_gate_not_passed")
    if _status(inputs["adversarial"]) == "blocked":
        blockers.append("adversarial_market_integrity_not_passed")
    if _status(inputs["market_impact"]) == "blocked":
        blockers.append("market_impact_readiness_not_passed")
    if _status(inputs["sciphyrl"]) == "blocked":
        blockers.append("optimizer_readiness_not_passed")

    missing = [
        name
        for name, payload in inputs.items()
        if name not in {"live"} and not payload
    ]
    if missing:
        warnings.append("missing_review_inputs:" + ",".join(sorted(missing)))

    blocked_mechanisms = [
        row["mechanism"]
        for row in mechanism_rows
        if row["coverage_state"] == "blocked"
    ]
    if blocked_mechanisms:
        blockers.append("mechanism_stress_coverage_blocked")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finstressts_readiness_review",
        "status": "blocked" if blockers else "available_for_manual_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_model_validation_only_no_weight_change",
        "as_of": live.get("requested_as_of_date") or live.get("actual_data_date") or "2026-07-20",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.03184.pdf",
            "title": "FinStressTS: A Parametric Synthetic Benchmark for Time-Series Forecasting in Finance",
            "imported_concepts": [
                "mechanism_specific_stress_testing",
                "controlled_counterfactual_financial_time_series",
                "proper_probabilistic_calibration_review",
                "data_efficiency_learning_curve_requirement",
                "simple_baseline_before_transformer_promotion",
                "failure_attribution_by_financial_mechanism",
            ],
            "not_imported": [
                "synthetic_returns_as_live_alpha",
                "KDD_benchmark_scores_as_Taiwan_ETF_evidence",
                "automatic_model_architecture_replacement",
                "automatic_weight_change_or_rebalance",
            ],
        },
        "mechanism_coverage": mechanism_rows,
        "summary": {
            "covered_mechanisms": int(sum(1 for row in mechanism_rows if row["coverage_state"] in {"partial", "blocked"})),
            "blocked_mechanisms": blocked_mechanisms,
            "missing_or_unpromoted_synthetic_counterfactual_suite": True,
            "simple_baseline_preferred_until_multi_window_evidence": True,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import FinStressTS as model-validation governance only. Current GroupA+ gates are blocked, "
                "and the paper is a diagnostic benchmark rather than a Taiwan ETF trading signal."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
            "next_research_step": "Build a small Taiwan ETF counterfactual stress harness before any model promotion claim.",
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "rebalance_review": str(rebalance_review_path),
            "option_state": str(option_state_path),
            "adversarial": str(adversarial_path),
            "sciphyrl": str(sciphyrl_path),
            "market_impact": str(market_impact_path),
            "heterogeneous_vol": str(heterogeneous_vol_path),
            "density_head": str(density_head_path),
            "cvar": str(cvar_path),
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    stamp = str(as_of).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(
    review: dict[str, Any],
    *,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review["as_of"])).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--rebalance-review", default=str(DEFAULT_REBALANCE_REVIEW))
    parser.add_argument("--option-state", default=str(DEFAULT_OPTION_STATE))
    parser.add_argument("--adversarial", default=str(DEFAULT_ADVERSARIAL))
    parser.add_argument("--sciphyrl", default=str(DEFAULT_SCIPHYRL))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--heterogeneous-vol", default=str(DEFAULT_HETEROGENEOUS_VOL))
    parser.add_argument("--density-head", default=str(DEFAULT_DENSITY_HEAD))
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        rebalance_review_path=_resolve(args.rebalance_review),
        option_state_path=_resolve(args.option_state),
        adversarial_path=_resolve(args.adversarial),
        sciphyrl_path=_resolve(args.sciphyrl),
        market_impact_path=_resolve(args.market_impact),
        heterogeneous_vol_path=_resolve(args.heterogeneous_vol),
        density_head_path=_resolve(args.density_head),
        cvar_path=_resolve(args.cvar),
    )
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"FinStressTS readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review['as_of'])}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "blocked_mechanisms": review["summary"]["blocked_mechanisms"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
