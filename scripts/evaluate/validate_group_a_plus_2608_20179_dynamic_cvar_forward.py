#!/usr/bin/env python3
"""Forward-validate the 2608.20179 dynamic CVaR residual shadow.

Research-only: tests whether historical CVaR residual breaches are associated
with worse future 00631L downside / underperformance. It never changes live
weights or creates orders.
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
from scripts.evaluate.build_group_a_plus_2608_20179_dynamic_cvar_constraint_shadow import (
    DEFAULT_LIVE_SIGNAL,
    _baseline_weights,
    _load_optional,
    _loss_cvar_budget,
    _weights,
)
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import (
    _load_close_panel,
    _portfolio_returns,
)

DEFAULT_GOLDEN2_SIGNAL = PROJECT_ROOT / "results/golden2_0830/group_a_combined_live_golden2_0830.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_20179_dynamic_cvar_forward_validation.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_20179_dynamic_cvar_forward_validation/history"
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


def _future_path_metrics(returns: pd.Series, *, horizon: int) -> dict[str, float | None]:
    if len(returns) < horizon:
        return {"return": None, "max_drawdown": None, "worst_daily_return": None}
    subset = returns.iloc[:horizon].fillna(0.0)
    curve = (1.0 + subset).cumprod()
    drawdown = curve / curve.cummax() - 1.0
    return {
        "return": float(curve.iloc[-1] - 1.0),
        "max_drawdown": float(drawdown.min()),
        "worst_daily_return": float(subset.min()),
    }


def _expected_shortfall_loss(losses: pd.Series, confidence: float) -> float | None:
    clean = pd.to_numeric(losses, errors="coerce").dropna()
    if clean.empty:
        return None
    var = float(clean.quantile(confidence))
    tail = clean[clean >= var]
    return float(tail.mean()) if len(tail) else var


def _rolling_residual(
    portfolio_returns: pd.Series,
    *,
    asof_pos: int,
    window: int,
    background_risk_buffer: float,
) -> dict[str, Any] | None:
    if asof_pos < window:
        return None
    hist = portfolio_returns.iloc[asof_pos - window : asof_pos].dropna()
    if len(hist) < window // 2:
        return None
    losses = -hist
    es95 = _expected_shortfall_loss(losses, 0.95)
    es99 = _expected_shortfall_loss(losses, 0.99)
    budget95 = _loss_cvar_budget(losses, 0.95, background_risk_buffer)
    budget99 = _loss_cvar_budget(losses, 0.99, background_risk_buffer)
    residual95 = None if es95 is None or budget95 is None else es95 - budget95
    residual99 = None if es99 is None or budget99 is None else es99 - budget99
    breach = bool((residual95 is not None and residual95 > 0) or (residual99 is not None and residual99 > 0))
    return {
        "metrics": {
            "rows": int(len(hist)),
            "expected_shortfall_loss_95": es95,
            "expected_shortfall_loss_99": es99,
        },
        "budget95": budget95,
        "budget99": budget99,
        "residual95": residual95,
        "residual99": residual99,
        "breach": breach,
    }


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "event_count": 0,
            "underperform_rate": None,
            "mean_future_relative_return": None,
            "mean_future_00631l_return": None,
            "mean_future_00631l_mdd": None,
            "mean_latest_minus_no_00631l_future_return": None,
            "mean_latest_minus_no_letf_future_return": None,
        }
    frame = pd.DataFrame(events)
    return {
        "event_count": int(len(frame)),
        "underperform_rate": float(frame["underperforms_0050"].mean()),
        "mean_future_relative_return": float(frame["future_relative_return"].mean()),
        "mean_future_00631l_return": float(frame["future_00631l_return"].mean()),
        "mean_future_00631l_mdd": float(frame["future_00631l_mdd"].mean()),
        "mean_latest_minus_no_00631l_future_return": float(frame["latest_minus_no_00631l_future_return"].mean()),
        "mean_latest_minus_no_letf_future_return": float(frame["latest_minus_no_letf_future_return"].mean()),
    }


def _rank_split(events: list[dict[str, Any]], *, top_quantile: float = 0.8, bottom_quantile: float = 0.2) -> dict[str, Any]:
    clean = [event for event in events if _finite(event.get("residual95")) is not None]
    if len(clean) < 30:
        return {
            "available": False,
            "reason": "insufficient_events",
            "high_residual": _summarize_events([]),
            "low_residual": _summarize_events([]),
            "high_minus_low": {},
        }
    frame = pd.DataFrame(clean)
    high_cut = float(frame["residual95"].quantile(top_quantile))
    low_cut = float(frame["residual95"].quantile(bottom_quantile))
    high = frame[frame["residual95"] >= high_cut].to_dict(orient="records")
    low = frame[frame["residual95"] <= low_cut].to_dict(orient="records")
    high_summary = _summarize_events(high)
    low_summary = _summarize_events(low)
    return {
        "available": bool(high and low),
        "top_quantile": float(top_quantile),
        "bottom_quantile": float(bottom_quantile),
        "high_cut": high_cut,
        "low_cut": low_cut,
        "high_residual": high_summary,
        "low_residual": low_summary,
        "high_minus_low": {
            "underperform_rate": _lift_vs_non_breach(high_summary, low_summary, metric="underperform_rate"),
            "mean_future_00631l_mdd": _lift_vs_non_breach(high_summary, low_summary, metric="mean_future_00631l_mdd"),
            "mean_latest_minus_no_00631l_future_return": _lift_vs_non_breach(
                high_summary,
                low_summary,
                metric="mean_latest_minus_no_00631l_future_return",
            ),
        },
    }


def _lift_vs_non_breach(
    breached: dict[str, Any],
    non_breached: dict[str, Any],
    *,
    metric: str,
) -> float | None:
    left = _finite(breached.get(metric))
    right = _finite(non_breached.get(metric))
    if left is None or right is None:
        return None
    return left - right


def build_report(
    *,
    db_path: Path,
    live_signal_path: Path,
    golden2_signal_path: Path,
    start: str,
    end: str,
    windows: tuple[int, ...],
    horizons: tuple[int, ...],
    background_risk_buffer: float,
    max_events: int,
) -> dict[str, Any]:
    signal = _load_optional(live_signal_path)
    actual_data_date = str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or end)
    latest_weights = _weights(signal)
    golden2_signal = _load_optional(golden2_signal_path)
    baselines = _baseline_weights(latest_weights, golden2_signal)
    panel = _load_close_panel(db_path, TICKERS, start, end, warmup_days=max(windows) + max(horizons) + 10).ffill()
    asset_returns = panel.pct_change().dropna(how="all")
    latest_returns = _portfolio_returns(asset_returns, latest_weights).dropna()
    no_00631l_returns = _portfolio_returns(asset_returns, baselines["no_00631l_to_cash"]).dropna()
    no_letf_returns = _portfolio_returns(asset_returns, baselines["no_letf_to_cash"]).dropna()
    common_index = latest_returns.index.intersection(asset_returns.index)
    latest_returns = latest_returns.loc[common_index]
    no_00631l_returns = no_00631l_returns.loc[common_index]
    no_letf_returns = no_letf_returns.loc[common_index]
    asset_returns = asset_returns.loc[common_index]

    validations: dict[str, Any] = {}
    pass_windows = 0
    valid_windows = 0
    for window in windows:
        by_horizon: dict[str, Any] = {}
        for horizon in horizons:
            breach_events: list[dict[str, Any]] = []
            non_breach_events: list[dict[str, Any]] = []
            for pos, asof in enumerate(common_index):
                if pos < window or pos + horizon >= len(common_index):
                    continue
                residual = _rolling_residual(
                    latest_returns,
                    asof_pos=pos,
                    window=window,
                    background_risk_buffer=background_risk_buffer,
                )
                if residual is None:
                    continue
                future_00631l = _future_path_metrics(asset_returns["00631L.TW"].iloc[pos + 1 :], horizon=horizon)
                future_0050 = _future_path_metrics(asset_returns["0050.TW"].iloc[pos + 1 :], horizon=horizon)
                future_latest = _future_path_metrics(latest_returns.iloc[pos + 1 :], horizon=horizon)
                future_no_00631l = _future_path_metrics(no_00631l_returns.iloc[pos + 1 :], horizon=horizon)
                future_no_letf = _future_path_metrics(no_letf_returns.iloc[pos + 1 :], horizon=horizon)
                if future_00631l["return"] is None or future_0050["return"] is None:
                    continue
                relative_return = float(future_00631l["return"] - future_0050["return"])
                event = {
                    "date": str(pd.Timestamp(asof).date()),
                    "residual95": residual["residual95"],
                    "residual99": residual["residual99"],
                    "future_00631l_return": future_00631l["return"],
                    "future_0050_return": future_0050["return"],
                    "future_relative_return": relative_return,
                    "future_00631l_mdd": future_00631l["max_drawdown"],
                    "underperforms_0050": relative_return < 0,
                    "latest_minus_no_00631l_future_return": None
                    if future_latest["return"] is None or future_no_00631l["return"] is None
                    else float(future_latest["return"] - future_no_00631l["return"]),
                    "latest_minus_no_letf_future_return": None
                    if future_latest["return"] is None or future_no_letf["return"] is None
                    else float(future_latest["return"] - future_no_letf["return"]),
                }
                if residual["breach"]:
                    breach_events.append(event)
                else:
                    non_breach_events.append(event)

            breach_summary = _summarize_events(breach_events)
            non_breach_summary = _summarize_events(non_breach_events)
            all_events = breach_events + non_breach_events
            rank_split = _rank_split(all_events)
            underperform_lift = _lift_vs_non_breach(
                breach_summary,
                non_breach_summary,
                metric="underperform_rate",
            )
            downside_lift = _lift_vs_non_breach(
                breach_summary,
                non_breach_summary,
                metric="mean_future_00631l_mdd",
            )
            latest_vs_no_00631l_lift = _lift_vs_non_breach(
                breach_summary,
                non_breach_summary,
                metric="mean_latest_minus_no_00631l_future_return",
            )
            horizon_pass = bool(
                breach_summary["event_count"] >= 30
                and non_breach_summary["event_count"] >= 30
                and underperform_lift is not None
                and underperform_lift > 0.05
                and latest_vs_no_00631l_lift is not None
                and latest_vs_no_00631l_lift < 0.0
            )
            rank_delta = rank_split.get("high_minus_low") or {}
            rank_pass = bool(
                rank_split.get("available")
                and _finite(rank_delta.get("underperform_rate")) is not None
                and float(rank_delta["underperform_rate"]) > 0.05
                and _finite(rank_delta.get("mean_latest_minus_no_00631l_future_return")) is not None
                and float(rank_delta["mean_latest_minus_no_00631l_future_return"]) < 0.0
            )
            by_horizon[str(horizon)] = {
                "horizon_days": int(horizon),
                "breach": breach_summary,
                "non_breach": non_breach_summary,
                "breach_minus_non_breach": {
                    "underperform_rate": underperform_lift,
                    "mean_future_00631l_mdd": downside_lift,
                    "mean_latest_minus_no_00631l_future_return": latest_vs_no_00631l_lift,
                },
                "rank_split": rank_split,
                "forward_validation_passed": horizon_pass or rank_pass,
                "breach_split_passed": horizon_pass,
                "rank_split_passed": rank_pass,
                "sample_events": {
                    "breach": breach_events[:max_events],
                    "non_breach": non_breach_events[:max_events],
                },
            }
        window_pass = any(row["forward_validation_passed"] for row in by_horizon.values())
        pass_windows += int(window_pass)
        valid_windows += int(bool(by_horizon))
        validations[str(window)] = {
            "window_days": int(window),
            "window_forward_validation_passed": window_pass,
            "horizons": by_horizon,
        }

    validation_passed = pass_windows >= max(1, len(windows) // 2 + 1)
    status = "available_for_shadow_review" if validation_passed else "blocked_for_live_promotion"
    blocking_reasons = [] if validation_passed else ["forward_validation_insufficient_for_live_gate"]
    if valid_windows == 0:
        blocking_reasons.append("no_valid_forward_validation_windows")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_20179_dynamic_cvar_forward_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.20179.pdf",
            "arxiv_id": "2608.20179v1",
            "title": "Dynamic Portfolio Optimization under CVaR Constraints",
            "adapted_concepts": [
                "CVaR constraint residual forward validation",
                "state-dependent leverage-add pacing validation",
                "baseline-relative downside validation",
            ],
        },
        "policy": "research_only_dynamic_cvar_forward_validation_no_weight_change",
        "status": status,
        "as_of": actual_data_date,
        "parameters": {
            "start": start,
            "end": end,
            "windows": list(windows),
            "horizons": list(horizons),
            "background_risk_buffer": float(background_risk_buffer),
            "max_events": int(max_events),
            "latest_weights": latest_weights,
            "baseline_weights": baselines,
            "live_signal_path": str(live_signal_path),
            "golden2_signal_path": str(golden2_signal_path),
        },
        "summary": {
            "valid_windows": valid_windows,
            "forward_validation_pass_windows": pass_windows,
            "forward_validation_passed": validation_passed,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
        },
        "validations": validations,
        "blocking_reasons": blocking_reasons,
        "decision": {
            "review_complete": True,
            "best_import": "forward_validation_for_cvar_residual_shadow_only",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_latest_strategy_unchanged": True,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.20179 Dynamic CVaR Forward Validation",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        f"- Forward validation passed: `{report['summary']['forward_validation_passed']}`",
        f"- Pass windows: `{report['summary']['forward_validation_pass_windows']}` / `{report['summary']['valid_windows']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "| window | horizon | breach n | non-breach n | underperform lift | latest-no00631L lift | passed |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window, row in report["validations"].items():
        for horizon, hrow in row["horizons"].items():
            delta = hrow["breach_minus_non_breach"]
            lines.append(
                "| {window} | {horizon} | {bn} | {nn} | {ulift} | {nlift} | `{passed}` |".format(
                    window=window,
                    horizon=horizon,
                    bn=hrow["breach"]["event_count"],
                    nn=hrow["non_breach"]["event_count"],
                    ulift=_fmt(delta.get("underperform_rate")),
                    nlift=_fmt(delta.get("mean_latest_minus_no_00631l_future_return")),
                    passed=hrow["forward_validation_passed"],
                )
            )
    lines.extend(
        [
            "",
            "## Residual Rank Split",
            "",
            "| window | horizon | high n | low n | high-low underperform | high-low latest-no00631L | rank passed |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for window, row in report["validations"].items():
        for horizon, hrow in row["horizons"].items():
            split = hrow.get("rank_split") or {}
            delta = split.get("high_minus_low") or {}
            lines.append(
                "| {window} | {horizon} | {hn} | {ln} | {ulift} | {nlift} | `{passed}` |".format(
                    window=window,
                    horizon=horizon,
                    hn=(split.get("high_residual") or {}).get("event_count"),
                    ln=(split.get("low_residual") or {}).get("event_count"),
                    ulift=_fmt(delta.get("underperform_rate")),
                    nlift=_fmt(delta.get("mean_latest_minus_no_00631l_future_return")),
                    passed=hrow.get("rank_split_passed"),
                )
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Shadow validation only.",
            "- No target-weight change.",
            "- No automatic rebalance.",
            "- No order generation.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2608_20179_dynamic_cvar_forward_validation_{as_of.replace('-', '')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--golden2-signal", default=str(DEFAULT_GOLDEN2_SIGNAL))
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2026-09-01")
    parser.add_argument("--windows", default="63,126,252")
    parser.add_argument("--horizons", default="5,10,20")
    parser.add_argument("--background-risk-buffer", type=float, default=0.10)
    parser.add_argument("--max-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    windows = tuple(int(x.strip()) for x in str(args.windows).split(",") if x.strip())
    horizons = tuple(int(x.strip()) for x in str(args.horizons).split(",") if x.strip())
    report = build_report(
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        golden2_signal_path=_resolve(args.golden2_signal),
        start=args.start,
        end=args.end,
        windows=windows,
        horizons=horizons,
        background_risk_buffer=args.background_risk_buffer,
        max_events=args.max_events,
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
    print(f"2608.20179 dynamic CVaR forward validation: {output}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
