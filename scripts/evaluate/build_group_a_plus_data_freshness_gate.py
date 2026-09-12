#!/usr/bin/env python3
"""Build a stricter data/artifact freshness gate for GroupA++."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
RESULTS_DIR = PROJECT_ROOT / "results"
DEFAULT_LIVE_SIGNAL = LATEST_DIR / "live_signal.json"
DEFAULT_EXPLAIN_SNAPSHOT = LATEST_DIR / "group_a_plusplus_latest_strategy_explain_snapshot.json"
DEFAULT_OHLCV_FRESHNESS = RESULTS_DIR / "ohlcv_freshness_latest.json"
DEFAULT_OUTPUT = LATEST_DIR / "data_freshness_gate.json"
DEFAULT_OUTPUT_MD = LATEST_DIR / "data_freshness_gate.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return None


def build_gate(
    *,
    live_signal_path: Path,
    explain_snapshot_path: Path,
    ohlcv_freshness_path: Path,
    as_of: str | None,
    max_business_stale_days: int = 3,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_signal = _load(live_signal_path)
    explain = _load(explain_snapshot_path)
    ohlcv = _load(ohlcv_freshness_path)

    if not live_signal:
        blockers.append("missing_live_signal")
    if not explain:
        warnings.append("missing_latest_strategy_explain_snapshot")
    if not ohlcv:
        warnings.append("missing_ohlcv_freshness_report")

    requested_as_of = _date(as_of)
    live_requested = _date(live_signal.get("requested_as_of_date"))
    live_actual = _date(live_signal.get("actual_data_date") or live_signal.get("signal_asof") or live_signal.get("as_of"))
    if live_signal and not live_actual:
        blockers.append("live_signal_actual_data_date_missing")
    if requested_as_of and live_requested and live_requested != requested_as_of:
        warnings.append("live_signal_requested_as_of_mismatch")

    business_stale = live_signal.get("business_stale_days")
    if isinstance(business_stale, (int, float)) and business_stale > max_business_stale_days:
        blockers.append("live_signal_business_stale_days_exceeds_limit")
    if live_signal.get("execution_guard_reasons"):
        warnings.append("live_signal_has_execution_guard_reasons")

    ohlcv_status = ohlcv.get("overall_status")
    if ohlcv_status == "error":
        blockers.append("ohlcv_freshness_report_error")
    elif ohlcv_status == "warning":
        warnings.append("ohlcv_freshness_report_warning")
    ohlcv_target = _date(ohlcv.get("target_date"))
    if requested_as_of and ohlcv_target and ohlcv_target != requested_as_of:
        warnings.append("ohlcv_freshness_target_date_mismatch")
    if live_actual and ohlcv_target and live_actual < ohlcv_target:
        warnings.append("live_signal_actual_date_lags_ohlcv_freshness_target")

    explain_identity = explain.get("strategy_identity") if isinstance(explain.get("strategy_identity"), dict) else {}
    explain_window = explain_identity.get("date_window") if isinstance(explain_identity.get("date_window"), dict) else {}
    explain_end = _date(explain_window.get("end"))
    if live_actual and explain_end and explain_end < live_actual:
        blockers.append("latest_strategy_explain_target_weight_window_lags_live_signal")
    if explain.get("warning_reasons"):
        warnings.append("latest_strategy_explain_snapshot_has_warnings")

    status = "blocked" if blockers else ("warning" if warnings else "passed")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_data_freshness_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "freshness_gate_only_no_weight_change_no_orders",
        "status": status,
        "inputs": {
            "live_signal": {"path": _rel(live_signal_path), "exists": live_signal_path.exists()},
            "latest_strategy_explain_snapshot": {
                "path": _rel(explain_snapshot_path),
                "exists": explain_snapshot_path.exists(),
            },
            "ohlcv_freshness": {"path": _rel(ohlcv_freshness_path), "exists": ohlcv_freshness_path.exists()},
        },
        "summary": {
            "requested_as_of": requested_as_of,
            "live_signal_requested_as_of": live_requested,
            "live_signal_actual_data_date": live_actual,
            "live_signal_business_stale_days": business_stale,
            "max_business_stale_days": max_business_stale_days,
            "ohlcv_freshness_status": ohlcv_status,
            "ohlcv_target_date": ohlcv_target,
            "latest_strategy_target_weight_window_end": explain_end,
            "latest_strategy_explain_status": explain.get("status"),
        },
        "decision": {
            "data_fresh_enough_for_unqualified_execution": not blockers,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "creates_orders": False,
        },
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# GroupA++ Data Freshness Gate",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Live signal actual data date: `{summary.get('live_signal_actual_data_date')}`",
        f"- Live signal business stale days: `{summary.get('live_signal_business_stale_days')}`",
        f"- OHLCV freshness status: `{summary.get('ohlcv_freshness_status')}`",
        f"- OHLCV target date: `{summary.get('ohlcv_target_date')}`",
        f"- Latest strategy target-weight window end: `{summary.get('latest_strategy_target_weight_window_end')}`",
        "",
        "## Decision",
        "",
        f"- Data fresh enough for unqualified execution: `{report['decision']['data_fresh_enough_for_unqualified_execution']}`",
        "- Creates orders: `False`",
        "- Changes latest/golden: `False`",
        "- Promotion allowed: `False`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- `{item}`" for item in report.get("blockers") or []] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{item}`" for item in report.get("warnings") or []] or ["- None"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--latest-strategy-explain-snapshot", default=str(DEFAULT_EXPLAIN_SNAPSHOT))
    parser.add_argument("--ohlcv-freshness", default=str(DEFAULT_OHLCV_FRESHNESS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    report = build_gate(
        live_signal_path=_resolve(args.live_signal),
        explain_snapshot_path=_resolve(args.latest_strategy_explain_snapshot),
        ohlcv_freshness_path=_resolve(args.ohlcv_freshness),
        as_of=args.as_of,
        max_business_stale_days=args.max_business_stale_days,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
