#!/usr/bin/env python3
"""Walk-forward stability check for the 2026-06-19 GARCH-proxy volatility
regime selector/guard (scripts/backtest/backtest_group_a_plus_financial_econometrics.py).

The 06-19 script picks its "best" ratio/percentile/risk-score threshold by
maximizing Sharpe over the *entire* backtest window -- i.e. the parameter
choice itself sees the future. This script instead:

1. Computes the GARCH-proxy features and every grid variant's regime/curve
   once over 2020-01-02 .. latest (causal at the feature level: rolling
   windows only use past data).
2. For a sequence of expanding-window folds, selects the best-Sharpe variant
   using ONLY the train segment (data_start .. train_end), freezes it, and
   evaluates that frozen choice's OOS performance on the following test
   segment.
3. Compares against always-a207, always-ma20, and "pick whichever of
   a207/ma20 had the better train-Sharpe" (a cheaper benchmark for whether
   GARCH-regime routing adds anything beyond picking the better simple rule).

Research-only. Does not modify any production file.
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
    _load_prices,
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
START = "2020-01-02"
END = "2026-07-03"
INITIAL_VALUE = 1_000_000.0

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

FOLDS = [
    ("2020-01-02", "2021-12-31", "2022-01-01", "2022-06-30"),
    ("2020-01-02", "2022-06-30", "2022-07-01", "2022-12-31"),
    ("2020-01-02", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2020-01-02", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2020-01-02", "2024-12-31", "2025-01-01", "2025-12-31"),
    ("2020-01-02", "2025-12-31", "2026-01-01", "2026-07-03"),
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
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }

    prices = _load_prices(_resolve(str(DB_PATH)), list(TICKERS), START, END)
    chip_features = _load_chip_features(_resolve(str(DB_PATH)), prices.index, START, END)

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

    fold_reports = []
    for data_start, train_end, test_start, test_end in FOLDS:
        a207_train_sharpe = _sharpe_on_segment(a207_curve, data_start, train_end)
        ma20_train_sharpe = _sharpe_on_segment(ma20_curve, data_start, train_end)
        static_best_name = "a207" if a207_train_sharpe >= ma20_train_sharpe else "ma20"
        static_best_curve = a207_curve if static_best_name == "a207" else ma20_curve

        best_selector_label = max(
            selector_curves, key=lambda label: _sharpe_on_segment(selector_curves[label], data_start, train_end)
        )
        best_guard_label = max(
            guard_curves, key=lambda label: _sharpe_on_segment(guard_curves[label], data_start, train_end)
        )

        candidates = {
            "a207": a207_curve,
            "ma20": ma20_curve,
            "static_best_frozen": static_best_curve,
            "garch_selector_frozen": selector_curves[best_selector_label],
            "garch_guard_frozen": guard_curves[best_guard_label],
        }
        test_metrics = {name: _fold_metrics(curve, test_start, test_end) for name, curve in candidates.items()}
        oracle_name = max(("a207", "ma20"), key=lambda name: test_metrics[name]["sharpe_ratio"])

        fold_reports.append(
            {
                "train_window": [data_start, train_end],
                "test_window": [test_start, test_end],
                "static_best_frozen_choice": static_best_name,
                "garch_selector_frozen_choice": best_selector_label,
                "garch_guard_frozen_choice": best_guard_label,
                "test_sharpe": {name: round(m["sharpe_ratio"], 4) for name, m in test_metrics.items()},
                "test_mdd": {name: round(m["max_drawdown"], 4) for name, m in test_metrics.items()},
                "test_final_value": {name: round(m["final_value"], 0) for name, m in test_metrics.items()},
                "oracle_static_choice_in_hindsight": oracle_name,
                "garch_selector_beats_static_best": bool(
                    test_metrics["garch_selector_frozen"]["sharpe_ratio"] > test_metrics["static_best_frozen"]["sharpe_ratio"]
                ),
                "garch_guard_beats_static_best": bool(
                    test_metrics["garch_guard_frozen"]["sharpe_ratio"] > test_metrics["static_best_frozen"]["sharpe_ratio"]
                ),
            }
        )

    selector_win_count = sum(1 for f in fold_reports if f["garch_selector_beats_static_best"])
    guard_win_count = sum(1 for f in fold_reports if f["garch_guard_beats_static_best"])
    chosen_selector_labels = sorted({f["garch_selector_frozen_choice"] for f in fold_reports})
    chosen_guard_labels = sorted({f["garch_guard_frozen_choice"] for f in fold_reports})

    report = {
        "experiment": "garch_proxy_specialist_routing_walkforward",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method_note": (
            "Expanding-window walk-forward: parameter grid selection uses only "
            "train-segment Sharpe; evaluation is out-of-sample on the following "
            "fold. Tests whether GARCH-proxy volatility-regime routing beats "
            "simply freezing whichever static rule (a207 vs ma20) had the "
            "better train-window Sharpe."
        ),
        "window": {"start": START, "end": END},
        "folds": fold_reports,
        "summary": {
            "fold_count": len(fold_reports),
            "garch_selector_beats_static_best_count": selector_win_count,
            "garch_guard_beats_static_best_count": guard_win_count,
            "distinct_selector_params_chosen_across_folds": chosen_selector_labels,
            "distinct_guard_params_chosen_across_folds": chosen_guard_labels,
        },
    }

    out_path = PROJECT_ROOT / "results" / "garch_specialist_routing_walkforward_20260705.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {out_path}")
    print(f"Folds: {len(fold_reports)}")
    print(f"garch_selector beats static_best_frozen OOS: {selector_win_count}/{len(fold_reports)} folds")
    print(f"garch_guard beats static_best_frozen OOS: {guard_win_count}/{len(fold_reports)} folds")
    print(f"Distinct selector params chosen across folds: {chosen_selector_labels}")
    print(f"Distinct guard params chosen across folds: {chosen_guard_labels}")
    print()
    for f in fold_reports:
        print(
            f"{f['test_window'][0]}..{f['test_window'][1]}: "
            f"static_best={f['static_best_frozen_choice']}(oracle_would_pick={f['oracle_static_choice_in_hindsight']}) "
            f"sharpe[a207={f['test_sharpe']['a207']:.3f} ma20={f['test_sharpe']['ma20']:.3f} "
            f"static_best_frozen={f['test_sharpe']['static_best_frozen']:.3f} "
            f"garch_selector={f['test_sharpe']['garch_selector_frozen']:.3f}({f['garch_selector_frozen_choice']}) "
            f"garch_guard={f['test_sharpe']['garch_guard_frozen']:.3f}({f['garch_guard_frozen_choice']})]"
        )


if __name__ == "__main__":
    main()
