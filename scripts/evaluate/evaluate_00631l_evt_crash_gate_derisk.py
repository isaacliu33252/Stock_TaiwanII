#!/usr/bin/env python3
"""EVT crash-probability gate: de-risk 00631L to 0% only when its own
walk-forward POT crash_prob crosses a rare, extreme threshold; otherwise
leave golden1 weights untouched.

Research-only, 2026-07-12. Follows
evaluate_00631l_evt_crash_probability.py, which found the crash_prob
estimator computed directly on 00631L.TW (not 0050.TW) shows a real,
monotonic (if modest) relationship with subsequent realized drawdown
severity -- the cleanest calibration result of this session's EVT/tail-risk
line. Tests the actual trading mechanism the user asked for: binary,
rare-trigger de-risk to 0%, NOT a continuously-adjusted score (the design
constraint that distinguishes this from the continuous vol-scaling and
staged-momentum mechanisms tested earlier this session, both of which
failed).

Same tuning+OOS discipline as every other mechanism test this session (4
tuning windows + 2017-2019 OOS), evaluated together from the start.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_evt_crash_probability import _walk_forward_crash_prob

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_evt_crash_gate_derisk_latest.json"
ROLLING_THRESHOLD_WINDOW = 504

TUNING_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("inflation_2022", "2022-01-03", "2022-12-30", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("live_2024_2026", "2024-01-02", "latest", "results/ncf_00631l_panel_latest_20260707.csv"),
    ("active_2025_2026", "2025-01-02", "latest", "results/ncf_00631l_panel_latest_20260707.csv"),
]
OOS_WINDOWS = [
    ("2017_bull", "2017-01-03", "2017-12-29", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
    ("2018_correction", "2018-01-02", "2018-12-28", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
    ("2019_recovery", "2019-01-02", "2019-12-31", "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"),
]


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _full_history_crash_prob(db_path: Path, feature_start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = '00631L.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [feature_start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.set_index("dt")["close"].astype(float)
    returns = close.pct_change().fillna(0.0)
    return _walk_forward_crash_prob(returns)


def _simulate(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    gate_active: pd.Series,
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
    rebalance_count = 0
    active_days = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            is_active = bool(gate_active.loc[dt]) if dt in gate_active.index and pd.notna(gate_active.loc[dt]) else False
            if is_active:
                active_days += 1
                weights = dict(golden_weights)
                shift = float(weights.get("00631L.TW", 0.0) or 0.0)
                weights["00631L.TW"] = 0.0
                weights["0050.TW"] = float(weights.get("0050.TW", 0.0) or 0.0) + shift
                key = "golden1_crash_gate_0pct"
                target_weights = weights
            else:
                key = "golden1"
                target_weights = golden_weights
        else:
            key = regime
            target_weights = weights_by_regime.get(regime, golden_weights)

        if key != applied_key:
            weights = _normalize(target_weights)
            current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
            net_value = gross_value
            cost = 0.0
            for _ in range(3):
                target_values = {t: net_value * weights.get(t, 0.0) for t in TICKERS}
                cost, _turnover = _trade_cost(
                    current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in TICKERS}
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            rebalance_count += 1
            applied_key = key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": total_cost,
        "rebalance_count": rebalance_count,
        "active_days": active_days,
    }


def evaluate_window(
    *, label: str, start: str, end: str, ncf_panel_631l: str, db_path: Path, initial_value: float,
    commission_rate: float, slippage_rate: float, equity_etf_sell_tax: float,
    crash_prob_full: pd.Series, gate_percentile: float,
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
    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])

    # BUG FOUND AND FIXED 2026-07-12: a single global (whole-history)
    # threshold meant covid_2020's crash_prob (max 0.0116) never came close
    # to the global p95 cutoff (0.0162), which is dominated by the
    # structurally higher crash_prob baseline of 2024-2026 -- covid_2020,
    # inflation_2022, and all three 2017-2019 OOS windows fired on ZERO days
    # under the global-threshold design, which defeats the purpose of a
    # crash gate (same "global weight drift" mistake pattern already known
    # in this project's NCF ensemble-weight history: a fixed whole-sample
    # cutoff silently absorbs regime differences instead of adapting to
    # them). Fixed to a rolling percentile threshold (matches how
    # garch_regime_shadow.py's vol_high ratio/percentile flags are already
    # computed), so the gate is calibrated against crash_prob's OWN trailing
    # distribution at each point in time, not a fixed historical level.
    rolling_threshold = crash_prob_full.rolling(ROLLING_THRESHOLD_WINDOW, min_periods=60).quantile(gate_percentile)
    gate_active = (crash_prob_full >= rolling_threshold).reindex(frame.index).fillna(False)
    threshold = float(rolling_threshold.reindex(frame.index).dropna().mean()) if rolling_threshold.notna().any() else float("nan")

    curve, sim = _simulate(
        total_return_prices, execution_regime, gate_active, golden_weights, weights_by_regime,
        initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
    )
    metrics = _metrics(curve, initial_value)

    return {
        "label": label,
        "window": {"start": start, "end": end},
        "gate_threshold": threshold,
        "active_days": sim["active_days"],
        "delta_vs_baseline": {
            "final_value": metrics["final_value"] - baseline_metrics["final_value"],
            "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
            "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--gate-percentile", type=float, default=0.95)
    parser.add_argument("--feature-start", default="2013-01-02")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    overall_end = _resolve_end_date(db_path, "latest")
    crash_prob_full = _full_history_crash_prob(db_path, args.feature_start, overall_end)

    results = []
    for win_label, start, end, panel in TUNING_WINDOWS + OOS_WINDOWS:
        kind = "tuning" if (win_label, start, end, panel) in TUNING_WINDOWS else "oos"
        result = evaluate_window(
            label=win_label, start=start, end=end, ncf_panel_631l=panel, db_path=db_path,
            initial_value=args.initial_value, commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate, equity_etf_sell_tax=args.equity_etf_sell_tax,
            crash_prob_full=crash_prob_full, gate_percentile=args.gate_percentile,
        )
        result["kind"] = kind
        results.append(result)
        d = result["delta_vs_baseline"]
        print(
            f"[{kind}] {result['label']}: active_days={result['active_days']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    tuning_sharpe = sum(r["delta_vs_baseline"]["sharpe_ratio"] for r in results if r["kind"] == "tuning")
    tuning_fv = sum(r["delta_vs_baseline"]["final_value"] for r in results if r["kind"] == "tuning")
    oos_sharpe = sum(r["delta_vs_baseline"]["sharpe_ratio"] for r in results if r["kind"] == "oos")
    oos_fv = sum(r["delta_vs_baseline"]["final_value"] for r in results if r["kind"] == "oos")
    print(f"\nTuning sum: ΔSharpe={tuning_sharpe:+.4f} Δfv={tuning_fv:+.1f}")
    print(f"OOS sum:    ΔSharpe={oos_sharpe:+.4f} Δfv={oos_fv:+.1f}")

    payload = {"gate_percentile": args.gate_percentile, "windows": results, "tuning_sum": {"sharpe": tuning_sharpe, "fv": tuning_fv}, "oos_sum": {"sharpe": oos_sharpe, "fv": oos_fv}}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
