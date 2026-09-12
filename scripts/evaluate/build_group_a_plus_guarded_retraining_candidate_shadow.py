#!/usr/bin/env python3
"""Build a guarded retraining-candidate shadow report for GroupA+.

The input is a research-only GroupA+ overlay backtest report. This wrapper
does not recalculate weights and does not alter latest strategy artifacts. It
adds the 00632R / inverse ETF governance gate before a backtest candidate can
be treated as a retraining or promotion candidate.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKTEST = PROJECT_ROOT / "results/group_a_plus_overlay_backtest_20250102_20260605.json"
DEFAULT_INVERSE_GATE = PROJECT_ROOT / "report/group_a_plus/latest/inverse_etf_manual_review_gate.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/guarded_retraining_candidate_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/guarded_retraining_candidate_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/guarded_retraining_candidate_shadow/history"
INVERSE_TICKER = "00632R.TW"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _uses_inverse(detail: dict[str, Any], *, threshold: float) -> dict[str, Any]:
    events = list(detail.get("events") or [])
    touched_dates: list[str] = []
    max_target = 0.0
    max_executable = 0.0
    inverse_control_enabled = False
    for event in events:
        if not isinstance(event, dict):
            continue
        target = dict(event.get("target_weights_before_execution") or {})
        executable = dict(event.get("executable_weights") or {})
        target_weight = abs(float(target.get(INVERSE_TICKER, 0.0) or 0.0))
        executable_weight = abs(float(executable.get(INVERSE_TICKER, 0.0) or 0.0))
        target_report = event.get("target_report") if isinstance(event.get("target_report"), dict) else {}
        inverse_control = (
            target_report.get("inverse_control") if isinstance(target_report.get("inverse_control"), dict) else {}
        )
        inverse_control_enabled = inverse_control_enabled or bool(inverse_control.get("enabled"))
        max_target = max(max_target, target_weight)
        max_executable = max(max_executable, executable_weight)
        if target_weight > threshold or executable_weight > threshold or inverse_control.get("enabled"):
            touched_dates.append(str(event.get("date")))
    return {
        "uses_inverse_etf": bool(touched_dates),
        "inverse_ticker": INVERSE_TICKER,
        "touch_count": len(touched_dates),
        "first_touch_date": touched_dates[0] if touched_dates else None,
        "last_touch_date": touched_dates[-1] if touched_dates else None,
        "max_target_weight": max_target,
        "max_executable_weight": max_executable,
        "inverse_control_enabled": inverse_control_enabled,
    }


def build_report(
    *,
    backtest_path: Path,
    inverse_gate_path: Path,
    as_of: str,
    inverse_threshold: float = 1e-12,
) -> dict[str, Any]:
    backtest = _load(backtest_path)
    inverse_gate = _load(inverse_gate_path) if inverse_gate_path.exists() else {}
    promotion_gate = (backtest.get("summary") or {}).get("promotion_gate") or {}
    base_decision = str(promotion_gate.get("decision") or "unknown")
    candidate_rows = list(promotion_gate.get("variants") or [])
    detail_by_variant = dict(backtest.get("plus_details") or {})

    rows: list[dict[str, Any]] = []
    inverse_blocked: list[str] = []
    for row in candidate_rows:
        variant = str(row.get("variant") or "")
        detail = detail_by_variant.get(variant, {})
        inverse = _uses_inverse(detail if isinstance(detail, dict) else {}, threshold=float(inverse_threshold))
        retrain_candidate = bool(row.get("retrain_candidate"))
        promotion_candidate = bool(row.get("return_upgrade_candidate"))
        governance_blocked = bool(inverse["uses_inverse_etf"])
        if governance_blocked:
            inverse_blocked.append(variant)
        rows.append(
            {
                "variant": variant,
                "base_retrain_candidate": retrain_candidate,
                "base_promotion_candidate": promotion_candidate,
                "final_drag_pct": row.get("final_drag_pct"),
                "sharpe_delta": row.get("sharpe_delta"),
                "mdd_improvement": row.get("mdd_improvement"),
                "volatility_reduction": row.get("volatility_reduction"),
                "inverse_etf": inverse,
                "guarded_retraining_allowed": retrain_candidate and not governance_blocked,
                "guarded_promotion_allowed": promotion_candidate and not governance_blocked,
                "governance_blocking_reasons": ["inverse_etf_00632r_manual_review_required"]
                if governance_blocked
                else [],
            }
        )

    guarded_retrain = [row["variant"] for row in rows if row["guarded_retraining_allowed"]]
    guarded_promote = [row["variant"] for row in rows if row["guarded_promotion_allowed"]]
    blockers: list[str] = []
    if inverse_blocked:
        blockers.append("inverse_etf_candidates_blocked_before_retraining_review")
    if inverse_gate.get("status") == "blocked" and (inverse_gate.get("guard") or {}).get("status") == "blocked":
        blockers.append("latest_inverse_etf_gate_blocked")

    if guarded_promote:
        decision = "guarded_promotion_candidate"
    elif guarded_retrain:
        decision = "guarded_retrain_candidate"
    elif base_decision in {"promotion_candidate", "retrain_candidate"} and inverse_blocked:
        decision = "blocked_by_inverse_etf_governance"
    else:
        decision = f"guarded_{base_decision}"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_guarded_retraining_candidate_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers and not (guarded_promote or guarded_retrain) else "shadow_review",
        "policy": "research_only_no_latest_replacement",
        "backtest": str(backtest_path),
        "inverse_gate": str(inverse_gate_path),
        "base_promotion_gate": {
            "decision": base_decision,
            "rationale": promotion_gate.get("rationale"),
            "best_return_variant": promotion_gate.get("best_return_variant"),
            "best_risk_variant": promotion_gate.get("best_risk_variant"),
        },
        "guarded_decision": {
            "decision": decision,
            "guarded_retrain_candidates": guarded_retrain,
            "guarded_promotion_candidates": guarded_promote,
            "inverse_blocked_candidates": inverse_blocked,
            "blocking_reasons": blockers,
            "replace_latest": False,
            "tune_latest": False,
            "requires_manual_review_before_latest_change": True,
        },
        "candidates": rows,
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    decision = report["guarded_decision"]
    base = report["base_promotion_gate"]
    lines = [
        "# GroupA+ Guarded Retraining Candidate Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Backtest: `{report['backtest']}`",
        f"- Inverse gate: `{report['inverse_gate']}`",
        "",
        "## Base Gate",
        "",
        f"- Decision: `{base['decision']}`",
        f"- Rationale: `{base['rationale']}`",
        f"- Best return variant: `{base['best_return_variant']}`",
        f"- Best risk variant: `{base['best_risk_variant']}`",
        "",
        "## Guarded Decision",
        "",
        f"- Decision: `{decision['decision']}`",
        f"- Guarded retrain candidates: `{decision['guarded_retrain_candidates']}`",
        f"- Guarded promotion candidates: `{decision['guarded_promotion_candidates']}`",
        f"- Inverse-blocked candidates: `{decision['inverse_blocked_candidates']}`",
        f"- Blocking reasons: `{decision['blocking_reasons']}`",
        f"- Replace latest: `{decision['replace_latest']}`",
        f"- Tune latest: `{decision['tune_latest']}`",
        "",
        "## Notes",
        "",
        "- Research-only shadow review.",
        "- No latest strategy, live signal, execution plan, or order file was changed.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(report["as_of"]).replace("-", "")
        (history_dir / f"guarded_retraining_candidate_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest", default=str(DEFAULT_BACKTEST))
    parser.add_argument("--inverse-gate", default=str(DEFAULT_INVERSE_GATE))
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--inverse-threshold", type=float, default=1e-12)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        backtest_path=_resolve(args.backtest),
        inverse_gate_path=_resolve(args.inverse_gate),
        as_of=str(args.as_of),
        inverse_threshold=float(args.inverse_threshold),
    )
    write_report(
        report,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "guarded_decision": report["guarded_decision"]["decision"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
