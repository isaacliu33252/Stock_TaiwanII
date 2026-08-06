#!/usr/bin/env python3
"""Align GroupA+ trough nowcast with execution-layer buy attempts.

Research-only. This script asks whether PARTIAL_REENTRY appears on days when a
staged execution model actually wants to add 0050/00631L exposure.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_shadow import (
    DEFAULT_WINDOWS,
    build_trough_state_frame,
    _forward_return,
    _load_external_rebound_frame,
    _load_ohlcv_frame,
    build_multisource_features,
)
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_param_sweep import (
    SweepParams,
    build_param_state_frame,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame

COMMON_A2118_KW = dict(
    h20_max=0.33,
    conf_min=0.55,
    h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
    momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
    momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
)

FORWARD_HORIZONS = (3, 5, 10)
RISK_TICKERS = ("0050.TW", "00631L.TW")


def _parse_windows(raw: str) -> list[tuple[str, str, str, str, str]]:
    if raw == "default":
        return DEFAULT_WINDOWS
    windows = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 5:
            raise ValueError("Each window must be label,start,end,panel,kind")
        windows.append(tuple(parts))  # type: ignore[arg-type]
    return windows


def _target_weights(report: dict[str, Any], regime: str) -> dict[str, float]:
    weights = report.get("base_weights") or report.get("weights") or {}
    if regime in weights:
        return _normalize(dict(weights[regime]))
    aliases = {"golden1": "golden1_0531_1m", "group_a_plus_defensive": "group_a_plus_defensive_1m"}
    alias = aliases.get(regime)
    if alias and alias in weights:
        return _normalize(dict(weights[alias]))
    raise KeyError(f"Missing target weights for {regime}")


def _portfolio_value(price_row: pd.Series, shares: dict[str, float], cash: float) -> float:
    return float(cash) + sum(float(shares.get(ticker, 0.0)) * float(price_row[ticker]) for ticker in TICKERS)


def _extreme_risk_blocks(row: pd.Series) -> bool:
    total_risk = int(row.get("total_risk_score", 0) or 0)
    tail_risk = int(row.get("tail_risk_score", 0) or 0)
    drawdown = float(row.get("drawdown", 0.0) or 0.0)
    return bool((total_risk >= 9 and drawdown <= -0.04) or tail_risk >= 2)


def _attempt_forward_returns(prices: pd.DataFrame, events: list[dict[str, Any]]) -> None:
    for ticker in RISK_TICKERS:
        if ticker not in prices:
            continue
        close = prices[ticker].astype(float)
        fwd = {h: _forward_return(close, h) for h in FORWARD_HORIZONS}
        for event in events:
            dt = pd.Timestamp(event["date"])
            for horizon, series in fwd.items():
                value = series.reindex([dt]).iloc[0] if dt in series.index else None
                event[f"{ticker}_fwd_return_{horizon}d"] = None if pd.isna(value) else round(float(value), 6)


def simulate_buy_attempt_alignment(
    *,
    prices: pd.DataFrame,
    frame: pd.DataFrame,
    trough_state: pd.DataFrame,
    gate_frame: pd.DataFrame,
    report: dict[str, Any],
    initial_value: float,
    min_attempt_weight: float = 0.0025,
    baseline_buy_fraction: float = 0.4,
    partial_buy_fraction: float = 0.7,
) -> dict[str, Any]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    events: list[dict[str, Any]] = []
    aligned_states = trough_state["state"].reindex(prices.index).fillna("NO_TROUGH")
    aligned_gate = gate_frame["volatility_gate"].reindex(prices.index).fillna("neutral_vol")
    regimes = frame["execution_regime"].astype(str).reindex(prices.index)

    for dt, price_row in prices.iterrows():
        value = _portfolio_value(price_row, shares, cash)
        if value <= 0.0:
            continue
        regime = str(regimes.loc[dt])
        target_w = _target_weights(report, regime)
        current_values = {ticker: float(shares[ticker]) * float(price_row[ticker]) for ticker in TICKERS}
        target_values = {ticker: value * float(target_w.get(ticker, 0.0)) for ticker in TICKERS}
        state = str(aligned_states.loc[dt])
        high_vol = str(aligned_gate.loc[dt]) == "high_vol_defensive"
        extreme = _extreme_risk_blocks(frame.loc[dt])
        partial = state == "PARTIAL_REENTRY"
        buy_fraction = partial_buy_fraction if partial else baseline_buy_fraction

        attempted: dict[str, float] = {}
        blocked: dict[str, str] = {}
        executed: dict[str, float] = {}
        for ticker in RISK_TICKERS:
            delta = target_values.get(ticker, 0.0) - current_values.get(ticker, 0.0)
            delta_weight = delta / value
            if delta_weight <= min_attempt_weight:
                continue
            attempted[ticker] = float(delta_weight)
            if ticker == "00631L.TW" and high_vol:
                blocked[ticker] = "volatility_gate_high_vol"
                continue
            if ticker in RISK_TICKERS and extreme:
                blocked[ticker] = "extreme_risk_no_new_adds"
                continue
            executed[ticker] = float(delta_weight * buy_fraction)

        if attempted:
            allowed_fast = bool(partial and executed and not blocked)
            events.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "regime": regime,
                    "trough_state": state,
                    "volatility_gate": str(aligned_gate.loc[dt]),
                    "extreme_risk_blocks": extreme,
                    "compounding_guard_status": "unavailable_not_evaluated",
                    "portfolio_value": round(value, 2),
                    "attempted_buy_weight": {k: round(v, 6) for k, v in attempted.items()},
                    "executed_buy_weight": {k: round(v, 6) for k, v in executed.items()},
                    "blocked": blocked,
                    "allowed_fast_reentry": allowed_fast,
                    "buy_fraction": buy_fraction,
                }
            )

        # Apply staged execution for all assets so deferred buys can generate
        # future daily buy attempts, not only regime-change attempts.
        new_values: dict[str, float] = {}
        for ticker in TICKERS:
            current = current_values.get(ticker, 0.0)
            target = target_values.get(ticker, 0.0)
            if target > current:
                blocked_add = (ticker == "00631L.TW" and high_vol) or (ticker in RISK_TICKERS and extreme)
                new_values[ticker] = current if blocked_add else current + (target - current) * buy_fraction
            else:
                new_values[ticker] = target
        invested = sum(new_values.values())
        cash = max(value - invested, 0.0)
        shares = {ticker: new_values.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12) for ticker in TICKERS}

    _attempt_forward_returns(prices, events)
    partial_events = [event for event in events if event["trough_state"] == "PARTIAL_REENTRY"]
    allowed_fast = [event for event in partial_events if event["allowed_fast_reentry"]]
    blocked_fast = [event for event in partial_events if event["blocked"]]
    missed_without_partial = [
        event
        for event in events
        if event["trough_state"] != "PARTIAL_REENTRY"
        and (event.get("00631L.TW_fwd_return_5d") or 0.0) >= 0.03
    ]
    missed_blocked = [
        event
        for event in blocked_fast
        if (event.get("00631L.TW_fwd_return_5d") or 0.0) >= 0.03
    ]
    return {
        "buy_attempt_days": len(events),
        "partial_reentry_days": int((aligned_states == "PARTIAL_REENTRY").sum()),
        "partial_reentry_buy_attempt_days": len(partial_events),
        "allowed_fast_reentry_days": len(allowed_fast),
        "blocked_fast_reentry_days": len(blocked_fast),
        "blocked_by_volatility_gate": sum(
            1 for event in partial_events if "volatility_gate_high_vol" in set(event["blocked"].values())
        ),
        "blocked_by_extreme_risk": sum(
            1 for event in partial_events if "extreme_risk_no_new_adds" in set(event["blocked"].values())
        ),
        "blocked_by_compounding_guard": 0,
        "missed_rebound_without_partial": len(missed_without_partial),
        "missed_rebound_blocked_by_guard": len(missed_blocked),
        "events": events[:300],
        "missed_rebound_without_partial_events": missed_without_partial[:100],
        "missed_rebound_blocked_by_guard_events": missed_blocked[:100],
    }


def _build_trough_state_with_params(
    *,
    db_path: Path,
    strategy_frame: pd.DataFrame,
    sweep_params: SweepParams,
) -> pd.DataFrame:
    """Same inputs/output shape as build_trough_state_frame, but reuses the
    parameterized classifier from evaluate_group_a_plus_trough_nowcast_param_sweep.py
    instead of trough_nowcast.py's hardcoded (v6-equivalent) thresholds.

    2026-08-05: added so this dollar-value evaluator can be re-run against a
    non-default threshold candidate (e.g. the sweep's breadth_min=0.6 finding)
    with the exact same methodology used for the existing +1527.6/9yr result,
    instead of approximating. Opt-in via --sweep-params; default (None)
    preserves existing behavior exactly.
    """
    index = pd.DatetimeIndex(strategy_frame.index)
    market_proxy = _load_ohlcv_frame(db_path, index)
    external = _load_external_rebound_frame(db_path, index)
    try:
        multisource = build_multisource_features(db_path, pd.bdate_range(index.min() - pd.Timedelta(days=420), index.max()))
    except Exception:
        multisource = pd.DataFrame(index=index)
    multisource = multisource.reindex(index)
    if "txo_pcr_volume_z20" in multisource:
        multisource["txo_pcr_volume_z20_chg5"] = multisource["txo_pcr_volume_z20"].diff(5)
    if "usdtwd_ret5_z60" in multisource:
        multisource["usdtwd_ret5_z60_chg5"] = multisource["usdtwd_ret5_z60"].diff(5)
    return build_param_state_frame(
        strategy_frame=strategy_frame,
        market_proxy=market_proxy,
        multisource=multisource,
        external=external,
        params=sweep_params,
    )


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    sweep_params: SweepParams | None = None,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        **COMMON_A2118_KW,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end).reindex(frame.index)
    chip = _load_chip_features(db_path, prices.index, start, end)
    gate_frame = _build_volatility_gate_frame(prices, chip).reindex(frame.index)
    if sweep_params is not None:
        trough = _build_trough_state_with_params(db_path=db_path, strategy_frame=frame, sweep_params=sweep_params)
    else:
        trough = build_trough_state_frame(db_path=db_path, strategy_frame=frame)
    alignment = simulate_buy_attempt_alignment(
        prices=prices,
        frame=frame,
        trough_state=trough,
        gate_frame=gate_frame,
        report=report,
        initial_value=initial_value,
    )
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "policy": "buy_attempt_alignment_research_only_target_weights_unchanged",
        "alignment": alignment,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "group_a_plus_trough_nowcast_buy_attempt_alignment_20260714.json"))
    parser.add_argument(
        "--sweep-params",
        default=None,
        help=(
            "Optional JSON object overriding PARTIAL_REENTRY thresholds via the "
            "param-sweep's parameterized classifier instead of trough_nowcast.py's "
            "hardcoded defaults, e.g. '{\"breadth_min\": 0.6}'. Unspecified fields "
            "fall back to SweepParams defaults (cap_min=3, reentry_min=3, "
            "rebound_0050_min=0.02, rebound_00631l_min=0.04, breadth_min=0.5, "
            "risk_unwind_chg_max=-0.5). Default None preserves existing behavior."
        ),
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    sweep_params = SweepParams(**json.loads(args.sweep_params)) if args.sweep_params else None
    payload = {
        "experiment": "group_a_plus_trough_nowcast_buy_attempt_alignment",
        "research_only": True,
        "full_reentry": "disabled",
        "sweep_params": asdict(sweep_params) if sweep_params is not None else None,
        "windows": [],
    }
    for label, start, end, panel, kind in _parse_windows(args.windows):
        print(f"Evaluating {label}: {start}..{end}")
        payload["windows"].append(
            evaluate_window(
                sweep_params=sweep_params,
                label=label,
                start=start,
                end=end,
                panel=panel,
                kind=kind,
                db_path=db_path,
                initial_value=args.initial_value,
            )
        )

    totals = {
        key: int(sum(window["alignment"][key] for window in payload["windows"]))
        for key in (
            "buy_attempt_days",
            "partial_reentry_days",
            "partial_reentry_buy_attempt_days",
            "allowed_fast_reentry_days",
            "blocked_fast_reentry_days",
            "blocked_by_volatility_gate",
            "blocked_by_extreme_risk",
            "blocked_by_compounding_guard",
            "missed_rebound_without_partial",
            "missed_rebound_blocked_by_guard",
        )
    }
    payload["totals"] = totals
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {out}")
    print(json.dumps(totals, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
