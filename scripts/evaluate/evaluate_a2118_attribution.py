#!/usr/bin/env python3
"""Attribution diagnostics for GroupA+ A21.18/A21.21 frames."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_OUTPUT = Path("results/a2118_attribution_latest.json")


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["data"] if payload.get("success") and "data" in payload else payload


def load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "dt" not in frame.columns:
        raise ValueError(f"{path} is missing dt column")
    frame["dt"] = pd.to_datetime(frame["dt"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["dt"]).set_index("dt").sort_index()
    if "portfolio_value" not in frame.columns or "execution_regime" not in frame.columns:
        raise ValueError(f"{path} must include portfolio_value and execution_regime")
    frame["portfolio_value"] = pd.to_numeric(frame["portfolio_value"], errors="coerce")
    frame["strategy_return"] = frame["portfolio_value"].pct_change().fillna(0.0)
    return frame


def _max_drawdown_from_returns(returns: pd.Series) -> float:
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    return float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0


def _summary(returns: pd.Series) -> dict[str, Any]:
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    total = float((1.0 + returns).prod() - 1.0)
    vol = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 and returns.std(ddof=1) > 0 else 0.0
    return {
        "rows": int(len(returns)),
        "total_return": total,
        "mean_daily_return": float(returns.mean()) if len(returns) else 0.0,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": _max_drawdown_from_returns(returns),
        "worst_day": str(returns.idxmin().date()) if len(returns) else None,
        "worst_day_return": float(returns.min()) if len(returns) else 0.0,
        "best_day": str(returns.idxmax().date()) if len(returns) else None,
        "best_day_return": float(returns.max()) if len(returns) else 0.0,
    }


def regime_attribution(frame: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for regime, part in frame.groupby(frame["execution_regime"].astype(str)):
        out[str(regime)] = _summary(part["strategy_return"])
    return out


def transition_events(frame: pd.DataFrame, *, lookahead_days: int = 20) -> list[dict[str, Any]]:
    regimes = frame["execution_regime"].astype(str)
    changed = regimes != regimes.shift(1)
    events: list[dict[str, Any]] = []
    for dt in frame.index[changed.fillna(True)]:
        loc = frame.index.get_loc(dt)
        if isinstance(loc, slice):
            continue
        start = int(loc)
        end = min(start + lookahead_days, len(frame) - 1)
        forward = frame["portfolio_value"].iloc[start : end + 1]
        forward_ret = float(forward.iloc[-1] / forward.iloc[0] - 1.0) if len(forward) > 1 else 0.0
        forward_mdd = float((forward / forward.cummax() - 1.0).min()) if len(forward) else 0.0
        prev_regime = None if start == 0 else str(regimes.iloc[start - 1])
        events.append(
            {
                "date": str(dt.date()),
                "from": prev_regime,
                "to": str(regimes.iloc[start]),
                "portfolio_value": float(frame["portfolio_value"].iloc[start]),
                f"forward_return_{lookahead_days}d": forward_ret,
                f"forward_mdd_{lookahead_days}d": forward_mdd,
            }
        )
    return events


def worst_days(frame: pd.DataFrame, *, n: int = 10) -> list[dict[str, Any]]:
    cols = [
        "execution_regime",
        "base_regime",
        "0050_close",
        "ma_gap",
        "drawdown",
        "exit_momentum",
        "total_risk_score",
        "chip_score",
        "tail_risk_score",
        "strategy_return",
        "portfolio_value",
    ]
    available = [col for col in cols if col in frame.columns]
    rows = frame.nsmallest(n, "strategy_return")[available].reset_index()
    rows["dt"] = rows["dt"].dt.strftime("%Y-%m-%d")
    return rows.where(pd.notna(rows), None).to_dict(orient="records")


def compare_frames(baseline: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
    joined = baseline[["portfolio_value", "strategy_return", "execution_regime"]].join(
        candidate[["portfolio_value", "strategy_return", "execution_regime"]],
        how="inner",
        lsuffix="_baseline",
        rsuffix="_candidate",
    )
    joined["return_delta"] = joined["strategy_return_candidate"] - joined["strategy_return_baseline"]
    joined["value_delta"] = joined["portfolio_value_candidate"] - joined["portfolio_value_baseline"]
    regime_diff = joined[joined["execution_regime_baseline"] != joined["execution_regime_candidate"]]
    top_help = joined.nlargest(10, "return_delta")
    top_hurt = joined.nsmallest(10, "return_delta")
    return {
        "rows": int(len(joined)),
        "final_value_delta": float(joined["value_delta"].iloc[-1]) if len(joined) else 0.0,
        "return_delta_summary": _summary(joined["return_delta"]),
        "regime_different_days": int(len(regime_diff)),
        "top_help_days": _records(top_help),
        "top_hurt_days": _records(top_hurt),
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = frame.reset_index()
    if "dt" not in out.columns and "index" in out.columns:
        out = out.rename(columns={"index": "dt"})
    out["dt"] = out["dt"].dt.strftime("%Y-%m-%d")
    return out.where(pd.notna(out), None).to_dict(orient="records")


def build_report(
    *,
    baseline_report: Path,
    baseline_frame: Path,
    candidate_report: Path | None,
    candidate_frame: Path | None,
) -> dict[str, Any]:
    baseline_payload = _load_payload(baseline_report)
    baseline = load_frame(baseline_frame)
    report: dict[str, Any] = {
        "schema_version": 1,
        "report_type": "a2118_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "report": str(baseline_report),
            "frame": str(baseline_frame),
            "strategy": baseline_payload.get("strategy"),
            "window": baseline_payload.get("window"),
            "metrics": baseline_payload.get("metrics"),
            "execution": baseline_payload.get("execution"),
            "overall_from_frame": _summary(baseline["strategy_return"]),
            "by_execution_regime": regime_attribution(baseline),
            "transition_events": transition_events(baseline),
            "worst_days": worst_days(baseline),
        },
        "active_allocation_impact": "none",
    }
    if candidate_report and candidate_frame:
        candidate_payload = _load_payload(candidate_report)
        candidate = load_frame(candidate_frame)
        report["candidate"] = {
            "report": str(candidate_report),
            "frame": str(candidate_frame),
            "strategy": candidate_payload.get("strategy"),
            "window": candidate_payload.get("window"),
            "metrics": candidate_payload.get("metrics"),
            "execution": candidate_payload.get("execution"),
            "overall_from_frame": _summary(candidate["strategy_return"]),
            "by_execution_regime": regime_attribution(candidate),
        }
        report["baseline_vs_candidate"] = compare_frames(baseline, candidate)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", required=True)
    parser.add_argument("--baseline-frame", required=True)
    parser.add_argument("--candidate-report", default=None)
    parser.add_argument("--candidate-frame", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_report(
        baseline_report=Path(args.baseline_report),
        baseline_frame=Path(args.baseline_frame),
        candidate_report=Path(args.candidate_report) if args.candidate_report else None,
        candidate_frame=Path(args.candidate_frame) if args.candidate_frame else None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"A21.18 attribution: {output.resolve()}")


if __name__ == "__main__":
    main()
