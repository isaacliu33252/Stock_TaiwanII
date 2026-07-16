#!/usr/bin/env python3
"""Sweep volatility thresholds for the 00631L no-add pre-trade guard.

This is a guard-usability sweep, not a strategy promotion test. It varies the
high-volatility gate thresholds and reports whether any setting would have
encountered actual A21.18 rebalance days where 00631L additions were blocked.
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
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.backtest.backtest_group_a_plus_financial_econometrics import _garch_features
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import DEFAULT_WINDOWS, _parse_windows, _resolve_end_date
from scripts.evaluate.evaluate_group_a_plus_volatility_pretrade_guard import _audit_no_add_guard_events


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_volatility_pretrade_guard_threshold_sweep_20260710.json"
DEFAULT_RATIO_THRESHOLDS = [1.05, 1.10, 1.15, 1.20, 1.25, 1.30]
DEFAULT_PERCENTILE_THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
DEFAULT_REQUIRE_NEGATIVE_5D = [True, False]


def _parse_float_list(raw: str, default: list[float]) -> list[float]:
    if not raw:
        return list(default)
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_bool_list(raw: str | None) -> list[bool]:
    if not raw:
        return list(DEFAULT_REQUIRE_NEGATIVE_5D)
    values: list[bool] = []
    for item in raw.split(","):
        text = item.strip().lower()
        if text in {"1", "true", "yes", "y"}:
            values.append(True)
        elif text in {"0", "false", "no", "n"}:
            values.append(False)
        else:
            raise ValueError(f"Invalid boolean value: {item}")
    return values


def _threshold_gate_frame(
    prices: pd.DataFrame,
    chip_features: pd.DataFrame,
    *,
    ratio_threshold: float,
    percentile_threshold: float,
    require_negative_5d: bool,
) -> pd.DataFrame:
    features = _garch_features(prices, chip_features)
    high_vol = (
        (features["garch_proxy_vol_ratio"] >= float(ratio_threshold))
        | (features["garch_proxy_vol_percentile"] >= float(percentile_threshold))
    )
    if require_negative_5d:
        high_vol = high_vol & (features["return_0050_5d"] < 0.0)
    out = features.copy()
    out["volatility_gate"] = "neutral_vol"
    out.loc[high_vol, "volatility_gate"] = "high_vol_defensive"
    out["high_vol_gate"] = high_vol.astype(bool)
    return out


def _prepare_window(
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
    total_return_prices, _dividend_coverage = _load_total_return_prices(db_path, prices.index)
    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "prices": prices,
        "chip_features": chip_features,
        "total_return_prices": total_return_prices.reindex(frame.index),
        "execution_regime": frame["execution_regime"].astype(str),
        "weights_by_regime": dict(report["base_weights"]),
    }


def evaluate_sweep(
    *,
    windows: list[dict[str, Any]],
    ratio_thresholds: list[float],
    percentile_thresholds: list[float],
    require_negative_5d_values: list[bool],
    initial_value: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ratio in ratio_thresholds:
        for percentile in percentile_thresholds:
            for require_negative_5d in require_negative_5d_values:
                window_results: list[dict[str, Any]] = []
                for window in windows:
                    gate_frame = _threshold_gate_frame(
                        window["prices"],
                        window["chip_features"],
                        ratio_threshold=ratio,
                        percentile_threshold=percentile,
                        require_negative_5d=require_negative_5d,
                    ).reindex(window["execution_regime"].index)
                    audit = _audit_no_add_guard_events(
                        window["total_return_prices"],
                        window["execution_regime"],
                        gate_frame,
                        window["weights_by_regime"],
                        initial_value,
                    )
                    high_vol_days = int((gate_frame["volatility_gate"].fillna("neutral_vol") == "high_vol_defensive").sum())
                    window_results.append(
                        {
                            "label": window["label"],
                            "all_high_vol_days": high_vol_days,
                            "checked_rebalance_days": audit["checked_rebalance_days"],
                            "high_vol_rebalance_days": audit["high_vol_rebalance_days"],
                            "blocked_days": audit["blocked_days"],
                            "blocked_notional": audit["cumulative_blocked_00631l_notional"],
                        }
                    )
                rows.append(
                    {
                        "ratio_threshold": ratio,
                        "percentile_threshold": percentile,
                        "require_negative_5d": require_negative_5d,
                        "total_high_vol_days": int(sum(item["all_high_vol_days"] for item in window_results)),
                        "total_checked_rebalance_days": int(sum(item["checked_rebalance_days"] for item in window_results)),
                        "total_high_vol_rebalance_days": int(sum(item["high_vol_rebalance_days"] for item in window_results)),
                        "total_blocked_days": int(sum(item["blocked_days"] for item in window_results)),
                        "total_blocked_notional": round(float(sum(item["blocked_notional"] for item in window_results)), 2),
                        "window_results": window_results,
                    }
                )
    rows.sort(
        key=lambda item: (
            -int(item["total_blocked_days"]),
            -int(item["total_high_vol_rebalance_days"]),
            int(item["total_high_vol_days"]),
        )
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--windows", default=None, help="Comma-separated label:start:end entries.")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260630.csv")
    parser.add_argument("--ratio-thresholds", default=",".join(str(v) for v in DEFAULT_RATIO_THRESHOLDS))
    parser.add_argument("--percentile-thresholds", default=",".join(str(v) for v in DEFAULT_PERCENTILE_THRESHOLDS))
    parser.add_argument("--require-negative-5d", default="true,false")
    args = parser.parse_args()

    db_path = Path(args.db)
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    prepared_windows = [
        _prepare_window(
            label=label,
            start=start,
            end=end,
            db_path=db_path,
            initial_value=args.initial_value,
            ncf_panel_631l=args.ncf_panel_631l,
        )
        for label, start, end in _parse_windows(args.windows)
    ]
    sweep = evaluate_sweep(
        windows=prepared_windows,
        ratio_thresholds=_parse_float_list(args.ratio_thresholds, DEFAULT_RATIO_THRESHOLDS),
        percentile_thresholds=_parse_float_list(args.percentile_thresholds, DEFAULT_PERCENTILE_THRESHOLDS),
        require_negative_5d_values=_parse_bool_list(args.require_negative_5d),
        initial_value=args.initial_value,
    )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/evaluate/evaluate_group_a_plus_volatility_pretrade_guard_sweep.py",
        "policy": "threshold_sweep_for_pre_trade_no_00631l_add_guard",
        "windows": [item["window"] | {"label": item["label"]} for item in prepared_windows],
        "sweep_count": len(sweep),
        "top_results": sweep[:20],
        "all_results": sweep,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_rows = [
        {key: value for key, value in row.items() if key != "window_results"}
        for row in sweep
    ]
    pd.DataFrame(csv_rows).to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"Wrote {output}")
    print(f"Wrote {output.with_suffix('.csv')}")
    if sweep:
        best = sweep[0]
        print(
            "Best: "
            f"blocked_days={best['total_blocked_days']} "
            f"high_vol_rebalance_days={best['total_high_vol_rebalance_days']} "
            f"high_vol_days={best['total_high_vol_days']} "
            f"ratio={best['ratio_threshold']} "
            f"percentile={best['percentile_threshold']} "
            f"require_negative_5d={best['require_negative_5d']}"
        )


if __name__ == "__main__":
    main()
