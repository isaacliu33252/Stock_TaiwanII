#!/usr/bin/env python3
"""Shadow test: does a Gaussian-HMM regime classifier + Top-1 rotation
(arXiv:2605.27848, "Regime-Based Portfolio Allocation Using Hidden Markov
Models and Reinforcement Learning") add value over Group A+'s existing
regime-switching mechanisms, adapted to Group A+'s actual Taiwan universe?

The paper itself is weak (no significance testing, single 70/30 split, no
walk-forward, RL result tied with a naive Equal-Weight-Monthly baseline in
its own headline table, no transaction costs) -- see
GROUP_A_PLUS_2605_27848_HMM_RL_REGIME_ROTATION_REVIEW_20260812.md for the
paper review. This script tests the core *mechanism* (3-state Gaussian
HMM regime detection -> regime-conditioned Top-1 rotation) on Group A+'s
own assets with a proper purged walk-forward protocol, rather than relying
on the paper's own thin evidence either way.

Universe adaptation: paper uses SPY(equity)/TLT(bond)/GLD(gold). Group A+
has no gold ETF in its tradable set, so this uses 0050(equity)/
00679B(20y US treasury, TW-listed)/00632R(inverse, as the paper's GLD
plays "falls less / rises when equities fall" role during stress) instead.

hmmlearn is not installed in this environment (would require
--break-system-packages); a compact univariate 3-state Gaussian HMM
(Baum-Welch EM + Viterbi/forward-filter) is implemented here instead --
short enough that adding a new dependency for a one-off research script
isn't worth it.

Research-only. Does not touch production DB, pointers, or the daily
pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit  # noqa: E402

DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/hmm_regime_rotation_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/hmm_regime_rotation_shadow.md"

TICKERS = {"equity": "0050.TW", "bond": "00679B.TWO", "inverse": "00632R.TW"}
N_STATES = 3
N_SPLITS = 5
PURGE_DAYS = 1  # 1-day execution lag matches the paper's protocol
MIN_TRAIN_SIZE = 250
EM_MAX_ITER = 100
EM_TOL = 1e-6
N_EM_RESTARTS = 5


def load_returns() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        frames = {}
        for name, ticker in TICKERS.items():
            rows = con.execute(
                "SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]
            ).fetchall()
            df = pd.DataFrame(rows, columns=["dt", "close"]).set_index("dt")
            frames[name] = df["close"].astype(float)
    finally:
        con.close()
    prices = pd.DataFrame(frames).dropna()
    returns = np.log(prices / prices.shift(1)).dropna()
    return returns


class GaussianHMM3:
    """Compact univariate 3-state Gaussian HMM (Baum-Welch EM + forward filter)."""

    def __init__(self, n_states: int = N_STATES, seed: int = 0) -> None:
        self.n_states = n_states
        self.rng = np.random.default_rng(seed)
        self.means: np.ndarray | None = None
        self.stds: np.ndarray | None = None
        self.trans: np.ndarray | None = None
        self.start: np.ndarray | None = None
        self.loglik: float = -np.inf

    def _emission(self, x: np.ndarray) -> np.ndarray:
        # (T, K) Gaussian densities
        return np.stack(
            [
                (1.0 / (self.stds[k] * np.sqrt(2 * np.pi)))
                * np.exp(-0.5 * ((x - self.means[k]) / self.stds[k]) ** 2)
                for k in range(self.n_states)
            ],
            axis=1,
        )

    def _forward_backward(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        t_len = len(x)
        emis = self._emission(x) + 1e-300
        alpha = np.zeros((t_len, self.n_states))
        c = np.zeros(t_len)
        alpha[0] = self.start * emis[0]
        c[0] = alpha[0].sum()
        alpha[0] /= c[0]
        for t in range(1, t_len):
            alpha[t] = (alpha[t - 1] @ self.trans) * emis[t]
            c[t] = alpha[t].sum()
            alpha[t] /= c[t]
        beta = np.zeros((t_len, self.n_states))
        beta[-1] = 1.0
        for t in range(t_len - 2, -1, -1):
            beta[t] = (self.trans @ (emis[t + 1] * beta[t + 1])) / c[t + 1]
        loglik = np.sum(np.log(c))
        return alpha, beta, emis, loglik

    def fit(self, x: np.ndarray) -> "GaussianHMM3":
        best = None
        for restart in range(N_EM_RESTARTS):
            rng = np.random.default_rng(restart * 97 + 1)
            order = np.argsort(rng.permutation(len(x))[: self.n_states])
            self.means = np.quantile(x, rng.uniform(0.1, 0.9, self.n_states)).astype(float)
            self.means.sort()
            self.stds = np.full(self.n_states, x.std() + 1e-9)
            self.trans = np.full((self.n_states, self.n_states), 0.05)
            np.fill_diagonal(self.trans, 0.9)
            self.trans /= self.trans.sum(axis=1, keepdims=True)
            self.start = np.full(self.n_states, 1.0 / self.n_states)

            prev_ll = -np.inf
            for _it in range(EM_MAX_ITER):
                alpha, beta, emis, ll = self._forward_backward(x)
                gamma = alpha * beta
                gamma /= gamma.sum(axis=1, keepdims=True)
                xi_sum = np.zeros((self.n_states, self.n_states))
                for t in range(len(x) - 1):
                    num = (alpha[t][:, None] * self.trans) * (emis[t + 1] * beta[t + 1])[None, :]
                    denom = num.sum()
                    if denom > 0:
                        xi_sum += num / denom
                self.start = gamma[0]
                row_sums = gamma[:-1].sum(axis=0)
                self.trans = xi_sum / np.maximum(row_sums[:, None], 1e-12)
                self.trans /= self.trans.sum(axis=1, keepdims=True)
                w = gamma.sum(axis=0)
                self.means = (gamma * x[:, None]).sum(axis=0) / np.maximum(w, 1e-12)
                var = (gamma * (x[:, None] - self.means[None, :]) ** 2).sum(axis=0) / np.maximum(w, 1e-12)
                self.stds = np.sqrt(np.maximum(var, 1e-10))
                if abs(ll - prev_ll) < EM_TOL * abs(prev_ll if prev_ll != -np.inf else 1.0):
                    prev_ll = ll
                    break
                prev_ll = ll
            if best is None or prev_ll > best[0]:
                best = (prev_ll, self.means.copy(), self.stds.copy(), self.trans.copy(), self.start.copy())
        self.loglik, self.means, self.stds, self.trans, self.start = best
        order = np.argsort(self.means)
        self.means, self.stds = self.means[order], self.stds[order]
        self.trans = self.trans[order][:, order]
        self.start = self.start[order]
        return self

    def filter_states(self, x: np.ndarray) -> np.ndarray:
        """Causal (online) filtered state probabilities -- no smoothing,
        no look-ahead: state estimate at t uses only x[0..t]."""
        emis = self._emission(x) + 1e-300
        alpha = np.zeros((len(x), self.n_states))
        alpha[0] = self.start * emis[0]
        alpha[0] /= alpha[0].sum()
        for t in range(1, len(x)):
            alpha[t] = (alpha[t - 1] @ self.trans) * emis[t]
            alpha[t] /= alpha[t].sum()
        return alpha.argmax(axis=1)


def run_fold(returns: pd.DataFrame, train_idx: np.ndarray, test_idx: np.ndarray) -> dict[str, Any]:
    regime_series = returns["equity"].values.astype(float) * 100.0  # % units, matches paper's Table 2 scale
    train_x = regime_series[train_idx]

    hmm = GaussianHMM3().fit(train_x)
    train_states = hmm.filter_states(train_x)

    state_top1 = {}
    for s in range(N_STATES):
        mask = train_states == s
        if mask.sum() < 5:
            state_top1[s] = "equity"  # fallback: default to equity if a state barely occurs in-sample
            continue
        means = {name: returns[name].values[train_idx][mask].mean() for name in TICKERS}
        state_top1[s] = max(means, key=means.get)

    # causal filter over train+test jointly (test states use only data up to
    # and including that day -- no future leakage), but re-normalize test
    # window index for filtering starting from full history each fold
    full_idx = np.concatenate([train_idx, test_idx])
    full_x = regime_series[full_idx]
    full_states = hmm.filter_states(full_x)
    test_states = full_states[len(train_idx):]

    test_dates = returns.index[test_idx]
    daily_returns = []
    ew_daily_returns = []
    bh_daily_returns = []
    allocations = []
    for i, s in enumerate(test_states):
        asset = state_top1[int(s)]
        # 1-day execution lag: regime detected using info through day i is
        # acted on for day i+1's return
        if i + 1 >= len(test_idx):
            continue
        day_idx = test_idx[i + 1]
        r = returns[asset].values[day_idx]
        daily_returns.append(float(r))
        ew_daily_returns.append(float(returns[["equity", "bond", "inverse"]].values[day_idx].mean()))
        bh_daily_returns.append(float(returns["equity"].values[day_idx]))
        allocations.append(asset)

    arr = np.array(daily_returns)
    sharpe = float(arr.mean() / arr.std() * np.sqrt(252)) if len(arr) > 1 and arr.std() > 0 else 0.0
    cum = np.cumsum(arr)
    running_max = np.maximum.accumulate(cum) if len(cum) else np.array([0.0])
    mdd = float((running_max - cum).max()) if len(cum) else 0.0
    ar = float(arr.mean() * 252) if len(arr) else 0.0

    return {
        "train_dates": [str(returns.index[train_idx[0]]), str(returns.index[train_idx[-1]])],
        "test_dates": [str(test_dates[0]), str(test_dates[-1])],
        "state_top1_assets": state_top1,
        "state_means_train": {
            s: {name: float(returns[name].values[train_idx][train_states == s].mean()) if (train_states == s).sum() else None for name in TICKERS}
            for s in range(N_STATES)
        },
        "n_test_days": len(daily_returns),
        "annual_return": ar,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "asset_allocation_frac": {a: allocations.count(a) / len(allocations) for a in set(allocations)} if allocations else {},
        "daily_returns": daily_returns,
        "ew_daily_returns": ew_daily_returns,
        "bh_daily_returns": bh_daily_returns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    print("Loading Taiwan ETF returns (0050/00679B/00632R)...", flush=True)
    returns = load_returns()
    print(f"n_days={len(returns)}, range={returns.index[0]}..{returns.index[-1]}", flush=True)

    splitter = PurgedWalkForwardSplit(n_splits=N_SPLITS, purge=PURGE_DAYS, min_train_size=MIN_TRAIN_SIZE)
    n = len(returns)
    fold_results = []
    for fold_i, (train_idx, test_idx) in enumerate(splitter.split(np.arange(n))):
        print(f"fold {fold_i + 1}/{N_SPLITS}: fitting HMM on {len(train_idx)} train days...", flush=True)
        result = run_fold(returns, train_idx, test_idx)
        result["fold"] = fold_i
        print(
            f"  fold {fold_i + 1}: test {result['test_dates']}, "
            f"AR={result['annual_return']:.3f}, Sharpe={result['sharpe']:.3f}, "
            f"alloc={result['asset_allocation_frac']}",
            flush=True,
        )
        fold_results.append(result)

    def _pooled_stats(key: str) -> dict[str, float]:
        pooled = np.concatenate([np.array(f[key]) for f in fold_results])
        sharpe = float(pooled.mean() / pooled.std() * np.sqrt(252)) if pooled.std() > 0 else 0.0
        ar = float(pooled.mean() * 252)
        cum = np.cumsum(pooled)
        running_max = np.maximum.accumulate(cum)
        mdd = float((running_max - cum).max())
        return {"annual_return": ar, "sharpe": sharpe, "max_drawdown": mdd, "n_test_days": len(pooled)}

    overall = _pooled_stats("daily_returns")
    ew_overall = _pooled_stats("ew_daily_returns")
    bh_overall = _pooled_stats("bh_daily_returns")

    output = {
        "universe": TICKERS,
        "n_splits": N_SPLITS,
        "purge_days": PURGE_DAYS,
        "folds": fold_results,
        "overall": {
            "hmm_regime_top1": overall,
            "equal_weight_reference": ew_overall,
            "buy_hold_0050_reference": bh_overall,
        },
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    md = [
        "# HMM Regime-Conditioned Top-1 Rotation Shadow (arXiv:2605.27848 mechanism test)",
        "",
        f"Universe: 0050 (equity) / 00679B (bond) / 00632R (inverse, GLD-role substitute). "
        f"{N_SPLITS}-fold purged walk-forward, {PURGE_DAYS}-day execution lag, 3-state Gaussian HMM "
        f"(Baum-Welch EM, {N_EM_RESTARTS} restarts) fit fresh on each fold's train-only data.",
        "",
        "| fold | test window | Top-1 by state | annual return | Sharpe | max drawdown |",
        "|---|---|---|---|---|---|",
    ]
    for f in fold_results:
        md.append(
            f"| {f['fold'] + 1} | {f['test_dates'][0][:10]}..{f['test_dates'][1][:10]} | "
            f"{f['state_top1_assets']} | {f['annual_return']:.3f} | {f['sharpe']:.3f} | {f['max_drawdown']:.3f} |"
        )
    md += [
        "",
        "| strategy | annual return | Sharpe | max drawdown | n test days |",
        "|---|---|---|---|---|",
        f"| HMM regime Top-1 | {overall['annual_return']:.3f} | {overall['sharpe']:.3f} | {overall['max_drawdown']:.3f} | {overall['n_test_days']} |",
        f"| Equal-weight (0050/00679B/00632R) | {ew_overall['annual_return']:.3f} | {ew_overall['sharpe']:.3f} | {ew_overall['max_drawdown']:.3f} | {ew_overall['n_test_days']} |",
        f"| Buy & hold 0050 | {bh_overall['annual_return']:.3f} | {bh_overall['sharpe']:.3f} | {bh_overall['max_drawdown']:.3f} | {bh_overall['n_test_days']} |",
        "",
        "All three rows evaluated on the exact same pooled OOS test days for a fair comparison.",
        "",
    ]
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nWritten to {args.output} and {args.output_md}", flush=True)


if __name__ == "__main__":
    main()
