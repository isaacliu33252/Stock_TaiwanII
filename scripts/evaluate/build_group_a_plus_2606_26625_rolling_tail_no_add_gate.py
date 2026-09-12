#!/usr/bin/env python3
"""Rolling tail dashboard and no-add gate inspired by arXiv 2606.26625.

Research-only: converts CVaR/EVT/turnover governance into daily no-add
diagnostics. It never changes target weights, orders, or strategy state.
"""

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
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import (
    _hill_tail_index,
    _load_close_panel,
    _portfolio_returns,
    _summarize_returns,
)

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_26625_rolling_tail_no_add_gate/history"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _load_signal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _weights(signal: dict[str, Any]) -> dict[str, float]:
    raw = {str(k): float(v) for k, v in dict(signal.get("target_weights") or {}).items()}
    for ticker in TICKERS:
        raw.setdefault(ticker, 0.0)
    raw["cash"] = raw.get("cash", max(0.0, 1.0 - sum(raw[ticker] for ticker in TICKERS)))
    total = sum(max(0.0, raw.get(key, 0.0)) for key in [*TICKERS, "cash"])
    if total <= 0:
        raise ValueError("live signal target weights must have positive total")
    return {key: max(0.0, raw.get(key, 0.0)) / total for key in [*TICKERS, "cash"]}


def _variants(latest: dict[str, float]) -> dict[str, dict[str, float]]:
    no_00631l = dict(latest)
    no_00631l["cash"] += no_00631l["00631L.TW"]
    no_00631l["00631L.TW"] = 0.0

    no_00632r = dict(latest)
    no_00632r["cash"] += no_00632r["00632R.TW"]
    no_00632r["00632R.TW"] = 0.0

    no_letf = dict(no_00631l)
    no_letf["cash"] += no_letf["00632R.TW"]
    no_letf["00632R.TW"] = 0.0

    return {
        "latest_strategy": latest,
        "no_00631l_to_cash": no_00631l,
        "no_00632r_to_cash": no_00632r,
        "no_letf_to_cash": no_letf,
    }


def _tail_gap(latest: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    latest_es = _finite(latest.get("expected_shortfall_loss_95"))
    ref_es = _finite(reference.get("expected_shortfall_loss_95"))
    latest_mdd = _finite(latest.get("max_drawdown"))
    ref_mdd = _finite(reference.get("max_drawdown"))
    return {
        "es95_delta_vs_reference": None if latest_es is None or ref_es is None else latest_es - ref_es,
        "mdd_delta_vs_reference": None if latest_mdd is None or ref_mdd is None else latest_mdd - ref_mdd,
        "latest_worse_es95": bool(latest_es is not None and ref_es is not None and latest_es > ref_es),
        "latest_worse_mdd": bool(latest_mdd is not None and ref_mdd is not None and latest_mdd < ref_mdd),
    }


def build_report(
    *,
    db_path: Path,
    live_signal_path: Path,
    end: str,
    windows: tuple[int, ...],
    es_gap_threshold: float,
    hill_xi_threshold: float,
) -> dict[str, Any]:
    signal = _load_signal(live_signal_path)
    actual_data_date = str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or end)
    latest_weights = _weights(signal)
    start = (pd.Timestamp(end) - pd.Timedelta(days=max(windows) * 2 + 30)).strftime("%Y-%m-%d")
    panel = _load_close_panel(db_path, TICKERS, start, end, warmup_days=10).ffill()
    asset_returns = panel.pct_change().dropna(how="all")
    variants = _variants(latest_weights)

    rolling: dict[str, Any] = {}
    no_00631l_blocks = 0
    no_00632r_blocks = 0
    no_letf_blocks = 0
    for window in windows:
        subset = asset_returns.tail(int(window))
        metrics: dict[str, Any] = {}
        for name, weights in variants.items():
            returns = _portfolio_returns(subset, weights)
            metrics[name] = _summarize_returns(returns)
        latest_metrics = metrics["latest_strategy"]
        gap_00631l = _tail_gap(latest_metrics, metrics["no_00631l_to_cash"])
        gap_00632r = _tail_gap(latest_metrics, metrics["no_00632r_to_cash"])
        gap_letf = _tail_gap(latest_metrics, metrics["no_letf_to_cash"])
        losses = -_portfolio_returns(subset, latest_weights).dropna().to_numpy(dtype=float)
        hill = _hill_tail_index(losses, 0.95)
        high_hill = bool((_finite(hill.get("hill_xi")) or 0.0) > float(hill_xi_threshold))
        block_00631l = bool(((_finite(gap_00631l["es95_delta_vs_reference"]) or 0.0) > es_gap_threshold) or high_hill)
        block_00632r = bool(((_finite(gap_00632r["es95_delta_vs_reference"]) or 0.0) > es_gap_threshold) or high_hill)
        block_letf = bool(((_finite(gap_letf["es95_delta_vs_reference"]) or 0.0) > es_gap_threshold) or high_hill)
        no_00631l_blocks += int(block_00631l)
        no_00632r_blocks += int(block_00632r)
        no_letf_blocks += int(block_letf)
        rolling[str(window)] = {
            "rows": int(len(subset)),
            "start": str(subset.index.min().date()) if len(subset) else None,
            "end": str(subset.index.max().date()) if len(subset) else None,
            "latest_hill_95": hill,
            "metrics": metrics,
            "gaps": {
                "no_00631l_to_cash": gap_00631l,
                "no_00632r_to_cash": gap_00632r,
                "no_letf_to_cash": gap_letf,
            },
            "window_gate": {
                "block_00631l_add": block_00631l,
                "block_00632r_open": block_00632r,
                "block_any_letf_add": block_letf,
                "high_hill_tail_index": high_hill,
            },
        }

    allow_00631l_add = no_00631l_blocks == 0
    allow_00632r_open = no_00632r_blocks == 0
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_26625_rolling_tail_no_add_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.26625.pdf",
            "title": "Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns",
            "adapted_concepts": ["rolling CVaR dashboard", "EVT/Hill no-add warning", "conservative-variant tail gap"],
        },
        "policy": "research_only_rolling_tail_no_add_gate_no_weight_change",
        "status": "available_for_shadow_monitoring",
        "as_of": actual_data_date,
        "parameters": {
            "end": end,
            "windows": list(windows),
            "es_gap_threshold": float(es_gap_threshold),
            "hill_xi_threshold": float(hill_xi_threshold),
            "live_signal_path": str(live_signal_path),
            "latest_weights": latest_weights,
        },
        "summary": {
            "window_count": len(windows),
            "block_00631l_add_windows": no_00631l_blocks,
            "block_00632r_open_windows": no_00632r_blocks,
            "block_any_letf_add_windows": no_letf_blocks,
            "allow_00631l_add": allow_00631l_add,
            "allow_00632r_open": allow_00632r_open,
            "allow_any_letf_add": no_letf_blocks == 0,
        },
        "rolling_windows": rolling,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": allow_00631l_add,
            "allow_00632r_open": allow_00632r_open,
            "allow_00679b_add": False,
            "manual_review_required": not (allow_00631l_add and allow_00632r_open),
            "best_import": "rolling_cvar_evt_no_add_shadow_gate",
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2606.26625 Rolling Tail No-Add Gate",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        f"- 00631L add: `{'allowed' if report['decision']['allow_00631l_add'] else 'blocked'}`",
        f"- 00632R open: `{'allowed' if report['decision']['allow_00632r_open'] else 'blocked'}`",
        f"- Policy: `{report['policy']}`",
        "",
        "| window | latest ES95 | no-00631L ES95 | no-00632R ES95 | no-LETF ES95 | Hill xi95 | block 00631L | block 00632R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window, row in report["rolling_windows"].items():
        metrics = row["metrics"]
        gate = row["window_gate"]
        lines.append(
            "| {window} | {latest} | {no631} | {no632} | {noletf} | {hill} | `{b631}` | `{b632}` |".format(
                window=window,
                latest=_fmt(metrics["latest_strategy"].get("expected_shortfall_loss_95")),
                no631=_fmt(metrics["no_00631l_to_cash"].get("expected_shortfall_loss_95")),
                no632=_fmt(metrics["no_00632r_to_cash"].get("expected_shortfall_loss_95")),
                noletf=_fmt(metrics["no_letf_to_cash"].get("expected_shortfall_loss_95")),
                hill=_fmt(row["latest_hill_95"].get("hill_xi")),
                b631=gate["block_00631l_add"],
                b632=gate["block_00632r_open"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Shadow monitoring only.",
            "- No target-weight change.",
            "- No automatic rebalance.",
            "- No order generation.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2606_26625_rolling_tail_no_add_gate_{as_of.replace('-', '')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--windows", default="63,126,252")
    parser.add_argument("--es-gap-threshold", type=float, default=0.001)
    parser.add_argument("--hill-xi-threshold", type=float, default=0.25)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    windows = tuple(int(x.strip()) for x in str(args.windows).split(",") if x.strip())
    report = build_report(
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        end=args.end,
        windows=windows,
        es_gap_threshold=args.es_gap_threshold,
        hill_xi_threshold=args.hill_xi_threshold,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, _resolve(args.md_output))
    if not args.no_history:
        history_dir = _resolve(args.history_dir)
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(report["as_of"])).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"2606.26625 rolling tail no-add gate: {output}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
