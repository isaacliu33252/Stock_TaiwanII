#!/usr/bin/env python3
"""Build a hierarchical cash/equity shadow inspired by arXiv 2605.17307."""

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
from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import (  # noqa: E402
    DEFAULT_LADDER,
    DEFAULT_LIVE_SNAPSHOT,
    TICKERS,
    _float,
    _metrics,
    _normalize,
)
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    _load_close,
    _portfolio_return,
)
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_hierarchical_cash_equity_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_hierarchical_cash_equity_shadow/history"
DEFAULT_EQUITY_BUDGETS = (0.25, 0.30, 0.40)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _split_hierarchy(weights: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize(weights)
    cash = float(normalized.get("cash", 0.0))
    equity_budget = max(0.0, 1.0 - cash)
    sleeve = {
        ticker: value / equity_budget
        for ticker, value in normalized.items()
        if ticker != "cash" and equity_budget > 0.0
    }
    return {
        "equity_budget": _float(equity_budget),
        "cash_budget": _float(cash),
        "equity_sleeve": sleeve,
    }


def _weights_from_hierarchy(sleeve: dict[str, float], equity_budget: float) -> dict[str, float]:
    budget = float(equity_budget)
    out = {ticker: float(weight) * budget for ticker, weight in sleeve.items() if abs(float(weight)) > 1e-12}
    out["cash"] = max(0.0, 1.0 - budget)
    return _normalize(out)


def _base_sleeves(ladder: dict[str, Any], live_snapshot: dict[str, Any]) -> dict[str, dict[str, float]]:
    sleeves: dict[str, dict[str, float]] = {
        "guarded_0050_only_sleeve": {"0050.TW": 1.0},
        "raw_a2118_70_30_sleeve": {"0050.TW": 0.70, "00631L.TW": 0.30},
    }
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    current = dict(portfolio.get("weights") or {})
    if portfolio.get("cash_weight") is not None:
        current["cash"] = portfolio.get("cash_weight")
    if current:
        sleeves["current_authoritative_sleeve"] = _split_hierarchy(current)["equity_sleeve"]
    best_stage = ladder.get("best_ready_stage_if_extreme") if isinstance(ladder.get("best_ready_stage_if_extreme"), dict) else {}
    target = best_stage.get("target_weights") if isinstance(best_stage.get("target_weights"), dict) else {}
    if target:
        sleeves["staged_4pct_sleeve"] = _split_hierarchy(target)["equity_sleeve"]
    return sleeves


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    ladder_path: Path = DEFAULT_LADDER,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    equity_budgets: tuple[float, ...] = DEFAULT_EQUITY_BUDGETS,
) -> dict[str, Any]:
    blockers: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        returns = pd.DataFrame()
    else:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if returns.empty:
        blockers.append("return_panel_missing")
    ladder = _load_json(_resolve(ladder_path))
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    latest = ladder.get("latest_state") if isinstance(ladder.get("latest_state"), dict) else {}
    latest_state = latest.get("risk_aversion_state")
    sleeves = _base_sleeves(ladder, live_snapshot)
    rows: list[dict[str, Any]] = []
    if not returns.empty:
        for sleeve_name, sleeve in sleeves.items():
            for budget in equity_budgets:
                weights = _weights_from_hierarchy(sleeve, budget)
                rows.append(
                    {
                        "candidate": f"{sleeve_name}_equity_{int(round(budget * 100))}pct",
                        "sleeve_name": sleeve_name,
                        "equity_budget": _float(budget),
                        "cash_budget": _float(1.0 - budget),
                        "weights": weights,
                        "metrics": _metrics(_portfolio_return(returns, weights)),
                    }
                )
    rows = sorted(rows, key=lambda row: row["metrics"].get("ir2_like") or -999.0, reverse=True)
    best = rows[0] if rows else None
    best_reviewable_now = bool(
        best
        and best.get("sleeve_name") in {"guarded_0050_only_sleeve", "current_authoritative_sleeve"}
    )
    best_extreme_candidate = next(
        (row for row in rows if row.get("sleeve_name") == "staged_4pct_sleeve" and row.get("equity_budget") == 0.30),
        None,
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_hierarchical_cash_equity_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "imported_concept": "hierarchical_equity_cash_decision_shadow",
            "not_imported": ["SAC_training", "Dirichlet_policy", "RL_generated_target_weights"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "equity_budgets": list(equity_budgets),
            "candidate_generation": "fixed_sleeves_times_fixed_equity_budgets_no_optimization",
        },
        "latest_state": latest,
        "hierarchical_candidates": rows,
        "decision": {
            "best_hierarchical_candidate": best.get("candidate") if best else None,
            "best_hierarchical_candidate_reviewable_now": best_reviewable_now,
            "staged_4pct_equity_30pct_reference_ir2": (best_extreme_candidate or {}).get("metrics", {}).get("ir2_like"),
            "latest_risk_aversion_state": latest_state,
            "hierarchical_shadow_supports_live_weight_change": False,
            "train_sac_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Hierarchical cash/equity shadow is a fixed-grid governance test only; it does not authorize target weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2605_17307_hierarchical_cash_equity_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--ladder", default=str(DEFAULT_LADDER))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--equity-budgets", default="0.25,0.30,0.40")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        ladder_path=_resolve(args.ladder),
        live_snapshot_path=_resolve(args.live_snapshot),
        equity_budgets=tuple(float(item.strip()) for item in args.equity_budgets.split(",") if item.strip()),
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
