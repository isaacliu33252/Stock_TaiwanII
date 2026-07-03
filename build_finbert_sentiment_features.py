#!/usr/bin/env python3
"""Build FinBERT-style daily sentiment features from local market news."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from build_llm_sentiment_features import (
    NEGATIVE_TERMS,
    POSITIVE_TERMS,
    RISK_OFF_TERMS,
    build_date_series,
    combine_text_columns,
    infer_text_columns,
    read_input_source,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_ROOT / "news"
DEFAULT_OUTPUT = PROJECT_ROOT / "FinRL" / "data" / "sentiment" / "finbert_market_sentiment_daily.csv"
DEFAULT_MODEL_NAME = "ProsusAI/finbert"
OUTPUT_COLUMNS = [
    "date",
    "finbert_sentiment_score",
    "finbert_negative_ratio",
    "finbert_positive_ratio",
    "finbert_neutral_ratio",
    "finbert_confidence",
    "finbert_news_intensity",
    "finbert_record_count",
    "finbert_scoring_mode",
]


EXTRA_POSITIVE = {
    "復甦", "買盤", "避風港", "資金流入", "上漲", "反彈", "強勢", "樂觀", "支撐", "創新高",
    "上涨", "涨停", "牛市", "利好", "增持", "買入", "买入", "推薦", "推荐", "看多",
    "盈利", "增長", "增长", "超預期", "超预期", "強勁", "强劲", "回升", "復蘇",
    "复苏", "突破", "回暖", "上揚", "上扬", "利好消息", "收益增長", "收益增长",
    "利潤增長", "利润增长", "業績優異", "业绩优异", "績優股", "绩优股", "走高",
    "攀升", "大漲", "大涨", "飆升", "飙升", "井噴", "井喷", "暴漲", "暴涨",
}
EXTRA_NEGATIVE = {
    "暴跌", "重挫", "下跌", "賣壓", "斷頭", "疲軟", "下行", "跌破", "衝擊", "警戒",
    "跌停", "熊市", "回調", "回调", "新低", "利空", "減持", "减持", "賣出", "卖出",
    "看空", "虧損", "亏损", "下滑", "萎縮", "萎缩", "不及預期", "不及预期",
    "疲软", "惡化", "恶化", "衰退", "創新低", "创新低", "走弱", "下挫",
    "利空消息", "收益下降", "利潤下滑", "利润下滑", "業績不佳", "业绩不佳",
    "風險股", "风险股", "弱勢", "弱势", "走低", "縮量", "缩量", "大跌",
    "崩盤", "崩盘", "跳水", "跌超", "跌逾", "跌近", "回吐", "轉跌", "转跌",
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def resolve_finbert_text_columns(
    table: pd.DataFrame,
    explicit: Sequence[str] | None = None,
) -> list[str]:
    if explicit:
        return infer_text_columns(table, explicit=explicit)

    lowered = {str(col).strip().lower(): col for col in table.columns}
    preferred_groups = (
        ("title", "snippet"),
        ("headline", "snippet"),
        ("title", "description"),
        ("headline", "summary"),
        ("text",),
        ("content",),
    )
    for group in preferred_groups:
        resolved = [lowered.get(candidate) for candidate in group]
        if all(col is not None for col in resolved):
            return [str(col) for col in resolved]
    return infer_text_columns(table)


def score_text_finbert_proxy(text: str) -> dict[str, float]:
    """Return FinBERT-compatible probabilities using a deterministic proxy.

    This is intentionally shaped like FinBERT output:
    positive / negative / neutral probabilities plus sentiment_score
    (positive - negative). It is a local fallback for environments without the
    ProsusAI/finbert weights.
    """
    lowered = str(text).lower()
    positive_hits = sum(1 for token in POSITIVE_TERMS | EXTRA_POSITIVE if token in lowered)
    negative_hits = sum(1 for token in NEGATIVE_TERMS | EXTRA_NEGATIVE if token in lowered)
    risk_hits = sum(1 for token in RISK_OFF_TERMS if token in lowered)
    negative_hits += 0.5 * risk_hits

    pos_logit = 0.35 + positive_hits
    neg_logit = 0.35 + negative_hits
    neutral_logit = 1.35 + 0.2 * max(0.0, 1.0 - abs(positive_hits - negative_hits))
    logits = np.array([pos_logit, neg_logit, neutral_logit], dtype=float)
    probs = np.exp(logits - logits.max())
    probs = probs / probs.sum()
    positive, negative, neutral = [float(x) for x in probs]
    confidence = float(max(positive, negative, neutral))
    return {
        "finbert_positive_ratio": positive,
        "finbert_negative_ratio": negative,
        "finbert_neutral_ratio": neutral,
        "finbert_sentiment_score": positive - negative,
        "finbert_confidence": confidence,
    }


def _probability_payload(
    *,
    positive: float,
    negative: float,
    neutral: float,
) -> dict[str, float]:
    confidence = float(max(positive, negative, neutral))
    return {
        "finbert_positive_ratio": float(positive),
        "finbert_negative_ratio": float(negative),
        "finbert_neutral_ratio": float(neutral),
        "finbert_sentiment_score": float(positive - negative),
        "finbert_confidence": confidence,
    }


def _label_lookup(model: Any) -> dict[str, int]:
    id2label = getattr(getattr(model, "config", None), "id2label", {}) or {}
    normalized = {str(label).lower(): int(idx) for idx, label in id2label.items()}
    required = {"positive", "negative", "neutral"}
    if not required.issubset(normalized):
        raise ValueError(f"FinBERT model labels must include {sorted(required)}; got {id2label}")
    return normalized


def score_texts_with_finbert_model(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    cache_dir: str | Path | None = None,
    batch_size: int = 16,
    device: str = "auto",
) -> list[dict[str, float]]:
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "True FinBERT scoring requires torch and transformers. "
            "Install with: .venv/bin/pip install transformers safetensors huggingface_hub"
        ) from exc

    if device == "auto":
        resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        resolved_device = device

    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=str(cache_dir) if cache_dir else None)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    model.to(resolved_device)
    model.eval()
    labels = _label_lookup(model)

    payloads: list[dict[str, float]] = []
    clean_texts = [str(text) for text in texts]
    with torch.no_grad():
        for start in range(0, len(clean_texts), batch_size):
            batch = clean_texts[start:start + batch_size]
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            encoded = {key: value.to(resolved_device) for key, value in encoded.items()}
            probs = torch.softmax(model(**encoded).logits, dim=-1).detach().cpu().numpy()
            for row in probs:
                payloads.append(
                    _probability_payload(
                        positive=float(row[labels["positive"]]),
                        negative=float(row[labels["negative"]]),
                        neutral=float(row[labels["neutral"]]),
                    )
                )
    return payloads


def build_finbert_daily_features(
    table: pd.DataFrame,
    *,
    date_column: str = "date",
    text_columns: Sequence[str] | None = None,
    max_rows: int | None = None,
    scoring_mode: str = "proxy",
    model_name: str = DEFAULT_MODEL_NAME,
    model_cache_dir: str | Path | None = None,
    batch_size: int = 16,
    device: str = "auto",
) -> pd.DataFrame:
    if table.empty:
        raise ValueError("Input table is empty")
    if max_rows is not None and max_rows > 0:
        table = table.head(max_rows).copy()

    resolved_text_columns = resolve_finbert_text_columns(table, explicit=text_columns)
    frame = table[list(resolved_text_columns)].copy()
    frame["date"] = build_date_series(table, preferred=date_column)
    frame["text"] = combine_text_columns(frame, resolved_text_columns)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date", "text"])
    frame = frame[frame["text"].astype(str).str.strip() != ""].copy()

    texts = frame["text"].astype(str).tolist()
    if scoring_mode == "model":
        scores = score_texts_with_finbert_model(
            texts,
            model_name=model_name,
            cache_dir=model_cache_dir,
            batch_size=batch_size,
            device=device,
        )
        mode_label = f"huggingface:{model_name}"
    elif scoring_mode == "proxy":
        scores = [score_text_finbert_proxy(text) for text in texts]
        mode_label = "rule_based_finbert_proxy"
    else:
        raise ValueError("scoring_mode must be one of: proxy, model")

    records = []
    for date, score in zip(frame["date"], scores):
        records.append({"date": date, **score, "record_count": 1.0})
    scored = pd.DataFrame(records)
    if scored.empty:
        raise ValueError("No scorable text rows found")

    daily = scored.groupby("date", as_index=False).agg(
        finbert_sentiment_score=("finbert_sentiment_score", "mean"),
        finbert_negative_ratio=("finbert_negative_ratio", "mean"),
        finbert_positive_ratio=("finbert_positive_ratio", "mean"),
        finbert_neutral_ratio=("finbert_neutral_ratio", "mean"),
        finbert_confidence=("finbert_confidence", "mean"),
        finbert_record_count=("record_count", "sum"),
    )
    daily["finbert_news_intensity"] = np.log1p(daily["finbert_record_count"]).clip(0.0, 5.0)
    daily["finbert_scoring_mode"] = mode_label
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    return daily[OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="News file or directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Daily FinBERT-style CSV output")
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--text-columns", default=None, help="Comma-separated text columns")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--scoring-mode", choices=["proxy", "model"], default="proxy")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--model-cache-dir", default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or cuda:0")
    args = parser.parse_args()

    text_columns = None
    if args.text_columns:
        text_columns = [item.strip() for item in args.text_columns.split(",") if item.strip()]

    source = _resolve(args.input)
    output = _resolve(args.output)
    table = read_input_source(source)
    daily = build_finbert_daily_features(
        table,
        date_column=args.date_column,
        text_columns=text_columns,
        max_rows=args.max_rows,
        scoring_mode=args.scoring_mode,
        model_name=args.model_name,
        model_cache_dir=args.model_cache_dir,
        batch_size=args.batch_size,
        device=args.device,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output, index=False, encoding="utf-8")

    print("=" * 72)
    print("FinBERT-style sentiment feature build complete")
    print(f"Input:       {source}")
    print(f"Output:      {output}")
    print(f"Daily rows:  {len(daily)}")
    print(f"Date range:  {daily['date'].iloc[0]} ~ {daily['date'].iloc[-1]}")
    print(f"Mean score:  {daily['finbert_sentiment_score'].mean():.4f}")
    print(f"Mean neg:    {daily['finbert_negative_ratio'].mean():.4f}")
    print(f"Mode:        {daily['finbert_scoring_mode'].iloc[0]}")


if __name__ == "__main__":
    main()
