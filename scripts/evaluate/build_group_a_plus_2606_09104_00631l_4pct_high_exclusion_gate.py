#!/usr/bin/env python3
"""Build a HIGH-exclusion gate for the 2606.09104 00631L 4% candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_regime_split import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REGIME_SPLIT,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_high_exclusion_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_high_exclusion_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _passes(summary: dict[str, Any], *, min_events: int, min_hit_rate: float, min_excess_return: float, max_es_extra_loss: float) -> bool:
    return bool(
        int(summary.get("event_count") or 0) >= min_events
        and float(summary.get("hit_rate_micro_beats_guarded") or 0.0) >= min_hit_rate
        and float(summary.get("mean_micro_minus_guarded_20d") or 0.0) >= min_excess_return
        and float(summary.get("mean_es_extra_loss") or -999.0) >= max_es_extra_loss
    )


def build_gate(
    *,
    regime_split_path: Path = DEFAULT_REGIME_SPLIT,
    min_extreme_events: int = 50,
    min_extreme_hit_rate: float = 0.55,
    min_extreme_excess_return: float = 0.001,
    max_extreme_es_extra_loss: float = -0.0025,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    split = _load_json(_resolve(regime_split_path))
    if not split:
        blockers.append("regime_split_missing")
    state_split = split.get("state_split_summary") if isinstance(split.get("state_split_summary"), dict) else {}
    latest_state = split.get("latest_state") if isinstance(split.get("latest_state"), dict) else {}
    high = state_split.get("HIGH", {}) if isinstance(state_split.get("HIGH"), dict) else {}
    extreme = state_split.get("EXTREME", {}) if isinstance(state_split.get("EXTREME"), dict) else {}
    high_passes = _passes(
        high,
        min_events=50,
        min_hit_rate=0.55,
        min_excess_return=0.001,
        max_es_extra_loss=max_extreme_es_extra_loss,
    )
    extreme_passes = _passes(
        extreme,
        min_events=min_extreme_events,
        min_hit_rate=min_extreme_hit_rate,
        min_excess_return=min_extreme_excess_return,
        max_es_extra_loss=max_extreme_es_extra_loss,
    )
    current_state = latest_state.get("risk_aversion_state")
    if current_state == "HIGH":
        blockers.append("latest_state_high_excluded")
    elif current_state != "EXTREME":
        warnings.append("latest_state_not_extreme_candidate_inactive")
    if not extreme_passes and not blockers:
        blockers.append("extreme_state_does_not_pass_micro_add_gate")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_high_exclusion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "high_exclusion_shadow_gate_only_no_live_weight_change",
        "status": "blocked" if blockers else "extreme_only_shadow_candidate_active",
        "as_of": str(split.get("as_of") or datetime.now().date()),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "skip_high_regime_micro_add_gate",
            "not_imported": ["live_weight_change", "auto_rebalance", "unconstrained_BLED_optimizer"],
        },
        "rule": {
            "HIGH": "excluded",
            "EXTREME": "shadow_eligible_if_historical_gate_passes",
            "LOW_MEDIUM": "monitor_only_not_promotion_context",
            "candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
        },
        "thresholds": {
            "min_extreme_events": min_extreme_events,
            "min_extreme_hit_rate": min_extreme_hit_rate,
            "min_extreme_excess_return": min_extreme_excess_return,
            "max_extreme_es_extra_loss": max_extreme_es_extra_loss,
        },
        "latest_state": latest_state,
        "high_summary": high,
        "extreme_summary": extreme,
        "eligibility_review": {
            "high_passes_original_style_gate": high_passes,
            "extreme_passes_high_exclusion_gate": extreme_passes,
            "latest_state_high_excluded": current_state == "HIGH",
            "latest_state_extreme_eligible": current_state == "EXTREME" and extreme_passes,
        },
        "decision": {
            "skip_high_regime": True,
            "extreme_only_candidate_has_historical_value": extreme_passes,
            "candidate_active_today": bool(current_state == "EXTREME" and extreme_passes and not blockers),
            "allow_00631l_micro_add_from_high_exclusion_gate": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "HIGH can be skipped, but this gate is shadow-only; today's latest state is excluded unless it is EXTREME and all promotion prerequisites later pass.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_gate(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_high_exclusion_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regime-split", default=str(DEFAULT_REGIME_SPLIT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_gate(regime_split_path=_resolve(args.regime_split))
    write_gate(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
