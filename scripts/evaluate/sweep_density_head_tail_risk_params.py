#!/usr/bin/env python3
"""Parameter sweep for density-head tail-risk shadow.

Research-only. This checks whether residual GMM settings can consistently beat
the Gaussian residual head on 00631L H20 tail calibration.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_density_head_tail_risk_shadow import (  # noqa: E402
    DEFAULT_PANEL,
    evaluate_density_heads,
    _load_panel,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "density_head_tail_risk_param_sweep_00631l_20250102_20260716.json"


def _parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _metric(report: dict[str, Any], head: str) -> dict[str, Any]:
    agg = (report.get("aggregate") or {}).get(head) or {}
    tail = agg.get("tail_alert_global_threshold") or {}
    return {
        "crps": agg.get("crps_sample"),
        "pinball_q05": (agg.get("pinball") or {}).get("q05"),
        "var05_breach_rate": ((agg.get("var_backtest") or {}).get("var_05") or {}).get("breach_rate"),
        "central90_coverage": ((agg.get("coverage") or {}).get("central_90") or {}).get("coverage"),
        "tail_alert_precision": tail.get("combined_adverse_precision"),
        "tail_alert_recall": tail.get("combined_adverse_recall"),
        "tail_alert_fpr": tail.get("combined_adverse_fpr"),
        "tail_alert_active_days": tail.get("active_days"),
    }


def _score(row: dict[str, Any]) -> float:
    crps = row.get("gmm_crps")
    pinball = row.get("gmm_pinball_q05")
    breach = row.get("gmm_var05_breach_rate")
    coverage = row.get("gmm_central90_coverage")
    if crps is None or pinball is None or breach is None or coverage is None:
        return -1.0
    breach_error = abs(float(breach) - 0.05)
    coverage_error = abs(float(coverage) - 0.90)
    return float(-(0.45 * crps) - (0.30 * pinball) - (0.15 * breach_error) - (0.10 * coverage_error))


def run_sweep(
    *,
    panel_path: Path,
    start: str | None,
    end: str | None,
    n_splits: int,
    gap: int,
    n_samples: int,
    gmm_components_grid: list[int],
    alert_quantile_grid: list[float],
    seed_grid: list[int],
) -> dict[str, Any]:
    panel = _load_panel(panel_path, start, end)
    rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for gmm_components, alert_quantile, seed in itertools.product(
        gmm_components_grid,
        alert_quantile_grid,
        seed_grid,
    ):
        report, _pred = evaluate_density_heads(
            panel,
            n_splits=n_splits,
            gap=gap,
            n_samples=n_samples,
            gmm_components=gmm_components,
            alert_quantile=alert_quantile,
            seed=seed,
        )
        point = _metric(report, "point")
        gaussian = _metric(report, "gaussian")
        gmm = _metric(report, "gmm")
        row = {
            "gmm_components": int(gmm_components),
            "alert_quantile": float(alert_quantile),
            "seed": int(seed),
            "best_by_crps": report.get("best_by_crps"),
            "best_by_pinball_q05": report.get("best_by_pinball_q05"),
            "point_crps": point["crps"],
            "gaussian_crps": gaussian["crps"],
            "gmm_crps": gmm["crps"],
            "point_pinball_q05": point["pinball_q05"],
            "gaussian_pinball_q05": gaussian["pinball_q05"],
            "gmm_pinball_q05": gmm["pinball_q05"],
            "point_var05_breach_rate": point["var05_breach_rate"],
            "gaussian_var05_breach_rate": gaussian["var05_breach_rate"],
            "gmm_var05_breach_rate": gmm["var05_breach_rate"],
            "point_central90_coverage": point["central90_coverage"],
            "gaussian_central90_coverage": gaussian["central90_coverage"],
            "gmm_central90_coverage": gmm["central90_coverage"],
            "gmm_tail_alert_precision": gmm["tail_alert_precision"],
            "gmm_tail_alert_recall": gmm["tail_alert_recall"],
            "gmm_tail_alert_fpr": gmm["tail_alert_fpr"],
            "gmm_tail_alert_active_days": gmm["tail_alert_active_days"],
        }
        row["gmm_score"] = _score(row)
        row["gmm_beats_gaussian_crps"] = bool(row["gmm_crps"] < row["gaussian_crps"])
        row["gmm_beats_gaussian_pinball_q05"] = bool(row["gmm_pinball_q05"] < row["gaussian_pinball_q05"])
        rows.append(row)
        reports.append(
            {
                "gmm_components": int(gmm_components),
                "alert_quantile": float(alert_quantile),
                "seed": int(seed),
                "best_by_crps": report.get("best_by_crps"),
                "best_by_pinball_q05": report.get("best_by_pinball_q05"),
                "promotion_decision": report.get("promotion_decision"),
            }
        )

    rows_sorted = sorted(rows, key=lambda row: row["gmm_score"], reverse=True)
    gaussian_wins_crps = sum(1 for row in rows if row["best_by_crps"] == "gaussian")
    gaussian_wins_pinball = sum(1 for row in rows if row["best_by_pinball_q05"] == "gaussian")
    gmm_wins_crps = sum(1 for row in rows if row["best_by_crps"] == "gmm")
    gmm_wins_pinball = sum(1 for row in rows if row["best_by_pinball_q05"] == "gmm")
    return {
        "schema_version": 1,
        "experiment": "density_head_tail_risk_param_sweep",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_weight_change",
        "parameters": {
            "panel": str(panel_path),
            "start": start,
            "end": end,
            "n_splits": int(n_splits),
            "gap": int(gap),
            "n_samples": int(n_samples),
            "gmm_components_grid": gmm_components_grid,
            "alert_quantile_grid": alert_quantile_grid,
            "seed_grid": seed_grid,
        },
        "win_counts": {
            "rows": int(len(rows)),
            "gaussian_wins_crps": int(gaussian_wins_crps),
            "gaussian_wins_pinball_q05": int(gaussian_wins_pinball),
            "gmm_wins_crps": int(gmm_wins_crps),
            "gmm_wins_pinball_q05": int(gmm_wins_pinball),
        },
        "best_gmm_candidate": rows_sorted[0] if rows_sorted else None,
        "top_rows": rows_sorted[:20],
        "rows": rows_sorted,
        "decision": (
            "Use Gaussian residual head as the current research baseline unless GMM "
            "wins both CRPS and q05 pinball across stable stress windows. No live promotion."
        ),
        "reports": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=20)
    parser.add_argument("--n-samples", type=int, default=500)
    parser.add_argument("--gmm-components-grid", default="2,3,4,6,8")
    parser.add_argument("--alert-quantile-grid", default="0.10,0.20,0.30")
    parser.add_argument("--seed-grid", default="42,137")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    report = run_sweep(
        panel_path=_resolve_panel(args.panel),
        start=args.start,
        end=args.end,
        n_splits=int(args.n_splits),
        gap=int(args.gap),
        n_samples=int(args.n_samples),
        gmm_components_grid=_parse_ints(args.gmm_components_grid),
        alert_quantile_grid=_parse_floats(args.alert_quantile_grid),
        seed_grid=_parse_ints(args.seed_grid),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_output = output.with_name(output.stem + "_rows.csv")
    pd.DataFrame(report["rows"]).to_csv(csv_output, index=False, encoding="utf-8-sig")
    report["csv_output"] = str(csv_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"CSV: {csv_output}")
    print(
        json.dumps(
            {
                "win_counts": report["win_counts"],
                "best_gmm_candidate": report["best_gmm_candidate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _resolve_panel(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


if __name__ == "__main__":
    main()
