#!/usr/bin/env python3
"""Shadow-audit the volatility no-add pre-trade guard for 00631L.

This does not promote a strategy or change target weights. It replays the active
A21.18 regime path and asks how often a high-volatility gate would have blocked
an attempted increase in 00631L exposure at execution time.
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import (
    DEFAULT_WINDOWS,
    _build_volatility_gate_frame,
    _cap_00631l_add,
    _current_weights,
    _parse_windows,
    _resolve_end_date,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_volatility_pretrade_guard_shadow_latest.json"


def _audit_no_add_guard_events(
    prices: pd.DataFrame,
    regimes: pd.Series,
    gate_frame: pd.DataFrame,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
) -> dict[str, Any]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    events: list[dict[str, Any]] = []
    checked_rebalance_days = 0
    high_vol_rebalance_days = 0
    cumulative_blocked_weight = 0.0
    cumulative_blocked_notional = 0.0

    aligned_gate = gate_frame["volatility_gate"].reindex(regimes.index).fillna("neutral_vol")
    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        high_vol = str(aligned_gate.loc[dt]) == "high_vol_defensive"
        if next_regime == current_regime:
            continue

        checked_rebalance_days += 1
        current_w = _current_weights(gross_value, price_row, shares, cash)
        requested_w = _normalize(weights_by_regime[next_regime])
        guarded_w = requested_w
        capped = False
        blocked_weight = 0.0
        if high_vol:
            high_vol_rebalance_days += 1
            guarded_w, capped, blocked_weight = _cap_00631l_add(requested_w, current_w)

        if capped:
            blocked_notional = float(blocked_weight * gross_value)
            cumulative_blocked_weight += float(blocked_weight)
            cumulative_blocked_notional += blocked_notional
            events.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "regime": next_regime,
                    "volatility_gate": str(aligned_gate.loc[dt]),
                    "portfolio_value_before_trade": round(float(gross_value), 2),
                    "current_00631l_weight": round(float(current_w.get("00631L.TW", 0.0)), 6),
                    "requested_00631l_weight": round(float(requested_w.get("00631L.TW", 0.0)), 6),
                    "guarded_00631l_weight": round(float(guarded_w.get("00631L.TW", 0.0)), 6),
                    "blocked_00631l_weight": round(float(blocked_weight), 6),
                    "blocked_00631l_notional": round(blocked_notional, 2),
                }
            )

        current_regime = next_regime
        shares = {
            ticker: gross_value * float(guarded_w.get(ticker, 0.0)) / max(float(price_row[ticker]), 1e-12)
            for ticker in TICKERS
        }
        cash = gross_value * float(guarded_w.get("cash", 0.0))

    return {
        "checked_rebalance_days": int(checked_rebalance_days),
        "high_vol_rebalance_days": int(high_vol_rebalance_days),
        "blocked_days": int(len(events)),
        "cumulative_blocked_00631l_weight": round(float(cumulative_blocked_weight), 6),
        "cumulative_blocked_00631l_notional": round(float(cumulative_blocked_notional), 2),
        "events": events,
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip_features = _load_chip_features(db_path, prices.index, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)
    gate_frame = _build_volatility_gate_frame(prices, chip_features).reindex(frame.index)
    weights_by_regime = dict(report["base_weights"])
    execution_regime = frame["execution_regime"].astype(str)
    audit = _audit_no_add_guard_events(
        total_return_prices.reindex(execution_regime.index),
        execution_regime,
        gate_frame,
        weights_by_regime,
        initial_value,
    )
    high_vol_days = int((gate_frame["volatility_gate"].fillna("neutral_vol") == "high_vol_defensive").sum())
    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(execution_regime))},
        "policy": "pre_trade_no_00631l_add_only_no_target_weight_change",
        "gate_counts": {
            "all_high_vol_days": high_vol_days,
            "high_vol_rebalance_days": audit["high_vol_rebalance_days"],
        },
        "audit": audit,
        "baseline": {
            "final_value": report["metrics"].get("final_value"),
            "max_drawdown": report["metrics"].get("max_drawdown"),
            "rebalance_count": report["execution"].get("rebalance_count"),
        },
        "dividend_coverage": dividend_coverage,
    }


def _write_csv(path: Path, windows: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for window in windows:
        for event in window["audit"]["events"]:
            rows.append({"window": window["label"], **event})
    columns = [
        "window",
        "date",
        "regime",
        "volatility_gate",
        "portfolio_value_before_trade",
        "current_00631l_weight",
        "requested_00631l_weight",
        "guarded_00631l_weight",
        "blocked_00631l_weight",
        "blocked_00631l_notional",
    ]
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--windows", default=None, help="Comma-separated label:start:end entries.")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260630.csv")
    args = parser.parse_args()

    db_path = Path(args.db)
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    windows = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            db_path=db_path,
            initial_value=args.initial_value,
            ncf_panel_631l=args.ncf_panel_631l,
        )
        for label, start, end in _parse_windows(args.windows)
    ]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard.py",
        "policy": "pre_trade_no_00631l_add_only_no_target_weight_change",
        "windows": windows,
        "totals": {
            "blocked_days": int(sum(window["audit"]["blocked_days"] for window in windows)),
            "cumulative_blocked_00631l_notional": round(
                float(sum(window["audit"]["cumulative_blocked_00631l_notional"] for window in windows)),
                2,
            ),
        },
    }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_csv(output.with_suffix(".csv"), windows)
    print(f"Wrote {output}")
    print(f"Wrote {output.with_suffix('.csv')}")
    print(f"Blocked days: {summary['totals']['blocked_days']}")


if __name__ == "__main__":
    main()
