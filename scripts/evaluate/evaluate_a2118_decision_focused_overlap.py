#!/usr/bin/env python3
"""Compare DFL action-shadow dates with existing risk guards.

Research-only. This script reads a decision-focused action shadow report and
checks whether its effective non-KEEP dates overlap existing volatility-gate
and A21.18 extreme-warning style signals.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame


DEFAULT_INPUT = PROJECT_ROOT / "results" / "a2118_decision_focused_action_shadow_stateful_panelgate_edge0005_adj60_7win_20260714.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_decision_focused_action_overlap_latest.json"


def _load_panel(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    panel_path = _resolve(path)
    if not panel_path.exists():
        return None
    panel = pd.read_csv(panel_path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    panel.index = pd.to_datetime(panel.index).normalize()
    return panel


def _extreme_warning_proxy(panel: pd.DataFrame | None, index: pd.DatetimeIndex, *, h20_max: float, mdd_min: float) -> pd.Series:
    if panel is None:
        return pd.Series(False, index=index, dtype=bool)
    h20 = pd.to_numeric(panel.get("prob_up_h20"), errors="coerce").reindex(index)
    mdd = pd.to_numeric(panel.get("prob_fwd_mdd_gt5_h20"), errors="coerce").reindex(index)
    return ((h20 <= float(h20_max)) & (mdd >= float(mdd_min))).fillna(False).astype(bool)


def _window_overlap(
    item: dict[str, Any],
    *,
    db_path: Path,
    h20_max: float,
    mdd_min: float,
) -> dict[str, Any]:
    start = item["window"]["start"]
    end = item["window"]["end"]
    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip = _load_chip_features(db_path, prices.index, start, end)
    gate = _build_volatility_gate_frame(prices, chip)
    panel = _load_panel(item.get("ncf_panel"))
    extreme = _extreme_warning_proxy(panel, prices.index, h20_max=h20_max, mdd_min=mdd_min)
    non_keep = item.get("non_keep_decisions") or []
    rows: list[dict[str, Any]] = []
    for decision in non_keep:
        dt = pd.Timestamp(decision["date"]).normalize()
        high_vol = bool(gate["high_vol_gate"].reindex([dt]).fillna(False).iloc[0])
        vol_gate = str(gate["volatility_gate"].reindex([dt]).fillna("missing").iloc[0])
        extreme_active = bool(extreme.reindex([dt]).fillna(False).iloc[0])
        rows.append(
            {
                **decision,
                "volatility_gate": vol_gate,
                "volatility_high_vol": high_vol,
                "a2118_extreme_warning_proxy": extreme_active,
                "covered_by_existing_guard": bool(high_vol or extreme_active),
            }
        )
    covered = sum(1 for row in rows if row["covered_by_existing_guard"])
    return {
        "label": item["label"],
        "window": item["window"],
        "non_keep_days": int(len(rows)),
        "covered_by_existing_guard_days": int(covered),
        "coverage_rate": float(covered / len(rows)) if rows else None,
        "volatility_high_vol_days": int(sum(1 for row in rows if row["volatility_high_vol"])),
        "a2118_extreme_warning_proxy_days": int(sum(1 for row in rows if row["a2118_extreme_warning_proxy"])),
        "decisions": rows,
    }


def build_overlap_report(
    input_path: Path,
    *,
    db_path: Path,
    h20_max: float,
    mdd_min: float,
) -> dict[str, Any]:
    report = json.loads(input_path.read_text(encoding="utf-8"))
    results = [
        _window_overlap(item, db_path=db_path, h20_max=h20_max, mdd_min=mdd_min)
        for item in report.get("results", [])
    ]
    total_non_keep = sum(item["non_keep_days"] for item in results)
    total_covered = sum(item["covered_by_existing_guard_days"] for item in results)
    return {
        "report_type": "a2118_decision_focused_action_overlap",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_report": str(input_path),
        "guards": {
            "volatility_gate": "historical high_vol_gate from garch proxy",
            "a2118_extreme_warning_proxy": {
                "prob_up_h20_max": float(h20_max),
                "prob_fwd_mdd_gt5_h20_min": float(mdd_min),
                "note": "proxy uses panel thresholds only; live warning also requires current signal and golden1 regime",
            },
        },
        "summary": {
            "windows": len(results),
            "total_non_keep_days": int(total_non_keep),
            "covered_by_existing_guard_days": int(total_covered),
            "coverage_rate": float(total_covered / total_non_keep) if total_non_keep else None,
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--h20-max", type=float, default=0.22)
    parser.add_argument("--mdd-min", type=float, default=0.85)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_overlap_report(
        _resolve(args.input),
        db_path=_resolve(args.db),
        h20_max=float(args.h20_max),
        mdd_min=float(args.mdd_min),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    summary = payload["summary"]
    print(
        f"Overlap: {summary['covered_by_existing_guard_days']}/{summary['total_non_keep_days']} "
        f"({summary['coverage_rate'] if summary['coverage_rate'] is not None else 'n/a'})"
    )
    for item in payload["results"]:
        if item["non_keep_days"]:
            print(
                f"{item['label']}: covered={item['covered_by_existing_guard_days']}/"
                f"{item['non_keep_days']}, high_vol={item['volatility_high_vol_days']}, "
                f"extreme={item['a2118_extreme_warning_proxy_days']}"
            )


if __name__ == "__main__":
    main()
