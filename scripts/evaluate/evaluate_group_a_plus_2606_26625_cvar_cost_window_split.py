#!/usr/bin/env python3
"""Window-split CVaR/cost audit inspired by arXiv 2606.26625.

Research-only: compare current GroupA+ target weights with conservative
variants under monthly rebalancing costs. This does not optimize weights and
never changes the live strategy.
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
from scripts.evaluate.evaluate_cvar_tail_risk_diagnostic_shadow import _load_close_panel, _summarize_returns

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_cvar_cost_window_split.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_26625_cvar_cost_window_split.md"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
WINDOWS = {
    "covid_2020": ("2020-02-03", "2020-06-30"),
    "rate_hike_2022": ("2022-01-03", "2022-12-30"),
    "post_2023": ("2023-01-03", None),
    "recent_2024_2026": ("2024-01-02", None),
    "active_2025_2026": ("2025-01-02", None),
}


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _load_latest_weights(path: Path) -> tuple[str | None, dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    weights = {str(k): float(v) for k, v in dict(data.get("target_weights") or {}).items()}
    for ticker in TICKERS:
        weights.setdefault(ticker, 0.0)
    weights["cash"] = float(weights.get("cash", max(0.0, 1.0 - sum(weights[t] for t in TICKERS))))
    return data.get("actual_data_date") or data.get("requested_as_of_date"), weights


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    out = {ticker: max(0.0, float(weights.get(ticker, 0.0))) for ticker in TICKERS}
    out["cash"] = max(0.0, float(weights.get("cash", 0.0)))
    total = sum(out.values())
    if total <= 0:
        raise ValueError("weights must have positive total")
    return {k: v / total for k, v in out.items()}


def _variants(latest: dict[str, float]) -> dict[str, dict[str, float]]:
    no_00631l = dict(latest)
    no_00631l["cash"] = no_00631l.get("cash", 0.0) + no_00631l.get("00631L.TW", 0.0)
    no_00631l["00631L.TW"] = 0.0

    no_00632r = dict(latest)
    no_00632r["cash"] = no_00632r.get("cash", 0.0) + no_00632r.get("00632R.TW", 0.0)
    no_00632r["00632R.TW"] = 0.0

    no_letf = dict(no_00631l)
    no_letf["cash"] = no_letf.get("cash", 0.0) + no_letf.get("00632R.TW", 0.0)
    no_letf["00632R.TW"] = 0.0

    return {
        "latest_strategy": _normalize(latest),
        "no_00631l_to_cash": _normalize(no_00631l),
        "no_00632r_to_cash": _normalize(no_00632r),
        "no_letf_to_cash": _normalize(no_letf),
        "golden1_base_50_20_30": _normalize({"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}),
    }


def _simulate_monthly_rebalanced(
    asset_returns: pd.DataFrame,
    target: dict[str, float],
    *,
    rebalance_every: int,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    target = _normalize(target)
    weights = dict(target)
    cost_rate = float(cost_bps) / 10000.0
    returns: list[float] = []
    turnovers: list[float] = []
    dates: list[pd.Timestamp] = []
    for idx, (date, row) in enumerate(asset_returns.iterrows()):
        turnover = 0.0
        if idx > 0 and idx % int(rebalance_every) == 0:
            turnover = 0.5 * sum(abs(weights.get(key, 0.0) - target.get(key, 0.0)) for key in set(weights) | set(target))
            weights = dict(target)
        gross = sum(weights.get(ticker, 0.0) * float(row.get(ticker, 0.0) or 0.0) for ticker in TICKERS)
        net = gross - turnover * cost_rate
        denom = 1.0 + gross
        if abs(denom) > 1e-12:
            weights = {
                ticker: weights.get(ticker, 0.0) * (1.0 + float(row.get(ticker, 0.0) or 0.0)) / denom
                for ticker in TICKERS
            } | {"cash": weights.get("cash", 0.0) / denom}
        returns.append(float(net))
        turnovers.append(float(turnover))
        dates.append(pd.Timestamp(date))
    return pd.Series(returns, index=pd.Index(dates, name="dt")), pd.Series(turnovers, index=pd.Index(dates, name="dt"))


def build_report(
    *,
    db_path: Path,
    live_signal_path: Path,
    start: str,
    end: str,
    rebalance_every: int,
    cost_bps: float,
) -> dict[str, Any]:
    signal_date, latest_weights = _load_latest_weights(live_signal_path)
    panel = _load_close_panel(db_path, TICKERS, start, end, warmup_days=10).ffill()
    returns = panel.pct_change().dropna(how="all")
    variants = _variants(latest_weights)
    window_rows: list[dict[str, Any]] = []
    latest_loses_to_no_00631l = 0
    latest_loses_to_no_letf = 0
    valid_windows = 0
    for name, (window_start, raw_end) in WINDOWS.items():
        window_end = raw_end or end
        subset = returns.loc[(returns.index >= pd.Timestamp(window_start)) & (returns.index <= pd.Timestamp(window_end))]
        if subset.empty:
            continue
        valid_windows += 1
        metrics: dict[str, Any] = {}
        for variant_name, weights in variants.items():
            simulated, turnover = _simulate_monthly_rebalanced(
                subset,
                weights,
                rebalance_every=rebalance_every,
                cost_bps=cost_bps,
            )
            summary = _summarize_returns(simulated)
            summary["mean_rebalance_turnover"] = _finite(turnover[turnover > 0].mean())
            summary["max_rebalance_turnover"] = _finite(turnover.max())
            metrics[variant_name] = summary
        latest = metrics["latest_strategy"]
        no_00631l = metrics["no_00631l_to_cash"]
        no_letf = metrics["no_letf_to_cash"]
        latest_es = _finite(latest.get("expected_shortfall_loss_95"))
        no_00631l_es = _finite(no_00631l.get("expected_shortfall_loss_95"))
        no_letf_es = _finite(no_letf.get("expected_shortfall_loss_95"))
        latest_mdd = _finite(latest.get("max_drawdown"))
        no_00631l_mdd = _finite(no_00631l.get("max_drawdown"))
        no_letf_mdd = _finite(no_letf.get("max_drawdown"))
        loses_00631l = bool(
            latest_es is not None
            and no_00631l_es is not None
            and latest_mdd is not None
            and no_00631l_mdd is not None
            and (latest_es > no_00631l_es or latest_mdd < no_00631l_mdd)
        )
        loses_letf = bool(
            latest_es is not None
            and no_letf_es is not None
            and latest_mdd is not None
            and no_letf_mdd is not None
            and (latest_es > no_letf_es or latest_mdd < no_letf_mdd)
        )
        latest_loses_to_no_00631l += int(loses_00631l)
        latest_loses_to_no_letf += int(loses_letf)
        window_rows.append(
            {
                "window": name,
                "start": str(subset.index.min().date()),
                "end": str(subset.index.max().date()),
                "rows": int(len(subset)),
                "latest_loses_to_no_00631l_tail_or_mdd": loses_00631l,
                "latest_loses_to_no_letf_tail_or_mdd": loses_letf,
                "metrics": metrics,
            }
        )
    blocked = latest_loses_to_no_00631l > 0 or latest_loses_to_no_letf > 0
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_26625_cvar_cost_window_split",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.26625.pdf",
            "title": "Portfolio Optimization for Commodity ETFs under Heavy-Tailed Returns",
            "adapted_concepts": [
                "CVaR/expected-shortfall window split",
                "tail and max-drawdown comparison against conservative variants",
                "monthly rebalance turnover-cost accounting",
            ],
        },
        "policy": "research_only_cvar_cost_window_split_no_optimizer_no_weight_change",
        "status": "blocked_for_live_promotion" if blocked else "available_for_shadow_review",
        "as_of": signal_date,
        "parameters": {
            "start": start,
            "end": end,
            "rebalance_every": int(rebalance_every),
            "cost_bps": float(cost_bps),
            "live_signal_path": str(live_signal_path),
            "latest_weights": latest_weights,
            "variants": variants,
        },
        "summary": {
            "valid_windows": valid_windows,
            "latest_loses_to_no_00631l_windows": latest_loses_to_no_00631l,
            "latest_loses_to_no_letf_windows": latest_loses_to_no_letf,
            "tail_cost_window_split_passed": not blocked,
        },
        "windows": window_rows,
        "decision": {
            "review_complete": True,
            "best_import": "cvar_cost_window_split_shadow_only",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "dynamic_optimizer_ready": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_00679b_add": False,
            "keep_latest_strategy_unchanged": True,
            "reason": (
                "This audit is comparative evidence only; it does not implement a dynamic optimizer. "
                "Any window where latest has worse ES95 or MDD than conservative variants blocks live promotion."
            ),
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2606.26625 CVaR/Cost Window Split",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Policy: `{report['policy']}`",
        f"- Valid windows: `{report['summary']['valid_windows']}`",
        f"- Latest loses to no-00631L windows: `{report['summary']['latest_loses_to_no_00631l_windows']}`",
        f"- Latest loses to no-LETF windows: `{report['summary']['latest_loses_to_no_letf_windows']}`",
        "",
        "| window | latest ES95 | no-00631L ES95 | no-LETF ES95 | latest MDD | no-00631L MDD | no-LETF MDD | latest STARR95 | latest loses? |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["windows"]:
        metrics = row["metrics"]
        latest = metrics["latest_strategy"]
        no_00631l = metrics["no_00631l_to_cash"]
        no_letf = metrics["no_letf_to_cash"]
        loses = row["latest_loses_to_no_00631l_tail_or_mdd"] or row["latest_loses_to_no_letf_tail_or_mdd"]
        lines.append(
            "| {window} | {le} | {ne} | {nle} | {lm} | {nm} | {nlm} | {ls} | `{loses}` |".format(
                window=row["window"],
                le=_fmt(latest.get("expected_shortfall_loss_95")),
                ne=_fmt(no_00631l.get("expected_shortfall_loss_95")),
                nle=_fmt(no_letf.get("expected_shortfall_loss_95")),
                lm=_fmt(latest.get("max_drawdown")),
                nm=_fmt(no_00631l.get("max_drawdown")),
                nlm=_fmt(no_letf.get("max_drawdown")),
                ls=_fmt(latest.get("starr_95")),
                loses=loses,
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Research/shadow only.",
            "- No optimizer promotion.",
            "- No target-weight change.",
            "- No automatic rebalance.",
            "- No `00631L.TW` add.",
            "- No `00632R.TW` open.",
            "- No `00679B.TWO` add.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--rebalance-every", type=int, default=21)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(
        db_path=Path(args.db),
        live_signal_path=Path(args.live_signal),
        start=args.start,
        end=args.end,
        rebalance_every=args.rebalance_every,
        cost_bps=args.cost_bps,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"2606.26625 CVaR/cost window split: {output}")
    print(f"Markdown: {Path(args.md_output)}")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
