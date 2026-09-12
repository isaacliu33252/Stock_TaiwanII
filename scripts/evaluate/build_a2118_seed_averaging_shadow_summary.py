#!/usr/bin/env python3
"""Summarize A21.18 PPO seed-averaging evidence into a shadow gate artifact.

This reads an existing robustness JSON. It does not load PPO checkpoints,
train models, generate live actions, or alter production weights.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_INPUT_GLOB = "results/a2118_ppo_seed_averaging_robustness_2607_00475_*.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_shadow.md"
DEFAULT_FORWARD_MONITOR = (
    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.json"
)
DEFAULT_PROMOTION_GATE = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_promotion_gate.json"
PREFERRED_ENSEMBLE = "42+43+44"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _latest_input(pattern: str) -> Path:
    paths = [Path(path) for path in glob.glob(str(_resolve(pattern)))]
    if not paths:
        raise FileNotFoundError(f"No robustness files matched {pattern!r}")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _metric(row: dict[str, Any], section: str, key: str) -> float:
    return float(((row.get(section) or {}).get(key)))


def _best_individual(individual: dict[str, Any], metric: str, *, higher_is_better: bool = True) -> tuple[str, dict[str, Any]]:
    return sorted(
        individual.items(),
        key=lambda item: _metric(item[1], "full", metric),
        reverse=higher_is_better,
    )[0]


def _mean_individual(individual: dict[str, Any], metric: str) -> float:
    values = [_metric(row, "full", metric) for row in individual.values()]
    return sum(values) / len(values)


def _production_blockers(
    forward_monitor: dict[str, Any] | None = None,
    promotion_gate: dict[str, Any] | None = None,
) -> list[str]:
    if forward_monitor and isinstance(forward_monitor.get("production_blockers"), list):
        blockers = [str(item) for item in forward_monitor["production_blockers"]]
        if promotion_gate:
            blockers = [item for item in blockers if item != "no_production_promotion_gate"]
            blockers.extend(str(item) for item in promotion_gate.get("blockers", []) if item)
            return list(dict.fromkeys(blockers))
        return blockers
    blockers = [
        "inference_integration_not_implemented",
        "latest_live_action_parity_not_validated",
        "forward_shadow_monitoring_missing",
        "no_production_promotion_gate",
    ]
    if forward_monitor:
        blockers = [item for item in blockers if item != "forward_shadow_monitoring_missing"]
        requirements = (
            forward_monitor.get("monitoring_requirements")
            if isinstance(forward_monitor.get("monitoring_requirements"), dict)
            else {}
        )
        rows = int(requirements.get("current_forward_rows_counted_by_log") or 0)
        minimum = int(requirements.get("minimum_forward_rows_before_review") or 20)
        if rows < minimum:
            blockers.insert(2, "forward_shadow_monitoring_history_insufficient")
    return blockers


def build_summary(
    report: dict[str, Any],
    *,
    preferred: str = PREFERRED_ENSEMBLE,
    forward_monitor: dict[str, Any] | None = None,
    promotion_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    individual = report.get("individual") if isinstance(report.get("individual"), dict) else {}
    ensembles = report.get("ensembles") if isinstance(report.get("ensembles"), dict) else {}
    if preferred not in ensembles:
        raise KeyError(f"Preferred ensemble {preferred!r} not found")
    if not individual:
        raise ValueError("Missing individual seed results")

    ensemble = ensembles[preferred]
    best_sharpe_seed, best_sharpe = _best_individual(individual, "sharpe", higher_is_better=True)
    worst_mdd_seed, worst_mdd = _best_individual(individual, "max_drawdown", higher_is_better=False)
    best_mdd_seed, best_mdd = _best_individual(individual, "max_drawdown", higher_is_better=True)

    ensemble_full = ensemble["full"]
    ensemble_2024 = ensemble["sub_periods"]["2024"]
    ensemble_2025 = ensemble["sub_periods"]["2025_2026"]
    mean_sharpe = _mean_individual(individual, "sharpe")
    mean_mdd = _mean_individual(individual, "max_drawdown")

    checks = [
        {
            "name": "ensemble_sharpe_above_individual_mean",
            "passed": float(ensemble_full["sharpe"]) >= mean_sharpe,
            "actual": float(ensemble_full["sharpe"]),
            "required": f">= individual mean {mean_sharpe:.6f}",
        },
        {
            "name": "ensemble_mdd_better_than_individual_mean",
            "passed": float(ensemble_full["max_drawdown"]) >= mean_mdd,
            "actual": float(ensemble_full["max_drawdown"]),
            "required": f">= individual mean {mean_mdd:.6f}",
        },
        {
            "name": "ensemble_not_far_below_best_sharpe",
            "passed": float(ensemble_full["sharpe"]) >= float(best_sharpe["full"]["sharpe"]) - 0.02,
            "actual": {
                "ensemble_sharpe": float(ensemble_full["sharpe"]),
                "best_seed": best_sharpe_seed,
                "best_seed_sharpe": float(best_sharpe["full"]["sharpe"]),
            },
            "required": "within 0.02 Sharpe of best individual seed",
        },
        {
            "name": "ensemble_avoids_bad_seed_mdd_tail",
            "passed": float(ensemble_full["max_drawdown"]) > float(worst_mdd["full"]["max_drawdown"]) + 0.05,
            "actual": {
                "ensemble_mdd": float(ensemble_full["max_drawdown"]),
                "worst_seed": worst_mdd_seed,
                "worst_seed_mdd": float(worst_mdd["full"]["max_drawdown"]),
            },
            "required": "at least 5 percentage points better than worst individual MDD",
        },
        {
            "name": "subperiods_positive_sharpe",
            "passed": float(ensemble_2024["sharpe"]) > 0.0 and float(ensemble_2025["sharpe"]) > 0.0,
            "actual": {
                "2024_sharpe": float(ensemble_2024["sharpe"]),
                "2025_2026_sharpe": float(ensemble_2025["sharpe"]),
            },
            "required": "positive Sharpe in both subperiods",
        },
    ]
    passed = all(item["passed"] for item in checks)
    return {
        "schema_version": 1,
        "report_type": "a2118_ppo_seed_averaging_shadow_summary",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "preferred_ensemble": preferred,
        "decision": {
            "shadow_gate": "pass" if passed else "fail",
            "shadow_queue": "candidate_for_forward_shadow_monitoring" if passed else "do_not_queue",
            "production": "do_not_promote",
            "reason": (
                "3-seed probability averaging stays near the best seed while reducing bad-seed drawdown tail risk."
                if passed
                else "One or more seed-averaging evidence checks failed."
            ),
            "production_blockers": _production_blockers(forward_monitor, promotion_gate),
        },
        "checks": checks,
        "summary": {
            "preferred_full": ensemble_full,
            "preferred_2024": ensemble_2024,
            "preferred_2025_2026": ensemble_2025,
            "individual_mean": {
                "sharpe": mean_sharpe,
                "max_drawdown": mean_mdd,
            },
            "best_individual_sharpe": {"seed": best_sharpe_seed, **best_sharpe["full"]},
            "best_individual_mdd": {"seed": best_mdd_seed, **best_mdd["full"]},
            "worst_individual_mdd": {"seed": worst_mdd_seed, **worst_mdd["full"]},
            "available_ensembles": sorted(ensembles.keys()),
        },
    }


def _write_md(path: Path, payload: dict[str, Any], source: Path) -> None:
    decision = payload["decision"]
    summary = payload["summary"]
    preferred = summary["preferred_full"]
    lines = [
        "# A21.18 PPO Seed Averaging Shadow",
        "",
        f"- Source: `{source}`",
        f"- Shadow gate: `{decision['shadow_gate']}`",
        f"- Shadow queue: `{decision['shadow_queue']}`",
        f"- Production: `{decision['production']}`",
        f"- Preferred ensemble: `{payload['preferred_ensemble']}`",
        f"- Full Sharpe / MDD: `{preferred['sharpe']:.4f}` / `{preferred['max_drawdown']:.4f}`",
        "",
        "## Checks",
        "",
    ]
    for check in payload["checks"]:
        lines.append(f"- `{check['name']}`: `{check['passed']}`")
    lines.extend(
        [
            "",
            "## Note",
            "",
            "This artifact is shadow-only. It summarizes existing backtests and does not generate live actions.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None)
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    args = parser.parse_args()

    source = _resolve(args.input) if args.input else _latest_input(args.input_glob)
    forward_monitor_path = _resolve(args.forward_monitor)
    forward_monitor = _load_json(forward_monitor_path) if forward_monitor_path.exists() else None
    promotion_gate_path = _resolve(args.promotion_gate)
    promotion_gate = _load_json(promotion_gate_path) if promotion_gate_path.exists() else None
    payload = build_summary(_load_json(source), forward_monitor=forward_monitor, promotion_gate=promotion_gate)
    payload["source_robustness_report"] = str(source)
    if forward_monitor:
        payload["source_forward_monitor"] = str(forward_monitor_path)
    if promotion_gate:
        payload["source_promotion_gate"] = str(promotion_gate_path)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload, source)
    print(json.dumps({"output": str(output), "status": payload["decision"]["shadow_gate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
