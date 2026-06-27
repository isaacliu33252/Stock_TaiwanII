#!/usr/bin/env python3
"""Run latest GroupA+ on several TWII proxy stress windows."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import twii_proxy_utils
from compare_group_a_plus_2008_golden_latest import (
    GROUP_A_PLUS_CONFIG,
    LATEST_MODEL,
    LATEST_PAYLOAD,
    _capture_model_events,
    _load_json,
    _row,
    _run_group_a_plus,
)


PROJECT_ROOT = Path(__file__).resolve().parent
WINDOWS = [
    ("gfc_2008", "2007-07-01", "2010-12-31"),
    ("china_fx_2015", "2015-01-01", "2016-12-31"),
    ("china_fx_2016_partial", "2016-01-01", "2016-12-31"),
    ("covid_2020", "2020-01-01", "2020-12-31"),
    ("inflation_2022", "2022-01-01", "2022-12-31"),
]
TWII_2008_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20030101_20110101_1d_market_v2.parquet"
TWII_2015_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20150101_20161231_1d_market_v3.parquet"
TWII_2016_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20160101_20260509_1d_market_v2.parquet"
TWII_2020_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20200101_20260608_1d_market_v3.parquet"


def _select_twii_cache(start: str) -> Path | None:
    year = pd.Timestamp(start).year
    if year < 2011:
        return TWII_2008_CACHE
    if year == 2015:
        return TWII_2015_CACHE
    if year >= 2016 and year < 2020:
        return TWII_2016_CACHE
    if year >= 2020:
        return TWII_2020_CACHE
    return None


def main() -> None:
    config = _load_json(GROUP_A_PLUS_CONFIG)
    rows: list[dict[str, Any]] = []
    strategies: dict[str, Any] = {}
    skipped: list[dict[str, str]] = []

    for label, start, end in WINDOWS:
        cache = _select_twii_cache(start)
        if cache is None or not cache.exists():
            skipped.append({"window": label, "reason": f"no local TWII proxy cache for {start} ~ {end}"})
            continue
        twii_proxy_utils.DEFAULT_TWII_MARKET_CACHE = cache
        try:
            captured = _capture_model_events(
                name="latest_group_a_production_2020_2025_100k",
                payload_path=LATEST_PAYLOAD,
                model_path=LATEST_MODEL,
                start=start,
                end=end,
            )
        except Exception as exc:
            skipped.append({"window": label, "reason": str(exc)})
            continue
        plus = _run_group_a_plus(captured, config)
        base_row = {"window": label, **_row(captured["name"], "base_model_proxy", captured["base_metrics"])}
        plus_row = {"window": label, **_row(captured["name"], "groupA_plus_current_proxy", plus["metrics"])}
        rows.extend([base_row, plus_row])
        strategies[label] = {
            "requested_window": {"start": start, "end": end},
            "twii_market_cache": str(cache.resolve()),
            "actual_window": {
                "start": captured["actual_start"],
                "end": captured["actual_end"],
                "rows": captured["rows"],
            },
            "base_metrics": captured["base_metrics"],
            "group_a_plus_metrics": plus["metrics"],
            "delta_plus_vs_base": {
                key: float(plus["metrics"][key] - captured["base_metrics"][key])
                for key in ["final_value", "sharpe_ratio", "max_drawdown", "volatility", "contribution_return"]
            },
            "group_a_plus_event_count": len(plus["events"]),
        }

    report = {
        "experiment": "group_a_plus_multi_window_twii_proxy_stress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "group_a_plus_config": str(GROUP_A_PLUS_CONFIG.resolve()),
        "group_a_plus_profile": config.get("recommended_profile", {}).get("name", config.get("name")),
        "model_path": str(LATEST_MODEL.resolve()),
        "payload_path": str(LATEST_PAYLOAD.resolve()),
        "proxy_method": {
            "0050.TW": "1x TWII daily returns",
            "00631L.TW": "2x TWII daily returns",
            "00632R.TW": "-1x TWII daily returns",
            "00679B.TWO": "synthetic lower-volatility bond proxy",
        },
        "strategies": strategies,
        "skipped": skipped,
        "comparison_rows": rows,
        "limitations": [
            "TWII-derived proxy paths are stress scenarios, not exact ETF trading histories.",
            "00679B is synthetic for periods before its listing history is available.",
            "Unavailable historical institutional, margin, and LLM inputs are zero-filled by the proxy capture path.",
        ],
    }

    output = PROJECT_ROOT / "results" / "group_a_plus_multi_window_stress_20260612.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for item in skipped:
        print(f"SKIPPED {item['window']}: {item['reason']}")
    for row in rows:
        print(
            f"{row['window']} / {row['mode']}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"vol={row['volatility']:.4%}, contribution_return={row['contribution_return']:.4%}"
        )


if __name__ == "__main__":
    main()
