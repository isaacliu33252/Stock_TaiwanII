#!/usr/bin/env python3
"""Inspect local parquet date ranges for a ticker keyword."""

import argparse
from pathlib import Path

import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect parquet date ranges.")
    parser.add_argument("keyword", help="Keyword in parquet filename, for example 0056")
    args = parser.parse_args()

    roots = [
        Path("data/cache"),
        Path("data/portfolio_cache"),
        Path("../data/cache"),
        Path("../data/portfolio_cache"),
    ]
    paths = []
    for root in roots:
        if root.exists():
            paths.extend(root.glob(f"*{args.keyword}*.parquet"))
            paths.extend(root.glob(f"*{args.keyword}*.parquet.bak"))

    for path in sorted(paths):
        try:
            pf = pq.ParquetFile(path)
            date_col = None
            names = pf.schema_arrow.names
            for candidate in ("date", "Date"):
                if candidate in names:
                    date_col = names.index(candidate)
                    break
            if date_col is None:
                date_col = 0
            stats = pf.metadata.row_group(0).column(date_col).statistics
            print(f"{path}\trows={pf.metadata.num_rows}\tmin={stats.min}\tmax={stats.max}")
        except Exception as exc:
            print(f"{path}\tERROR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
