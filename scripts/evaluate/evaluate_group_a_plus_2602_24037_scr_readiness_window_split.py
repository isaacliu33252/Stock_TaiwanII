#!/usr/bin/env python3
"""Window-split SCR readiness diagnostics for arXiv:2602.24037."""

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
    _scenario_audit,
    _summarize_rows,
    _target_weights,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_window_split.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_window_split.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2602_24037_scr_readiness_window_split/history"

WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("covid_2020", "2020-02-03", "2020-06-30"),
    ("rate_hike_2022", "2022-01-03", "2022-12-30"),
    ("post_2023", "2023-01-03", "2026-08-28"),
    ("recent_2024_2026", "2024-01-02", "2026-08-28"),
    ("active_2025_2026", "2025-01-02", "2026-08-28"),
)


def _filter_rows(rows: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [row for row in rows if start <= str(row.get("date") or "") <= end]


def build_window_split(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    data_start: str = "2018-01-02",
    end: str = "latest",
    windows: tuple[tuple[str, str, str], ...] = WINDOWS,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    min_history: int = 252,
    k_neighbors: int = 30,
    gap_limit: float = 0.01,
) -> dict[str, Any]:
    blockers: list[str] = []
    pdf = _read_pdf_summary(pdf_path)
    if not pdf.get("exists"):
        blockers.append("source_pdf_missing")
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
        end_resolved = end
    else:
        end_resolved = _resolve_end_date(db_path, end) if end == "latest" else end
        close = _load_close(db_path, tickers, data_start, end_resolved)
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
    rows: list[dict[str, Any]] = []
    if base in available and not blockers:
        features = _feature_frame(returns[list(available)], base)
        port_rets = _portfolio_returns(returns[list(available)], weights)
        earliest = min(start for _label, start, _end in windows)
        all_rows = _scenario_audit(
            returns[list(available)],
            features,
            port_rets,
            eval_start=earliest,
            min_history=min_history,
            k_neighbors=k_neighbors,
        )
    else:
        all_rows = []

    for label, start, window_end in windows:
        window_rows = _filter_rows(all_rows, start, window_end)
        summary = _summarize_rows(window_rows, gap_limit=gap_limit)
        beta = summary.get("beta_cf_from_bias_variance_proxy")
        rows.append(
            {
                "label": label,
                "start": start,
                "end": window_end,
                "summary": summary,
                "gap_gate_passed": summary.get("scenario_real_gap_gate_passed") is True,
                "beta_cf_moderate": isinstance(beta, (int, float)) and 0.25 <= float(beta) <= 0.75,
            }
        )

    valid = [row for row in rows if row["summary"].get("status") == "available"]
    gap_pass = [row for row in valid if row["gap_gate_passed"]]
    beta_ok = [row for row in valid if row["beta_cf_moderate"]]
    mean_gaps = [
        float(row["summary"]["mean_abs_scenario_real_gap"])
        for row in valid
        if isinstance(row["summary"].get("mean_abs_scenario_real_gap"), (int, float))
    ]
    betas = [
        float(row["summary"]["beta_cf_from_bias_variance_proxy"])
        for row in valid
        if isinstance(row["summary"].get("beta_cf_from_bias_variance_proxy"), (int, float))
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2602_24037_scr_readiness_window_split",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked_for_live_promotion" if blockers else "available_for_shadow_review",
        "policy": "research_shadow_only_no_rl_training_no_live_weight_change",
        "source_paper": pdf,
        "parameters": {
            "data_start": data_start,
            "end": end_resolved,
            "windows": [{"label": label, "start": start, "end": window_end} for label, start, window_end in windows],
            "tickers": list(tickers),
            "available_tickers": list(available),
            "base": base,
            "min_history": min_history,
            "k_neighbors": k_neighbors,
            "gap_limit": gap_limit,
            "live_signal_path": str(live_signal_path),
            "reference_weights": weights,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "all_audit_rows": int(len(all_rows)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "rows": rows,
        "summary": {
            "valid_windows": len(valid),
            "gap_gate_pass_windows": len(gap_pass),
            "beta_moderate_windows": len(beta_ok),
            "mean_gap_min": _float(min(mean_gaps)) if mean_gaps else None,
            "mean_gap_max": _float(max(mean_gaps)) if mean_gaps else None,
            "beta_cf_min": _float(min(betas)) if betas else None,
            "beta_cf_max": _float(max(betas)) if betas else None,
            "stress_gap_readiness_passed": bool(valid) and len(gap_pass) == len(valid),
            "stress_beta_cf_moderate_passed": bool(valid) and len(beta_ok) == len(valid),
        },
        "decision": {
            "window_split_complete": True,
            "best_import": "scr_readiness_and_mismatch_guard_only",
            "scr_shadow_training_allowed_by_this_window_split": False,
            "ppo_training_allowed": False,
            "model_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_00679b_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# 2602.24037 SCR Readiness Window Split",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        "",
        "## Summary",
        "",
        f"- Valid windows: `{summary['valid_windows']}`",
        f"- Gap gate pass windows: `{summary['gap_gate_pass_windows']}`",
        f"- Beta moderate windows: `{summary['beta_moderate_windows']}`",
        f"- Mean gap range: `{summary['mean_gap_min']}` to `{summary['mean_gap_max']}`",
        f"- Beta cf range: `{summary['beta_cf_min']}` to `{summary['beta_cf_max']}`",
        f"- Stress gap readiness passed: `{summary['stress_gap_readiness_passed']}`",
        f"- Stress beta cf moderate passed: `{summary['stress_beta_cf_moderate_passed']}`",
        "",
        "## Rows",
        "",
        "| Window | OOS days | Mean gap | P90 gap | Beta cf | Gap pass | Beta moderate |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload["rows"]:
        stats = row["summary"]
        lines.append(
            "| {label} | {oos_days} | {mean_gap} | {p90_gap} | {beta} | {gap_pass} | {beta_ok} |".format(
                label=row["label"],
                oos_days=stats.get("oos_days"),
                mean_gap=stats.get("mean_abs_scenario_real_gap"),
                p90_gap=stats.get("p90_abs_scenario_real_gap"),
                beta=stats.get("beta_cf_from_bias_variance_proxy"),
                gap_pass=row.get("gap_gate_passed"),
                beta_ok=row.get("beta_cf_moderate"),
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Keep as shadow readiness guard only.",
            "- Do not train SCR-PPO from this window split.",
            "- Do not change target weights or rebalance.",
            "- Keep `Golden1_0531` unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2602_24037_scr_readiness_window_split_{as_of.replace('-', '')}.json"


def write_outputs(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
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
    parser.add_argument("--data-start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--min-history", type=int, default=252)
    parser.add_argument("--k-neighbors", type=int, default=30)
    parser.add_argument("--gap-limit", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_window_split(
        pdf_path=Path(args.pdf),
        db_path=Path(args.db),
        live_signal_path=Path(args.live_signal),
        data_start=args.data_start,
        end=args.end,
        min_history=args.min_history,
        k_neighbors=args.k_neighbors,
        gap_limit=args.gap_limit,
    )
    write_outputs(payload, Path(args.output), Path(args.output_md), None if args.no_history else Path(args.history_dir))
    print(f"2602.24037 SCR readiness window split: {Path(args.output).resolve()}")
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "decision": payload["decision"]}, indent=2))


if __name__ == "__main__":
    main()
