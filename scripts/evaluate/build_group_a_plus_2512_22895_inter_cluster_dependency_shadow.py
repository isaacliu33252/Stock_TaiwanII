#!/usr/bin/env python3
"""Build inter-cluster dependency shadow inspired by arXiv 2512.22895 limitations."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2411_19649_semicovariance_review import _load_close  # noqa: E402
from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import TICKERS, _float  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_DYNAMIC_BUCKET = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_dynamic_bucket_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_inter_cluster_dependency_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_inter_cluster_dependency_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _equal_sleeve_return(returns: pd.DataFrame, assets: list[str]) -> pd.Series:
    available = [asset for asset in assets if asset in returns.columns]
    if not available:
        return pd.Series(np.nan, index=returns.index)
    return returns[available].mean(axis=1)


def _semi_corr(left: pd.Series, right: pd.Series, mar: float = 0.0) -> float | None:
    frame = pd.concat([left, right], axis=1).dropna()
    if len(frame) < 10:
        return None
    down = frame.sub(mar).clip(upper=0.0)
    if float(down.iloc[:, 0].std(ddof=0)) <= 1e-12 or float(down.iloc[:, 1].std(ddof=0)) <= 1e-12:
        return None
    return _float(down.iloc[:, 0].corr(down.iloc[:, 1]))


def _conditional_corr(left: pd.Series, right: pd.Series, condition: pd.Series, min_rows: int = 8) -> dict[str, Any]:
    frame = pd.concat([left, right, condition], axis=1).dropna()
    if frame.empty:
        return {"status": "insufficient_data", "observations": 0, "corr": None}
    sample = frame[frame.iloc[:, 2]]
    if len(sample) < min_rows:
        return {"status": "insufficient_conditional_rows", "observations": int(len(sample)), "corr": None}
    return {"status": "available", "observations": int(len(sample)), "corr": _float(sample.iloc[:, 0].corr(sample.iloc[:, 1]))}


def _pair_metrics(returns: pd.DataFrame, left: str, right: str, anchor: str) -> dict[str, Any]:
    columns = list(dict.fromkeys([left, right, anchor]))
    pair = returns[columns].dropna()
    if pair.empty:
        return {"left": left, "right": right, "status": "insufficient_data"}
    return {
        "left": left,
        "right": right,
        "status": "available",
        "ordinary_corr": _float(pair[left].corr(pair[right])),
        "downside_semi_corr": _semi_corr(pair[left], pair[right]),
        "stress_corr_0050_down": _conditional_corr(pair[left], pair[right], pair[anchor] < 0.0),
        "stress_corr_0050_down_1pct": _conditional_corr(pair[left], pair[right], pair[anchor] < -0.01),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    dynamic_bucket_path: Path = DEFAULT_DYNAMIC_BUCKET,
    start: str = "2020-01-01",
    end: str = "latest",
    lookback: int = 75,
) -> dict[str, Any]:
    blockers: list[str] = []
    bucket = _load_json(_resolve(dynamic_bucket_path))
    latest = bucket.get("latest_bucket_snapshot") if isinstance(bucket.get("latest_bucket_snapshot"), dict) else {}
    bucket_rows = latest.get("buckets") if isinstance(latest.get("buckets"), dict) else {}
    if not bucket_rows:
        blockers.append("dynamic_bucket_snapshot_missing")
    quality_assets = [ticker for ticker, row in bucket_rows.items() if row.get("bucket") == "quality"]
    ordinary_assets = [ticker for ticker, row in bucket_rows.items() if row.get("bucket") == "ordinary"]
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if returns.empty or len(returns) < lookback:
        blockers.append("insufficient_return_history")

    latest_window: dict[str, Any] = {}
    pair_rows: list[dict[str, Any]] = []
    if not blockers:
        win = returns.tail(lookback)
        quality_ret = _equal_sleeve_return(win, quality_assets)
        ordinary_ret = _equal_sleeve_return(win, ordinary_assets)
        anchor = win["0050.TW"]
        latest_window = {
            "window_start": str(win.index[0].date()),
            "window_end": str(win.index[-1].date()),
            "quality_assets": quality_assets,
            "ordinary_assets": ordinary_assets,
            "quality_vs_ordinary": {
                "ordinary_corr": _float(quality_ret.corr(ordinary_ret)),
                "downside_semi_corr": _semi_corr(quality_ret, ordinary_ret),
                "stress_corr_0050_down": _conditional_corr(quality_ret, ordinary_ret, anchor < 0.0),
                "stress_corr_0050_down_1pct": _conditional_corr(quality_ret, ordinary_ret, anchor < -0.01),
            },
        }
        for left in quality_assets:
            for right in ordinary_assets:
                pair_rows.append(_pair_metrics(win, left, right, "0050.TW"))

    hedge_row = next((row for row in pair_rows if row.get("right") == "00632R.TW" or row.get("left") == "00632R.TW"), {})
    bond_row = next((row for row in pair_rows if row.get("right") == "00679B.TWO" or row.get("left") == "00679B.TWO"), {})
    hedge_corr = (((hedge_row.get("stress_corr_0050_down") or {}).get("corr")) if hedge_row else None)
    bond_corr = (((bond_row.get("stress_corr_0050_down") or {}).get("corr")) if bond_row else None)
    supports_hedge = hedge_corr is not None and float(hedge_corr) < -0.50
    bond_not_helpful = bond_corr is None or float(bond_corr) > -0.30

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_inter_cluster_dependency_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "imported_concept": "inter_cluster_dependency_diagnostic",
            "paper_limitation_addressed": "dynamic clustering does not explicitly capture inter-cluster dependencies",
            "not_imported": ["graph_neural_network", "correlation_attention_allocator", "live_target_weight_generation"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "lookback": lookback,
            "anchor": "0050.TW",
            "fixed_no_optimization": True,
        },
        "latest_dynamic_bucket": {
            "as_of": latest.get("as_of"),
            "quality_assets": quality_assets,
            "ordinary_assets": ordinary_assets,
        },
        "latest_window_dependency": latest_window,
        "quality_ordinary_pair_metrics": pair_rows,
        "decision": {
            "supports_00632r_hedge": bool(supports_hedge),
            "supports_00679b_as_defensive_diversifier": not bool(bond_not_helpful),
            "inter_cluster_dependency_available": not bool(blockers),
            "target_weight_change_allowed": False,
            "production_effect": "none",
            "summary": "Inter-cluster dependency is a diagnostic only; it can support or question hedge/diversifier roles but cannot change A21.18 weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_inter_cluster_dependency_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--dynamic-bucket", default=str(DEFAULT_DYNAMIC_BUCKET))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--lookback", type=int, default=75)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        dynamic_bucket_path=_resolve(args.dynamic_bucket),
        start=args.start,
        end=args.end,
        lookback=args.lookback,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
