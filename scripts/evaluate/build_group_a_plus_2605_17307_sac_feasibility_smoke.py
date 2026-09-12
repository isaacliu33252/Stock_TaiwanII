#!/usr/bin/env python3
"""Build a SAC feasibility smoke report for arXiv 2605.17307 and GroupA+.

This is intentionally not a training script. It checks whether the local
project is ready to schedule a controlled SAC experiment without letting SAC
generate live target weights.
"""

from __future__ import annotations

import argparse
import importlib.util
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
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import _load_close  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_sac_feasibility_smoke.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_sac_feasibility_smoke/history"
DEFAULT_STRATEGY = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_LIVE_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_LADDER = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_staged_ladder_readiness.json"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
REQUIRED_MODULES = ("torch", "stable_baselines3", "gymnasium", "numpy", "pandas")
PAPER_WFO_TRADING_DAYS = 252 * 7


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _finite_float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_return_panel(db_path: Path, start: str, end: str) -> tuple[pd.DataFrame, str, list[str]]:
    blockers: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        return pd.DataFrame(), str(end_resolved), ["stock_database_missing"]
    try:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
    except Exception as exc:
        return pd.DataFrame(), str(end_resolved), [f"stock_panel_load_failed:{type(exc).__name__}"]
    if close.empty:
        blockers.append("close_panel_missing")
    missing_tickers = [ticker for ticker in TICKERS if ticker not in close.columns]
    if missing_tickers:
        blockers.append("close_panel_missing_required_tickers")
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if returns.empty:
        blockers.append("return_panel_missing")
    return returns, str(end_resolved), blockers


def _panel_summary(returns: pd.DataFrame) -> dict[str, Any]:
    if returns.empty:
        return {
            "observations": 0,
            "start": None,
            "end": None,
            "tickers": list(TICKERS),
            "missing_return_ratio": None,
            "paper_style_5y_1y_1y_wfo_possible": False,
            "paper_style_wfo_observation_shortfall": PAPER_WFO_TRADING_DAYS,
        }
    obs = int(len(returns))
    missing = float(returns[list(TICKERS)].isna().sum().sum() / max(obs * len(TICKERS), 1))
    shortfall = max(PAPER_WFO_TRADING_DAYS - obs, 0)
    return {
        "observations": obs,
        "start": str(returns.index.min().date()) if hasattr(returns.index.min(), "date") else str(returns.index.min()),
        "end": str(returns.index.max().date()) if hasattr(returns.index.max(), "date") else str(returns.index.max()),
        "tickers": list(TICKERS),
        "missing_return_ratio": _finite_float(missing),
        "paper_style_5y_1y_1y_wfo_possible": obs >= PAPER_WFO_TRADING_DAYS,
        "paper_style_wfo_required_observations": PAPER_WFO_TRADING_DAYS,
        "paper_style_wfo_observation_shortfall": int(shortfall),
    }


def _latest_strategy_id(path: Path) -> str | None:
    strategy = _load_json(path)
    active = strategy.get("active_strategy") if isinstance(strategy.get("active_strategy"), dict) else {}
    value = active.get("id")
    return str(value) if value else None


def _current_assets(live_snapshot_path: Path) -> dict[str, Any]:
    snapshot = _load_json(live_snapshot_path)
    portfolio = snapshot.get("portfolio_state") if isinstance(snapshot.get("portfolio_state"), dict) else {}
    weights = portfolio.get("weights") if isinstance(portfolio.get("weights"), dict) else {}
    out = {ticker: _finite_float(weights.get(ticker), 8) for ticker in TICKERS}
    out["cash"] = _finite_float(portfolio.get("cash_weight"), 8)
    return {
        "weights": out,
        "nonzero_assets": sorted([key for key, value in out.items() if value is not None and abs(value) > 1e-9]),
        "total_weight": _finite_float(sum(value for value in out.values() if value is not None), 8),
    }


def _ladder_state(path: Path) -> dict[str, Any]:
    ladder = _load_json(path)
    latest = ladder.get("latest_state") if isinstance(ladder.get("latest_state"), dict) else {}
    return {
        "risk_aversion_state": latest.get("risk_aversion_state"),
        "best_stage_ready_now": bool(ladder.get("best_stage_ready_now")),
        "best_stage": ladder.get("best_stage"),
    }


def build_smoke_report(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    strategy_path: Path = DEFAULT_STRATEGY,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    ladder_path: Path = DEFAULT_LADDER,
) -> dict[str, Any]:
    modules = {name: _module_available(name) for name in REQUIRED_MODULES}
    returns, end_resolved, blockers = _load_return_panel(_resolve(db_path), start, end)
    panel = _panel_summary(returns)
    if not all(modules.values()):
        blockers.extend(f"python_module_missing:{name}" for name, available in modules.items() if not available)
    if not panel["paper_style_5y_1y_1y_wfo_possible"]:
        blockers.append("insufficient_history_for_paper_style_5y_1y_1y_walk_forward")
    blockers.extend(
        [
            "stable_baselines3_sac_uses_box_action_not_native_dirichlet_simplex_policy",
            "groupa_plus_needs_custom_long_only_sum_to_one_action_projection_before_any_sac_training",
            "no_sac_oos_promotion_gate_exists_for_groupa_plus_live_weights",
        ]
    )
    can_run_environment_smoke = bool(all(modules.values()) and panel["observations"] > 252)
    paper_style_sac_ready = bool(can_run_environment_smoke and not blockers)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_sac_feasibility_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "tested_concept": "SAC_training_feasibility_precheck_only",
        },
        "scope": {
            "runs_policy_training": False,
            "runs_backtest": False,
            "creates_model_file": False,
            "production_effect": "none",
        },
        "environment": {
            "python_modules": modules,
            "stable_baselines3_sac_available": modules.get("stable_baselines3", False),
            "gymnasium_available": modules.get("gymnasium", False),
            "torch_available": modules.get("torch", False),
        },
        "data_panel": panel | {"requested_start": start, "requested_end": end, "resolved_end": end_resolved},
        "action_design": {
            "assets": list(TICKERS) + ["cash"],
            "continuous_action_dimension": len(TICKERS) + 1,
            "required_constraints": ["long_only", "sum_to_one", "cash_allowed", "regime_bounds", "turnover_cost"],
            "sb3_sac_native_action_space": "Box",
            "paper_action_distribution": "Dirichlet_simplex",
            "custom_wrapper_required": True,
        },
        "current_groupa_plus_context": {
            "latest_strategy": _latest_strategy_id(_resolve(strategy_path)),
            "current_authoritative_weights": _current_assets(_resolve(live_snapshot_path)),
            "staged_ladder_state": _ladder_state(_resolve(ladder_path)),
        },
        "decision": {
            "can_run_local_sac_environment_smoke": can_run_environment_smoke,
            "paper_style_sac_training_ready": paper_style_sac_ready,
            "train_sac_now": False,
            "minimal_sac_training_trial_recommended_now": False,
            "allow_sac_generated_target_weights": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Local SAC dependencies exist, but this only clears an environment smoke check. Paper-style SAC training is not ready because GroupA+ still lacks a custom simplex action wrapper, enough paper-style WFO history, and an OOS promotion gate.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_report(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    stamp = str(report.get("data_panel", {}).get("resolved_end") or datetime.now().date()).replace("-", "")
    (history_dir / f"2605_17307_sac_feasibility_smoke_{stamp}.json").write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--ladder", default=str(DEFAULT_LADDER))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_smoke_report(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        strategy_path=_resolve(args.strategy),
        live_snapshot_path=_resolve(args.live_snapshot),
        ladder_path=_resolve(args.ladder),
    )
    write_report(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
