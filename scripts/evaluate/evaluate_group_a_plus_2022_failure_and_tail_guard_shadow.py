#!/usr/bin/env python3
"""GroupA+ 2022 failure attribution and tail no-new-00631L proxy shadow.

Research-only.  Codex 2026-08-14: this does not alter latest strategy,
golden1_0531, live signal, execution plan, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import (  # noqa: E402
    _load_total_return_prices,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/group_a_plus_2022_failure_tail_guard_shadow_latest.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results/group_a_plus_2022_failure_tail_guard_shadow_curve_latest.csv"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2022_failure_tail_guard_shadow.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _zero_00631l_to_0050(weights: dict[str, float]) -> dict[str, float]:
    shifted = dict(weights)
    amount = float(shifted.get("00631L.TW", 0.0) or 0.0)
    shifted["00631L.TW"] = 0.0
    shifted["0050.TW"] = float(shifted.get("0050.TW", 0.0) or 0.0) + amount
    return _normalize(shifted)


def _weights_by_regime(latest_report: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = latest_report.get("base_weights") or latest_report.get("weights") or {}
    out = {str(name): _normalize(dict(weights or {})) for name, weights in raw.items()}
    if not out:
        raise ValueError("latest report does not include base_weights")
    return out


def _tail_guard_regime_name(regime: str) -> str:
    return f"{regime}__tail_no_00631l_add_proxy"


def _apply_tail_guard_proxy(
    frame: pd.DataFrame,
    *,
    base_regime_col: str = "execution_regime",
    tail_risk_score_min: int = 1,
    total_risk_score_min: int | None = None,
    drawdown_max: float | None = None,
    realized_vol_ratio_min: float | None = None,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    regimes = frame[base_regime_col].astype(str).copy()
    guarded = regimes.copy()
    events: list[dict[str, Any]] = []
    previous_guarded = False
    for dt, row in frame.iterrows():
        regime = str(regimes.loc[dt])
        if regime != "golden1":
            previous_guarded = False
            continue
        reasons = []
        if int(row.get("tail_risk_score", 0) or 0) >= int(tail_risk_score_min):
            reasons.append("tail_risk_score")
        if total_risk_score_min is not None and int(row.get("total_risk_score", 0) or 0) >= int(total_risk_score_min):
            reasons.append("total_risk_score")
        if drawdown_max is not None and float(row.get("drawdown", 0.0) or 0.0) <= float(drawdown_max):
            reasons.append("drawdown")
        if realized_vol_ratio_min is not None and float(row.get("realized_vol_ratio_20_60", 0.0) or 0.0) >= float(realized_vol_ratio_min):
            reasons.append("realized_vol_ratio")
        if not reasons:
            previous_guarded = False
            continue
        guarded.loc[dt] = _tail_guard_regime_name(regime)
        if not previous_guarded:
            events.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "regime": regime,
                    "guarded_regime": str(guarded.loc[dt]),
                    "reasons": reasons,
                    "tail_risk_score": int(row.get("tail_risk_score", 0) or 0),
                    "total_risk_score": int(row.get("total_risk_score", 0) or 0),
                    "drawdown": float(row.get("drawdown", 0.0) or 0.0),
                    "realized_vol_ratio_20_60": float(row.get("realized_vol_ratio_20_60", 0.0) or 0.0),
                }
            )
        previous_guarded = True
    return guarded, events


def _top_drawdown_episodes(values: pd.Series, *, top_n: int = 8) -> list[dict[str, Any]]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    running_max = clean.cummax()
    drawdown = clean / running_max - 1.0
    episodes: list[dict[str, Any]] = []
    in_episode = False
    start: pd.Timestamp | None = None
    trough: pd.Timestamp | None = None
    trough_dd = 0.0
    for dt, dd in drawdown.items():
        if not in_episode and dd < 0.0:
            in_episode = True
            start = pd.Timestamp(dt)
            trough = pd.Timestamp(dt)
            trough_dd = float(dd)
        elif in_episode:
            if float(dd) < trough_dd:
                trough = pd.Timestamp(dt)
                trough_dd = float(dd)
            if dd >= 0.0:
                episodes.append(
                    {
                        "start": str(start.date()) if start is not None else None,
                        "trough": str(trough.date()) if trough is not None else None,
                        "end": str(pd.Timestamp(dt).date()),
                        "max_drawdown": trough_dd,
                    }
                )
                in_episode = False
                start = None
                trough = None
                trough_dd = 0.0
    if in_episode:
        episodes.append(
            {
                "start": str(start.date()) if start is not None else None,
                "trough": str(trough.date()) if trough is not None else None,
                "end": str(clean.index[-1].date()),
                "max_drawdown": trough_dd,
            }
        )
    return sorted(episodes, key=lambda item: item["max_drawdown"])[:top_n]


def _top_loss_days(frame: pd.DataFrame, *, top_n: int = 12) -> list[dict[str, Any]]:
    values = pd.to_numeric(frame["portfolio_value"], errors="coerce")
    returns = values.pct_change()
    out = []
    for dt, ret in returns.nsmallest(top_n).items():
        row = frame.loc[dt]
        out.append(
            {
                "date": str(pd.Timestamp(dt).date()),
                "portfolio_return": float(ret),
                "portfolio_value": float(row["portfolio_value"]),
                "execution_regime": str(row.get("execution_regime")),
                "tail_risk_score": int(row.get("tail_risk_score", 0) or 0),
                "total_risk_score": int(row.get("total_risk_score", 0) or 0),
                "drawdown": float(row.get("drawdown", 0.0) or 0.0),
                "ma_gap": float(row.get("ma_gap", 0.0) or 0.0),
                "return_0050_1d": float(row.get("return_0050_1d", 0.0) or 0.0),
            }
        )
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    initial_value: float,
    tail_risk_score_min: int,
    total_risk_score_min: int | None,
    drawdown_max: float | None,
    realized_vol_ratio_min: float | None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    latest_report, frame = run_latest(start, end, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    weights = _weights_by_regime(latest_report)
    guarded_weights = dict(weights)
    guarded_weights[_tail_guard_regime_name("golden1")] = _zero_00631l_to_0050(weights["golden1"])
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    baseline_curve, baseline_exec = _simulate_costed_curve(
        total_return_prices,
        frame["execution_regime"].astype(str),
        weights,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    guarded_regime, guard_events = _apply_tail_guard_proxy(
        frame,
        tail_risk_score_min=tail_risk_score_min,
        total_risk_score_min=total_risk_score_min,
        drawdown_max=drawdown_max,
        realized_vol_ratio_min=realized_vol_ratio_min,
    )
    guarded_curve, guarded_exec = _simulate_costed_curve(
        total_return_prices,
        guarded_regime,
        guarded_weights,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    curves = pd.DataFrame(
        {
            "baseline_latest": baseline_curve,
            "tail_no_00631l_add_proxy": guarded_curve,
            "baseline_runner_frame_value": frame["portfolio_value"],
            "execution_regime": frame["execution_regime"].astype(str),
            "proxy_execution_regime": guarded_regime.astype(str),
            "tail_risk_score": frame["tail_risk_score"],
            "total_risk_score": frame["total_risk_score"],
            "drawdown": frame["drawdown"],
            "realized_vol_ratio_20_60": frame["realized_vol_ratio_20_60"],
        }
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    guarded_metrics = _metrics(guarded_curve, initial_value)
    metric_delta = {
        key: float(guarded_metrics[key] - baseline_metrics[key])
        for key in ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    }
    guard_days = int((guarded_regime != frame["execution_regime"].astype(str)).sum())
    promotion_ready = bool(
        metric_delta["final_value"] > 0.0
        and metric_delta["sortino_ratio"] > 0.0
        and metric_delta["max_drawdown"] >= 0.0
    )
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_2022_failure_tail_guard_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_weight_change",
        "codex_note": "Codex 2026-08-14: proxy hard no-new-00631L/tail trim shadow only; production strategy is unchanged.",
        "inputs": {
            "db": str(db_path),
            "window": {"start": start, "end": end, "rows": int(len(frame))},
            "initial_value": float(initial_value),
            "tail_risk_score_min": int(tail_risk_score_min),
            "total_risk_score_min": total_risk_score_min,
            "drawdown_max": drawdown_max,
            "realized_vol_ratio_min": realized_vol_ratio_min,
            "active_strategy_id": latest_report.get("active_strategy_id"),
        },
        "failure_attribution": {
            "top_loss_days": _top_loss_days(frame),
            "top_drawdown_episodes": _top_drawdown_episodes(frame["portfolio_value"]),
            "regime_day_counts": {str(k): int(v) for k, v in frame["execution_regime"].value_counts().items()},
            "tail_risk_day_count": int((frame["tail_risk_score"] >= tail_risk_score_min).sum()),
            "golden1_tail_guard_candidate_days": guard_days,
        },
        "weights": {
            "baseline_golden1": weights.get("golden1"),
            "proxy_guarded_golden1": guarded_weights[_tail_guard_regime_name("golden1")],
        },
        "execution": {
            "baseline_latest": baseline_exec,
            "tail_no_00631l_add_proxy": guarded_exec,
            "guard_event_count": int(len(guard_events)),
            "guard_days": guard_days,
            "guard_events_sample": guard_events[:50],
            "dividend_coverage": dividend_coverage,
        },
        "metrics": {
            "baseline_latest": baseline_metrics,
            "tail_no_00631l_add_proxy": guarded_metrics,
            "delta_proxy_minus_baseline": metric_delta,
        },
        "decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "promotion_ready": promotion_ready,
            "recommended_use": "needs_multi_window_validation" if promotion_ready else "keep_research_only",
        },
    }
    return report, curves


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    base = report["metrics"]["baseline_latest"]
    guard = report["metrics"]["tail_no_00631l_add_proxy"]
    delta = report["metrics"]["delta_proxy_minus_baseline"]
    lines = [
        "# GroupA+ 2022 Failure + Tail Guard Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Window: `{report['inputs']['window']['start']}` ~ `{report['inputs']['window']['end']}`",
        f"- Policy: `{report['policy']}`",
        f"- Promotion ready: `{report['decision']['promotion_ready']}`",
        f"- Guard days: `{report['execution']['guard_days']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Baseline latest | Tail no-00631L proxy | Delta |",
        "|---|---:|---:|---:|",
        f"| final_value | {base['final_value']:.2f} | {guard['final_value']:.2f} | {delta['final_value']:.2f} |",
        f"| annual_return | {base['annual_return']:.6f} | {guard['annual_return']:.6f} | {delta['annual_return']:.6f} |",
        f"| sharpe_ratio | {base['sharpe_ratio']:.6f} | {guard['sharpe_ratio']:.6f} | {delta['sharpe_ratio']:.6f} |",
        f"| sortino_ratio | {base['sortino_ratio']:.6f} | {guard['sortino_ratio']:.6f} | {delta['sortino_ratio']:.6f} |",
        f"| max_drawdown | {base['max_drawdown']:.6f} | {guard['max_drawdown']:.6f} | {delta['max_drawdown']:.6f} |",
        "",
        "## Worst Drawdowns",
        "",
        "| Start | Trough | End | Max drawdown |",
        "|---|---:|---:|---:|",
    ]
    for item in report["failure_attribution"]["top_drawdown_episodes"][:5]:
        lines.append(f"| {item['start']} | {item['trough']} | {item['end']} | {item['max_drawdown']:.6f} |")
    lines.extend(
        [
            "",
            "Codex 2026-08-14: research-only proxy; do not promote without independent multi-window validation.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], curves: pd.DataFrame, *, output_json: Path, output_csv: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    curves.to_csv(output_csv, encoding="utf-8-sig")
    _write_markdown(report, output_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2022-01-03")
    parser.add_argument("--end", default="2022-12-30")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--tail-risk-score-min", type=int, default=1)
    parser.add_argument("--total-risk-score-min", type=int, default=None)
    parser.add_argument("--drawdown-max", type=float, default=None)
    parser.add_argument("--realized-vol-ratio-min", type=float, default=None)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, curves = build_report(
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        initial_value=args.initial_value,
        tail_risk_score_min=args.tail_risk_score_min,
        total_risk_score_min=args.total_risk_score_min,
        drawdown_max=args.drawdown_max,
        realized_vol_ratio_min=args.realized_vol_ratio_min,
    )
    write_outputs(
        report,
        curves,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        output_md=_resolve(args.output_md),
    )
    print(
        json.dumps(
            {
                "promotion_ready": report["decision"]["promotion_ready"],
                "guard_days": report["execution"]["guard_days"],
                "final_value_delta": report["metrics"]["delta_proxy_minus_baseline"]["final_value"],
                "sortino_delta": report["metrics"]["delta_proxy_minus_baseline"]["sortino_ratio"],
                "max_drawdown_delta": report["metrics"]["delta_proxy_minus_baseline"]["max_drawdown"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
