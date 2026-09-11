#!/usr/bin/env python3
"""Review whether golden2_0830 is ready to enter the production promotion gate."""

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

from group_a_plus.governance.compare import _candidate_rows, _metrics_from_report, compare_candidates  # noqa: E402


DEFAULT_BASELINE = PROJECT_ROOT / "results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json"
DEFAULT_PROMOTION_GATE = PROJECT_ROOT / "results/group_a_plus_promotion_gate_20260831.json"
# 2026-09-01: was "results/group_a_plus_multi_window_gate_20260706.json", a stale
# gate file unrelated to golden2 (predates the golden2_0830 release by weeks, so
# its "decision" could never reflect golden2's own multi-window evidence). Now
# points at the gate computed specifically from the golden2 same-window candidate
# backtests below (see DEFAULT_GOLDEN2_SAME_WINDOW_DIR).
DEFAULT_MULTI_WINDOW_GATE = PROJECT_ROOT / "report/group_a_plus/latest/golden2_multi_window_gate.json"
DEFAULT_GOLDEN2_RELEASE = PROJECT_ROOT / "results/group_a_plus_release_golden2_0830.json"
DEFAULT_GOLDEN2_BACKTEST = PROJECT_ROOT / "results/golden2_0830/last_ppo_group_a_backtest_golden2_0830.json"
DEFAULT_LATEST_2024_2026 = PROJECT_ROOT / "results/group_a_plus_latest_backtest_2024_2026_after_20260813_refresh.json"
DEFAULT_LATEST_2025_2026 = PROJECT_ROOT / "results/group_a_plus_latest_backtest_2025_2026_after_20260813_refresh.json"
# 2026-09-01: per-window golden2-vs-latest candidate reports written by
# scripts/evaluate/build_group_a_plus_golden2_same_window_candidate_backtests.py.
# Unlike the three legacy paths above (which have never had extractable
# `rows`/`metrics` in the shape compare_candidates()/_candidate_rows() expect --
# see "Next Required Work" this review used to print), each file here already has
# the exact `baseline.metrics` + `rows[{name, metrics}]` shape, so they are
# genuinely promotion_candidate_compatible.
DEFAULT_GOLDEN2_SAME_WINDOW_DIR = PROJECT_ROOT / "report/group_a_plus/latest/golden2_same_window_candidate_backtests"
DEFAULT_PANEL_DRIFT = PROJECT_ROOT / "results/ncf_panel_drift_active_vs_20260831.json"
DEFAULT_DFL_AUDIT = PROJECT_ROOT / "results/a2118_dfl_active_date_audit_20260831.json"
DEFAULT_CVAR_FORWARD = PROJECT_ROOT / "report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json"
DEFAULT_DAILY_STATUS = PROJECT_ROOT / "results/group_a_plus_daily_status_final_20260831.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/golden2_promotion_candidate_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/golden2_promotion_candidate_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/golden2_promotion_candidate_review/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _window(report: dict[str, Any]) -> dict[str, Any]:
    value = report.get("window")
    return value if isinstance(value, dict) else {}


def _metrics(report: dict[str, Any]) -> dict[str, Any]:
    try:
        metrics = _metrics_from_report(report)
    except Exception:
        return {}
    return metrics if isinstance(metrics, dict) else {}


def _compatibility(path: Path) -> dict[str, Any]:
    report = _load(path)
    rows: list[dict[str, Any]] = []
    try:
        rows = _candidate_rows(report)
    except Exception:
        rows = []
    metrics = _metrics(report)
    window = _window(report)
    return {
        "path": str(path),
        "exists": path.exists(),
        "experiment": report.get("experiment") or report.get("report_type") or path.stem,
        "window": window,
        "metrics_available": bool(metrics),
        "candidate_row_count": len(rows),
        "promotion_candidate_compatible": bool(rows),
        "reason": "candidate rows available" if rows else "no candidate rows for compare_candidates",
        "metrics": {
            "final_value": metrics.get("final_value"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
        },
    }


def _drift_summary(panel_drift: dict[str, Any]) -> dict[str, Any]:
    columns = panel_drift.get("column_summary") if isinstance(panel_drift.get("column_summary"), dict) else {}
    h20 = columns.get("h20_prob_up") if isinstance(columns.get("h20_prob_up"), dict) else {}
    confidence = columns.get("confidence") if isinstance(columns.get("confidence"), dict) else {}
    return {
        "status": "fail" if float(h20.get("max_abs_delta", 0.0) or 0.0) > 0.15 else "pass",
        "h20_prob_up_max_abs_delta": h20.get("max_abs_delta"),
        "h20_prob_up_max_abs_delta_date": h20.get("max_abs_delta_date"),
        "confidence_max_abs_delta": confidence.get("max_abs_delta"),
        "confidence_max_abs_delta_date": confidence.get("max_abs_delta_date"),
    }


_BLOCKER_NEXT_STEPS = {
    "no_golden2_promotion_compatible_candidate_rows": (
        "build same-window golden2/latest backtest candidate rows (see golden2_same_window_dir) "
        "so compare_candidates() has rows/metrics to compare"
    ),
    "promotion_metrics_gate_failed": "resolve the promotion_gate metrics_gate failure before reconsidering golden2",
    "panel_drift_gate_failed": "resolve the promotion_gate panel_drift_gate failure before reconsidering golden2",
    "multi_window_gate_failed": "resolve the promotion_gate multi_window_gate failure before reconsidering golden2",
    "no_multi_window_candidate_available": (
        "golden2 does not pass the multi-window stability gate (see golden2_multi_window_gate.json); "
        "it must reach multi_window_pass on all evaluated windows before this blocker clears"
    ),
    "dfl_latest_audit_not_promotion_ready": "resolve the DFL active-date audit before reconsidering golden2",
    "dynamic_cvar_forward_validation_blocks_live_weight_change": (
        "resolve the 2608.20179 dynamic-CVaR forward validation block before reconsidering golden2"
    ),
}


def _next_required_work(blockers: list[str], compatible_paths: list[Path]) -> list[str]:
    if not blockers:
        return ["none -- all gates pass; still requires manual promotion approval before any live weight change"]
    steps = [_BLOCKER_NEXT_STEPS[b] for b in blockers if b in _BLOCKER_NEXT_STEPS]
    if compatible_paths and "no_golden2_promotion_compatible_candidate_rows" not in blockers:
        steps.insert(0, f"candidate rows are available ({len(compatible_paths)} compatible files); remaining work is the blockers below")
    return steps


def build_review(
    *,
    baseline_path: Path = DEFAULT_BASELINE,
    promotion_gate_path: Path = DEFAULT_PROMOTION_GATE,
    multi_window_gate_path: Path = DEFAULT_MULTI_WINDOW_GATE,
    golden2_release_path: Path = DEFAULT_GOLDEN2_RELEASE,
    golden2_backtest_path: Path = DEFAULT_GOLDEN2_BACKTEST,
    latest_2024_2026_path: Path = DEFAULT_LATEST_2024_2026,
    latest_2025_2026_path: Path = DEFAULT_LATEST_2025_2026,
    golden2_same_window_dir: Path | None = None,
    panel_drift_path: Path = DEFAULT_PANEL_DRIFT,
    dfl_audit_path: Path = DEFAULT_DFL_AUDIT,
    cvar_forward_path: Path = DEFAULT_CVAR_FORWARD,
    daily_status_path: Path = DEFAULT_DAILY_STATUS,
) -> dict[str, Any]:
    baseline = _load(baseline_path)
    promotion_gate = _load(promotion_gate_path)
    multi_window_gate = _load(multi_window_gate_path)
    golden2_release = _load(golden2_release_path)
    panel_drift = _load(panel_drift_path)
    dfl_audit = _load(dfl_audit_path)
    cvar_forward = _load(cvar_forward_path)
    daily_status = _load(daily_status_path)

    candidate_paths = [golden2_backtest_path, latest_2024_2026_path, latest_2025_2026_path]
    if golden2_same_window_dir is not None and golden2_same_window_dir.is_dir():
        candidate_paths.extend(sorted(golden2_same_window_dir.glob("*.json")))
    compatibility = [_compatibility(path) for path in candidate_paths]
    compatible_paths = [Path(item["path"]) for item in compatibility if item["promotion_candidate_compatible"]]
    comparison = compare_candidates(baseline_path, compatible_paths) if compatible_paths else {}

    release_state = golden2_release.get("source_state") if isinstance(golden2_release.get("source_state"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if not compatible_paths:
        blockers.append("no_golden2_promotion_compatible_candidate_rows")
    if str(release_state.get("actual_data_date") or "") != "2026-08-31":
        warnings.append("golden2_release_is_frozen_before_latest_20260831_data")
    if promotion_gate.get("metrics_gate", {}).get("status") != "pass":
        blockers.append("promotion_metrics_gate_failed")
    if promotion_gate.get("panel_drift_gate", {}).get("status") != "pass":
        blockers.append("panel_drift_gate_failed")
    if promotion_gate.get("multi_window_gate", {}).get("status") != "pass":
        blockers.append("multi_window_gate_failed")
    if multi_window_gate.get("decision") != "candidate_available":
        blockers.append("no_multi_window_candidate_available")
    if dfl_audit.get("summary", {}).get("all_checks_pass") is not True:
        blockers.append("dfl_latest_audit_not_promotion_ready")
    if cvar_forward.get("decision", {}).get("target_weight_change_allowed") is not True:
        blockers.append("dynamic_cvar_forward_validation_blocks_live_weight_change")

    ready = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_golden2_promotion_candidate_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "promotion_candidate_ready" if ready else "blocked_prepare_multi_window_backtest",
        "policy": "diagnostic_only_no_strategy_change_no_weight_change_no_orders",
        "baseline": {
            "path": str(baseline_path),
            "window": _window(baseline),
            "metrics": _compatibility(baseline_path)["metrics"],
        },
        "golden2_release": {
            "path": str(golden2_release_path),
            "release_date": golden2_release.get("release_date"),
            "status": golden2_release.get("status"),
            "source_actual_data_date": release_state.get("actual_data_date"),
            "latest_live_actual_data_date": "2026-08-31",
        },
        "candidate_compatibility": compatibility,
        "compatible_candidate_count": len(compatible_paths),
        "comparison": {
            "candidate_row_count": comparison.get("candidate_row_count", 0),
            "formal_upgrade_pass_count": comparison.get("formal_upgrade_pass_count", 0),
            "research_watchlist_pass_count": comparison.get("research_watchlist_pass_count", 0),
            "top_candidates": comparison.get("top_candidates", [])[:5],
        },
        "current_gates": {
            "daily_status": daily_status.get("overall_status"),
            "promotion_gate_decision": promotion_gate.get("decision"),
            "promotion_blocking_gates": promotion_gate.get("blocking_gates") or [],
            "panel_drift": _drift_summary(panel_drift),
            "multi_window_decision": multi_window_gate.get("decision"),
            "dfl_all_checks_pass": dfl_audit.get("summary", {}).get("all_checks_pass"),
            "dfl_conclusion": dfl_audit.get("conclusion"),
            "dynamic_cvar_forward_status": cvar_forward.get("status"),
            "dynamic_cvar_forward_passed": cvar_forward.get("decision", {}).get("forward_validation_passed"),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        # 2026-09-01: was a static 3-item checklist ("build same-window
        # candidate rows" / "rerun multi-window gate" / "only rerun promotion
        # gate after both exist") describing a data-availability gap that has
        # since been closed -- golden2_same_window_dir now supplies real
        # compatible candidate rows and a golden2-specific multi-window gate
        # result every time this review runs. That checklist no longer
        # described the actual remaining blockers, so it is now generated
        # from the real per-blocker reasons instead of being hardcoded.
        "next_required_work": _next_required_work(blockers, compatible_paths),
        "decision": {
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "creates_orders": False,
        },
        "inputs": {
            "baseline": str(baseline_path),
            "promotion_gate": str(promotion_gate_path),
            "multi_window_gate": str(multi_window_gate_path),
            "golden2_release": str(golden2_release_path),
            "panel_drift": str(panel_drift_path),
            "dfl_audit": str(dfl_audit_path),
            "cvar_forward": str(cvar_forward_path),
            "daily_status": str(daily_status_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Golden2 Promotion Candidate Review",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Policy: `{report.get('policy')}`",
        f"- Compatible candidates: `{report.get('compatible_candidate_count')}`",
        f"- Daily status: `{report['current_gates'].get('daily_status')}`",
        f"- Promotion gate: `{report['current_gates'].get('promotion_gate_decision')}`",
        f"- Multi-window decision: `{report['current_gates'].get('multi_window_decision')}`",
        f"- CVaR forward passed: `{report['current_gates'].get('dynamic_cvar_forward_passed')}`",
        "",
        "## Candidate Compatibility",
        "",
        "| file | window | metrics | candidate rows | compatible | reason |",
        "|---|---|---:|---:|---|---|",
    ]
    for item in report.get("candidate_compatibility") or []:
        window = item.get("window") or {}
        label = f"{window.get('start', '?')}..{window.get('end', '?')}" if window else "-"
        lines.append(
            f"| `{Path(item['path']).name}` | `{label}` | `{item.get('metrics_available')}` | "
            f"`{item.get('candidate_row_count')}` | `{item.get('promotion_candidate_compatible')}` | "
            f"{item.get('reason')} |"
        )
    lines.extend(["", "## Blockers", ""])
    blockers = report.get("blocking_reasons") or []
    if not blockers:
        lines.append("- None")
    else:
        lines.extend(f"- `{item}`" for item in blockers)
    lines.extend(["", "## Next Required Work", ""])
    lines.extend(f"- {item}" for item in report.get("next_required_work") or [])
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path) -> Path:
    return history_dir / "golden2_promotion_candidate_review_20260831.json"


def write_outputs(report: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--promotion-gate", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--multi-window-gate", default=str(DEFAULT_MULTI_WINDOW_GATE))
    parser.add_argument("--golden2-release", default=str(DEFAULT_GOLDEN2_RELEASE))
    parser.add_argument("--golden2-backtest", default=str(DEFAULT_GOLDEN2_BACKTEST))
    parser.add_argument("--latest-2024-2026", default=str(DEFAULT_LATEST_2024_2026))
    parser.add_argument("--latest-2025-2026", default=str(DEFAULT_LATEST_2025_2026))
    parser.add_argument("--golden2-same-window-dir", default=str(DEFAULT_GOLDEN2_SAME_WINDOW_DIR))
    parser.add_argument("--panel-drift", default=str(DEFAULT_PANEL_DRIFT))
    parser.add_argument("--dfl-audit", default=str(DEFAULT_DFL_AUDIT))
    parser.add_argument("--cvar-forward", default=str(DEFAULT_CVAR_FORWARD))
    parser.add_argument("--daily-status", default=str(DEFAULT_DAILY_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_review(
        baseline_path=_resolve(args.baseline),
        promotion_gate_path=_resolve(args.promotion_gate),
        multi_window_gate_path=_resolve(args.multi_window_gate),
        golden2_release_path=_resolve(args.golden2_release),
        golden2_backtest_path=_resolve(args.golden2_backtest),
        latest_2024_2026_path=_resolve(args.latest_2024_2026),
        latest_2025_2026_path=_resolve(args.latest_2025_2026),
        golden2_same_window_dir=_resolve(args.golden2_same_window_dir),
        panel_drift_path=_resolve(args.panel_drift),
        dfl_audit_path=_resolve(args.dfl_audit),
        cvar_forward_path=_resolve(args.cvar_forward),
        daily_status_path=_resolve(args.daily_status),
    )
    write_outputs(
        report,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"Golden2 promotion candidate review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "compatible_candidate_count": report["compatible_candidate_count"],
                "blocking_reasons": report["blocking_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
