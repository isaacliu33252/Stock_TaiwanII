#!/usr/bin/env python3
"""Build a small-position A21.20 00631L re-entry shadow advisory.

This is advisory-only. It does not alter live target weights, signal pointers,
execution plans, or production strategy manifests.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_A2120 = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2120_letf_compounding_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2120_small_00631l_reentry_shadow.json"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"
SIGNAL_GLOB = "results/group_a_plus_live_signal_v2_*.json"
PRODUCTION_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _latest_signal_path(pattern: str = SIGNAL_GLOB) -> Path:
    paths = [
        Path(path)
        for path in glob.glob(str(_resolve(pattern)))
        if not path.endswith("_pointer.json")
    ]
    if not paths:
        raise FileNotFoundError(f"No signal files matched {pattern!r}")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _load_signal(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = signal.get("target_weights") if isinstance(signal.get("target_weights"), dict) else {}
    out = {ticker: max(0.0, _num(raw.get(ticker), 0.0)) for ticker in PRODUCTION_TICKERS}
    total = sum(out.values())
    if total <= 0.0:
        return out
    return {ticker: value / total for ticker, value in out.items()}


def _fund_00631l_from_cash(weights: dict[str, float], target_00631l: float) -> dict[str, float]:
    out = {ticker: max(0.0, _num(weights.get(ticker), 0.0)) for ticker in PRODUCTION_TICKERS}
    current = out.get("00631L.TW", 0.0)
    target = max(current, min(max(float(target_00631l), 0.0), 0.10))
    add = max(0.0, target - current)
    shift = min(add, out.get("cash", 0.0))
    out["cash"] = max(0.0, out.get("cash", 0.0) - shift)
    out["00631L.TW"] = current + shift
    total = sum(out.values())
    return {ticker: value / total for ticker, value in out.items()} if total > 0.0 else out


def build_small_reentry_shadow(
    *,
    signal: dict[str, Any],
    a2120: dict[str, Any],
    small_target_00631l: float = 0.05,
) -> dict[str, Any]:
    current = _weights(signal)
    state = a2120.get("daily_state") if isinstance(a2120.get("daily_state"), dict) else {}
    scorecard = a2120.get("scorecard_decision") if isinstance(a2120.get("scorecard_decision"), dict) else {}
    latest_features = signal.get("latest_features") if isinstance(signal.get("latest_features"), dict) else {}
    trough = signal.get("trough_nowcast") if isinstance(signal.get("trough_nowcast"), dict) else {}
    trough_inputs = trough.get("inputs") if isinstance(trough.get("inputs"), dict) else {}
    alignment = trough_inputs.get("signal_alignment") if isinstance(trough_inputs.get("signal_alignment"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    live_date = str(signal.get("actual_data_date") or "")
    a2120_date = str(state.get("date") or "")
    if not live_date or not a2120_date or live_date != a2120_date:
        blockers.append("a2120_daily_state_not_aligned_with_live_signal")
    if signal.get("execution_allowed") is not True:
        blockers.append("execution_not_allowed")
    if str(signal.get("execution_regime") or "") != "golden1":
        blockers.append("execution_regime_not_golden1")
    if scorecard.get("daily_advisory") != "enable_daily_advisory_shadow_only":
        blockers.append("a2120_daily_advisory_not_enabled")
    if scorecard.get("production") != "do_not_promote":
        warnings.append("unexpected_a2120_production_state")
    if str(state.get("compounding_regime") or "") != "TREND_PERSISTENT":
        blockers.append("a2120_regime_not_trend_persistent")
    if str(state.get("raw_action") or "") != "FAST_REENTER_CANDIDATE":
        blockers.append("a2120_raw_action_not_fast_reenter")
    hard_blockers = state.get("hard_blockers") if isinstance(state.get("hard_blockers"), list) else []
    if hard_blockers:
        blockers.append("a2120_full_reentry_has_hard_blockers")
    if current.get("cash", 0.0) < small_target_00631l:
        blockers.append("insufficient_cash_for_small_00631l_stage")
    if current.get("00631L.TW", 0.0) >= small_target_00631l:
        blockers.append("current_00631l_already_at_or_above_small_target")
    if int(_num(latest_features.get("tail_risk_score"), 0.0)) > 0:
        blockers.append("tail_risk_score_positive")
    if str(alignment.get("dominant_direction") or "") == "bearish":
        blockers.append("dominant_direction_bearish")

    proposed_if_clear = _fund_00631l_from_cash(current, small_target_00631l)
    active = not blockers
    proposed = proposed_if_clear if active else dict(current)
    return {
        "status": "active_shadow_candidate" if active else "inactive",
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "candidate_policy": "a2120_small_00631l_reentry_cap5pct_cash_funded",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_data_date": live_date or None,
        "a2120_daily_state_date": a2120_date or None,
        "current_target_weights": current,
        "proposed_shadow_target_weights": proposed,
        "candidate_target_weights_if_blockers_clear": proposed_if_clear,
        "delta_weights": {
            ticker: proposed.get(ticker, 0.0) - current.get(ticker, 0.0)
            for ticker in PRODUCTION_TICKERS
        },
        "blockers": blockers,
        "warnings": warnings,
        "inputs": {
            "a2120_daily_state": state,
            "a2120_scorecard_decision": scorecard,
            "latest_features": {
                key: latest_features.get(key)
                for key in ("ma_gap", "drawdown", "exit_momentum_5d", "total_risk_score", "tail_risk_score")
            },
            "signal_alignment": alignment,
        },
        "promotion_requirements": [
            "fresh A21.20 daily_state aligned to live signal actual_data_date",
            "separate execution-plan replay for the small 5pct target, not the full re-entry target",
            "forward shadow monitoring before any live target-weight integration",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=None)
    parser.add_argument("--a2120", default=str(DEFAULT_A2120))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--small-target-00631l", type=float, default=0.05)
    args = parser.parse_args()

    signal_path = _resolve(args.signal) if args.signal else _latest_signal_path()
    signal = _load_signal(signal_path)
    a2120_path = _resolve(args.a2120)
    result = build_small_reentry_shadow(
        signal=signal,
        a2120=_load_json(a2120_path),
        small_target_00631l=args.small_target_00631l,
    )
    result["source_signal_path"] = str(signal_path)
    result["source_a2120_path"] = str(a2120_path)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = _resolve(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    result_path = results_dir / f"a2120_small_00631l_reentry_shadow_{stamp}.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"output": str(output), "result_path": str(result_path), "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
