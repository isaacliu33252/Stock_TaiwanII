#!/usr/bin/env python3
"""Temporal OOS validation for the TSI compounding ensemble sweep."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_sweep import DEFAULT_OUTPUT as DEFAULT_SWEEP
from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_sweep import _float
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _resolve


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_temporal_oos.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_temporal_oos.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_compounding_ensemble_temporal_oos/history"
DEFAULT_FOLDS = (
    "train_2020_2023__holdout_2024_2026:"
    "covid_2020,recovery_2021,rate_hike_2022,rebound_2023|"
    "full_2024,active_2025_2026,taiwan_2026_q1q2_stress,taiwan_2026_recent;"
    "train_2020_2024__holdout_2025_2026:"
    "covid_2020,recovery_2021,rate_hike_2022,rebound_2023,full_2024|"
    "active_2025_2026,taiwan_2026_q1q2_stress,taiwan_2026_recent"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_folds(raw: str) -> list[dict[str, Any]]:
    folds = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        name, rest = item.split(":", 1)
        train_raw, holdout_raw = rest.split("|", 1)
        folds.append(
            {
                "name": name.strip(),
                "train_labels": [label.strip() for label in train_raw.split(",") if label.strip()],
                "holdout_labels": [label.strip() for label in holdout_raw.split(",") if label.strip()],
            }
        )
    if not folds:
        raise ValueError("Expected at least one fold")
    return folds


def _combo_key(combo: dict[str, Any]) -> tuple[float, float]:
    return (float(combo["threshold"]), float(combo["tsi_trend_cap"]))


def _window_map(combo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["label"]): item for item in combo.get("windows") or []}


def _aggregate(combo: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    by_label = _window_map(combo)
    windows = [by_label[label] for label in labels if label in by_label]
    return {
        "labels": labels,
        "available_labels": [item["label"] for item in windows],
        "missing_labels": [label for label in labels if label not in by_label],
        "final_value_sum": float(sum(item["ensemble_delta_vs_compounding"]["final_value"] for item in windows)),
        "sharpe_sum": float(sum(item["ensemble_delta_vs_compounding"]["sharpe_ratio"] for item in windows)),
        "max_drawdown_sum": float(sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] for item in windows)),
        "positive_windows": int(sum(item["ensemble_delta_vs_compounding"]["final_value"] > 0.0 for item in windows)),
        "non_worse_drawdown_windows": int(sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] >= 0.0 for item in windows)),
        "n": int(len(windows)),
    }


def _combo_descriptor(combo: dict[str, Any]) -> dict[str, float]:
    return {"threshold": float(combo["threshold"]), "tsi_trend_cap": float(combo["tsi_trend_cap"])}


def build_temporal_oos_validation(sweep: dict[str, Any], folds: list[dict[str, Any]]) -> dict[str, Any]:
    combos = list(sweep.get("combo_windows") or [])
    blockers: list[str] = ["research_only_no_live_weight_change"]
    fold_reports: list[dict[str, Any]] = []
    if not combos:
        blockers.append("missing_combo_windows_in_sweep")

    for fold in folds:
        train_labels = list(fold["train_labels"])
        holdout_labels = list(fold["holdout_labels"])
        train_ranked = [
            {
                **_combo_descriptor(combo),
                "train": _aggregate(combo, train_labels),
                "holdout": _aggregate(combo, holdout_labels),
            }
            for combo in combos
        ]
        train_ranked.sort(
            key=lambda item: (
                item["train"]["final_value_sum"],
                item["train"]["non_worse_drawdown_windows"],
                item["train"]["sharpe_sum"],
            ),
            reverse=True,
        )
        selected = train_ranked[0] if train_ranked else None
        train = selected["train"] if selected else {}
        holdout = selected["holdout"] if selected else {}
        passed = bool(
            selected
            and train.get("final_value_sum", 0.0) > 0.0
            and train.get("positive_windows", 0) > 0
            and holdout.get("missing_labels") == []
            and holdout.get("final_value_sum", 0.0) > 0.0
            and holdout.get("non_worse_drawdown_windows", 0) == holdout.get("n", -1)
        )
        if not passed:
            blockers.append(f"temporal_oos_fold_failed:{fold['name']}")
        fold_reports.append(
            {
                "name": fold["name"],
                "train_labels": train_labels,
                "holdout_labels": holdout_labels,
                "selected_by_train": selected,
                "temporal_oos_passed": passed,
                "top3_by_train": train_ranked[:3],
            }
        )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_compounding_ensemble_temporal_oos",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "source_sweep_report_type": sweep.get("report_type"),
        "folds": fold_reports,
        "blocking_reasons": blockers,
        "decision": {
            "temporal_oos_passed": len(blockers) == 1,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    rows = []
    for fold in payload.get("folds") or []:
        selected = fold.get("selected_by_train") or {}
        holdout = selected.get("holdout") or {}
        rows.append(
            "| {name} | {threshold:.2f} | {cap:.2f} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} | {pos}/{n} | {mdd_ok}/{n} | {passed} |".format(
                name=fold.get("name"),
                threshold=_float(selected.get("threshold")),
                cap=_float(selected.get("tsi_trend_cap")),
                dfv=_float(holdout.get("final_value_sum")),
                dsharpe=_float(holdout.get("sharpe_sum")),
                dmdd=_float(holdout.get("max_drawdown_sum")),
                pos=int(holdout.get("positive_windows") or 0),
                mdd_ok=int(holdout.get("non_worse_drawdown_windows") or 0),
                n=int(holdout.get("n") or 0),
                passed=fold.get("temporal_oos_passed"),
            )
        )
    return """# GroupA+ TSI Compounding Ensemble Temporal OOS

- status: `research_only`
- production_effect: `none`
- temporal_oos_passed: `{passed}`
- promotion_allowed: `{promotion}`

## Folds

| fold | selected_threshold | selected_cap | holdout_delta_final_value | holdout_delta_sharpe | holdout_delta_max_drawdown | positive_windows | non_worse_mdd_windows | passed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Blocking Reasons

```json
{blockers}
```

## Governance

This validation is research-only. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L permission.
""".format(
        passed=payload.get("decision", {}).get("temporal_oos_passed"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - | - | - | - |",
        blockers=json.dumps(payload.get("blocking_reasons") or [], ensure_ascii=False, indent=2),
    )


def write_report(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"tsi_compounding_ensemble_temporal_oos_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--folds", default=DEFAULT_FOLDS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_temporal_oos_validation(_load_json(_resolve(args.sweep)), _parse_folds(args.folds))
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"TSI compounding ensemble temporal OOS: {_resolve(args.output)}")
    print(json.dumps(payload["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
