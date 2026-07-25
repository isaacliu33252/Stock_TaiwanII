#!/usr/bin/env python3
"""Windowed stability review for weak GIFT-style state/reward proxies.

This focuses on whether the feature-stability findings persist in rolling and
stress windows. It is research-only and never produces actions, target weights,
model training, or live rebalance decisions.
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

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_feature_stability import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_FEATURE_STABILITY,
    _finite_float,
    _load_feature_frames,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_MULTI_TICKER_SMOKE,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    ACCEPTED_PROPOSAL_ID,
    DEFAULT_DB,
    DEFAULT_VALIDATION,
    _accepted_proposals,
    _load_json,
    _resolve,
)
from scripts.evaluate.evaluate_group_a_plus_sin_lite_crash_window_backtest import (  # noqa: E402
    DEFAULT_WINDOWS,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_windowed_stability_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_windowed_stability/history"
DEFAULT_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
DEFAULT_ROLLING_WINDOWS = [63, 126, 252]


def _corr_beta(pair: pd.DataFrame, left: str, right: str, *, min_overlap: int) -> dict[str, Any]:
    clean = pair[[left, right]].dropna()
    corr = np.nan
    beta = np.nan
    if len(clean) >= min_overlap:
        left_std = clean[left].std(ddof=0)
        right_std = clean[right].std(ddof=0)
        if left_std > 0 and right_std > 0:
            corr = clean[left].corr(clean[right])
        variance = clean[left].var(ddof=0)
        if pd.notna(variance) and variance > 0:
            beta = clean[right].cov(clean[left], ddof=0) / variance
    return {
        "overlap_rows": int(len(clean)),
        "correlation": _finite_float(corr),
        "beta": _finite_float(beta),
    }


def _rolling_relationships(
    frames: dict[str, pd.DataFrame],
    *,
    benchmark: str,
    targets: list[str],
    windows: list[int],
) -> list[dict[str, Any]]:
    if benchmark not in frames:
        return []
    benchmark_returns = frames[benchmark].set_index("date")["return"].rename(benchmark)
    rows: list[dict[str, Any]] = []
    for target in targets:
        if target == benchmark or target not in frames:
            continue
        pair = pd.concat([benchmark_returns, frames[target].set_index("date")["return"].rename(target)], axis=1).dropna()
        for window in windows:
            if len(pair) < window:
                rows.append(
                    {
                        "target": target,
                        "window_days": window,
                        "available": False,
                        "latest_date": None,
                        "latest_correlation": None,
                        "latest_beta": None,
                        "max_correlation": None,
                        "min_correlation": None,
                        "max_abs_correlation": None,
                    }
                )
                continue
            rolling_corr = pair[benchmark].rolling(window).corr(pair[target]).replace([np.inf, -np.inf], np.nan)
            rolling_cov = pair[target].rolling(window).cov(pair[benchmark])
            rolling_var = pair[benchmark].rolling(window).var()
            rolling_beta = (rolling_cov / rolling_var).replace([np.inf, -np.inf], np.nan)
            corr_values = rolling_corr.dropna()
            rows.append(
                {
                    "target": target,
                    "window_days": window,
                    "available": not corr_values.empty,
                    "latest_date": pair.index.max().date().isoformat(),
                    "latest_correlation": _finite_float(rolling_corr.dropna().iloc[-1]) if not rolling_corr.dropna().empty else None,
                    "latest_beta": _finite_float(rolling_beta.dropna().iloc[-1]) if not rolling_beta.dropna().empty else None,
                    "max_correlation": _finite_float(corr_values.max()) if not corr_values.empty else None,
                    "min_correlation": _finite_float(corr_values.min()) if not corr_values.empty else None,
                    "max_abs_correlation": _finite_float(corr_values.abs().max()) if not corr_values.empty else None,
                }
            )
    return rows


def _zscore_series(series: pd.Series, window: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.rolling(window, min_periods=max(20, window // 4)).mean()
    std = numeric.rolling(window, min_periods=max(20, window // 4)).std(ddof=0)
    return ((numeric - mean) / std).replace([np.inf, -np.inf], np.nan)


def _benchmark_zscore_windows(
    benchmark_frame: pd.DataFrame,
    windows: list[dict[str, str]],
    *,
    zscore_window: int,
    zscore_threshold: float,
) -> list[dict[str, Any]]:
    frame = benchmark_frame.copy()
    frame["drawdown_penalty_zscore"] = _zscore_series(frame["drawdown_penalty"], zscore_window)
    frame["reward_proxy_zscore"] = _zscore_series(frame["reward_proxy"], zscore_window)
    rows: list[dict[str, Any]] = []
    for item in windows:
        start = pd.Timestamp(item["start"])
        end = pd.Timestamp(item["end"])
        subset = frame[(frame["date"] >= start) & (frame["date"] <= end)].copy()
        if subset.empty:
            rows.append({**item, "status": "no_data", "available_days": 0})
            continue
        drawdown_extreme = subset["drawdown_penalty_zscore"].abs() >= zscore_threshold
        reward_extreme = subset["reward_proxy_zscore"].abs() >= zscore_threshold
        rows.append(
            {
                **item,
                "status": "available",
                "available_days": int(len(subset)),
                "latest_date": subset["date"].max().date().isoformat(),
                "latest_drawdown_penalty_zscore": _finite_float(subset["drawdown_penalty_zscore"].dropna().iloc[-1])
                if not subset["drawdown_penalty_zscore"].dropna().empty
                else None,
                "latest_reward_proxy_zscore": _finite_float(subset["reward_proxy_zscore"].dropna().iloc[-1])
                if not subset["reward_proxy_zscore"].dropna().empty
                else None,
                "max_abs_drawdown_penalty_zscore": _finite_float(subset["drawdown_penalty_zscore"].abs().max()),
                "max_abs_reward_proxy_zscore": _finite_float(subset["reward_proxy_zscore"].abs().max()),
                "drawdown_penalty_extreme_days": int(drawdown_extreme.sum()),
                "reward_proxy_extreme_days": int(reward_extreme.sum()),
            }
        )
    return rows


def _stress_window_relationships(
    frames: dict[str, pd.DataFrame],
    windows: list[dict[str, str]],
    *,
    benchmark: str,
    targets: list[str],
    min_overlap: int,
) -> list[dict[str, Any]]:
    if benchmark not in frames:
        return []
    benchmark_returns = frames[benchmark].set_index("date")["return"].rename(benchmark)
    rows: list[dict[str, Any]] = []
    for item in windows:
        start = pd.Timestamp(item["start"])
        end = pd.Timestamp(item["end"])
        relationships: list[dict[str, Any]] = []
        for target in targets:
            if target == benchmark or target not in frames:
                relationships.append(
                    {
                        "target": target,
                        "status": "missing_target",
                        "overlap_rows": 0,
                        "correlation": None,
                        "beta": None,
                        "relationship": "unavailable",
                    }
                )
                continue
            target_returns = frames[target].set_index("date")["return"].rename(target)
            pair = pd.concat([benchmark_returns, target_returns], axis=1)
            pair = pair[(pair.index >= start) & (pair.index <= end)]
            stats = _corr_beta(pair, benchmark, target, min_overlap=min_overlap)
            corr = stats["correlation"]
            relationship = "neutral_or_low_overlap"
            if stats["overlap_rows"] < min_overlap:
                relationship = "low_overlap"
            elif corr is not None and corr >= 0.9:
                relationship = "high_positive_benchmark_correlation"
            elif corr is not None and corr <= -0.9:
                relationship = "high_negative_benchmark_correlation"
            relationships.append(
                {
                    "target": target,
                    "status": "available" if stats["overlap_rows"] >= min_overlap else "low_overlap",
                    "overlap_rows": stats["overlap_rows"],
                    "correlation": corr,
                    "beta": stats["beta"],
                    "relationship": relationship,
                }
            )
        rows.append({**item, "relationships": relationships})
    return rows


def build_review(
    *,
    validation_path: Path = DEFAULT_VALIDATION,
    multi_ticker_smoke_path: Path = DEFAULT_MULTI_TICKER_SMOKE,
    feature_stability_path: Path = DEFAULT_FEATURE_STABILITY,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    benchmark: str = "0050.TW",
    targets: list[str] | None = None,
    start: str = "2016-01-01",
    rolling_windows: list[int] | None = None,
    stress_windows: list[dict[str, str]] | None = None,
    min_overlap: int = 40,
    zscore_window: int = 252,
    zscore_threshold: float = 3.0,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    selected_tickers = tickers or list(DEFAULT_TICKERS)
    selected_targets = targets or [ticker for ticker in selected_tickers if ticker != benchmark]
    selected_rolling_windows = rolling_windows or list(DEFAULT_ROLLING_WINDOWS)
    selected_stress_windows = stress_windows or DEFAULT_WINDOWS

    validation = _load_json(validation_path)
    multi_ticker_smoke = _load_json(multi_ticker_smoke_path)
    feature_stability = _load_json(feature_stability_path)
    accepted_ids = _accepted_proposals(validation)

    blockers: list[str] = []
    warnings: list[str] = []
    if not validation:
        blockers.append("missing_proposal_validation_review")
    if proposal_id not in accepted_ids:
        blockers.append("accepted_sample_proposal_missing")
    if not multi_ticker_smoke:
        blockers.append("missing_multi_ticker_smoke_review")
    elif multi_ticker_smoke.get("status") != "available_for_manual_offline_review":
        blockers.append(f"multi_ticker_smoke_not_available:{multi_ticker_smoke.get('status')}")
    if not feature_stability:
        blockers.append("missing_feature_stability_review")
    elif feature_stability.get("status") != "available_for_manual_offline_review":
        blockers.append(f"feature_stability_not_available:{feature_stability.get('status')}")
    if not db_path.exists():
        blockers.append("missing_duckdb")

    frames = _load_feature_frames(db_path, selected_tickers, start=start, proposal_id=proposal_id) if db_path.exists() else {}
    missing_tickers = [ticker for ticker in selected_tickers if ticker not in frames]
    if missing_tickers:
        blockers.append(f"missing_feature_frames:{','.join(missing_tickers)}")
    if benchmark not in frames:
        blockers.append("missing_benchmark_frame")

    rolling_relationships = _rolling_relationships(
        frames,
        benchmark=benchmark,
        targets=selected_targets,
        windows=selected_rolling_windows,
    )
    stress_relationships = _stress_window_relationships(
        frames,
        selected_stress_windows,
        benchmark=benchmark,
        targets=selected_targets,
        min_overlap=min_overlap,
    )
    benchmark_zscore_windows = (
        _benchmark_zscore_windows(
            frames[benchmark],
            selected_stress_windows,
            zscore_window=zscore_window,
            zscore_threshold=zscore_threshold,
        )
        if benchmark in frames
        else []
    )

    latest_rolling_by_target: dict[str, dict[str, Any]] = {}
    for target in selected_targets:
        target_rows = [row for row in rolling_relationships if row["target"] == target and row["available"]]
        latest_rolling_by_target[target] = {
            str(row["window_days"]): {
                "latest_correlation": row["latest_correlation"],
                "latest_beta": row["latest_beta"],
            }
            for row in target_rows
        }

    recent_window = next((row for row in benchmark_zscore_windows if row.get("name") == "taiwan_2026_recent"), None)
    if recent_window:
        if recent_window.get("drawdown_penalty_extreme_days", 0) > 0:
            warnings.append("recent_0050_drawdown_zscore_extreme_days_present")
        if recent_window.get("reward_proxy_extreme_days", 0) > 0:
            warnings.append("recent_0050_reward_zscore_extreme_days_present")

    for window in stress_relationships:
        for relationship in window["relationships"]:
            target = relationship["target"]
            relation = relationship["relationship"]
            if target == "00631L.TW" and relation == "high_positive_benchmark_correlation":
                warnings.append(f"{window['name']}:00631l_amplified_benchmark_exposure")
            if target == "00632R.TW" and relation != "high_negative_benchmark_correlation":
                warnings.append(f"{window['name']}:00632r_not_stable_high_negative_hedge")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_windowed_stability_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "windowed_stability_review_only_no_model_training_no_live_action",
        "inputs": {
            "validation_review": str(validation_path),
            "multi_ticker_smoke_review": str(multi_ticker_smoke_path),
            "feature_stability_review": str(feature_stability_path),
            "db": str(db_path),
            "tickers": selected_tickers,
            "benchmark": benchmark,
            "targets": selected_targets,
            "start": start,
            "rolling_windows": selected_rolling_windows,
            "stress_windows": selected_stress_windows,
            "min_overlap": min_overlap,
            "zscore_window": zscore_window,
            "zscore_threshold": zscore_threshold,
            "accepted_proposal_id": proposal_id,
            "accepted_proposal_found": proposal_id in accepted_ids,
        },
        "summary": {
            "ticker_count": len(selected_tickers),
            "available_ticker_count": len(frames),
            "missing_tickers": missing_tickers,
            "latest_rolling_by_target": latest_rolling_by_target,
            "recent_0050_drawdown_extreme_days": recent_window.get("drawdown_penalty_extreme_days") if recent_window else None,
            "recent_0050_reward_extreme_days": recent_window.get("reward_proxy_extreme_days") if recent_window else None,
        },
        "rolling_relationships": rolling_relationships,
        "stress_window_relationships": stress_relationships,
        "benchmark_zscore_windows": benchmark_zscore_windows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "00631L high positive rolling or stress-window correlation means amplified benchmark exposure, not diversification.",
            "00632R needs persistent high negative stress-window correlation before it can be considered hedge-like; this review still cannot open it automatically.",
            "0050 drawdown/reward z-score extremes are manual-review evidence only, not live rebalance signals.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "windowed_stability_ready_for_research_review": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_windowed_stability_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--multi-ticker-smoke", default=str(DEFAULT_MULTI_TICKER_SMOKE))
    parser.add_argument("--feature-stability", default=str(DEFAULT_FEATURE_STABILITY))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[], help="Ticker to include; default uses 0050/00631L/00632R.")
    parser.add_argument("--benchmark", default="0050.TW")
    parser.add_argument("--target", action="append", default=[], help="Target ticker; default uses non-benchmark selected tickers.")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--rolling-window", action="append", type=int, default=[])
    parser.add_argument("--min-overlap", type=int, default=40)
    parser.add_argument("--zscore-window", type=int, default=252)
    parser.add_argument("--zscore-threshold", type=float, default=3.0)
    parser.add_argument("--proposal-id", default=ACCEPTED_PROPOSAL_ID)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        validation_path=_resolve(args.validation),
        multi_ticker_smoke_path=_resolve(args.multi_ticker_smoke),
        feature_stability_path=_resolve(args.feature_stability),
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        benchmark=args.benchmark,
        targets=args.target or None,
        start=args.start,
        rolling_windows=args.rolling_window or None,
        min_overlap=args.min_overlap,
        zscore_window=args.zscore_window,
        zscore_threshold=args.zscore_threshold,
        proposal_id=args.proposal_id,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward windowed stability review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "ticker_count": review["summary"]["ticker_count"],
                "available_ticker_count": review["summary"]["available_ticker_count"],
                "recent_0050_drawdown_extreme_days": review["summary"]["recent_0050_drawdown_extreme_days"],
                "recent_0050_reward_extreme_days": review["summary"]["recent_0050_reward_extreme_days"],
                "warning_count": len(review["warning_reasons"]),
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
