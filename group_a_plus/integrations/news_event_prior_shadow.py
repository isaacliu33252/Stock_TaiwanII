"""News event-prior shadow inspired by arXiv:2608.14014.

The paper's transferable lesson is not "trade sentiment direction"; it is that
public-news direction is mostly spent by publication close, while event type,
coverage intensity, first/follow-up structure, rumor status, and quantified
content remain useful context. This module therefore produces advisory metadata
only. It must not change target weights.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EVENT_BUCKETS: dict[str, dict[str, Any]] = {
    "hard_quantified": {
        "direction_prior": "continuation_watch",
        "width_prior": "widen_before_compress_after",
        "keywords": (
            "營收", "獲利", "財報", "法說", "EPS", "每股盈餘", "股利", "配息", "配股",
            "除息", "回購", "庫藏股", "展望", "財測", "目標價", "評等", "升評", "降評",
            "earnings", "dividend", "guidance", "buyback", "target price", "rating",
        ),
    },
    "soft_story": {
        "direction_prior": "reversal_watch",
        "width_prior": "attention_width",
        "keywords": (
            "新品", "發表", "合作", "客戶", "訂單", "供應鏈", "人事", "董事長", "執行長",
            "總經理", "併購傳聞", "題材", "概念股", "AI", "輝達", "OpenAI", "new product",
            "launch", "partnership", "customer", "leadership", "theme",
        ),
    },
    "macro_through_stock": {
        "direction_prior": "reversal_watch",
        "width_prior": "macro_width",
        "keywords": (
            "聯準會", "Fed", "降息", "升息", "利率", "殖利率", "通膨", "CPI", "就業",
            "美元", "匯率", "美債", "關稅", "地緣", "景氣", "衰退", "recession",
            "inflation", "tariff", "yield",
        ),
    },
    "legal_regulatory": {
        "direction_prior": "neutral_after_placebo",
        "width_prior": "event_width",
        "keywords": (
            "法規", "監管", "金管會", "證交所", "訴訟", "調查", "裁罰", "禁令", "出口管制",
            "regulatory", "lawsuit", "probe", "fine", "sanction", "export control",
        ),
    },
    "fund_flow_positioning": {
        "direction_prior": "do_not_trade_direction",
        "width_prior": "coverage_baseline",
        "keywords": (
            "外資", "投信", "自營商", "三大法人", "官股", "國家隊", "買超", "賣超",
            "加碼", "減碼", "砍", "倒貨", "提款", "掃貨", "籌碼", "張", "成交量",
            "爆量", "吸金", "申購", "贖回", "定期定額", "受益人", "投資人數",
            "fund flow", "foreign investors", "institutional investors",
        ),
    },
    "etf_structure": {
        "direction_prior": "do_not_trade_direction",
        "width_prior": "coverage_baseline",
        "keywords": (
            "ETF", "指數", "追蹤", "成分股", "換股", "調整", "分割", "經理費", "管理費",
            "配息", "高股息", "市值型", "連結基金", "規模", "基金", "TISA",
            "index", "constituent", "rebalance", "fee",
        ),
    },
    "investor_education": {
        "direction_prior": "do_not_trade_direction",
        "width_prior": "coverage_baseline",
        "keywords": (
            "存股", "退休", "小資", "入門", "月投", "定存", "怎麼選", "該買", "比較",
            "達人", "專家", "網曝", "網勸", "一表看", "懶錢包", "股民", "投資人",
            "portfolio", "how to invest",
        ),
    },
    "price_commentary": {
        "direction_prior": "do_not_trade_direction",
        "width_prior": "coverage_baseline",
        "keywords": (
            "大漲", "大跌", "反彈", "拉回", "創高", "創低", "多頭", "空頭", "賣壓", "買盤",
            "技術面", "price", "rally", "selloff", "record high",
        ),
    },
    "promotional": {
        "direction_prior": "reversal_watch_low_confidence",
        "width_prior": "promotional_attention",
        "keywords": (
            "飆股", "黑馬", "必買", "爆發", "翻倍", "明牌", "推薦", "潛力股", "promotional",
            "must buy", "top pick",
        ),
    },
}

RUMOR_KEYWORDS = ("傳聞", "市場傳", "據傳", "rumor", "rumour", "傳出")
SCHEDULED_KEYWORDS = ("法說", "財報", "除息", "股東會", "FOMC", "CPI", "earnings", "ex-dividend")
QUANTIFIED_RE = re.compile(r"(\d+(\.\d+)?\s?(%|％|元|億|兆|bps|點|倍|萬|million|billion))", re.IGNORECASE)
QUANTIFIED_CONTEXT_KEYWORDS = (
    "營收", "獲利", "財報", "EPS", "每股盈餘", "股利", "配息", "配股", "除息", "回購",
    "庫藏股", "展望", "財測", "目標價", "評等", "升評", "降評", "利率", "殖利率",
    "CPI", "earnings", "dividend", "guidance", "buyback", "target price", "rating",
    "yield", "inflation",
)


def _text(article: dict[str, Any]) -> str:
    return " ".join(str(article.get(key) or "") for key in ("title", "snippet", "category", "source"))


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(str(keyword).lower() in lowered for keyword in keywords)


def classify_article(article: dict[str, Any]) -> dict[str, Any]:
    text = _text(article)
    matched: list[str] = []
    bucket_scores: Counter[str] = Counter()
    for bucket, spec in EVENT_BUCKETS.items():
        keywords = tuple(spec.get("keywords") or ())
        hits = [keyword for keyword in keywords if str(keyword).lower() in text.lower()]
        if hits:
            bucket_scores[bucket] += len(hits)
            matched.extend(hits[:3])
    if bucket_scores:
        bucket = bucket_scores.most_common(1)[0][0]
        confidence = min(0.3 + 0.15 * bucket_scores[bucket], 0.8)
    else:
        bucket = "unknown"
        confidence = 0.1
    spec = EVENT_BUCKETS.get(bucket, {})
    quantified = bool(
        bucket == "hard_quantified"
        or (
            QUANTIFIED_RE.search(text) is not None
            and _contains_any(text, QUANTIFIED_CONTEXT_KEYWORDS)
        )
    )
    rumor = _contains_any(text, RUMOR_KEYWORDS)
    scheduled = _contains_any(text, SCHEDULED_KEYWORDS)
    return {
        "date": article.get("date"),
        "symbol": article.get("match_scope"),
        "source": article.get("source"),
        "title": article.get("title"),
        "url": article.get("url"),
        "event_bucket": bucket,
        "event_confidence": round(float(confidence), 4),
        "direction_prior": spec.get("direction_prior", "unknown"),
        "width_prior": spec.get("width_prior", "unknown"),
        "attributes": {
            "rumor_like": rumor,
            "scheduled_like": scheduled,
            "quantified_like": quantified,
            "primary_source_like": str(article.get("source") or "") in {"證交所", "櫃買中心", "公開資訊觀測站"},
            "followup_like": False,
        },
        "matched_terms": sorted(set(str(term) for term in matched))[:8],
    }


def _symbol_from_article(article: dict[str, Any]) -> str:
    symbol = str(article.get("match_scope") or "")
    if symbol and symbol != "market_fallback":
        return symbol
    keywords = article.get("matched_keywords") if isinstance(article.get("matched_keywords"), list) else []
    return "market_fallback" if keywords else "unknown"


def build_news_event_prior_shadow(
    *,
    watchlist_news: dict[str, Any],
    as_of: str | None = None,
    max_articles: int = 80,
) -> dict[str, Any]:
    articles = watchlist_news.get("articles") if isinstance(watchlist_news.get("articles"), list) else []
    classified = []
    for article in articles[:max_articles]:
        if not isinstance(article, dict):
            continue
        item = dict(article)
        item["match_scope"] = _symbol_from_article(article)
        classified.append(classify_article(item))

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in classified:
        by_symbol[str(item.get("symbol") or "unknown")].append(item)

    per_symbol: dict[str, Any] = {}
    for symbol, rows in sorted(by_symbol.items()):
        bucket_counts = Counter(str(row.get("event_bucket") or "unknown") for row in rows)
        direction_counts = Counter(str(row.get("direction_prior") or "unknown") for row in rows)
        width_counts = Counter(str(row.get("width_prior") or "unknown") for row in rows)
        attr_counts = Counter()
        for row in rows:
            attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            for key, value in attrs.items():
                if value is True:
                    attr_counts[key] += 1
        dominant_bucket = bucket_counts.most_common(1)[0][0] if bucket_counts else "unknown"
        per_symbol[symbol] = {
            "article_count": len(rows),
            "event_bucket_counts": dict(bucket_counts),
            "direction_prior_counts": dict(direction_counts),
            "width_prior_counts": dict(width_counts),
            "attribute_counts": dict(attr_counts),
            "dominant_event_bucket": dominant_bucket,
            "dominant_direction_prior": direction_counts.most_common(1)[0][0] if direction_counts else "unknown",
            "dominant_width_prior": width_counts.most_common(1)[0][0] if width_counts else "unknown",
            "coverage_intensity": "high" if len(rows) >= 5 else "medium" if len(rows) >= 2 else "low",
        }

    total_bucket_counts = Counter(str(row.get("event_bucket") or "unknown") for row in classified)
    hard_count = int(total_bucket_counts.get("hard_quantified", 0))
    soft_count = int(total_bucket_counts.get("soft_story", 0) + total_bucket_counts.get("macro_through_stock", 0))
    width_watch = any(
        row.get("width_prior") in {"widen_before_compress_after", "attention_width", "macro_width", "event_width"}
        for row in classified
    )
    direction_trade_allowed = False
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_news_event_prior_shadow",
        "research_source": "arXiv:2608.14014 news priced-in event-study review",
        "status": "available" if classified else "unavailable",
        "reason": None if classified else "no_articles",
        "as_of": as_of or watchlist_news.get("signal_date"),
        "policy": "shadow_only_no_target_weight_change",
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "direction_trade_allowed": direction_trade_allowed,
        "article_count": len(classified),
        "source": {
            "watchlist_news_source": watchlist_news.get("source"),
            "watchlist_signal_date": watchlist_news.get("signal_date"),
            "watchlist_article_count": watchlist_news.get("article_count"),
        },
        "event_bucket_counts": dict(total_bucket_counts),
        "summary": {
            "hard_quantified_count": hard_count,
            "soft_story_or_macro_count": soft_count,
            "rumor_like_count": sum(1 for row in classified if (row.get("attributes") or {}).get("rumor_like") is True),
            "scheduled_like_count": sum(1 for row in classified if (row.get("attributes") or {}).get("scheduled_like") is True),
            "quantified_like_count": sum(1 for row in classified if (row.get("attributes") or {}).get("quantified_like") is True),
            "coverage_width_watch": width_watch,
        },
        "per_symbol": per_symbol,
        "classified_articles": classified,
        "interpretation": (
            "Public-news direction is treated as mostly priced by publication close; "
            "event buckets and coverage intensity are context/width priors only."
        ),
        "next_required_validation": (
            "Run a Taiwan-specific coverage-presence baseline event study before any "
            "news-event prior can affect target weights."
        ),
    }


def append_news_event_prior_shadow_log(log_path: Path, report: dict[str, Any]) -> None:
    if report.get("status") == "unavailable":
        return
    date_key = str(report.get("as_of") or "")
    row = {
        "date": date_key,
        "policy": report.get("policy"),
        "target_weight_change_allowed": report.get("target_weight_change_allowed"),
        "direction_trade_allowed": report.get("direction_trade_allowed"),
        "article_count": report.get("article_count"),
        "event_bucket_counts": report.get("event_bucket_counts"),
        "summary": report.get("summary"),
        "per_symbol": report.get("per_symbol"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != date_key:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("date") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8")
