#!/usr/bin/env python3
"""A21.20 T+1 execution-delay robustness audit -- the one item on the
promotion scorecard's blocker list ("requires_t_plus_1_execution_alignment_
audit") that has never actually been run.

Research-only. Reuses every existing building block UNMODIFIED: the same 7
windows and same tuned-candidate thresholds as
evaluate_a2120_ce20_variant_a2119_overlap.py's WINDOWS/PREFERRED_THRESHOLDS
(imported, not duplicated), the same simulate_no_add_guard/_simulate_baseline
cost/regime-application engine as
evaluate_00631l_compounding_regime_no_add_shadow.py (imported, not
duplicated). The only new logic is the delay itself: regimes.shift(1) before
simulation, so the regime driving day t's add-speed decision is whatever was
classified as of day t-1 -- i.e. what a real operator could actually react to
the next trading day, instead of the same-day classification every prior
A21.20 backtest (7-window, cost-stress, rolling-window) implicitly assumed.

Does not touch target_weights, execution_plan.json, or any production file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.integrations.leveraged_compounding_regime import (
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import (
    _metric_delta,
    _simulate_baseline,
    _simulate_speed_baseline,
    simulate_no_add_guard,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve_end_date, _targets_from_report
from scripts.evaluate.evaluate_a2120_ce20_variant_a2119_overlap import PREFERRED_THRESHOLDS, WINDOWS

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_compounding_t_plus_1_execution_delay_shadow.json"
CANDIDATE = {
    "name": "score3_ar0_persist50_rev50__base40_mr0_trend100",
    "baseline_add_fraction": 0.40,
    "mean_reversion_add_fraction": 0.00,
    "trend_persistent_add_fraction": 1.00,
}


def evaluate_window_with_delay(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    db_path: Path,
    initial_value: float,
    delay_days: int,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    prices = _load_prices(db_path, list(TICKERS), start, resolved_end).reindex(frame.index).dropna()
    target_weights = _targets_from_report(frame.reindex(prices.index), report)
    features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
    classified = classify_compounding_regime(features, thresholds=PREFERRED_THRESHOLDS)
    regimes_same_day = classified["compounding_regime"].reindex(prices.index)

    # The delay: day t's add-speed decision uses whatever regime was
    # classified as of day t-delay_days, not today's own classification.
    # Forward-fills the pre-window gap with the first available regime
    # (matches this project's existing _delayed_regime convention in
    # backtest_group_a_plus_defensive_basket.py).
    regimes_delayed = regimes_same_day.shift(delay_days)
    if len(regimes_delayed) and regimes_delayed.iloc[:delay_days].isna().all():
        regimes_delayed.iloc[:delay_days] = regimes_same_day.iloc[0]

    baseline = _simulate_speed_baseline(
        prices, target_weights, initial_value, float(CANDIDATE["baseline_add_fraction"]), 0.0,
    )
    same_day = simulate_no_add_guard(
        prices=prices, target_weights=target_weights, regimes=regimes_same_day,
        initial_value=initial_value,
        baseline_add_fraction=float(CANDIDATE["baseline_add_fraction"]),
        mean_reversion_add_fraction=float(CANDIDATE["mean_reversion_add_fraction"]),
        trend_persistent_add_fraction=float(CANDIDATE["trend_persistent_add_fraction"]),
    )
    delayed = simulate_no_add_guard(
        prices=prices, target_weights=target_weights, regimes=regimes_delayed,
        initial_value=initial_value,
        baseline_add_fraction=float(CANDIDATE["baseline_add_fraction"]),
        mean_reversion_add_fraction=float(CANDIDATE["mean_reversion_add_fraction"]),
        trend_persistent_add_fraction=float(CANDIDATE["trend_persistent_add_fraction"]),
    )
    return {
        "label": label,
        "start": start,
        "end": resolved_end,
        "same_day_delta_vs_baseline": _metric_delta(same_day, baseline),
        "delayed_delta_vs_baseline": _metric_delta(delayed, baseline),
        "same_day_blocked_days": same_day["blocked_days"],
        "delayed_blocked_days": delayed["blocked_days"],
        "delay_days": delay_days,
    }


def build_report(delay_days: int, db_path: Path, initial_value: float) -> dict[str, Any]:
    windows = []
    for label, start, end, panel in WINDOWS:
        print(f"Evaluating {label} (delay={delay_days}d): {start}..{end}")
        windows.append(
            evaluate_window_with_delay(
                label=label, start=start, end=end, panel=panel,
                db_path=db_path, initial_value=initial_value, delay_days=delay_days,
            )
        )

    same_day_sum = float(sum(w["same_day_delta_vs_baseline"]["final_value"] for w in windows))
    delayed_sum = float(sum(w["delayed_delta_vs_baseline"]["final_value"] for w in windows))
    same_day_positive = int(sum(w["same_day_delta_vs_baseline"]["final_value"] > 0.0 for w in windows))
    delayed_positive = int(sum(w["delayed_delta_vs_baseline"]["final_value"] > 0.0 for w in windows))

    return {
        "schema_version": 1,
        "experiment": "00631l_compounding_t_plus_1_execution_delay_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "purpose": (
            "Resolves the a2120_letf_compounding_shadow_scorecard's "
            "'requires_t_plus_1_execution_alignment_audit' promotion blocker: "
            "does the tuned candidate's positive same-day-execution backtest "
            "survive a realistic 1-trading-day execution lag?"
        ),
        "candidate": CANDIDATE,
        "thresholds": PREFERRED_THRESHOLDS.__dict__,
        "delay_days_tested": delay_days,
        "windows": windows,
        "totals": {
            "same_day_delta_final_value_sum": same_day_sum,
            "delayed_delta_final_value_sum": delayed_sum,
            "same_day_positive_windows": same_day_positive,
            "delayed_positive_windows": delayed_positive,
            "window_count": len(windows),
            "degradation_from_delay": same_day_sum - delayed_sum,
            "delayed_still_positive_overall": delayed_sum > 0.0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--delay-days", type=int, default=1)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(int(args.delay_days), Path(args.db), float(args.initial_value))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== T+{args.delay_days} execution delay audit ===")
    for w in report["windows"]:
        sd = w["same_day_delta_vs_baseline"]["final_value"]
        dl = w["delayed_delta_vs_baseline"]["final_value"]
        print(f"  {w['label']}: same_day={sd:+,.0f}  delayed={dl:+,.0f}  degradation={sd - dl:+,.0f}")
    t = report["totals"]
    print(
        f"\n  same_day_sum={t['same_day_delta_final_value_sum']:+,.0f} "
        f"({t['same_day_positive_windows']}/{t['window_count']} windows positive)"
    )
    print(
        f"  delayed_sum ={t['delayed_delta_final_value_sum']:+,.0f} "
        f"({t['delayed_positive_windows']}/{t['window_count']} windows positive)"
    )
    print(f"  delayed_still_positive_overall={t['delayed_still_positive_overall']}")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
