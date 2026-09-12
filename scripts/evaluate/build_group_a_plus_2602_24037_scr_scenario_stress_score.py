#!/usr/bin/env python3
"""Latest SCR scenario stress score for arXiv:2602.24037."""

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

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.build_group_a_plus_2602_24037_scr_readiness_review import (
    DEFAULT_LIVE_SIGNAL,
    DEFAULT_PDF,
    DEFAULT_TICKERS,
    _feature_frame,
    _float,
    _load_close,
    _portfolio_returns,
    _read_pdf_summary,
    _target_weights,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_scenario_stress_score.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2602_24037_scr_scenario_stress_score/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _nearest_scenarios(
    features: pd.DataFrame,
    portfolio_returns: pd.Series,
    *,
    as_of: str,
    min_history: int,
    k_neighbors: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    usable = features.dropna()
    if usable.empty:
        return [], {"status": "insufficient_features"}
    as_of_ts = pd.Timestamp(as_of)
    eligible_current = usable.loc[usable.index <= as_of_ts]
    if eligible_current.empty:
        return [], {"status": "as_of_before_feature_start"}
    current_date = eligible_current.index[-1]
    loc = usable.index.get_loc(current_date)
    if isinstance(loc, slice) or isinstance(loc, np.ndarray) or int(loc) < min_history:
        return [], {"status": "insufficient_history", "as_of": str(current_date.date())}

    next_returns = portfolio_returns.shift(-1)
    history = usable.iloc[: int(loc)].dropna()
    history = history.loc[next_returns.loc[history.index].dropna().index]
    if len(history) < min_history:
        return [], {"status": "insufficient_next_return_history", "as_of": str(current_date.date())}

    current = usable.loc[current_date]
    sigma = history.std(ddof=0).replace(0.0, np.nan)
    normalized_history = (history - history.mean()) / sigma
    normalized_current = (current - history.mean()) / sigma
    distances = ((normalized_history - normalized_current) ** 2).sum(axis=1).pow(0.5).dropna()
    if len(distances) < k_neighbors:
        return [], {"status": "insufficient_neighbors", "as_of": str(current_date.date())}

    selected = distances.nsmallest(k_neighbors)
    rows: list[dict[str, Any]] = []
    for dt, distance in selected.items():
        ret = next_returns.loc[dt]
        if not np.isfinite(ret):
            continue
        rows.append(
            {
                "context_date": str(dt.date()),
                "next_date": str((dt + pd.tseries.offsets.BDay(1)).date()),
                "distance": _float(distance),
                "scenario_next_portfolio_return": _float(ret),
            }
        )
    return rows, {"status": "available", "as_of": str(current_date.date())}


def _scenario_stats(rows: list[dict[str, Any]], *, var_alpha: float, warning_es_threshold: float) -> dict[str, Any]:
    if not rows:
        return {"status": "insufficient_data", "scenario_count": 0}
    returns = np.array(
        [float(row["scenario_next_portfolio_return"]) for row in rows if row.get("scenario_next_portfolio_return") is not None],
        dtype=float,
    )
    if len(returns) == 0:
        return {"status": "insufficient_data", "scenario_count": 0}
    var = float(np.quantile(returns, var_alpha))
    tail = returns[returns <= var]
    es = float(tail.mean()) if len(tail) else var
    prob_loss = float((returns < 0).mean())
    warning = es <= warning_es_threshold
    return {
        "status": "available",
        "scenario_count": int(len(returns)),
        "mean_next_return": _float(np.mean(returns)),
        "median_next_return": _float(np.median(returns)),
        "p10_next_return": _float(np.quantile(returns, 0.10)),
        "var_alpha": var_alpha,
        "var_next_return": _float(var),
        "es_next_return": _float(es),
        "probability_loss": _float(prob_loss),
        "worst_next_return": _float(np.min(returns)),
        "best_next_return": _float(np.max(returns)),
        "warning_es_threshold": warning_es_threshold,
        "downside_warning_active": bool(warning),
    }


def build_score(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    min_history: int = 504,
    k_neighbors: int = 60,
    var_alpha: float = 0.05,
    warning_es_threshold: float = -0.02,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    pdf = _read_pdf_summary(pdf_path)
    if not pdf.get("exists"):
        blockers.append("source_pdf_missing")
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
        end_resolved = end
    else:
        end_resolved = _resolve_end_date(db_path, end) if end == "latest" else end
        close = _load_close(db_path, tickers, start, end_resolved)
    if close.empty or base not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    weights = _target_weights(live_signal_path, tickers)
    if sum(abs(value) for value in weights.values()) <= 0:
        blockers.append("target_weights_missing")

    available = tuple(ticker for ticker in tickers if ticker in returns.columns and returns[ticker].notna().sum() > min_history)
    if base not in available:
        blockers.append("base_has_insufficient_history")

    if blockers:
        scenario_rows: list[dict[str, Any]] = []
        scenario_context = {"status": "blocked"}
        summary = {"status": "blocked", "scenario_count": 0}
    else:
        features = _feature_frame(returns[list(available)], base)
        port_rets = _portfolio_returns(returns[list(available)], weights)
        scenario_rows, scenario_context = _nearest_scenarios(
            features,
            port_rets,
            as_of=end_resolved,
            min_history=min_history,
            k_neighbors=k_neighbors,
        )
        summary = _scenario_stats(
            scenario_rows,
            var_alpha=var_alpha,
            warning_es_threshold=warning_es_threshold,
        )

    if summary.get("downside_warning_active") is True:
        warnings.append("scr_scenario_downside_warning_active")
    if summary.get("status") != "available":
        warnings.append("scr_scenario_score_unavailable")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2602_24037_scr_scenario_stress_score",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "policy": "research_shadow_only_no_orders_no_weight_change",
        "source_paper": pdf,
        "parameters": {
            "start": start,
            "end": end_resolved,
            "tickers": list(tickers),
            "available_tickers": list(available),
            "base": base,
            "min_history": min_history,
            "k_neighbors": k_neighbors,
            "var_alpha": var_alpha,
            "warning_es_threshold": warning_es_threshold,
            "live_signal_path": str(live_signal_path),
            "reference_weights": weights,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "scenario_context": scenario_context,
        "summary": summary,
        "nearest_scenarios": scenario_rows[:20],
        "decision": {
            "score_complete": not blockers and summary.get("status") == "available",
            "best_import": "latest_scr_scenario_downside_stress_score_only",
            "downside_warning_active": summary.get("downside_warning_active") is True,
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "scr_shadow_training_allowed_by_this_score": False,
            "ppo_training_allowed": False,
            "model_training_allowed": False,
            "promote_to_live": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_00679b_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# 2602.24037 SCR Scenario Stress Score",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        f"As of: `{payload.get('scenario_context', {}).get('as_of')}`",
        "",
        "## Summary",
        "",
        f"- Scenario count: `{summary.get('scenario_count')}`",
        f"- Mean next return: `{summary.get('mean_next_return')}`",
        f"- Median next return: `{summary.get('median_next_return')}`",
        f"- P10 next return: `{summary.get('p10_next_return')}`",
        f"- VaR next return: `{summary.get('var_next_return')}`",
        f"- ES next return: `{summary.get('es_next_return')}`",
        f"- Probability loss: `{summary.get('probability_loss')}`",
        f"- Downside warning active: `{summary.get('downside_warning_active')}`",
        "",
        "## Decision",
        "",
        "- Shadow downside stress score only.",
        "- Do not create orders or target weights.",
        "- Do not train SCR-PPO from this score.",
        "- Keep `Golden1_0531` unchanged.",
        "",
    ]
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2602_24037_scr_scenario_stress_score_{as_of.replace('-', '')}.json"


def write_score(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = str(payload.get("parameters", {}).get("end") or datetime.now().strftime("%Y-%m-%d"))
        _history_path(history_dir, as_of).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--min-history", type=int, default=504)
    parser.add_argument("--k-neighbors", type=int, default=60)
    parser.add_argument("--var-alpha", type=float, default=0.05)
    parser.add_argument("--warning-es-threshold", type=float, default=-0.02)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_score(
        pdf_path=_resolve(args.pdf),
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        start=args.start,
        end=args.end,
        min_history=args.min_history,
        k_neighbors=args.k_neighbors,
        var_alpha=args.var_alpha,
        warning_es_threshold=args.warning_es_threshold,
    )
    write_score(
        payload,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"2602.24037 SCR scenario stress score: {_resolve(args.output)}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
