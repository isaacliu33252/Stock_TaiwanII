#!/usr/bin/env python3
"""Summarize 2609.04917 turnover bridge cap variants."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_cap_sweep_summary.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_cap_sweep_summary.md"
DEFAULT_INPUTS = [
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap20.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap30.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap40.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap45.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap465.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow_cap47.json",
    PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow.json",
]


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _target(data: dict[str, Any], ticker: str) -> int | None:
    raw = data.get("bridge_target_shares") or data.get("target_shares") or {}
    if not isinstance(raw, dict) or ticker not in raw:
        return None
    return int(raw[ticker])


def _row(path: Path) -> dict[str, Any]:
    data = _load(path)
    computed = data.get("computed") if isinstance(data.get("computed"), dict) else {}
    trades = data.get("bridge_trades") if isinstance(data.get("bridge_trades"), list) else []
    return {
        "path": str(path),
        "status": data.get("status") or "missing",
        "cap": (data.get("limits") or {}).get("max_turnover"),
        "turnover": computed.get("bridge_turnover"),
        "turnover_reduction": computed.get("turnover_reduction"),
        "target_00679b": _target(data, "00679B.TWO"),
        "target_00713": _target(data, "00713.TW"),
        "target_00631l": _target(data, "00631L.TW"),
        "trade_count": len(trades),
        "trade_summary": [
            {
                "ticker": row.get("ticker"),
                "side": row.get("side"),
                "target_shares": row.get("target_shares"),
                "delta_shares": row.get("delta_shares"),
                "notional": row.get("notional"),
            }
            for row in trades
            if isinstance(row, dict)
        ],
    }


def build_report(paths: list[Path]) -> dict[str, Any]:
    rows = sorted((_row(path) for path in paths), key=lambda row: float(row.get("cap") or 999))
    feasible = [
        row
        for row in rows
        if row["status"] == "shadow_bridge_available_for_manual_review"
        and row.get("target_00631l") == 0
        and row.get("turnover") is not None
        and float(row["turnover"]) <= 0.50
    ]
    clean_exit = [row for row in feasible if row.get("target_00679b") == 0 and (row.get("target_00713") or 0) == 0]
    recommended = clean_exit[0] if clean_exit else (feasible[-1] if feasible else None)
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_turnover_bridge_cap_sweep_summary",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_cap_sweep_summary_no_order_no_weight_change",
        "status": "available" if recommended else "blocked",
        "rows": rows,
        "recommended_cap": None if recommended is None else recommended.get("cap"),
        "recommended_path": None if recommended is None else recommended.get("path"),
        "decision": {
            "live_execution_allowed": False,
            "manual_review_candidate": None if recommended is None else recommended.get("path"),
            "summary": (
                "Prefer the lowest cap that fully exits 00679B without adding 00631L or 00713."
                if recommended
                else "No feasible turnover bridge cap was found."
            ),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Turnover Bridge Cap Sweep",
        "",
        f"- status: {report['status']}",
        f"- recommended_cap: {report['recommended_cap']}",
        f"- live_execution_allowed: {report['decision']['live_execution_allowed']}",
        "",
        "| cap | turnover | target 00679B | target 00713 | target 00631L | trade count |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['cap']} | {row['turnover']} | {row['target_00679b']} | "
            f"{row['target_00713']} | {row['target_00631l']} | {row['trade_count']} |"
        )
    lines.extend(["", "## Decision", "", report["decision"]["summary"], ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="*", default=[str(path) for path in DEFAULT_INPUTS])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report([_resolve(path) for path in args.inputs])
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"], "recommended_cap": report["recommended_cap"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
