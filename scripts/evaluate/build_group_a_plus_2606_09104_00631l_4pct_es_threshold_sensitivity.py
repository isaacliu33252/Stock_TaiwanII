#!/usr/bin/env python3
"""Build ES-threshold sensitivity for the 2606.09104 00631L 4% candidate."""

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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import build_sweep  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_es_threshold_sensitivity.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_es_threshold_sensitivity/history"
DEFAULT_ES_THRESHOLDS = (-0.002, -0.0025, -0.003)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def build_sensitivity(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    min_events: int = 20,
    es_thresholds: tuple[float, ...] = DEFAULT_ES_THRESHOLDS,
    max_mdd_extra_loss: float = -0.01,
) -> dict[str, Any]:
    reviews: list[dict[str, Any]] = []
    blockers: list[str] = []
    as_of = end
    for threshold in es_thresholds:
        report = build_sweep(
            db_path=db_path,
            start=start,
            end=end,
            horizon=horizon,
            lookback=lookback,
            caps=(0.04,),
            min_events=min_events,
            max_mdd_extra_loss=max_mdd_extra_loss,
            max_es_extra_loss=threshold,
        )
        if report.get("blocking_reasons"):
            blockers.extend(str(reason) for reason in report.get("blocking_reasons", []))
        as_of = str(report.get("as_of") or as_of)
        cap_review = report.get("cap_reviews", [{}])[0] if report.get("cap_reviews") else {}
        reviews.append(
            {
                "max_es_extra_loss": threshold,
                "passes_high_extreme_gate": cap_review.get("passes_high_extreme_gate", False),
                "passes_all_state_gate": cap_review.get("passes_all_state_gate", False),
                "high_extreme_summary": cap_review.get("high_extreme_summary", {}),
                "all_state_summary": cap_review.get("all_state_summary", {}),
            }
        )
    pass_count = sum(1 for row in reviews if row["passes_high_extreme_gate"])
    fragile = bool(0 < pass_count < len(reviews))
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_es_threshold_sensitivity",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "fixed_threshold_sensitivity_shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "student_t_tail_gate_threshold_sensitivity",
            "not_imported": ["threshold_optimization", "unconstrained_BLED_optimizer", "short_selling"],
        },
        "parameters": {
            "start": start,
            "end": end,
            "horizon": horizon,
            "lookback": lookback,
            "candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
            "es_thresholds": list(es_thresholds),
            "max_mdd_extra_loss": max_mdd_extra_loss,
            "min_events": min_events,
        },
        "threshold_reviews": reviews,
        "decision": {
            "passes_all_tested_es_thresholds": pass_count == len(reviews) and not bool(blockers),
            "passes_any_tested_es_threshold": pass_count > 0 and not bool(blockers),
            "tail_gate_fragile_to_threshold": fragile,
            "allow_00631l_micro_add_from_sensitivity": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Fixed ES threshold sensitivity only; it cannot authorize live exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": ["tail_gate_threshold_fragile"] if fragile else [],
    }


def write_sensitivity(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_es_threshold_sensitivity_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--es-thresholds", default="-0.002,-0.0025,-0.003")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_sensitivity(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        min_events=args.min_events,
        es_thresholds=tuple(float(item.strip()) for item in args.es_thresholds.split(",") if item.strip()),
    )
    write_sensitivity(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
