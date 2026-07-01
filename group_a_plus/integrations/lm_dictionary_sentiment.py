"""Loughran-McDonald dictionary sentiment shadow signal.

This is a lightweight fallback/sanity-check inspired by StocksProject-master.
It is intentionally weaker than FinBERT and should not directly drive active
allocation. The intended use is to expose a transparent English financial-word
count signal when suitable English text and dictionaries are available.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT


DEFAULT_WATCHLIST_NEWS = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"
STOCKS_PROJECT_SENTIMENT_DIR = Path(
    "/mnt/c/Users/isaac/Downloads/StocksProject-master/StocksProject-master/SentimentAnalysis"
)

DICT_FILES = {
    "positive": "LoughranMcDonald_Positive.csv",
    "negative": "LoughranMcDonald_Negative.csv",
    "uncertainty": "LoughranMcDonald_Uncertainty.csv",
    "litigious": "LoughranMcDonald_Litigious.csv",
}


def _candidate_dictionary_dirs(explicit: str | Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_dir = os.environ.get("LM_DICTIONARY_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend(
        [
            PROJECT_ROOT / "FinRL/data/sentiment/loughran_mcdonald",
            PROJECT_ROOT / "FinRL/data/sentiment",
            STOCKS_PROJECT_SENTIMENT_DIR,
        ]
    )
    return candidates


def resolve_dictionary_dir(explicit: str | Path | None = None) -> Path | None:
    for candidate in _candidate_dictionary_dirs(explicit):
        if all((candidate / filename).exists() for filename in (DICT_FILES["positive"], DICT_FILES["negative"])):
            return candidate
    return None


def load_word_set(path: Path) -> set[str]:
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        token = line.strip().split(",", 1)[0].strip().lower()
        if token and token.isalpha():
            words.add(token)
    return words


def load_dictionaries(dictionary_dir: str | Path | None = None) -> dict[str, set[str]]:
    resolved = resolve_dictionary_dir(dictionary_dir)
    if resolved is None:
        return {}
    out: dict[str, set[str]] = {}
    for name, filename in DICT_FILES.items():
        path = resolved / filename
        out[name] = load_word_set(path) if path.exists() else set()
    return out


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", text.lower())


def score_texts(texts: list[str], dictionaries: dict[str, set[str]]) -> dict[str, Any]:
    tokens = [token for text in texts for token in _tokens(str(text))]
    counts = {
        name: sum(1 for token in tokens if token in words)
        for name, words in dictionaries.items()
    }
    positive = int(counts.get("positive", 0))
    negative = int(counts.get("negative", 0))
    sentiment_denominator = positive + negative
    sentiment_score = (
        (positive - negative) / sentiment_denominator
        if sentiment_denominator > 0
        else 0.0
    )
    risk_score = negative / sentiment_denominator if sentiment_denominator > 0 else 0.0
    return {
        "token_count": len(tokens),
        "positive_count": positive,
        "negative_count": negative,
        "uncertainty_count": int(counts.get("uncertainty", 0)),
        "litigious_count": int(counts.get("litigious", 0)),
        "dictionary_hit_count": int(sum(counts.values())),
        "sentiment_score": round(float(sentiment_score), 4),
        "risk_score": round(float(risk_score), 4),
    }


def _texts_from_watchlist_news(path: Path) -> tuple[list[str], dict[str, Any]]:
    if not path.exists():
        return [], {"status": "unavailable", "reason": "watchlist_news_not_found", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    articles = payload.get("articles") or []
    texts = [
        " ".join(str(article.get(key, "")) for key in ("title", "snippet"))
        for article in articles
        if isinstance(article, dict)
    ]
    return texts, {
        "status": "available",
        "path": str(path),
        "article_count": len(articles),
        "source": payload.get("source"),
        "signal_date": payload.get("signal_date"),
    }


def build_lm_dictionary_snapshot(
    signal_date: str,
    *,
    watchlist_news_path: str | Path = DEFAULT_WATCHLIST_NEWS,
    dictionary_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_dir = resolve_dictionary_dir(dictionary_dir)
    if resolved_dir is None:
        return {
            "status": "unavailable",
            "reason": "dictionary_not_found",
            "signal_date": signal_date,
            "risk_score": 0.0,
        }

    texts, source_info = _texts_from_watchlist_news(Path(watchlist_news_path))
    if not texts:
        return {
            "status": "unavailable",
            "reason": source_info.get("reason", "no_texts"),
            "signal_date": signal_date,
            "dictionary_dir": str(resolved_dir),
            "source": source_info,
            "risk_score": 0.0,
        }

    dictionaries = load_dictionaries(resolved_dir)
    score = score_texts(texts, dictionaries)
    status = "ok"
    reason = "scored"
    if score["token_count"] == 0:
        status = "no_english_tokens"
        reason = "source_text_has_no_english_tokens"
    elif score["positive_count"] + score["negative_count"] == 0:
        status = "no_dictionary_hits"
        reason = "no_positive_or_negative_dictionary_hits"

    return {
        "status": status,
        "reason": reason,
        "signal_date": signal_date,
        "dictionary_dir": str(resolved_dir),
        "source": source_info,
        "active_allocation_impact": "none",
        **score,
    }
