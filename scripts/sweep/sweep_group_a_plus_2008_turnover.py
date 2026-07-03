#!/usr/bin/env python3
"""Sweep current GroupA+ turnover caps on the TWII 2008 proxy path."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from compare_group_a_plus_2008_golden_latest import (
    END,
    GOLDEN_2008_SOURCE,
    GROUP_A_PLUS_CONFIG,
    LATEST_MODEL,
    LATEST_PAYLOAD,
    START,
    _capture_existing_golden_source,
    _capture_model_events,
    _load_json,
    _row,
    _run_group_a_plus,
)


def _variant_config(base: dict[str, Any], cap: float) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg.setdefault("execution_control", {})["max_turnover_ratio_by_regime"] = {
        "risk_on": 1.0,
        "caution": 1.0,
        "risk_off": float(cap),
        "severe": float(cap),
    }
    cfg["name"] = f"{base.get('name', 'GroupA+')} turn{int(round(cap * 100)):02d}"
    return cfg


def main() -> None:
    base_config = _load_json(GROUP_A_PLUS_CONFIG)
    caps = [0.25, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08]
    captured = [
        _capture_existing_golden_source(GOLDEN_2008_SOURCE, START, END),
        _capture_model_events(
            name="latest_group_a_production_2020_2025_100k",
            payload_path=LATEST_PAYLOAD,
            model_path=LATEST_MODEL,
            start=START,
            end=END,
        ),
    ]

    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for cap in caps:
        cfg = _variant_config(base_config, cap)
        variant = f"turn{int(round(cap * 100)):02d}"
        for item in captured:
            result = _run_group_a_plus(item, cfg)
            row = _row(item["name"], f"groupA_plus_2008_proxy_{variant}", result["metrics"])
            row["turnover_cap"] = float(cap)
            rows.append(row)
            details[f"{item['name']}:{variant}"] = {
                "metrics": result["metrics"],
                "final_weights": result["final_weights"],
                "final_cash_weight": result["final_cash_weight"],
                "event_count": len(result["events"]),
            }

    output = PROJECT_ROOT / "results" / "group_a_plus_2008_turnover_sweep_20260612.json"
    csv_path = output.with_suffix(".csv")
    report = {
        "experiment": "group_a_plus_2008_turnover_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {"start": START, "end": END},
        "group_a_plus_config": str(GROUP_A_PLUS_CONFIG.resolve()),
        "base_profile": base_config.get("recommended_profile", {}).get("name", base_config.get("name")),
        "turnover_caps": caps,
        "rows": rows,
        "details": details,
        "limitations": [
            "TWII-derived proxy path, not exact ETF trading history.",
            "00679B is synthetic because true 2008 00679B history does not exist.",
            "Missing 2008-era TDCC/institutional/margin/LLM inputs are proxied or zero-filled.",
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in rows:
        print(
            f"{row['strategy']} / {row['mode']}: "
            f"final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, vol={row['volatility']:.4%}"
        )


if __name__ == "__main__":
    main()
