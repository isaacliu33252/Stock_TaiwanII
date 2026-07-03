#!/usr/bin/env python3
"""Research-only StockMixer+ATFNet shadow benchmark on 0050 holdings.

Implements a simplified version of the architecture from Sun et al. 2025
(Scientific Reports, s41598-025-14872-6): MultTime2dMixer (time-mixing +
stock-mixing MLP paths), NoGraphMixer (learnable implicit stock-correlation
matrix), and ATFNet (FFT-based frequency-domain linear reweighting), fused
by a simple average. Trained to predict next-day direction (up/down) jointly
for a fixed universe of N stocks using only each stock's own daily log
return as input (no OHLCV, no external features) -- this is a deliberately
minimal reproduction to test whether the paper's core ideas (implicit
cross-stock mixing + frequency-domain features) beat a naive per-stock
baseline on a much smaller universe (N=15 vs the paper's N=1026).

Does not touch any live Group A+ allocation logic. Universe can be 0050's
top-15 holdings by weight or a static 2026 full-50 Taiwan 50 constituent
set (individual TWSE stocks), not 00631L/00632R.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yfinance as yf
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = PROJECT_ROOT / "results" / "stockmixer_atfnet_0050top15_ohlcv_cache.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "stockmixer_atfnet_shadow_latest_20260702.json"

TOP15_TICKERS = [
    "2330.TW", "2454.TW", "2308.TW", "2317.TW", "3711.TW", "2303.TW", "2327.TW",
    "2383.TW", "3037.TW", "2345.TW", "2891.TW", "2881.TW", "2382.TW", "1303.TW", "2882.TW",
]
FULL50_TICKERS_202606 = [
    "2059.TW", "2301.TW", "2303.TW", "2308.TW", "2317.TW", "2327.TW", "2330.TW",
    "2344.TW", "2345.TW", "2357.TW", "2360.TW", "2368.TW", "2382.TW", "2383.TW",
    "2395.TW", "2408.TW", "2449.TW", "2454.TW", "3008.TW", "3017.TW", "3037.TW",
    "3231.TW", "3443.TW", "3653.TW", "3661.TW", "3665.TW", "3711.TW", "4958.TW",
    "6669.TW", "7769.TW", "8046.TW", "1216.TW", "1303.TW", "2412.TW", "2603.TW",
    "3045.TW", "4904.TW", "6505.TW", "2880.TW", "2881.TW", "2882.TW", "2883.TW",
    "2884.TW", "2885.TW", "2886.TW", "2887.TW", "2890.TW", "2891.TW", "2892.TW",
    "5880.TW",
]
TOP75_CANDIDATE_TICKERS_202606 = FULL50_TICKERS_202606 + [
    "1101.TW", "1102.TW", "1402.TW", "1590.TW", "2002.TW", "2207.TW", "2227.TW",
    "2376.TW", "2377.TW", "2379.TW", "2392.TW", "2409.TW", "2474.TW", "2609.TW",
    "2615.TW", "2618.TW", "2912.TW", "3034.TW", "5871.TW", "5876.TW", "6415.TW",
    "6446.TW", "6488.TW", "9910.TW", "9945.TW",
]
PARTIAL_0050_PROXY_WEIGHTS = {
    # Research-only proxy weights. Values are decimals; missing universe members
    # receive an equal share of the remaining weight.
    "2330.TW": 0.54496937,
    "2317.TW": 0.04834110,
    "2454.TW": 0.03959831,
    "2308.TW": 0.02607424,
    "2382.TW": 0.01352036,
    "2881.TW": 0.01306231,
    "2882.TW": 0.01296288,
    "2303.TW": 0.01109557,
    "2412.TW": 0.00946836,
    "2886.TW": 0.00927207,
    "3711.TW": 0.00922795,
    "2891.TW": 0.00902772,
    "2884.TW": 0.00887874,
    "1216.TW": 0.00860242,
    "2357.TW": 0.00832916,
    "2885.TW": 0.00701342,
    "2892.TW": 0.00688608,
    "2883.TW": 0.00643995,
    "2890.TW": 0.00641338,
    "2603.TW": 0.00638586,
    "3037.TW": 0.00638430,
    "2880.TW": 0.00618717,
    "1303.TW": 0.00603028,
    "5871.TW": 0.00583204,
    "2327.TW": 0.00513102,
    "3008.TW": 0.00493602,
}
LOOKBACK = 16  # matches paper's T


def _tickers_for_universe(universe: str) -> list[str]:
    if universe == "top15":
        return TOP15_TICKERS
    if universe == "full50_202606":
        return FULL50_TICKERS_202606
    if universe == "top75_candidate_202606":
        return TOP75_CANDIDATE_TICKERS_202606
    raise ValueError(f"unknown universe: {universe}")


def _default_cache_for_universe(universe: str) -> Path:
    if universe == "top15":
        return PROJECT_ROOT / "results" / "stockmixer_atfnet_0050top15_ohlcv_cache.parquet"
    return PROJECT_ROOT / "results" / f"stockmixer_atfnet_{universe}_ohlcv_cache.parquet"


def build_universe_weights(tickers: list[str], partial_weights: dict[str, float]) -> dict[str, float]:
    known = {ticker: float(partial_weights[ticker]) for ticker in tickers if ticker in partial_weights}
    known_total = sum(known.values())
    if known_total > 1.0:
        # Keep every requested ticker in the output (missing members get 0
        # weight) so downstream `universe_weights[ticker]` lookups never
        # KeyError -- previously this branch silently dropped them.
        renormalized = {ticker: weight / known_total for ticker, weight in known.items()}
        return {ticker: renormalized.get(ticker, 0.0) for ticker in tickers}

    missing = [ticker for ticker in tickers if ticker not in known]
    residual = max(0.0, 1.0 - known_total)
    missing_weight = residual / len(missing) if missing else 0.0
    weights = {ticker: known.get(ticker, missing_weight) for ticker in tickers}
    total = sum(weights.values())
    return {ticker: weight / total for ticker, weight in weights.items()}


def download_cache(cache_path: Path, tickers: list[str], start: str, end: str) -> dict[str, Any]:
    data = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    if data.empty:
        raise RuntimeError("yfinance returned no rows")
    if not isinstance(data.columns, pd.MultiIndex):
        if len(tickers) != 1:
            raise RuntimeError("unexpected non-MultiIndex yfinance output for multi-ticker request")
        data = pd.concat({tickers[0]: data}, axis=1)

    available: list[str] = []
    missing: list[str] = []
    normalized_parts: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        if ticker not in data.columns.get_level_values(0):
            missing.append(ticker)
            continue
        frame = data[ticker].copy()
        if "Close" not in frame or frame["Close"].dropna().empty:
            missing.append(ticker)
            continue
        normalized_parts[ticker] = frame
        available.append(ticker)

    if len(available) < 10:
        raise RuntimeError(f"too few tickers downloaded: {len(available)} available, missing={missing}")
    normalized = pd.concat(normalized_parts, axis=1).sort_index()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(cache_path)
    return {
        "cache": str(cache_path),
        "start": start,
        "end": end,
        "requested_tickers": len(tickers),
        "available_tickers": available,
        "missing_tickers": missing,
        "rows": int(len(normalized)),
    }


def load_returns(cache_path: Path, tickers: list[str], min_history_days: int = 0) -> pd.DataFrame:
    raw = pd.read_parquet(cache_path)
    available = [ticker for ticker in tickers if ticker in raw.columns.get_level_values(0)]
    close_parts = {}
    for ticker in available:
        frame = raw[ticker]
        # Use dividend/split-adjusted close -- raw Close produces spurious
        # "down" labels on ex-dividend dates for high-yield constituents
        # (e.g. 2454/2882/2881 saw single-day drops up to ~10% from this).
        close = frame["Adj Close"] if "Adj Close" in frame.columns else frame["Close"]
        if int(close.notna().sum()) < min_history_days:
            continue
        close_parts[ticker] = close
    if not close_parts:
        raise RuntimeError("no tickers passed the history filter")
    closes = pd.concat(close_parts, axis=1)
    closes = closes.sort_index().ffill().dropna()
    log_ret = np.log(closes / closes.shift(1)).dropna()
    return log_ret


def make_windows(returns: pd.DataFrame, lookback: int) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    values = returns.values.astype(np.float32)
    dates = returns.index
    X, y, idx = [], [], []
    for t in range(lookback, len(values) - 1):
        # Window ends at t (inclusive) so the model sees the most recent
        # known return before predicting t+1 -- previously ended at t-1,
        # leaving a 1-day gap between the window and the target.
        X.append(values[t - lookback + 1:t + 1, :])
        y.append((values[t + 1, :] > 0).astype(np.float32))
        idx.append(dates[t + 1])
    return np.stack(X), np.stack(y), pd.DatetimeIndex(idx)


class MultTime2dMixer(nn.Module):
    """Dual-path MLP mixer: time-mixing per stock + stock-mixing per timestep."""

    def __init__(self, lookback: int, n_stocks: int, hidden: int = 32):
        super().__init__()
        self.time_mlp = nn.Sequential(
            nn.Linear(lookback, hidden), nn.ReLU(), nn.Linear(hidden, lookback)
        )
        self.conv = nn.Conv1d(n_stocks, n_stocks, kernel_size=3, padding=1, groups=1)
        self.stock_mlp = nn.Sequential(
            nn.Linear(n_stocks, hidden), nn.ReLU(), nn.Linear(hidden, n_stocks)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, T, N]
        xt = self.time_mlp(x.transpose(1, 2)).transpose(1, 2)  # mix across T per stock
        xc = self.conv(x.transpose(1, 2)).transpose(1, 2)  # local smoothing across T
        xc = self.stock_mlp(xc)  # mix across N (stocks) per timestep
        return xt + xc


class NoGraphMixer(nn.Module):
    """Learnable implicit stock-correlation matrix Ws (N x N), no explicit graph."""

    def __init__(self, n_stocks: int):
        super().__init__()
        self.Ws = nn.Linear(n_stocks, n_stocks, bias=False)
        self.fc_time = nn.Linear(n_stocks, n_stocks)
        self.fc_stock = nn.Linear(n_stocks, n_stocks)

    def forward(self, y: torch.Tensor) -> torch.Tensor:
        # y: [B, T, N]
        z = self.Ws(y)
        o = self.fc_time(y) + self.fc_stock(z)
        return o.mean(dim=1)  # pool over T -> [B, N]


class ATFNet(nn.Module):
    """FFT -> linear reweight real/imag -> iFFT -> mean-pool -> linear project."""

    def __init__(self, n_stocks: int):
        super().__init__()
        self.w_real = nn.Linear(n_stocks, n_stocks)
        self.w_imag = nn.Linear(n_stocks, n_stocks)
        self.out = nn.Linear(n_stocks, n_stocks)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, T, N]
        freq = torch.fft.rfft(x, dim=1)  # [B, F, N] complex
        real = self.w_real(freq.real)
        imag = self.w_imag(freq.imag)
        recon = torch.fft.irfft(torch.complex(real, imag), n=x.shape[1], dim=1)  # [B, T, N]
        pooled = recon.mean(dim=1)  # [B, N]
        return self.out(pooled)


class StockMixerATFNetLite(nn.Module):
    """Simplified StockMixer+ATFNet: MultTime2dMixer -> NoGraphMixer, fused with ATFNet."""

    def __init__(self, lookback: int, n_stocks: int, alpha: float = 0.5):
        super().__init__()
        self.mixer = MultTime2dMixer(lookback, n_stocks)
        self.nograph = NoGraphMixer(n_stocks)
        self.atfnet = ATFNet(n_stocks)
        self.alpha = alpha

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.mixer(x)
        o_time = self.nograph(y)
        o_freq = self.atfnet(x)
        return self.alpha * o_time + (1.0 - self.alpha) * o_freq  # logits [B, N]


def train_model(
    model: nn.Module,
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    epochs: int = 60, lr: float = 1e-3, batch_size: int = 32,
) -> dict[str, list[float]]:
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.BCEWithLogitsLoss()
    Xt = torch.from_numpy(X_train)
    yt = torch.from_numpy(y_train)
    Xv = torch.from_numpy(X_val)
    yv = torch.from_numpy(y_val)
    n = Xt.shape[0]
    history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}
    best_val = float("inf")
    best_state = None
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n)
        total_loss = 0.0
        for i in range(0, n, batch_size):
            batch_idx = perm[i:i + batch_size]
            opt.zero_grad()
            logits = model(Xt[batch_idx])
            loss = loss_fn(logits, yt[batch_idx])
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(batch_idx)
        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(Xv), yv).item()
        history["train_loss"].append(total_loss / n)
        history["val_loss"].append(val_loss)
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    if best_state is not None:
        model.load_state_dict(best_state)
    return history


def evaluate_predictions(scores: np.ndarray, y_true_ret: np.ndarray, y_true_dir: np.ndarray, top_n: int = 3) -> dict[str, float]:
    pred_dir = (scores > 0.5).astype(int)
    accuracy = float((pred_dir == y_true_dir).mean())
    ics, rics, precs = [], [], []
    for day in range(scores.shape[0]):
        s, r = scores[day], y_true_ret[day]
        if np.std(s) < 1e-9 or np.std(r) < 1e-9:
            continue
        ics.append(float(np.corrcoef(s, r)[0, 1]))
        rho, _ = spearmanr(s, r)
        if not np.isnan(rho):
            rics.append(float(rho))
        top_idx = np.argsort(-s)[:top_n]
        precs.append(float((r[top_idx] > 0).mean()))
    return {
        "accuracy": accuracy,
        "ic": float(np.mean(ics)) if ics else None,
        "ric": float(np.mean(rics)) if rics else None,
        f"prec_at_{top_n}": float(np.mean(precs)) if precs else None,
    }


def weighted_index_metrics(
    scores: np.ndarray,
    y_true_ret: np.ndarray,
    weights: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    weights = weights / weights.sum()
    weighted_prob = scores @ weights
    weighted_ret = y_true_ret @ weights
    # `threshold` should normally be calibrated on validation-period
    # weighted_prob (e.g. its median), not left at 0.5: per-stock
    # probabilities are trained to each stock's own ~50% base rate, while
    # a market-cap-weighted index base rate can sit meaningfully above
    # 50% (0050 test period: ~56%) -- a hard 0.5 cutoff then predicts
    # "down" every day regardless of model skill, producing an
    # accuracy/Sharpe number that reflects the index's own drift, not the
    # model. `weighted_return_corr` below is threshold-independent and is
    # the metric to trust when threshold calibration isn't available.
    pred_up = weighted_prob > threshold
    actual_up = weighted_ret > 0.0
    active = np.where(pred_up, weighted_ret, 0.0)
    long_short = np.where(pred_up, weighted_ret, -weighted_ret)
    ann = np.sqrt(252.0)

    def _sharpe(ret: np.ndarray) -> float | None:
        std = float(np.std(ret))
        if std < 1e-12:
            return None
        return float(np.mean(ret) / std * ann)

    corr = None
    if np.std(weighted_prob) > 1e-12 and np.std(weighted_ret) > 1e-12:
        corr = float(np.corrcoef(weighted_prob, weighted_ret)[0, 1])
    return {
        "threshold": float(threshold),
        "weighted_direction_accuracy": float((pred_up == actual_up).mean()),
        "weighted_return_corr": corr,
        "weighted_prob_mean": float(np.mean(weighted_prob)),
        "weighted_prob_last": float(weighted_prob[-1]),
        "weighted_actual_up_rate": float(actual_up.mean()),
        "weighted_pred_up_rate": float(pred_up.mean()),
        "long_flat_mean_daily_return": float(np.mean(active)),
        "long_flat_sharpe": _sharpe(active),
        "long_short_sharpe": _sharpe(long_short),
    }


def own_history_logistic_baseline(returns: pd.DataFrame, lookback: int, train_end: int, val_end: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-stock logistic regression using only that stock's own lagged returns (no cross-stock info)."""
    values = returns.values.astype(np.float64)
    n_days, n_stocks = values.shape
    all_scores = np.zeros((n_days - lookback - 1, n_stocks), dtype=np.float64)
    for s in range(n_stocks):
        X, y = [], []
        for t in range(lookback, n_days - 1):
            X.append(values[t - lookback + 1:t + 1, s])
            y.append(1 if values[t + 1, s] > 0 else 0)
        X, y = np.array(X), np.array(y)
        X_train, y_train = X[:train_end], y[:train_end]
        if len(np.unique(y_train)) < 2:
            all_scores[:, s] = 0.5
            continue
        clf = LogisticRegression(max_iter=1000)
        clf.fit(X_train, y_train)
        all_scores[:, s] = clf.predict_proba(X)[:, 1]
    return all_scores[train_end:val_end], all_scores[val_end:]


def persistence_baseline(X: np.ndarray) -> np.ndarray:
    """Predict next-day direction = sign of most recent day's return."""
    last = X[:, -1, :]
    return (last > 0).astype(np.float64) * 0.9 + (last <= 0).astype(np.float64) * 0.1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe",
        choices=["top15", "full50_202606", "top75_candidate_202606"],
        default="top15",
    )
    parser.add_argument("--cache", default=None)
    parser.add_argument("--download-cache", action="store_true")
    parser.add_argument("--download-start", default="2019-01-01")
    parser.add_argument("--download-end", default="2026-07-03")
    parser.add_argument("--min-history-days", type=int, default=0)
    parser.add_argument("--lookback", type=int, default=LOOKBACK)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    torch.manual_seed(42)
    np.random.seed(42)

    tickers = _tickers_for_universe(args.universe)
    cache_path = Path(args.cache) if args.cache else _default_cache_for_universe(args.universe)
    cache_report = None
    if args.download_cache or not cache_path.exists():
        cache_report = download_cache(cache_path, tickers, args.download_start, args.download_end)
    returns = load_returns(cache_path, tickers, min_history_days=args.min_history_days)
    tickers = list(returns.columns)
    X, y, dates = make_windows(returns, args.lookback)
    n = len(X)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)

    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]
    test_dates = dates[val_end:]

    # actual next-day returns for IC/RIC/Prec@N (not just direction)
    ret_values = returns.values.astype(np.float32)
    y_ret_all = np.stack([ret_values[t + 1, :] for t in range(args.lookback, len(ret_values) - 1)])
    y_ret_test = y_ret_all[val_end:]
    universe_weights = build_universe_weights(tickers, PARTIAL_0050_PROXY_WEIGHTS)
    weight_arr = np.array([universe_weights[ticker] for ticker in tickers], dtype=np.float64)

    model = StockMixerATFNetLite(args.lookback, len(tickers), alpha=args.alpha)
    history = train_model(model, X_train, y_train, X_val, y_val, epochs=args.epochs)

    def _calibrated_threshold(val_scores: np.ndarray) -> float:
        # Median weighted probability on the *validation* period, not a
        # hard 0.5 -- per-stock probabilities are calibrated to each
        # stock's own ~50% base rate, while the market-cap-weighted index
        # base rate can differ meaningfully (0050 test period: ~56% up).
        # A hard 0.5 cutoff then predicts "down" every day regardless of
        # model skill (see weighted_index_metrics docstring note).
        weighted_val_prob = val_scores @ (weight_arr / weight_arr.sum())
        return float(np.median(weighted_val_prob))

    model.eval()
    with torch.no_grad():
        val_logits = model(torch.from_numpy(X_val)).numpy()
        test_logits = model(torch.from_numpy(X_test)).numpy()
    val_scores = 1.0 / (1.0 + np.exp(-val_logits))
    test_scores = 1.0 / (1.0 + np.exp(-test_logits))
    ours_metrics = evaluate_predictions(test_scores, y_ret_test, y_test, top_n=args.top_n)
    ours_weighted = weighted_index_metrics(
        test_scores, y_ret_test, weight_arr, threshold=_calibrated_threshold(val_scores)
    )

    persist_val_scores = persistence_baseline(X_val)
    persist_scores = persistence_baseline(X_test)
    persist_metrics = evaluate_predictions(persist_scores, y_ret_test, y_test, top_n=args.top_n)
    persist_weighted = weighted_index_metrics(
        persist_scores, y_ret_test, weight_arr, threshold=_calibrated_threshold(persist_val_scores)
    )

    logistic_val_scores, logistic_test_scores = own_history_logistic_baseline(
        returns, args.lookback, train_end, val_end
    )
    logistic_metrics = evaluate_predictions(logistic_test_scores, y_ret_test, y_test, top_n=args.top_n)
    logistic_weighted = weighted_index_metrics(
        logistic_test_scores, y_ret_test, weight_arr, threshold=_calibrated_threshold(logistic_val_scores)
    )

    result = {
        "schema_version": 1,
        "report_type": "stockmixer_atfnet_shadow",
        "generated_at": datetime.now().isoformat(),
        "status": "research_only",
        "active_allocation_impact": "none",
        "note": (
            "Simplified reproduction of Sun et al. 2025 (s41598-025-14872-6) StockMixer+ATFNet, "
            f"tested on 0050 universe={args.universe} (individual TWSE stocks), not the paper's "
            "original NASDAQ/NYSE universe (N=1026) and not Group A+'s 00631L/00632R models. "
            "Input is each stock's own daily log return only (no OHLCV/volume/external features), "
            "lookback=16 matching the paper. This does not affect any live Group A+ allocation logic."
        ),
        "universe_name": args.universe,
        "universe_source": (
            "static Taiwan 50 constituents after 2026-06 rebalance, derived from Taiwan 50 Index page"
            if args.universe == "full50_202606"
            else "static Taiwan 50 plus 25 large-cap Taiwan candidates, research-only approximate top-75 universe"
            if args.universe == "top75_candidate_202606"
            else "static 0050 top-15 holdings list"
        ),
        "universe": tickers,
        "universe_weights": universe_weights,
        "universe_weights_method": (
            "partial_0050_proxy_weights_else_equal_residual; research-only proxy, not official Yuanta holdings"
        ),
        "cache": str(cache_path),
        "cache_report": cache_report,
        "min_history_days": args.min_history_days,
        "dropped_tickers": sorted(set(_tickers_for_universe(args.universe)) - set(tickers)),
        "lookback": args.lookback,
        "alpha": args.alpha,
        "n_samples": {"train": int(train_end), "val": int(val_end - train_end), "test": int(n - val_end)},
        "test_period": {"start": str(test_dates.min().date()), "end": str(test_dates.max().date())},
        "results": {
            "stockmixer_atfnet_lite": ours_metrics,
            "own_history_logistic_baseline": logistic_metrics,
            "persistence_baseline": persist_metrics,
        },
        "weighted_0050_proxy_results": {
            "stockmixer_atfnet_lite": ours_weighted,
            "own_history_logistic_baseline": logistic_weighted,
            "persistence_baseline": persist_weighted,
        },
        "training_history": {
            "final_train_loss": history["train_loss"][-1],
            "final_val_loss": history["val_loss"][-1],
            "best_val_loss": min(history["val_loss"]),
        },
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["results"], indent=2))
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
