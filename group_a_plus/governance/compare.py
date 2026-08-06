"""Compare GroupA+ candidate result JSON files against an A20.7 baseline."""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tw_output_standard import OutputStandardizer, write_standard_output


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data", payload) if isinstance(payload, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return _unwrap(json.load(handle))


def _metrics_from_report(report: dict[str, Any]) -> dict[str, float]:
    if isinstance(report.get("metrics"), dict):
        return report["metrics"]
    baseline = report.get("baseline")
    if isinstance(baseline, dict):
        if isinstance(baseline.get("metrics"), dict):
            return baseline["metrics"]
        if "final_value" in baseline:
            return baseline
    summary = report.get("summary")
    if isinstance(summary, dict):
        if isinstance(summary.get("a207"), dict):
            return summary["a207"]
        if isinstance(summary.get("switch_risk_ma75_dd11_total6_hold5_eg0175_xg020"), dict):
            return summary["switch_risk_ma75_dd11_total6_hold5_eg0175_xg020"]
    raise ValueError("Could not locate baseline metrics in report")


def _candidate_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("rows", "selector_rows", "guard_rows", "rule_reports"):
        value = report.get(key)
        if isinstance(value, list):
            if key == "rule_reports":
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("metrics"), dict):
                        rows.append({"variant": item.get("variant") or item.get("name"), **item["metrics"]})
            else:
                rows.extend(row for row in value if isinstance(row, dict))
    if not rows and isinstance(report.get("best"), dict):
        rows.append(report["best"])
    summary = report.get("summary")
    if isinstance(summary, dict):
        for key in ("best_by_final_value", "best_by_max_drawdown", "best_by_sharpe"):
            value = summary.get(key)
            if isinstance(value, dict):
                candidate = {"variant": key, **value}
                if isinstance(value.get("metrics"), dict):
                    candidate.update(value["metrics"])
                rows.append(candidate)
    for key in ("top_by_final_value", "top_by_sharpe", "top_by_mdd_then_value"):
        value = report.get(key)
        if isinstance(value, dict):
            candidate = {"variant": key, **value}
            if isinstance(value.get("metrics"), dict):
                candidate.update(value["metrics"])
            rows.append(candidate)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidate = {"variant": key, **item}
                    if isinstance(item.get("metrics"), dict):
                        candidate.update(item["metrics"])
                    rows.append(candidate)
    return rows


def _effective_override(row: dict[str, Any]) -> int:
    for key in ("override_days", "effective_override_days"):
        if key in row and pd.notna(row[key]):
            return int(row[key])
    for key in ("trigger_days", "event_count"):
        if key in row and pd.notna(row[key]):
            return int(row[key])
    return 0


# 2026-08-01 user proposal (grounded in arXiv:2607.16450v1, Taiwan/semiconductor-ETF
# heavy-tail study): variance-based measures (final_value/Sharpe/MDD, the three
# constraints above) can rank candidates very differently from tail-sensitive
# measures. These field names match what scripts/evaluate/evaluate_cvar_tail_risk_
# diagnostic_shadow.py and evaluate_a2118_h20_tail_score_shadow.py already compute
# as shadow-only research diagnostics -- no current candidate report populates them
# into its `metrics` dict yet, so promotion_utility below is forward-looking
# infrastructure, not something already influencing real candidates today.
TAIL_RISK_METRIC_KEYS = {
    "expected_shortfall_95": "expected_shortfall_loss_95",
    "starr_95": "starr_95",
    "rachev_95_95": "rachev_95_95",
    "worst_5d_return": "worst_5d_return",
    "worst_10d_return": "worst_10d_return",
    "max_drawdown_duration": "max_drawdown_duration",
    "recovery_duration": "recovery_duration",
    "transaction_cost": "transaction_cost",
}


def _optional_float(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _tail_risk_metrics(metrics: dict[str, Any]) -> dict[str, float | None]:
    return {name: _optional_float(metrics, key) for name, key in TAIL_RISK_METRIC_KEYS.items()}


def _promotion_utility(
    *,
    final_value_delta: float,
    baseline_tail: dict[str, float | None],
    candidate_tail: dict[str, float | None],
    lambda_starr: float,
    lambda_es: float,
) -> dict[str, Any]:
    """Additional advisory score combining final_value with tail-risk deltas.

    This is reported alongside, and never substitutes for, the existing
    final_value/Sharpe/MDD gate in compare_candidates -- consistent with this
    repo's promotion discipline (a new score must be observed, not wired into
    a live decision, until it has been OOS-validated; see e.g. w6_credit and
    --use-calibration-model, which shipped with the same default-neutral
    posture). lambda_starr/lambda_es default to 0.0 so promotion_utility is a
    no-op until someone deliberately calibrates non-zero weights.
    """
    components_used: list[str] = ["final_value_delta"]
    utility = final_value_delta

    starr_delta = None
    if candidate_tail["starr_95"] is not None and baseline_tail["starr_95"] is not None:
        starr_delta = candidate_tail["starr_95"] - baseline_tail["starr_95"]
        if lambda_starr:
            utility += lambda_starr * starr_delta
            components_used.append("starr_delta")

    es_delta = None
    if candidate_tail["expected_shortfall_95"] is not None and baseline_tail["expected_shortfall_95"] is not None:
        es_delta = candidate_tail["expected_shortfall_95"] - baseline_tail["expected_shortfall_95"]
        if lambda_es:
            utility -= lambda_es * max(0.0, es_delta)
            components_used.append("expected_shortfall_delta")

    transaction_cost_delta = None
    if candidate_tail["transaction_cost"] is not None and baseline_tail["transaction_cost"] is not None:
        transaction_cost_delta = candidate_tail["transaction_cost"] - baseline_tail["transaction_cost"]
        utility -= transaction_cost_delta
        components_used.append("transaction_cost_delta")

    return {
        "promotion_utility": utility,
        "promotion_utility_starr_delta": starr_delta,
        "promotion_utility_expected_shortfall_delta": es_delta,
        "promotion_utility_transaction_cost_delta": transaction_cost_delta,
        "promotion_utility_components_used": components_used,
        "promotion_utility_equals_final_value_delta": components_used == ["final_value_delta"],
    }


def _constraint_summary(*, final_floor_pass: bool, mdd_non_worse_pass: bool, sharpe_non_worse_pass: bool) -> str:
    failures: list[str] = []
    if not final_floor_pass:
        failures.append("final_value_floor")
    if not mdd_non_worse_pass:
        failures.append("max_drawdown_non_worse")
    if not sharpe_non_worse_pass:
        failures.append("sharpe_non_worse")
    return "pass" if not failures else "fail:" + ",".join(failures)


def compare_candidates(
    baseline_path: Path,
    candidate_paths: list[Path],
    *,
    tail_risk_lambda_starr: float = 0.0,
    tail_risk_lambda_es: float = 0.0,
) -> dict[str, Any]:
    baseline_report = _load_json(baseline_path)
    baseline_metrics = _metrics_from_report(baseline_report)
    baseline_tail = _tail_risk_metrics(baseline_metrics)
    rows = []
    for path in candidate_paths:
        try:
            report = _load_json(path)
        except Exception as exc:
            rows.append({"path": str(path), "load_error": str(exc)})
            continue
        experiment = report.get("experiment", path.stem)
        for row in _candidate_rows(report):
            metrics = row.get("metrics", row)
            if "final_value" not in metrics:
                continue
            effective_override = _effective_override(row)
            final_value = float(metrics.get("final_value", 0.0))
            sharpe = float(metrics.get("sharpe_ratio", 0.0))
            mdd = float(metrics.get("max_drawdown", -1.0))
            formal_eligible = bool(row.get("formal_eligible", True))
            baseline_final = float(baseline_metrics["final_value"])
            baseline_sharpe = float(baseline_metrics["sharpe_ratio"])
            baseline_mdd = float(baseline_metrics["max_drawdown"])
            final_floor = baseline_final * 0.98
            final_floor_pass = final_value >= final_floor
            mdd_non_worse_pass = mdd >= baseline_mdd
            sharpe_non_worse_pass = sharpe >= baseline_sharpe
            formal_upgrade = (
                formal_eligible
                and final_value >= baseline_final
                and sharpe_non_worse_pass
                and mdd_non_worse_pass
                and effective_override > 0
            )
            watchlist = (
                final_floor_pass
                and sharpe_non_worse_pass
                and mdd_non_worse_pass
                and effective_override > 0
            )
            candidate_tail = _tail_risk_metrics(metrics)
            promotion_utility = _promotion_utility(
                final_value_delta=final_value - baseline_final,
                baseline_tail=baseline_tail,
                candidate_tail=candidate_tail,
                lambda_starr=tail_risk_lambda_starr,
                lambda_es=tail_risk_lambda_es,
            )
            rows.append(
                {
                    "path": str(path),
                    "experiment": experiment,
                    "variant": row.get("variant") or row.get("name") or "candidate",
                    "final_value": final_value,
                    "sharpe_ratio": sharpe,
                    "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
                    "max_drawdown": mdd,
                    "trigger_days": int(row.get("trigger_days", row.get("event_count", 0)) or 0),
                    "override_days": effective_override,
                    "defense_days": int(row.get("defense_days", 0) or 0),
                    "delta_final": final_value - baseline_final,
                    "delta_sharpe": sharpe - baseline_sharpe,
                    "delta_mdd": mdd - baseline_mdd,
                    "final_value_floor": final_floor,
                    "final_value_floor_pass": final_floor_pass,
                    "max_drawdown_non_worse_pass": mdd_non_worse_pass,
                    "sharpe_non_worse_pass": sharpe_non_worse_pass,
                    "promotion_objective_status": _constraint_summary(
                        final_floor_pass=final_floor_pass,
                        mdd_non_worse_pass=mdd_non_worse_pass,
                        sharpe_non_worse_pass=sharpe_non_worse_pass,
                    ),
                    "formal_eligible": formal_eligible,
                    "formal_ineligible_reason": row.get("formal_ineligible_reason"),
                    "formal_upgrade_pass": formal_upgrade,
                    "research_watchlist_pass": watchlist,
                    "tail_risk_metrics": candidate_tail,
                    **promotion_utility,
                }
            )
    unique_rows = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (
            row.get("path"),
            row.get("experiment"),
            row.get("variant"),
            row.get("final_value"),
            row.get("sharpe_ratio"),
            row.get("max_drawdown"),
            row.get("trigger_days"),
            row.get("override_days"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    rows = unique_rows
    ranked = sorted(
        rows,
        key=lambda item: (
            item.get("formal_upgrade_pass", False),
            item.get("research_watchlist_pass", False),
            item.get("final_value_floor_pass", False),
            item.get("max_drawdown_non_worse_pass", False),
            item.get("final_value", 0),
            item.get("max_drawdown", -1),
            item.get("sharpe_ratio", -99),
            item.get("override_days", 0),
        ),
        reverse=True,
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_path": str(baseline_path),
        "baseline_metrics": baseline_metrics,
        "baseline_tail_risk_metrics": baseline_tail,
        "tail_risk_lambda_starr": tail_risk_lambda_starr,
        "tail_risk_lambda_es": tail_risk_lambda_es,
        "candidate_file_count": len(candidate_paths),
        "candidate_row_count": len(rows),
        "formal_upgrade_pass_count": sum(1 for row in rows if row.get("formal_upgrade_pass")),
        "research_watchlist_pass_count": sum(1 for row in rows if row.get("research_watchlist_pass")),
        "top_candidates": ranked[:25],
        "rows": rows,
    }


def _expand_patterns(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(Path(pattern))
    return sorted(set(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--output", default="results/group_a_plus_compare_20260619.json")
    parser.add_argument(
        "--tail-risk-lambda-starr",
        type=float,
        default=0.0,
        help="Weight on STARR-ratio delta in promotion_utility. Default 0.0 (no-op, advisory-only until calibrated).",
    )
    parser.add_argument(
        "--tail-risk-lambda-es",
        type=float,
        default=0.0,
        help="Weight on Expected Shortfall (95%%) delta in promotion_utility. Default 0.0 (no-op, advisory-only until calibrated).",
    )
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.governance.compare")
    try:
        report = compare_candidates(
            Path(args.baseline),
            _expand_patterns(args.candidates),
            tail_risk_lambda_starr=args.tail_risk_lambda_starr,
            tail_risk_lambda_es=args.tail_risk_lambda_es,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Compare: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
