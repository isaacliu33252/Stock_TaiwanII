#!/usr/bin/env python3
"""Filter Liberty Times merged news into a market-relevant JSONL subset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_mainstream_202002_20260520_merged.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_mainstream_202002_20260520_market.jsonl"
DEFAULT_METADATA = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_mainstream_202002_20260520_market_metadata.json"
REQUIRED_FIELDS = ("date", "source", "title", "url", "category", "snippet")

STRONG_CATEGORIES = {"財經", "財經週報"}
WEAK_CATEGORIES = {"國際", "政治", "3C", "地產", "軍武", "評論", "焦點", "汽車", "消費", "生活"}

MARKET_CORE_KEYWORDS = {
    "台股", "美股", "股市", "大盤", "加權指數", "櫃買", "上市櫃", "收盤", "開盤", "盤前",
    "道瓊", "那斯達克", "納斯達克", "標普", "s&p", "nasdaq", "dow jones",
    "外資", "投信", "自營商", "融資", "融券", "漲停", "跌停", "權值股", "成交量",
    "股價", "eps", "本益比", "殖利率", "配息", "除息", "財報", "法說", "營收", "獲利",
}
MACRO_POLICY_KEYWORDS = {
    "聯準會", "fed", "fomc", "央行", "貨幣政策", "利率", "降息", "升息", "通膨", "cpi",
    "ppi", "景氣", "gdp", "pmi", "匯率", "美元", "美債", "殖利率", "關稅", "制裁",
    "衰退", "recession", "流動性", "失業率", "非農", "油價", "原油", "金價", "黃金",
}
ETF_TICKER_KEYWORDS = {
    "etf", "0050", "00631l", "00632r", "0056", "00878", "00713", "00679b", "00751b",
}
SECTOR_TECH_KEYWORDS = {
    "半導體", "晶片", "ai", "伺服器", "台積電", "輝達", "nvidia", "iphone", "供應鏈",
    "記憶體", "封測", "面板", "電子股", "金融股", "傳產", "航運股", "鋼鐵股",
}


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    return candidate


def collapse_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _hit_keywords(text: str, keywords: set[str]) -> list[str]:
    lowered = text.lower()
    hits = [keyword for keyword in sorted(keywords) if keyword.lower() in lowered]
    return hits


def score_market_relevance(record: dict[str, str]) -> tuple[bool, dict[str, object]]:
    category = collapse_text(record.get("category", ""))
    title = collapse_text(record.get("title", ""))
    snippet = collapse_text(record.get("snippet", ""))
    text = f"{title} {snippet}".strip()

    score = 0
    reasons: list[str] = []
    keyword_hits: dict[str, list[str]] = {}

    if category in STRONG_CATEGORIES:
        score += 3
        reasons.append(f"strong_category:{category}")
    elif category in WEAK_CATEGORIES:
        score += 1
        reasons.append(f"weak_category:{category}")

    group_map = {
        "market_core": MARKET_CORE_KEYWORDS,
        "macro_policy": MACRO_POLICY_KEYWORDS,
        "etf_ticker": ETF_TICKER_KEYWORDS,
        "sector_tech": SECTOR_TECH_KEYWORDS,
    }
    for group_name, keywords in group_map.items():
        hits = _hit_keywords(text, keywords)
        if not hits:
            continue
        keyword_hits[group_name] = hits
        if group_name in {"market_core", "macro_policy", "etf_ticker"}:
            score += 2
        else:
            score += 1
        reasons.append(f"{group_name}:{','.join(hits[:6])}")

    include = score >= 3
    debug = {
        "score": score,
        "category": category,
        "reasons": reasons,
        "keyword_hits": keyword_hits,
    }
    return include, debug


def read_records(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            record = {field: collapse_text(payload.get(field, "")) for field in REQUIRED_FIELDS}
            if record["date"] and record["title"]:
                records.append(record)
    return records


def write_jsonl(records: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_metadata(
    *,
    input_path: Path,
    output_path: Path,
    kept_records: list[dict[str, str]],
    total_records: int,
    category_counts: Counter[str],
    reason_counts: Counter[str],
) -> dict[str, object]:
    dates = [record["date"] for record in kept_records if record.get("date")]
    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "total_input_rows": total_records,
        "kept_rows": len(kept_records),
        "drop_rows": total_records - len(kept_records),
        "keep_ratio": (len(kept_records) / total_records) if total_records else 0.0,
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "category_counts": dict(category_counts.most_common()),
        "reason_counts": dict(reason_counts.most_common()),
        "strong_categories": sorted(STRONG_CATEGORIES),
        "weak_categories": sorted(WEAK_CATEGORIES),
    }


def write_metadata(metadata: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter Liberty Times merged JSONL into market-relevant subset.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Merged Liberty Times JSONL path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Market-only JSONL output path")
    parser.add_argument("--metadata-output", default=str(DEFAULT_METADATA), help="Metadata JSON output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)
    metadata_path = _resolve_path(args.metadata_output)

    records = read_records(input_path)
    kept_records: list[dict[str, str]] = []
    category_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for record in records:
        include, debug = score_market_relevance(record)
        if not include:
            continue
        kept_records.append(record)
        category_counts[debug["category"]] += 1
        for reason in debug["reasons"]:
            reason_counts[reason.split(":")[0]] += 1

    write_jsonl(kept_records, output_path)
    metadata = build_metadata(
        input_path=input_path,
        output_path=output_path,
        kept_records=kept_records,
        total_records=len(records),
        category_counts=category_counts,
        reason_counts=reason_counts,
    )
    write_metadata(metadata, metadata_path)

    print("=" * 72)
    print("Liberty Times market filter complete")
    print(f"Input:      {input_path}")
    print(f"Output:     {output_path}")
    print(f"Metadata:   {metadata_path}")
    print(f"Input rows: {len(records)}")
    print(f"Kept rows:  {len(kept_records)}")


if __name__ == "__main__":
    main()
