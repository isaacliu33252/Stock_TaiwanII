#!/usr/bin/env python3
"""News anomaly overlay tests for GroupA+ inspired by Fincept news signals."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

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
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from tw_output_standard import OutputStandardizer, write_standard_output


PROJECT_ROOT = Path(__file__).resolve().parent
NEWS_DIR = PROJECT_ROOT / "news"

A207_RULE = SwitchRule(
    "risk_ma75_dd11_total6_hold5_eg0175_xg020",
    75,
    -0.0175,
    0.02,
    75,
    -0.11,
    5,
    5,
    0,
    None,
    0,
    None,
    6,
    6,
)
MA20_RULE = SwitchRule("ma20_dd7_hold5", 20, -0.03, 0.01, 20, -0.07, 5, 5)

RISK_TERMS = {
    "風險", "衰退", "危機", "恐慌", "戰爭", "制裁", "關稅", "通膨", "升息", "違約",
    "流動性", "地緣", "崩跌", "暴跌", "賣壓", "利空", "下修", "虧損", "裁員", "封鎖",
    "risk", "recession", "crisis", "panic", "war", "tariff", "inflation", "hawkish",
    "default", "selloff", "slump", "downgrade", "weak",
}
MARKET_TERMS = {
    "台股", "大盤", "加權指數", "0050", "00631l", "00632r", "etf", "外資", "投信",
    "自營商", "融資", "融券", "台積電", "半導體", "ai", "美股", "那斯達克", "標普",
    "聯準會", "fed", "fomc", "利率", "匯率", "美元", "美債",
}


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _read_news_records(news_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(news_dir.glob("ltn_mainstream_*.jsonl")):
        if path.name.endswith("_market.jsonl"):
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("date") and payload.get("title"):
                    records.append(payload)
    return records


def _contains_any(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _news_features(news_dir: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    category_counter: Counter[str] = Counter()
    for item in _read_news_records(news_dir):
        dt = pd.to_datetime(item.get("date"), errors="coerce")
        if pd.isna(dt):
            continue
        text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('category', '')}"
        market = _contains_any(text, MARKET_TERMS)
        risk = _contains_any(text, RISK_TERMS)
        if not market and not risk:
            continue
        category = str(item.get("category", ""))
        category_counter[category] += 1
        rows.append(
            {
                "dt": dt.normalize(),
                "news_count": 1,
                "market_news_count": int(market),
                "risk_news_count": int(risk),
                "risk_market_news_count": int(risk and market),
            }
        )
    if not rows:
        return pd.DataFrame(0.0, index=index, columns=["news_count", "risk_news_count", "risk_news_z", "risk_news_intensity"])
    daily = pd.DataFrame(rows).groupby("dt").sum().sort_index()
    daily = daily.reindex(index.normalize()).fillna(0.0)
    daily.index = index
    risk = daily["risk_news_count"].astype(float)
    mean = risk.rolling(60, min_periods=20).mean()
    std = risk.rolling(60, min_periods=20).std().replace(0.0, math.nan)
    daily["risk_news_z"] = ((risk - mean) / std).replace([math.inf, -math.inf], math.nan).fillna(0.0)
    daily["risk_news_intensity"] = (daily["risk_news_count"] / daily["news_count"].replace(0.0, math.nan)).fillna(0.0)
    daily["risk_market_news_z"] = (
        (daily["risk_market_news_count"] - daily["risk_market_news_count"].rolling(60, min_periods=20).mean())
        / daily["risk_market_news_count"].rolling(60, min_periods=20).std().replace(0.0, math.nan)
    ).replace([math.inf, -math.inf], math.nan).fillna(0.0)
    return daily


def _selector_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    ma20_regime: pd.Series,
    z_threshold: float,
    min_count: int,
    max_return_5d: float,
) -> pd.DataFrame:
    trigger = (
        (features["risk_news_z"] >= z_threshold)
        & (features["risk_news_count"] >= min_count)
        & (features["return_0050_5d"] <= max_return_5d)
    )
    frame = features.copy()
    frame["news_trigger"] = trigger.astype(int)
    frame["regime"] = a207_regime.copy()
    frame.loc[trigger, "regime"] = ma20_regime.loc[trigger]
    return frame


def _guard_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    z_threshold: float,
    min_count: int,
    max_return_5d: float,
    min_hold_days: int,
) -> pd.DataFrame:
    in_guard = False
    hold = 0
    regimes = []
    events = []
    for dt, row in features.iterrows():
        trigger = (
            float(row["risk_news_z"]) >= z_threshold
            and int(row["risk_news_count"]) >= min_count
            and float(row["return_0050_5d"]) <= max_return_5d
        )
        exit_ = float(row["risk_news_z"]) < 0.5 and float(row["return_0050_5d"]) >= 0.0
        if in_guard:
            hold += 1
            if hold >= min_hold_days and exit_:
                in_guard = False
                hold = 0
        elif trigger:
            in_guard = True
            hold = 1
            events.append({"date": str(dt.date()), "risk_news_z": float(row["risk_news_z"]), "risk_news_count": int(row["risk_news_count"])})
        regimes.append("group_a_plus_defensive" if in_guard else str(a207_regime.loc[dt]))
    frame = features.copy()
    frame["news_trigger"] = 0
    if events:
        event_dates = {pd.Timestamp(event["date"]) for event in events}
        frame.loc[frame.index.normalize().isin(event_dates), "news_trigger"] = 1
    frame["regime"] = regimes
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--news-dir", default=str(NEWS_DIR))
    parser.add_argument("--z-thresholds", default="1.0,1.5,2.0")
    parser.add_argument("--min-counts", default="2,4,6")
    parser.add_argument("--max-return-5d", default="0.0,-0.02,-0.04")
    parser.add_argument("--min-hold-days", default="3,5,10")
    parser.add_argument("--output-prefix", default="results/group_a_plus_news_anomaly_20260619")
    args = parser.parse_args()
    std = OutputStandardizer("backtest_group_a_plus_news_anomaly.py")

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    weights_by_regime = {"golden1": golden_weights, "group_a_plus_defensive": defensive_weights}
    a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
    base_curves = {
        "a207": _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value),
        "ma20": _simulate_regime_curve(prices, ma20_frame["regime"], weights_by_regime, args.initial_value),
    }
    features = _news_features(Path(args.news_dir), prices.index)
    features["return_0050_5d"] = prices["0050.TW"].pct_change(5).fillna(0.0)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for z in _parse_float_list(args.z_thresholds):
        for min_count in _parse_int_list(args.min_counts):
            for max_ret in _parse_float_list(args.max_return_5d):
                selector_label = f"news_selector_z{int(z*10):02d}_c{min_count}_r{int(abs(max_ret)*100):02d}"
                frame = _selector_regime(features, a207_frame["regime"], ma20_frame["regime"], z, min_count, max_ret)
                curve = _simulate_regime_curve(prices, frame["regime"], weights_by_regime, args.initial_value)
                rows.append(
                    {
                        "variant": selector_label,
                        "mode": "selector",
                        **_metrics(curve, args.initial_value),
                        "z_threshold": z,
                        "min_count": min_count,
                        "max_return_5d": max_ret,
                        "min_hold_days": 0,
                        "trigger_days": int(frame["news_trigger"].sum()),
                        "override_days": int((frame["regime"] != a207_frame["regime"]).sum()),
                        "defense_days": int((frame["regime"] == "group_a_plus_defensive").sum()),
                    }
                )
                frames[selector_label] = frame
                for hold in _parse_int_list(args.min_hold_days):
                    guard_label = f"news_guard_z{int(z*10):02d}_c{min_count}_r{int(abs(max_ret)*100):02d}_h{hold}"
                    guard = _guard_regime(features, a207_frame["regime"], z, min_count, max_ret, hold)
                    curve = _simulate_regime_curve(prices, guard["regime"], weights_by_regime, args.initial_value)
                    rows.append(
                        {
                            "variant": guard_label,
                            "mode": "guard",
                            **_metrics(curve, args.initial_value),
                            "z_threshold": z,
                            "min_count": min_count,
                            "max_return_5d": max_ret,
                            "min_hold_days": hold,
                            "trigger_days": int(guard["news_trigger"].sum()),
                            "override_days": int((guard["regime"] != a207_frame["regime"]).sum()),
                            "defense_days": int((guard["regime"] == "group_a_plus_defensive").sum()),
                        }
                    )
                    frames[guard_label] = guard

    summary = {name: _metrics(curve, args.initial_value) for name, curve in base_curves.items()}
    ranked = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]), reverse=True)
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_news_anomaly_overlay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "actual_window": {"start": str(prices.index[0].date()), "end": str(prices.index[-1].date()), "rows": int(len(prices))},
        "inputs": {"policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)), "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT))},
        "rules": {"a207": asdict(A207_RULE), "ma20": asdict(MA20_RULE)},
        "summary": summary,
        "rows": rows,
        "best_by_sharpe": ranked[:10],
        "best": best,
        "news_feature_summary": {
            "total_news_count": int(features["news_count"].sum()),
            "total_risk_news_count": int(features["risk_news_count"].sum()),
            "max_risk_news_z": float(features["risk_news_z"].max()),
        },
    }
    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    curve_path = prefix.with_name(prefix.name + "_curve.csv")
    best_frame_path = prefix.with_name(prefix.name + "_best_frame.csv")
    write_standard_output(std.success(report), str(json_path))
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(base_curves).to_csv(curve_path, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(best_frame_path, encoding="utf-8-sig")
    print(f"JSON: {json_path}")
    print(f"Best: {best['variant']} final={best['final_value']:,.0f}, sharpe={best['sharpe_ratio']:.3f}, mdd={best['max_drawdown']:.2%}")


if __name__ == "__main__":
    main()
