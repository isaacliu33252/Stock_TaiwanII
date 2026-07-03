"""Generate a lightweight local data registry for GroupA+ workflows."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import NEWS_DIR, PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


def _table_summary(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, Any]:
    cols = con.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = ?
        ORDER BY ordinal_position
        """,
        [table],
    ).fetchall()
    column_names = [row[0] for row in cols]
    date_col = "dt" if "dt" in column_names else ("date" if "date" in column_names else None)
    row_count = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    summary: dict[str, Any] = {
        "table": table,
        "row_count": row_count,
        "columns": [{"name": name, "type": typ} for name, typ in cols],
        "date_column": date_col,
    }
    if date_col:
        dates = con.execute(f"SELECT min({date_col}), max({date_col}) FROM {table}").fetchone()
        summary["date_start"] = str(dates[0]) if dates and dates[0] is not None else None
        summary["date_end"] = str(dates[1]) if dates and dates[1] is not None else None
    for key_col in ("ticker", "stock_id", "futures_id", "option_id", "commodity_id", "market_type"):
        if key_col in column_names:
            values = con.execute(f"SELECT DISTINCT {key_col} FROM {table} ORDER BY {key_col} LIMIT 50").fetchall()
            summary[f"{key_col}_values"] = [str(row[0]) for row in values]
    return summary


def build_registry(db_path: Path, news_dir: Path) -> dict[str, Any]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = [
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        ]
        table_summaries = [_table_summary(con, table) for table in tables]
    finally:
        con.close()

    news_files = []
    if news_dir.exists():
        for path in sorted(news_dir.glob("*.jsonl")) + sorted(news_dir.glob("*.csv")):
            stat = path.stat()
            news_files.append(
                {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )

    topics = []
    for table in table_summaries:
        name = table["table"]
        if name == "ohlcv":
            topics.append({"topic": "market:ohlcv:<ticker>", "source": name, "ttl": "daily"})
        elif "derivative" in name or "dealer_options" in name or "taifex" in name:
            topics.append({"topic": f"derivatives:{name}", "source": name, "ttl": "daily"})
        elif any(part in name for part in ("institutional", "margin", "shareholding", "lending", "short", "day_trading")):
            topics.append({"topic": f"chip:{name}", "source": name, "ttl": "daily"})
        else:
            topics.append({"topic": f"data:{name}", "source": name, "ttl": "daily"})
    if news_files:
        topics.append({"topic": "news:ltn:market", "source": "news/*.jsonl", "ttl": "manual"})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path.relative_to(PROJECT_ROOT) if db_path.is_relative_to(PROJECT_ROOT) else db_path),
        "table_count": len(table_summaries),
        "tables": table_summaries,
        "news_files": news_files,
        "topic_registry": topics,
        "notes": [
            "Registry is intentionally static: it records local coverage and topic naming for runners.",
            "It does not fetch or mutate any market data.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--news-dir", default=str(NEWS_DIR))
    parser.add_argument("--output", default="results/group_a_plus_data_registry_20260619.json")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.data.registry")
    try:
        registry = build_registry(Path(args.db), Path(args.news_dir))
        payload = std.success(registry)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Registry: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()

