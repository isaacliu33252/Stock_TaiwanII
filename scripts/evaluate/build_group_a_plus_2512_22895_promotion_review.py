#!/usr/bin/env python3
"""Build promotion review for arXiv 2512.22895 SAMP-HDRL shadows."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_promotion_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_promotion_review/history"
DEFAULT_INPUTS = {
    "readiness": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_samp_hdrl_readiness_review.json",
    "dynamic_bucket": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_dynamic_bucket_shadow.json",
    "rebound_gate_00631l": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_rebound_gate_00631l_shadow.json",
    "cash_temperature": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_cash_temperature_shadow.json",
    "explainability_daily_audit": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_explainability_daily_audit.json",
    "inter_cluster_dependency": PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_inter_cluster_dependency_shadow.json",
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError:
        return {}


def build_review(inputs: dict[str, Path] = DEFAULT_INPUTS) -> dict[str, Any]:
    loaded = {name: _load_json(path) for name, path in inputs.items()}
    missing = [name for name, payload in loaded.items() if not payload]
    dynamic_decision = loaded.get("dynamic_bucket", {}).get("decision", {})
    rebound_decision = loaded.get("rebound_gate_00631l", {}).get("decision", {})
    cash_decision = loaded.get("cash_temperature", {}).get("decision", {})
    explain_decision = loaded.get("explainability_daily_audit", {}).get("decision", {})
    dependency_decision = loaded.get("inter_cluster_dependency", {}).get("decision", {})

    retained = []
    rejected = []
    monitoring = []

    if dynamic_decision:
        retained.append(
            {
                "component": "dynamic_two_bucket_shadow",
                "reason": "Explains quality/ordinary grouping but cluster separation is weak in a four-ETF universe.",
                "production_effect": "none",
            }
        )
    if rebound_decision:
        rejected.append(
            {
                "component": "00631l_rebound_gate",
                "reason": "Historical rebound events underperformed non-rebound events and latest gate is false.",
                "production_effect": "none",
            }
        )
    if cash_decision:
        monitoring.append(
            {
                "component": "cash_temperature_shadow",
                "reason": "Supports higher discretionary conservative cash, but cannot override A21.18.",
                "production_effect": "none",
            }
        )
    if explain_decision:
        retained.append(
            {
                "component": "explainability_daily_audit",
                "reason": "Useful to explain ambiguous 00631L plus 00632R exposure.",
                "production_effect": "none",
            }
        )
    if dependency_decision:
        retained.append(
            {
                "component": "inter_cluster_dependency_shadow",
                "reason": "Confirms 00632R hedge role and 00679B weak/moderate diversifier role.",
                "production_effect": "none",
            }
        )

    can_promote = bool(
        not missing
        and False
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_promotion_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": loaded.get("explainability_daily_audit", {}).get("as_of")
        or loaded.get("dynamic_bucket", {}).get("as_of"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "title": "SAMP-HDRL: Segmented Allocation with Momentum-Adjusted Utility for Multi-agent Portfolio Management via Hierarchical Deep Reinforcement Learning",
        },
        "input_status": {
            "missing_inputs": missing,
            "available_inputs": [name for name in inputs if name not in missing],
        },
        "component_decisions": {
            "retained_for_monitoring_or_explanation": retained,
            "shadow_only_monitoring": monitoring,
            "rejected_for_promotion": rejected,
        },
        "evidence_summary": {
            "dynamic_bucket": dynamic_decision,
            "rebound_gate_00631l": rebound_decision,
            "cash_temperature": cash_decision,
            "explainability_daily_audit": explain_decision,
            "inter_cluster_dependency": dependency_decision,
        },
        "decision": {
            "promote_any_component_to_live_strategy": can_promote,
            "change_latest_strategy": False,
            "latest_strategy_after_review": "a2118_a2111_ncf_late_bull_deleverage",
            "target_weight_change_allowed": False,
            "train_hdrl_or_ddpg_now": False,
            "allow_auto_rebalance": False,
            "production_effect": "none",
            "summary": "2512.22895 contributes useful diagnostics, but no component clears promotion for live weights.",
        },
        "blocking_reasons": [
            "no_component_has_trade_permission",
            "00631l_rebound_gate_failed",
            "cash_temperature_is_diagnostic_only",
            "dynamic_bucket_cluster_separation_is_weak",
            "hdrl_training_not_approved_for_groupa_plus",
        ],
    }


def write_review(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_promotion_review_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_review()
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
