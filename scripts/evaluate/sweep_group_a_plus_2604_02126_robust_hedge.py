#!/usr/bin/env python3
"""Sweep GroupA+ 2604.02126 robust hedge shadow parameters."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2604_02126_robust_hedge_review import (
    DEFAULT_DB,
    DEFAULT_LATEST_STRATEGY,
    DEFAULT_LETF_READINESS,
    _finite,
    _resolve,
    build_review,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_robust_hedge_sweep.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_robust_hedge_sweep.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_02126_robust_hedge_sweep/history"


def _parse_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _method(review: dict[str, Any], name: str) -> dict[str, Any]:
    return (((review.get("hedge_review") or {}).get("method_comparison") or {}).get(name) or {})


def _effectiveness(method: dict[str, Any], field: str) -> float | None:
    eff = method.get("effectiveness")
    if not isinstance(eff, dict):
        return None
    return _finite(eff.get(field))


def _row(review: dict[str, Any], *, window: int, uncertainty_window: int, cap: float) -> dict[str, Any]:
    standard = _method(review, "standard")
    robust = _method(review, "robust_variance_only")
    full_box = _method(review, "robust_full_box")
    robust_turnover_delta = _finite(robust.get("turnover_reduction_vs_standard"))
    robust_std_delta = _finite(robust.get("exposure_std_reduction_vs_standard"))
    robust_cond_he = _effectiveness(robust, "conditional_hedge_effectiveness")
    standard_cond_he = _effectiveness(standard, "conditional_hedge_effectiveness")
    robust_he = _effectiveness(robust, "hedge_effectiveness")
    standard_he = _effectiveness(standard, "hedge_effectiveness")
    full_box_zero_rate = _finite(full_box.get("zero_or_near_zero_exposure_rate"))
    passes_shadow_filter = (
        robust_turnover_delta is not None
        and robust_turnover_delta >= 0.0
        and robust_std_delta is not None
        and robust_std_delta >= 0.0
        and robust_cond_he is not None
        and standard_cond_he is not None
        and robust_cond_he >= standard_cond_he
    )
    score_terms = [
        robust_turnover_delta,
        robust_std_delta,
        _finite((robust_cond_he or 0.0) - (standard_cond_he or 0.0)),
        _finite((robust_he or 0.0) - (standard_he or 0.0)),
    ]
    score = sum(term for term in score_terms if term is not None)
    return {
        "window": window,
        "uncertainty_window": uncertainty_window,
        "max_hedge_weight": cap,
        "observation_count": (review.get("hedge_review") or {}).get("observation_count"),
        "robust_latest_exposure": robust.get("latest_long_inverse_exposure"),
        "standard_latest_exposure": standard.get("latest_long_inverse_exposure"),
        "robust_mean_turnover": robust.get("mean_abs_daily_turnover"),
        "standard_mean_turnover": standard.get("mean_abs_daily_turnover"),
        "robust_turnover_reduction_vs_standard": robust_turnover_delta,
        "robust_exposure_std_reduction_vs_standard": robust_std_delta,
        "robust_he": robust_he,
        "standard_he": standard_he,
        "robust_conditional_he": robust_cond_he,
        "standard_conditional_he": standard_cond_he,
        "full_box_zero_or_near_zero_exposure_rate": full_box_zero_rate,
        "passes_shadow_filter": passes_shadow_filter,
        "score": _finite(score),
    }


def build_sweep(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    start: str = "2020-01-01",
    windows: list[int] | None = None,
    uncertainty_windows: list[int] | None = None,
    caps: list[float] | None = None,
    letf_readiness_path: Path = DEFAULT_LETF_READINESS,
    latest_strategy_path: Path = DEFAULT_LATEST_STRATEGY,
) -> dict[str, Any]:
    window_values = windows or [63, 126, 252]
    uncertainty_values = uncertainty_windows or [63, 126, 252]
    cap_values = caps or [0.10, 0.20, 0.30]
    rows: list[dict[str, Any]] = []
    for window in window_values:
        for uncertainty_window in uncertainty_values:
            for cap in cap_values:
                if window + uncertainty_window < 40:
                    continue
                review = build_review(
                    db_path=db_path,
                    as_of=as_of,
                    start=start,
                    window=window,
                    uncertainty_window=uncertainty_window,
                    max_hedge_weight=cap,
                    letf_readiness_path=letf_readiness_path,
                    latest_strategy_path=latest_strategy_path,
                )
                rows.append(_row(review, window=window, uncertainty_window=uncertainty_window, cap=cap))

    eligible = [row for row in rows if row["passes_shadow_filter"]]
    ranked = sorted(rows, key=lambda row: (-np.inf if row.get("score") is None else -float(row["score"])))
    blockers = [
        "research_only_parameter_sweep",
        "letf_readiness_blocks_00632r_open",
        "live_hedge_policy_not_validated_for_robust_ratio",
        "daily_close_proxy_not_high_frequency_realized_covariance",
        "transaction_cost_and_execution_slippage_not_revalidated",
    ]
    if not eligible:
        blockers.append("no_parameter_set_passed_shadow_stability_filter")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_02126_robust_hedge_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "research_only_parameter_sweep_no_00632r_open_no_weight_change",
        "status": "blocked_for_live_promotion",
        "grid": {
            "windows": window_values,
            "uncertainty_windows": uncertainty_values,
            "max_hedge_weights": cap_values,
            "parameter_count": len(rows),
        },
        "selection_rule": {
            "passes_shadow_filter": [
                "robust_turnover_reduction_vs_standard >= 0",
                "robust_exposure_std_reduction_vs_standard >= 0",
                "robust_conditional_he >= standard_conditional_he",
            ],
            "score": "turnover_reduction + exposure_std_reduction + conditional_he_delta + he_delta",
        },
        "eligible_parameter_count": len(eligible),
        "best_rows": ranked[:10],
        "eligible_rows": sorted(eligible, key=lambda row: (-np.inf if row.get("score") is None else -float(row["score"])))[:10],
        "all_rows": rows,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "sweep_complete": bool(rows),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "robust_hedge_ratio_can_cap_00632r_shadow": True,
            "robust_hedge_ratio_can_increase_00632r_live": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "db_path": str(db_path),
            "letf_tracking_error_effective_fee_readiness": str(letf_readiness_path),
            "latest_strategy_preview": str(latest_strategy_path),
        },
    }


def _fmt(value: Any, digits: int = 6) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def render_markdown(sweep: dict[str, Any]) -> str:
    lines = [
        "# 2604.02126 Robust Hedge Parameter Sweep",
        "",
        f"Generated: `{sweep.get('generated_at')}`",
        f"As of: `{sweep.get('as_of')}`",
        f"Status: `{sweep.get('status')}`",
        "",
        "## Decision",
        "",
        "- Do not change live target weights.",
        "- Do not open or increase `00632R.TW`.",
        "- Keep `Golden1_0531` unchanged.",
        "- Keep robust hedge ratio as shadow/cap diagnostics only.",
        "",
        "## Sweep Summary",
        "",
        f"- parameter count: `{(sweep.get('grid') or {}).get('parameter_count')}`",
        f"- eligible parameter count: `{sweep.get('eligible_parameter_count')}`",
        "",
        "## Top Rows",
        "",
        "| window | uncertainty | cap | score | robust latest | turnover delta | std delta | robust CHE | standard CHE | pass |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in sweep.get("best_rows", [])[:10]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("window")),
                    str(row.get("uncertainty_window")),
                    _fmt(row.get("max_hedge_weight"), 2),
                    _fmt(row.get("score")),
                    _fmt(row.get("robust_latest_exposure")),
                    _fmt(row.get("robust_turnover_reduction_vs_standard")),
                    _fmt(row.get("robust_exposure_std_reduction_vs_standard")),
                    _fmt(row.get("robust_conditional_he")),
                    _fmt(row.get("standard_conditional_he")),
                    str(row.get("passes_shadow_filter")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Blockers",
            "",
            *(f"- `{reason}`" for reason in sweep.get("blocking_reasons", [])),
            "",
        ]
    )
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"2604_02126_robust_hedge_sweep_{stamp}.json"


def write_sweep(
    sweep: dict[str, Any],
    output_path: Path,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sweep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_markdown(sweep) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, sweep.get("as_of")).write_text(
        json.dumps(sweep, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--windows", default="63,126,252")
    parser.add_argument("--uncertainty-windows", default="63,126,252")
    parser.add_argument("--caps", default="0.10,0.20,0.30")
    parser.add_argument("--letf-readiness", default=str(DEFAULT_LETF_READINESS))
    parser.add_argument("--latest-strategy", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    sweep = build_sweep(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        start=args.start,
        windows=_parse_ints(args.windows),
        uncertainty_windows=_parse_ints(args.uncertainty_windows),
        caps=_parse_floats(args.caps),
        letf_readiness_path=_resolve(args.letf_readiness),
        latest_strategy_path=_resolve(args.latest_strategy),
    )
    output_md = None if not args.output_md else _resolve(args.output_md)
    write_sweep(sweep, _resolve(args.output), output_md, None if args.no_history else _resolve(args.history_dir))
    print(f"2604.02126 robust hedge sweep: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": sweep["status"],
                "parameter_count": sweep["grid"]["parameter_count"],
                "eligible_parameter_count": sweep["eligible_parameter_count"],
                "allow_00632r_open": sweep["decision"]["allow_00632r_open"],
                "top_score": sweep["best_rows"][0]["score"] if sweep["best_rows"] else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
