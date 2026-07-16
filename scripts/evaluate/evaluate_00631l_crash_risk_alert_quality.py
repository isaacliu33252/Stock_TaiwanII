#!/usr/bin/env python3
"""Evaluate alert-only 00631L crash-risk snapshot quality.

Reads report/group_a_plus/crash_risk_alert/history/*.json and summarizes
what happened to 00631L.TW after alert/watch days. This is monitoring only;
it does not change live signals or target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_oracle_ceiling import _label_max_drawdown
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_race_classifier import _load_ohlc

DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "crash_risk_alert" / "history"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "crash_risk_alert" / "quality_latest.json"


def _load_history(history_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        as_of = payload.get("as_of")
        if not isinstance(as_of, str) or not as_of:
            continue
        rows.append(
            {
                "as_of": pd.Timestamp(as_of),
                "watch_level": payload.get("watch_level"),
                "alert_active": bool(payload.get("alert_active", False)),
                "category_score": int(payload.get("category_score", 0) or 0),
                "freshness_status": (payload.get("freshness") or {}).get("status"),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["as_of", "watch_level", "alert_active", "category_score", "freshness_status"])
    return pd.DataFrame(rows).drop_duplicates("as_of", keep="last").sort_values("as_of")


def _rate(values: pd.Series, threshold: float) -> float | None:
    valid = values.dropna()
    if valid.empty:
        return None
    return float((valid <= threshold).mean())


def evaluate(*, history_dir: Path, db_path: Path, output: Path, horizons: tuple[int, ...]) -> dict[str, Any]:
    hist = _load_history(history_dir)
    if hist.empty:
        payload = {"status": "no_history", "history_dir": str(history_dir), "rows": 0}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    close = _load_ohlc(db_path, "00631L.TW", "2015-01-01", "2100-01-01")["close"].astype(float)
    frame = hist.set_index("as_of")
    for h in horizons:
        frame[f"forward_mdd_{h}d"] = _label_max_drawdown(close, h).reindex(frame.index)

    groups = {
        "all": frame,
        "watch_or_higher": frame[frame["category_score"] >= 1],
        "medium_or_higher": frame[frame["category_score"] >= 2],
        "active_alert": frame[frame["alert_active"]],
    }
    summaries = {}
    for name, part in groups.items():
        item: dict[str, Any] = {
            "count": int(len(part)),
            "freshness_degraded_count": int((part["freshness_status"] == "degraded").sum()) if len(part) else 0,
        }
        for h in horizons:
            values = part[f"forward_mdd_{h}d"] if len(part) else pd.Series(dtype=float)
            item[f"mean_forward_mdd_{h}d"] = float(values.mean()) if values.notna().any() else None
            item[f"hit_rate_mdd_le_5pct_{h}d"] = _rate(values, -0.05)
            item[f"hit_rate_mdd_le_8pct_{h}d"] = _rate(values, -0.08)
        summaries[name] = item

    payload = {
        "status": "ok",
        "history_dir": str(history_dir),
        "rows": int(len(frame)),
        "date_range": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
        },
        "summaries": summaries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--horizons", default="5,10,20")
    args = parser.parse_args()

    horizons = tuple(int(item) for item in args.horizons.split(",") if item.strip())
    payload = evaluate(history_dir=args.history_dir, db_path=args.db.resolve(), output=args.output, horizons=horizons)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
