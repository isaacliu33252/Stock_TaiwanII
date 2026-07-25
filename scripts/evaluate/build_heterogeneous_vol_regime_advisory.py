#!/usr/bin/env python3
"""Build latest heterogeneous-volatility advisory JSON for GroupA+.

Research-only. Reads the heterogeneous vol-regime shadow report and writes a
compact advisory artifact under report/group_a_plus/latest. It never changes
target weights or execution guards.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_shadow_20250102_20260717.json"
DEFAULT_CONDITIONAL = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_conditional_overlap_20250102_20260717.json"
DEFAULT_WF_H10 = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_walkforward_ablation_20180102_20260717_h10.json"
DEFAULT_PARAM_SWEEP = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_param_sweep_20250102_20260717.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal_20260720_estimate.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "heterogeneous_vol_regime_advisory.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _top_crisis_sources(source_diagnostics: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = []
    for source, detail in source_diagnostics.items():
        regime = str(detail.get("latest_regime"))
        if regime not in {"Crisis", "Elevated"}:
            continue
        rows.append(
            {
                "source": source,
                "regime": regime,
                "vol_percentile": detail.get("latest_vol_percentile"),
                "variance_ratio": detail.get("latest_variance_ratio"),
                "passes_shadow_verification": bool(detail.get("passes_shadow_verification")),
            }
        )
    rows.sort(
        key=lambda row: (
            1 if row["regime"] == "Crisis" else 0,
            float(row["vol_percentile"] or 0.0),
            float(row["variance_ratio"] or 0.0),
        ),
        reverse=True,
    )
    return rows[:limit]


def _metric(summary: dict[str, Any], name: str) -> dict[str, Any]:
    item = summary.get(name) or {}
    h10 = ((item.get("h10") or {}).get("confusion") or {})
    return {
        "active_days": item.get("active_days"),
        "h10_precision": h10.get("precision"),
        "h10_recall": h10.get("recall"),
        "h10_fpr": h10.get("false_positive_rate"),
    }


def _wf_best(wf_report: dict[str, Any]) -> dict[str, Any] | None:
    rank = wf_report.get("aggregate_rank") or []
    return dict(rank[0]) if rank else None


def _param_sweep_best(param_sweep: dict[str, Any]) -> dict[str, Any] | None:
    candidates = param_sweep.get("recommended_research_candidates") or param_sweep.get("top_candidates") or []
    if not candidates:
        return None
    candidate = dict(candidates[0])
    return {
        key: candidate.get(key)
        for key in (
            "signal",
            "vol_window",
            "percentile_window",
            "hetero_source_min_count",
            "crisis_source_min_count",
            "active_days",
            "latest_active",
            "h10_precision",
            "h10_recall",
            "h10_fpr",
            "score",
        )
    }


def build_advisory(
    *,
    shadow_path: Path,
    conditional_path: Path,
    wf_h10_path: Path,
    param_sweep_path: Path,
    live_signal_path: Path | None,
    top_sources_limit: int,
) -> dict[str, Any]:
    shadow = _load(shadow_path)
    conditional = _load(conditional_path) if conditional_path.exists() else {}
    wf_h10 = _load(wf_h10_path) if wf_h10_path.exists() else {}
    param_sweep = _load(param_sweep_path) if param_sweep_path.exists() else {}
    live_signal = _load(live_signal_path) if live_signal_path and live_signal_path.exists() else {}
    live_data = live_signal.get("data") or {}
    latest = shadow.get("latest_snapshot") or {}
    source_diagnostics = shadow.get("source_diagnostics") or {}

    sparse_active = bool(latest.get("sparse_crisis_active"))
    stress_active = bool(latest.get("heterogeneous_stress_active"))
    verified_crisis_count = int(latest.get("verified_crisis_count") or 0)
    verified_stress_count = int(latest.get("verified_stress_count") or 0)

    if sparse_active and verified_crisis_count >= 3:
        advisory_level = "high"
        suggested_review = "avoid_adding_00631l_until_manual_review"
    elif stress_active:
        advisory_level = "medium"
        suggested_review = "review_00631l_add_or_rebalance_timing"
    else:
        advisory_level = "normal"
        suggested_review = "none"

    return {
        "schema_version": 1,
        "report_type": "heterogeneous_vol_regime_advisory",
        "status": "available",
        "policy": "manual_review_only_no_weight_change",
        "active_allocation_impact": "none",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "C:/Users/isaac/Downloads/2603.16035.pdf",
        "as_of": latest.get("date"),
        "live_signal": str(live_signal_path) if live_signal_path else None,
        "live_signal_context": {
            "requested_as_of_date": live_data.get("requested_as_of_date"),
            "actual_data_date": live_data.get("actual_data_date"),
            "strategy_id": live_data.get("strategy_id"),
            "execution_regime": live_data.get("execution_regime"),
            "execution_allowed": live_data.get("execution_allowed"),
            "target_weights": live_data.get("target_weights"),
            "market_state": {
                key: (live_data.get("market_state") or {}).get(key)
                for key in ("state", "label_zh", "risk_level")
            },
        },
        "advisory": {
            "level": advisory_level,
            "active": advisory_level != "normal",
            "suggested_review": suggested_review,
            "recommended_action": "manual_review",
            "allow_auto_weight_change": False,
            "allow_execution_block": False,
            "allow_00631l_auto_reduce": False,
            "allow_00631l_auto_add": False,
        },
        "latest_snapshot": {
            "heterogeneous_stress_count": latest.get("heterogeneous_stress_count"),
            "heterogeneous_crisis_count": latest.get("heterogeneous_crisis_count"),
            "heteroskedastic_source_count": latest.get("heteroskedastic_source_count"),
            "verified_stress_count": verified_stress_count,
            "verified_crisis_count": verified_crisis_count,
            "heterogeneous_stress_active": stress_active,
            "sparse_crisis_active": sparse_active,
        },
        "top_stress_sources": _top_crisis_sources(source_diagnostics, top_sources_limit),
        "evidence": {
            "shadow_metrics": {
                "sparse_crisis_active": _metric(shadow.get("summary") or {}, "sparse_crisis_active"),
                "heterogeneous_stress_active": _metric(shadow.get("summary") or {}, "heterogeneous_stress_active"),
            },
            "conditional_metrics": {
                "hetero_sparse_or_qgms_endpoint": _metric(
                    conditional.get("summary") or {},
                    "hetero_sparse_or_qgms_endpoint",
                ),
                "verified_crisis_count_ge_3": next(
                    (
                        row
                        for row in ((conditional.get("threshold_sweep") or {}).get("rows") or [])
                        if row.get("signal") == "verified_crisis_count_ge_3"
                    ),
                    None,
                ),
            },
            "walkforward_h10_best": _wf_best(wf_h10),
            "param_sweep_best": _param_sweep_best(param_sweep),
        },
        "inputs": {
            "shadow_report": str(shadow_path),
            "conditional_overlap": str(conditional_path) if conditional_path.exists() else None,
            "walkforward_h10": str(wf_h10_path) if wf_h10_path.exists() else None,
            "param_sweep": str(param_sweep_path) if param_sweep_path.exists() else None,
        },
        "interpretation": (
            "Heterogeneous volatility regime is a source-level risk dashboard. "
            "Walk-forward validation did not support live promotion; this advisory "
            "must not modify target weights or execution guards."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", default=str(DEFAULT_SHADOW))
    parser.add_argument("--conditional", default=str(DEFAULT_CONDITIONAL))
    parser.add_argument("--wf-h10", default=str(DEFAULT_WF_H10))
    parser.add_argument("--param-sweep", default=str(DEFAULT_PARAM_SWEEP))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--top-sources-limit", type=int, default=6)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = _resolve(args.output)
    advisory = build_advisory(
        shadow_path=_resolve(args.shadow),
        conditional_path=_resolve(args.conditional),
        wf_h10_path=_resolve(args.wf_h10),
        param_sweep_path=_resolve(args.param_sweep),
        live_signal_path=_resolve(args.live_signal) if args.live_signal else None,
        top_sources_limit=int(args.top_sources_limit),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(advisory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Advisory: {output}")
    print(
        json.dumps(
            {
                "as_of": advisory["as_of"],
                "level": advisory["advisory"]["level"],
                "suggested_review": advisory["advisory"]["suggested_review"],
                "verified_crisis_count": advisory["latest_snapshot"]["verified_crisis_count"],
                "policy": advisory["policy"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
