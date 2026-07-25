#!/usr/bin/env python3
"""Evaluate SRR-lite crash-watch overlap with other shadow-style risk proxies.

Research-only. This script does not change live signals, target weights, or
strategy manifests. It uses SRR-lite's historical frame, then adds same-day
diagnostic proxies for tail risk, volatility regime, and 00631L compounding
regime so we can test whether SRR-lite is useful alone or only when confirmed
by another shadow.
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

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.leveraged_compounding_regime import (
    CompoundingRegimeThresholds,
    build_compounding_features,
    classify_compounding_regime,
)
from scripts.evaluate.evaluate_srr_lite_shadow import (
    _score_forward_summary_for_signal,
    build_srr_lite_backtest,
)
from group_a_plus.integrations.srr_lite_shadow import DEFAULT_SYMBOLS, _load_close_panel_from_db


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "srr_lite_ensemble_shadow_latest.json"


def _vol_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    def pct_rank(values: pd.Series) -> float:
        clean = pd.to_numeric(values, errors="coerce").dropna()
        if clean.empty:
            return float("nan")
        return float((clean <= clean.iloc[-1]).mean())

    return series.rolling(window, min_periods=max(60, window // 4)).apply(pct_rank, raw=False)


def _add_tail_proxy(frame: pd.DataFrame, close_631l: pd.Series) -> pd.Series:
    close = close_631l.reindex(frame.index).astype(float)
    ret5 = close.pct_change(5, fill_method=None)
    returns = close.pct_change(fill_method=None)
    vol20 = returns.rolling(20, min_periods=10).std()
    vol60 = returns.rolling(60, min_periods=20).std()
    drawdown252 = close / close.rolling(252, min_periods=40).max() - 1.0
    vol_ratio = vol20 / vol60.replace(0.0, pd.NA)
    return (
        (ret5 < -0.08)
        | (drawdown252 < -0.14)
        | (vol_ratio > 1.60)
    ).reindex(frame.index).fillna(False).astype(bool)


def _add_garch_proxy(frame: pd.DataFrame, close_0050: pd.Series) -> pd.Series:
    close = close_0050.reindex(frame.index).astype(float)
    returns = close.pct_change(fill_method=None)
    vol20 = returns.rolling(20, min_periods=10).std()
    vol60 = returns.rolling(60, min_periods=20).std()
    ratio = vol20 / vol60.replace(0.0, pd.NA)
    percentile = _vol_percentile(vol20)
    ret5 = close.pct_change(5, fill_method=None)
    return (
        ((ratio >= 1.05) | (percentile >= 0.70))
        & (ret5 < 0.0)
    ).reindex(frame.index).fillna(False).astype(bool)


def _add_compounding_proxy(frame: pd.DataFrame, prices: pd.DataFrame) -> pd.Series:
    close_631l = prices["00631L.TW"].reindex(frame.index).astype(float)
    close_0050 = prices["0050.TW"].reindex(frame.index).astype(float)
    features = build_compounding_features(close_631l, close_0050)
    thresholds = CompoundingRegimeThresholds(
        ar1_revert_max=-0.15,
        mean_reversion_score_min=5,
    )
    classified = classify_compounding_regime(features, thresholds=thresholds)
    return (
        classified["compounding_regime"].eq("MEAN_REVERTING")
        & (classified["rolling_AR1_20d"] <= -0.15)
    ).reindex(frame.index).fillna(False).astype(bool)


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_forward_summary_for_signal(frame, signal, 5),
        "h10": _score_forward_summary_for_signal(frame, signal, 10),
    }


def build_ensemble_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    load_lookback_days: int,
    corr_window: int,
    baseline_window: int,
    underperform_threshold: float,
    mdd_threshold: float,
    cross_market_frame: Path | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    srr_report, frame = build_srr_lite_backtest(
        db_path=db_path,
        start=start,
        end=end,
        symbols=DEFAULT_SYMBOLS,
        load_lookback_days=load_lookback_days,
        corr_window=corr_window,
        baseline_window=baseline_window,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )
    prices = _load_close_panel_from_db(
        db_path,
        symbols=DEFAULT_SYMBOLS,
        end_date=pd.Timestamp(end).normalize(),
        lookback_days=load_lookback_days,
    ).sort_index()
    if prices.empty:
        raise RuntimeError("No prices loaded for ensemble evaluation")

    frame = frame.copy()
    frame["tail_proxy_active"] = _add_tail_proxy(frame, prices["00631L.TW"])
    frame["garch_proxy_high_vol_active"] = _add_garch_proxy(frame, prices["0050.TW"])
    frame["compounding_mean_reverting_active"] = _add_compounding_proxy(frame, prices)
    if cross_market_frame is not None:
        cm = pd.read_csv(cross_market_frame, parse_dates=["date"]).set_index("date").sort_index()
        frame["cross_market_no_add_active"] = (
            cm["no_add_active"].astype(bool).reindex(frame.index, fill_value=False).astype(bool)
            if "no_add_active" in cm
            else False
        )
        frame["cross_market_prob_NO_ADD"] = (
            cm["prob_NO_ADD"].reindex(frame.index) if "prob_NO_ADD" in cm else pd.NA
        )
        frame["cross_market_prob_REENTER"] = (
            cm["prob_REENTER"].reindex(frame.index) if "prob_REENTER" in cm else pd.NA
        )
    else:
        frame["cross_market_no_add_active"] = False
        frame["cross_market_prob_NO_ADD"] = pd.NA
        frame["cross_market_prob_REENTER"] = pd.NA
    frame["other_shadow_votes"] = (
        frame[
            [
                "tail_proxy_active",
                "garch_proxy_high_vol_active",
                "compounding_mean_reverting_active",
                "cross_market_no_add_active",
            ]
        ]
        .astype(int)
        .sum(axis=1)
    )
    frame["ensemble_srr_crash_and_any_other"] = frame["crash_watch_active"] & (frame["other_shadow_votes"] >= 1)
    frame["ensemble_srr_crash_and_tail"] = frame["crash_watch_active"] & frame["tail_proxy_active"]
    frame["ensemble_srr_crash_and_garch"] = frame["crash_watch_active"] & frame["garch_proxy_high_vol_active"]
    frame["ensemble_srr_crash_and_compounding"] = (
        frame["crash_watch_active"] & frame["compounding_mean_reverting_active"]
    )
    frame["ensemble_srr_crash_and_cross_market"] = (
        frame["crash_watch_active"] & frame["cross_market_no_add_active"]
    )
    frame["ensemble_srr_noadd_or_crash_confirmed"] = frame["no_add_active"] | frame[
        "ensemble_srr_crash_and_any_other"
    ]

    signals = {
        "srr_no_add_active": frame["no_add_active"],
        "srr_crash_watch_active": frame["crash_watch_active"],
        "tail_proxy_active": frame["tail_proxy_active"],
        "garch_proxy_high_vol_active": frame["garch_proxy_high_vol_active"],
        "compounding_mean_reverting_active": frame["compounding_mean_reverting_active"],
        "cross_market_no_add_active": frame["cross_market_no_add_active"],
        "ensemble_srr_crash_and_any_other": frame["ensemble_srr_crash_and_any_other"],
        "ensemble_srr_crash_and_tail": frame["ensemble_srr_crash_and_tail"],
        "ensemble_srr_crash_and_garch": frame["ensemble_srr_crash_and_garch"],
        "ensemble_srr_crash_and_compounding": frame["ensemble_srr_crash_and_compounding"],
        "ensemble_srr_crash_and_cross_market": frame["ensemble_srr_crash_and_cross_market"],
        "ensemble_srr_noadd_or_crash_confirmed": frame["ensemble_srr_noadd_or_crash_confirmed"],
    }
    summary = {name: _summarize_signal(frame, signal) for name, signal in signals.items()}

    report = {
        "report_type": "srr_lite_ensemble_shadow_backtest",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": srr_report["window"],
        "policy": "shadow_only_no_weight_change",
        "parameters": {
            "srr_lite": srr_report["parameters"],
            "tail_proxy": "ret5<-8% or drawdown252<-14% or vol20/vol60>1.60",
            "garch_proxy": "0050 vol20/vol60>=1.05 or vol20 percentile>=70%, and 0050 ret5<0",
            "compounding_proxy": "MEAN_REVERTING with rolling_AR1_20d<=-0.15 and mean_reversion_score>=5",
            "cross_market_frame": str(cross_market_frame) if cross_market_frame is not None else None,
            "cross_market_proxy": "cross-market graph no_add_active from optional prediction frame",
        },
        "summary": summary,
        "interpretation": (
            "This evaluates overlap quality only. The non-SRR columns are lightweight historical "
            "proxies for existing shadow ideas, not a promotion to live execution guards."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--load-lookback-days", type=int, default=900)
    parser.add_argument("--corr-window", type=int, default=7)
    parser.add_argument("--baseline-window", type=int, default=60)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--cross-market-frame")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_ensemble_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        load_lookback_days=int(args.load_lookback_days),
        corr_window=int(args.corr_window),
        baseline_window=int(args.baseline_window),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
        cross_market_frame=Path(args.cross_market_frame) if args.cross_market_frame else None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    compact = {
        key: {
            "active_days": value["active_days"],
            "h10_precision": value["h10"]["confusion"]["precision"],
            "h10_recall": value["h10"]["confusion"]["recall"],
            "h10_fpr": value["h10"]["confusion"]["false_positive_rate"],
        }
        for key, value in report["summary"].items()
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
