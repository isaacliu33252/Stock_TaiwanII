#!/usr/bin/env python3
"""Backtest GroupA+'s latest production strategy vs. golden1_0531 across five crises.

Two curves per crisis fold:

- ``latest_strategy``: the current production base regime logic -- the A21.11
  switch rule (``group_a_plus.runners.a2111._build_switch_rule``: MA100,
  tight entry_gap=0.003, exit_gap=0.010, bond30_cash30 defensive basket) plus
  the recovery-ramp overlay (``_recovery_ramp_regime``) and a2118's
  chip-data-staleness fallback (``chip_data_fallback_max_stale_days=10``).
  This is a2118 *minus* its NCF late-bull overlay, because that overlay needs
  a trained NCF panel and no NCF model exists (or could honestly exist,
  without lookahead) for 2008/2011/2015/2018 -- a2118's own module docstring
  states its "historical regime" is identical to A21.11 whenever no panel is
  supplied. golden1 weights are resolved the same way `run_a2118`/`run_a2111`
  resolve them live: newest-mtime ``results/signal_group_a_*.json`` (a known
  drift caveat, see H3 in the 2026-07-02 Fable 5 audit -- this replays every
  fold under *today's* golden1 weights, not the historical ones).
- ``golden1_0531``: buy-and-hold the frozen 2026-05-31 golden1 allocation
  (``results/signal_group_a_golden1_0531_predict_20260615_from_all_20260613_
  total1000000.json``, GroupA+'s ``DEFAULT_GOLDEN_SIGNAL``) for the entire
  window, no switching at all -- the same baseline curve every existing
  switch-policy backtest in this repo calls ``golden1_0531_1m``.

Both curves reuse ``_simulate_regime_curve`` (no transaction costs, no
total-return/dividend adjustment) rather than a2118's costed
``_simulate_costed_curve``, because ``total_return_index_data`` (the real
dividend table) only has coverage from 2025-01-02 onward -- it does not exist
for any of these five historical windows. This matches the existing
2008/2011/2020 GARCH-specialist-routing fold scripts' precedent exactly.

Five folds:
  2008    -- TWII proxy (results/twii_proxy_2008_prepared_20260705_*)
  2011    -- TWII proxy (results/twii_proxy_2011_2014_prepared_20260705_*)
  2015    -- real ETF OHLCV (results/real_2015_china_crash_prepared_20260706_*)
  2018    -- TWII proxy (results/twii_proxy_2018_trade_war_prepared_20260706_*)
  2020    -- real ETF OHLCV, loaded directly from stock_data.db (same
             ``_load_real_prices_with_00679b_backfill`` technique as
             scripts/misc/garch_specialist_routing_2020_fold_20260705.py)

Research-only. Does not touch any production file, model weight, live
signal, or allocation. Read-only against stock_data.db.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS, _recovery_ramp_regime
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _metrics, _simulate_regime_curve, _switch_returns
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INITIAL_VALUE = 1_000_000.0
CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10  # matches a2118's own default

FOLDS: dict[str, dict[str, Any]] = {
    "2008_gfc": {
        "label": "2008 Global Financial Crisis (TWII proxy)",
        "prices_csv": "results/twii_proxy_2008_prepared_20260705_prices.csv",
        "chip_csv": "results/twii_proxy_2008_prepared_20260705_chip_features.csv",
        "report_start": "2007-10-01",
        "report_end": None,  # None = end of available data
    },
    "2011_euro_debt": {
        "label": "2011 European Sovereign Debt Crisis (TWII proxy)",
        "prices_csv": "results/twii_proxy_2011_2014_prepared_20260705_prices.csv",
        "chip_csv": "results/twii_proxy_2011_2014_prepared_20260705_chip_features.csv",
        "report_start": "2011-07-01",
        "report_end": None,
    },
    "2015_china_crash": {
        "label": "2015 China A-Share Crash + 2016-01 Circuit Breaker (real ETF data)",
        "prices_csv": "results/real_2015_china_crash_prepared_20260706_prices.csv",
        "chip_csv": "results/real_2015_china_crash_prepared_20260706_chip_features.csv",
        "report_start": "2015-06-01",
        "report_end": None,
    },
    "2018_trade_war": {
        "label": "2018 US-China Trade War (TWII proxy)",
        "prices_csv": "results/twii_proxy_2018_trade_war_prepared_20260706_prices.csv",
        "chip_csv": "results/twii_proxy_2018_trade_war_prepared_20260706_chip_features.csv",
        "report_start": "2018-01-01",
        "report_end": None,
    },
    "2020_covid": {
        "label": "2020 COVID Crash (real ETF data, loaded directly from DB)",
        "prices_csv": None,
        "chip_csv": None,
        "report_start": "2020-01-01",
        "report_end": "2020-12-31",
    },
}


def _load_real_2020_prices_with_00679b_backfill(db_path: Path, start: str, end: str) -> pd.DataFrame:
    """Real OHLCV for all four tickers; 00679B.TWO (real from 2020-01-02 only)
    is back-filled flat for the pre-2020 lead-in gap only -- bfill() fills
    from the first real value *present in this query's own date range*, so
    real 2020 00679B prices (which this fold's test window actually needs)
    are used as-is, not flattened. (Fixed 2026-07-06: an earlier version of
    this function unconditionally overwrote the whole column with the
    first-ever real price, flattening 00679B for the 2020 test window too,
    not just the pre-2020 lead-in -- see the risk-score-lookback basket
    sweep session for how this was caught: bond30_cash30 and bond40 produced
    bit-identical 2020 metrics despite different 00679B weights, which is
    only possible if 00679B carried zero real variance that year.)
    """
    tickers = list(TICKERS)
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    prices.index = pd.to_datetime(prices.index)
    if "00679B.TWO" in prices.columns:
        prices["00679B.TWO"] = prices["00679B.TWO"].bfill()
    return prices.dropna(subset=tickers)


def _load_fold_data(name: str, spec: dict[str, Any], db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if name == "2020_covid":
        prices = _load_real_2020_prices_with_00679b_backfill(db_path, "2015-01-05", "2020-12-31")
        chip_features = _load_chip_features(db_path, prices.index, "2015-01-05", "2020-12-31")
        return prices, chip_features

    prices_path = PROJECT_ROOT / spec["prices_csv"]
    chip_path = PROJECT_ROOT / spec["chip_csv"]
    prices = pd.read_csv(prices_path, index_col=0, parse_dates=True)
    chip_features = pd.read_csv(chip_path, index_col=0, parse_dates=True)
    return prices, chip_features


def _trim(series: pd.Series, start: str, end: str | None) -> pd.Series:
    if end is None:
        return series.loc[start:]
    return series.loc[start:end]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/group_a_plus_latest_vs_golden1_0531_five_crises_20260706.json")
    args = parser.parse_args()

    db_path = _resolve(str(DB_PATH))

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(str(DEFAULT_DECISION_POINTER)))
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])

    latest_golden_signal_path = _resolve_golden_signal_path()
    latest_golden_signal = _load(latest_golden_signal_path)
    latest_golden_weights = _normalize(_weights_from_group_a(latest_golden_signal))

    golden1_0531_path = _resolve(str(DEFAULT_GOLDEN_SIGNAL))
    golden1_0531_signal = _load(golden1_0531_path)
    golden1_0531_weights = _normalize(_weights_from_group_a(golden1_0531_signal))

    switch_rule = _build_switch_rule()

    results: dict[str, Any] = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "backtest GroupA+'s latest production strategy (A21.11 base regime, no NCF overlay) vs. frozen golden1_0531 buy-and-hold, across five historical crises",
        "inputs": {
            "latest_golden_signal_path": str(latest_golden_signal_path.relative_to(PROJECT_ROOT)),
            "latest_golden_weights": latest_golden_weights,
            "golden1_0531_path": str(golden1_0531_path.relative_to(PROJECT_ROOT)) if golden1_0531_path.is_absolute() else str(golden1_0531_path),
            "golden1_0531_weights": golden1_0531_weights,
            "current_defensive_weights": current_defensive,
            "policy_signal_path": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "switch_rule": switch_rule.name,
            "chip_data_fallback_max_stale_days": CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        },
        "folds": {},
    }

    for name, spec in FOLDS.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)

        events, frame = _switch_returns(
            prices,
            chip_features,
            switch_rule,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        )
        execution_regime = _recovery_ramp_regime(frame["regime"], frame)
        weights_by_regime = {
            "golden1": latest_golden_weights,
            "group_a_plus_defensive": basket,
            "group_a_plus_recovery": current_defensive,
        }
        latest_curve = _simulate_regime_curve(prices, execution_regime, weights_by_regime, INITIAL_VALUE)

        golden_regime = pd.Series("golden1", index=prices.index)
        golden_curve = _simulate_regime_curve(
            prices, golden_regime, {"golden1": golden1_0531_weights}, INITIAL_VALUE
        )

        report_start = spec["report_start"]
        report_end = spec["report_end"]
        latest_report_curve = _trim(latest_curve, report_start, report_end)
        golden_report_curve = _trim(golden_curve, report_start, report_end)

        defensive_days = int((execution_regime.loc[latest_report_curve.index] == "group_a_plus_defensive").sum())
        recovery_days = int((execution_regime.loc[latest_report_curve.index] == "group_a_plus_recovery").sum())
        switch_events_in_window = [
            e for e in events
            if pd.Timestamp(report_start) <= pd.Timestamp(e["date"]) <= (pd.Timestamp(report_end) if report_end else prices.index[-1])
        ]

        results["folds"][name] = {
            "label": spec["label"],
            "data_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
            "report_window": {
                "start": str(latest_report_curve.index[0].date()),
                "end": str(latest_report_curve.index[-1].date()),
                "rows": int(len(latest_report_curve)),
            },
            "latest_strategy": {
                "metrics": _metrics(latest_report_curve, float(latest_report_curve.iloc[0])),
                "defensive_days": defensive_days,
                "recovery_days": recovery_days,
                "switch_event_count": len(switch_events_in_window),
            },
            "golden1_0531": {
                "metrics": _metrics(golden_report_curve, float(golden_report_curve.iloc[0])),
            },
        }

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Output: {output_path}")
    print()
    header = f"{'Fold':<20} {'Strategy':<16} {'Final Value':>14} {'Total Ret':>10} {'Sharpe':>8} {'MDD':>8} {'Defense d':>10}"
    print(header)
    print("-" * len(header))
    for name, fold in results["folds"].items():
        for strategy_key, strategy_label in (("latest_strategy", "latest"), ("golden1_0531", "golden1_0531")):
            m = fold[strategy_key]["metrics"]
            defense_d = fold[strategy_key].get("defensive_days", "-")
            print(
                f"{name:<20} {strategy_label:<16} {m['final_value']:>14,.0f} "
                f"{m['total_return']:>10.2%} {m['sharpe_ratio']:>8.3f} {m['max_drawdown']:>8.2%} {str(defense_d):>10}"
            )


if __name__ == "__main__":
    main()
