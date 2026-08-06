#!/usr/bin/env python3
"""Read-only research: does gating the CVaR-tangency defensive allocation
(scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py's dynamic_
tangency_cvar strategy) behind risk_mechanism_classifier's FAST_CRASH /
PERSISTENT_DRAWDOWN states capture "best of both worlds" -- crisis
protection without giving up the golden1-frozen-proxy bull-market upside?

2026-08-01 follow-up to the same day's promotion_utility wiring: a first-pass
OOS check (compare_candidates on the shadow script's four existing windows)
found dynamic_tangency_cvar cleanly beats golden1_frozen_proxy_50_20_30 on
final_value/MDD/Sharpe in all three independent crisis windows (2018, 2020,
2022) but badly fails the final_value floor in the live 2025-2026 bull
window. This script tests whether switching between the two allocations
based on risk_mechanism_classifier's daily state (computed one day before
use, so no lookahead) does better than either pure strategy across all four
windows.

Data-quality caveat (same limitation documented in market_state_2008_proxy_
backtest.py, reused verbatim here): institutional/margin/derivative tables
only have real coverage from ~2020 (institutional_data/margin_data) or ~2025
(short_sale/foreign_shareholding/securities_lending/day_trading) onward --
nowhere near enough for a consistent 2018-2026 panel. `_regime_features` is
therefore called with chip_features=None throughout, pinning chip_score/
derivative_score/total_risk_score at 0 for the WHOLE window (not just 2018).
Combined with execution_regime being hardcoded "golden1" (matching the 2008
proxy script's finding that a2118's real switch rule can never leave golden1
without chip data), classify_market_state can only reach price-driven
buckets: FAST_CRASH fires only via tail_risk_score>=2 or a sharp ma_gap/
momentum break; PERSISTENT_DRAWDOWN can only be built from repeated
bull_pullback_deep days (bear_breakdown/choppy_range_high_risk are
unreachable with total_risk_score pinned at 0). This is a conservative,
price-only proxy for the classifier, not what it would do live with real
chip/derivative data -- report accordingly.

Does not modify market_state.py, risk_mechanism_classifier.py,
daily_signal.py, or any production/report file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _regime_features  # noqa: E402
from group_a_plus.governance.compare import compare_candidates  # noqa: E402
from group_a_plus.integrations.risk_mechanism_classifier import classify_risk_mechanism  # noqa: E402
from group_a_plus.operations.market_state import classify_market_state  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import (  # noqa: E402
    GridSpec,
    _load_close_panel,
    _portfolio_returns,
    _run_dynamic_grid,
    _summarize_returns,
)

PANEL_START = "2016-09-01"
PANEL_END = "2026-07-27"
LOOKBACK = 252
MIN_LOOKBACK = 126
REBALANCE_EVERY = 21
COST_BPS = 10.0
GRID = GridSpec(step=0.05, max_00631l=0.20)
GOLDEN1_WEIGHTS = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}
DEFENSIVE_MECHANISMS = {"FAST_CRASH", "PERSISTENT_DRAWDOWN"}

WINDOWS = {
    "2018_correction": ("2018-01-02", "2018-12-28"),
    "2020_covid": ("2020-01-02", "2020-06-30"),
    "2022_rate_hike": ("2022-01-03", "2022-10-31"),
    "recent_bull_20260727": ("2025-01-02", "2026-07-27"),
}


def _build_mechanism_series(features: pd.DataFrame) -> pd.Series:
    """Walk forward day by day; each day's risk_mechanism uses only strictly
    prior days' market_state buckets (history), matching the real
    daily-pipeline contract in risk_mechanism_classifier.py's docstring."""
    history: list[dict[str, Any]] = []
    mechanisms: dict[pd.Timestamp, str] = {}
    for dt, row in features.iterrows():
        feat = {
            "ma_gap": float(row["ma_gap"]),
            "drawdown": float(row["drawdown"]),
            "exit_momentum_5d": float(row["exit_momentum"]),
            "total_risk_score": int(row["total_risk_score"]),
            "tail_risk_score": int(row["tail_risk_score"]),
        }
        market_state = classify_market_state("golden1", feat)
        risk_mechanism = classify_risk_mechanism(market_state, None, history)
        mechanisms[dt] = risk_mechanism["mechanism"]
        history.append({"date": str(dt.date()), "bucket": market_state["bucket"]})
    return pd.Series(mechanisms).sort_index()


def _build_overlay_return(
    golden1_returns: pd.Series, tangency_gross: pd.Series, mechanism: pd.Series
) -> pd.Series:
    """Day t's allocation is decided by day t-1's mechanism reading (no lookahead)."""
    idx = golden1_returns.index
    prev_mechanism = mechanism.reindex(idx).shift(1)
    use_defensive = prev_mechanism.isin(DEFENSIVE_MECHANISMS)
    overlay = golden1_returns.where(~use_defensive, tangency_gross.reindex(idx))
    return overlay.fillna(golden1_returns).rename("overlay_return")


def _metrics_for_compare(returns: pd.Series) -> dict[str, Any]:
    s = _summarize_returns(returns)
    cum = s.get("cumulative_return") or 0.0
    return {
        "final_value": 100.0 * (1.0 + cum),
        "sharpe_ratio": s.get("sharpe") or 0.0,
        "max_drawdown": s.get("max_drawdown") or 0.0,
        "starr_95": s.get("starr_95"),
        "expected_shortfall_loss_95": s.get("expected_shortfall_loss_95"),
        "rachev_95_95": s.get("rachev_95_95"),
    }


def main() -> None:
    prices = _load_close_panel(DB_PATH, ("0050.TW", "00631L.TW"), PANEL_START, PANEL_END, warmup_days=0)
    returns = prices.pct_change(fill_method=None).dropna(how="any")

    rule = _build_switch_rule()
    features = _regime_features(prices, rule, chip_features=None)
    assert (features["total_risk_score"] == 0).all(), "expected total_risk_score pinned at 0 (see module docstring)"

    mechanism = _build_mechanism_series(features)

    golden1_returns = _portfolio_returns(returns, GOLDEN1_WEIGHTS)
    tangency_gross, _tangency_net, _allocations = _run_dynamic_grid(
        returns,
        objective="tangency_cvar",
        confidence=0.95,
        lookback=LOOKBACK,
        min_lookback=MIN_LOOKBACK,
        rebalance_every=REBALANCE_EVERY,
        cost_bps=COST_BPS,
        grid=GRID,
    )

    overlay_returns = _build_overlay_return(golden1_returns, tangency_gross, mechanism)

    import tempfile

    results: dict[str, Any] = {"windows": {}}
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for label, (start, end) in WINDOWS.items():
            window_slice = slice(pd.Timestamp(start), pd.Timestamp(end))
            g = golden1_returns.loc[window_slice]
            t = tangency_gross.loc[window_slice]
            o = overlay_returns.loc[window_slice]
            m = mechanism.loc[pd.Timestamp(start):pd.Timestamp(end)]

            baseline_path = tmp / f"{label}_baseline.json"
            baseline_path.write_text(json.dumps({"metrics": _metrics_for_compare(g)}), encoding="utf-8")
            candidate_path = tmp / f"{label}_candidates.json"
            candidate_path.write_text(
                json.dumps(
                    {
                        "experiment": label,
                        "rows": [
                            {"variant": "dynamic_tangency_cvar_pure", "override_days": 1, **_metrics_for_compare(t)},
                            {"variant": "risk_mechanism_overlay", "override_days": 1, **_metrics_for_compare(o)},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = compare_candidates(baseline_path, [candidate_path], tail_risk_lambda_starr=1.0, tail_risk_lambda_es=1.0)
            results["windows"][label] = {
                "start": start,
                "end": end,
                "mechanism_day_counts": m.value_counts().to_dict(),
                "baseline_final_value": report["baseline_metrics"]["final_value"],
                "rows": [
                    {
                        "variant": row["variant"],
                        "final_value": row["final_value"],
                        "delta_final": row["delta_final"],
                        "max_drawdown": row["max_drawdown"],
                        "sharpe_ratio": row["sharpe_ratio"],
                        "promotion_utility": row["promotion_utility"],
                        "final_value_floor_pass": row["final_value_floor_pass"],
                        "max_drawdown_non_worse_pass": row["max_drawdown_non_worse_pass"],
                        "sharpe_non_worse_pass": row["sharpe_non_worse_pass"],
                        "formal_upgrade_pass": row["formal_upgrade_pass"],
                    }
                    for row in report["rows"]
                ],
            }

    out_path = PROJECT_ROOT / "results" / "risk_mechanism_regime_overlay_backtest_20260801.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")
    for label, window in results["windows"].items():
        print(f"\n=== {label} ({window['start']} ~ {window['end']}) ===")
        print("  mechanism day counts:", window["mechanism_day_counts"])
        print(f"  baseline (golden1) final_value: {window['baseline_final_value']:.2f}")
        for row in window["rows"]:
            print(
                f"  {row['variant']:28s} final_value={row['final_value']:.2f} "
                f"delta={row['delta_final']:+.2f} mdd={row['max_drawdown']:.4f} "
                f"sharpe={row['sharpe_ratio']:.3f} formal_upgrade={row['formal_upgrade_pass']}"
            )


if __name__ == "__main__":
    main()
