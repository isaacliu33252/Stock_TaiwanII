#!/usr/bin/env python3
"""Fable 00631L round-2 direction #8 (2026-08-23): dedicated shadow log for
a2118's late-bull-hedge trigger -- but reframed after round-2 direction #3
established the trigger fires ZERO times across the full 2017-2026 combined
panel history (not merely rare in one window). A log that only records
"trigger fired: yes/no" would add no information beyond what is already
known (it would say "no" every single day, forever, under current
thresholds).

What genuinely doesn't exist yet and IS useful regardless of whether the
trigger ever fires again: a CONTINUOUS "how close did we come" record. The
trigger requires three simultaneous conditions (ma_gap > NCF_LB_MA_GAP_MIN,
h20_prob_up < NCF_LB_H20_MAX, confidence > NCF_LB_CONF_MIN); this computes
the signed margin for each condition every day (positive = condition met,
negative = how far short) and the BINDING constraint (the minimum of the
three margins -- the condition furthest from being satisfied, i.e. the one
actually preventing the trigger that day). This is new, actionable
diagnostic history that could inform any future threshold recalibration
decision, independent of whether the trigger ever fires again.

Research-only. Read-only over already-existing panels (the 2017-2026
backfill set used in round-2 direction #3) and DB OHLCV. Does not touch
a2118.py, does not change any live threshold, does not wire into the daily
pipeline (that would be a production change requiring separate sign-off).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.runners.a2118 import NCF_LB_CONF_MIN, NCF_LB_H20_MAX, NCF_LB_MA_GAP_MIN  # noqa: E402

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_late_bull_trigger_margin_shadow_log.csv"
DEFAULT_SUMMARY = PROJECT_ROOT / "results" / "a2118_late_bull_trigger_margin_shadow_summary.json"

NCF_PANELS = {
    "2017_2019": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2017_2019_20260710.csv",
    "2020": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2020_20260716.csv",
    "2021": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2021_20260726.csv",
    "2022": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    "2023": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2023_20260726.csv",
    "2024": PROJECT_ROOT / "results" / "ncf_00631l_panel_backfill_2024_20260726.csv",
    "2025_2026_live": PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260716.csv",
}


def _load_ma_gap(db_path: Path) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = '0050.TW' ORDER BY dt").fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.set_index("dt")["close"].astype(float)
    ma100 = close.rolling(100, min_periods=34).mean()
    return (close / ma100 - 1.0).rename("ma_gap")


def build_margin_log(
    *,
    db_path: Path = DB_PATH,
    ma_gap_min: float = NCF_LB_MA_GAP_MIN,
    h20_max: float = NCF_LB_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
) -> pd.DataFrame:
    ma_gap = _load_ma_gap(db_path)
    frames = []
    for label, path in NCF_PANELS.items():
        panel = pd.read_csv(path, encoding="utf-8-sig")
        panel["date"] = pd.to_datetime(panel["date"])
        panel = panel.set_index("date")[["prob_up_h20", "confidence"]].dropna()
        panel["source_panel"] = label
        frames.append(panel)
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.join(ma_gap, how="left").dropna(subset=["ma_gap"])

    combined["ma_gap_margin"] = combined["ma_gap"] - ma_gap_min
    combined["h20_margin"] = h20_max - combined["prob_up_h20"]
    combined["conf_margin"] = combined["confidence"] - conf_min
    combined["binding_margin"] = combined[["ma_gap_margin", "h20_margin", "conf_margin"]].min(axis=1)
    combined["binding_constraint"] = combined[["ma_gap_margin", "h20_margin", "conf_margin"]].idxmin(axis=1)
    combined["would_trigger"] = combined["binding_margin"] > 0.0
    combined.index.name = "date"
    return combined.reset_index()


def summarize(log: pd.DataFrame) -> dict[str, Any]:
    binding_counts = log["binding_constraint"].value_counts().to_dict()
    near_misses = log[(log["binding_margin"] <= 0.0) & (log["binding_margin"] > -0.02)]
    return {
        "total_days": int(len(log)),
        "trigger_days": int(log["would_trigger"].sum()),
        "binding_constraint_counts": {k: int(v) for k, v in binding_counts.items()},
        "binding_constraint_share": {k: float(v / len(log)) for k, v in binding_counts.items()},
        "near_miss_days_within_0.02_of_triggering": int(len(near_misses)),
        "closest_ever_binding_margin": float(log["binding_margin"].max()),
        "closest_ever_date": str(log.loc[log["binding_margin"].idxmax(), "date"]),
        "median_binding_margin": float(log["binding_margin"].median()),
        "years_covered": sorted(pd.to_datetime(log["date"]).dt.year.unique().tolist()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()

    log = build_margin_log()
    summary = summarize(log)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(output, index=False, encoding="utf-8-sig")

    summary_output = Path(args.summary_output)
    summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Saved: {output}")
    print(f"Saved: {summary_output}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
