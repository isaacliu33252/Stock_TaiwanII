#!/usr/bin/env python3
"""Feature-stability review for the accepted LLM state/reward proposal.

This report checks whether the weak GIFT-style feature/reward proxies behave
consistently across the GroupA+ ETF universe. It is offline-only and never
produces actions, target weights, model training, or live rebalance decisions.
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

from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_MULTI_TICKER_SMOKE,
    DEFAULT_TICKERS,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    ACCEPTED_PROPOSAL_ID,
    DEFAULT_DB,
    DEFAULT_VALIDATION,
    _accepted_proposals,
    _feature_frame,
    _load_json,
    _load_ohlcv_from_db,
    _proposal_columns,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_feature_stability_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_feature_stability/history"
FEATURE_COLUMNS = ["relative_momentum", "realized_volatility"]
REWARD_COLUMNS = ["drawdown_penalty", "reward_proxy"]


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _series_stats(series: pd.Series, *, zscore_window: int) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))]
    if finite.empty:
        return {
            "finite_count": 0,
            "finite_ratio": 0.0,
            "latest": None,
            "latest_zscore": None,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "p05": None,
            "p50": None,
            "p95": None,
        }

    latest = finite.iloc[-1]
    trailing = finite.tail(zscore_window)
    trailing_std = trailing.std(ddof=0)
    latest_zscore = None
    if pd.notna(trailing_std) and trailing_std > 0:
        latest_zscore = (latest - trailing.mean()) / trailing_std
    return {
        "finite_count": int(len(finite)),
        "finite_ratio": float(len(finite) / len(series)) if len(series) else 0.0,
        "latest": _finite_float(latest),
        "latest_zscore": _finite_float(latest_zscore),
        "mean": _finite_float(finite.mean()),
        "std": _finite_float(finite.std(ddof=0)),
        "min": _finite_float(finite.min()),
        "max": _finite_float(finite.max()),
        "p05": _finite_float(finite.quantile(0.05)),
        "p50": _finite_float(finite.quantile(0.50)),
        "p95": _finite_float(finite.quantile(0.95)),
    }


def _load_feature_frames(
    db_path: Path,
    tickers: list[str],
    *,
    start: str,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    downside_drawdown_weight: float = 0.50,
    downside_volatility_weight: float = 0.30,
    downside_tail_decay_weight: float = 0.20,
    volatility_penalty_scale: float = 3.0,
    tail_decay_scale: float = 4.0,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df = _load_ohlcv_from_db(db_path, ticker=ticker, start=start)
        if df.empty:
            continue
        frame = _feature_frame(
            df,
            proposal_id=proposal_id,
            downside_drawdown_weight=downside_drawdown_weight,
            downside_volatility_weight=downside_volatility_weight,
            downside_tail_decay_weight=downside_tail_decay_weight,
            volatility_penalty_scale=volatility_penalty_scale,
            tail_decay_scale=tail_decay_scale,
        )
        frame["ticker"] = ticker
        frame["return"] = pd.to_numeric(frame["close"], errors="coerce").pct_change()
        frames[ticker] = frame
    return frames


def _ticker_stability(
    ticker: str,
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    reward_columns: list[str],
    min_finite_ratio: float,
    zscore_window: int,
    zscore_warning: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    column_stats = {
        column: _series_stats(frame[column], zscore_window=zscore_window)
        for column in feature_columns + reward_columns
        if column in frame.columns
    }

    for column, stats in column_stats.items():
        if stats["finite_ratio"] < min_finite_ratio:
            warnings.append(f"low_finite_ratio:{column}:{stats['finite_ratio']:.4f}")
        zscore = stats.get("latest_zscore")
        if zscore is not None and abs(zscore) >= zscore_warning:
            warnings.append(f"latest_zscore_extreme:{column}:{zscore:.4f}")

    return {
        "ticker": ticker,
        "data_range": {
            "start": frame["date"].min().date().isoformat(),
            "end": frame["date"].max().date().isoformat(),
            "rows": int(len(frame)),
        },
        "column_stats": column_stats,
        "warning_reasons": sorted(set(warnings)),
    }


def _pairwise_correlations(frames: dict[str, pd.DataFrame], column: str, *, min_overlap: int) -> dict[str, Any]:
    if not frames:
        return {"column": column, "pairs": [], "summary": {}}
    wide = pd.concat(
        [
            frame.set_index("date")[[column]].rename(columns={column: ticker})
            for ticker, frame in frames.items()
            if column in frame.columns
        ],
        axis=1,
    ).sort_index()

    pairs: list[dict[str, Any]] = []
    tickers = list(wide.columns)
    for idx, left in enumerate(tickers):
        for right in tickers[idx + 1 :]:
            pair = wide[[left, right]].dropna()
            corr = np.nan
            if len(pair) >= min_overlap and pair[left].std(ddof=0) > 0 and pair[right].std(ddof=0) > 0:
                corr = pair[left].corr(pair[right])
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "overlap_rows": int(len(pair)),
                    "correlation": _finite_float(corr),
                }
            )

    finite_corrs = [row["correlation"] for row in pairs if row["correlation"] is not None]
    return {
        "column": column,
        "pairs": pairs,
        "summary": {
            "pair_count": len(pairs),
            "finite_pair_count": len(finite_corrs),
            "max_abs_correlation": max((abs(value) for value in finite_corrs), default=None),
            "min_correlation": min(finite_corrs) if finite_corrs else None,
            "max_correlation": max(finite_corrs) if finite_corrs else None,
        },
    }


def _benchmark_relationships(frames: dict[str, pd.DataFrame], *, benchmark: str, min_overlap: int) -> dict[str, Any]:
    if benchmark not in frames:
        return {"benchmark": benchmark, "relationships": [], "warning_reasons": ["missing_benchmark"]}

    benchmark_returns = frames[benchmark].set_index("date")["return"].rename(benchmark)
    relationships: list[dict[str, Any]] = []
    warnings: list[str] = []
    for ticker, frame in frames.items():
        if ticker == benchmark:
            continue
        pair = pd.concat([benchmark_returns, frame.set_index("date")["return"].rename(ticker)], axis=1).dropna()
        corr = np.nan
        if len(pair) >= min_overlap and pair[benchmark].std(ddof=0) > 0 and pair[ticker].std(ddof=0) > 0:
            corr = pair[benchmark].corr(pair[ticker])
        beta = np.nan
        variance = pair[benchmark].var(ddof=0) if len(pair) >= min_overlap else np.nan
        if pd.notna(variance) and variance > 0:
            beta = pair[ticker].cov(pair[benchmark], ddof=0) / variance
        corr_value = _finite_float(corr)
        beta_value = _finite_float(beta)
        relation = "neutral_or_low_overlap"
        if corr_value is not None and corr_value >= 0.9:
            relation = "high_positive_benchmark_correlation"
        elif corr_value is not None and corr_value <= -0.9:
            relation = "high_negative_benchmark_correlation"
        if relation != "neutral_or_low_overlap":
            warnings.append(f"{ticker}:{relation}")
        relationships.append(
            {
                "ticker": ticker,
                "overlap_rows": int(len(pair)),
                "return_correlation_to_benchmark": corr_value,
                "return_beta_to_benchmark": beta_value,
                "relationship": relation,
            }
        )
    return {
        "benchmark": benchmark,
        "relationships": relationships,
        "warning_reasons": sorted(set(warnings)),
    }


def build_review(
    *,
    validation_path: Path = DEFAULT_VALIDATION,
    multi_ticker_smoke_path: Path = DEFAULT_MULTI_TICKER_SMOKE,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    start: str = "2016-01-01",
    benchmark: str = "0050.TW",
    min_overlap: int = 240,
    min_finite_ratio: float = 0.95,
    zscore_window: int = 252,
    zscore_warning: float = 3.0,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    downside_drawdown_weight: float = 0.50,
    downside_volatility_weight: float = 0.30,
    downside_tail_decay_weight: float = 0.20,
    volatility_penalty_scale: float = 3.0,
    tail_decay_scale: float = 4.0,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    selected_tickers = tickers or list(DEFAULT_TICKERS)
    validation = _load_json(validation_path)
    multi_ticker_smoke = _load_json(multi_ticker_smoke_path)
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
    if not db_path.exists():
        blockers.append("missing_duckdb")

    frames = (
        _load_feature_frames(
            db_path,
            selected_tickers,
            start=start,
            proposal_id=proposal_id,
            downside_drawdown_weight=downside_drawdown_weight,
            downside_volatility_weight=downside_volatility_weight,
            downside_tail_decay_weight=downside_tail_decay_weight,
            volatility_penalty_scale=volatility_penalty_scale,
            tail_decay_scale=tail_decay_scale,
        )
        if db_path.exists()
        else {}
    )
    missing_tickers = [ticker for ticker in selected_tickers if ticker not in frames]
    if missing_tickers:
        blockers.append(f"missing_feature_frames:{','.join(missing_tickers)}")

    columns = _proposal_columns(proposal_id)
    feature_columns = columns["feature_columns"]
    reward_columns = columns["reward_columns"]
    ticker_stability = [
        _ticker_stability(
            ticker,
            frames[ticker],
            feature_columns=feature_columns,
            reward_columns=reward_columns,
            min_finite_ratio=min_finite_ratio,
            zscore_window=zscore_window,
            zscore_warning=zscore_warning,
        )
        for ticker in selected_tickers
        if ticker in frames
    ]
    for row in ticker_stability:
        warnings.extend(f"{row['ticker']}:{reason}" for reason in row.get("warning_reasons", []))

    correlations = [
        _pairwise_correlations(frames, column, min_overlap=min_overlap)
        for column in ["return", *feature_columns, "reward_proxy"]
    ]
    benchmark_relationships = _benchmark_relationships(frames, benchmark=benchmark, min_overlap=min_overlap)
    warnings.extend(benchmark_relationships.get("warning_reasons", []))

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_feature_stability_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "feature_stability_review_only_no_model_training_no_live_action",
        "inputs": {
            "validation_review": str(validation_path),
            "multi_ticker_smoke_review": str(multi_ticker_smoke_path),
            "db": str(db_path),
            "tickers": selected_tickers,
            "start": start,
            "benchmark": benchmark,
            "min_overlap": min_overlap,
            "min_finite_ratio": min_finite_ratio,
            "zscore_window": zscore_window,
            "zscore_warning": zscore_warning,
            "accepted_proposal_id": proposal_id,
            "accepted_proposal_found": proposal_id in accepted_ids,
            "downside_tail_decay_params": {
                "drawdown_weight": downside_drawdown_weight,
                "volatility_weight": downside_volatility_weight,
                "tail_decay_weight": downside_tail_decay_weight,
                "volatility_scale": volatility_penalty_scale,
                "tail_decay_scale": tail_decay_scale,
            },
        },
        "summary": {
            "ticker_count": len(selected_tickers),
            "available_ticker_count": len(frames),
            "missing_tickers": missing_tickers,
            "tickers_with_stability_warnings": [
                row["ticker"] for row in ticker_stability if row.get("warning_reasons")
            ],
            "benchmark_relationship_warning_count": len(benchmark_relationships.get("warning_reasons", [])),
        },
        "ticker_stability": ticker_stability,
        "cross_ticker_correlations": correlations,
        "benchmark_relationships": benchmark_relationships,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "High positive benchmark correlation is expected for 00631L-like exposure, but it means LLM reward proposals must not treat it as a diversifier.",
            "High negative benchmark correlation is expected for 00632R-like exposure, but it means reward shaping must not auto-open hedge exposure.",
            "Feature stability availability is a research-control improvement only; it is not live strategy approval.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "feature_stability_ready_for_research_review": not blockers,
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
    return history_dir / f"llm_state_reward_interface_feature_stability_{stamp}.json"


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
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[], help="Ticker to include; default uses ETF universe.")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--benchmark", default="0050.TW")
    parser.add_argument("--min-overlap", type=int, default=240)
    parser.add_argument("--min-finite-ratio", type=float, default=0.95)
    parser.add_argument("--zscore-window", type=int, default=252)
    parser.add_argument("--zscore-warning", type=float, default=3.0)
    parser.add_argument("--proposal-id", default=ACCEPTED_PROPOSAL_ID)
    parser.add_argument("--downside-drawdown-weight", type=float, default=0.50)
    parser.add_argument("--downside-volatility-weight", type=float, default=0.30)
    parser.add_argument("--downside-tail-decay-weight", type=float, default=0.20)
    parser.add_argument("--volatility-penalty-scale", type=float, default=3.0)
    parser.add_argument("--tail-decay-scale", type=float, default=4.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        validation_path=_resolve(args.validation),
        multi_ticker_smoke_path=_resolve(args.multi_ticker_smoke),
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        start=args.start,
        benchmark=args.benchmark,
        min_overlap=args.min_overlap,
        min_finite_ratio=args.min_finite_ratio,
        zscore_window=args.zscore_window,
        zscore_warning=args.zscore_warning,
        proposal_id=args.proposal_id,
        downside_drawdown_weight=args.downside_drawdown_weight,
        downside_volatility_weight=args.downside_volatility_weight,
        downside_tail_decay_weight=args.downside_tail_decay_weight,
        volatility_penalty_scale=args.volatility_penalty_scale,
        tail_decay_scale=args.tail_decay_scale,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward feature stability review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "ticker_count": review["summary"]["ticker_count"],
                "available_ticker_count": review["summary"]["available_ticker_count"],
                "tickers_with_stability_warnings": review["summary"]["tickers_with_stability_warnings"],
                "benchmark_relationship_warning_count": review["summary"]["benchmark_relationship_warning_count"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
