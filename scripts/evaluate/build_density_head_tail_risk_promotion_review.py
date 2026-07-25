#!/usr/bin/env python3
"""Build a multi-window promotion review for the density-head GMM shadow.

Research-only. This combines existing parameter-sweep JSON artifacts and
decides whether the GMM residual head is stable enough to promote over the
Gaussian residual head. It never changes live weights or execution guards.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "report"
    / "group_a_plus"
    / "latest"
    / "density_head_tail_risk_promotion_review.json"
)
DEFAULT_SWEEPS = [
    (
        "2018_correction",
        "crash",
        PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2018_correction.json",
    ),
    (
        "2020_covid",
        "crash",
        PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2020_covid.json",
    ),
    (
        "2022_rate_hike_backfill",
        "stress",
        PROJECT_ROOT
        / "results"
        / "density_head_tail_risk_param_sweep_00631l_2022_rate_hike_backfill_20260717.json",
    ),
    (
        "2025_2026_main",
        "main",
        PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_20250102_20260716.json",
    ),
    (
        "2026_recent",
        "recent",
        PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_2026_recent.json",
    ),
]


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if denominator in (None, 0):
        return None
    if numerator is None:
        return None
    return float(numerator) / float(denominator)


def _window_summary(name: str, role: str, path: Path) -> dict[str, Any]:
    payload = _load(path)
    win_counts = payload.get("win_counts") or {}
    best = payload.get("best_gmm_candidate") or {}
    rows = int(win_counts.get("rows") or 0)
    gmm_crps = int(win_counts.get("gmm_wins_crps") or 0)
    gmm_q05 = int(win_counts.get("gmm_wins_pinball_q05") or 0)
    gaussian_crps = int(win_counts.get("gaussian_wins_crps") or 0)
    gaussian_q05 = int(win_counts.get("gaussian_wins_pinball_q05") or 0)
    gmm_crps_rate = _ratio(gmm_crps, rows)
    gmm_q05_rate = _ratio(gmm_q05, rows)
    stable_gmm_win = bool(
        rows > 0
        and gmm_crps_rate is not None
        and gmm_q05_rate is not None
        and gmm_crps_rate >= 0.80
        and gmm_q05_rate >= 0.60
    )
    return {
        "window": name,
        "role": role,
        "path": str(path),
        "available": bool(payload),
        "rows": rows,
        "win_counts": {
            "gmm_wins_crps": gmm_crps,
            "gmm_wins_pinball_q05": gmm_q05,
            "gaussian_wins_crps": gaussian_crps,
            "gaussian_wins_pinball_q05": gaussian_q05,
        },
        "rates": {
            "gmm_crps_win_rate": gmm_crps_rate,
            "gmm_q05_win_rate": gmm_q05_rate,
        },
        "stable_gmm_win": stable_gmm_win,
        "best_gmm_candidate": {
            "gmm_components": best.get("gmm_components"),
            "alert_quantile": best.get("alert_quantile"),
            "seed": best.get("seed"),
            "gmm_crps": best.get("gmm_crps"),
            "gaussian_crps": best.get("gaussian_crps"),
            "gmm_pinball_q05": best.get("gmm_pinball_q05"),
            "gaussian_pinball_q05": best.get("gaussian_pinball_q05"),
            "gmm_tail_alert_precision": best.get("gmm_tail_alert_precision"),
            "gmm_tail_alert_fpr": best.get("gmm_tail_alert_fpr"),
        },
    }


def build_review(sweeps: list[tuple[str, str, Path]]) -> dict[str, Any]:
    windows = [_window_summary(name, role, path) for name, role, path in sweeps]
    available = [row for row in windows if row["available"]]
    critical = [row for row in available if row["role"] == "crash"]
    gmm_stable_windows = [row for row in available if row["stable_gmm_win"]]
    crash_failures = [row for row in critical if not row["stable_gmm_win"]]
    total_rows = sum(int(row["rows"]) for row in available)
    gmm_crps_wins = sum(int(row["win_counts"]["gmm_wins_crps"]) for row in available)
    gmm_q05_wins = sum(int(row["win_counts"]["gmm_wins_pinball_q05"]) for row in available)
    aggregate = {
        "available_windows": len(available),
        "total_rows": total_rows,
        "gmm_crps_win_rate": _ratio(gmm_crps_wins, total_rows),
        "gmm_q05_win_rate": _ratio(gmm_q05_wins, total_rows),
        "stable_gmm_windows": [row["window"] for row in gmm_stable_windows],
        "crash_failures": [row["window"] for row in crash_failures],
    }
    promote_to_live = bool(
        len(available) == len(windows)
        and not crash_failures
        and aggregate["gmm_crps_win_rate"] is not None
        and aggregate["gmm_q05_win_rate"] is not None
        and aggregate["gmm_crps_win_rate"] >= 0.70
        and aggregate["gmm_q05_win_rate"] >= 0.60
    )
    blockers: list[str] = []
    if len(available) != len(windows):
        blockers.append("missing_required_sweep_window")
    if crash_failures:
        blockers.append("gmm_failed_required_crash_windows")
    if not promote_to_live and aggregate["gmm_crps_win_rate"] is not None:
        if aggregate["gmm_crps_win_rate"] < 0.70:
            blockers.append("aggregate_gmm_crps_win_rate_below_70pct")
        if (aggregate["gmm_q05_win_rate"] or 0.0) < 0.60:
            blockers.append("aggregate_gmm_q05_win_rate_below_60pct")

    return {
        "schema_version": 1,
        "report_type": "density_head_tail_risk_promotion_review",
        "status": "available" if available else "missing_inputs",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.30037.pdf",
            "title": "Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns",
        },
        "promotion_gate": {
            "candidate": "gmm_residual_head",
            "baseline": "gaussian_residual_head",
            "required_windows": [name for name, _role, _path in sweeps],
            "rules": {
                "all_required_windows_available": True,
                "no_required_crash_window_failure": True,
                "aggregate_gmm_crps_win_rate_min": 0.70,
                "aggregate_gmm_q05_win_rate_min": 0.60,
                "per_window_stable_gmm_win": "gmm_crps_win_rate >= 0.80 and gmm_q05_win_rate >= 0.60",
            },
        },
        "aggregate": aggregate,
        "windows": windows,
        "decision": {
            "promote_to_live": promote_to_live,
            "promote_to_no_add_guard": False,
            "allow_auto_weight_change": False,
            "allow_00631l_auto_add": False,
            "recommended_research_baseline": "gaussian_residual_head" if not promote_to_live else "gmm_residual_head",
            "summary": (
                "Do not promote GMM: it improved 2022 backfill and 2026 recent, "
                "but failed required 2018/2020 crash-window stability."
                if not promote_to_live
                else "GMM passed the multi-window research promotion gate."
            ),
            "blockers": blockers,
        },
    }


def _parse_sweep(raw: str) -> tuple[str, str, Path]:
    parts = raw.split("=", 2)
    if len(parts) != 3:
        raise ValueError("--sweep must use name=role=path")
    name, role, path = parts
    return name, role, _resolve(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep",
        action="append",
        default=[],
        help="Optional sweep in name=role=path format. May be repeated.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    sweeps = [_parse_sweep(item) for item in args.sweep] if args.sweep else DEFAULT_SWEEPS
    output = _resolve(args.output)
    review = build_review(sweeps)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Promotion review: {output}")
    print(
        json.dumps(
            {
                "promote_to_live": review["decision"]["promote_to_live"],
                "recommended_research_baseline": review["decision"]["recommended_research_baseline"],
                "blockers": review["decision"]["blockers"],
                "aggregate": review["aggregate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
