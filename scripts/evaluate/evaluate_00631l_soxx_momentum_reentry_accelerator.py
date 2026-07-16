#!/usr/bin/env python3
"""SOXX momentum-triggered 00631L re-entry accelerator: staged 0% -> 10% ->
20% re-entry when 00631L is in its own drawdown AND SOXX short-term
momentum recovers.

Research-only, 2026-07-12. Follows the "test the raw predictive premise
cheaply before building trading-curve machinery" discipline used all
session: evaluate_00631l_cross_asset_momentum_reentry.py first established
that SOXX 3-5 day trailing momentum has the most consistent (all-positive-
sign, best case p=0.096 at 3-day lookback / 20-day horizon) though still not
conventionally-significant lead-lag relationship with 00631L's forward
return, out of 0050/2330/SOXX/combined and 5 lookback windows tested. This
script builds the actual staged re-entry mechanism on that specific
(lookback=3, threshold~75-80th percentile) signal and tests it with the
SAME tuning+OOS discipline established for a2124
(project_a2124_rebound_recapture_20260710.md): 4 tuning windows
(covid_2020/inflation_2022/live_2024_2026/active_2025_2026) AND the
2017-2019 out-of-sample window, evaluated together from the start (not
tuned-then-checked), to avoid repeating A22's overfitting mistake.

Distinct from a2124 (2026-07-10, shadow candidate, never promoted): a2124's
trigger is 0050's own single-day shock+rebound event detection and boosts
for 1 day; this trigger is SOXX's OWN short-term momentum (an external
leading proxy, available before Taiwan's session open) and stages a
multi-day ladder (10% -> 20%) rather than a single-day pulse.

Mechanism:
  Precondition (eligible for re-entry, i.e. "currently de-risked"): 00631L's
  own trailing drawdown from its rolling peak <= --drawdown-threshold
  (default -0.10).
  Trigger: SOXX trailing --soxx-lookback-days (default 3) return >=
  --soxx-momentum-threshold (default 0.02, ~75th percentile of the
  unconditional distribution).
  Staged action (golden1 days only): on the first triggered day, set
  00631L target weight to --stage1-weight (default 0.10); if the trigger
  is still active the next trading day, escalate to --stage2-weight
  (default 0.20); hold at the reached stage for --hold-days (default 5)
  trading days after the last confirmed trigger day, then revert to
  golden1's base weight.
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
from scripts.evaluate.evaluate_00631l_cross_asset_momentum_reentry import _load_external_close

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_soxx_momentum_reentry_accelerator_latest.json"

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


def _build_signals(
    close_00631l: pd.Series,
    *,
    drawdown_threshold: float,
    soxx_lookback_days: int,
    soxx_momentum_threshold: float,
) -> tuple[pd.Series, pd.Series]:
    rolling_peak = close_00631l.cummax()
    drawdown = close_00631l / rolling_peak - 1.0
    eligible = drawdown <= drawdown_threshold

    soxx = _load_external_close("SOXX")
    soxx_momentum = soxx.pct_change(soxx_lookback_days).reindex(close_00631l.index).ffill(limit=2)
    trigger = (soxx_momentum >= soxx_momentum_threshold) & eligible
    return trigger.fillna(False), eligible.fillna(False)


def _staged_weight_series(trigger: pd.Series, *, stage1_weight: float, stage2_weight: float, hold_days: int) -> pd.Series:
    stage = pd.Series(0.0, index=trigger.index)
    days_since_trigger: int | None = None
    consecutive_trigger_days = 0
    for i, (dt, fired) in enumerate(trigger.items()):
        if fired:
            consecutive_trigger_days += 1
            days_since_trigger = 0
            stage.iloc[i] = stage2_weight if consecutive_trigger_days >= 2 else stage1_weight
        elif days_since_trigger is not None:
            days_since_trigger += 1
            consecutive_trigger_days = 0
            if days_since_trigger <= hold_days:
                stage.iloc[i] = stage.iloc[i - 1] if i > 0 else 0.0
            else:
                stage.iloc[i] = 0.0
                days_since_trigger = None
        else:
            consecutive_trigger_days = 0
            stage.iloc[i] = 0.0
    return stage


def _simulate(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    reentry_weight: pd.Series,
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
    triggered_days = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            override = float(reentry_weight.loc[dt]) if dt in reentry_weight.index and pd.notna(reentry_weight.loc[dt]) else 0.0
            if override > 0.0:
                triggered_days += 1
                weights = dict(golden_weights)
                shift = override - float(weights.get("00631L.TW", 0.0) or 0.0)
                weights["00631L.TW"] = override
                weights["0050.TW"] = max(0.0, float(weights.get("0050.TW", 0.0) or 0.0) - shift)
                key = f"golden1_reentry_{override:.4f}"
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
        "triggered_days": triggered_days,
    }


def evaluate_window(
    *, label: str, start: str, end: str, ncf_panel_631l: str, db_path: Path, initial_value: float,
    commission_rate: float, slippage_rate: float, equity_etf_sell_tax: float,
    drawdown_threshold: float, soxx_lookback_days: int, soxx_momentum_threshold: float,
    stage1_weight: float, stage2_weight: float, hold_days: int,
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
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])

    trigger, eligible = _build_signals(
        close_00631l, drawdown_threshold=drawdown_threshold,
        soxx_lookback_days=soxx_lookback_days, soxx_momentum_threshold=soxx_momentum_threshold,
    )
    reentry_weight = _staged_weight_series(trigger, stage1_weight=stage1_weight, stage2_weight=stage2_weight, hold_days=hold_days)

    curve, sim = _simulate(
        total_return_prices, execution_regime, reentry_weight, golden_weights, weights_by_regime,
        initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
    )
    metrics = _metrics(curve, initial_value)

    return {
        "label": label,
        "window": {"start": start, "end": end},
        "eligible_days": int(eligible.sum()),
        "trigger_days": int(trigger.sum()),
        "active_reentry_days": int(sim["triggered_days"]),
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
    parser.add_argument("--drawdown-threshold", type=float, default=-0.10)
    parser.add_argument("--soxx-lookback-days", type=int, default=3)
    parser.add_argument("--soxx-momentum-threshold", type=float, default=0.02)
    parser.add_argument("--stage1-weight", type=float, default=0.10)
    parser.add_argument("--stage2-weight", type=float, default=0.20)
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    results = []
    for win_label, start, end, panel in TUNING_WINDOWS + OOS_WINDOWS:
        kind = "tuning" if (win_label, start, end, panel) in TUNING_WINDOWS else "oos"
        result = evaluate_window(
            label=win_label, start=start, end=end, ncf_panel_631l=panel, db_path=db_path,
            initial_value=args.initial_value, commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate, equity_etf_sell_tax=args.equity_etf_sell_tax,
            drawdown_threshold=args.drawdown_threshold, soxx_lookback_days=args.soxx_lookback_days,
            soxx_momentum_threshold=args.soxx_momentum_threshold,
            stage1_weight=args.stage1_weight, stage2_weight=args.stage2_weight, hold_days=args.hold_days,
        )
        result["kind"] = kind
        results.append(result)
        d = result["delta_vs_baseline"]
        print(
            f"[{kind}] {result['label']}: eligible={result['eligible_days']} trigger={result['trigger_days']} "
            f"active={result['active_reentry_days']} delta_final={d['final_value']:.1f} "
            f"delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    tuning_sharpe = sum(r["delta_vs_baseline"]["sharpe_ratio"] for r in results if r["kind"] == "tuning")
    tuning_fv = sum(r["delta_vs_baseline"]["final_value"] for r in results if r["kind"] == "tuning")
    oos_sharpe = sum(r["delta_vs_baseline"]["sharpe_ratio"] for r in results if r["kind"] == "oos")
    oos_fv = sum(r["delta_vs_baseline"]["final_value"] for r in results if r["kind"] == "oos")
    print(f"\nTuning sum: ΔSharpe={tuning_sharpe:+.4f} Δfv={tuning_fv:+.1f}")
    print(f"OOS sum:    ΔSharpe={oos_sharpe:+.4f} Δfv={oos_fv:+.1f}")

    payload = {"params": vars(args), "windows": results, "tuning_sum": {"sharpe": tuning_sharpe, "fv": tuning_fv}, "oos_sum": {"sharpe": oos_sharpe, "fv": oos_fv}}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
