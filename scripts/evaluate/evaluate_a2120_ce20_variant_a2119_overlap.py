#!/usr/bin/env python3
"""Audit A21.20 CE20 weak-edge variant against A21.19 reentry events.

Research-only.  This checks whether the CE20-negative-to-trend90 variant would
slow 00631L reentry on dates where A21.19 event-study evidence says NO_ADD
would hurt.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from group_a_plus.integrations.leveraged_compounding_regime import CompoundingRegimeThresholds, build_compounding_features, classify_compounding_regime
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import PANEL_2017_2019, PANEL_2025_2026


DEFAULT_A2119_OVERLAP = PROJECT_ROOT / "results" / "a2120_a2119_tunedtrend_overlap_audit_20260715.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2120_ce20_variant_a2119_overlap_audit_20260716.json"

PREFERRED_THRESHOLDS = CompoundingRegimeThresholds(
    ar1_trend_min=0.00,
    ar1_revert_max=-0.15,
    variance_ratio_trend_min=1.02,
    variance_ratio_revert_max=0.98,
    trend_persistence_min=0.50,
    trend_persistence_revert_max=0.55,
    reversal_speed_revert_min=0.55,
    reversal_speed_trend_max=0.50,
    drawdown_recovery_revert_min=0.50,
    trend_score_min=3,
    mean_reversion_score_min=5,
)


WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026),
    ("live_2024_2026", "2024-01-02", "latest", PANEL_2025_2026),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019),
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_latest(db_path: Path, end: str) -> str:
    if end != "latest":
        return end
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = '00631L.TW'").fetchone()
    finally:
        con.close()
    return str(row[0])[:10]


def _classified_by_window(db_path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for label, start, end, _panel in WINDOWS:
        resolved_end = _resolve_latest(db_path, end)
        prices = _load_prices(db_path, ["0050.TW", "00631L.TW"], start, resolved_end).dropna()
        features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
        classified = classify_compounding_regime(features, thresholds=PREFERRED_THRESHOLDS)
        by_date: dict[str, dict[str, Any]] = {}
        for dt, row in classified.iterrows():
            by_date[str(dt.date())] = {
                "compounding_regime": row.get("compounding_regime"),
                "trend_score": int(row.get("trend_score") or 0),
                "mean_reversion_score": int(row.get("mean_reversion_score") or 0),
                "compounding_effect_20d": float(row.get("compounding_effect_20d") or 0.0),
                "relative_momentum_20d": float(row.get("00631L_vs_0050_relative_momentum") or 0.0),
            }
        out[label] = by_date
    return out


def _event_rows(overlap_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in ("overlap_event_rows", "non_overlap_event_rows"):
        for row in overlap_report.get(key) or []:
            if isinstance(row, dict) and "00631l_target_increase" in (row.get("event_types") or []):
                item = dict(row)
                item["source_bucket"] = key
                rows.append(item)
    return rows


def build_audit(*, overlap_report: dict[str, Any], db_path: Path) -> dict[str, Any]:
    classified = _classified_by_window(db_path)
    rows: list[dict[str, Any]] = []
    for event in _event_rows(overlap_report):
        label = str(event.get("window_label"))
        date = str(event.get("date"))
        regime_row = classified.get(label, {}).get(date, {})
        ce20 = float(regime_row.get("compounding_effect_20d") or 0.0)
        main_fast_reentry = str(regime_row.get("compounding_regime")) == "TREND_PERSISTENT"
        ce20_variant_slows = bool(main_fast_reentry and ce20 < 0.0)
        no_add_regret = (event.get("realized_regret") or {}).get("NO_ADD")
        no_add_would_hurt = bool(no_add_regret is not None and float(no_add_regret) < 0.0)
        rows.append(
            {
                "date": date,
                "window_label": label,
                "source_bucket": event.get("source_bucket"),
                "event_types": event.get("event_types"),
                "delta_00631l_weight": event.get("delta_00631l_weight"),
                "no_add_regret": float(no_add_regret) if no_add_regret is not None else None,
                "no_add_would_hurt": no_add_would_hurt,
                "no_add_would_help": bool(no_add_regret is not None and float(no_add_regret) > 0.0),
                "a2120_main_fast_reentry": main_fast_reentry,
                "ce20_variant_slows_reentry": ce20_variant_slows,
                "compounding_effect_20d": ce20,
                "trend_score": regime_row.get("trend_score"),
                "mean_reversion_score": regime_row.get("mean_reversion_score"),
                "relative_momentum_20d": regime_row.get("relative_momentum_20d"),
            }
        )

    slowed = [row for row in rows if row["ce20_variant_slows_reentry"]]
    slowed_hurt = [row for row in slowed if row["no_add_would_hurt"]]
    slowed_help = [row for row in slowed if row["no_add_would_help"]]
    main_overlap = [row for row in rows if row["a2120_main_fast_reentry"]]
    return {
        "schema_version": 1,
        "experiment": "a2120_ce20_variant_a2119_overlap_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "variant": "ce20_negative_to_trend90",
        "summary": {
            "a2119_00631l_increase_events": len(rows),
            "a2120_main_fast_reentry_overlap_events": len(main_overlap),
            "ce20_variant_slowed_overlap_events": len(slowed),
            "ce20_variant_slowed_no_add_hurt_events": len(slowed_hurt),
            "ce20_variant_slowed_no_add_help_events": len(slowed_help),
            "ce20_variant_slowed_total_no_add_regret": sum(float(row["no_add_regret"] or 0.0) for row in slowed),
            "ce20_variant_slowed_hurt_regret_sum": sum(float(row["no_add_regret"] or 0.0) for row in slowed_hurt),
            "pass": len(slowed_help) == 0,
            "interpretation": (
                "CE20 variant slows some A21.19 increase events where NO_ADD would hurt; keep as risk-sensitive advisory."
                if slowed_hurt
                else "CE20 variant does not slow A21.19 increase events where NO_ADD would hurt."
            ),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlap-report", default=str(DEFAULT_A2119_OVERLAP))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_audit(overlap_report=_load_json(Path(args.overlap_report)), db_path=Path(args.db))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
