#!/usr/bin/env python3
"""FinGPT-inspired multi-horizon sentiment alignment overlay for GroupA+."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
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
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from backtest_group_a_plus_news_anomaly import A207_RULE
from build_llm_sentiment_features import score_text_rule_based


PROJECT_ROOT = Path(__file__).resolve().parent
NEWS_DIR = PROJECT_ROOT / "news"

MARKET_TERMS = {
    "台股", "大盤", "加權指數", "0050", "00631l", "00632r", "etf", "外資", "投信",
    "自營商", "融資", "融券", "台積電", "半導體", "晶片", "ai", "美股", "那斯達克",
    "標普", "聯準會", "fed", "fomc", "利率", "匯率", "美元", "美債", "taiwan",
    "tsmc", "semiconductor", "nasdaq", "s&p",
}
EVENT_TERMS = {
    "macro_rates": {
        "升息", "降息", "通膨", "衰退", "聯準會", "fed", "fomc", "殖利率", "利率",
        "inflation", "recession", "hawkish", "rate hike", "yield",
    },
    "fx_liquidity": {
        "匯率", "新台幣", "美元", "流動性", "融資", "斷頭", "違約", "美元荒",
        "currency", "liquidity", "margin call", "default",
    },
    "semiconductor": {
        "台積電", "半導體", "晶片", "先進製程", "出口管制", "禁令", "tsmc",
        "semiconductor", "chip", "export control", "restriction",
    },
    "geopolitics": {
        "戰爭", "軍演", "制裁", "關稅", "地緣", "封鎖", "衝突", "war", "sanction",
        "tariff", "geopolitical", "blockade", "conflict",
    },
}


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _read_jsonl(path: Path, source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(
                {
                    "date": payload.get("date") or payload.get("pub_date"),
                    "title": payload.get("title") or payload.get("headline") or "",
                    "summary": payload.get("snippet") or payload.get("description") or payload.get("summary") or "",
                    "category": payload.get("category") or "",
                    "url": payload.get("url") or payload.get("link") or "",
                    "source": payload.get("source") or source,
                }
            )
    return records


def _read_csv(path: Path, source: str) -> list[dict[str, Any]]:
    try:
        table = pd.read_csv(path)
    except (pd.errors.EmptyDataError, UnicodeDecodeError):
        return []
    records: list[dict[str, Any]] = []
    for row in table.to_dict("records"):
        records.append(
            {
                "date": row.get("date") or row.get("pub_date") or row.get("published_at"),
                "title": row.get("title") or row.get("headline") or "",
                "summary": row.get("description") or row.get("summary") or row.get("snippet") or "",
                "category": row.get("category") or "",
                "url": row.get("link") or row.get("url") or "",
                "source": row.get("source") or source,
            }
        )
    return records


def _load_news_records(news_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    files: list[str] = []
    for path in sorted(news_dir.glob("ltn_mainstream_*.jsonl")):
        raw.extend(_read_jsonl(path, "ltn"))
        files.append(str(path))
    for path in sorted(news_dir.glob("gdelt*.csv")):
        raw.extend(_read_csv(path, "gdelt"))
        files.append(str(path))

    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in raw:
        date = pd.to_datetime(record.get("date"), errors="coerce")
        title = str(record.get("title", "")).strip()
        url = str(record.get("url", "")).strip()
        if pd.isna(date) or not title:
            continue
        key = (str(date.date()), url or title, title)
        normalized = dict(record)
        normalized["date"] = str(date.date())
        normalized["source"] = "gdelt" if str(record.get("source", "")).lower() == "gdelt" else "ltn"
        deduped[key] = normalized

    records = list(deduped.values())
    return records, {
        "files_scanned": len(files),
        "raw_rows": len(raw),
        "deduped_rows": len(records),
        "files": files,
    }


def _score_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        text = " ".join(
            str(record.get(field, "")).strip()
            for field in ("title", "summary", "category")
            if str(record.get(field, "")).strip()
        )
        if not _contains_any(text, MARKET_TERMS):
            continue
        score = score_text_rule_based(text)
        event_hits = {
            event: int(_contains_any(text, terms))
            for event, terms in EVENT_TERMS.items()
        }
        event_risk = min(1.0, sum(event_hits.values()) / 3.0)
        risk_score = max(float(score["llm_risk_off_score"]), event_risk)
        rows.append(
            {
                "date": pd.Timestamp(record["date"]),
                "source": str(record["source"]),
                "sentiment": float(score["llm_sentiment_score"]),
                "risk_score": risk_score,
                "concern": int(risk_score >= 0.25 or float(score["llm_sentiment_score"]) < 0.0),
                **event_hits,
            }
        )
    return pd.DataFrame(rows)


def _rolling_ratio(numerator: pd.Series, denominator: pd.Series, window: int) -> pd.Series:
    return (
        numerator.rolling(window, min_periods=1).sum()
        / denominator.rolling(window, min_periods=1).sum().replace(0.0, np.nan)
    ).fillna(0.0)


def _build_features(records: list[dict[str, Any]], index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    scored = _score_records(records)
    columns = [
        "sentiment_7d", "sentiment_14d", "sentiment_28d", "sentiment_acceleration",
        "risk_7d", "risk_14d", "risk_28d", "fingpt_risk_score", "news_count_7d",
        "news_count_28d", "news_intensity_z", "concern_ratio_7d", "source_coverage_28d",
        "bearish_source_count_7d", "source_sentiment_spread_7d",
    ]
    if scored.empty:
        return pd.DataFrame(0.0, index=index, columns=columns), {
            "scored_rows": 0,
            "sources": [],
            "source_count": 0,
            "date_start": None,
            "date_end": None,
        }

    calendar = pd.date_range(scored["date"].min(), max(scored["date"].max(), index.max()), freq="D")
    scored["count"] = 1.0
    scored["sentiment_sum"] = scored["sentiment"]
    scored["risk_sum"] = scored["risk_score"]
    daily = scored.groupby("date").agg(
        count=("count", "sum"),
        sentiment_sum=("sentiment_sum", "sum"),
        risk_sum=("risk_sum", "sum"),
        concern=("concern", "sum"),
    ).reindex(calendar, fill_value=0.0)

    features = pd.DataFrame(index=calendar)
    for window in (7, 14, 28):
        count = daily["count"].rolling(window, min_periods=1).sum()
        features[f"sentiment_{window}d"] = (
            daily["sentiment_sum"].rolling(window, min_periods=1).sum()
            / count.replace(0.0, np.nan)
        ).fillna(0.0)
        features[f"risk_{window}d"] = (
            daily["risk_sum"].rolling(window, min_periods=1).sum()
            / count.replace(0.0, np.nan)
        ).fillna(0.0)
        features[f"news_count_{window}d"] = count
    features["sentiment_acceleration"] = features["sentiment_7d"] - features["sentiment_28d"]
    features["fingpt_risk_score"] = (
        0.5 * features["risk_7d"] + 0.3 * features["risk_14d"] + 0.2 * features["risk_28d"]
    )
    features["concern_ratio_7d"] = _rolling_ratio(daily["concern"], daily["count"], 7)
    intensity_mean = features["news_count_7d"].rolling(180, min_periods=30).mean()
    intensity_std = features["news_count_7d"].rolling(180, min_periods=30).std().replace(0.0, np.nan)
    features["news_intensity_z"] = (
        (features["news_count_7d"] - intensity_mean) / intensity_std
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    source_scores: dict[str, pd.Series] = {}
    source_activity: dict[str, pd.Series] = {}
    for source, group in scored.groupby("source"):
        source_daily = group.groupby("date").agg(
            count=("count", "sum"),
            sentiment_sum=("sentiment_sum", "sum"),
        ).reindex(calendar, fill_value=0.0)
        rolling_count = source_daily["count"].rolling(28, min_periods=1).sum()
        source_activity[source] = rolling_count
        source_scores[source] = (
            source_daily["sentiment_sum"].rolling(7, min_periods=1).sum()
            / source_daily["count"].rolling(7, min_periods=1).sum().replace(0.0, np.nan)
        )

    activity_frame = pd.DataFrame(source_activity)
    score_frame = pd.DataFrame(source_scores)
    features["source_coverage_28d"] = (activity_frame > 0.0).sum(axis=1)
    active_7d = score_frame.notna()
    features["bearish_source_count_7d"] = ((score_frame < 0.0) & active_7d).sum(axis=1)
    features["source_sentiment_spread_7d"] = (
        score_frame.max(axis=1, skipna=True) - score_frame.min(axis=1, skipna=True)
    ).fillna(0.0)

    # Use only information available through the prior calendar day.
    lagged = features.shift(1).reindex(index).fillna(0.0)
    return lagged[columns], {
        "scored_rows": int(len(scored)),
        "sources": sorted(scored["source"].unique().tolist()),
        "source_count": int(scored["source"].nunique()),
        "date_start": str(scored["date"].min().date()),
        "date_end": str(scored["date"].max().date()),
    }


def _alignment_regime(
    features: pd.DataFrame,
    a207_regime: pd.Series,
    *,
    min_risk_score: float,
    max_sentiment: float,
    min_news_z: float,
    max_return_5d: float,
    min_source_coverage: int,
    hold_days: int,
) -> tuple[pd.DataFrame, list[str]]:
    base = a207_regime.to_numpy(dtype=object)
    trigger = (
        (features["fingpt_risk_score"].to_numpy() >= min_risk_score)
        & (features["sentiment_7d"].to_numpy() <= max_sentiment)
        & (features["news_intensity_z"].to_numpy() >= min_news_z)
        & (features["return_0050_5d"].to_numpy() <= max_return_5d)
        & (features["source_coverage_28d"].to_numpy() >= min_source_coverage)
        & (features["bearish_source_count_7d"].to_numpy() >= 1)
        & (base == "golden1")
    )
    regime = base.copy()
    active = 0
    trigger_dates: list[str] = []
    for i, dt in enumerate(features.index):
        if active > 0:
            if base[i] == "golden1":
                regime[i] = "group_a_plus_defensive"
            active -= 1
        elif trigger[i]:
            regime[i] = "group_a_plus_defensive"
            active = hold_days - 1
            trigger_dates.append(str(dt.date()))
    frame = features.copy()
    frame["fingpt_trigger"] = trigger.astype(int)
    frame["regime"] = regime
    return frame, trigger_dates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--news-dir", default=str(NEWS_DIR))
    parser.add_argument("--min-risk-scores", default="0.10,0.20,0.30")
    parser.add_argument("--max-sentiments", default="0.0,-0.05,-0.10")
    parser.add_argument("--min-news-z", default="0.0,0.5,1.0")
    parser.add_argument("--max-return-5d", default="0.0,-0.02")
    parser.add_argument("--min-source-coverage", type=int, default=1)
    parser.add_argument("--formal-min-sources", type=int, default=2)
    parser.add_argument("--formal-min-source-day-ratio", type=float, default=0.50)
    parser.add_argument("--hold-days", default="1,2,3,5")
    parser.add_argument("--output-prefix", default="results/group_a_plus_fingpt_sentiment_alignment_20260619")
    args = parser.parse_args()

    policy_signal, policy_signal_path = _load_policy_signal(_resolve(args.decision_pointer))
    golden_signal_path = _resolve(args.golden_signal)
    golden_signal = _load(golden_signal_path)
    defensive_weights = _weights_from_group_a_plus(policy_signal)
    golden_weights = _weights_from_group_a(golden_signal)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": defensive_weights,
    }

    prices = _load_prices(_resolve(args.db), list(TICKERS), args.start, args.end)
    chip_features = _load_chip_features(_resolve(args.db), prices.index, args.start, args.end)
    _events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
    baseline_curve = _simulate_regime_curve(prices, a207_frame["regime"], weights_by_regime, args.initial_value)
    baseline_metrics = _metrics(baseline_curve, args.initial_value)

    records, ingestion = _load_news_records(Path(args.news_dir))
    features, coverage = _build_features(records, prices.index)
    features["return_0050_5d"] = prices["0050.TW"].pct_change(5).fillna(0.0)

    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for risk_score in _parse_float_list(args.min_risk_scores):
        for sentiment in _parse_float_list(args.max_sentiments):
            for news_z in _parse_float_list(args.min_news_z):
                for max_return in _parse_float_list(args.max_return_5d):
                    for hold_days in _parse_int_list(args.hold_days):
                        label = (
                            f"fingpt_align_r{int(risk_score * 100):02d}"
                            f"_s{int(abs(sentiment) * 100):02d}_z{int(news_z * 10):02d}"
                            f"_ret{int(abs(max_return) * 100):02d}_h{hold_days}"
                        )
                        frame, trigger_dates = _alignment_regime(
                            features,
                            a207_frame["regime"],
                            min_risk_score=risk_score,
                            max_sentiment=sentiment,
                            min_news_z=news_z,
                            max_return_5d=max_return,
                            min_source_coverage=args.min_source_coverage,
                            hold_days=hold_days,
                        )
                        curve = _simulate_regime_curve(
                            prices,
                            frame["regime"],
                            weights_by_regime,
                            args.initial_value,
                        )
                        override_days = int((frame["regime"] != a207_frame["regime"]).sum())
                        rows.append(
                            {
                                "variant": label,
                                **_metrics(curve, args.initial_value),
                                "min_risk_score": risk_score,
                                "max_sentiment_7d": sentiment,
                                "min_news_intensity_z": news_z,
                                "max_return_0050_5d": max_return,
                                "min_source_coverage": args.min_source_coverage,
                                "hold_days": hold_days,
                                "trigger_days": len(trigger_dates),
                                "override_days": override_days,
                                "trigger_dates": trigger_dates,
                            }
                        )
                        frames[label] = frame

    formal_source_days = int((features["source_coverage_28d"] >= args.formal_min_sources).sum())
    formal_source_day_ratio = formal_source_days / len(features) if len(features) else 0.0
    data_ready = (
        coverage["source_count"] >= args.formal_min_sources
        and formal_source_day_ratio >= args.formal_min_source_day_ratio
    )
    for row in rows:
        row["formal_eligible"] = data_ready
        row["formal_ineligible_reason"] = (
            None if data_ready else "insufficient_sustained_independent_news_source_coverage"
        )
    formal = [
        row for row in rows
        if data_ready
        and row["final_value"] >= baseline_metrics["final_value"]
        and row["sharpe_ratio"] >= baseline_metrics["sharpe_ratio"]
        and row["max_drawdown"] >= baseline_metrics["max_drawdown"]
        and row["override_days"] > 0
    ]
    effective = [row for row in rows if row["override_days"] > 0]
    ranked = sorted(
        effective or rows,
        key=lambda row: (
            row in formal,
            row["sharpe_ratio"],
            row["max_drawdown"],
            row["final_value"],
        ),
        reverse=True,
    )
    best = ranked[0]
    report = {
        "experiment": "group_a_plus_fingpt_sentiment_alignment",
        "method_note": (
            "FinGPT-inspired proxy using multi-horizon financial sentiment, event concerns, "
            "source coverage, mention intensity, and price confirmation. News features are "
            "lagged by one calendar day and can only override A20.7 while it is in golden1."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {
            "start": str(prices.index[0].date()),
            "end": str(prices.index[-1].date()),
            "rows": int(len(prices)),
        },
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
            "news_dir": str(Path(args.news_dir).resolve()),
        },
        "weights": {
            "golden1_0531_1m": _normalize(golden_weights),
            "group_a_plus_defensive_1m": _normalize(defensive_weights),
        },
        "summary": {"a207": baseline_metrics},
        "news_ingestion": ingestion,
        "news_coverage": coverage,
        "data_readiness": {
            "formal_min_sources": args.formal_min_sources,
            "formal_min_source_day_ratio": args.formal_min_source_day_ratio,
            "formal_source_days": formal_source_days,
            "formal_source_day_ratio": formal_source_day_ratio,
            "ready_for_formal_upgrade": data_ready,
            "reason": None if data_ready else "insufficient_sustained_independent_news_source_coverage",
        },
        "rows": rows,
        "effective_candidate_count": len(effective),
        "formal_upgrade_pass_count": len(formal),
        "top_formal": sorted(
            formal,
            key=lambda row: (row["sharpe_ratio"], row["max_drawdown"], row["final_value"]),
            reverse=True,
        )[:10],
        "best": best,
    }

    prefix = Path(args.output_prefix)
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    best_frame_path = prefix.with_name(prefix.name + "_best_frame.csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    frames[best["variant"]].to_csv(best_frame_path, encoding="utf-8-sig")

    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Best frame: {best_frame_path}")
    print(f"Sources: {coverage['sources']} formal-ready={data_ready}")
    print(f"Formal passes: {len(formal)} / {len(rows)}")
    print(
        f"Best: {best['variant']} final={best['final_value']:,.0f}, "
        f"sharpe={best['sharpe_ratio']:.3f}, mdd={best['max_drawdown']:.2%}, "
        f"overrides={best['override_days']}"
    )


if __name__ == "__main__":
    main()
