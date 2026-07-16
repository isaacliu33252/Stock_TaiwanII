#!/usr/bin/env python3
"""Add a real-crash 2008 fold to the GARCH-proxy specialist-routing walk-forward test.

Companion to scripts/misc/garch_specialist_routing_walkforward_20260705.py (which
covered 2022-2026 on real ETF data) and
scripts/misc/prepare_2008_twii_proxy_data_20260705.py (which built the TWII-proxy
2003-2010 dataset). Same expanding-window methodology: pick the best-Sharpe grid
variant using ONLY the train segment, freeze it, evaluate out-of-sample on the
test segment. Train = 2003-01-02..2007-06-30 (pre-crisis calm/bull years -- what
you would actually have had to select parameters on in real time). Test =
2007-07-01..2009-12-31 (the crash itself plus the start of recovery).

Caveat found while preparing the 2008 data and reproduced here: a207's entry
gate requires total_risk_score>=6, which depends on chip/derivative sources
that only exist in stock_data.db from 2020 onward. On the 2008 proxy dataset
total_risk_score never reaches 6, so a207 never leaves golden1 -- it is
included as a reference point ("what a chip-gated rule looks like with zero
chip signal available"), not as a claim about how the real a207 rule would
have performed in 2008 with real chip data (which does not exist locally).

Research-only. Does not touch any production file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    _load,
    _load_policy_signal,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics, _simulate_regime_curve, _switch_returns
from scripts.backtest.backtest_group_a_plus_financial_econometrics import (
    A207_RULE,
    MA20_RULE,
    _garch_guard_regime,
    _garch_selector_regime,
)
from scripts.misc.prepare_2008_twii_proxy_data_20260705 import build_2008_proxy_prices

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
DATA_START = "2003-01-02"
DATA_END = "2010-12-31"
TRAIN_END = "2007-06-30"
TEST_START = "2007-07-01"
TEST_END = "2009-12-31"

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

    prices = build_2008_proxy_prices(DATA_START, DATA_END)
    from backtest_group_a_plus_switch_policy import _load_chip_features

    chip_features = _load_chip_features(_resolve(str(DB_PATH)), prices.index, DATA_START, DATA_END)

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
            test_metrics["garch_selector_frozen"]["sharpe_ratio"] > test_metrics["static_best_frozen"]["sharpe_ratio"]
        ),
        "garch_guard_beats_static_best": bool(
            test_metrics["garch_guard_frozen"]["sharpe_ratio"] > test_metrics["static_best_frozen"]["sharpe_ratio"]
        ),
        "caveat": (
            "a207 never leaves golden1 on this dataset (chip/derivative sources start "
            "2020+ in stock_data.db, so total_risk_score never reaches a207's "
            "require_total_risk_score=6 gate). a207 here reflects 'chip-gated rule with "
            "zero chip signal available', not a claim about real 2008 a207 performance."
        ),
    }

    report = {
        "experiment": "garch_proxy_specialist_routing_2008_fold",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "TWII proxy dataset from scripts/misc/prepare_2008_twii_proxy_data_20260705.py",
        "fold": fold_report,
    }
    out_path = PROJECT_ROOT / "results" / "garch_specialist_routing_2008_fold_20260705.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {out_path}")
    print(f"Train: {DATA_START}..{TRAIN_END}  (a207_sharpe={a207_train_sharpe:.3f}, ma20_sharpe={ma20_train_sharpe:.3f})")
    print(f"static_best_frozen choice: {static_best_name}")
    print(f"garch_selector_frozen choice: {best_selector_label}")
    print(f"garch_guard_frozen choice: {best_guard_label}")
    print(f"Test: {TEST_START}..{TEST_END}")
    for name, m in test_metrics.items():
        print(
            f"  {name}: sharpe={m['sharpe_ratio']:.3f}, mdd={m['max_drawdown']:.2%}, "
            f"final={m['final_value']:,.0f}, total_return={m['total_return']:.2%}"
        )
    print(f"garch_selector beats static_best_frozen OOS: {fold_report['garch_selector_beats_static_best']}")
    print(f"garch_guard beats static_best_frozen OOS: {fold_report['garch_guard_beats_static_best']}")
    print(f"oracle (in-hindsight best of a207/ma20): {oracle_name}")


if __name__ == "__main__":
    main()
