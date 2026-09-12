#!/usr/bin/env python3
"""Build an IR2-like candidate scorecard inspired by arXiv 2605.17307."""

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
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    _load_close,
    _portfolio_return,
)
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_ir2_candidate_scorecard.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_ir2_candidate_scorecard/history"
DEFAULT_LADDER = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json"
DEFAULT_LIVE_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _annualized_return(returns: pd.Series) -> float:
    values = (1.0 + returns.fillna(0.0)).cumprod()
    if values.empty:
        return 0.0
    years = len(values) / 252.0
    return float(values.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = returns.fillna(0.0)
    if clean.empty:
        return {
            "observations": 0,
            "annualized_return": None,
            "annualized_volatility": None,
            "max_drawdown": None,
            "sharpe": None,
            "ir1": None,
            "ir2_like": None,
        }
    equity = (1.0 + clean).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    arc = _annualized_return(clean)
    vol = float(clean.std(ddof=0) * np.sqrt(252.0))
    mdd = float(drawdown.min())
    sharpe = float(clean.mean() / clean.std(ddof=0) * np.sqrt(252.0)) if clean.std(ddof=0) > 0 else 0.0
    ir1 = arc / vol if vol > 0 else 0.0
    ir2 = ir1 * arc * np.sign(arc) / abs(mdd) if mdd < 0 else 0.0
    return {
        "observations": int(len(clean)),
        "annualized_return": _float(arc),
        "annualized_volatility": _float(vol),
        "max_drawdown": _float(mdd),
        "sharpe": _float(sharpe),
        "ir1": _float(ir1),
        "ir2_like": _float(ir2),
    }


def _normalize(weights: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in weights.items():
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(val) and abs(val) > 1e-12:
            out[str(key)] = val
    return out


def _candidate_weights(ladder: dict[str, Any], live_snapshot: dict[str, Any]) -> dict[str, dict[str, float]]:
    candidates: dict[str, dict[str, float]] = {
        "guarded_live_target_0050_30_cash_70": {"0050.TW": 0.30, "cash": 0.70},
        "raw_a2118_target_0050_70_00631l_30": {"0050.TW": 0.70, "00631L.TW": 0.30},
        "equal_0050_00631l_cash": {"0050.TW": 1.0 / 3.0, "00631L.TW": 1.0 / 3.0, "cash": 1.0 / 3.0},
    }
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    current = dict(portfolio.get("weights") or {})
    if portfolio.get("cash_weight") is not None:
        current["cash"] = portfolio.get("cash_weight")
    if current:
        candidates["current_authoritative_portfolio"] = _normalize(current)
    for stage in ladder.get("stage_reviews", []) if isinstance(ladder.get("stage_reviews"), list) else []:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id") or "")
        target = stage.get("target_weights")
        if stage_id and isinstance(target, dict):
            candidates[f"staged_ladder_{stage_id}"] = _normalize(target)
    return candidates


def build_scorecard(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    ladder_path: Path = DEFAULT_LADDER,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
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
    candidates = _candidate_weights(ladder, live_snapshot)
    rows: list[dict[str, Any]] = []
    latest = ladder.get("latest_state") if isinstance(ladder.get("latest_state"), dict) else {}
    latest_state = latest.get("risk_aversion_state")
    if not returns.empty:
        for name, weights in candidates.items():
            port = _portfolio_return(returns, weights)
            eligibility = "review_only"
            eligibility_blockers: list[str] = []
            if name == "equal_0050_00631l_cash":
                eligibility = "benchmark_only_not_trade_candidate"
                eligibility_blockers.append("not_existing_groupa_plus_policy_candidate")
            elif name == "raw_a2118_target_0050_70_00631l_30":
                eligibility = "blocked_by_existing_governance"
                eligibility_blockers.append("raw_a2118_target_disallowed_by_existing_tail_and_cost_gates")
            elif name.startswith("staged_ladder_"):
                eligibility = "manual_review_candidate_only_if_extreme"
                if latest_state != "EXTREME":
                    eligibility_blockers.append("latest_state_not_extreme")
            elif name == "current_authoritative_portfolio":
                eligibility = "status_quo_reference"
            elif name == "guarded_live_target_0050_30_cash_70":
                eligibility = "existing_guarded_reference"
            rows.append(
                {
                    "candidate": name,
                    "weights": weights,
                    "metrics": _metrics(port),
                    "governance_eligibility": eligibility,
                    "eligibility_blockers": sorted(set(eligibility_blockers)),
                }
            )
    rows = sorted(rows, key=lambda row: (row["metrics"].get("ir2_like") is not None, row["metrics"].get("ir2_like") or -999), reverse=True)
    best = rows[0] if rows else None
    governed_pool = [
        row
        for row in rows
        if row.get("governance_eligibility") in {"status_quo_reference", "existing_guarded_reference", "manual_review_candidate_only_if_extreme"}
    ]
    best_governed = governed_pool[0] if governed_pool else None
    best_governed_active_now = bool(best_governed and not best_governed.get("eligibility_blockers"))
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_ir2_candidate_scorecard",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "imported_concept": "IR2_like_drawdown_adjusted_candidate_scorecard",
            "not_imported": ["SAC_training", "RL_generated_target_weights", "Transformer_policy"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "candidate_generation": "fixed_existing_groupa_plus_candidates_only_no_optimization",
        },
        "candidate_rankings": rows,
        "decision": {
            "best_raw_ir2_candidate": best.get("candidate") if best else None,
            "best_governed_candidate": best_governed.get("candidate") if best_governed else None,
            "best_governed_candidate_active_now": best_governed_active_now,
            "latest_risk_aversion_state": latest_state,
            "ir2_scorecard_supports_live_weight_change": False,
            "train_sac_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "IR2-like scorecard is a governance ranking only; it cannot authorize weights or SAC training.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_scorecard(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2605_17307_ir2_candidate_scorecard_{as_of.replace('-', '')}.json").write_text(
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
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_scorecard(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        ladder_path=_resolve(args.ladder),
        live_snapshot_path=_resolve(args.live_snapshot),
    )
    write_scorecard(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
