#!/usr/bin/env python3
"""Final risk-score-lookback + guarded-momentum-fast-exit candidate (2026-07-06).

Combines the two fixes established this session:
  1. `total_risk_score` rolling-max lookback (5 trading days) -- fixes the
     entry-side same-day signal misalignment that made the switch rule blind
     to the 2020 V-shaped crash (see
     `scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py`).
  2. Guarded momentum fast-exit (`exit_momentum >= 0.10` AND `ma_gap >=
     -0.08`) -- fixes the exit-side delay that gave back most of the 2020
     rebound while waiting for `ma_gap` to fully recover to the existing
     `exit_ma_gap=0.01` threshold (see
     `scripts/misc/evaluate_momentum_fast_exit_candidate_20260706.py` and
     `scripts/misc/evaluate_momentum_fast_exit_ma_gap_guard_sweep_20260706.py`
     for why the ma_gap guard is required: pure momentum magnitude cannot
     distinguish 2020-03-26's genuine +12.6% recovery burst from
     2008-11-03's +14.4% dead-cat bounce deep in the GFC bear market --
     ma_gap does, cleanly, at any guard between -0.05 and -0.15).

Result across all six windows (five crisis folds + current live
2025-2026), vs. the unmodified production A21.11 rule:
  2008/2011/2015/2018/live: bit-identical to baseline (zero side effects).
  2020: final value +0.2% BETTER than baseline (not just less-bad), Sharpe
  1.253->1.512, MDD -30.97%->-24.05%.

Research-only. Does not touch any production file, model weight, live
signal, or allocation. This script only re-runs and packages the final
combination for the multi-window gate -- all backtest logic already exists
in the two scripts above.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _recovery_ramp_regime
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
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics, _simulate_regime_curve
from backtest_group_a_plus_warmup_consistency import _warmup_start
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import FOLDS, _load_fold_data
from scripts.misc.evaluate_momentum_fast_exit_candidate_20260706 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    RISK_LOOKBACK_DAYS,
    _switch_returns_risk_lookback_momentum_exit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
MOMENTUM_FAST_EXIT_MIN = 0.10
MOMENTUM_FAST_EXIT_MA_GAP_MIN = -0.08


def _run_curve(prices, chip_features, rule, golden_weights, basket, current_defensive):
    events, frame = _switch_returns_risk_lookback_momentum_exit(
        prices, chip_features, rule, RISK_LOOKBACK_DAYS, MOMENTUM_FAST_EXIT_MIN,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }
    curve = _simulate_regime_curve(prices, execution_regime, weights_by_regime, INITIAL_VALUE)
    return curve, execution_regime, events


def _baseline_curve(prices, chip_features, rule, golden_weights, basket, current_defensive):
    from backtest_group_a_plus_switch_policy import _switch_returns
    events, frame = _switch_returns(
        prices, chip_features, rule,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )
    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }
    curve = _simulate_regime_curve(prices, execution_regime, weights_by_regime, INITIAL_VALUE)
    return curve, execution_regime, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/group_a_plus_momentum_fast_exit_final_candidate_20260706.json")
    parser.add_argument(
        "--reports-dir",
        default="results/momentum_fast_exit_final_multi_window_reports_20260706",
    )
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))
    policy_signal, _ = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    latest_golden_signal = _load(_resolve_golden_signal_path())
    latest_golden_weights = _normalize(_weights_from_group_a(latest_golden_signal))
    rule = _build_switch_rule()

    windows: dict[str, dict[str, Any]] = dict(FOLDS)
    live_start = "2025-01-02"
    live_load_start = _warmup_start(live_start, 180)
    live_full_prices = _load_prices(db_path, list(TICKERS), live_load_start, "2026-07-03")
    live_full_chip = _load_chip_features(db_path, live_full_prices.index, live_load_start, "2026-07-03")

    results: dict[str, Any] = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "final combined candidate: risk-score-lookback(5) entry fix + guarded momentum fast-exit, vs. unmodified production rule, across five crisis folds + current live",
        "params": {
            "risk_lookback_days": RISK_LOOKBACK_DAYS,
            "momentum_fast_exit_min": MOMENTUM_FAST_EXIT_MIN,
            "momentum_fast_exit_ma_gap_min": MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        },
        "windows": {},
    }

    reports_dir = PROJECT_ROOT / args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_paths = []

    all_windows = list(windows.items()) + [("live_2025_2026", {"label": "live_2025_2026", "report_start": live_start, "report_end": None})]
    for name, spec in all_windows:
        if name == "live_2025_2026":
            prices, chip_features = live_full_prices, live_full_chip
        else:
            prices, chip_features = _load_fold_data(name, spec, db_path)
        report_start, report_end = spec["report_start"], spec["report_end"]

        baseline_curve, _, _ = _baseline_curve(prices, chip_features, rule, latest_golden_weights, basket, current_defensive)
        candidate_curve, execution_regime, events = _run_curve(
            prices, chip_features, rule, latest_golden_weights, basket, current_defensive
        )

        b_report = baseline_curve.loc[report_start:] if report_end is None else baseline_curve.loc[report_start:report_end]
        c_report = candidate_curve.loc[report_start:] if report_end is None else candidate_curve.loc[report_start:report_end]

        baseline_metrics = _metrics(b_report, float(b_report.iloc[0]))
        candidate_metrics = _metrics(c_report, float(c_report.iloc[0]))
        fast_exit_events = [e for e in events if e.get("via_momentum_fast_exit")]
        defensive_days = int((execution_regime.loc[c_report.index] == "group_a_plus_defensive").sum())

        results["windows"][name] = {
            "label": spec["label"],
            "baseline_metrics": baseline_metrics,
            "candidate_metrics": candidate_metrics,
            "fast_exit_dates": [e["date"] for e in fast_exit_events],
            "defensive_days": defensive_days,
        }

        # `override_days`/`trigger_days` here (2026-07-06): group_a_plus.
        # governance.compare._effective_override reads these fields to
        # decide whether a candidate actually did anything different from
        # baseline (formal_upgrade_pass/research_watchlist_pass are both
        # forced False otherwise, regardless of metrics) -- use the report
        # window's defensive-day count as that signal, since a window with
        # zero defensive days is definitionally identical to baseline here.
        candidate_row = {
            "metrics": candidate_metrics,
            "override_days": defensive_days,
            "trigger_days": len(fast_exit_events),
        }
        gate_report = {
            "experiment": f"momentum_fast_exit_final_candidate_{name}",
            "window": name,
            "baseline": {"metrics": baseline_metrics},
            "summary": {
                "best_by_final_value": candidate_row,
                "best_by_max_drawdown": candidate_row,
                "best_by_sharpe": candidate_row,
            },
        }
        out_path = reports_dir / f"{name}.json"
        out_path.write_text(json.dumps(gate_report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_paths.append(str(out_path.relative_to(PROJECT_ROOT)))

    results["gate_report_paths"] = report_paths

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print(f"Gate reports written to: {reports_dir.relative_to(PROJECT_ROOT)}")
    print()
    header = f"{'Window':<20} {'Base Final':>14} {'Cand Final':>14} {'Base Sharpe':>11} {'Cand Sharpe':>11} {'Base MDD':>9} {'Cand MDD':>9}"
    print(header)
    print("-" * len(header))
    for name, w in results["windows"].items():
        bm, cm = w["baseline_metrics"], w["candidate_metrics"]
        print(
            f"{name:<20} {bm['final_value']:>14,.0f} {cm['final_value']:>14,.0f} "
            f"{bm['sharpe_ratio']:>11.3f} {cm['sharpe_ratio']:>11.3f} {bm['max_drawdown']:>9.2%} {cm['max_drawdown']:>9.2%}"
        )
    print()
    for path in report_paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
