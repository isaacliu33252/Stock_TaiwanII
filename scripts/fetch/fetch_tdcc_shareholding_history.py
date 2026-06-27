#!/usr/bin/env python3
"""Fetch the one-year TDCC shareholding history available from the official query page."""

from __future__ import annotations

import argparse
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import parse_shareholding_distribution_rows, upsert_shareholding_distribution


QUERY_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
DEFAULT_TICKERS = "0050,00631L,00632R"


def _extract_hidden(html: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}"\s+value="([^"]*)"', html)
    if not match:
        raise RuntimeError(f"Missing hidden input: {name}")
    return match.group(1)


def _extract_dates(html: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'<option value="(\d{8})"', html)))


class _TDCCStockTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table" and "table" in str(attr_map.get("class", "")).split():
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"td", "th"} and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif self.in_table and tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
        elif self.in_table and tag == "table":
            self.in_table = False


def _parse_history_html(html: str, stock_id: str, sca_date: str) -> pd.DataFrame:
    parser = _TDCCStockTableParser()
    parser.feed(html)
    rows = [row for row in parser.rows if len(row) == 5]
    if not rows or "持股/單位數分級" not in rows[0]:
        return pd.DataFrame()

    normalized_rows: list[dict[str, object]] = []
    for row in rows[1:]:
        tier_label = str(row[1]).replace("\u3000", "").strip()
        if tier_label == "合計":
            level: object = "合計"
        else:
            level = row[0]
        normalized_rows.append(
            {
                "資料日期": sca_date,
                "證券代號": stock_id,
                "持股分級": level,
                "人數": row[2],
                "股數": row[3],
                "占集保庫存數比例%": row[4],
            }
        )
    return parse_shareholding_distribution_rows(normalized_rows, source="tdcc_qryStock")


def fetch_history(
    tickers: list[str],
    *,
    pause_seconds: float = 0.15,
    selected_dates: list[str] | None = None,
    retries: int = 3,
) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
    )
    first = session.get(QUERY_URL, timeout=30)
    first.raise_for_status()
    dates = _extract_dates(first.text)
    if not dates:
        raise RuntimeError(f"TDCC page did not expose history dates: url={first.url}, bytes={len(first.text)}")
    if selected_dates:
        selected = set(selected_dates)
        dates = [sca_date for sca_date in dates if sca_date in selected]

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        for idx, sca_date in enumerate(dates, start=1):
            frame = pd.DataFrame()
            for attempt in range(max(int(retries), 1)):
                page = session.get(QUERY_URL, timeout=30)
                page.raise_for_status()
                html = page.text
                response = session.post(
                    QUERY_URL,
                    data={
                        "SYNCHRONIZER_TOKEN": _extract_hidden(html, "SYNCHRONIZER_TOKEN"),
                        "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock",
                        "method": "submit",
                        "firDate": _extract_hidden(html, "firDate"),
                        "scaDate": sca_date,
                        "sqlMethod": "StockNo",
                        "stockNo": ticker,
                        "stockName": "",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                frame = _parse_history_html(response.text, ticker, sca_date)
                if not frame.empty:
                    break
                time.sleep(0.5 * (attempt + 1))
            if frame.empty:
                print(f"[TDCC] WARN {ticker} {sca_date}: no rows")
            else:
                frames.append(frame)
                print(f"[TDCC] {ticker} {sca_date}: {len(frame)} rows ({idx}/{len(dates)})")
            time.sleep(max(float(pause_seconds), 0.0))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=DEFAULT_TICKERS, help="Comma-separated TDCC stock IDs")
    parser.add_argument("--dates", default="", help="Optional comma-separated YYYYMMDD dates")
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    tickers = [item.strip().upper() for item in args.tickers.split(",") if item.strip()]
    dates = [item.strip() for item in args.dates.split(",") if item.strip()]
    rows = fetch_history(tickers, pause_seconds=args.pause_seconds, selected_dates=dates, retries=args.retries)
    if rows.empty:
        raise SystemExit("No TDCC rows fetched")
    written = upsert_shareholding_distribution(rows)
    print(
        f"[TDCC] rows_written={written}, stocks={rows['stock_id'].nunique()}, "
        f"dates={rows['dt'].nunique()}, range={rows['dt'].min()} ~ {rows['dt'].max()}"
    )


if __name__ == "__main__":
    main()
