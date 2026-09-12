#!/usr/bin/env python3
"""Build risk-down mapped shadow variants for A21.18 seed averaging.

The raw A21.18 ensemble can request 00631L exposure. This report maps that raw
shadow action into tail-review-compatible variants such as 0050-only and
00631L-capped allocations. It is shadow-only and never changes live targets.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INFERENCE = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_TAIL_SCORECARD = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_tail_sensitive_scorecard.json"
DEFAULT_COST_ROBUSTNESS = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_turnover_cost_robustness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_risk_down_mapped_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/a2118_risk_down_mapped_shadow/history"

WEIGHT_KEYS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _live_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _weights(raw: Any) -> dict[str, float]:
    src = raw if isinstance(raw, dict) else {}
    out = {key: max(0.0, float(src.get(key) or 0.0)) for key in WEIGHT_KEYS}
    total = sum(out.values())
    if total <= 0:
        return out
    return {key: value / total for key, value in out.items()}


def _map_0050_only(raw: dict[str, float], live: dict[str, float]) -> dict[str, float]:
    target_0050 = max(float(live.get("0050.TW", 0.0)), float(raw.get("0050.TW", 0.0)) + float(raw.get("00631L.TW", 0.0)))
    target_0050 = min(target_0050, 1.0)
    return _weights({"0050.TW": target_0050, "cash": max(0.0, 1.0 - target_0050)})


def _map_00631l_cap(raw: dict[str, float], live: dict[str, float], cap: float) -> dict[str, float]:
    capped_631 = min(max(0.0, float(raw.get("00631L.TW", 0.0))), cap)
    target_0050 = max(float(live.get("0050.TW", 0.0)), float(raw.get("0050.TW", 0.0)))
    if target_0050 + capped_631 > 1.0:
        target_0050 = max(0.0, 1.0 - capped_631)
    return _weights({
        "0050.TW": target_0050,
        "00631L.TW": capped_631,
        "cash": max(0.0, 1.0 - target_0050 - capped_631),
    })


def _delta(weights: dict[str, float], live: dict[str, float]) -> dict[str, float]:
    return {key: float(weights.get(key, 0.0) - live.get(key, 0.0)) for key in WEIGHT_KEYS}


def _tail_allows_00631l(scorecard: dict[str, Any], cost: dict[str, Any]) -> bool:
    score_decision = scorecard.get("decision") if isinstance(scorecard.get("decision"), dict) else {}
    cost_decision = cost.get("decision") if isinstance(cost.get("decision"), dict) else {}
    return bool(score_decision.get("allow_00631l_add_from_scorecard")) or bool(
        cost_decision.get("allow_00631l_add_from_cost_sweep")
    )


def build_risk_down_mapping(
    *,
    inference_path: Path,
    live_signal_path: Path,
    tail_scorecard_path: Path,
    cost_robustness_path: Path,
    cap_00631l: float = 0.05,
) -> dict[str, Any]:
    inference = _load(inference_path)
    live_signal = _live_data(_load(live_signal_path))
    scorecard = _load(tail_scorecard_path)
    cost = _load(cost_robustness_path)

    blockers: list[str] = []
    if not inference:
        blockers.append("missing_a2118_inference_snapshot")
    if not live_signal:
        blockers.append("missing_live_signal")
    if not scorecard:
        blockers.append("missing_tail_scorecard")
    if not cost:
        blockers.append("missing_cost_robustness")

    live_weights = _weights(live_signal.get("target_weights"))
    raw_weights = _weights(inference.get("target_weights_for_action"))
    raw_00631l = raw_weights.get("00631L.TW", 0.0)
    tail_allows = _tail_allows_00631l(scorecard, cost)
    variants = [
        {
            "name": "map_to_0050_only",
            "status": "tail_compatible_shadow_candidate",
            "weights": _map_0050_only(raw_weights, live_weights),
            "rationale": "Move raw A21.18 00631L intent into 0050 exposure while preserving cash residual.",
            "allow_00631l_add": False,
        },
        {
            "name": f"map_to_00631l_cap_{int(cap_00631l * 100)}pct",
            "status": "blocked_by_tail_review" if not tail_allows else "tail_capped_shadow_candidate",
            "weights": _map_00631l_cap(raw_weights, live_weights, cap_00631l),
            "rationale": "Cap 00631L exposure for research comparison only.",
            "allow_00631l_add": bool(tail_allows),
        },
    ]
    for item in variants:
        item["delta_vs_live"] = _delta(item["weights"], live_weights)
        item["raw_action_distance_l1"] = float(sum(abs(item["weights"].get(key, 0.0) - raw_weights.get(key, 0.0)) for key in WEIGHT_KEYS))

    if raw_00631l > 0 and not tail_allows:
        blockers.append("raw_a2118_action_adds_00631l_but_tail_review_disallows")

    return {
        "schema_version": 1,
        "report_type": "a2118_risk_down_mapped_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "status": "mapped_shadow_available_blocked_for_live_promotion" if blockers else "mapped_shadow_available",
        "as_of": inference.get("as_of") or live_signal.get("actual_data_date"),
        "raw_a2118": {
            "action": inference.get("action"),
            "action_index": inference.get("action_index"),
            "target_weights_for_action": raw_weights,
            "average_probabilities": inference.get("average_probabilities"),
        },
        "live_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "actual_data_date": live_signal.get("actual_data_date"),
            "execution_regime": live_signal.get("execution_regime"),
            "action": live_signal.get("action"),
            "target_weights": live_weights,
        },
        "tail_context": {
            "tail_scorecard_status": scorecard.get("status"),
            "cost_robustness_status": cost.get("status"),
            "tail_allows_00631l_add": tail_allows,
        },
        "mapped_variants": variants,
        "decision": {
            "use_for_promotion_review": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "summary": "Risk-down mapping creates shadow-only variants for observation; it does not rescue A21.18 for live promotion.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "inputs": {
            "inference_snapshot": str(inference_path),
            "live_signal": str(live_signal_path),
            "tail_scorecard": str(tail_scorecard_path),
            "cost_robustness": str(cost_robustness_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"a2118_risk_down_mapped_shadow_{stamp}.json"


def write_report(report: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", default=str(DEFAULT_INFERENCE))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--tail-scorecard", default=str(DEFAULT_TAIL_SCORECARD))
    parser.add_argument("--cost-robustness", default=str(DEFAULT_COST_ROBUSTNESS))
    parser.add_argument("--cap-00631l", type=float, default=0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_risk_down_mapping(
        inference_path=_resolve(args.inference),
        live_signal_path=_resolve(args.live_signal),
        tail_scorecard_path=_resolve(args.tail_scorecard),
        cost_robustness_path=_resolve(args.cost_robustness),
        cap_00631l=float(args.cap_00631l),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output, history_dir)
    print(f"A21.18 risk-down mapped shadow: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, report.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "variants": [item["name"] for item in report["mapped_variants"]],
                "target_weight_change_allowed": report["decision"]["target_weight_change_allowed"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
