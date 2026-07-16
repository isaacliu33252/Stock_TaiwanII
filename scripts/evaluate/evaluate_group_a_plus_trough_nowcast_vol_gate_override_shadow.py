#!/usr/bin/env python3
"""Shadow test a narrow volatility-gate override for trough re-entry.

Research-only. The override is only considered when:

1. trough nowcast state is PARTIAL_REENTRY,
2. volatility gate is high-vol,
3. there is an attempted 00631L buy,
4. extreme-risk guard is not active.

It does not change target weights and never buys beyond the original target.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.leveraged_compounding_regime import (
    TREND_PERSISTENT,
    CompoundingRegimeThresholds,
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.runners.a2118 import run_a2118
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment import (
    COMMON_A2118_KW,
    _attempt_forward_returns,
    _extreme_risk_blocks,
    _parse_windows,
    _portfolio_value,
    _target_weights,
)
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_shadow import DEFAULT_WINDOWS, build_trough_state_frame
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame

OVERRIDE_POLICIES = {
    "no_override": 0.0,
    "micro_override_25pct": 0.25,
    "small_override_50pct": 0.50,
    "full_override_100pct": 1.0,
}
CONFIRMATION_MODES = (
    "none",
    "second_partial",
    "no_lower_low_3d",
    "second_or_no_lower_low_3d",
)
# Fable audit (2026-07-16, combination opportunities #1): eligibility was
# previously PARTIAL_REENTRY-only, which produced only 2 eligible events in
# the full backtest history -- too few to promote. A21.20's compounding
# regime (TREND_PERSISTENT) is an independent signal computed from serial
# return dependence rather than trough microstructure, so unioning it in
# should grow the sample without just re-detecting the same days. Two other
# candidates named in that audit -- cross-market graph REENTER probability
# and the DFL REENTER action -- are deliberately NOT included here: both
# have their own evaluators documenting that their REENTER side is unstable
# / has no demonstrated case (see evaluate_cross_market_directed_graph_shadow.py
# and the A21.18 DFL shadow handoffs), so folding them in would launder an
# already-rejected signal into this eligibility gate.
ELIGIBILITY_MODES = (
    "trough_partial_reentry_only",
    "trough_or_compounding_trend_persistent",
)
# Same tuned thresholds run_a2120_daily_shadow_pipeline.py uses for its daily
# shadow diagnostic, so this experiment tests the same TREND_PERSISTENT
# signal that is actually being produced in shadow today.
TUNED_COMPOUNDING_THRESHOLDS = CompoundingRegimeThresholds(
    ar1_trend_min=0.00,
    ar1_revert_max=-0.15,
    variance_ratio_trend_min=1.02,
    variance_ratio_revert_max=0.98,
    trend_persistence_min=0.50,
    trend_persistence_revert_max=0.55,
    reversal_speed_revert_min=0.55,
    reversal_speed_trend_max=0.50,
    drawdown_recovery_revert_min=0.50,
    trend_score_min=3,
    mean_reversion_score_min=5,
)


def _build_compounding_regime_series(prices: pd.DataFrame) -> pd.Series:
    features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
    classified = classify_compounding_regime(features, thresholds=TUNED_COMPOUNDING_THRESHOLDS)
    return classified["compounding_regime"].reindex(prices.index)


def _confirmation_snapshot(
    *,
    dt: pd.Timestamp,
    prices: pd.DataFrame,
    aligned_states: pd.Series,
    mode: str,
) -> dict[str, Any]:
    pos = prices.index.get_loc(dt)
    if isinstance(pos, slice):
        pos = pos.start
    pos = int(pos)
    previous_state = str(aligned_states.iloc[pos - 1]) if pos > 0 else None
    second_partial = bool(previous_state == "PARTIAL_REENTRY")
    no_lower_low_3d = False
    close_0050 = None
    prior_3d_low_0050 = None
    if "0050.TW" in prices.columns and pos >= 1:
        prior = prices["0050.TW"].iloc[max(0, pos - 3):pos].astype(float).dropna()
        close_0050 = float(prices["0050.TW"].iloc[pos])
        if not prior.empty:
            prior_3d_low_0050 = float(prior.min())
            no_lower_low_3d = bool(close_0050 >= prior_3d_low_0050)

    if mode == "none":
        confirmed = True
    elif mode == "second_partial":
        confirmed = second_partial
    elif mode == "no_lower_low_3d":
        confirmed = no_lower_low_3d
    elif mode == "second_or_no_lower_low_3d":
        confirmed = bool(second_partial or no_lower_low_3d)
    else:
        raise ValueError(f"unknown confirmation mode: {mode}")

    return {
        "confirmation_mode": mode,
        "confirmation_passed": bool(confirmed),
        "previous_trough_state": previous_state,
        "second_consecutive_partial": second_partial,
        "no_fresh_0050_lower_low_3d": no_lower_low_3d,
        "0050_close": round(close_0050, 4) if close_0050 is not None else None,
        "0050_prior_3d_low": round(prior_3d_low_0050, 4) if prior_3d_low_0050 is not None else None,
    }


def simulate_override_policy(
    *,
    prices: pd.DataFrame,
    frame: pd.DataFrame,
    trough_state: pd.DataFrame,
    gate_frame: pd.DataFrame,
    report: dict[str, Any],
    initial_value: float,
    override_fraction: float,
    confirmation_mode: str = "none",
    eligibility_mode: str = "trough_partial_reentry_only",
    compounding_regime: pd.Series | None = None,
    min_attempt_weight: float = 0.0025,
    baseline_buy_fraction: float = 0.4,
    partial_buy_fraction: float = 0.7,
) -> dict[str, Any]:
    if eligibility_mode not in ELIGIBILITY_MODES:
        raise ValueError(f"unknown eligibility mode: {eligibility_mode}")
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    events: list[dict[str, Any]] = []
    override_events: list[dict[str, Any]] = []
    aligned_states = trough_state["state"].reindex(prices.index).fillna("NO_TROUGH")
    aligned_gate = gate_frame["volatility_gate"].reindex(prices.index).fillna("neutral_vol")
    aligned_compounding_regime = (
        compounding_regime.reindex(prices.index).fillna("UNAVAILABLE")
        if compounding_regime is not None
        else pd.Series("UNAVAILABLE", index=prices.index)
    )
    regimes = frame["execution_regime"].astype(str).reindex(prices.index)
    values: list[float] = []

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
        compounding_state = str(aligned_compounding_regime.loc[dt])
        trend_persistent_signal = (
            eligibility_mode == "trough_or_compounding_trend_persistent"
            and compounding_state == TREND_PERSISTENT
        )
        buy_fraction = partial_buy_fraction if partial else baseline_buy_fraction
        confirmation = _confirmation_snapshot(
            dt=pd.Timestamp(dt),
            prices=prices,
            aligned_states=aligned_states,
            mode=confirmation_mode,
        )

        attempted_631l = target_values.get("00631L.TW", 0.0) - current_values.get("00631L.TW", 0.0)
        attempted_631l_weight = attempted_631l / value
        override_eligible = bool(
            (partial or trend_persistent_signal)
            and high_vol
            and not extreme
            and attempted_631l_weight > min_attempt_weight
            and confirmation["confirmation_passed"]
        )
        override_weight = max(attempted_631l_weight, 0.0) * float(override_fraction) if override_eligible else 0.0

        new_values: dict[str, float] = {}
        for ticker in TICKERS:
            current = current_values.get(ticker, 0.0)
            target = target_values.get(ticker, 0.0)
            if target <= current:
                new_values[ticker] = target
                continue
            if ticker == "00631L.TW" and high_vol:
                allowed_delta = value * override_weight if override_eligible else 0.0
                new_values[ticker] = min(current + allowed_delta, target)
            elif ticker in {"0050.TW", "00631L.TW"} and extreme:
                new_values[ticker] = current
            else:
                new_values[ticker] = current + (target - current) * buy_fraction

        if override_eligible:
            trigger_source = (
                "trough_and_compounding" if partial and trend_persistent_signal
                else "trough" if partial
                else "compounding_trend_persistent"
            )
            event = {
                "date": str(pd.Timestamp(dt).date()),
                "regime": regime,
                "trough_state": state,
                "compounding_regime": compounding_state,
                "trigger_source": trigger_source,
                "volatility_gate": str(aligned_gate.loc[dt]),
                "portfolio_value": round(value, 2),
                "attempted_00631l_buy_weight": round(float(attempted_631l_weight), 6),
                "override_fraction": float(override_fraction),
                "override_00631l_buy_weight": round(float(override_weight), 6),
                **confirmation,
            }
            override_events.append(event)
            events.append(event)

        invested = sum(new_values.values())
        cash = max(value - invested, 0.0)
        shares = {ticker: new_values.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12) for ticker in TICKERS}
        values.append(_portfolio_value(price_row, shares, cash))

    _attempt_forward_returns(prices, events)
    curve = pd.Series(values, index=prices.index[: len(values)], dtype=float)
    dd10_bad = [
        event
        for event in events
        if (event.get("00631L.TW_fwd_return_5d") or 0.0) >= 0.03
    ]
    return {
        "metrics": _metrics(curve, initial_value),
        "override_eligible_days": len(override_events),
        "override_events": events[:100],
        "missed_rebound_recovered_proxy_count": len(dd10_bad),
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
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
    trough = build_trough_state_frame(db_path=db_path, strategy_frame=frame)
    compounding_regime = _build_compounding_regime_series(prices)
    policies = {}
    for eligibility_mode in ELIGIBILITY_MODES:
        eligibility_suffix = "" if eligibility_mode == "trough_partial_reentry_only" else f"__{eligibility_mode}"
        for confirm_mode in CONFIRMATION_MODES:
            for name, fraction in OVERRIDE_POLICIES.items():
                policy_name = name if confirm_mode == "none" else f"{name}__{confirm_mode}"
                policy_name = f"{policy_name}{eligibility_suffix}"
                policies[policy_name] = simulate_override_policy(
                    prices=prices,
                    frame=frame,
                    trough_state=trough,
                    gate_frame=gate_frame,
                    report=report,
                    initial_value=initial_value,
                    override_fraction=fraction,
                    confirmation_mode=confirm_mode,
                    eligibility_mode=eligibility_mode,
                    compounding_regime=compounding_regime,
                )
    baseline = policies["no_override"]["metrics"]
    for payload in policies.values():
        payload["delta_vs_no_override"] = {
            key: float(payload["metrics"][key] - baseline[key])
            for key in ("final_value", "sharpe_ratio", "max_drawdown")
        }
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "policies": policies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "group_a_plus_trough_nowcast_vol_gate_override_shadow_20260714.json"))
    args = parser.parse_args()

    db_path = Path(args.db)
    windows = _parse_windows(args.windows)
    payload = {
        "experiment": "group_a_plus_trough_nowcast_vol_gate_override_shadow",
        "research_only": True,
        "policy_scope": "PARTIAL_REENTRY_high_vol_00631l_buy_attempt_only",
        "windows": [],
    }
    for label, start, end, panel, kind in windows:
        print(f"Evaluating {label}: {start}..{end}")
        payload["windows"].append(
            evaluate_window(
                label=label,
                start=start,
                end=end,
                panel=panel,
                kind=kind,
                db_path=db_path,
                initial_value=args.initial_value,
            )
        )

    totals: dict[str, Any] = {}
    policy_names = [name for window in payload["windows"] for name in window["policies"]]
    for policy in sorted(set(policy_names)):
        totals[policy] = {
            "override_eligible_days": int(sum(w["policies"][policy]["override_eligible_days"] for w in payload["windows"])),
            "delta_final_value_sum": float(sum(w["policies"][policy]["delta_vs_no_override"]["final_value"] for w in payload["windows"])),
            "delta_sharpe_sum": float(sum(w["policies"][policy]["delta_vs_no_override"]["sharpe_ratio"] for w in payload["windows"])),
            "delta_max_drawdown_sum": float(sum(w["policies"][policy]["delta_vs_no_override"]["max_drawdown"] for w in payload["windows"])),
        }
    payload["totals"] = totals
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {out}")
    print(json.dumps(totals, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
