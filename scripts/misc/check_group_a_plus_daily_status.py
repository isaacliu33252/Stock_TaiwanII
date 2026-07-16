#!/usr/bin/env python3
"""Daily status check for the active GroupA+ baseline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus_report_manager import GroupAPlusReportManager


def _load(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return json.loads(candidate.read_text(encoding="utf-8"))


def _load_optional(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _unwrap_standard_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _latest_compounding_regime_path() -> Path | None:
    matches = sorted(
        (PROJECT_ROOT / "results").glob("00631l_leveraged_compounding_regime_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _load_compounding_regime(path: str | Path | None) -> dict[str, Any]:
    candidate: Path | None
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
    else:
        candidate = _latest_compounding_regime_path()
    if candidate is None or not candidate.exists():
        return {"status": "unavailable", "reason": "compounding_regime_report_missing"}
    payload = _load(candidate)
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
    regime = latest.get("compounding_regime")
    return {
        "status": "ok" if regime else "unavailable",
        "source_path": str(candidate),
        "report_type": payload.get("report_type"),
        "generated_at": payload.get("generated_at"),
        "date": latest.get("date"),
        "compounding_regime": regime,
        "recommended_policy": latest.get("recommended_policy"),
        "trend_score": latest.get("trend_score"),
        "mean_reversion_score": latest.get("mean_reversion_score"),
        "features": {
            "rolling_AR1_5d": latest.get("rolling_AR1_5d"),
            "rolling_AR1_20d": latest.get("rolling_AR1_20d"),
            "variance_ratio": latest.get("variance_ratio"),
            "trend_persistence": latest.get("trend_persistence"),
            "reversal_speed": latest.get("reversal_speed"),
            "positive_return_streak": latest.get("positive_return_streak"),
            "negative_return_streak": latest.get("negative_return_streak"),
            "drawdown_recovery_ratio": latest.get("drawdown_recovery_ratio"),
            "00631L_vs_0050_relative_momentum": latest.get("00631L_vs_0050_relative_momentum"),
        },
        "regime_policy": payload.get("regime_policy"),
        "active_allocation_impact": payload.get("active_allocation_impact", "none"),
    }


def _dfl_frozen_input_staleness(dfl_advisory: dict[str, Any] | None, check_date: str) -> dict[str, Any]:
    """Fable audit (2026-07-16, combination opportunities #2): dfl_advisory
    only ever matches decisions whose date equals today's live-signal date
    against a fixed backtest file (see build_a2118_dfl_advisory.py) that is
    never re-run. Once the file's own live-window coverage falls behind
    check_date, matched_decision_count is structurally guaranteed to be 0
    forever -- the advisory step keeps "running" but can never again report
    a non-KEEP action. This surfaces that gap instead of letting it look
    like ordinary sparse-output KEEP behavior.
    """
    if not dfl_advisory or dfl_advisory.get("status") != "available":
        return {"status": "not_applicable", "detail": "dfl_advisory unavailable"}
    input_path_raw = dfl_advisory.get("input")
    if not input_path_raw:
        return {"status": "not_applicable", "detail": "dfl_advisory has no input path"}
    input_path = Path(input_path_raw)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not input_path.exists():
        return {"status": "unavailable", "detail": f"frozen input missing: {input_path}"}
    try:
        source = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "detail": f"failed to read frozen input: {exc}"}

    live_dates: list[str] = []
    for window in source.get("results") or []:
        if not isinstance(window, dict) or window.get("bucket") == "out_of_sample":
            continue
        for row in window.get("recent_decisions") or []:
            if isinstance(row, dict) and row.get("date"):
                live_dates.append(str(row["date"]))

    if not live_dates:
        return {"status": "unavailable", "detail": "frozen input has no tuning-window decisions"}

    max_live_date = max(live_dates)
    calendar_gap = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(max_live_date).normalize()).days)
    return {
        "status": "ok",
        "frozen_input_path": str(input_path),
        "frozen_input_generated_at": source.get("generated_at"),
        "max_live_window_decision_date": max_live_date,
        "calendar_gap_days": calendar_gap,
    }


def _business_days_between(start: str, end: str) -> int:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts <= start_ts:
        return 0
    return int(len(pd.bdate_range(start_ts + pd.Timedelta(days=1), end_ts)))


def _status(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "block"
    if warn:
        return "warn"
    return "ok"


def _markdown_text(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA+ Daily Status",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Check date: `{report['check_date']}`",
        f"Overall: `{report['overall_status']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['name']} | `{check['status']}` | {check['detail']} |")
    lines.extend(
        [
            "",
            "## Signal",
            "",
            f"- Group A status: `{report['signal']['signal_status']}`",
            f"- Reason: `{report['signal']['signal_reason']}`",
            f"- Actual data date: `{report['signal']['actual_data_date']}`",
            f"- Business stale days: `{report['signal']['business_stale_days']}`",
            f"- Calendar stale days: `{report['signal']['calendar_stale_days']}`",
            "",
            "## GroupA+",
            "",
            f"- Profile: `{report['profile']}`",
            f"- Overlay regime: `{report['group_a_plus']['overlay_regime']}`",
            f"- 00679B target weight: `{report['group_a_plus']['overlay_00679b_weight']:.2%}`",
            f"- Cash after cost: `{report['group_a_plus']['cash_after_cost']:,.0f}`",
        ]
    )
    pre_trade_guard = report["group_a_plus"].get("pre_trade_guard") or {}
    compounding_guard = report["group_a_plus"].get("compounding_regime_pre_trade_guard") or {}
    dfl_advisory = report["group_a_plus"].get("dfl_advisory") or {}
    dfl_shadow_ensemble = report["group_a_plus"].get("dfl_shadow_ensemble") or {}
    dfl_active_date_audit = report["group_a_plus"].get("dfl_active_date_audit") or {}
    if pre_trade_guard:
        lines.extend(
            [
                "",
                "## Pre-Trade Guard",
                "",
                f"- Status: `{pre_trade_guard.get('status')}`",
                f"- 00631L add: `{'allowed' if pre_trade_guard.get('allow_00631l_add') else 'blocked'}`",
                f"- Policy: `{pre_trade_guard.get('policy')}`",
            ]
        )
        for blocked in pre_trade_guard.get("blocked_trades", []) or []:
            if not isinstance(blocked, dict):
                continue
            lines.append(
                "- Blocked: `{ticker}` `{side}` current `{current}` requested `{requested}` guarded `{guarded}`".format(
                    ticker=blocked.get("ticker"),
                    side=blocked.get("side"),
                    current=blocked.get("current_shares"),
                    requested=blocked.get("requested_target_shares"),
                    guarded=blocked.get("guarded_target_shares"),
                )
            )
    if dfl_shadow_ensemble and dfl_shadow_ensemble.get("status") == "available":
        lines.extend(
            [
                "",
                "## A21.18 DFL Shadow Ensemble",
                "",
                f"- Level: `{dfl_shadow_ensemble.get('ensemble_level')}`",
                f"- Manual review: `{dfl_shadow_ensemble.get('manual_review_required')}`",
                f"- Policy: `{dfl_shadow_ensemble.get('policy')}`",
            ]
        )
        signals = dfl_shadow_ensemble.get("signals") or {}
        for name in ("base", "p50", "p70"):
            signal = signals.get(name) if isinstance(signals.get(name), dict) else {}
            if signal:
                lines.append(
                    "- `{name}` action `{action}` active `{active}` reliability `{reliability}`".format(
                        name=name,
                        action=signal.get("action"),
                        active=signal.get("active"),
                        reliability=signal.get("reliability_error_percentile"),
                    )
                )
    if compounding_guard:
        lines.extend(
            [
                "",
                "## 00631L Compounding Guard",
                "",
                f"- Status: `{compounding_guard.get('status')}`",
                f"- 00631L add: `{'allowed' if compounding_guard.get('allow_00631l_add') else 'blocked'}`",
                f"- Regime: `{compounding_guard.get('compounding_regime')}`",
                f"- Policy: `{compounding_guard.get('recommended_policy')}`",
            ]
        )
    compounding = report["group_a_plus"].get("compounding_regime_diagnostic") or {}
    if compounding and compounding.get("status") == "ok":
        features = compounding.get("features") or {}
        lines.extend(
            [
                "",
                "## 00631L Compounding Regime",
                "",
                f"- Regime: `{compounding.get('compounding_regime')}`",
                f"- Policy: `{compounding.get('recommended_policy')}`",
                f"- Trend score: `{compounding.get('trend_score')}`",
                f"- Mean-reversion score: `{compounding.get('mean_reversion_score')}`",
                f"- AR1 5d / 20d: `{features.get('rolling_AR1_5d')}` / `{features.get('rolling_AR1_20d')}`",
                f"- Variance ratio: `{features.get('variance_ratio')}`",
                f"- 00631L vs 0050 relative momentum: `{features.get('00631L_vs_0050_relative_momentum')}`",
            ]
        )
    if dfl_advisory and dfl_advisory.get("status") == "available":
        lines.extend(
            [
                "",
                "## A21.18 DFL Advisory",
                "",
                f"- Action: `{dfl_advisory.get('action')}`",
                f"- Active: `{dfl_advisory.get('advisory_active')}`",
                f"- Policy: `{dfl_advisory.get('policy')}`",
            ]
        )
        selected = dfl_advisory.get("selected_decision") or {}
        if selected:
            lines.append(f"- Predicted regret: `{selected.get('predicted_regret')}`")
        selective_variants = dfl_advisory.get("selective_variants") or {}
        if selective_variants:
            lines.extend(["", "### Selective Variants", ""])
            for name, variant in sorted(selective_variants.items()):
                if not isinstance(variant, dict):
                    continue
                selected_variant = variant.get("selected_decision") or {}
                lines.append(
                    "- `{name}` action `{action}` active `{active}` reliability `{reliability}`".format(
                        name=name,
                        action=variant.get("action"),
                        active=variant.get("advisory_active"),
                        reliability=selected_variant.get("reliability_error_percentile"),
                    )
                )
    if dfl_active_date_audit and dfl_active_date_audit.get("status") == "research_only":
        summary = dfl_active_date_audit.get("summary") or {}
        lines.extend(
            [
                "",
                "## A21.18 DFL Active-Date Audit",
                "",
                f"- Conclusion: `{dfl_active_date_audit.get('conclusion')}`",
                f"- Active days: `{summary.get('active_days')}`",
                f"- Hard checks pass: `{summary.get('all_checks_pass')}`",
                f"- Warning days: `{summary.get('warning_days')}`",
                f"- Existing guard overlap days: `{summary.get('existing_guard_overlap_days')}`",
                f"- Total estimated cost bps / 1M: `{summary.get('total_estimated_cost_bps')}`",
                "- Policy: `shadow_only_no_auto_weight_change`",
            ]
        )
    return "\n".join(lines) + "\n"


def _write_markdown(path: Path, report: dict[str, Any]) -> str:
    text = _markdown_text(report)
    path.write_text(text, encoding="utf-8")
    return text


def _live_status_report(args: argparse.Namespace) -> dict[str, Any]:
    live_signal = _load(args.live_signal)
    data = live_signal.get("data") if isinstance(live_signal.get("data"), dict) else live_signal
    execution_plan = _unwrap_standard_payload(_load_optional(getattr(args, "execution_plan", None)))
    check_date = str(args.check_date)
    actual_data_date = str(data.get("actual_data_date") or data.get("requested_as_of_date") or check_date)
    business_stale = _business_days_between(actual_data_date, check_date)
    calendar_stale = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(actual_data_date).normalize()).days)

    execution_allowed = bool(data.get("execution_allowed"))
    guard_reasons = list(data.get("execution_guard_reasons") or [])
    warning_reasons = list(data.get("execution_warning_reasons") or [])
    target_shares = data.get("reference_target_shares_before_cost") or {}
    cash_after_cost = float(data.get("estimated_cash_after_rounding_before_cost", 0.0) or 0.0)
    target_weights = dict(data.get("target_weights") or {})
    overlay_00679b_weight = float(target_weights.get("00679B.TWO", 0.0) or 0.0)
    execution_regime = str(data.get("execution_regime") or data.get("base_regime") or "unknown")
    strategy_status = str(data.get("strategy_status") or "unknown")
    execution_plan_path = Path(getattr(args, "execution_plan", ""))
    execution_plan_exists = False
    if str(execution_plan_path):
        execution_plan_exists = execution_plan_path.is_absolute() and execution_plan_path.exists()
        execution_plan_exists = execution_plan_exists or (PROJECT_ROOT / execution_plan_path).exists()
    execution_plan_aligned = False
    pre_trade_guard: dict[str, Any] = {}
    pre_trade_guards: list[dict[str, Any]] = []
    compounding_regime_pre_trade_guard: dict[str, Any] = {}
    if execution_plan:
        execution_plan_aligned = (
            str(execution_plan.get("actual_data_date") or "") == actual_data_date
            and str(execution_plan.get("strategy_id") or "") == str(data.get("strategy_id") or "")
        )
        if execution_plan_aligned and isinstance(execution_plan.get("pre_trade_guard"), dict):
            pre_trade_guard = dict(execution_plan["pre_trade_guard"])
        if execution_plan_aligned and isinstance(execution_plan.get("compounding_regime_pre_trade_guard"), dict):
            compounding_regime_pre_trade_guard = dict(execution_plan["compounding_regime_pre_trade_guard"])
        if execution_plan_aligned and isinstance(execution_plan.get("pre_trade_guards"), list):
            pre_trade_guards = [
                dict(guard) for guard in execution_plan["pre_trade_guards"] if isinstance(guard, dict)
            ]
    compounding_regime = _load_compounding_regime(getattr(args, "compounding_regime", None))
    dfl_advisory = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_advisory", None)))
    dfl_shadow_ensemble = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_shadow_ensemble", None)))
    dfl_active_date_audit = _unwrap_standard_payload(_load_optional(getattr(args, "dfl_active_date_audit", None)))
    dfl_frozen_input_staleness = _dfl_frozen_input_staleness(dfl_advisory, check_date)
    max_dfl_frozen_staleness_days = int(getattr(args, "max_dfl_frozen_staleness_days", 14))

    optional_sources = ((data.get("data_freshness") or {}).get("optional_sources") or {})
    hard_source_blocks = [
        name for name, source in optional_sources.items()
        if source.get("severity") == "hard" and source.get("status") not in {"ok", "warn"}
    ]
    soft_source_warnings = [
        name for name, source in optional_sources.items()
        if source.get("severity") != "hard" and source.get("status") not in {"ok", None}
    ]

    checks = [
        {
            "name": "live_signal_success",
            "status": _status(bool(live_signal.get("success", True))),
            "detail": "live signal loaded" if live_signal.get("success", True) else str(live_signal.get("error")),
        },
        {
            "name": "execution_allowed",
            "status": _status(execution_allowed),
            "detail": "allowed" if execution_allowed else "; ".join(guard_reasons) or "blocked",
        },
        {
            "name": "data_freshness",
            "status": _status(
                business_stale <= int(args.max_business_stale_days),
                warn=calendar_stale > business_stale,
            ),
            "detail": f"{business_stale} business days stale, {calendar_stale} calendar days stale",
        },
        {
            "name": "strategy_status",
            "status": _status(strategy_status == "active", warn=strategy_status not in {"active", "unknown"}),
            "detail": f"strategy_status={strategy_status}, strategy_id={data.get('strategy_id')}",
        },
        {
            "name": "source_freshness",
            "status": _status(not hard_source_blocks, warn=bool(warning_reasons or soft_source_warnings)),
            "detail": (
                "all required sources ok"
                if not hard_source_blocks and not warning_reasons and not soft_source_warnings
                else "; ".join(guard_reasons + warning_reasons + hard_source_blocks + soft_source_warnings)
            ),
        },
        {
            "name": "cash_constraint",
            "status": _status(cash_after_cost >= 0),
            "detail": f"estimated_cash_after_rounding_before_cost={cash_after_cost:,.0f}",
        },
        {
            "name": "execution_plan_pre_trade_guard",
            "status": _status(
                True,
                warn=bool(execution_plan_exists and execution_plan and not execution_plan_aligned),
            ),
            "detail": (
                "pre_trade_guards="
                + ",".join(
                    str(guard.get("status"))
                    for guard in pre_trade_guards
                    if guard.get("status") not in {None, "inactive", "unavailable"}
                )
                if pre_trade_guards
                else "execution plan unavailable"
                if not execution_plan_exists
                else "execution plan has no aligned pre_trade_guard"
            ),
        },
        {
            "name": "dfl_advisory_frozen_input_staleness",
            # research-only/advisory input, so this never blocks the run --
            # it only warns when the frozen backtest has gone stale.
            "status": _status(
                True,
                warn=dfl_frozen_input_staleness.get("status") == "ok"
                and int(dfl_frozen_input_staleness.get("calendar_gap_days", 0)) > max_dfl_frozen_staleness_days,
            ),
            "detail": (
                f"frozen backtest last covers {dfl_frozen_input_staleness.get('max_live_window_decision_date')} "
                f"({dfl_frozen_input_staleness.get('calendar_gap_days')} calendar days behind check_date); "
                "matched_decision_count is structurally 0 until this is re-run"
                if dfl_frozen_input_staleness.get("status") == "ok"
                else dfl_frozen_input_staleness.get("detail", "dfl_advisory not in use")
            ),
        },
    ]
    overall = "block" if any(item["status"] == "block" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "ok"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "overall_status": overall,
        "profile": str(data.get("strategy_id") or "group_a_plus_live"),
        "mode": "live_signal",
        "source_paths": {
            "live_signal": str(Path(args.live_signal)),
            "execution_plan": str(Path(getattr(args, "execution_plan", ""))),
            "compounding_regime": compounding_regime.get("source_path"),
            "dfl_advisory": str(Path(getattr(args, "dfl_advisory", ""))),
            "dfl_shadow_ensemble": str(Path(getattr(args, "dfl_shadow_ensemble", ""))),
            "dfl_active_date_audit": str(Path(getattr(args, "dfl_active_date_audit", ""))),
        },
        "checks": checks,
        "signal": {
            "signal_status": str(data.get("action") or ""),
            "signal_reason": str(data.get("regime_reason") or ""),
            "actual_data_date": actual_data_date,
            "requested_as_of_date": data.get("requested_as_of_date"),
            "business_stale_days": business_stale,
            "calendar_stale_days": calendar_stale,
        },
        "group_a_plus": {
            "overlay_regime": execution_regime,
            "overlay_00679b_weight": overlay_00679b_weight,
            "cash_after_cost": cash_after_cost,
            "target_shares": target_shares,
            "pre_trade_guard": pre_trade_guard,
            "pre_trade_guards": pre_trade_guards,
            "compounding_regime_pre_trade_guard": compounding_regime_pre_trade_guard,
            "compounding_regime_diagnostic": compounding_regime,
            "dfl_advisory": dfl_advisory or {},
            "dfl_shadow_ensemble": dfl_shadow_ensemble or {},
            "dfl_active_date_audit": dfl_active_date_audit or {},
            "dfl_frozen_input_staleness": dfl_frozen_input_staleness,
        },
    }


def _baseline_status_report(args: argparse.Namespace) -> dict[str, Any]:
    baseline = _load(args.baseline)
    signal_path = baseline["latest_group_a_signal"]
    plus_signal_path = baseline["latest_group_a_plus_final_signal"]
    clean_payload_path = baseline["clean_payload"]
    stress_path = baseline["stress_test_result"]
    strict_cost_path = baseline["strict_cost_result"]

    signal = _load(signal_path)
    plus_signal = _load(plus_signal_path)
    actual_data_date = str(signal.get("actual_data_date"))
    check_date = str(args.check_date)
    calendar_stale = int((pd.Timestamp(check_date).normalize() - pd.Timestamp(actual_data_date).normalize()).days)
    business_stale = _business_days_between(actual_data_date, check_date)

    signal_status = str(signal.get("signal_status"))
    signal_reason = str(signal.get("signal_reason"))
    guard_reasons = list(signal.get("guard_reasons") or [])
    cash_after_cost = float((plus_signal.get("execution_summary") or {}).get("cash_after_cost", 0.0))
    overlay_regime = str((plus_signal.get("overlay_policy") or {}).get("regime"))
    overlay_00679b_weight = float(plus_signal.get("overlay_00679b_weight", 0.0))

    required_paths = [signal_path, plus_signal_path, clean_payload_path, stress_path, strict_cost_path]
    missing = [path for path in required_paths if not (PROJECT_ROOT / path).exists()]

    checks = [
        {
            "name": "required_files",
            "status": _status(not missing),
            "detail": "all required files present" if not missing else f"missing: {missing}",
        },
        {
            "name": "data_freshness",
            "status": _status(business_stale <= int(args.max_business_stale_days), warn=calendar_stale > business_stale),
            "detail": f"{business_stale} business days stale, {calendar_stale} calendar days stale",
        },
        {
            "name": "signal_guard",
            "status": _status(signal_status != "guard_blocked"),
            "detail": signal_reason if not guard_reasons else "; ".join(guard_reasons),
        },
        {
            "name": "group_a_plus_cash_constraint",
            "status": _status(cash_after_cost >= 0),
            "detail": f"cash_after_cost={cash_after_cost:,.0f}",
        },
        {
            "name": "overlay_regime",
            "status": _status(overlay_regime in {"risk_on", "caution", "risk_off", "severe"}),
            "detail": f"regime={overlay_regime}, 00679B_weight={overlay_00679b_weight:.2%}",
        },
    ]
    overall = "block" if any(item["status"] == "block" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "ok"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "overall_status": overall,
        "profile": baseline["profile"],
        "baseline": str(Path(args.baseline)),
        "mode": "baseline",
        "source_paths": {
            "latest_group_a_signal": signal_path,
            "latest_group_a_plus_final_signal": plus_signal_path,
            "clean_payload": clean_payload_path,
            "stress_test_result": stress_path,
            "strict_cost_result": strict_cost_path,
        },
        "checks": checks,
        "signal": {
            "signal_status": signal_status,
            "signal_reason": signal_reason,
            "actual_data_date": actual_data_date,
            "requested_as_of_date": signal.get("requested_as_of_date"),
            "business_stale_days": business_stale,
            "calendar_stale_days": calendar_stale,
        },
        "group_a_plus": {
            "overlay_regime": overlay_regime,
            "overlay_00679b_weight": overlay_00679b_weight,
            "cash_after_cost": cash_after_cost,
            "target_shares": plus_signal.get("target_shares"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "baseline"], default="live")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--live-signal", default="report/group_a_plus/latest/live_signal.json")
    parser.add_argument("--execution-plan", default="report/group_a_plus/latest/execution_plan.json")
    parser.add_argument(
        "--compounding-regime",
        default=None,
        help="Optional 00631L leveraged compounding regime JSON. Defaults to latest matching result; missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-advisory",
        default="report/group_a_plus/latest/a2118_dfl_advisory.json",
        help="Optional A21.18 decision-focused advisory JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-active-date-audit",
        default="results/a2118_dfl_active_date_audit_latest.json",
        help="Optional A21.18 DFL active-date audit JSON. Missing file is non-blocking.",
    )
    parser.add_argument(
        "--dfl-shadow-ensemble",
        default="report/group_a_plus/latest/a2118_dfl_shadow_ensemble.json",
        help="Optional A21.18 DFL shadow ensemble JSON. Missing file is non-blocking.",
    )
    parser.add_argument("--check-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument(
        "--max-dfl-frozen-staleness-days",
        type=int,
        default=14,
        help=(
            "Warn when the DFL advisory's frozen backtest file's live-window "
            "decisions fall this many calendar days behind check-date (it is "
            "never re-run automatically, so matched_decision_count becomes "
            "structurally 0 once this gap opens up)."
        ),
    )
    parser.add_argument("--output-prefix", default="results/group_a_plus_daily_status")
    parser.add_argument("--report-dir", default="report/group_a_plus")
    parser.add_argument("--skip-managed-report", action="store_true")
    args = parser.parse_args()

    report = _live_status_report(args) if args.mode == "live" else _baseline_status_report(args)

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = PROJECT_ROOT / prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _write_markdown(md_path, report)
    managed_paths: dict[str, str] | None = None
    if not args.skip_managed_report:
        manager = GroupAPlusReportManager(args.report_dir)
        managed_paths = manager.save_daily_status(
            report,
            markdown=markdown,
            metadata={
                "legacy_json_path": str(json_path.relative_to(PROJECT_ROOT)),
                "legacy_markdown_path": str(md_path.relative_to(PROJECT_ROOT)),
                "baseline_path": str(Path(args.baseline)),
            },
        )
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    if managed_paths:
        print(f"Managed HTML: {managed_paths['html']}")
        print(f"Managed JSON: {managed_paths['json']}")
        print(f"Managed MD:   {managed_paths['markdown']}")
        print(f"Managed meta: {managed_paths['metadata']}")
        print(f"Latest ptr:   {managed_paths['latest']}")
    print(f"Overall: {report['overall_status']}")
    for check in report["checks"]:
        print(f"{check['name']}: {check['status']} - {check['detail']}")


if __name__ == "__main__":
    main()
