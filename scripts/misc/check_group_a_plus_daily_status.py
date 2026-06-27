#!/usr/bin/env python3
"""Daily status check for the active GroupA+ baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from group_a_plus_report_manager import GroupAPlusReportManager


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"


def _load(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return json.loads(candidate.read_text(encoding="utf-8"))


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
    return "\n".join(lines) + "\n"


def _write_markdown(path: Path, report: dict[str, Any]) -> str:
    text = _markdown_text(report)
    path.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--check-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--output-prefix", default="results/group_a_plus_daily_check_20260613")
    parser.add_argument("--report-dir", default="report/group_a_plus")
    parser.add_argument("--skip-managed-report", action="store_true")
    args = parser.parse_args()

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
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "check_date": check_date,
        "overall_status": overall,
        "profile": baseline["profile"],
        "baseline": str(Path(args.baseline)),
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
    print(f"Overall: {overall}")
    for check in checks:
        print(f"{check['name']}: {check['status']} - {check['detail']}")


if __name__ == "__main__":
    main()
