#!/usr/bin/env python3
"""Build latest density-head tail-risk advisory for GroupA+.

Research-only summary inspired by arXiv 2606.30037. It never changes
allocation weights or execution guards.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DENSITY = PROJECT_ROOT / "results" / "density_head_tail_risk_shadow_00631l_20250102_20260716.json"
DEFAULT_PARAM_SWEEP = PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_20250102_20260716.json"
DEFAULT_CRASH_SWEEPS = [
    PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2018_correction.json",
    PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2020_covid.json",
    PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2026_recent.json",
]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal_20260720_estimate.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "density_head_tail_risk_advisory.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _head_summary(report: dict[str, Any], head: str) -> dict[str, Any]:
    aggregate = (report.get("aggregate") or {}).get(head) or {}
    return {
        "crps_sample": aggregate.get("crps_sample"),
        "pinball_q05": (aggregate.get("pinball") or {}).get("q05"),
        "var_05_breach_rate": ((aggregate.get("var_backtest") or {}).get("var_05") or {}).get("breach_rate"),
        "central_90_coverage": ((aggregate.get("coverage") or {}).get("central_90") or {}).get("coverage"),
        "mae_mean": aggregate.get("mae_mean"),
        "mse_mean": aggregate.get("mse_mean"),
    }


def _crash_sweep_summary(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        report = _load(path)
        if not report:
            continue
        stem = path.stem.replace("density_head_tail_risk_param_sweep_00631l_", "")
        rows.append(
            {
                "window": stem,
                "path": str(path),
                "win_counts": report.get("win_counts"),
                "best_gmm_candidate": report.get("best_gmm_candidate"),
            }
        )
    return rows


def build_advisory(
    *,
    density_path: Path,
    param_sweep_path: Path,
    crash_sweep_paths: list[Path],
    live_signal_path: Path | None,
) -> dict[str, Any]:
    density = _load(density_path)
    param_sweep = _load(param_sweep_path)
    live = _data(_load(live_signal_path)) if live_signal_path else {}
    best_by_crps = density.get("best_by_crps")
    best_by_pinball = density.get("best_by_pinball_q05")
    gaussian = _head_summary(density, "gaussian")
    gmm = _head_summary(density, "gmm")
    point = _head_summary(density, "point")

    return {
        "schema_version": 1,
        "report_type": "density_head_tail_risk_advisory",
        "status": "available" if density else "missing_density_report",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_advisory_only_no_weight_change",
        "active_allocation_impact": "none",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.30037.pdf",
            "title": "Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns",
            "implementation_note": "Post-hoc residual density-head shadow on existing NCF panel; no new backbone and no live trading rule.",
        },
        "live_signal_context": {
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
            "strategy_id": live.get("strategy_id"),
            "execution_regime": live.get("execution_regime"),
            "execution_allowed": live.get("execution_allowed"),
            "target_weights": live.get("target_weights"),
        },
        "best_heads": {
            "best_by_crps": best_by_crps,
            "best_by_pinball_q05": best_by_pinball,
            "recommended_research_baseline": "gaussian_residual_head",
            "gmm_status": "unstable_across_windows_research_only",
            "param_sweep": {
                "available": bool(param_sweep),
                "win_counts": param_sweep.get("win_counts"),
                "best_gmm_candidate": param_sweep.get("best_gmm_candidate"),
            },
            "crash_window_param_sweeps": _crash_sweep_summary(crash_sweep_paths),
        },
        "head_metrics": {
            "point": point,
            "gaussian": gaussian,
            "gmm": gmm,
        },
        "advisory": {
            "level": "research_only",
            "active": False,
            "recommended_action": "keep_density_head_as_tail_calibration_diagnostic",
            "allow_auto_weight_change": False,
            "allow_execution_block": False,
            "allow_00631l_auto_reduce": False,
            "allow_00631l_auto_add": False,
        },
        "decision": {
            "summary": "Gaussian residual density head improves 00631L H20 tail calibration. Crash-window sweeps support Gaussian in 2018/2020; 2026 recent GMM strength is not enough for live promotion.",
            "promote_to_live": False,
            "promote_to_no_add_guard": False,
            "target_weight_change_allowed": False,
        },
        "inputs": {
            "density_report": str(density_path) if density_path.exists() else None,
            "param_sweep": str(param_sweep_path) if param_sweep_path.exists() else None,
            "live_signal": str(live_signal_path) if live_signal_path and live_signal_path.exists() else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--density", default=str(DEFAULT_DENSITY))
    parser.add_argument("--param-sweep", default=str(DEFAULT_PARAM_SWEEP))
    parser.add_argument(
        "--crash-sweep",
        action="append",
        default=[],
        help="Optional crash-window param sweep JSON. May be repeated.",
    )
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = _resolve(args.output)
    advisory = build_advisory(
        density_path=_resolve(args.density),
        param_sweep_path=_resolve(args.param_sweep),
        crash_sweep_paths=[_resolve(path) for path in (args.crash_sweep or [])]
        or [path.resolve() for path in DEFAULT_CRASH_SWEEPS],
        live_signal_path=_resolve(args.live_signal) if args.live_signal else None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(advisory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Advisory: {output}")
    print(
        json.dumps(
            {
                "best_by_crps": advisory["best_heads"]["best_by_crps"],
                "best_by_pinball_q05": advisory["best_heads"]["best_by_pinball_q05"],
                "recommended_research_baseline": advisory["best_heads"]["recommended_research_baseline"],
                "promote_to_live": advisory["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
