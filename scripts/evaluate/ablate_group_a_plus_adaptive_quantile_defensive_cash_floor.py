#!/usr/bin/env python3
"""Run fold ablation for the defensive cash-floor shadow candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.backtest_group_a_plus_adaptive_quantile_risk_gate_frame import (  # noqa: E402
    DB_PATH,
    DEFAULT_FRAME,
    DEFAULT_REPORT,
    DEFAULT_TICKERS,
    _json_default,
    _load_close,
    _load_report,
)
from scripts.evaluate.sweep_group_a_plus_adaptive_quantile_defensive_cash_floor import (  # noqa: E402
    _parse_floats,
    _parse_ints,
    _score,
    _variant_replay,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_ablation_latest.json"

HOLDOUT_WINDOWS = {
    "year_2024": ("2024-01-01", "2024-12-31"),
    "year_2025": ("2025-01-01", "2025-12-31"),
    "year_2026": ("2026-01-01", "2026-12-31"),
    "2025_tariff_shock": ("2025-02-24", "2025-05-09"),
    "2026_summer_drawdown": ("2026-06-01", "2026-08-05"),
}


def _name(cash_floor: float, total_risk_min: int, tail_risk_min: int) -> str:
    return f"cash{int(cash_floor * 100):02d}_risk{total_risk_min}_tail{tail_risk_min}"


def _params_from_name(name: str) -> dict[str, Any]:
    cash_part, risk_part, tail_part = name.split("_")
    return {
        "cash_floor": int(cash_part.replace("cash", "")) / 100.0,
        "total_risk_min": int(risk_part.replace("risk", "")),
        "tail_risk_min": int(tail_part.replace("tail", "")),
    }


def _rank_variants(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    *,
    cash_floors: list[float],
    total_risk_mins: list[int],
    tail_risk_mins: list[int],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for cash_floor in cash_floors:
        for total_risk_min in total_risk_mins:
            for tail_risk_min in tail_risk_mins:
                replay = _variant_replay(
                    report,
                    frame,
                    close,
                    cash_floor=cash_floor,
                    total_risk_min=total_risk_min,
                    tail_risk_min=tail_risk_min,
                )
                delta = replay["delta"]
                ranked.append(
                    {
                        "variant": _name(cash_floor, total_risk_min, tail_risk_min),
                        "score": _score(replay),
                        "cash_floor": cash_floor,
                        "total_risk_min": total_risk_min,
                        "tail_risk_min": tail_risk_min,
                        "changed_days": replay["changed_days"],
                        "active_days": replay["active_days"],
                        "total_return_delta": delta["total_return_delta"],
                        "sharpe_delta": delta["sharpe_delta"],
                        "max_drawdown_delta": delta["max_drawdown_delta"],
                        "worst_day_delta": delta["worst_day_delta"],
                    }
                )
    return sorted(ranked, key=lambda row: (row["score"], row["total_return_delta"]), reverse=True)


def _holdout_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    dt = pd.to_datetime(frame["dt"]).dt.normalize()
    return (dt >= pd.Timestamp(start)) & (dt <= pd.Timestamp(end))


def _evaluate_variant(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    variant: str,
) -> dict[str, Any]:
    params = _params_from_name(variant)
    replay = _variant_replay(report, frame, close, **params)
    delta = replay["delta"]
    return {
        "variant": variant,
        **params,
        "rows": replay["raw_metrics"]["n"],
        "changed_days": replay["changed_days"],
        "active_days": replay["active_days"],
        "score": _score(replay),
        "delta": delta,
        "checks": {
            "changed_days_present": replay["changed_days"] > 0,
            "nonworse_total_return": delta["total_return_delta"] >= -0.002,
            "nonworse_max_drawdown": delta["max_drawdown_delta"] >= -1e-12,
            "nonworse_worst_day": delta["worst_day_delta"] >= -1e-12,
        },
    }


def _same_family(candidate: str, selected: str) -> bool:
    base = _params_from_name(candidate)
    other = _params_from_name(selected)
    return (
        other["cash_floor"] >= 0.50
        and abs(other["cash_floor"] - base["cash_floor"]) <= 0.0500001
        and abs(other["total_risk_min"] - base["total_risk_min"]) <= 1
        and other["tail_risk_min"] in {1, 2}
    )


def ablate(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    *,
    candidate: str,
    cash_floors: list[float],
    total_risk_mins: list[int],
    tail_risk_mins: list[int],
) -> dict[str, Any]:
    work = frame.copy()
    work["dt"] = pd.to_datetime(work["dt"]).dt.normalize()
    folds: list[dict[str, Any]] = []
    for fold_name, (start, end) in HOLDOUT_WINDOWS.items():
        mask = _holdout_mask(work, start, end)
        train_frame = work.loc[~mask].copy()
        holdout_frame = work.loc[mask].copy()
        if holdout_frame.empty:
            folds.append({"fold": fold_name, "start": start, "end": end, "status": "no_rows"})
            continue

        train_ranked = _rank_variants(
            report,
            train_frame,
            close,
            cash_floors=cash_floors,
            total_risk_mins=total_risk_mins,
            tail_risk_mins=tail_risk_mins,
        )
        selected = train_ranked[0]["variant"] if train_ranked else None
        candidate_holdout = _evaluate_variant(report, holdout_frame, close, candidate)
        selected_holdout = _evaluate_variant(report, holdout_frame, close, selected) if selected else None
        candidate_checks = candidate_holdout["checks"]
        candidate_pass = all(candidate_checks.values())
        folds.append(
            {
                "fold": fold_name,
                "start": start,
                "end": end,
                "status": "ok",
                "train_rows": int(len(train_frame)),
                "holdout_rows": int(len(holdout_frame)),
                "train_selected_variant": selected,
                "train_selected_same_family": _same_family(candidate, selected) if selected else False,
                "train_selected_top5": train_ranked[:5],
                "candidate_holdout": candidate_holdout,
                "selected_holdout": selected_holdout,
                "candidate_holdout_pass": candidate_pass,
            }
        )

    evaluable = [
        fold
        for fold in folds
        if fold.get("status") == "ok" and (fold.get("candidate_holdout") or {}).get("changed_days", 0) > 0
    ]
    pass_count = sum(bool(fold.get("candidate_holdout_pass")) for fold in evaluable)
    same_family_count = sum(bool(fold.get("train_selected_same_family")) for fold in evaluable)
    fail_folds = [fold["fold"] for fold in evaluable if not fold.get("candidate_holdout_pass")]
    promotion = (
        "shadow_candidate_for_signed_review"
        if evaluable and pass_count == len(evaluable) and same_family_count >= max(1, len(evaluable) - 1)
        else "do_not_promote"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_defensive_cash_floor_ablation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "candidate": candidate,
        "method": "Leave one year/crisis period out, re-sweep on the remaining frame, then test both fixed and selected variants on the holdout.",
        "summary": {
            "fold_count": len(folds),
            "evaluable_changed_fold_count": len(evaluable),
            "candidate_pass_count": pass_count,
            "same_family_train_selection_count": same_family_count,
            "fail_folds": fail_folds,
        },
        "folds": folds,
        "decision": {
            "promotion_decision": promotion,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "reason": (
                "fixed candidate passed all changed holdouts and train-selected variants stayed in the same family"
                if promotion != "do_not_promote"
                else "holdout performance failed or train-selected variants were unstable"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--frame", default=str(DEFAULT_FRAME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--candidate", default="cash55_risk7_tail1")
    parser.add_argument("--cash-floors", default="0.40,0.45,0.50,0.55")
    parser.add_argument("--total-risk-mins", default="5,6,7,8")
    parser.add_argument("--tail-risk-mins", default="1,2,99")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = _load_report(Path(args.report))
    frame = pd.read_csv(args.frame)
    close = _load_close(Path(args.db), DEFAULT_TICKERS)
    result = ablate(
        report,
        frame,
        close,
        candidate=args.candidate,
        cash_floors=_parse_floats(args.cash_floors),
        total_risk_mins=_parse_ints(args.total_risk_mins),
        tail_risk_mins=_parse_ints(args.tail_risk_mins),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    print(
        "candidate={candidate} decision={decision} pass={passed}/{total} same_family={same}/{total} fails={fails}".format(
            candidate=result["candidate"],
            decision=result["decision"]["promotion_decision"],
            passed=result["summary"]["candidate_pass_count"],
            same=result["summary"]["same_family_train_selection_count"],
            total=result["summary"]["evaluable_changed_fold_count"],
            fails=result["summary"]["fail_folds"],
        )
    )
    print(f"JSON: {output}")


if __name__ == "__main__":
    main()
