#!/usr/bin/env python3
"""Read-only verification: does the 2008-proxy shadow candidate patch help or hurt
on real 2025-2026 GroupA+ overlay data? Does NOT modify group_a_plus_config.json.

See GROUP_A_PLUS_2008_SHADOW_CANDIDATE_2025_2026_VERIFY_HANDOFF_20260703.md for context.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_overlay import (  # noqa: E402
    DEFAULT_SOURCE,
    DEFAULT_DCA_SOURCE,
    DEFAULT_VARIANT,
    DEFAULT_INITIAL_CASH,
    _load_prices,
    _load_dca_history,
    _scale_dca_history,
    _set_nested,
    _simulate_base_events_approx,
    _simulate_plus,
    _metrics,
    _promotion_gate,
)

GROUP_A_PLUS_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"

SHADOW_PATCH = {
    "overlay.dynamic_weight_bands": {
        "risk_on": 0.0,
        "caution": 0.01,
        "risk_off": 0.0,
        "severe": 0.0,
    },
    "execution_control.max_turnover_ratio_by_regime": {
        "risk_on": 1.0,
        "caution": 1.0,
        "risk_off": 0.10,
        "severe": 0.10,
    },
    "fast_risk_off_control.cash_floor": 0.35,
}


def build_shadow_config(base_config: dict) -> dict:
    cfg = copy.deepcopy(base_config)
    for dotted_key, value in SHADOW_PATCH.items():
        _set_nested(cfg, dotted_key, copy.deepcopy(value))
    return cfg


def main() -> None:
    base_config = json.loads(GROUP_A_PLUS_CONFIG.read_text(encoding="utf-8"))
    shadow_config = build_shadow_config(base_config)

    source = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
    dca_history = _scale_dca_history(_load_dca_history(DEFAULT_DCA_SOURCE), 1.0)
    replay = source["details"][DEFAULT_VARIANT]["replay"]
    start = str(source["actual_window"]["start"])
    end = str(source["actual_window"]["end"])
    prices = _load_prices(start, end)

    base_approx = _simulate_base_events_approx(
        prices, replay,
        commission_rate=0.001425, etf_sell_tax_rate=0.001,
        initial_cash=DEFAULT_INITIAL_CASH, dca_history=dca_history,
    )

    plus_results = {}
    for name, cfg in [("current_active", base_config), ("shadow_2008_candidate", shadow_config)]:
        plus_results[name] = _simulate_plus(
            prices, replay, cfg,
            commission_rate=0.001425, etf_sell_tax_rate=0.001,
            initial_cash=DEFAULT_INITIAL_CASH, dca_history=dca_history,
        )

    gate = _promotion_gate(base_approx["metrics"], plus_results)

    print(f"Window: {start} ~ {end}  rows={len(prices)}  variant(meta signal)={DEFAULT_VARIANT}")
    print(f"\n{'mode':<24}{'final_value':>14}{'annual_ret':>12}{'sharpe':>9}{'mdd':>9}{'vol':>9}{'rebal':>7}")
    b = base_approx["metrics"]
    print(f"{'base_events_approx':<24}{b['final_value']:>14,.2f}{b.get('annual_return',0):>12.4%}{b['sharpe_ratio']:>9.4f}{b['max_drawdown']:>9.4%}{b['volatility']:>9.4%}{b.get('num_rebalances',0):>7}")
    for name, result in plus_results.items():
        m = result["metrics"]
        print(f"{name:<24}{m['final_value']:>14,.2f}{m.get('annual_return',0):>12.4%}{m['sharpe_ratio']:>9.4f}{m['max_drawdown']:>9.4%}{m['volatility']:>9.4%}{m.get('num_rebalances',0):>7}")

    cur = plus_results["current_active"]["metrics"]
    sh = plus_results["shadow_2008_candidate"]["metrics"]
    print("\nDelta shadow vs current_active:")
    for key in ["final_value", "sharpe_ratio", "max_drawdown", "volatility", "num_rebalances"]:
        print(f"  {key}: {sh[key] - cur[key]:+.6f}")

    print("\nPromotion gate (base-relative):")
    print(json.dumps(gate, indent=2, ensure_ascii=False, default=str))

    out = PROJECT_ROOT / "results" / "group_a_plus_2008_shadow_candidate_vs_active_2025_2026_verify.json"
    out.write_text(json.dumps({
        "window": {"start": start, "end": end, "rows": len(prices)},
        "meta_variant": DEFAULT_VARIANT,
        "base_events_approx": base_approx["metrics"],
        "current_active_metrics": cur,
        "shadow_2008_candidate_metrics": sh,
        "delta_shadow_vs_current": {k: sh[k] - cur[k] for k in ["final_value", "sharpe_ratio", "max_drawdown", "volatility", "num_rebalances"]},
        "promotion_gate": gate,
        "shadow_patch": SHADOW_PATCH,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
