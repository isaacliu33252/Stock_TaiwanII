#!/usr/bin/env python3
"""Merge Liberty Times JSONL exports and build daily sentiment features."""

from __future__ import annotations

import argparse
import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from build_llm_sentiment_features import prepare_llm_sentiment_path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_ROOT.parent / "news"
DEFAULT_INCLUDE_GLOB = "ltn_mainstream_*.jsonl"
DEFAULT_EXCLUDES = {"ltn_mainstream_2020-02-01.jsonl"}
DEFAULT_MERGED_OUTPUT = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_mainstream_202002_20260520_merged.jsonl"
DEFAULT_SENTIMENT_OUTPUT = PROJECT_ROOT / "FinRL" / "data" / "sentiment" / "llm_market_sentiment_daily.csv"
DEFAULT_METADATA_OUTPUT = PROJECT_ROOT / "data" / "news" / "liberty_times" / "ltn_mainstream_202002_20260520_metadata.json"
REQUIRED_FIELDS = ("date", "source", "title", "url", "category", "snippet")


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    return candidate


def collapse_text(value: object) -> str:
    return " ".join(str(value or "").split())


def iter_input_paths(
    input_dir: Path,
    *,
    include_glob: str,
    exclude_names: set[str],
) -> list[Path]:
    paths = sorted(path for path in input_dir.iterdir() if path.is_file() and fnmatch(path.name, include_glob))
    return [path for path in paths if path.name not in exclude_names]


def read_jsonl_records(paths: Iterable[Path]) -> tuple[list[dict[str, str]], dict[str, int]]:
    records: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for path in paths:
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                record = {field: collapse_text(payload.get(field, "")) for field in REQUIRED_FIELDS}
                if record["date"] and record["title"]:
                    records.append(record)
                    count += 1
        counts[path.name] = count
    return records, counts


def deduplicate_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    seen_fallback: set[tuple[str, str, str]] = set()
    for record in records:
        url = record.get("url", "")
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        else:
            fallback_key = (record.get("date", ""), record.get("title", ""), record.get("snippet", ""))
            if fallback_key in seen_fallback:
                continue
            seen_fallback.add(fallback_key)
        deduped.append(record)
    deduped.sort(key=lambda row: (row.get("date", ""), row.get("url", ""), row.get("title", "")))
    return deduped


def write_jsonl(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_metadata(
    *,
    input_dir: Path,
    source_files: list[Path],
    source_counts: dict[str, int],
    merged_records: list[dict[str, str]],
    merged_output: Path,
    sentiment_output: Path,
    sentiment_info: dict[str, object],
    mode: str,
) -> dict[str, object]:
    dates = [record["date"] for record in merged_records if record.get("date")]
    return {
        "input_dir": str(input_dir),
        "include_glob": DEFAULT_INCLUDE_GLOB,
        "source_files": [path.name for path in source_files],
        "source_file_count": len(source_files),
        "source_row_counts": source_counts,
        "merged_rows": len(merged_records),
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "merged_output": str(merged_output),
        "sentiment_output": str(sentiment_output),
        "sentiment_mode": mode,
        "sentiment_info": sentiment_info,
    }


def write_metadata(metadata: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge Liberty Times JSONL exports and build daily sentiment features.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing Liberty Times JSONL files")
    parser.add_argument("--include-glob", default=DEFAULT_INCLUDE_GLOB, help="Input filename pattern")
    parser.add_argument(
        "--exclude-name",
        action="append",
        default=[],
        help="Filename to exclude from merge; can be passed multiple times",
    )
    parser.add_argument("--merged-output", default=str(DEFAULT_MERGED_OUTPUT), help="Merged JSONL output path")
    parser.add_argument("--sentiment-output", default=str(DEFAULT_SENTIMENT_OUTPUT), help="Daily sentiment CSV/Parquet output path")
    parser.add_argument("--metadata-output", default=str(DEFAULT_METADATA_OUTPUT), help="Metadata JSON path")
    parser.add_argument(
        "--mode",
        choices=["auto", "rule_based", "openai_compatible", "pre_scored"],
        default="rule_based",
        help="Scoring mode passed to build_llm_sentiment_features",
    )
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--text-columns", default="title,snippet", help="Comma-separated text columns for headline inputs")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sleep-ms", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = _resolve_path(args.input_dir)
    merged_output = _resolve_path(args.merged_output)
    sentiment_output = _resolve_path(args.sentiment_output)
    metadata_output = _resolve_path(args.metadata_output)
    exclude_names = set(DEFAULT_EXCLUDES) | {name.strip() for name in args.exclude_name if name.strip()}
    text_columns = [item.strip() for item in str(args.text_columns).split(",") if item.strip()]

    source_files = iter_input_paths(input_dir, include_glob=args.include_glob, exclude_names=exclude_names)
    if not source_files:
        raise FileNotFoundError(f"No input JSONL files found in {input_dir} matching {args.include_glob}")

    records, source_counts = read_jsonl_records(source_files)
    merged_records = deduplicate_records(records)
    write_jsonl(merged_records, merged_output)

    sentiment_path, sentiment_info = prepare_llm_sentiment_path(
        merged_output,
        output_path=sentiment_output,
        mode=args.mode,
        date_column=args.date_column,
        text_columns=text_columns,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout=args.timeout,
        sleep_ms=args.sleep_ms,
    )
    metadata = build_metadata(
        input_dir=input_dir,
        source_files=source_files,
        source_counts=source_counts,
        merged_records=merged_records,
        merged_output=merged_output,
        sentiment_output=Path(sentiment_path),
        sentiment_info=sentiment_info,
        mode=args.mode,
    )
    write_metadata(metadata, metadata_output)

    print("=" * 72)
    print("Liberty Times LLM sentiment bundle complete")
    print(f"Input dir:        {input_dir}")
    print(f"Source files:     {len(source_files)}")
    print(f"Merged JSONL:     {merged_output}")
    print(f"Merged rows:      {len(merged_records)}")
    print(f"Sentiment output: {sentiment_path}")
    print(f"Sentiment mode:   {args.mode}")
    print(f"Metadata:         {metadata_output}")


if __name__ == "__main__":
    main()
