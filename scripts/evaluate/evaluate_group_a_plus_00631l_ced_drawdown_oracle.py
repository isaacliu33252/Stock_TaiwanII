#!/usr/bin/env python3
"""Oracle ceiling test for Conditional-Expected-Drawdown-style 00631L labels
(user-specified thresholds, 2026-07-11), following Goldberg & Mahmoud,
"Drawdown: From Practice to Theory and Back Again" -- CED formalizes drawdown
risk as the average severity of drawdowns that breach a threshold, and notes
CED is sensitive to serial correlation in a way plain volatility is not.

This reuses the exact oracle-ceiling harness already built and tested
2026-07-10 (evaluate_group_a_plus_00631l_downside_oracle_ceiling.py, label A:
future max-drawdown-threshold) with two new, tighter threshold/horizon
combinations the user asked about instead of that script's original
(-10%, 10d):

  A) future 10-trading-day 00631L max drawdown < -5%
  B) future 20-trading-day 00631L max drawdown < -8%

Same important framing as the original script: this is NOT a real forecast
-- it uses actual future prices (look-ahead) to answer only "is there even a
theoretical edge worth chasing." The original oracle test (three different
labels, thresholds -10%/10d, race -8%/+12%, semivar top20%) was the first
time in this project's whole volatility/regime-routing research history that
an oracle ceiling came back positive on all three windows/labels tested --
but every REAL (non-oracle) classifier and rule built on similar labels
since then (race classifier line, A22_bad_vol_overlay line) failed to
capture that ceiling in true out-of-sample testing. See
GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md and
memory project_00631l_downside_risk_forecast_20260710.md for that full
history before drawing conclusions from this oracle number alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_oracle_ceiling import (
    _label_max_drawdown,
    _resolve_end_date,
    _simulate_oracle_curve,
    _weights_de_risked,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_00631l_ced_drawdown_oracle_latest.json"

CED_LABELS = [
    ("A_10d_mdd_lt_5pct", 10, -0.05),
    ("B_20d_mdd_lt_8pct", 20, -0.08),
]

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start, end=end, initial_value=initial_value, db=db_path,
        commission_rate=commission_rate, slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax, ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
    close_00631l = total_return_prices["00631L.TW"].reindex(frame.index)

    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])
    de_risked_weights = _weights_de_risked(golden_weights)
    golden_mask = execution_regime == "golden1"

    label_results = {}
    for name, horizon, threshold in CED_LABELS:
        flag = (_label_max_drawdown(close_00631l, horizon) < threshold).reindex(frame.index)
        flag = flag.fillna(False).astype(bool)
        curve, sim = _simulate_oracle_curve(
            total_return_prices, execution_regime, flag, golden_weights, de_risked_weights,
            weights_by_regime, initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        label_results[name] = {
            "horizon": horizon,
            "threshold": threshold,
            "metrics": metrics,
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "flagged_days_within_golden1": int((flag & golden_mask).sum()),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        }

    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "golden1_days": int(golden_mask.sum()),
        "baseline_metrics": baseline_metrics,
        "ced_labels": label_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    results = []
    for win_label, start, end in DEFAULT_WINDOWS:
        result = evaluate_window(
            label=win_label, start=start, end=end, db_path=db_path,
            initial_value=args.initial_value, ncf_panel_631l=args.ncf_panel_631l,
            commission_rate=args.commission_rate, slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax,
        )
        results.append(result)
        print(f"\n{result['label']} ({result['window']['start']}..{result['window']['end']}, golden1_days={result['golden1_days']}):")
        for name, res in result["ced_labels"].items():
            d = res["delta_vs_baseline"]
            print(
                f"  {name}: flagged={res['flagged_days_within_golden1']} "
                f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"windows": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
