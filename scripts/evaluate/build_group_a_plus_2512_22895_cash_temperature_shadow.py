#!/usr/bin/env python3
"""Build a cash-temperature shadow inspired by arXiv 2512.22895 SAMP-HDRL."""

from __future__ import annotations

import argparse
import json
import math
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
from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import TICKERS, _float  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import _load_close  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "results/group_a_combined_live_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_cash_temperature_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_cash_temperature_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _softmax(logits: list[float], temperature: float) -> list[float]:
    temp = max(float(temperature), 1e-6)
    arr = np.array(logits, dtype=float) / temp
    arr = arr - np.nanmax(arr)
    exp = np.exp(arr)
    return [float(x) for x in exp / exp.sum()]


def _portfolio_return(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=returns.index)
    for ticker, weight in weights.items():
        if ticker == "cash" or ticker not in returns.columns:
            continue
        out = out.add(returns[ticker].fillna(0.0) * float(weight), fill_value=0.0)
    return out


def _sortino(ret: pd.Series) -> float:
    clean = ret.dropna()
    if clean.empty:
        return 0.0
    downside = clean[clean < 0.0]
    denom = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
    if denom <= 1e-12:
        return 0.0
    return float(clean.mean() / denom)


def _live_weights(live_signal: dict[str, Any]) -> dict[str, float]:
    raw = dict(live_signal.get("target_weights") or {})
    raw["cash"] = float(live_signal.get("target_cash_weight") or live_signal.get("cash_weight") or 0.0)
    total = sum(float(v) for v in raw.values())
    if total <= 0:
        return {}
    return {k: float(v) / total for k, v in raw.items()}


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    start: str = "2020-01-01",
    end: str = "latest",
    window: int = 75,
    temperatures: tuple[float, ...] = (0.50, 0.75, 1.00, 1.50, 2.00),
) -> dict[str, Any]:
    blockers: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    live_signal = _load_json(_resolve(live_signal_path))
    live_weights = _live_weights(live_signal)
    if not live_weights:
        blockers.append("live_target_weights_missing")
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if returns.empty or len(returns) < window:
        blockers.append("insufficient_return_history")

    diagnostics: list[dict[str, Any]] = []
    sleeve_weights: dict[str, float] = {}
    sleeve_ret = pd.Series(dtype=float)
    metrics: dict[str, float] = {}
    if not blockers:
        live_cash = float(live_weights.get("cash", 0.0))
        risky_budget = max(1.0 - live_cash, 1e-12)
        sleeve_weights = {
            ticker: float(weight) / risky_budget
            for ticker, weight in live_weights.items()
            if ticker != "cash" and float(weight) > 0.0
        }
        win = returns.tail(window)
        sleeve_ret = _portfolio_return(win, sleeve_weights)
        mean = float(sleeve_ret.mean())
        vol = float(sleeve_ret.std(ddof=0))
        downside = sleeve_ret[sleeve_ret < 0.0]
        downside_vol = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
        momentum_20 = float(sleeve_ret.tail(20).sum()) if len(sleeve_ret) >= 20 else 0.0
        sortino = _sortino(sleeve_ret)
        # Fixed, interpretable logits: risky attractiveness versus cash baseline 0.
        risk_penalty = downside_vol * math.sqrt(252.0) * 2.0
        risky_logit = 8.0 * sortino + 3.0 * momentum_20 - risk_penalty
        cash_logit = 0.0
        metrics = {
            "mean_daily_return": _float(mean),
            "daily_vol": _float(vol),
            "downside_vol": _float(downside_vol),
            "momentum_20": _float(momentum_20),
            "sortino": _float(sortino),
            "risk_penalty": _float(risk_penalty),
            "risky_logit": _float(risky_logit),
            "cash_logit": _float(cash_logit),
        }
        for temp in temperatures:
            cash_weight, risky_weight = _softmax([cash_logit, risky_logit], temp)
            diagnostics.append(
                {
                    "temperature": _float(temp),
                    "diagnostic_cash_weight": _float(cash_weight),
                    "diagnostic_risky_weight": _float(risky_weight),
                    "cash_gap_vs_live": _float(cash_weight - live_cash),
                }
            )

    reference = next((row for row in diagnostics if abs(row["temperature"] - 1.0) < 1e-9), diagnostics[0] if diagnostics else {})
    live_cash = float(live_weights.get("cash", 0.0)) if live_weights else None
    diagnostic_cash = reference.get("diagnostic_cash_weight")
    if diagnostic_cash is None or live_cash is None:
        cash_bias = "unknown"
    elif live_cash < diagnostic_cash - 0.10:
        cash_bias = "live_cash_lower_than_diagnostic"
    elif live_cash > diagnostic_cash + 0.10:
        cash_bias = "live_cash_higher_than_diagnostic"
    else:
        cash_bias = "live_cash_near_diagnostic"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_cash_temperature_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "imported_concept": "risk_free_cash_baseline_temperature_allocation_diagnostic",
            "not_imported": ["softmax_live_allocator", "hierarchical_DRL_training", "target_weight_generation"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "window": window,
            "temperatures": list(temperatures),
            "fixed_no_optimization": True,
        },
        "live_signal": {
            "requested_as_of_date": live_signal.get("requested_as_of_date"),
            "actual_data_date": live_signal.get("actual_data_date"),
            "weights": live_weights,
            "cash_weight": _float(live_cash) if live_cash is not None else None,
        },
        "risky_sleeve_weights": sleeve_weights,
        "risky_sleeve_metrics": metrics,
        "temperature_diagnostics": diagnostics,
        "decision": {
            "reference_temperature": 1.0,
            "reference_diagnostic_cash_weight": diagnostic_cash,
            "live_cash_bias": cash_bias,
            "supports_increasing_cash": cash_bias == "live_cash_lower_than_diagnostic",
            "supports_decreasing_cash": cash_bias == "live_cash_higher_than_diagnostic",
            "target_weight_change_allowed": False,
            "production_effect": "none",
            "summary": "Cash-temperature output is a diagnostic only; it cannot change A21.18 cash or ETF weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_cash_temperature_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--window", type=int, default=75)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        live_signal_path=_resolve(args.live_signal),
        start=args.start,
        end=args.end,
        window=args.window,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
