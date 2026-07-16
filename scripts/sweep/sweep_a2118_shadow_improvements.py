#!/usr/bin/env python3
"""Grid-sweep shadow improvements for GroupA+ A21.18.

The script does not change the active latest manifest.  It loads the A21.18
backtest inputs once, evaluates candidate trigger parameters, and writes a JSON
report that can be used as a promotion gate input.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _delayed_regime,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    NCF_LB_REGIME,
    NCF_LB_SOFT_REGIME,
    _apply_late_bull_overlay,
    _late_bull_hedge_weights,
    _load_ncf_panel,
)
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_shadow_improvement_sweep_latest.json"
INITIAL_VALUE = 1_000_000.0
COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005
EQUITY_SELL_TAX = 0.001


def parse_float_list(value: str) -> list[float]:
    out = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not out:
        raise ValueError("Expected at least one float value")
    return out


def parse_optional_float_list(value: str) -> list[float | None]:
    out: list[float | None] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        out.append(None if item.lower() in {"none", "null"} else float(item))
    if not out:
        raise ValueError("Expected at least one optional float value")
    return out


def parse_int_list(value: str) -> list[int]:
    out = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not out:
        raise ValueError("Expected at least one integer value")
    return out


def _load_static_data(
    *,
    start: str,
    end: str,
    db: Path,
    warmup_days: int,
    chip_data_fallback_max_stale_days: int | None,
) -> dict[str, Any]:
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve_golden_signal_path()
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, warmup_days)
    switch_rule = _build_switch_rule()
    full_prices = _load_prices(_resolve(db), list(TICKERS), load_start, end)
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(
        full_prices,
        full_chip,
        switch_rule,
        chip_data_fallback_max_stale_days=chip_data_fallback_max_stale_days,
    )
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(db), close_prices.index)
    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
        NCF_LB_REGIME: _late_bull_hedge_weights(golden_weights),
        NCF_LB_SOFT_REGIME: _late_bull_hedge_weights(golden_weights, intensity=0.5),
    }
    return {
        "policy_signal_path": str(policy_signal_path),
        "golden_signal_path": str(golden_signal_path),
        "total_return_prices": total_return_prices,
        "frame": frame,
        "events": events,
        "execution_regime": execution_regime,
        "weights_by_regime": weights_by_regime,
        "ma_gap_series": frame["ma_gap"].reindex(execution_regime.index).fillna(0.0),
        "dividend_coverage": dividend_coverage,
    }


def evaluate_candidate(
    static: dict[str, Any],
    panel: pd.DataFrame,
    *,
    name: str,
    h20_max: float,
    conf_min: float,
    h5_reentry_min: float,
    gain_prob_soft_min: float | None,
    rally_suppress_min: float | None,
    soft_hedge_intensity: float,
    regime_execution_delay_days: int,
) -> dict[str, Any]:
    weights_by_regime = dict(static["weights_by_regime"])
    weights_by_regime[NCF_LB_SOFT_REGIME] = _late_bull_hedge_weights(
        weights_by_regime["golden1"],
        intensity=soft_hedge_intensity,
    )
    modified, overlay = _apply_late_bull_overlay(
        static["execution_regime"],
        panel,
        static["ma_gap_series"],
        ma_gap_min=0.10,
        h20_max=h20_max,
        conf_min=conf_min,
        h5_reentry_min=h5_reentry_min,
        gain_prob_soft_min=gain_prob_soft_min,
        rally_suppress_min=rally_suppress_min,
    )
    executed = _delayed_regime(modified, regime_execution_delay_days)
    curve, execution = _simulate_costed_curve(
        static["total_return_prices"],
        executed,
        weights_by_regime,
        INITIAL_VALUE,
        COMMISSION_RATE,
        SLIPPAGE_RATE,
        EQUITY_SELL_TAX,
    )
    metrics = _metrics(curve, INITIAL_VALUE)
    return {
        "name": name,
        "h20_max": float(h20_max),
        "conf_min": float(conf_min),
        "h5_reentry_min": float(h5_reentry_min),
        "gain_prob_soft_min": gain_prob_soft_min,
        "rally_suppress_min": rally_suppress_min,
        "soft_hedge_intensity": float(soft_hedge_intensity),
        "regime_execution_delay_days": int(regime_execution_delay_days),
        **metrics,
        "transaction_cost": float(execution.get("transaction_cost", 0.0)),
        "turnover_value": float(execution.get("turnover_value", 0.0)),
        "rebalance_count": int(execution.get("rebalance_count", 0)),
        "trigger_days": int(overlay.get("late_bull_trigger_days", 0)),
        "total_hedge_days": int(overlay.get("total_hedge_days", overlay.get("late_bull_trigger_days", 0))),
        "hold_days": len(overlay.get("hold_days", [])),
        "soft_days": len(overlay.get("soft_hedge_days", [])),
        "suppressed_days": len(overlay.get("suppressed_days", [])),
    }


def _score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    """Conservative scalar score for ranking shadow candidates."""
    return float(
        (row["sharpe_ratio"] - baseline["sharpe_ratio"])
        + 0.25 * (row["sortino_ratio"] - baseline["sortino_ratio"])
        + 0.50 * (row["max_drawdown"] - baseline["max_drawdown"])
        + 0.10 * ((row["final_value"] - baseline["final_value"]) / baseline["final_value"])
    )


def build_report(
    *,
    panel_path: Path,
    start: str,
    end: str,
    db: Path,
    warmup_days: int,
    h20_values: list[float],
    conf_values: list[float],
    h5_values: list[float],
    gain_soft_values: list[float | None],
    rally_suppress_values: list[float | None],
    soft_intensity_values: list[float],
    delay_values: list[int],
    chip_data_fallback_max_stale_days: int | None,
) -> dict[str, Any]:
    if not panel_path.is_absolute():
        panel_path = PROJECT_ROOT / panel_path
    panel = _load_ncf_panel(panel_path)
    if panel is None:
        raise ValueError(f"Could not load panel: {panel_path}")
    static = _load_static_data(
        start=start,
        end=end,
        db=db,
        warmup_days=warmup_days,
        chip_data_fallback_max_stale_days=chip_data_fallback_max_stale_days,
    )
    baseline = evaluate_candidate(
        static,
        panel,
        name="active_a2118_manifest_params",
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        gain_prob_soft_min=None,
        rally_suppress_min=None,
        soft_hedge_intensity=0.5,
        regime_execution_delay_days=0,
    )

    rows: list[dict[str, Any]] = [baseline]
    seen = {
        (
            baseline["h20_max"],
            baseline["conf_min"],
            baseline["h5_reentry_min"],
            baseline["gain_prob_soft_min"],
            baseline["rally_suppress_min"],
            baseline["soft_hedge_intensity"],
            baseline["regime_execution_delay_days"],
        )
    }
    for h20, conf, h5, gain_soft, suppress, intensity, delay in itertools.product(
        h20_values,
        conf_values,
        h5_values,
        gain_soft_values,
        rally_suppress_values,
        soft_intensity_values,
        delay_values,
    ):
        key = (h20, conf, h5, gain_soft, suppress, intensity, delay)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            evaluate_candidate(
                static,
                panel,
                name="grid_candidate",
                h20_max=h20,
                conf_min=conf,
                h5_reentry_min=h5,
                gain_prob_soft_min=gain_soft,
                rally_suppress_min=suppress,
                soft_hedge_intensity=intensity,
                regime_execution_delay_days=delay,
            )
        )

    for row in rows:
        row["score_vs_active"] = _score(row, baseline)
        row["delta_final_value"] = float(row["final_value"] - baseline["final_value"])
        row["delta_sharpe"] = float(row["sharpe_ratio"] - baseline["sharpe_ratio"])
        row["delta_sortino"] = float(row["sortino_ratio"] - baseline["sortino_ratio"])
        row["delta_max_drawdown"] = float(row["max_drawdown"] - baseline["max_drawdown"])
        row["dominates_active"] = bool(
            row["final_value"] >= baseline["final_value"]
            and row["sharpe_ratio"] >= baseline["sharpe_ratio"]
            and row["max_drawdown"] >= baseline["max_drawdown"]
        )
    ranked = sorted(rows, key=lambda item: item["score_vs_active"], reverse=True)
    best = ranked[0]
    decision = (
        "candidate_for_manual_review"
        if best["dominates_active"] and best["name"] != baseline["name"]
        else "keep_active_a2118"
    )
    return {
        "schema_version": 1,
        "report_type": "a2118_shadow_improvement_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "panel": str(panel_path),
            "panel_rows": int(len(panel)),
            "panel_start": str(panel.index.min().date()),
            "panel_end": str(panel.index.max().date()),
            "db": str(db),
            "start": start,
            "end": end,
            "warmup_days": warmup_days,
            "chip_data_fallback_max_stale_days": chip_data_fallback_max_stale_days,
        },
        "search_space": {
            "h20_values": h20_values,
            "conf_values": conf_values,
            "h5_values": h5_values,
            "gain_soft_values": gain_soft_values,
            "rally_suppress_values": rally_suppress_values,
            "soft_intensity_values": soft_intensity_values,
            "delay_values": delay_values,
        },
        "baseline": baseline,
        "best": best,
        "decision": decision,
        "rows": ranked,
        "active_allocation_impact": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--h20-values", default="0.28,0.30,0.33,0.35,0.38")
    parser.add_argument("--conf-values", default="0.50,0.55,0.60")
    parser.add_argument("--h5-values", default="0.0,0.55")
    parser.add_argument("--gain-soft-values", default="none,0.30,0.35")
    parser.add_argument("--rally-suppress-values", default="none,0.50")
    parser.add_argument("--soft-intensity-values", default="0.25,0.50")
    parser.add_argument("--delay-values", default="0,1")
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int, default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("sweep_a2118_shadow_improvements")
    try:
        panel_path = Path(args.panel)
        if not panel_path.is_absolute():
            panel_path = PROJECT_ROOT / panel_path
        report = build_report(
            panel_path=panel_path,
            start=args.start,
            end=args.end,
            db=Path(args.db),
            warmup_days=args.warmup_days,
            h20_values=parse_float_list(args.h20_values),
            conf_values=parse_float_list(args.conf_values),
            h5_values=parse_float_list(args.h5_values),
            gain_soft_values=parse_optional_float_list(args.gain_soft_values),
            rally_suppress_values=parse_optional_float_list(args.rally_suppress_values),
            soft_intensity_values=parse_float_list(args.soft_intensity_values),
            delay_values=parse_int_list(args.delay_values),
            chip_data_fallback_max_stale_days=args.chip_data_fallback_max_stale_days,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A21.18 shadow sweep: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
