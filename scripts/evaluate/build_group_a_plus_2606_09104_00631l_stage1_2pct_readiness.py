#!/usr/bin/env python3
"""Build stage-1 00631L 2% readiness for the 2606.09104 micro-add path.

Stage 1 only raises 00631L to 2% from current holdings and funds the difference
from cash. It does not force 0050 to 30%, so it is a turnover-light staging
review rather than the full 4% target.
"""

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

from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_cap_sweep import build_sweep  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_promotion_gate import (  # noqa: E402
    DEFAULT_LIVE_SNAPSHOT,
    _current_weights,
    _turnover_review,
    _weights,
)
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_extreme_only_promotion_readiness import (  # noqa: E402
    DEFAULT_HOLDINGS_SNAPSHOT,
    DEFAULT_LIVE_SIGNAL,
    _live_actual_date,
)
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_4pct_regime_split import DEFAULT_OUTPUT as DEFAULT_REGIME_SPLIT  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_stage1_2pct_readiness.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_stage1_2pct_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _stage_target(current: dict[str, float], *, stage_cap: float) -> tuple[dict[str, float], list[str]]:
    blockers: list[str] = []
    target = dict(current)
    current_00631l = float(current.get("00631L.TW", 0.0) or 0.0)
    cash = float(current.get("cash", 0.0) or 0.0)
    if current_00631l >= stage_cap:
        blockers.append("current_00631l_already_at_or_above_stage_cap")
        target["00631L.TW"] = current_00631l
        return _weights(target), blockers
    delta = stage_cap - current_00631l
    if cash < delta:
        blockers.append("insufficient_cash_for_stage_delta")
    target["00631L.TW"] = stage_cap
    target["cash"] = cash - delta
    return _weights(target), blockers


def build_readiness(
    *,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    holdings_snapshot_path: Path = DEFAULT_HOLDINGS_SNAPSHOT,
    regime_split_path: Path = DEFAULT_REGIME_SPLIT,
    stage_cap: float = 0.02,
    max_turnover: float = 0.05,
    max_cost_bps: float = 0.5,
    linear_cost_bps: float = 5.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    live_signal = _load_json(_resolve(live_signal_path))
    holdings = _load_json(_resolve(holdings_snapshot_path))
    regime_split = _load_json(_resolve(regime_split_path))
    if not live_snapshot:
        blockers.append("live_snapshot_missing")
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

    current, reliable, source_status = _current_weights(live_snapshot)
    if not reliable:
        blockers.append("current_weights_missing_or_stale")
    target, target_blockers = _stage_target(current, stage_cap=stage_cap)
    blockers.extend(target_blockers)
    turnover = _turnover_review(current, target, linear_cost_bps=linear_cost_bps)
    if reliable and (turnover.get("turnover_l1_half") or 999.0) > max_turnover:
        blockers.append("stage_turnover_exceeds_limit")
    if reliable and (turnover.get("estimated_linear_cost_bps_of_assets") or 999.0) > max_cost_bps:
        blockers.append("stage_cost_bps_exceeds_limit")

    split_latest = regime_split.get("latest_state") if isinstance(regime_split.get("latest_state"), dict) else {}
    latest_state = split_latest.get("risk_aversion_state")
    if latest_state != "EXTREME":
        blockers.append("latest_state_not_extreme")
    cap_review = build_sweep(caps=(stage_cap,))
    stage_review = cap_review.get("cap_reviews", [{}])[0] if cap_review.get("cap_reviews") else {}
    if stage_review and stage_review.get("passes_high_extreme_gate") is not True:
        warnings.append("stage_cap_does_not_pass_high_extreme_gate")
    ready = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_stage1_2pct_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "stage1_readiness_shadow_only_no_live_weight_change",
        "status": "ready_for_manual_review" if ready else "blocked",
        "as_of": required_as_of or holdings_as_of or live_snapshot.get("as_of") or datetime.now().date().isoformat(),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "turnover_limited_staged_micro_add",
            "not_imported": ["live_weight_change", "auto_rebalance", "unconstrained_BLED_optimizer"],
        },
        "stage": {
            "stage_id": "stage1_00631l_to_2pct",
            "stage_cap_00631l": stage_cap,
            "activation_rule": "latest risk_aversion_state must be EXTREME",
            "current_weights": current,
            "current_weights_reliable": reliable,
            "current_weight_source_status": source_status,
            "target_weights": target,
            "turnover_review": turnover,
        },
        "freshness_check": {
            "required_as_of": required_as_of,
            "holdings_snapshot_as_of": holdings_as_of,
            "same_day_holdings_available": bool(holdings and holdings_as_of == required_as_of),
        },
        "latest_state": split_latest,
        "stage_cap_shadow_review": stage_review,
        "decision": {
            "stage_ready_for_manual_review": ready,
            "stage_turnover_ok": turnover.get("execution_cost_state") == "LOW_COST",
            "stage_cap_has_shadow_value": stage_review.get("passes_high_extreme_gate") is True,
            "allow_stage1_00631l_add": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "Stage 1 tests a turnover-light move to 2pct 00631L; it cannot authorize live exposure.",
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
    (history_dir / f"2606_09104_00631l_stage1_2pct_readiness_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--holdings-snapshot", default=str(DEFAULT_HOLDINGS_SNAPSHOT))
    parser.add_argument("--regime-split", default=str(DEFAULT_REGIME_SPLIT))
    parser.add_argument("--stage-cap", type=float, default=0.02)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_readiness(
        live_snapshot_path=_resolve(args.live_snapshot),
        live_signal_path=_resolve(args.live_signal),
        holdings_snapshot_path=_resolve(args.holdings_snapshot),
        regime_split_path=_resolve(args.regime_split),
        stage_cap=args.stage_cap,
    )
    write_readiness(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
