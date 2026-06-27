# Data Refresh Automation

Use [refresh_group_data.py](/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/refresh_group_data.py) to refresh Group A / Group B price caches and DuckDB in one command.

## Manual run

```bash
python3 refresh_group_data.py --group both
python3 refresh_group_data.py --group both --target-date 2026-05-22 --strict
python3 refresh_group_data.py --group both --summary-path results/data_refresh_latest.json
```

Notes:

- Default `--target-date auto` uses `Asia/Taipei`.
- Before `18:00`, it targets the previous weekday.
- Default raw cache windows follow the current operational setup: Group A `2020-01-01`, Group B `2020-01-01`.
- If you want to rebuild a longer Group B window, for example `2017-01-01`, run:

```bash
python3 refresh_group_data.py --group b --group-b-start 2017-01-01 --extra-market-start 2017-01-01
```

- The script checks `FinRL/data/portfolio_cache` and `FinRL/data/stock_data.db` first.
- If everything already covers the target date, it exits without redownloading unless `--force` is set.
- When refresh is needed, it redownloads into a temporary cache, validates the real max date, copies cache files into `FinRL/data/portfolio_cache`, then upserts DuckDB.

## Cron example

Run after Taiwan market data is usually available:

```bash
30 18 * * 1-5 cd /mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main && /usr/bin/python3 refresh_group_data.py --group both --summary-path results/data_refresh_latest.json >> results/data_refresh_cron.log 2>&1
```

## What gets refreshed

- Group A raw caches: `0050.TW`, `00631L.TW`, `00632R.TW`
- Group B raw caches: `0056.TW`, `00713.TW`, `00646.TW`, `00679B.TWO`, `00751B.TWO`
- Market caches: `TWII_DJI_*_1d_market_v3.parquet`
- DuckDB rows in `FinRL/data/stock_data.db`
