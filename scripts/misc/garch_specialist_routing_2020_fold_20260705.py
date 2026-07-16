#!/usr/bin/env python3
"""Third independent real-crisis fold: 2020 COVID crash (V-shaped, fast).

Companion to the 2008 (prolonged crash) and 2011 (grinding decline) folds.
Unlike those two, this fold needs NO synthetic TWII proxy at all: 0050.TW/
00631L.TW/00632R.TW have continuous real OHLCV from 2015-01-05 onward (the
2011-2014 hole this session filled with a TWII proxy sits entirely before
this fold's train window), and institutional_data/margin_data (the two chip
tables _load_chip_features can actually use pre-2020... note: most other
optional chip tables -- foreign_shareholding_data, short_sale_balance_data,
securities_lending_data, day_trading_data, derivative_institutional_data --
only start 2025-01-02, so total_risk_score is still chip-thin for 2020, just
less thin than the 2008/2011 folds) start exactly 2020-01-02, i.e. the first
day of this fold's test window.

00679B.TWO (the fourth GroupA+ ticker) only has real data from 2020-01-02
onward -- exactly the test window start. For the pre-2020 train window it is
back-filled flat at its first real price (2020-01-02 close); its weight in
both golden1 and defensive books is ~0-0.05%, so a flat/non-moving proxy
price for that sliver of allocation has negligible effect on train-period
Sharpe (the only thing the train window is used for: picking a207 vs ma20 /
the grid-search variant).

Train = 2015-01-05..2019-12-31 (real data). Test = 2020-01-01..2020-12-31
(the Feb-Mar 2020 crash plus the fast V-shaped recovery through year-end).

Research-only. Does not touch any production file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from scripts.backtest.backtest_group_a_plus_financial_econometrics import (
    A207_RULE,
    MA20_RULE,
    _garch_guard_regime,
    _garch_selector_regime,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
DATA_START = "2015-01-05"
DATA_END = "2020-12-31"
TRAIN_END = "2019-12-31"
TEST_START = "2020-01-01"
TEST_END = "2020-12-31"

SELECTOR_GRID = [
    (ratio, percentile, negative)
    for ratio in (1.05, 1.10, 1.20, 1.30)
    for percentile in (0.70, 0.80, 0.90)
    for negative in (True, False)
]
GUARD_GRID = [
    (ratio, percentile, risk)
    for ratio in (1.05, 1.10, 1.20)
    for percentile in (0.70, 0.80, 0.90)
    for risk in (0, 4, 6)
]


def _load_real_prices_with_00679b_backfill(db_path: Path, start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(TICKERS))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*TICKERS, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {TICKERS} between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    # 00679B.TWO only has real prices from 2020-01-02 onward; back-fill flat
    # for the pre-2020 train window (see module docstring for why this is a
    # negligible approximation, not a load-bearing one).
    prices["00679B.TWO"] = prices["00679B.TWO"].bfill()
    return prices.dropna(subset=list(TICKERS))


def _sharpe_on_segment(curve: pd.Series, start: str, end: str) -> float:
    segment = curve.loc[start:end]
    if len(segment) < 5:
        return float("-inf")
    return float(_metrics(segment, float(segment.iloc[0]))["sharpe_ratio"])


def _fold_metrics(curve: pd.Series, start: str, end: str) -> dict[str, Any]:
    segment = curve.loc[start:end]
    return _metrics(segment, float(segment.iloc[0]))


def main() -> None:
    policy_signal, _ = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    golden_signal = _load(_resolve(str(DEFAULT_GOLDEN_SIGNAL)))
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}

    db_path = _resolve(str(DB_PATH))
    prices = _load_real_prices_with_00679b_backfill(db_path, DATA_START, DATA_END)
    chip_features = _load_chip_features(db_path, prices.index, DATA_START, DATA_END)

    a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
    a207_curve = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, INITIAL_VALUE)
    ma20_curve = _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, INITIAL_VALUE)

    selector_curves: dict[str, pd.Series] = {}
    for ratio, percentile, negative in SELECTOR_GRID:
        label = f"sel_r{int(ratio*100):03d}_p{int(percentile*100):02d}_{'neg5d' if negative else 'any'}"
        frame = _garch_selector_regime(
            prices, chip_features, a207_frame["regime"], ma20_frame["regime"], ratio, percentile, negative
        )
        selector_curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, INITIAL_VALUE)

    guard_curves: dict[str, pd.Series] = {}
    for ratio, percentile, risk in GUARD_GRID:
        label = f"grd_r{int(ratio*100):03d}_p{int(percentile*100):02d}_risk{risk}"
        _events, frame = _garch_guard_regime(
            prices, chip_features, a207_frame["regime"], ratio, percentile,
            min_hold_days=5, exit_ratio=1.00, require_total_risk_score=risk,
        )
        guard_curves[label] = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, INITIAL_VALUE)

    a207_train_sharpe = _sharpe_on_segment(a207_curve, DATA_START, TRAIN_END)
    ma20_train_sharpe = _sharpe_on_segment(ma20_curve, DATA_START, TRAIN_END)
    static_best_name = "a207" if a207_train_sharpe >= ma20_train_sharpe else "ma20"
    static_best_curve = a207_curve if static_best_name == "a207" else ma20_curve

    best_selector_label = max(
        selector_curves, key=lambda label: _sharpe_on_segment(selector_curves[label], DATA_START, TRAIN_END)
    )
    best_guard_label = max(
        guard_curves, key=lambda label: _sharpe_on_segment(guard_curves[label], DATA_START, TRAIN_END)
    )

    candidates = {
        "a207": a207_curve,
        "ma20": ma20_curve,
        "static_best_frozen": static_best_curve,
        "garch_selector_frozen": selector_curves[best_selector_label],
        "garch_guard_frozen": guard_curves[best_guard_label],
    }
    test_metrics = {name: _fold_metrics(curve, TEST_START, TEST_END) for name, curve in candidates.items()}
    oracle_name = max(("a207", "ma20"), key=lambda name: test_metrics[name]["sharpe_ratio"])

    static_best_test_sharpe = test_metrics["static_best_frozen"]["sharpe_ratio"]
    selector_test_sharpes = {
        label: _sharpe_on_segment(curve, TEST_START, TEST_END) for label, curve in selector_curves.items()
    }
    guard_test_sharpes = {
        label: _sharpe_on_segment(curve, TEST_START, TEST_END) for label, curve in guard_curves.items()
    }
    selector_wins_vs_static_best = sum(1 for s in selector_test_sharpes.values() if s > static_best_test_sharpe)
    guard_wins_vs_static_best = sum(1 for s in guard_test_sharpes.values() if s > static_best_test_sharpe)

    fold_report = {
        "train_window": [DATA_START, TRAIN_END],
        "test_window": [TEST_START, TEST_END],
        "a207_train_sharpe": round(a207_train_sharpe, 4),
        "ma20_train_sharpe": round(ma20_train_sharpe, 4),
        "static_best_frozen_choice": static_best_name,
        "garch_selector_frozen_choice": best_selector_label,
        "garch_guard_frozen_choice": best_guard_label,
        "test_sharpe": {name: round(m["sharpe_ratio"], 4) for name, m in test_metrics.items()},
        "test_mdd": {name: round(m["max_drawdown"], 4) for name, m in test_metrics.items()},
        "test_final_value": {name: round(m["final_value"], 0) for name, m in test_metrics.items()},
        "a207_switch_event_count_full_window": len(a207_events),
        "ma20_switch_event_count_full_window": len(ma20_events),
        "oracle_static_choice_in_hindsight": oracle_name,
        "garch_selector_beats_static_best": bool(
            test_metrics["garch_selector_frozen"]["sharpe_ratio"] > static_best_test_sharpe
        ),
        "garch_guard_beats_static_best": bool(
            test_metrics["garch_guard_frozen"]["sharpe_ratio"] > static_best_test_sharpe
        ),
        "robustness_check_full_grid_oos": {
            "method": "evaluate every grid variant (not just the train-selected best) directly on the test segment",
            "static_best_frozen_test_sharpe": round(static_best_test_sharpe, 4),
            "selector_variants_beating_static_best": f"{selector_wins_vs_static_best}/{len(selector_curves)}",
            "selector_test_sharpe_range": [round(min(selector_test_sharpes.values()), 4), round(max(selector_test_sharpes.values()), 4)],
            "guard_variants_beating_static_best": f"{guard_wins_vs_static_best}/{len(guard_curves)}",
            "guard_test_sharpe_range": [round(min(guard_test_sharpes.values()), 4), round(max(guard_test_sharpes.values()), 4)],
        },
        "caveat": (
            "Unlike 2008/2011, this fold uses 100% real OHLCV (no TWII proxy). "
            "total_risk_score is still chip-thin for 2020 (foreign_shareholding/"
            "short_sale/securities_lending/day_trading/derivative_institutional "
            "tables only start 2025-01-02), so a207 may still rarely fire for "
            "reasons other than pure data absence this time."
        ),
    }

    report = {
        "experiment": "garch_proxy_specialist_routing_2020_fold",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "real stock_data.db OHLCV (no synthetic proxy)",
        "fold": fold_report,
    }
    out_path = PROJECT_ROOT / "results" / "garch_specialist_routing_2020_fold_20260705.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {out_path}")
    print(f"Train: {DATA_START}..{TRAIN_END}  (a207_sharpe={a207_train_sharpe:.3f}, ma20_sharpe={ma20_train_sharpe:.3f})")
    print(f"static_best_frozen choice: {static_best_name}")
    print(f"garch_selector_frozen choice: {best_selector_label}")
    print(f"garch_guard_frozen choice: {best_guard_label}")
    print(f"a207 switch events (full window): {len(a207_events)}, ma20 switch events: {len(ma20_events)}")
    print(f"Test: {TEST_START}..{TEST_END}")
    for name, m in test_metrics.items():
        print(
            f"  {name}: sharpe={m['sharpe_ratio']:.3f}, mdd={m['max_drawdown']:.2%}, "
            f"final={m['final_value']:,.0f}, total_return={m['total_return']:.2%}"
        )
    print(f"garch_selector beats static_best_frozen OOS: {fold_report['garch_selector_beats_static_best']}")
    print(f"garch_guard beats static_best_frozen OOS: {fold_report['garch_guard_beats_static_best']}")
    print(f"oracle (in-hindsight best of a207/ma20): {oracle_name}")
    print()
    print("Robustness check (full grid, evaluated directly OOS):")
    print(f"  static_best_frozen test sharpe (benchmark): {static_best_test_sharpe:.3f}")
    print(f"  selector variants beating static_best: {selector_wins_vs_static_best}/{len(selector_curves)} (range {min(selector_test_sharpes.values()):.3f}..{max(selector_test_sharpes.values()):.3f})")
    print(f"  guard variants beating static_best: {guard_wins_vs_static_best}/{len(guard_curves)} (range {min(guard_test_sharpes.values()):.3f}..{max(guard_test_sharpes.values()):.3f})")


if __name__ == "__main__":
    main()
