#!/usr/bin/env python3
"""Build a 2607.16450 geopolitical-risk CVaR overlay for GroupA+.

The paper lists geopolitical risk conditioning as future research. This
implementation is a local-news keyword overlay over the existing watchlist
news artifact. It is conservative: it can only raise risk warnings and lower
advisory leverage caps; it never emits orders or target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WATCHLIST_NEWS = PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_geopolitical_cvar_overlay.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_geopolitical_cvar_overlay/history"

KEYWORD_BUCKETS: dict[str, dict[str, Any]] = {
    "cross_strait_military": {
        "weight": 3.0,
        "keywords": [
            "台海",
            "兩岸",
            "軍演",
            "共軍",
            "解放軍",
            "海峽中線",
            "飛彈",
            "封鎖",
            "invasion",
            "military drill",
            "PLA",
            "Taiwan Strait",
            "blockade",
        ],
    },
    "export_control_sanctions": {
        "weight": 2.5,
        "keywords": [
            "出口管制",
            "禁令",
            "制裁",
            "實體清單",
            "晶片禁令",
            "先進製程",
            "export control",
            "sanction",
            "entity list",
            "chip ban",
        ],
    },
    "supply_chain_disruption": {
        "weight": 2.0,
        "keywords": [
            "供應鏈",
            "斷鏈",
            "缺料",
            "停工",
            "中斷",
            "地震",
            "停電",
            "supply chain",
            "disruption",
            "shutdown",
            "power outage",
        ],
    },
    "regional_conflict_macro": {
        "weight": 1.5,
        "keywords": [
            "戰爭",
            "衝突",
            "地緣政治",
            "關稅",
            "貿易戰",
            "伊朗",
            "中東",
            "war",
            "conflict",
            "geopolitical",
            "tariff",
            "trade war",
        ],
    },
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "snippet", "category", "source"))


def _matches(blob: str) -> dict[str, list[str]]:
    lowered = blob.lower()
    out: dict[str, list[str]] = {}
    for bucket, cfg in KEYWORD_BUCKETS.items():
        found = []
        for keyword in cfg["keywords"]:
            key = str(keyword)
            haystack = lowered if key.isascii() else blob
            needle = key.lower() if key.isascii() else key
            if needle in haystack:
                found.append(key)
        if found:
            out[bucket] = found
    return out


def _risk_state(score: float) -> str:
    if score >= 8.0:
        return "high_geopolitical_stress"
    if score >= 4.0:
        return "elevated_geopolitical_stress"
    if score > 0.0:
        return "watch"
    return "normal"


def _cvar_multiplier(state: str) -> float:
    return {
        "high_geopolitical_stress": 1.50,
        "elevated_geopolitical_stress": 1.25,
        "watch": 1.10,
        "normal": 1.00,
    }[state]


def _advisory_00631l_cap(state: str) -> float:
    return {
        "high_geopolitical_stress": 0.0,
        "elevated_geopolitical_stress": 0.05,
        "watch": 0.10,
        "normal": 0.20,
    }[state]


def build_overlay(
    *,
    watchlist_news_path: Path = DEFAULT_WATCHLIST_NEWS,
    as_of: str | None = None,
    max_articles: int = 80,
) -> dict[str, Any]:
    watchlist = _load(watchlist_news_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not watchlist:
        blockers.append("watchlist_news_missing")
    articles = watchlist.get("articles") if isinstance(watchlist.get("articles"), list) else []
    selected = articles[:max_articles]
    scored_articles: list[dict[str, Any]] = []
    bucket_scores = {bucket: 0.0 for bucket in KEYWORD_BUCKETS}
    for row in selected:
        if not isinstance(row, dict):
            continue
        matches = _matches(_text(row))
        if not matches:
            continue
        article_score = 0.0
        for bucket, found in matches.items():
            score = float(KEYWORD_BUCKETS[bucket]["weight"]) * len(found)
            bucket_scores[bucket] += score
            article_score += score
        scored_articles.append(
            {
                "date": row.get("date"),
                "source": row.get("source"),
                "title": row.get("title"),
                "url": row.get("url"),
                "matched_buckets": matches,
                "score": round(article_score, 3),
            }
        )

    raw_score = sum(bucket_scores.values())
    article_count = max(len(selected), 1)
    normalized_score = raw_score / article_count * 8.0
    state = _risk_state(normalized_score)
    if state != "normal":
        warnings.append(f"geopolitical_risk_state:{state}")
    if not scored_articles and not blockers:
        warnings.append("no_geopolitical_keywords_matched_in_watchlist_news")
    if watchlist.get("source") == "local_ltn_jsonl":
        warnings.append("local_news_keyword_overlay_not_validated_geopolitical_index")

    as_of_value = as_of or watchlist.get("signal_date") or "unknown"
    cvar_multiplier = _cvar_multiplier(state)
    advisory_cap = _advisory_00631l_cap(state)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_geopolitical_cvar_overlay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_risk_overlay_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_monitoring",
        "as_of": as_of_value,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "future_research_concept": "geopolitical_risk_index_into_cvar",
            "implemented_as": "local_news_keyword_stress_overlay",
            "paper_equivalent": False,
        },
        "score": {
            "raw_score": round(raw_score, 3),
            "normalized_score": round(normalized_score, 3),
            "state": state,
            "bucket_scores": {key: round(value, 3) for key, value in bucket_scores.items()},
            "matched_article_count": len(scored_articles),
            "article_count": len(selected),
        },
        "overlay": {
            "cvar_penalty_multiplier": cvar_multiplier,
            "advisory_max_00631l_weight": advisory_cap,
            "delay_reentry_when_state_at_or_above": "elevated_geopolitical_stress",
        },
        "matched_articles": scored_articles[:20],
        "decision": {
            "promote_geopolitical_cvar_overlay": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_geopolitical_overlay": False,
            "summary": "Geopolitical CVaR overlay is monitoring-only; it can only add caution around CVaR and 00631L exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {"watchlist_news": str(watchlist_news_path)},
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_geopolitical_cvar_overlay_{stamp}.json"


def write_overlay(overlay: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(overlay.get("as_of"))).write_text(
            json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist-news", default=str(DEFAULT_WATCHLIST_NEWS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--max-articles", type=int, default=80)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    overlay = build_overlay(
        watchlist_news_path=_resolve(args.watchlist_news),
        as_of=args.as_of,
        max_articles=int(args.max_articles),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_overlay(overlay, output, history_dir)
    print(f"2607.16450 geopolitical CVaR overlay: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, str(overlay.get('as_of')))}")
    print(
        json.dumps(
            {
                "status": overlay["status"],
                "state": overlay["score"]["state"],
                "cvar_multiplier": overlay["overlay"]["cvar_penalty_multiplier"],
                "advisory_max_00631l_weight": overlay["overlay"]["advisory_max_00631l_weight"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
