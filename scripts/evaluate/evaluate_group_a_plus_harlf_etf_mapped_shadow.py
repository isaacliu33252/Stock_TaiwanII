#!/usr/bin/env python3
"""Evaluate ETF-only mappings for HARLF branch weights.

HARLF research branches may allocate to 2330, but Group A+ execution is ETF-only.
This shadow report compares two conservative mappings without creating orders:

* drop_2330_renormalize: remove 2330 and renormalize remaining ETF weights.
* map_2330_to_0050: add 2330 weight to 0050 as a broad Taiwan equity proxy.
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

from scripts.evaluate.evaluate_group_a_plus_harlf_branch_ablation_shadow import (
    DEFAULT_DB,
    DEFAULT_TICKERS,
    _load_close,
    _metrics,
    _portfolio_turnover_cost,
)


DEFAULT_BRANCH = PROJECT_ROOT / "report/group_a_plus/latest/harlf_branch_ablation_shadow.json"
DEFAULT_META = PROJECT_ROOT / "report/group_a_plus/latest/harlf_compound_defensive_meta_agent_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_etf_mapped_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_etf_mapped_shadow/history"
ETF_ASSETS = ("0050", "00631L", "00632R", "00679B")
MODES = ("drop_2330_renormalize", "map_2330_to_0050")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _monthly_next_returns(close: pd.DataFrame) -> pd.DataFrame:
    monthly_close = close.resample("ME").last()
    next_return = monthly_close.pct_change(fill_method=None).shift(-1)
    next_return.index = [idx.to_period("M").strftime("%Y-%m") for idx in next_return.index]
    return next_return


def _map_weights(weights: dict[str, Any], mode: str) -> dict[str, float]:
    mapped = {asset: float(weights.get(asset, 0.0) or 0.0) for asset in ETF_ASSETS}
    extra = float(weights.get("2330", 0.0) or 0.0)
    if mode == "map_2330_to_0050":
        mapped["0050"] += extra
    elif mode != "drop_2330_renormalize":
        raise ValueError(f"unsupported mapping mode: {mode}")
    total = sum(value for value in mapped.values() if value > 0.0)
    if total <= 1e-12:
        return {asset: 1.0 / len(ETF_ASSETS) for asset in ETF_ASSETS}
    return {asset: max(value, 0.0) / total for asset, value in mapped.items()}


def _reprice_branch_rows(
    branch_report: dict[str, Any],
    next_returns: pd.DataFrame,
    mode: str,
) -> list[dict[str, Any]]:
    prev_weights: dict[str, pd.Series | None] = {}
    rows: list[dict[str, Any]] = []
    for row in branch_report.get("branch_returns") or []:
        month = str(row.get("month"))
        branch = str(row.get("branch"))
        if month not in next_returns.index:
            continue
        mapped = _map_weights(dict(row.get("weights") or {}), mode)
        returns = next_returns.loc[month, list(mapped)].dropna()
        if returns.empty:
            continue
        weights = pd.Series(mapped).reindex(returns.index).fillna(0.0)
        total = float(weights.sum())
        if total <= 1e-12:
            weights = pd.Series(1.0 / len(returns), index=returns.index)
        else:
            weights = weights / total
        gross = float((weights * returns).sum())
        cost = _portfolio_turnover_cost(prev_weights.get(branch), weights)
        prev_weights[branch] = weights
        rows.append(
            {
                "month": month,
                "branch": branch,
                "gross_return": gross,
                "turnover_cost": cost,
                "net_return": gross - cost,
                "assets": list(weights.index),
                "weights": {asset: float(weight) for asset, weight in weights.items()},
                "mapping_mode": mode,
            }
        )
    return rows


def _branch_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}
    out: dict[str, Any] = {}
    for branch, group in frame.groupby("branch"):
        out[branch] = {
            "gross": _metrics(group["gross_return"]),
            "net": _metrics(group["net_return"]),
            "mean_turnover_cost": float(group["turnover_cost"].mean()),
            "evaluated_months": int(len(group)),
        }
    return out


def _meta_returns(rows: list[dict[str, Any]], meta_report: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = {(str(row["month"]), str(row["branch"])): row for row in rows}
    out: list[dict[str, Any]] = []
    for decision in meta_report.get("monthly_decisions") or []:
        month = str(decision.get("month"))
        branch = str(decision.get("selected_branch"))
        row = lookup.get((month, branch))
        if not row:
            continue
        out.append(
            {
                "month": month,
                "selected_branch": branch,
                "net_return": row["net_return"],
                "gross_return": row["gross_return"],
                "turnover_cost": row["turnover_cost"],
                "weights": row["weights"],
            }
        )
    return out


def build_mapped_shadow(
    *,
    branch_report: dict[str, Any],
    meta_report: dict[str, Any],
    close: pd.DataFrame,
) -> dict[str, Any]:
    if close.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_etf_mapped_shadow",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "blocking_reasons": ["missing_close_prices"],
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "promotion_ready": False,
            },
        }
    next_returns = _monthly_next_returns(close)
    variants: dict[str, Any] = {}
    for mode in MODES:
        rows = _reprice_branch_rows(branch_report, next_returns, mode)
        meta_rows = _meta_returns(rows, meta_report)
        meta_series = pd.Series([row["net_return"] for row in meta_rows])
        used_assets = sorted(
            {
                asset
                for row in meta_rows
                for asset, weight in row.get("weights", {}).items()
                if float(weight or 0.0) > 1e-12
            }
        )
        variants[mode] = {
            "branch_metrics": _branch_metrics(rows),
            "meta_agent_metrics": _metrics(meta_series),
            "meta_agent_monthly_returns": meta_rows,
            "meta_agent_used_assets": used_assets,
            "non_etf_assets": sorted(set(used_assets) - set(ETF_ASSETS)),
            "branch_returns": rows,
        }
    ranked = sorted(
        [
            {
                "mapping_mode": mode,
                "meta_total_return": payload["meta_agent_metrics"].get("total_return"),
                "meta_sharpe": payload["meta_agent_metrics"].get("annualized_sharpe"),
                "meta_max_drawdown": payload["meta_agent_metrics"].get("max_drawdown"),
                "non_etf_assets": payload["non_etf_assets"],
            }
            for mode, payload in variants.items()
        ],
        key=lambda row: (row["meta_total_return"] is not None, row["meta_total_return"] or -999.0),
        reverse=True,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_etf_mapped_shadow",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_etf_mapping_no_weight_change",
        "mapping_modes": list(MODES),
        "etf_assets": list(ETF_ASSETS),
        "variants": variants,
        "ranked_mapping_modes": ranked,
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "best_mapping_mode_for_next_shadow": ranked[0]["mapping_mode"] if ranked else None,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_etf_mapped_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--branch", default=str(DEFAULT_BRANCH))
    parser.add_argument("--meta", default=str(DEFAULT_META))
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = tuple(part.strip() for part in str(args.tickers).split(",") if part.strip())
    report = build_mapped_shadow(
        branch_report=_load_json(_resolve(args.branch)),
        meta_report=_load_json(_resolve(args.meta)),
        close=_load_close(_resolve(args.db), tickers),
    )
    report["inputs"] = {
        "db": str(_resolve(args.db)),
        "branch": str(_resolve(args.branch)),
        "meta": str(_resolve(args.meta)),
        "tickers": list(tickers),
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "ranked_mapping_modes": report.get("ranked_mapping_modes"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
