#!/usr/bin/env python3
"""Research sweep: use ncf_2330 (TSMC individual-stock) tail-risk as a
re-entry veto on a2118's NCF late-bull hedge hold logic, instead of the
already-rejected standalone exit trim (`_apply_tsmc_weakness_trim`).

a2118's hold mechanism (`h5_reentry_min>0` branch of `_apply_late_bull_overlay`
in group_a_plus/runners/a2118.py): once the late-bull hedge triggers, it stays
in `ncf_late_bull_hedge` until 00631L's own H5 NCF probability confirms
reversal (`h5_prob >= h5_reentry_min`). This tests an asymmetric use of
ncf_2330: never trigger a new hedge entry, only *delay* re-entry to golden1
(hold the existing de-leverage one more day) if TSMC's own tail-risk output
is still elevated when 00631L's signal would otherwise exit. This fits
a2118's "never fully exit late-bull" design philosophy better than a new
exit-side trim would.

Read-only with respect to production strategy code: reimplements only the
`h5_reentry_min>0` loop (production does not set gain_prob_soft_min /
rally_suppress_min, so those branches are omitted) with the veto condition
added; does not edit group_a_plus/runners/a2118.py. Writes one JSON report
to results/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import (  # noqa: E402
    DEFENSIVE_BASKETS,
    _delayed_regime,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (  # noqa: E402
    DEFAULT_DECISION_POINTER,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (  # noqa: E402
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path  # noqa: E402
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    NCF_LB_REGIME,
    _apply_late_bull_overlay,
    _late_bull_hedge_weights,
    _load_ncf_panel,
)

START = "2025-01-02"
END = "2026-07-03"
INITIAL_VALUE = 1_000_000.0

PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
PANEL_2330 = PROJECT_ROOT / "results" / "ncf_2330_improved_panel_latest_20260703.csv"
OUT = PROJECT_ROOT / "results" / "ncf_2330_reentry_veto_sweep_20260705.json"

# Production a2118 params (report/group_a_plus/latest/strategy.json runner_params).
MA_GAP_MIN = 0.10
H20_MAX = 0.33
CONF_MIN = 0.55
H5_REENTRY_MIN = 0.55

VETO_THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60]


def _apply_late_bull_overlay_with_tsmc_veto(
    execution_regime: pd.Series,
    panel_631l: pd.DataFrame,
    ma_gap_series: pd.Series,
    tsmc_tail: pd.Series,
    *,
    veto_max: float,
    ma_gap_min: float = MA_GAP_MIN,
    h20_max: float = H20_MAX,
    conf_min: float = CONF_MIN,
    h5_reentry_min: float = H5_REENTRY_MIN,
) -> tuple[pd.Series, dict]:
    """Same hold state machine as a2118's h5_reentry_min>0 branch, plus:
    when 00631L's own H5 signal would exit the hold, also require TSMC's own
    tail-risk probability to be below `veto_max` that day. If TSMC data is
    unavailable for the day, don't veto (fail open, same policy as the rest
    of the diagnostic-only ncf_2330 integration)."""
    modified = execution_regime.copy()
    trigger_events: list[dict] = []
    hold_days: list[str] = []
    vetoed_exit_days: list[str] = []
    in_hedge = False

    for d in execution_regime.index:
        if str(execution_regime.loc[d]) != "golden1":
            in_hedge = False
            continue
        if d not in panel_631l.index:
            continue

        ma_gap = float(ma_gap_series.get(d, 0.0))
        h20_raw = panel_631l.loc[d, "prob_up_h20"]
        conf_raw = panel_631l.loc[d, "confidence"]
        if pd.isna(h20_raw) or pd.isna(conf_raw):
            continue
        h20_prob = float(h20_raw)
        conf = float(conf_raw)
        h5_raw = panel_631l.loc[d, "prob_up_h5"] if "prob_up_h5" in panel_631l.columns else 1.0
        h5_prob = float(h5_raw) if pd.notna(h5_raw) else 1.0

        is_trigger = ma_gap > ma_gap_min and h20_prob < h20_max and conf > conf_min

        if is_trigger and not in_hedge:
            in_hedge = True
            modified.loc[d] = NCF_LB_REGIME
            trigger_events.append({
                "date": str(d.date()),
                "ma_gap": round(ma_gap, 4),
                "prob_up_h20": round(h20_prob, 4),
                "confidence": round(conf, 4),
            })
        elif in_hedge:
            if is_trigger:
                hold_days.append(str(d.date()))
            else:
                would_exit = h5_prob >= h5_reentry_min
                tail_val = tsmc_tail.get(d)
                tsmc_still_weak = tail_val is not None and pd.notna(tail_val) and float(tail_val) >= veto_max
                if would_exit and tsmc_still_weak:
                    vetoed_exit_days.append(str(d.date()))
                    hold_days.append(str(d.date()))
                elif would_exit:
                    in_hedge = False
                else:
                    hold_days.append(str(d.date()))

            if in_hedge:
                modified.loc[d] = NCF_LB_REGIME

    return modified, {
        "late_bull_trigger_days": len(trigger_events),
        "late_bull_trigger_events": trigger_events,
        "hold_days": len(hold_days),
        "vetoed_exit_days": vetoed_exit_days,
    }


def _setup():
    policy_signal, _ = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal = _load(_resolve_golden_signal_path())
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(START, 180)
    switch_rule = _build_switch_rule()
    full_prices = _load_prices(_resolve(DB_PATH), list(TICKERS), load_start, END)
    full_chip = _load_chip_features(_resolve(DB_PATH), full_prices.index, load_start, END)
    full_events, full_frame = _switch_returns(
        full_prices, full_chip, switch_rule,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )
    close_prices, frame, _events = _trim_window(full_prices, full_frame, full_events, START, END)
    total_return_prices, _dividend_coverage = _load_total_return_prices(_resolve(DB_PATH), close_prices.index)

    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
        NCF_LB_REGIME: _late_bull_hedge_weights(golden_weights),
    }
    panel_631l = _load_ncf_panel(PANEL_631L)
    ma_gap_series = frame["ma_gap"].reindex(execution_regime.index).fillna(0.0)
    return execution_regime, weights_by_regime, panel_631l, ma_gap_series, total_return_prices


def _simulate(regime: pd.Series, weights_by_regime: dict, total_return_prices: pd.DataFrame) -> dict:
    executed_regime = _delayed_regime(regime, 0)
    curve, sim_result = _simulate_costed_curve(
        total_return_prices, executed_regime, weights_by_regime, INITIAL_VALUE,
        0.001425, 0.0005, 0.001,
    )
    return {"metrics": _metrics(curve, INITIAL_VALUE), "execution": sim_result}


def main() -> None:
    execution_regime, weights_by_regime, panel_631l, ma_gap_series, total_return_prices = _setup()
    tsmc_panel = _load_ncf_panel(PANEL_2330)
    tsmc_tail = tsmc_panel["prob_fwd_mdd_gt5_h20"].astype(float)

    baseline_regime, baseline_overlay = _apply_late_bull_overlay(
        execution_regime, panel_631l, ma_gap_series,
        ma_gap_min=MA_GAP_MIN, h20_max=H20_MAX, conf_min=CONF_MIN, h5_reentry_min=H5_REENTRY_MIN,
    )
    baseline_sim = _simulate(baseline_regime, weights_by_regime, total_return_prices)

    # Sanity check: veto_max so high it can never fire should exactly reproduce baseline.
    sanity_regime, _sanity_overlay = _apply_late_bull_overlay_with_tsmc_veto(
        execution_regime, panel_631l, ma_gap_series, tsmc_tail, veto_max=1.01,
    )
    sanity_matches = bool((sanity_regime == baseline_regime).all())

    variants: list[dict[str, Any]] = []
    for veto_max in VETO_THRESHOLDS:
        veto_regime, veto_overlay = _apply_late_bull_overlay_with_tsmc_veto(
            execution_regime, panel_631l, ma_gap_series, tsmc_tail, veto_max=veto_max,
        )
        veto_sim = _simulate(veto_regime, weights_by_regime, total_return_prices)
        extra_hold_days = int((veto_regime == NCF_LB_REGIME).sum()) - int((baseline_regime == NCF_LB_REGIME).sum())
        m = veto_sim["metrics"]
        bm = baseline_sim["metrics"]
        variants.append({
            "veto_max": veto_max,
            "vetoed_exit_days": veto_overlay["vetoed_exit_days"],
            "extra_hedge_days_vs_baseline": extra_hold_days,
            "metrics": m,
            "delta_vs_baseline": {
                "final_value": float(m["final_value"]) - float(bm["final_value"]),
                "sharpe_ratio": float(m["sharpe_ratio"]) - float(bm["sharpe_ratio"]),
                "max_drawdown": float(m["max_drawdown"]) - float(bm["max_drawdown"]),
            },
        })

    result = {
        "experiment": "ncf_2330_reentry_veto_sweep",
        "window": {"start": START, "end": END},
        "sanity_check_veto_disabled_matches_baseline": sanity_matches,
        "baseline": {
            "metrics": baseline_sim["metrics"],
            "late_bull_trigger_days": baseline_overlay["late_bull_trigger_days"],
            "hedge_days": int((baseline_regime == NCF_LB_REGIME).sum()),
        },
        "variants": variants,
        "inputs": {
            "panel_631l": str(PANEL_631L.relative_to(PROJECT_ROOT)),
            "panel_2330": str(PANEL_2330.relative_to(PROJECT_ROOT)),
        },
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "saved": str(OUT),
                "sanity_check_veto_disabled_matches_baseline": sanity_matches,
                "baseline": {
                    "final_value": baseline_sim["metrics"]["final_value"],
                    "sharpe_ratio": baseline_sim["metrics"]["sharpe_ratio"],
                    "max_drawdown": baseline_sim["metrics"]["max_drawdown"],
                    "hedge_days": result["baseline"]["hedge_days"],
                },
                "variants": [
                    {
                        "veto_max": v["veto_max"],
                        "vetoed_exit_days": v["vetoed_exit_days"],
                        "extra_hedge_days_vs_baseline": v["extra_hedge_days_vs_baseline"],
                        "delta_vs_baseline": v["delta_vs_baseline"],
                    }
                    for v in variants
                ],
            },
            indent=2, ensure_ascii=False, default=str,
        )
    )


if __name__ == "__main__":
    main()
