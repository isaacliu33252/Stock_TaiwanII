#!/usr/bin/env python3
"""Build a shadow-only staged re-entry suggestion for GroupA+ live signals.

This script does not change live weights, execution regimes, signal pointers,
or order generation. It reads one live signal JSON and writes an advisory JSON
that answers: if a staged re-entry policy existed, what would it suggest today?
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"
DEFAULT_LATEST_REPORT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "staged_reentry_shadow.json"
DEFAULT_HISTORY_REPORT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "staged_reentry_shadow_event_study.json"
DEFAULT_DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
SIGNAL_GLOB = "results/group_a_plus_live_signal_v2_*.json"
PRODUCTION_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash")
FORWARD_HORIZONS = (5, 10, 20)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _latest_signal_path(pattern: str = SIGNAL_GLOB) -> Path:
    paths = [
        Path(path)
        for path in glob.glob(str(_resolve(pattern)))
        if not path.endswith("_pointer.json")
    ]
    if not paths:
        raise FileNotFoundError(f"No signal files matched {pattern!r}")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _load_signal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    normalized = {ticker: max(0.0, _num(weights.get(ticker), 0.0)) for ticker in PRODUCTION_TICKERS}
    total = sum(normalized.values())
    if total <= 0.0:
        return normalized
    return {ticker: value / total for ticker, value in normalized.items()}


def _move_cash_to_0050(weights: dict[str, float], add_weight: float) -> dict[str, float]:
    out = {ticker: _num(weights.get(ticker), 0.0) for ticker in PRODUCTION_TICKERS}
    available = max(0.0, out.get("cash", 0.0))
    shift = min(max(add_weight, 0.0), available)
    out["cash"] = available - shift
    out["0050.TW"] = max(0.0, out.get("0050.TW", 0.0)) + shift
    return _normalize_weights(out)


def build_staged_reentry_shadow(
    signal: dict[str, Any],
    *,
    first_stage_cash_to_0050: float = 0.15,
    min_cash_weight: float = 0.40,
) -> dict[str, Any]:
    target = _normalize_weights(signal.get("target_weights") or {})
    latest = signal.get("latest_features") if isinstance(signal.get("latest_features"), dict) else {}
    market_state = signal.get("market_state") if isinstance(signal.get("market_state"), dict) else {}
    trough = signal.get("trough_nowcast") if isinstance(signal.get("trough_nowcast"), dict) else {}
    trough_inputs = trough.get("inputs") if isinstance(trough.get("inputs"), dict) else {}
    market_proxy = trough_inputs.get("market_proxy") if isinstance(trough_inputs.get("market_proxy"), dict) else {}
    signal_alignment = trough_inputs.get("signal_alignment") if isinstance(trough_inputs.get("signal_alignment"), dict) else {}
    full_reentry_checks = trough.get("full_reentry_checks") if isinstance(trough.get("full_reentry_checks"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    if signal.get("execution_allowed") is not True:
        blockers.append("execution_not_allowed")
    if str(signal.get("execution_regime") or "") != "golden1":
        blockers.append("execution_regime_not_golden1")
    if target.get("cash", 0.0) < min_cash_weight:
        blockers.append("cash_buffer_below_minimum")
    if target.get("0050.TW", 0.0) < 0.20:
        blockers.append("0050_core_weight_too_low_for_reentry_anchor")
    if _num(target.get("00632R.TW"), 0.0) > 0.0:
        blockers.append("inverse_hedge_active")
    if int(_num(latest.get("tail_risk_score"), 0.0)) > 0:
        blockers.append("tail_risk_score_positive")
    if int(_num(latest.get("total_risk_score"), 0.0)) > 6:
        blockers.append("total_risk_score_above_first_stage_limit")
    if _num(latest.get("ma_gap"), 0.0) <= 0.0:
        blockers.append("ma_gap_not_positive")
    drawdown = _num(latest.get("drawdown"), 0.0)
    if not (-0.10 <= drawdown <= -0.04):
        blockers.append("drawdown_not_in_bull_pullback_reentry_band")
    if market_proxy.get("no_fresh_0050_lower_low_3d") is not True:
        blockers.append("fresh_0050_lower_low_not_cleared")
    if full_reentry_checks.get("risk_unwind_confirm") is not True:
        blockers.append("risk_unwind_not_confirmed")

    state = str(market_state.get("state") or "")
    if state not in {"bull_pullback_deep", "bull_pullback_shallow", "recovery_early", "recovery_confirmed"}:
        blockers.append("market_state_not_reentry_candidate")

    dominant = str(signal_alignment.get("dominant_direction") or "")
    if dominant == "bearish":
        warnings.append("dominant_direction_bearish_blocks_00631l_stage")

    trough_state = str(trough.get("state") or "NO_TROUGH")
    if trough_state in {"PARTIAL_REENTRY", "FULL_REENTRY"}:
        warnings.append(f"trough_nowcast_{trough_state.lower()}_already_present")
    elif trough_state == "NO_TROUGH":
        warnings.append("trough_nowcast_no_trough_first_stage_0050_only")

    active = not blockers
    proposed = _move_cash_to_0050(target, first_stage_cash_to_0050) if active else dict(target)
    proposed["00631L.TW"] = 0.0 if dominant == "bearish" else proposed.get("00631L.TW", 0.0)
    proposed = _normalize_weights(proposed)

    return {
        "status": "active_shadow_candidate" if active else "inactive",
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "candidate_policy": "bull_pullback_cash_to_0050_first_stage_no_00631l_when_bearish",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_data_date": signal.get("actual_data_date"),
        "requested_as_of_date": signal.get("requested_as_of_date"),
        "strategy_id": signal.get("strategy_id"),
        "current_target_weights": target,
        "proposed_shadow_target_weights": proposed,
        "delta_weights": {
            ticker: proposed.get(ticker, 0.0) - target.get(ticker, 0.0)
            for ticker in PRODUCTION_TICKERS
        },
        "blockers": blockers,
        "warnings": warnings,
        "inputs": {
            "execution_allowed": signal.get("execution_allowed"),
            "execution_regime": signal.get("execution_regime"),
            "market_state": market_state,
            "latest_features": {
                key: latest.get(key)
                for key in ("ma_gap", "drawdown", "exit_momentum_5d", "total_risk_score", "tail_risk_score")
            },
            "trough_nowcast": {
                "state": trough_state,
                "capitulation_score": trough.get("capitulation_score"),
                "reentry_confirmation_score": trough.get("reentry_confirmation_score"),
                "full_reentry_checks": full_reentry_checks,
            },
            "market_proxy": {
                key: market_proxy.get(key)
                for key in (
                    "no_fresh_0050_lower_low_3d",
                    "latest_0050_close",
                    "prior_0050_3d_low",
                    "rebound_0050_from_5d_low",
                    "ret_0050_5d",
                    "ret_00631l_5d",
                    "breadth_up_fraction_groupa",
                )
            },
            "signal_alignment": signal_alignment,
        },
        "promotion_requirements": [
            "run historical shadow backtest before any target_weight integration",
            "00631L stage requires non-bearish dominant direction and independent A21.20 rolling monitor evidence",
            "must remain advisory until ops/promotion gates clear deployment consistency",
        ],
    }


def _load_close_series(db_path: Path, ticker: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ?
            ORDER BY dt
            """,
            [ticker],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No OHLCV rows for {ticker}")
    frame["dt"] = pd.to_datetime(frame["dt"])
    return frame.set_index("dt")["close"].astype(float).sort_index()


def _event_forward_edges(close: pd.Series, date: str, delta_0050: float) -> dict[str, Any]:
    dt = pd.Timestamp(date).normalize()
    eligible = close.loc[close.index <= dt]
    if eligible.empty:
        return {"available": False, "reason": "no_price_at_or_before_signal_date"}
    anchor_date = pd.Timestamp(eligible.index[-1]).normalize()
    anchor_pos = int(close.index.get_loc(anchor_date))
    anchor_price = float(close.iloc[anchor_pos])
    out: dict[str, Any] = {"available": True, "price_anchor_date": str(anchor_date.date())}
    for horizon in FORWARD_HORIZONS:
        pos = anchor_pos + horizon
        if pos >= len(close.index):
            out[f"edge_{horizon}d"] = None
            out[f"ret_0050_{horizon}d"] = None
            continue
        ret = float(close.iloc[pos] / max(anchor_price, 1e-12) - 1.0)
        out[f"ret_0050_{horizon}d"] = ret
        out[f"edge_{horizon}d"] = float(delta_0050) * ret
        out[f"end_date_{horizon}d"] = str(pd.Timestamp(close.index[pos]).date())
    return out


def _stats(values: list[float | None]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None and pd.notna(value)]
    if not clean:
        return {"count": 0, "mean": None, "positive_rate": None, "worst": None, "best": None}
    series = pd.Series(clean, dtype=float)
    return {
        "count": int(len(series)),
        "mean": float(series.mean()),
        "positive_rate": float((series > 0.0).mean()),
        "worst": float(series.min()),
        "best": float(series.max()),
        "median": float(series.median()),
    }


def build_event_study(
    *,
    signal_pattern: str = SIGNAL_GLOB,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    close_0050 = _load_close_series(db_path, "0050.TW")
    paths = sorted(
        [
            Path(path)
            for path in glob.glob(str(_resolve(signal_pattern)))
            if not path.endswith("_pointer.json")
        ],
        key=lambda path: path.stat().st_mtime,
    )
    latest_by_date: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in paths:
        try:
            signal = _load_signal(path)
        except (json.JSONDecodeError, OSError):
            continue
        actual = signal.get("actual_data_date")
        if not actual:
            continue
        latest_by_date[str(actual)] = (path, signal)

    events: list[dict[str, Any]] = []
    inactive_counts: dict[str, int] = {}
    for actual, (path, signal) in sorted(latest_by_date.items()):
        shadow = build_staged_reentry_shadow(signal)
        if shadow["status"] != "active_shadow_candidate":
            for blocker in shadow["blockers"]:
                inactive_counts[blocker] = inactive_counts.get(blocker, 0) + 1
            continue
        delta_0050 = float(shadow["delta_weights"].get("0050.TW", 0.0) or 0.0)
        event = {
            "actual_data_date": actual,
            "source_signal_path": str(path),
            "delta_0050": delta_0050,
            "current_target_weights": shadow["current_target_weights"],
            "proposed_shadow_target_weights": shadow["proposed_shadow_target_weights"],
            "warnings": shadow["warnings"],
            "forward": _event_forward_edges(close_0050, actual, delta_0050),
        }
        events.append(event)

    return {
        "status": "event_study_complete",
        "policy": "shadow_only_no_live_weight_change",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_pattern": signal_pattern,
        "unique_signal_dates": int(len(latest_by_date)),
        "active_event_count": int(len(events)),
        "inactive_blocker_counts": inactive_counts,
        "summary": {
            f"edge_{horizon}d": _stats(
                [
                    event["forward"].get(f"edge_{horizon}d")
                    for event in events
                    if event.get("forward", {}).get("available") is True
                ]
            )
            for horizon in FORWARD_HORIZONS
        },
        "events": events,
        "interpretation": (
            "Event-study only: edge_horizon equals delta_0050_weight times forward 0050 return, "
            "with cash return assumed zero. It is not a full portfolio replay."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", type=str, default=None, help="Signal JSON path. Defaults to latest results signal.")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--latest-report", type=str, default=str(DEFAULT_LATEST_REPORT))
    parser.add_argument("--history-report", type=str, default=str(DEFAULT_HISTORY_REPORT))
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--evaluate-history", action="store_true")
    parser.add_argument("--first-stage-cash-to-0050", type=float, default=0.15)
    args = parser.parse_args()

    if args.evaluate_history:
        history = build_event_study(db_path=_resolve(args.db_path))
        history_report = _resolve(args.history_report)
        history_report.parent.mkdir(parents=True, exist_ok=True)
        history_report.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"history_report": str(history_report), "active_event_count": history["active_event_count"]}, ensure_ascii=False))
        return 0

    signal_path = _resolve(args.signal) if args.signal else _latest_signal_path()
    signal = _load_signal(signal_path)
    result = build_staged_reentry_shadow(
        signal,
        first_stage_cash_to_0050=args.first_stage_cash_to_0050,
    )
    result["source_signal_path"] = str(signal_path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"group_a_plus_staged_reentry_shadow_{stamp}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    latest_report = _resolve(args.latest_report)
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"output_path": str(output_path), "latest_report": str(latest_report), "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
