#!/usr/bin/env python3
"""arXiv:2103.10157 "Leveraged ETF Investing" (Miller, 2021) applicability
test for GroupA+.

Core paper claim: a FIXED-RATIO mix of a leveraged stock ETF and a bond ETF,
rebalanced back to target whenever any weight drifts >20% from target
(deviation-band rebalancing, not a regime switch), historically beat a 100%
unleveraged-stock buy-and-hold portfolio on BOTH risk (5th-percentile final
yield, max drawdown) AND reward (median/CAGR) in 1989-2020 US market data.
The mechanism is a "rebalancing bonus": stock/bond anti-correlation means
forced rebalances buy the dip in whichever leg just fell, systematically.
Cites Hedgefundie's Excellent Adventure (Bogleheads) as the origin of this
2x/3x-leveraged-stock + leveraged-bond idea.

Why this needed an independent test rather than reasoning by analogy from
already-closed research: GroupA+ already tested 00679B (Taiwan-listed long-
duration US treasury ETF) as a defensive-basket component and REMOVED it
(project_a2118_defensive_basket_00679b_removed_promoted_20260818, arXiv:
2601.21447) because it hurt performance in 2022 and 2025-03 specifically --
but that was a REGIME-SWITCH mechanism (100% golden1 OR 100% defensive
basket, never both), not this paper's core mechanism: a CONTINUOUSLY-HELD,
deviation-band-rebalanced FIXED ratio of leveraged-stock + bond. The two are
structurally different enough that the prior negative result does not
automatically transfer -- this paper's own "rebalancing bonus" argument only
applies when you always hold both legs and let rebalancing trades buy/sell
into genuine anti-correlated moves, which the regime-switch tests never
exercised. Per feedback_verify_every_paper_independently, this must be
tested on its own, not just reasoned about.

Also relevant: the paper's own 1989-2020 backtest window does not include
any period resembling 2022's simultaneous stock-and-bond selloff (rate-hike
regime) -- the exact episode that broke bond diversification for GroupA+'s
own already-closed 00679B research. Testing this paper's specific mechanism
on Taiwan data covering 2022 directly checks whether that gap matters.

Method: standalone deviation-band rebalancing loop (not reusing
_simulate_costed_curve, which only rebalances on regime-label change, a
poor fit for a continuously-drifting fixed-ratio portfolio). Tracks real
share counts for a 2-asset mix (00631L + one of {00679B, cash}), using
dividend-adjusted total-return prices (_load_total_return_prices, reused
unmodified from backtest_group_a_plus_defensive_basket.py). Rebalances to
target whenever either leg's weight drifts beyond the target +/- 20%
(relative, matching the paper's own choice) of the target itself -- e.g.
target 40% triggers outside [32%, 48%]. Standard cost assumptions used
elsewhere this session (commission 0.1425%, slippage 0.05%, equity ETF sell
tax 0.1%). Same 4 standard windows used throughout this session's LETF
guard work. Benchmarked against 100% 0050 buy-and-hold (the paper's own
benchmark) and 100% 00631L buy-and-hold.

Research-only. Never touches production strategy files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402

COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005
EQUITY_ETF_SELL_TAX = 0.001
DEVIATION_BAND = 0.20  # relative deviation from target that triggers a rebalance, matches the paper

WINDOWS = (
    ("full_2020_2026", "2020-01-02", "latest"),
    ("rate_hike_2022_2023", "2022-01-03", "2023-12-29"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
)

LEVERAGED_TICKER = "00631L.TW"
STOCK_TICKER = "0050.TW"


def _resolve_end(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if requested_end.lower() != "latest":
        return requested_end
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _trade_cost(current: dict[str, float], target: dict[str, float]) -> tuple[float, float]:
    turnover = sum(abs(target.get(t, 0.0) - current.get(t, 0.0)) for t in set(current) | set(target))
    sells = sum(max(current.get(t, 0.0) - target.get(t, 0.0), 0.0) for t in set(current) | set(target) if t != "cash")
    buys = sum(max(target.get(t, 0.0) - current.get(t, 0.0), 0.0) for t in set(current) | set(target) if t != "cash")
    cost = (buys + sells) * (COMMISSION_RATE + SLIPPAGE_RATE) + sells * EQUITY_ETF_SELL_TAX
    return cost, turnover


def _deviation_band_curve(
    prices: pd.DataFrame, *, leveraged_weight: float, bond_ticker: str | None, initial_value: float
) -> tuple[pd.Series, dict[str, Any]]:
    tickers = [LEVERAGED_TICKER] + ([bond_ticker] if bond_ticker else [])
    target = {LEVERAGED_TICKER: leveraged_weight}
    if bond_ticker:
        target[bond_ticker] = 1.0 - leveraged_weight
    else:
        target["cash"] = 1.0 - leveraged_weight

    shares = {t: 0.0 for t in tickers}
    cash = 0.0
    values: list[float] = []
    rebalance_count = 0
    total_cost = 0.0

    def _current_values(price_row: pd.Series) -> dict[str, float]:
        out = {t: shares[t] * float(price_row[t]) for t in tickers}
        out["cash"] = cash
        return out

    first_row = True
    for dt, price_row in prices.iterrows():
        if first_row:
            current_values = {"cash": initial_value, **{t: 0.0 for t in tickers}}
            gross = initial_value
            cost, _ = _trade_cost(current_values, {**target})
            net = gross - cost
            for t in tickers:
                shares[t] = net * target.get(t, 0.0) / max(float(price_row[t]), 1e-12)
            cash = net * target.get("cash", 0.0)
            total_cost += cost
            rebalance_count += 1
            values.append(net)
            first_row = False
            continue

        current_values = _current_values(price_row)
        gross = sum(current_values.values())
        current_weights = {k: v / gross for k, v in current_values.items()} if gross > 0 else current_values

        needs_rebalance = False
        for t, w in target.items():
            if w <= 0.0:
                continue
            lo, hi = w * (1 - DEVIATION_BAND), w * (1 + DEVIATION_BAND)
            if not (lo <= current_weights.get(t, 0.0) <= hi):
                needs_rebalance = True
                break

        if needs_rebalance:
            target_values = {k: gross * v for k, v in target.items()}
            cost, _ = _trade_cost(current_values, target_values)
            net = max(gross - cost, 0.0)
            for t in tickers:
                shares[t] = net * target.get(t, 0.0) / max(float(price_row[t]), 1e-12)
            cash = net * target.get("cash", 0.0)
            total_cost += cost
            rebalance_count += 1
            gross = net

        values.append(gross)

    return pd.Series(values, index=prices.index, dtype=float), {
        "rebalance_count": int(rebalance_count),
        "transaction_cost": float(total_cost),
    }


def _buy_hold_curve(prices: pd.DataFrame, ticker: str, initial_value: float) -> pd.Series:
    shares = initial_value * (1 - COMMISSION_RATE - SLIPPAGE_RATE) / float(prices[ticker].iloc[0])
    return prices[ticker] * shares


def _trading_dates(db_path: Path, start: str, end: str, ticker: str = "0050.TW") -> pd.DatetimeIndex:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt", [ticker, start, end]
        ).fetchdf()
    finally:
        con.close()
    return pd.DatetimeIndex(pd.to_datetime(rows["dt"]))


def run_window(*, db_path: Path, label: str, start: str, end: str, initial_value: float) -> dict[str, Any]:
    end_resolved = _resolve_end(db_path, end)
    idx = _trading_dates(db_path, start, end_resolved)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, idx)
    total_return_prices = total_return_prices.dropna(subset=[STOCK_TICKER, LEVERAGED_TICKER])

    variants: dict[str, Any] = {}
    for label_name, leveraged_weight, bond_ticker in (
        ("00631l40_00679b60", 0.40, "00679B.TWO"),
        ("00631l50_00679b50", 0.50, "00679B.TWO"),
        ("00631l40_cash60", 0.40, None),
        ("00631l50_cash50", 0.50, None),
    ):
        if bond_ticker is not None and bond_ticker not in total_return_prices.columns:
            continue
        curve, exec_info = _deviation_band_curve(
            total_return_prices, leveraged_weight=leveraged_weight, bond_ticker=bond_ticker, initial_value=initial_value
        )
        metrics = _metrics(curve, initial_value)
        variants[label_name] = {"metrics": metrics, "execution": exec_info}

    bench_0050 = _buy_hold_curve(total_return_prices, STOCK_TICKER, initial_value)
    bench_00631l = _buy_hold_curve(total_return_prices, LEVERAGED_TICKER, initial_value)

    return {
        "window": label,
        "start": start,
        "end": end_resolved,
        "rows": int(len(total_return_prices)),
        "dividend_coverage": dividend_coverage,
        "variants": variants,
        "benchmark_0050_buy_hold": _metrics(bench_0050, initial_value),
        "benchmark_00631l_buy_hold": _metrics(bench_00631l, initial_value),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "letf_bond_deviation_band_rebalance_2103_10157.json"))
    args = parser.parse_args()

    db_path = Path(args.db)
    window_reports = [
        run_window(db_path=db_path, label=label, start=start, end=end, initial_value=float(args.initial_value))
        for label, start, end in WINDOWS
    ]

    report = {
        "schema_version": 1,
        "report_type": "letf_bond_deviation_band_rebalance_test",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2103.10157 (Miller, 2021, Leveraged ETF Investing)",
        "policy": "research_only_no_weight_change",
        "deviation_band": DEVIATION_BAND,
        "window_reports": window_reports,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved: {output}")

    for wr in window_reports:
        print(f"\n=== {wr['window']} ({wr['start']} ~ {wr['end']}, {wr['rows']} rows) ===")
        b50 = wr["benchmark_0050_buy_hold"]
        bl = wr["benchmark_00631l_buy_hold"]
        print(f"  benchmark 0050 buy&hold:    final={b50['final_value']:,.0f} sharpe={b50['sharpe_ratio']:.3f} mdd={b50['max_drawdown']:.4f}")
        print(f"  benchmark 00631L buy&hold:  final={bl['final_value']:,.0f} sharpe={bl['sharpe_ratio']:.3f} mdd={bl['max_drawdown']:.4f}")
        for name, v in wr["variants"].items():
            m = v["metrics"]
            print(f"  {name}: final={m['final_value']:,.0f} sharpe={m['sharpe_ratio']:.3f} mdd={m['max_drawdown']:.4f} rebalances={v['execution']['rebalance_count']}")


if __name__ == "__main__":
    main()
