#!/usr/bin/env python3
"""Dynamic CVaR-constraint shadow review inspired by arXiv 2608.20179.

Research-only: estimates rolling CVaR budget residuals and state-dependent
exposure pacing for GroupA+. It never changes target weights or orders.
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
    _load_close_panel,
    _portfolio_returns,
    _summarize_returns,
)

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_ROLLING_TAIL_GATE = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_rolling_tail_no_add_gate.json"
DEFAULT_GOLDEN2_SIGNAL = PROJECT_ROOT / "results/golden2_0830/group_a_combined_live_golden2_0830.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_20179_dynamic_cvar_constraint_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_20179_dynamic_cvar_constraint_shadow/history"
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


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
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


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    raw = {ticker: max(0.0, float(weights.get(ticker, 0.0))) for ticker in TICKERS}
    raw["cash"] = max(0.0, float(weights.get("cash", 0.0)))
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("weights must have positive total")
    return {key: value / total for key, value in raw.items()}


def _baseline_weights(latest: dict[str, float], golden2_signal: dict[str, Any]) -> dict[str, dict[str, float]]:
    no_00631l = dict(latest)
    no_00631l["cash"] += no_00631l["00631L.TW"]
    no_00631l["00631L.TW"] = 0.0

    no_letf = dict(no_00631l)
    no_letf["cash"] += no_letf["00632R.TW"]
    no_letf["00632R.TW"] = 0.0

    baselines = {
        "no_00631l_to_cash": _normalize(no_00631l),
        "no_letf_to_cash": _normalize(no_letf),
        "golden1_0531_static": _normalize({"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}),
    }
    if golden2_signal:
        baselines["golden2_0830"] = _weights(golden2_signal)
    return baselines


def _loss_cvar_budget(values: pd.Series, quantile: float, buffer: float) -> float | None:
    base = _finite(values.quantile(quantile))
    if base is None:
        return None
    return max(0.0, base * (1.0 - float(buffer)))


def _state_bucket(
    *,
    latest_return: float | None,
    latest_drawdown: float | None,
    residual95: float | None,
    near_threshold: float,
) -> str:
    if residual95 is not None and residual95 > near_threshold:
        return "adverse_cvar_breach"
    if latest_drawdown is not None and latest_drawdown <= -0.08:
        return "adverse_drawdown"
    if latest_return is not None and latest_return > 0 and latest_drawdown is not None and latest_drawdown > -0.03:
        return "favorable"
    return "neutral"


def _pacing_multiplier(state_bucket: str, residual95: float | None, residual99: float | None) -> float:
    max_residual = max([x for x in (residual95, residual99) if x is not None], default=0.0)
    if state_bucket.startswith("adverse") or max_residual > 0:
        return 0.0
    if state_bucket == "neutral":
        return 0.5
    return 1.0


def _historical_drawdown(returns: pd.Series) -> pd.Series:
    curve = (1.0 + returns.fillna(0.0)).cumprod()
    return curve / curve.cummax() - 1.0


def _relative_gap(latest_metrics: dict[str, Any], baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    latest_es95 = _finite(latest_metrics.get("expected_shortfall_loss_95"))
    baseline_es95 = _finite(baseline_metrics.get("expected_shortfall_loss_95"))
    latest_mdd = _finite(latest_metrics.get("max_drawdown"))
    baseline_mdd = _finite(baseline_metrics.get("max_drawdown"))
    return {
        "es95_delta_vs_baseline": None if latest_es95 is None or baseline_es95 is None else latest_es95 - baseline_es95,
        "mdd_delta_vs_baseline": None if latest_mdd is None or baseline_mdd is None else latest_mdd - baseline_mdd,
        "latest_worse_es95": bool(latest_es95 is not None and baseline_es95 is not None and latest_es95 > baseline_es95),
        "latest_worse_mdd": bool(latest_mdd is not None and baseline_mdd is not None and latest_mdd < baseline_mdd),
    }


def _budget_sensitivity(
    *,
    losses: pd.Series,
    es95: float | None,
    es99: float | None,
    buffers: tuple[float, ...],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for buffer in buffers:
        budget95 = _loss_cvar_budget(losses, 0.95, buffer)
        budget99 = _loss_cvar_budget(losses, 0.99, buffer)
        residual95 = None if es95 is None or budget95 is None else es95 - budget95
        residual99 = None if es99 is None or budget99 is None else es99 - budget99
        out[f"{buffer:.2f}"] = {
            "loss_cvar95_budget": budget95,
            "loss_cvar99_budget": budget99,
            "loss_cvar95_residual": residual95,
            "loss_cvar99_residual": residual99,
            "breach": bool((residual95 is not None and residual95 > 0) or (residual99 is not None and residual99 > 0)),
        }
    return out


def build_report(
    *,
    db_path: Path,
    live_signal_path: Path,
    rolling_tail_gate_path: Path,
    golden2_signal_path: Path,
    end: str,
    windows: tuple[int, ...],
    background_risk_buffer: float,
    sensitivity_buffers: tuple[float, ...],
    near_threshold: float,
) -> dict[str, Any]:
    signal = _load_optional(live_signal_path)
    actual_data_date = str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or end)
    weights = _weights(signal)
    rolling_tail_gate = _load_optional(rolling_tail_gate_path)
    golden2_signal = _load_optional(golden2_signal_path)
    baselines = _baseline_weights(weights, golden2_signal)
    start = (pd.Timestamp(end) - pd.Timedelta(days=max(windows) * 3 + 30)).strftime("%Y-%m-%d")
    panel = _load_close_panel(db_path, TICKERS, start, end, warmup_days=10).ffill()
    asset_returns = panel.pct_change().dropna(how="all")
    portfolio_returns = _portfolio_returns(asset_returns, weights).dropna()
    drawdown = _historical_drawdown(portfolio_returns)

    rolling: dict[str, Any] = {}
    breach_windows = 0
    positive_residual_windows = 0
    latest_worse_than_no_00631l_windows = 0
    latest_worse_than_no_letf_windows = 0
    pacing_values: list[float] = []
    sensitivity_breach_windows = {f"{buffer:.2f}": 0 for buffer in sensitivity_buffers}
    for window in windows:
        subset = portfolio_returns.tail(int(window))
        dd_subset = drawdown.loc[subset.index] if len(subset) else pd.Series(dtype=float)
        metrics = _summarize_returns(subset)
        es95 = _finite(metrics.get("expected_shortfall_loss_95"))
        es99 = _finite(metrics.get("expected_shortfall_loss_99"))
        losses = -subset
        budget95 = _loss_cvar_budget(losses, 0.95, background_risk_buffer)
        budget99 = _loss_cvar_budget(losses, 0.99, background_risk_buffer)
        residual95 = None if es95 is None or budget95 is None else es95 - budget95
        residual99 = None if es99 is None or budget99 is None else es99 - budget99
        baseline_rows: dict[str, Any] = {}
        for baseline_name, baseline_weight in baselines.items():
            baseline_returns = _portfolio_returns(asset_returns.tail(int(window)), baseline_weight).dropna()
            baseline_metrics = _summarize_returns(baseline_returns)
            baseline_rows[baseline_name] = {
                "weights": baseline_weight,
                "metrics": baseline_metrics,
                "relative_gap": _relative_gap(metrics, baseline_metrics),
            }
        latest_worse_than_no_00631l_windows += int(
            bool((baseline_rows.get("no_00631l_to_cash") or {}).get("relative_gap", {}).get("latest_worse_es95"))
        )
        latest_worse_than_no_letf_windows += int(
            bool((baseline_rows.get("no_letf_to_cash") or {}).get("relative_gap", {}).get("latest_worse_es95"))
        )
        sensitivity = _budget_sensitivity(losses=losses, es95=es95, es99=es99, buffers=sensitivity_buffers)
        for key, row in sensitivity.items():
            sensitivity_breach_windows[key] += int(bool(row.get("breach")))
        latest_return = _finite(subset.iloc[-1]) if len(subset) else None
        latest_drawdown = _finite(dd_subset.iloc[-1]) if len(dd_subset) else None
        state = _state_bucket(
            latest_return=latest_return,
            latest_drawdown=latest_drawdown,
            residual95=residual95,
            near_threshold=near_threshold,
        )
        pacing = _pacing_multiplier(state, residual95, residual99)
        pacing_values.append(pacing)
        breaches = bool((residual95 is not None and residual95 > 0) or (residual99 is not None and residual99 > 0))
        breach_windows += int(breaches)
        positive_residual_windows += int(residual95 is not None and residual95 > near_threshold)
        rolling[str(window)] = {
            "rows": int(len(subset)),
            "start": str(subset.index.min().date()) if len(subset) else None,
            "end": str(subset.index.max().date()) if len(subset) else None,
            "metrics": metrics,
            "budget": {
                "loss_cvar95_budget": budget95,
                "loss_cvar99_budget": budget99,
                "background_risk_buffer": float(background_risk_buffer),
            },
            "residual": {
                "loss_cvar95_residual": residual95,
                "loss_cvar99_residual": residual99,
                "breach": breaches,
            },
            "relative_baselines": baseline_rows,
            "budget_sensitivity": sensitivity,
            "state": {
                "bucket": state,
                "latest_return": latest_return,
                "latest_drawdown": latest_drawdown,
                "pacing_multiplier": pacing,
            },
        }

    rolling_summary = rolling_tail_gate.get("summary") or {}
    rolling_gate_blocks_00631l = bool(
        rolling_tail_gate and rolling_summary.get("allow_00631l_add") is not True
    )
    relative_baseline_blocks_00631l = latest_worse_than_no_00631l_windows > 0 or latest_worse_than_no_letf_windows > 0
    allow_00631l_add = breach_windows == 0 and not relative_baseline_blocks_00631l and not rolling_gate_blocks_00631l
    min_pacing = min(pacing_values) if pacing_values else 0.0
    recommended_pacing = 0.0 if rolling_gate_blocks_00631l else min_pacing
    status = "blocked_for_live_promotion" if not allow_00631l_add else "available_for_shadow_review"
    blocking_reasons: list[str] = []
    if breach_windows:
        blocking_reasons.append("rolling_cvar_constraint_residual_positive")
    if positive_residual_windows:
        blocking_reasons.append("material_cvar95_residual_detected")
    if rolling_gate_blocks_00631l:
        blocking_reasons.append("upstream_2606_26625_rolling_tail_gate_blocks_00631l_add")
    if latest_worse_than_no_00631l_windows:
        blocking_reasons.append("latest_worse_than_no_00631l_baseline_es95")
    if latest_worse_than_no_letf_windows:
        blocking_reasons.append("latest_worse_than_no_letf_baseline_es95")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_20179_dynamic_cvar_constraint_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.20179.pdf",
            "arxiv_id": "2608.20179v1",
            "title": "Dynamic Portfolio Optimization under CVaR Constraints",
            "adapted_concepts": [
                "hard terminal CVaR constraint",
                "CVaR constraint residual",
                "state-dependent risky exposure response",
                "background-risk buffer",
                "price-impact-aware exposure pacing",
                "baseline-relative CVaR residual",
                "CVaR budget sensitivity sweep",
            ],
            "not_imported": [
                "continuous_time_stochastic_control_optimizer",
                "nested_bisection_golden_search_live_allocator",
                "Merton_exposure_target",
                "automatic_target_weight_change",
            ],
        },
        "policy": "research_only_dynamic_cvar_constraint_shadow_no_weight_change",
        "status": status,
        "as_of": actual_data_date,
        "parameters": {
            "end": end,
            "windows": list(windows),
            "background_risk_buffer": float(background_risk_buffer),
            "sensitivity_buffers": list(sensitivity_buffers),
            "near_threshold": float(near_threshold),
            "latest_weights": weights,
            "baseline_weights": baselines,
            "live_signal_path": str(live_signal_path),
            "rolling_tail_gate_path": str(rolling_tail_gate_path),
            "golden2_signal_path": str(golden2_signal_path),
        },
        "summary": {
            "window_count": len(windows),
            "cvar_residual_breach_windows": breach_windows,
            "material_cvar95_residual_windows": positive_residual_windows,
            "sensitivity_breach_windows_by_buffer": sensitivity_breach_windows,
            "latest_worse_than_no_00631l_es95_windows": latest_worse_than_no_00631l_windows,
            "latest_worse_than_no_letf_es95_windows": latest_worse_than_no_letf_windows,
            "relative_baseline_blocks_00631l": relative_baseline_blocks_00631l,
            "upstream_rolling_tail_gate_blocks_00631l": rolling_gate_blocks_00631l,
            "recommended_00631l_add_pacing_multiplier": recommended_pacing,
            "allow_00631l_add": allow_00631l_add,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
        },
        "rolling_windows": rolling,
        "blocking_reasons": blocking_reasons,
        "decision": {
            "review_complete": True,
            "best_import": "cvar_constraint_residual_and_state_dependent_pacing_shadow",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": allow_00631l_add,
            "allow_00632r_open": None,
            "recommended_00631l_add_pacing_multiplier": recommended_pacing,
            "keep_latest_strategy_unchanged": True,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.20179 Dynamic CVaR Constraint Shadow",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        f"- 00631L add: `{'allowed' if report['decision']['allow_00631l_add'] else 'blocked'}`",
        f"- Recommended 00631L add pacing: `{_fmt(report['decision']['recommended_00631l_add_pacing_multiplier'])}`",
        f"- CVaR residual breach windows: `{report['summary']['cvar_residual_breach_windows']}`",
        f"- Latest worse than no-00631L ES95 windows: `{report['summary']['latest_worse_than_no_00631l_es95_windows']}`",
        f"- Latest worse than no-LETF ES95 windows: `{report['summary']['latest_worse_than_no_letf_es95_windows']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "| window | ES95 | budget95 | residual95 | ES99 | budget99 | residual99 | state | pacing |",
        "|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for window, row in report["rolling_windows"].items():
        metrics = row["metrics"]
        budget = row["budget"]
        residual = row["residual"]
        state = row["state"]
        lines.append(
            "| {window} | {es95} | {budget95} | {res95} | {es99} | {budget99} | {res99} | `{bucket}` | {pacing} |".format(
                window=window,
                es95=_fmt(metrics.get("expected_shortfall_loss_95")),
                budget95=_fmt(budget.get("loss_cvar95_budget")),
                res95=_fmt(residual.get("loss_cvar95_residual")),
                es99=_fmt(metrics.get("expected_shortfall_loss_99")),
                budget99=_fmt(budget.get("loss_cvar99_budget")),
                res99=_fmt(residual.get("loss_cvar99_residual")),
                bucket=state.get("bucket"),
                pacing=_fmt(state.get("pacing_multiplier")),
            )
        )
    lines.extend(
        [
            "",
            "## Baseline Relative ES95",
            "",
            "| window | no-00631L delta | no-LETF delta | golden1_0531 delta | golden2_0830 delta |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for window, row in report["rolling_windows"].items():
        baselines = row.get("relative_baselines") or {}

        def delta(name: str) -> str:
            return _fmt((baselines.get(name) or {}).get("relative_gap", {}).get("es95_delta_vs_baseline"))

        lines.append(
            "| {window} | {no631} | {noletf} | {g1} | {g2} |".format(
                window=window,
                no631=delta("no_00631l_to_cash"),
                noletf=delta("no_letf_to_cash"),
                g1=delta("golden1_0531_static"),
                g2=delta("golden2_0830"),
            )
        )
    lines.extend(
        [
            "",
            "## Budget Sensitivity",
            "",
            "| buffer | breach windows |",
            "|---:|---:|",
        ]
    )
    for buffer, count in (report["summary"].get("sensitivity_breach_windows_by_buffer") or {}).items():
        lines.append(f"| {buffer} | {count} |")
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
    return history_dir / f"2608_20179_dynamic_cvar_constraint_shadow_{as_of.replace('-', '')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--rolling-tail-gate", default=str(DEFAULT_ROLLING_TAIL_GATE))
    parser.add_argument("--golden2-signal", default=str(DEFAULT_GOLDEN2_SIGNAL))
    parser.add_argument("--end", default="2026-09-01")
    parser.add_argument("--windows", default="63,126,252")
    parser.add_argument("--background-risk-buffer", type=float, default=0.10)
    parser.add_argument("--sensitivity-buffers", default="0,0.05,0.10,0.15,0.20")
    parser.add_argument("--near-threshold", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    windows = tuple(int(x.strip()) for x in str(args.windows).split(",") if x.strip())
    sensitivity_buffers = tuple(float(x.strip()) for x in str(args.sensitivity_buffers).split(",") if x.strip())
    report = build_report(
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        rolling_tail_gate_path=_resolve(args.rolling_tail_gate),
        golden2_signal_path=_resolve(args.golden2_signal),
        end=args.end,
        windows=windows,
        background_risk_buffer=args.background_risk_buffer,
        sensitivity_buffers=sensitivity_buffers,
        near_threshold=args.near_threshold,
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
    print(f"2608.20179 dynamic CVaR constraint shadow: {output}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
