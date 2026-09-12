#!/usr/bin/env python3
"""Build a freshness retry report for the 2606.09104 micro-add promotion gate."""

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

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_HOLDINGS_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/holdings_authoritative_snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_promotion_gate_freshness_retry.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_promotion_gate_freshness_retry/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _live_actual_date(live_signal: dict[str, Any]) -> str:
    data = live_signal.get("data") if isinstance(live_signal.get("data"), dict) else live_signal
    actual = data.get("actual_data_date") or data.get("requested_as_of_date")
    if not actual:
        raise ValueError("live signal missing actual_data_date/requested_as_of_date")
    return str(actual)


def build_retry_report(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    holdings_snapshot_path: Path = DEFAULT_HOLDINGS_SNAPSHOT,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_signal = _load_json(_resolve(live_signal_path))
    holdings = _load_json(_resolve(holdings_snapshot_path))
    if not live_signal:
        blockers.append("live_signal_missing")
        required_as_of = None
    else:
        try:
            required_as_of = _live_actual_date(live_signal)
        except Exception:
            required_as_of = None
            blockers.append("live_signal_actual_date_missing")
    holdings_as_of = str(holdings.get("as_of") or "") if holdings else None
    if not holdings:
        blockers.append("holdings_snapshot_missing")
    elif holdings_as_of != required_as_of:
        blockers.append("holdings_snapshot_not_same_day")

    promotion_gate = {}
    if not blockers:
        from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate import build_gate

        promotion_gate = build_gate()
    if promotion_gate and promotion_gate.get("status") != "manual_review_candidate_ready":
        warnings.extend([f"promotion_gate_{reason}" for reason in promotion_gate.get("blocking_reasons", [])])
    ready = bool(not blockers and promotion_gate.get("status") == "manual_review_candidate_ready")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_promotion_gate_freshness_retry",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "freshness_retry_only_no_live_weight_change",
        "status": "ready_for_manual_promotion_review" if ready else "blocked",
        "as_of": required_as_of or holdings_as_of or str(datetime.now().date()),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "promotion_gate_data_freshness_retry",
            "not_imported": ["auto_rebalance", "unconstrained_BLED_optimizer", "short_selling"],
        },
        "freshness_check": {
            "required_as_of": required_as_of,
            "holdings_snapshot_as_of": holdings_as_of,
            "same_day_holdings_available": bool(holdings and holdings_as_of == required_as_of),
            "holdings_source_file": holdings.get("source_file") if holdings else None,
        },
        "promotion_gate_snapshot": {
            "status": promotion_gate.get("status"),
            "blocking_reasons": promotion_gate.get("blocking_reasons", []),
            "candidate": promotion_gate.get("candidate"),
            "decision": promotion_gate.get("decision"),
        }
        if promotion_gate
        else {},
        "decision": {
            "ready_for_manual_promotion_review": ready,
            "rerun_promotion_gate_after_same_day_holdings_import": not ready,
            "allow_00631l_micro_add": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "Promotion review remains blocked until same-day authoritative holdings are available and the promotion gate itself is ready.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_retry_report(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_promotion_gate_freshness_retry_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--holdings-snapshot", default=str(DEFAULT_HOLDINGS_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_retry_report(
        live_signal_path=_resolve(args.live_signal),
        holdings_snapshot_path=_resolve(args.holdings_snapshot),
    )
    write_retry_report(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
