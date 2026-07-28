#!/usr/bin/env python3
"""Research-only: does walk-forward de-biasing prob_up_h20 change a2118's
late-bull-hedge dormancy?

Context: evaluate_ncf_h20_utility_weighted_calibration.py (2026-07-26) found
prob_up_h20 is systematically underconfident about "up" during 2025-2026
(mean predicted 0.558 vs realized 0.762, bias -0.20, worse near the 0.5
decision threshold). [[project_a2118_ncf_hedge_dormancy_root_cause_20260723]]
separately found late-bull-hedge has fired 0 times across four independent
years because confidence (=|prob_up_h20-0.5|*2) stays structurally low in
2025-2026 (mean 0.23-0.29 vs 0.40 in a 2017-2019 backfill). Naively: if
prob_up_h20 undershoots the true "up" probability, predictions cluster near
0.5 instead of confidently high, which mechanically suppresses confidence
even when the true probability is high -- a candidate explanation for *why*
confidence stays low, distinct from "model disagreement is genuinely low."

This script tests that mechanism directly: apply a purely walk-forward
(no-leakage) additive bias correction to prob_up_h20 -- at each date, shift
by the trailing mean(predicted)-mean(actual) computed only from labels
resolved strictly before that date (same resolved_end convention as
_build_expanding_horizon_ensemble_panel in ncf_00631l.py) -- then:
  1. Check whether the corrected series is actually better calibrated
     out-of-sample (it must be, almost by construction, but verify the
     walk-forward version doesn't degrade compared to the in-sample number).
  2. Check whether AUC is preserved (a constant daily shift should not
     change ranking on any single day, but the correction changes over
     time, so this is not guaranteed and must be checked).
  3. Re-run the actual run_a2118() backtest against the corrected panel
     and compare late_bull_trigger_days / Sharpe / MDD to the production
     panel, to see if the mechanism hypothesis has any real trigger-behavior
     consequence.

Does NOT touch any production file. Writes only to a temp directory.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, _resolve_end_date, run_a2118
HORIZON = 20  # h20 label needs 20 trading days to resolve
PRODUCTION_H20_MAX = 0.33
PRODUCTION_CONF_MIN = 0.55
PRODUCTION_H5_REENTRY_MIN = 0.55


def _walkforward_bias_correct(panel: pd.DataFrame, *, min_history: int = 60) -> pd.Series:
    """Additive de-bias of prob_up_h20 using only labels resolved strictly
    before each row (resolved_end = pos - HORIZON, matching the codebase's
    own leak-avoidance convention)."""
    prob = panel["prob_up_h20"].to_numpy(dtype=float)
    actual = panel["actual_up_h20"].to_numpy(dtype=float)  # NaN where unresolved (is_live rows)
    n = len(panel)
    corrected = prob.copy()
    for pos in range(n):
        resolved_end = max(0, pos - HORIZON)
        hist_actual = actual[:resolved_end]
        hist_prob = prob[:resolved_end]
        valid = ~np.isnan(hist_actual)
        if int(valid.sum()) < min_history:
            continue  # not enough history yet -- leave uncorrected
        bias = float(hist_prob[valid].mean() - hist_actual[valid].mean())
        corrected[pos] = float(np.clip(prob[pos] - bias, 0.0, 1.0))
    return pd.Series(corrected, index=panel.index, name="prob_up_h20_corrected")


def _brier(prob: pd.Series, actual: pd.Series) -> float:
    df = pd.DataFrame({"prob": prob, "actual": actual}).dropna()
    return float(np.mean((df["prob"] - df["actual"]) ** 2)) if not df.empty else float("nan")


def _bias(prob: pd.Series, actual: pd.Series) -> float:
    df = pd.DataFrame({"prob": prob, "actual": actual}).dropna()
    return float(df["prob"].mean() - df["actual"].mean()) if not df.empty else float("nan")


def _run_backtest(panel_path: Path, *, label: str, end: str) -> dict:
    report, _frame = run_a2118(
        start="2025-01-02",
        end=end,
        initial_value=1_000_000.0,
        db=DB_PATH,
        ncf_panel_631l_path=str(panel_path),
        h20_max=PRODUCTION_H20_MAX,
        conf_min=PRODUCTION_CONF_MIN,
        h5_reentry_min=PRODUCTION_H5_REENTRY_MIN,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )
    metrics = report["metrics"]
    execution = report["execution"]
    return {
        "label": label,
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "annual_return": metrics["annual_return"],
        "max_drawdown": metrics["max_drawdown"],
        "late_bull_trigger_days": execution.get("late_bull_trigger_days"),
        "late_bull_trigger_events": execution.get("late_bull_trigger_events"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260725.csv"))
    parser.add_argument("--min-history", type=int, default=60)
    args = parser.parse_args()

    panel = pd.read_csv(args.panel, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    corrected = _walkforward_bias_correct(panel, min_history=args.min_history)
    panel_corrected = panel.copy()
    panel_corrected["prob_up_h20"] = corrected
    panel_corrected["confidence"] = (corrected - 0.5).abs() * 2
    panel_corrected["prob_magnitude"] = panel_corrected["confidence"]

    resolved = panel[panel["is_live"] == False].copy()  # noqa: E712
    resolved_corrected = corrected[panel["is_live"] == False]

    print(f"Resolved rows: {len(resolved)}")
    print("\n=== Calibration: original vs walk-forward corrected (out-of-sample only) ===")
    print(f"Original   Brier={_brier(resolved['prob_up_h20'], resolved['actual_up_h20']):.4f}  "
          f"bias={_bias(resolved['prob_up_h20'], resolved['actual_up_h20']):+.4f}")
    print(f"Corrected  Brier={_brier(resolved_corrected, resolved['actual_up_h20']):.4f}  "
          f"bias={_bias(resolved_corrected, resolved['actual_up_h20']):+.4f}")

    valid_auc = resolved['actual_up_h20'].notna() & (resolved['actual_up_h20'].nunique() >= 2)
    auc_orig = roc_auc_score(resolved['actual_up_h20'], resolved['prob_up_h20'])
    auc_corr = roc_auc_score(resolved['actual_up_h20'], resolved_corrected)
    print(f"\nAUC original:  {auc_orig:.4f}")
    print(f"AUC corrected: {auc_corr:.4f}  (should be identical or very close -- daily shift preserves same-day ranking)")

    print(f"\nMean confidence original:  {panel['confidence'].mean():.4f}")
    print(f"Mean confidence corrected: {panel_corrected['confidence'].mean():.4f}")

    print("\n=== Actual a2118 backtest: production panel vs bias-corrected panel ===")
    resolved_end = _resolve_end_date(Path(DB_PATH), "latest")
    with tempfile.TemporaryDirectory() as tmp:
        corrected_path = Path(tmp) / "corrected_panel.csv"
        panel_corrected.to_csv(corrected_path, index=False)

        baseline = _run_backtest(Path(args.panel), label="production_panel", end=resolved_end)
        corrected_result = _run_backtest(corrected_path, label="bias_corrected_panel", end=resolved_end)

    for r in (baseline, corrected_result):
        print(
            f"{r['label']:>22}: sharpe={r['sharpe_ratio']:.4f}, sortino={r['sortino_ratio']:.4f}, "
            f"annual_return={r['annual_return']:.4f}, max_dd={r['max_drawdown']:.4f}, "
            f"late_bull_trigger_days={r['late_bull_trigger_days']}"
        )
        if r["late_bull_trigger_events"]:
            print(f"    events: {r['late_bull_trigger_events']}")


if __name__ == "__main__":
    main()
