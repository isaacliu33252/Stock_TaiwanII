#!/usr/bin/env python3
"""Robustness sweep for the StockMixer+ATFNet shadow.

Runs multi-seed, multi-window checks from cached OHLCV parquet data. This is a
research-only gate: it compares StockMixer+ATFNet against own-history logistic
and persistence baselines, and never writes live strategy outputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_stockmixer_atfnet_shadow import (  # noqa: E402
    LOOKBACK,
    PARTIAL_0050_PROXY_WEIGHTS,
    StockMixerATFNetLite,
    _default_cache_for_universe,
    _tickers_for_universe,
    build_universe_weights,
    evaluate_predictions,
    load_returns,
    make_windows,
    own_history_logistic_baseline,
    persistence_baseline,
    train_model,
    weighted_index_metrics,
)


DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/stockmixer_atfnet_robustness_sweep.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/stockmixer_atfnet_robustness/history"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _starts(n: int, train_rows: int, val_rows: int, test_rows: int, n_windows: int) -> list[int]:
    width = train_rows + val_rows + test_rows
    max_start = n - width
    if max_start < 0:
        raise ValueError(f"not enough samples: n={n}, required={width}")
    if n_windows <= 1:
        return [0]
    return sorted({int(round(x)) for x in np.linspace(0, max_start, n_windows)})


def _threshold(val_scores: np.ndarray, weights: np.ndarray) -> float:
    weighted = val_scores @ (weights / weights.sum())
    return float(np.median(weighted))


def _run_window(
    *,
    X: np.ndarray,
    y: np.ndarray,
    y_ret_all: np.ndarray,
    dates: Any,
    returns: Any,
    tickers: list[str],
    start: int,
    train_rows: int,
    val_rows: int,
    test_rows: int,
    seeds: list[int],
    epochs: int,
    alpha: float,
    top_n: int,
    lookback: int,
) -> dict[str, Any]:
    train_end = start + train_rows
    val_end = train_end + val_rows
    test_end = val_end + test_rows

    X_train, y_train = X[start:train_end], y[start:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:test_end], y[val_end:test_end]
    y_ret_test = y_ret_all[val_end:test_end]
    test_dates = dates[val_end:test_end]

    weights_dict = build_universe_weights(tickers, PARTIAL_0050_PROXY_WEIGHTS)
    weights = np.array([weights_dict[ticker] for ticker in tickers], dtype=np.float64)
    logistic_val, logistic_test = own_history_logistic_baseline(returns, lookback, train_end, val_end)
    logistic_test = logistic_test[:test_rows]
    persist_val = persistence_baseline(X_val)
    persist_test = persistence_baseline(X_test)

    logistic_metrics = evaluate_predictions(logistic_test, y_ret_test, y_test, top_n=top_n)
    persistence_metrics = evaluate_predictions(persist_test, y_ret_test, y_test, top_n=top_n)
    logistic_weighted = weighted_index_metrics(logistic_test, y_ret_test, weights, _threshold(logistic_val, weights))
    persistence_weighted = weighted_index_metrics(persist_test, y_ret_test, weights, _threshold(persist_val, weights))

    runs = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        model = StockMixerATFNetLite(lookback, len(tickers), alpha=alpha)
        history = train_model(model, X_train, y_train, X_val, y_val, epochs=epochs)
        model.eval()
        with torch.no_grad():
            val_logits = model(torch.from_numpy(X_val)).numpy()
            test_logits = model(torch.from_numpy(X_test)).numpy()
        val_scores = 1.0 / (1.0 + np.exp(-val_logits))
        test_scores = 1.0 / (1.0 + np.exp(-test_logits))
        metrics = evaluate_predictions(test_scores, y_ret_test, y_test, top_n=top_n)
        weighted = weighted_index_metrics(test_scores, y_ret_test, weights, _threshold(val_scores, weights))
        runs.append(
            {
                "seed": seed,
                "metrics": metrics,
                "weighted_0050_proxy": weighted,
                "training": {
                    "final_train_loss": float(history["train_loss"][-1]),
                    "final_val_loss": float(history["val_loss"][-1]),
                    "best_val_loss": float(min(history["val_loss"])),
                },
            }
        )

    return {
        "start_row": start,
        "train_rows": train_rows,
        "val_rows": val_rows,
        "test_rows": test_rows,
        "test_period": [str(test_dates.min().date()), str(test_dates.max().date())],
        "stockmixer_runs": runs,
        "baselines": {
            "own_history_logistic": {"metrics": logistic_metrics, "weighted_0050_proxy": logistic_weighted},
            "persistence": {"metrics": persistence_metrics, "weighted_0050_proxy": persistence_weighted},
        },
    }


def _mean(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return float(np.mean(clean)) if clean else None


def _aggregate(windows: list[dict[str, Any]]) -> dict[str, Any]:
    runs = [run for window in windows for run in window["stockmixer_runs"]]
    logistic = [window["baselines"]["own_history_logistic"] for window in windows]
    persistence = [window["baselines"]["persistence"] for window in windows]

    def metric_rows(rows: list[dict[str, Any]], nested: str) -> dict[str, Any]:
        return {
            "accuracy": _mean([row[nested]["accuracy"] for row in rows]),
            "ic": _mean([row[nested].get("ic") for row in rows]),
            "ric": _mean([row[nested].get("ric") for row in rows]),
        }

    stock_metrics = metric_rows([{"metrics": r["metrics"]} for r in runs], "metrics")
    stock_weighted_corr = _mean([r["weighted_0050_proxy"].get("weighted_return_corr") for r in runs])
    stock_weighted_sharpe = _mean([r["weighted_0050_proxy"].get("long_short_sharpe") for r in runs])
    return {
        "stockmixer_atfnet": {
            **stock_metrics,
            "weighted_return_corr": stock_weighted_corr,
            "long_short_sharpe": stock_weighted_sharpe,
        },
        "own_history_logistic": {
            **metric_rows(logistic, "metrics"),
            "weighted_return_corr": _mean([row["weighted_0050_proxy"].get("weighted_return_corr") for row in logistic]),
            "long_short_sharpe": _mean([row["weighted_0050_proxy"].get("long_short_sharpe") for row in logistic]),
        },
        "persistence": {
            **metric_rows(persistence, "metrics"),
            "weighted_return_corr": _mean([row["weighted_0050_proxy"].get("weighted_return_corr") for row in persistence]),
            "long_short_sharpe": _mean([row["weighted_0050_proxy"].get("long_short_sharpe") for row in persistence]),
        },
    }


def build_sweep(
    *,
    as_of: str,
    universe: str,
    cache_path: Path,
    seeds: list[int],
    n_windows: int,
    train_rows: int,
    val_rows: int,
    test_rows: int,
    epochs: int,
    min_history_days: int,
    lookback: int,
    alpha: float,
    top_n: int,
) -> dict[str, Any]:
    tickers = _tickers_for_universe(universe)
    returns = load_returns(cache_path, tickers, min_history_days=min_history_days)
    tickers = list(returns.columns)
    X, y, dates = make_windows(returns, lookback)
    ret_values = returns.values.astype(np.float32)
    y_ret_all = np.stack([ret_values[t + 1, :] for t in range(lookback, len(ret_values) - 1)])
    starts = _starts(len(X), train_rows, val_rows, test_rows, n_windows)
    windows = [
        _run_window(
            X=X,
            y=y,
            y_ret_all=y_ret_all,
            dates=dates,
            returns=returns,
            tickers=tickers,
            start=start,
            train_rows=train_rows,
            val_rows=val_rows,
            test_rows=test_rows,
            seeds=seeds,
            epochs=epochs,
            alpha=alpha,
            top_n=top_n,
            lookback=lookback,
        )
        for start in starts
    ]
    aggregate = _aggregate(windows)
    stock = aggregate["stockmixer_atfnet"]
    logistic = aggregate["own_history_logistic"]
    live_blockers = [
        "research_shadow_only_no_live_target_path",
        "no_execution_cost_or_turnover_backtest",
    ]
    if (stock.get("ic") or 0.0) <= (logistic.get("ic") or 0.0):
        live_blockers.append("stockmixer_ic_not_above_logistic_baseline")
    if (stock.get("weighted_return_corr") or 0.0) <= 0.0:
        live_blockers.append("weighted_0050_proxy_corr_not_positive")
    if (stock.get("long_short_sharpe") or -999.0) <= (logistic.get("long_short_sharpe") or -999.0):
        live_blockers.append("weighted_proxy_sharpe_not_above_logistic_baseline")

    return {
        "schema_version": 1,
        "report_type": "stockmixer_atfnet_robustness_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "universe": universe,
        "cache": str(cache_path),
        "seeds": seeds,
        "n_windows": len(windows),
        "window_shape": {"train_rows": train_rows, "val_rows": val_rows, "test_rows": test_rows},
        "aggregate": aggregate,
        "windows": windows,
        "decision": {
            "research_complete": True,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "live_blocking_reasons": sorted(set(live_blockers)),
        },
    }


def _write_md(payload: dict[str, Any], path: Path) -> None:
    agg = payload["aggregate"]
    lines = [
        "# StockMixer/ATFNet Robustness Sweep",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Universe: `{payload['universe']}`",
        f"- Windows: `{payload['n_windows']}`",
        f"- Seeds: `{payload['seeds']}`",
        f"- Promote to live: `{payload['decision']['promote_to_live']}`",
        f"- Target weight change allowed: `{payload['decision']['target_weight_change_allowed']}`",
        "",
        "## Aggregate",
        "",
        f"- StockMixer IC: `{agg['stockmixer_atfnet']['ic']}`",
        f"- Logistic IC: `{agg['own_history_logistic']['ic']}`",
        f"- Persistence IC: `{agg['persistence']['ic']}`",
        f"- StockMixer weighted return corr: `{agg['stockmixer_atfnet']['weighted_return_corr']}`",
        f"- StockMixer weighted long-short Sharpe: `{agg['stockmixer_atfnet']['long_short_sharpe']}`",
        "",
        "## Live Blocking Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in payload["decision"]["live_blocking_reasons"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sweep(payload: dict[str, Any], output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(payload, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(payload["as_of"]).replace("-", "")
        (history_dir / f"stockmixer_atfnet_robustness_sweep_{payload['universe']}_{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().date().isoformat())
    parser.add_argument("--universe", choices=["top15", "full50_202606", "top75_candidate_202606"], default="full50_202606")
    parser.add_argument("--cache", default=None)
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--n-windows", type=int, default=3)
    parser.add_argument("--train-rows", type=int, default=900)
    parser.add_argument("--val-rows", type=int, default=240)
    parser.add_argument("--test-rows", type=int, default=240)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--min-history-days", type=int, default=1200)
    parser.add_argument("--lookback", type=int, default=LOOKBACK)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = [int(part.strip()) for part in args.seeds.split(",") if part.strip()]
    cache = _resolve(args.cache) if args.cache else _default_cache_for_universe(args.universe)
    payload = build_sweep(
        as_of=args.as_of,
        universe=args.universe,
        cache_path=cache,
        seeds=seeds,
        n_windows=args.n_windows,
        train_rows=args.train_rows,
        val_rows=args.val_rows,
        test_rows=args.test_rows,
        epochs=args.epochs,
        min_history_days=args.min_history_days,
        lookback=args.lookback,
        alpha=args.alpha,
        top_n=args.top_n,
    )
    write_sweep(
        payload,
        _resolve(args.output_json),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"StockMixer/ATFNet robustness sweep: {_resolve(args.output_json)}")
    print(json.dumps({"aggregate": payload["aggregate"], "decision": payload["decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
