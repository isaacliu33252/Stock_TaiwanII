#!/usr/bin/env python3
"""Build promotion-readiness review for EXTREME-only 00631L 4% shadow candidate."""

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

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_extreme_only_forward_shadow import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_EXTREME_SHADOW,
)
from scripts.evaluate.build_group_a_plus_2606_09104_promotion_gate_freshness_retry import (  # noqa: E402
    DEFAULT_HOLDINGS_SNAPSHOT,
    DEFAULT_LIVE_SIGNAL,
    _live_actual_date,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_extreme_only_promotion_readiness.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_extreme_only_promotion_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_readiness(
    *,
    extreme_shadow_path: Path = DEFAULT_EXTREME_SHADOW,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    holdings_snapshot_path: Path = DEFAULT_HOLDINGS_SNAPSHOT,
    min_extreme_events: int = 50,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    shadow = _load_json(_resolve(extreme_shadow_path))
    live_signal = _load_json(_resolve(live_signal_path))
    holdings = _load_json(_resolve(holdings_snapshot_path))
    if not shadow:
        blockers.append("extreme_only_shadow_missing")
    latest_state = shadow.get("latest_state") if isinstance(shadow.get("latest_state"), dict) else {}
    active_summary = shadow.get("extreme_only_active_event_summary") if isinstance(shadow.get("extreme_only_active_event_summary"), dict) else {}
    historical_value = bool(shadow.get("decision", {}).get("extreme_only_has_historical_value"))
    if not historical_value:
        blockers.append("extreme_only_historical_value_missing")
    if int(active_summary.get("event_count") or 0) < min_extreme_events:
        blockers.append("insufficient_extreme_events")
    if latest_state.get("risk_aversion_state") != "EXTREME":
        blockers.append("latest_state_not_extreme")
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
    ready = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "promotion_readiness_only_no_live_weight_change",
        "status": "ready_for_manual_promotion_review" if ready else "blocked",
        "as_of": str(shadow.get("as_of") or required_as_of or holdings_as_of or datetime.now().date()),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "extreme_only_micro_add_promotion_readiness",
            "not_imported": ["live_weight_change", "auto_rebalance", "unconstrained_BLED_optimizer"],
        },
        "candidate": {
            "candidate_id": "extreme_only_0050_30_00631l_4_cash_66",
            "activation_rule": "latest risk_aversion_state must be EXTREME",
            "target_weights_when_active": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
            "guarded_weights_when_inactive": {"0050.TW": 0.3, "cash": 0.7},
        },
        "historical_shadow_review": {
            "extreme_only_has_historical_value": historical_value,
            "active_event_summary": active_summary,
        },
        "freshness_check": {
            "required_as_of": required_as_of,
            "holdings_snapshot_as_of": holdings_as_of,
            "same_day_holdings_available": bool(holdings and holdings_as_of == required_as_of),
        },
        "latest_state": latest_state,
        "decision": {
            "ready_for_manual_promotion_review": ready,
            "requires_signed_manual_approval": ready,
            "allow_00631l_micro_add": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "EXTREME-only candidate can only become manual-review ready when latest state is EXTREME and same-day holdings are available.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_readiness(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_extreme_only_promotion_readiness_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extreme-shadow", default=str(DEFAULT_EXTREME_SHADOW))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--holdings-snapshot", default=str(DEFAULT_HOLDINGS_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_readiness(
        extreme_shadow_path=_resolve(args.extreme_shadow),
        live_signal_path=_resolve(args.live_signal),
        holdings_snapshot_path=_resolve(args.holdings_snapshot),
    )
    write_readiness(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
