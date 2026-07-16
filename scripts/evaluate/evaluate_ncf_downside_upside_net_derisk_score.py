#!/usr/bin/env python3
"""Approximate historical backtest: does netting the (now-fixed) upside
signal against the downside signal improve on downside-only de-risking?

Research-only. User's proposal (2026-07-11, same day as the ncf_upside_signal
tail-risk fix): `de-risk_score = downside_signal - upside_signal`, motivated
by Pinelis & Ruppert's finding that reward-risk timing (using BOTH an
expected-return forecast and a risk forecast) beats risk-timing alone, and
by this project's own repeated finding that pure vol/risk-based de-risking
sacrifices too much upside during bull continuations (see
GROUP_A_PLUS_ML_REWARD_RISK_TIMING_VOL_SCALING_HANDOFF_20260711.md).

IMPORTANT DISCOVERY: `ncf_overlay_summary`/`adjust_golden1_weights` (the
actual live daily de-risk mechanism, called from
group_a_plus/operations/daily_signal.py) is NEVER invoked by
group_a_plus/runners/a2118.py's `run_a2118` -- the backtest engine used by
every other evaluate_* script in this project. This means the production
downside-only overlay itself has never been backtested before today; this
script is also, incidentally, the first historical backtest of that
mechanism, not just of the net-score variant.

APPROXIMATION CAVEATS (why this is "quick, not faithful" -- see handoff for
the two gaps that make a faithful version more work):
1. `direction_conflict` cannot be reconstructed from the NCF panel CSVs
   (`ncf_00631l_panel_latest_*.csv` / `ncf_00632r_panel_latest_*.csv`) --
   they lack the `weighted_return` field `load_ncf_signal` uses to derive
   it. This script therefore always sets `direction_conflict=False`, i.e.
   never triggers the both-conflict fallback fixed today. Both the
   downside-only and net conditions share this same approximation, so the
   *relative* comparison between them is still meaningful even though
   neither matches live behavior exactly.
2. Panel coverage is 2025-01-02 onward only (00632R has no 2017-2019
   backfill unlike 00631L) -- covid_2020/inflation_2022 are not reachable
   with this data. Only a single continuous live-ish window is tested.
3. `calibrated_prob_up` (post-shrinkage) is approximated by the panel's
   `ensemble_prob_up` (pre-shrinkage combined probability) -- the panel
   does not carry the calibrated value.

Three conditions compared, golden1 days only (non-golden1 days keep
whatever a2118 already assigns, unchanged):
  A) baseline: golden1 weights unmodified (a2118's own baseline)
  B) downside_only: adjust_golden1_weights(golden_weights, downside_signal)
  C) net_derisk: adjust_golden1_weights(golden_weights, max(0, downside_signal - upside_signal))
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.integrations.ncf import adjust_golden1_weights, ncf_downside_signal, ncf_upside_signal
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_downside_upside_net_derisk_score_latest.json"
PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260710.csv"
PANEL_632R = PROJECT_ROOT / "results" / "ncf_00632r_panel_latest_20260710.csv"


def _panel_signal_dict(row: pd.Series) -> dict:
    return {
        "calibrated_prob_up": float(row["ensemble_prob_up"]),
        "confidence": float(row["confidence"]),
        "tail_reward_risk_score": (
            float(row["tail_reward_risk_score_h20"]) if pd.notna(row["tail_reward_risk_score_h20"]) else None
        ),
        "prob_fwd_mdd_gt5_h20": (
            float(row["prob_fwd_mdd_gt5_h20"]) if pd.notna(row["prob_fwd_mdd_gt5_h20"]) else None
        ),
        "prob_fwd_gain_gt5_h20": (
            float(row["prob_fwd_gain_gt5_h20"]) if pd.notna(row["prob_fwd_gain_gt5_h20"]) else None
        ),
        "direction_conflict": False,  # approximation -- see module docstring
    }


def _build_signal_series(panel_631l: pd.DataFrame, panel_632r: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    merged = panel_631l.set_index("date").join(
        panel_632r.set_index("date"), lsuffix="_631l", rsuffix="_632r", how="inner"
    )
    downside = {}
    upside = {}
    for date_str, row in merged.iterrows():
        sig_631l = _panel_signal_dict(row.filter(regex="_631l$").rename(lambda c: c[: -len("_631l")]))
        sig_632r = _panel_signal_dict(row.filter(regex="_632r$").rename(lambda c: c[: -len("_632r")]))
        dt = pd.Timestamp(date_str)
        downside[dt] = ncf_downside_signal(sig_631l, sig_632r)
        upside[dt] = ncf_upside_signal(sig_631l, sig_632r)
    return pd.Series(downside).sort_index(), pd.Series(upside).sort_index()


def _simulate(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    score: pd.Series,
    golden_weights: dict[str, float],
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict]:
    shares = {t: 0.0 for t in TICKERS}
    cash = float(initial_value)
    applied_key: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            s = float(score.loc[dt]) if dt in score.index and pd.notna(score.loc[dt]) else 0.0
            s = min(max(s, 0.0), 1.0)
            key = f"golden1_score_{s:.4f}"
            target_weights = adjust_golden1_weights(golden_weights, s) if s > 0.0 else golden_weights
        else:
            key = regime
            target_weights = weights_by_regime.get(regime, golden_weights)

        if key != applied_key:
            weights = _normalize(target_weights)
            current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _ in range(3):
                target_values = {t: net_value * weights.get(t, 0.0) for t in TICKERS}
                cost, turnover = _trade_cost(
                    current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in TICKERS}
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            applied_key = key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": total_cost,
        "turnover_value": total_turnover,
        "rebalance_count": rebalance_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-631l", default=str(PANEL_631L))
    parser.add_argument("--panel-632r", default=str(PANEL_632R))
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    panel_631l = pd.read_csv(args.panel_631l)
    panel_632r = pd.read_csv(args.panel_632r)
    downside_series, upside_series = _build_signal_series(panel_631l, panel_632r)
    net_series = (downside_series - upside_series).clip(lower=0.0, upper=1.0)

    end = args.end
    if end.lower() == "latest":
        import duckdb

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            end = pd.Timestamp(con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = '0050.TW'").fetchone()[0]).strftime("%Y-%m-%d")
        finally:
            con.close()

    report, frame = run_a2118(
        start=args.start, end=end, initial_value=args.initial_value, db=db_path,
        commission_rate=args.commission_rate, slippage_rate=args.slippage_rate,
        equity_etf_sell_tax=args.equity_etf_sell_tax, ncf_panel_631l_path=args.ncf_panel_631l,
        h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), args.start, end)
    total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
    execution_regime = frame["execution_regime"].astype(str)
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])
    baseline_metrics = dict(report["metrics"])
    golden_mask = execution_regime == "golden1"

    zero_score = pd.Series(0.0, index=frame.index)
    downside_reindexed = downside_series.reindex(frame.index).fillna(0.0)
    net_reindexed = net_series.reindex(frame.index).fillna(0.0)

    results = {}
    for label, score in (
        ("downside_only", downside_reindexed),
        ("net_derisk", net_reindexed),
    ):
        curve, sim = _simulate(
            total_return_prices, execution_regime, score, golden_weights, weights_by_regime,
            args.initial_value, args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
        )
        metrics = _metrics(curve, args.initial_value)
        results[label] = {
            "metrics": metrics,
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "mean_score_on_golden1_days": float(score[golden_mask].mean()) if golden_mask.any() else None,
            "days_score_gt_0": int((score > 0.0).sum()),
        }

    payload = {
        "window": {"start": args.start, "end": end, "golden1_days": int(golden_mask.sum())},
        "baseline_metrics": baseline_metrics,
        "results": results,
    }
    for label, res in results.items():
        d = res["delta_vs_baseline"]
        print(
            f"{label}: mean_score={res['mean_score_on_golden1_days']:.4f} days>0={res['days_score_gt_0']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
