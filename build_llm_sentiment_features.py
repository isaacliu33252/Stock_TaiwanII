#!/usr/bin/env python3
"""Build daily LLM sentiment features for Group A / FinRL-style workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "FinRL" / "data" / "sentiment" / "llm_market_sentiment_daily.csv"
OUTPUT_COLUMNS = [
    "date",
    "llm_sentiment_score",
    "llm_sentiment_confidence",
    "llm_risk_off_score",
    "llm_news_intensity",
]

POSITIVE_TERMS = {
    "bullish", "beat", "surge", "growth", "upgrade", "rebound", "breakout", "optimistic",
    "strong", "improve", "profit", "record", "support", "加碼", "利多", "創高", "成長", "回升", "上修",
}
NEGATIVE_TERMS = {
    "bearish", "miss", "slump", "downgrade", "recession", "fraud", "loss", "cut", "selloff",
    "weak", "decline", "drop", "risk", "panic", "利空", "下修", "虧損", "衰退", "崩跌", "風險",
}
RISK_OFF_TERMS = {
    "war", "tariff", "inflation", "default", "crisis", "panic", "volatility", "hawkish",
    "geopolitical", "recession", "liquidity", "margin call", "戰爭", "通膨", "危機", "恐慌", "波動",
    "升息", "地緣", "違約", "流動性",
}
SUPPORTED_INPUT_SUFFIXES = {".parquet", ".csv", ".tsv", ".json", ".jsonl"}
DATE_COLUMN_CANDIDATES = ("date", "dt", "datetime", "published_at", "timestamp", "pub_date")
TEXT_COLUMN_GROUPS = (
    ("text",),
    ("headline", "summary"),
    ("headline", "description"),
    ("title", "description"),
    ("title", "summary"),
    ("headline",),
    ("title",),
    ("description",),
    ("summary",),
    ("content",),
)
PRE_SCORED_COLUMN_ALIASES = {
    "llm_sentiment_score",
    "llm_sentiment_confidence",
    "llm_risk_off_score",
    "llm_news_intensity",
    "sentiment_score",
    "market_sentiment_score",
    "score",
    "confidence",
    "sentiment_confidence",
    "risk_off_score",
    "risk_off",
    "fear_score",
    "headline_count",
    "news_count",
    "article_count",
    "mention_count",
}


def _resolve_local_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _normalized_columns(df: pd.DataFrame) -> dict[str, str]:
    return {str(col).strip().lower(): col for col in df.columns}


def resolve_date_column(df: pd.DataFrame, preferred: str = "date") -> str:
    if preferred in df.columns:
        return preferred

    lowered = _normalized_columns(df)
    preferred_lower = str(preferred).strip().lower()
    if preferred_lower in lowered:
        return lowered[preferred_lower]

    for candidate in DATE_COLUMN_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    raise ValueError("Input must contain a date-like column")


def _parse_datetime_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    return parsed


def build_date_series(df: pd.DataFrame, preferred: str = "date") -> pd.Series:
    lowered = _normalized_columns(df)
    ordered_columns: list[str] = []

    if preferred in df.columns:
        ordered_columns.append(preferred)
    else:
        preferred_lower = str(preferred).strip().lower()
        preferred_col = lowered.get(preferred_lower)
        if preferred_col is not None:
            ordered_columns.append(preferred_col)

    for candidate in DATE_COLUMN_CANDIDATES:
        candidate_col = lowered.get(candidate)
        if candidate_col is not None and candidate_col not in ordered_columns:
            ordered_columns.append(candidate_col)

    if not ordered_columns:
        raise ValueError("Input must contain a date-like column")

    combined = _parse_datetime_series(df[ordered_columns[0]])
    for col in ordered_columns[1:]:
        combined = combined.fillna(_parse_datetime_series(df[col]))
    return combined


def infer_text_columns(df: pd.DataFrame, explicit: Sequence[str] | None = None) -> list[str]:
    if explicit:
        missing = [col for col in explicit if col not in df.columns]
        if missing:
            raise ValueError(f"Missing text columns: {missing}")
        return list(explicit)

    lowered = _normalized_columns(df)
    for group in TEXT_COLUMN_GROUPS:
        resolved = [lowered.get(candidate) for candidate in group]
        if all(col is not None for col in resolved):
            return [str(col) for col in resolved]
    raise ValueError(
        "Could not infer text columns; provide --text-columns or include one of "
        "text/headline/title/description/summary/content."
    )


def combine_text_columns(df: pd.DataFrame, text_columns: Sequence[str]) -> pd.Series:
    if not text_columns:
        raise ValueError("At least one text column is required")

    text_frame = df[list(text_columns)].copy()
    for col in text_columns:
        text_frame[col] = text_frame[col].fillna("").astype(str).str.strip()
    combined = text_frame.apply(
        lambda row: " ".join(part for part in row if part),
        axis=1,
    )
    return combined.str.replace(r"\s+", " ", regex=True).str.strip()


def is_pre_scored_frame(df: pd.DataFrame) -> bool:
    lowered = set(_normalized_columns(df))
    return bool(lowered & PRE_SCORED_COLUMN_ALIASES)


def infer_mode(df: pd.DataFrame) -> str:
    return "pre_scored" if is_pre_scored_frame(df) else "rule_based"


def _iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"Input path not found: {path}")
    if not path.is_dir():
        raise ValueError(f"Unsupported input path: {path}")

    files = sorted(
        child for child in path.rglob("*")
        if child.is_file() and child.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )
    if not files:
        raise FileNotFoundError(
            f"No supported input files found under {path} "
            f"(expected one of {sorted(SUPPORTED_INPUT_SUFFIXES)})"
        )
    return files


def default_output_path_for_input(input_path: Path) -> Path:
    stem = input_path.stem if input_path.is_file() else input_path.name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "llm_input"
    return DEFAULT_OUTPUT.parent / f"{safe_stem}_llm_market_sentiment_daily.csv"


def read_input_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    if suffix == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return pd.DataFrame(records)
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return pd.DataFrame(payload["data"])
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        return pd.DataFrame([payload])
    raise ValueError(f"Unsupported input format: {path}")


def read_input_source(path: Path) -> pd.DataFrame:
    files = _iter_input_files(path)
    if len(files) == 1 and files[0] == path:
        return read_input_table(path)

    frames: list[pd.DataFrame] = []
    for file_path in files:
        frame = read_input_table(file_path)
        if frame.empty:
            continue
        frame = frame.copy()
        frame["__source_file"] = str(file_path)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def write_output_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix in {".csv", ".tsv"}:
        df.to_csv(path, index=False, sep="\t" if suffix == ".tsv" else ",")
    else:
        raise ValueError(f"Unsupported output format: {path}")


def extract_first_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:200]}")
    return json.loads(match.group(0))


def score_text_rule_based(text: str) -> dict[str, float]:
    lowered = str(text).lower()
    positive_hits = sum(1 for token in POSITIVE_TERMS if token in lowered)
    negative_hits = sum(1 for token in NEGATIVE_TERMS if token in lowered)
    risk_hits = sum(1 for token in RISK_OFF_TERMS if token in lowered)
    total_hits = positive_hits + negative_hits + risk_hits

    raw_score = positive_hits - negative_hits
    sentiment_score = float(np.tanh(raw_score / 3.0))
    confidence = float(min(1.0, 0.25 + 0.15 * total_hits))
    risk_off_score = float(min(1.0, max(risk_hits, negative_hits * 0.5) / 3.0))
    return {
        "llm_sentiment_score": sentiment_score,
        "llm_sentiment_confidence": confidence,
        "llm_risk_off_score": risk_off_score,
    }


def score_text_openai_compatible(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: int,
) -> dict[str, float]:
    prompt = (
        "You are scoring market headlines for a Taiwan ETF allocation model. "
        "Return JSON only with numeric fields: "
        "sentiment_score [-1,1], confidence [0,1], risk_off_score [0,1]. "
        "Use negative scores for risk-off / bearish tone and positive scores for bullish tone."
    )
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": str(text)},
        ],
    }
    endpoint = base_url.rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM scoring failed: HTTP {exc.code} {detail}") from exc

    content = payload["choices"][0]["message"]["content"]
    parsed = extract_first_json_object(content)
    return {
        "llm_sentiment_score": float(np.clip(parsed.get("sentiment_score", 0.0), -1.0, 1.0)),
        "llm_sentiment_confidence": float(np.clip(parsed.get("confidence", 0.0), 0.0, 1.0)),
        "llm_risk_off_score": float(np.clip(parsed.get("risk_off_score", 0.0), 0.0, 1.0)),
    }


def normalize_scored_frame(df: pd.DataFrame, *, date_column: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = build_date_series(out, preferred=date_column)
    alias_map = {
        "sentiment_score": "llm_sentiment_score",
        "market_sentiment_score": "llm_sentiment_score",
        "score": "llm_sentiment_score",
        "confidence": "llm_sentiment_confidence",
        "sentiment_confidence": "llm_sentiment_confidence",
        "risk_off_score": "llm_risk_off_score",
        "risk_off": "llm_risk_off_score",
        "headline_count": "llm_news_intensity",
        "news_count": "llm_news_intensity",
        "article_count": "llm_news_intensity",
        "mention_count": "llm_news_intensity",
    }
    present_aliases = {src: dst for src, dst in alias_map.items() if src in out.columns and dst not in out.columns}
    if present_aliases:
        out = out.rename(columns=present_aliases)

    out["date"] = _parse_datetime_series(out["date"])
    out = out.dropna(subset=["date"]).copy()
    out["date"] = out["date"].dt.normalize()

    for col in ("llm_sentiment_score", "llm_sentiment_confidence", "llm_risk_off_score"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    if "llm_news_intensity" not in out.columns:
        out["llm_news_intensity"] = 1.0
    out["llm_news_intensity"] = pd.to_numeric(out["llm_news_intensity"], errors="coerce").fillna(1.0).clip(lower=0.0)
    return out


def aggregate_daily_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["llm_sentiment_score"] = out["llm_sentiment_score"].clip(-1.0, 1.0)
    out["llm_sentiment_confidence"] = out["llm_sentiment_confidence"].clip(0.0, 1.0)
    out["llm_risk_off_score"] = out["llm_risk_off_score"].clip(0.0, 1.0)

    grouped = out.groupby("date", as_index=False).agg(
        llm_sentiment_score=("llm_sentiment_score", "mean"),
        llm_sentiment_confidence=("llm_sentiment_confidence", "mean"),
        llm_risk_off_score=("llm_risk_off_score", "mean"),
        llm_news_intensity=("llm_news_intensity", "sum"),
    )
    grouped["llm_news_intensity"] = np.log1p(grouped["llm_news_intensity"]).clip(0.0, 5.0)
    return grouped[OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


def build_scored_frame(
    df: pd.DataFrame,
    *,
    mode: str,
    date_column: str,
    text_columns: Sequence[str] | None = None,
    text_column: str | None = None,
    model: str,
    base_url: str,
    api_key: str | None,
    timeout: int,
    sleep_ms: int,
) -> pd.DataFrame:
    resolved_text_columns = infer_text_columns(
        df,
        explicit=text_columns or ([text_column] if text_column else None),
    )

    out = df[list(resolved_text_columns)].copy()
    out["date"] = build_date_series(df, preferred=date_column)
    out["text"] = combine_text_columns(out, resolved_text_columns)
    out["date"] = _parse_datetime_series(out["date"]).dt.normalize()
    out = out.dropna(subset=["date", "text"]).copy()
    out = out[["date", "text"]]

    records = []
    for _, row in out.iterrows():
        text = str(row["text"]).strip()
        if not text:
            continue
        if mode == "rule_based":
            score = score_text_rule_based(text)
        else:
            if not api_key:
                raise RuntimeError("OPENAI-compatible mode requires an API key")
            score = score_text_openai_compatible(
                text,
                model=model,
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        records.append(
            {
                "date": row["date"],
                "llm_sentiment_score": score["llm_sentiment_score"],
                "llm_sentiment_confidence": score["llm_sentiment_confidence"],
                "llm_risk_off_score": score["llm_risk_off_score"],
                "llm_news_intensity": 1.0,
            }
        )

    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


def build_daily_sentiment_features_from_table(
    table: pd.DataFrame,
    *,
    mode: str,
    date_column: str,
    text_columns: Sequence[str] | None = None,
    text_column: str | None = None,
    model: str,
    base_url: str,
    api_key: str | None,
    timeout: int,
    sleep_ms: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if table is None or table.empty:
        raise ValueError("Input table is empty")

    effective_mode = infer_mode(table) if mode == "auto" else mode
    info: dict[str, object] = {
        "mode": effective_mode,
        "input_rows": int(len(table)),
        "text_columns": [],
    }

    if effective_mode == "pre_scored":
        scored = normalize_scored_frame(table, date_column=date_column)
    else:
        resolved_text_columns = infer_text_columns(
            table,
            explicit=text_columns or ([text_column] if text_column else None),
        )
        scored = build_scored_frame(
            table,
            mode=effective_mode,
            date_column=date_column,
            text_columns=resolved_text_columns,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            sleep_ms=sleep_ms,
        )
        info["text_columns"] = list(resolved_text_columns)

    daily = aggregate_daily_features(scored)
    info["daily_rows"] = int(len(daily))
    if not daily.empty:
        info["date_start"] = str(pd.Timestamp(daily["date"].min()).date())
        info["date_end"] = str(pd.Timestamp(daily["date"].max()).date())
    return daily, info


def prepare_llm_sentiment_path(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    mode: str = "auto",
    date_column: str = "date",
    text_columns: Sequence[str] | None = None,
    text_column: str | None = None,
    max_rows: int | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
    timeout: int = 60,
    sleep_ms: int = 0,
) -> tuple[Path, dict[str, object]]:
    source_path = _resolve_local_path(input_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Input path not found: {source_path}")

    table = read_input_source(source_path)
    if max_rows is not None and max_rows > 0:
        table = table.head(max_rows).copy()

    effective_mode = infer_mode(table) if mode == "auto" else mode
    if output_path is None and source_path.is_file() and effective_mode == "pre_scored":
        daily, info = build_daily_sentiment_features_from_table(
            table,
            mode=effective_mode,
            date_column=date_column,
            text_columns=text_columns,
            text_column=text_column,
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv(api_key_env) if effective_mode == "openai_compatible" else None,
            timeout=timeout,
            sleep_ms=sleep_ms,
        )
        info.update(
            {
                "generated": False,
                "path": str(source_path),
                "source_path": str(source_path),
            }
        )
        return source_path, info

    destination = _resolve_local_path(output_path) if output_path else default_output_path_for_input(source_path)
    effective_api_key = os.getenv(api_key_env) if effective_mode == "openai_compatible" else None
    daily, info = build_daily_sentiment_features_from_table(
        table,
        mode=effective_mode,
        date_column=date_column,
        text_columns=text_columns,
        text_column=text_column,
        model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=effective_api_key,
        timeout=timeout,
        sleep_ms=sleep_ms,
    )
    write_output_table(daily, destination)
    info.update(
        {
            "generated": True,
            "path": str(destination),
            "source_path": str(source_path),
        }
    )
    return destination, info


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily LLM sentiment features for market-level ETF workflows.")
    parser.add_argument("--input", required=True, help="Headline-level or pre-scored input file/directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV/Parquet output path")
    parser.add_argument(
        "--mode",
        choices=["auto", "pre_scored", "rule_based", "openai_compatible"],
        default="auto",
        help="How to transform input rows into daily sentiment features",
    )
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--text-column", default="text")
    parser.add_argument(
        "--text-columns",
        default=None,
        help="Comma-separated text columns to concatenate for headline-level inputs",
    )
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sleep-ms", type=int, default=0)
    args = parser.parse_args()

    explicit_text_columns = None
    if args.text_columns:
        explicit_text_columns = [item.strip() for item in args.text_columns.split(",") if item.strip()]
    text_column_arg = args.text_column
    if explicit_text_columns is None and text_column_arg == "text":
        text_column_arg = None

    output_path, info = prepare_llm_sentiment_path(
        args.input,
        output_path=args.output,
        mode=args.mode,
        date_column=args.date_column,
        text_columns=explicit_text_columns,
        text_column=text_column_arg,
        max_rows=args.max_rows,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout=args.timeout,
        sleep_ms=args.sleep_ms,
    )
    daily = read_input_table(output_path)

    print("=" * 72)
    print("LLM sentiment feature build complete")
    print(f"Input:        {_resolve_local_path(args.input)}")
    print(f"Mode:         {info['mode']}")
    print(f"Output:       {output_path}")
    print(f"Daily rows:   {len(daily)}")
    if info.get("text_columns"):
        print(f"Text columns: {', '.join(str(col) for col in info['text_columns'])}")
    if not daily.empty:
        date_start = info.get("date_start") or str(pd.to_datetime(daily["date"]).min().date())
        date_end = info.get("date_end") or str(pd.to_datetime(daily["date"]).max().date())
        print(f"Date range:   {date_start} ~ {date_end}")
        print(f"Mean score:   {daily['llm_sentiment_score'].mean():.4f}")
        print(f"Mean riskOff: {daily['llm_risk_off_score'].mean():.4f}")


if __name__ == "__main__":
    main()
