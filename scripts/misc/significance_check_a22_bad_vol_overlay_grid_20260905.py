#!/usr/bin/env python3
"""Read-only research: retroactively apply the significance-testing tools in
group_a_plus/governance/significance.py -- including the 2026-09-04 addition
bonferroni_grid_significance() -- to the ONE candidate-config search in this
repo's history that was later independently proven to be overfit by real
out-of-sample testing: the A22_bad_vol_overlay champion (see project memory
project_00631l_downside_risk_forecast_20260710.md, phases 8-16).

bonferroni_grid_significance() was added after desk-reviewing arXiv:2608.08405
("Robustness or Crowding") -- see project memory
project_2608_08405_capacity_experiment_design_desk_review_20260904 -- whose
main capacity-experiment framework does not apply to GroupA+, but whose
Prop 3.12/Table 8 (a bracket built from the best-looking member of an
adaptively searched grid covers the truth far below nominal rate) is a
general statistical point worth applying to GroupA+'s own threshold/parameter
searches.

That memory record already established the ground truth the hard way: the
champion config (good_drawdown_min=-0.06, bad_drawdown_max=-0.08,
neutral_cap=0.15 (no-op vs golden1's ~10.9% baseline 00631L weight),
bad_cap=bad_no_vol_cap=0.0, bad_persistence_days=8), selected via 6+ rounds of
coordinate descent on 4 fixed windows (covid_2020/inflation_2022/
live_2024_2026/active_2025_2026), reached sum Sharpe +0.045 in-sample -- but
on the 2017/2018/2019 out-of-sample panel (never used for tuning), it LOST to
baseline: 3-year aggregate delta Sharpe -0.058.

The question this script asks: would bonferroni_grid_significance(), applied
to the IN-SAMPLE per-window comparison alone (no OOS data needed), already
have flagged the champion's apparent edge as not surviving correction for the
size of the search grid that was actually run -- i.e. would this tool have
given an early warning before the (data-gap-blocked, expensive) OOS
validation was ever attempted?

candidate_grid_size is counted directly from the actual result files this
search line left in results/group_a_plus_a22_bad_vol_overlay_*.json: one file
per evaluated configuration, excluding the "latest" pointer and the
"a22_champion_*" post-hoc confirmation/reproduction runs (those re-evaluate
the SAME already-selected champion, not a new candidate). That count is 32;
this script uses 33 to also credit the implicit round-0 default-parameter run
that produced no separate result file. This is a reconstruction after the
fact, since the grid was never pre-registered -- used here as the best
available honest count of "how wide was the search", not a rigorous
pre-registered bound, and if anything an undercount (each coordinate-descent
round's rejected intermediate values beyond what got saved to results/ are
not all recoverable).

2026-09-05 addition: the per-window Bonferroni checks below test 4 separate
hypotheses, each corrected for the full 33-candidate grid. But the actual
historical selection criterion that produced the champion was the SUM of
Sharpe deltas across all 4 windows -- a single joint statistic, not 4
independent ones. A Stouffer combined-z test across the 4 per-window
z-statistics is a more faithful reconstruction of "would the actual
selection criterion have survived correction" than 4 marginal per-window
tests -- and it turns out to matter here: the 4 windows' effects (2
negative, 2 positive, similar magnitude) largely cancel, giving a combined
z close to 0 (p=0.94), a materially stronger null result than any single
per-window p-value on its own already suggested.

Does not modify any production file, signal, or report.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices  # noqa: E402
from group_a_plus.governance.significance import (  # noqa: E402
    bonferroni_grid_significance,
    jobson_korkie_memmel_test,
)
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_a22_bad_vol_overlay import (  # noqa: E402
    DEFAULT_WINDOWS,
    _classify_trend,
    _require_bad_persistence,
    _resolve_end_date,
    _simulate_a22_curve,
    _vol_high_series,
)

CANDIDATE_GRID_SIZE = 33  # see module docstring: 32 result files + 1 implicit round-0 default run

CHAMPION_PARAMS = dict(
    good_ma_gap_min=0.02,
    good_drawdown_min=-0.06,
    bad_ma_gap_max=-0.02,
    bad_drawdown_max=-0.08,
    neutral_cap=0.15,
    bad_cap=0.0,
    bad_no_vol_cap=0.0,
    bad_persistence_days=8,
)


def main() -> None:
    db_path = Path(DB_PATH)
    overall_end = _resolve_end_date(db_path, "latest")
    feature_start = "2016-01-04"
    initial_value = 1_000_000.0
    commission_rate = 0.001425
    slippage_rate = 0.0005
    equity_etf_sell_tax = 0.001

    prices_0050 = _load_prices(db_path, ["0050.TW"], feature_start, overall_end)
    chip_features_all = _load_chip_features(db_path, prices_0050.index, feature_start, overall_end)
    vol_high_series = _vol_high_series(prices_0050, chip_features_all)

    jk_results: dict[str, dict[str, Any]] = {}
    per_window: dict[str, Any] = {}

    for win_label, start, end in DEFAULT_WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        report, frame = run_a2118(
            start=start, end=end_resolved, initial_value=initial_value, db=db_path,
            commission_rate=commission_rate, slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            ncf_panel_631l_path="results/ncf_00631l_panel_latest_20260707.csv",
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
            risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
            momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
            momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        )
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        golden_weights = dict(report["base_weights"]["golden1"])
        weights_by_regime = dict(report["base_weights"])

        win_vol_high = vol_high_series.reindex(frame.index).fillna(False)
        vol_high_never = pd.Series(False, index=frame.index)

        trend = _classify_trend(
            frame["ma_gap"], frame["drawdown"],
            good_ma_gap_min=CHAMPION_PARAMS["good_ma_gap_min"],
            good_drawdown_min=CHAMPION_PARAMS["good_drawdown_min"],
            bad_ma_gap_max=CHAMPION_PARAMS["bad_ma_gap_max"],
            bad_drawdown_max=CHAMPION_PARAMS["bad_drawdown_max"],
        )
        trend = _require_bad_persistence(trend, CHAMPION_PARAMS["bad_persistence_days"])

        # Baseline: reuses the exact same simulator with vol_high forced to
        # always-False, so no cap ever triggers regardless of trend -- pure
        # golden1 weights, apples-to-apples execution path with the champion
        # curve below (same execution_regime, same trade-cost model).
        baseline_curve, _ = _simulate_a22_curve(
            total_return_prices, execution_regime, trend, vol_high_never, golden_weights, weights_by_regime,
            CHAMPION_PARAMS["neutral_cap"], CHAMPION_PARAMS["bad_cap"], None,
            initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
        )
        champion_curve, _ = _simulate_a22_curve(
            total_return_prices, execution_regime, trend, win_vol_high, golden_weights, weights_by_regime,
            CHAMPION_PARAMS["neutral_cap"], CHAMPION_PARAMS["bad_cap"], CHAMPION_PARAMS["bad_no_vol_cap"],
            initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
        )

        b_returns = baseline_curve.pct_change().dropna()
        c_returns = champion_curve.pct_change().dropna()

        jk = jobson_korkie_memmel_test(c_returns, b_returns)
        jk_results[win_label] = jk
        per_window[win_label] = {
            "label": win_label,
            "n_days": len(b_returns),
            "baseline_final_value": float(baseline_curve.iloc[-1]),
            "champion_final_value": float(champion_curve.iloc[-1]),
            "reconstructed_baseline_matches_report": abs(
                float(baseline_curve.iloc[-1]) - float(report["metrics"]["final_value"])
            ) < 1.0,
            "jobson_korkie_memmel": jk,
        }
        print(f"=== {win_label} ===")
        print(f"  baseline_final={baseline_curve.iloc[-1]:,.0f} (report says {report['metrics']['final_value']:,.0f}) "
              f"champion_final={champion_curve.iloc[-1]:,.0f}")
        if jk.get("status") == "ok":
            print(f"  sharpe_champion={jk['sharpe_a']:.4f} sharpe_baseline={jk['sharpe_b']:.4f} "
                  f"p={jk['p_value']:.4f} significant_5pct(uncorrected)={jk['significant_at_5pct']}")
        else:
            print(f"  JK test: {jk.get('status')} ({jk.get('reason')})")

    grid_check = bonferroni_grid_significance(jk_results, candidate_grid_size=CANDIDATE_GRID_SIZE)

    print(f"\n=== Bonferroni grid check, per-window (candidate_grid_size={CANDIDATE_GRID_SIZE}) ===")
    print(f"corrected_alpha={grid_check['corrected_alpha']:.6f}")
    for win_label, c in grid_check["candidates"].items():
        print(f"  {win_label}: {c}")
    print(f"any_significant_after_correction={grid_check['any_significant']}")
    print(f"any_significant_improvement_after_correction={grid_check['any_significant_improvement']}")

    # The per-window checks above test 4 separate hypotheses, each corrected
    # for the full 33-candidate grid -- but the actual historical selection
    # criterion that produced the champion was the SUM of Sharpe deltas
    # across all 4 windows, a single joint statistic, not 4 independent ones.
    # A Stouffer combined-z test on the 4 (assumed independent -- different,
    # mostly non-overlapping calendar periods) per-window z-statistics is a
    # more faithful reconstruction of "would the actual selection criterion
    # survive correction for the grid it was chosen from" than 4 marginal
    # tests. Only defined when every window's JK test returned "ok".
    ok_windows = [w for w, jk in jk_results.items() if jk.get("status") == "ok"]
    combined: dict[str, Any] = {"status": "insufficient_windows"}
    if len(ok_windows) == len(jk_results) and len(ok_windows) > 0:
        z_values = [jk_results[w]["z_statistic"] for w in ok_windows]
        k = len(z_values)
        z_combined = sum(z_values) / math.sqrt(k)
        p_combined = float(2.0 * stats.norm.sf(abs(z_combined)))
        corrected_alpha = 0.05 / CANDIDATE_GRID_SIZE
        combined = {
            "status": "ok",
            "method": "stouffer_equal_weight_assumed_independent_windows",
            "windows": ok_windows,
            "z_values": z_values,
            "z_combined": z_combined,
            "p_combined": p_combined,
            "corrected_alpha": corrected_alpha,
            "significant": p_combined < corrected_alpha,
            "significant_uncorrected": p_combined < 0.05,
        }
        print(f"\n=== Combined cross-window check (Stouffer, more faithful to the actual sum-based selection) ===")
        print(f"z_combined={z_combined:.4f} p_combined={p_combined:.4f} "
              f"significant_uncorrected={combined['significant_uncorrected']} "
              f"significant_after_grid_correction={combined['significant']}")

    out_path = PROJECT_ROOT / "results" / "significance_check_a22_bad_vol_overlay_grid_20260905.json"
    out_path.write_text(
        json.dumps(
            {
                "candidate_grid_size": CANDIDATE_GRID_SIZE,
                "per_window": per_window,
                "bonferroni_grid_check_per_window": grid_check,
                "combined_cross_window_check": combined,
            },
            ensure_ascii=False, indent=2, default=str,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
