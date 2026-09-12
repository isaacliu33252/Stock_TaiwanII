#!/usr/bin/env python3
"""MAPLE-lite: scoped-down replication of arXiv:2607.24131 ("MAPLE:
Efficient and Diverse Multi-Alpha Generation for Portfolio Construction",
SinoPac Holdings + NCCU) on the 0050 top15 stock pool, as a follow-up to the
2026-07-02 StockMixer+ATFNet shadow experiment
(`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`), whose own verdict
was "noisy/inconclusive IC, do not invest more compute without proper
walk-forward validation first" (see
project_stockmixer_atfnet_0050_20260702 memory).

This is intentionally NOT a full reproduction of MAPLE's architecture --
kept to a GRU temporal encoder (one of the 5 backbones MAPLE was validated
against, with the largest reported relative gain: +23% SR, +43% CR) instead
of their default 2-layer causal Transformer, and with fixed (not learnable)
extreme-rank sharpness/margin parameters to reduce moving pieces for a first
pass. The three core, portable ideas ARE implemented faithfully:

1. A unified prediction head that sums an intra-stock MLP path and an
   inter-stock multi-head-attention path (one head per alpha) directly in
   prediction space (Sec 3.1, Eq. 1-5).
2. An extreme-rank weighted listwise Spearman ranking loss (Sec 3.2, Eq. 7,
   Algorithm 1) so each alpha's gradient concentrates on the stocks that
   would actually be selected into a top-k portfolio.
3. A diversity regularizer explicitly penalizing pairwise |correlation|
   across the N_alpha predicted rankings (Sec 3.3, Eq. 8-9).

Evaluated via purged walk-forward (`group_a_plus.validation.purged_walk_forward
.PurgedWalkForwardSplit`) comparing N_alpha=1 (single-alpha baseline) against
N_alpha=8 (diversity-regularized ensemble), reporting rank IC, individual-vs-
ensemble Sharpe (diversification gain), and alpha correlation -- the same
diagnostics MAPLE's own Table 3/4 use -- rather than only a headline
portfolio return number.

Research-only. Does not touch production DB, pointers, or the daily pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit  # noqa: E402

CACHE_PATH = PROJECT_ROOT / "results" / "stockmixer_atfnet_0050top15_ohlcv_cache.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "maple_lite_0050top15_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "maple_lite_0050top15_shadow.md"

LOOKBACK = 16
HORIZON = 5
TOP_K = 5
HIDDEN_DIM = 32
N_SPLITS = 5
EPOCHS_PER_FOLD = 30
LR = 3e-3
DIVERSITY_LAMBDA = 0.1
EXTREME_XI = 4.0
EXTREME_GAMMA = 0.3


def load_panel(cache_path: Path) -> tuple[pd.DataFrame, list[str]]:
    raw = pd.read_parquet(cache_path)
    tickers = sorted({t for t, _ in raw.columns})
    # BUG FIX (20260812): use dividend-adjusted close when the cache has it.
    # Raw Close on dividend-heavy names (e.g. 2317/2454/2881/2882/2891)
    # produces fake ex-dividend-day return crashes -- the same bug already
    # found and fixed in the 2026-07-02 StockMixer+ATFNet shadow
    # (project_stockmixer_atfnet_0050_20260702) but not carried over here.
    frames = []
    for ticker in tickers:
        price_field = "Adj Close" if (ticker, "Adj Close") in raw.columns else "Close"
        close = raw[(ticker, price_field)].astype(float)
        volume = raw[(ticker, "Volume")].astype(float)
        ret_1d = close.pct_change()
        feat = pd.DataFrame(
            {
                "ret_1d": ret_1d,
                "ret_5d": close.pct_change(5),
                "ret_10d": close.pct_change(10),
                "ret_20d": close.pct_change(20),
                "ma_gap_5": close / close.rolling(5).mean() - 1.0,
                "ma_gap_20": close / close.rolling(20).mean() - 1.0,
                "ma_gap_60": close / close.rolling(60).mean() - 1.0,
                "vol_20d": ret_1d.rolling(20).std(),
                "volume_z_20d": (volume - volume.rolling(20).mean()) / (volume.rolling(20).std() + 1e-9),
            }
        )
        feat["forward_return"] = close.pct_change(HORIZON).shift(-HORIZON)
        feat["next_return"] = close.shift(-1) / close - 1.0
        feat["ticker"] = ticker
        feat["date"] = raw.index
        frames.append(feat)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["ret_1d", "ma_gap_60", "vol_20d"])
    return panel, tickers


FEATURE_COLS = ["ret_1d", "ret_5d", "ret_10d", "ret_20d", "ma_gap_5", "ma_gap_20", "ma_gap_60", "vol_20d", "volume_z_20d"]


def build_tensors(panel: pd.DataFrame, tickers: list[str]) -> dict[str, Any]:
    """Wide (date x ticker x feature) tensor with NaN for missing days, plus
    date/ticker index arrays for slicing by fold."""
    panel = panel.copy()
    panel[FEATURE_COLS] = panel[FEATURE_COLS].fillna(0.0)
    dates = sorted(panel["date"].unique())
    date_idx = {d: i for i, d in enumerate(dates)}
    ticker_idx = {t: i for i, t in enumerate(tickers)}

    n_dates, n_tickers, n_feat = len(dates), len(tickers), len(FEATURE_COLS)
    feat_arr = np.full((n_dates, n_tickers, n_feat), np.nan, dtype=np.float32)
    fwd_arr = np.full((n_dates, n_tickers), np.nan, dtype=np.float32)
    next_arr = np.full((n_dates, n_tickers), np.nan, dtype=np.float32)

    for row in panel.itertuples(index=False):
        di, ti = date_idx[row.date], ticker_idx[row.ticker]
        feat_arr[di, ti, :] = [getattr(row, c) for c in FEATURE_COLS]
        fwd_arr[di, ti] = row.forward_return
        next_arr[di, ti] = row.next_return

    return {"dates": dates, "tickers": tickers, "features": feat_arr, "forward_return": fwd_arr, "next_return": next_arr}


class MapleLite(nn.Module):
    def __init__(self, n_features: int, hidden_dim: int, n_alpha: int):
        super().__init__()
        self.n_alpha = n_alpha
        self.gru = nn.GRU(n_features, hidden_dim, batch_first=True)
        self.norm = nn.LayerNorm(hidden_dim)

        intra_hidden = max(4, hidden_dim * max(1, n_alpha) // 8)
        self.intra = nn.Sequential(
            nn.Linear(hidden_dim, intra_hidden),
            nn.ReLU(),
            nn.Linear(intra_hidden, n_alpha),
        )

        emb_dim = max(n_alpha, 2 * hidden_dim * max(1, n_alpha) // 8)
        emb_dim = emb_dim - (emb_dim % n_alpha) if emb_dim % n_alpha else emb_dim
        self.d_k = max(1, emb_dim // n_alpha)
        self.emb_dim = self.d_k * n_alpha
        self.w_q = nn.Linear(hidden_dim, self.emb_dim, bias=False)
        self.w_k = nn.Linear(hidden_dim, self.emb_dim, bias=False)
        self.w_v = nn.Linear(hidden_dim, n_alpha, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (S, L, F) -- one day's cross-section, S stocks x lookback x features
        _, h_n = self.gru(x)
        h = h_n[-1]  # (S, D)
        h_tilde = self.norm(h)

        y_intra = self.intra(h_tilde)  # (S, N_alpha)

        q = self.w_q(h_tilde).view(-1, self.n_alpha, self.d_k)  # (S, N_alpha, d_k)
        k = self.w_k(h_tilde).view(-1, self.n_alpha, self.d_k)
        v = self.w_v(h_tilde)  # (S, N_alpha)

        scores = torch.einsum("snd,tnd->nst", q, k) / (self.d_k ** 0.5)  # (N_alpha, S, S)
        attn = torch.softmax(scores, dim=-1)
        y_inter = torch.einsum("nst,tn->sn", attn, v)  # (S, N_alpha)

        return y_intra + y_inter


def rank_surrogate(x: torch.Tensor) -> torch.Tensor:
    return torch.sigmoid(1.83 * (x - x.mean()) / (2 * x.std() + 1e-9))


def normalize_phi(phi: torch.Tensor) -> torch.Tensor:
    phi = phi - phi.mean()
    return phi / (phi.norm() + 1e-9)


def maple_loss(y_hat: torch.Tensor, y: torch.Tensor, diversity_lambda: float) -> torch.Tensor:
    # y_hat: (S, N_alpha), y: (S,)
    n_alpha = y_hat.shape[1]
    s = y_hat.shape[0]
    phi_y = normalize_phi(rank_surrogate(y))

    true_rank = torch.argsort(torch.argsort(-y)).float()  # 0 = top
    center = (s - 1) / 2.0
    d = torch.clamp(center - true_rank, min=0.0)
    delta = EXTREME_GAMMA * center
    z = torch.sigmoid(EXTREME_XI * (d - delta))
    v = z / (z.max() + 1e-9)
    coverage = 1.0 + 2 * delta / s

    phi_yhat = torch.stack([normalize_phi(rank_surrogate(y_hat[:, i])) for i in range(n_alpha)], dim=1)  # (S, N_alpha)

    spearman = (phi_yhat * phi_y.unsqueeze(1)).sum(dim=0).mean()
    extreme = coverage * (phi_yhat * phi_y.unsqueeze(1) * v.unsqueeze(1)).sum(dim=0).mean()

    if n_alpha > 1:
        corr_matrix = torch.corrcoef(phi_yhat.T)
        off_diag = corr_matrix - torch.eye(n_alpha, device=y_hat.device)
        diversity = off_diag.abs().sum() / (n_alpha * (n_alpha - 1))
    else:
        diversity = torch.tensor(0.0, device=y_hat.device)

    loss = -(spearman + extreme) + diversity_lambda * diversity
    return loss, diversity.item()


def train_fold(
    tensors: dict[str, Any], train_idx: np.ndarray, n_alpha: int, seed: int
) -> MapleLite:
    # BUG FIX (20260811): torch.manual_seed alone does not control
    # np.random.shuffle below -- runs with the "same" seed were not actually
    # reproducible. A dedicated Generator avoids perturbing global numpy
    # random state shared with other folds/configs.
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_features = len(FEATURE_COLS)
    model = MapleLite(n_features, HIDDEN_DIM, n_alpha)
    opt = torch.optim.Adam(model.parameters(), lr=LR)

    features = tensors["features"]
    forward_return = tensors["forward_return"]
    train_days = [d for d in train_idx if d >= LOOKBACK and not np.all(np.isnan(forward_return[d]))]

    for _epoch in range(EPOCHS_PER_FOLD):
        rng.shuffle(train_days)
        for d in train_days:
            window = features[d - LOOKBACK + 1 : d + 1]  # (L, S, F)
            y = forward_return[d]
            # BUG FIX (20260812): validity was label-only. A stock whose
            # forward_return is defined but whose lookback FEATURE window
            # contains NaN (e.g. a genuine price-history gap, such as
            # 7769.TW's early-2025 gap in the full50 universe) was still
            # fed into the GRU, producing NaN in that stock's embedding.
            # MapleLite's inter-stock attention path computes pairwise
            # dot products across every included stock, so one NaN
            # embedding poisons the whole day's y_hat via softmax, loss
            # goes NaN, and opt.step() permanently corrupts the model for
            # the rest of training. Now excludes any stock whose window
            # has NaN, not just NaN-labeled stocks.
            window_valid = ~np.isnan(window).any(axis=(0, 2))
            valid = ~np.isnan(y) & window_valid
            if valid.sum() < TOP_K + 2:
                continue
            x = torch.from_numpy(window[:, valid, :]).permute(1, 0, 2).float()  # (S, L, F)
            y_t = torch.from_numpy(y[valid]).float()

            y_hat = model(x)
            loss, _ = maple_loss(y_hat, y_t, DIVERSITY_LAMBDA if n_alpha > 1 else 0.0)
            opt.zero_grad()
            loss.backward()
            opt.step()

    return model


TX_COST_ROUND_TRIP = 0.005  # ~0.5%: ~0.1425% commission/side + 0.3% TW sell tax, rounded up


def evaluate_fold(model: MapleLite, tensors: dict[str, Any], test_idx: np.ndarray, n_alpha: int) -> dict[str, Any]:
    features = tensors["features"]
    forward_return = tensors["forward_return"]
    next_return = tensors["next_return"]
    tickers = np.array(tensors["tickers"])

    ic_list = []
    alpha_ic_lists = [[] for _ in range(n_alpha)]
    ensemble_daily_returns = []
    ensemble_daily_returns_net = []
    alpha_daily_returns = [[] for _ in range(n_alpha)]
    alpha_corrs = []
    turnovers = []
    prev_selection: set[str] | None = None

    model.eval()
    with torch.no_grad():
        for d in test_idx:
            if d < LOOKBACK or d + 1 >= len(tickers) * 0 + features.shape[0]:
                continue
            y = forward_return[d]
            window = features[d - LOOKBACK + 1 : d + 1]
            # BUG FIX (20260812): see matching fix in train_fold -- validity
            # must also require a NaN-free feature window, not just a
            # defined label.
            window_valid = ~np.isnan(window).any(axis=(0, 2))
            valid = ~np.isnan(y) & window_valid
            if valid.sum() < TOP_K + 2:
                continue
            x = torch.from_numpy(window[:, valid, :]).permute(1, 0, 2).float()
            y_hat = model(x).numpy()  # (S_valid, N_alpha)
            y_valid = y[valid]

            ensemble_score = y_hat.mean(axis=1)
            ic = pd.Series(ensemble_score).corr(pd.Series(y_valid), method="spearman")
            if not np.isnan(ic):
                ic_list.append(ic)

            for i in range(n_alpha):
                a_ic = pd.Series(y_hat[:, i]).corr(pd.Series(y_valid), method="spearman")
                if not np.isnan(a_ic):
                    alpha_ic_lists[i].append(a_ic)

            if n_alpha > 1:
                corr = np.corrcoef(y_hat.T)
                off = corr[~np.eye(n_alpha, dtype=bool)]
                alpha_corrs.append(np.nanmean(np.abs(off)))

            nxt = next_return[d]
            nxt_valid = nxt[valid]
            valid_next = ~np.isnan(nxt_valid)
            if valid_next.sum() < TOP_K:
                continue

            tickers_valid_next = tickers[valid][valid_next]
            ens_rank = np.argsort(-ensemble_score[valid_next])[:TOP_K]
            ensemble_daily_returns.append(float(np.mean(nxt_valid[valid_next][ens_rank])))

            current_selection = set(tickers_valid_next[ens_rank].tolist())
            if prev_selection is None:
                turnover = 1.0  # first day: treat as a full initial buy-in
            else:
                changed = len(current_selection - prev_selection)
                turnover = changed / TOP_K
            turnovers.append(turnover)
            cost = turnover * TX_COST_ROUND_TRIP
            ensemble_daily_returns_net.append(ensemble_daily_returns[-1] - cost)
            prev_selection = current_selection

            for i in range(n_alpha):
                a_rank = np.argsort(-y_hat[valid_next, i])[:TOP_K]
                alpha_daily_returns[i].append(float(np.mean(nxt_valid[valid_next][a_rank])))

    def sharpe(returns: list[float]) -> float:
        arr = np.array(returns)
        if len(arr) < 2 or arr.std() == 0:
            return 0.0
        return float(arr.mean() / arr.std() * np.sqrt(252))

    return {
        "mean_ic": float(np.mean(ic_list)) if ic_list else None,
        "ensemble_sharpe": sharpe(ensemble_daily_returns),
        "ensemble_sharpe_net": sharpe(ensemble_daily_returns_net),
        "individual_alpha_sharpe": [sharpe(r) for r in alpha_daily_returns],
        "mean_individual_alpha_sharpe": float(np.mean([sharpe(r) for r in alpha_daily_returns])) if n_alpha else None,
        "mean_alpha_correlation": float(np.mean(alpha_corrs)) if alpha_corrs else None,
        "mean_turnover": float(np.mean(turnovers)) if turnovers else None,
        "n_test_days": len(ensemble_daily_returns),
        "ensemble_daily_returns": ensemble_daily_returns,
        "ensemble_daily_returns_net": ensemble_daily_returns_net,
    }


def run(n_alpha: int, tensors: dict[str, Any], seed: int, job_progress: str = "") -> dict[str, Any]:
    n_dates = tensors["features"].shape[0]
    splitter = PurgedWalkForwardSplit(n_splits=N_SPLITS, purge=HORIZON, min_train_size=LOOKBACK + 60)
    fold_results = []
    for fold_i, (train_idx, test_idx) in enumerate(splitter.split(np.arange(n_dates))):
        model = train_fold(tensors, train_idx, n_alpha, seed=seed + fold_i)
        result = evaluate_fold(model, tensors, test_idx, n_alpha)
        result["fold"] = fold_i
        result["train_dates"] = [str(tensors["dates"][train_idx[0]]), str(tensors["dates"][train_idx[-1]])]
        result["test_dates"] = [str(tensors["dates"][test_idx[0]]), str(tensors["dates"][test_idx[-1]])]
        fold_pct = (fold_i + 1) / N_SPLITS
        print(
            f"{job_progress} fold {fold_i + 1}/{N_SPLITS} ({fold_pct:.0%}): {result['test_dates']} "
            f"IC={result['mean_ic']}, ens_sharpe={result['ensemble_sharpe']:.3f}",
            flush=True,
        )
        fold_results.append(result)

    def _pooled_sharpe(key: str) -> float:
        pooled = [r for fold in fold_results for r in fold[key]]
        a = np.array(pooled)
        return float(a.mean() / a.std() * np.sqrt(252)) if len(a) > 1 and a.std() > 0 else 0.0

    overall_sharpe = _pooled_sharpe("ensemble_daily_returns")
    overall_sharpe_net = _pooled_sharpe("ensemble_daily_returns_net")
    mean_ic = float(np.mean([f["mean_ic"] for f in fold_results if f["mean_ic"] is not None]))
    mean_alpha_corr = np.mean([f["mean_alpha_correlation"] for f in fold_results if f["mean_alpha_correlation"] is not None]) if n_alpha > 1 else None
    mean_individual_sharpe = np.mean([f["mean_individual_alpha_sharpe"] for f in fold_results if f["mean_individual_alpha_sharpe"] is not None])
    mean_turnover = np.mean([f["mean_turnover"] for f in fold_results if f["mean_turnover"] is not None])

    return {
        "n_alpha": n_alpha,
        "seed": seed,
        "overall_ensemble_sharpe": overall_sharpe,
        "overall_ensemble_sharpe_net": overall_sharpe_net,
        "mean_ic": mean_ic,
        "mean_individual_alpha_sharpe": float(mean_individual_sharpe),
        "diversification_gain": overall_sharpe - float(mean_individual_sharpe),
        "mean_alpha_correlation": float(mean_alpha_corr) if mean_alpha_corr is not None else None,
        "mean_turnover": float(mean_turnover),
        "folds": fold_results,
    }


def _agg(runs: list[dict[str, Any]], key: str) -> dict[str, float]:
    vals = [r[key] for r in runs if r.get(key) is not None]
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals))} if vals else {"mean": None, "std": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default=str(CACHE_PATH), help="ticker universe OHLCV cache parquet")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-seeds", type=int, default=3, help="number of seeds to run for EACH config (fair comparison)")
    parser.add_argument("--epochs", type=int, default=EPOCHS_PER_FOLD)
    args = parser.parse_args()
    globals()["EPOCHS_PER_FOLD"] = args.epochs
    cache_path = Path(args.cache)

    print(f"Loading panel from {cache_path.name}...", flush=True)
    panel, tickers = load_panel(cache_path)
    print(f"tickers={len(tickers)}, panel rows={len(panel)}", flush=True)
    tensors = build_tensors(panel, tickers)
    print(f"n_dates={len(tensors['dates'])}", flush=True)

    seeds = [args.seed + i * 1000 for i in range(args.n_seeds)]
    total_jobs = 2 * len(seeds)  # 2 configs (n_alpha=1, n_alpha=8) x n_seeds
    job_i = 0

    r1_runs, r8_runs = [], []
    for n_alpha, bucket in ((1, r1_runs), (8, r8_runs)):
        for seed in seeds:
            job_i += 1
            progress = f"[job {job_i}/{total_jobs} ({job_i / total_jobs:.0%})] n_alpha={n_alpha} seed={seed}"
            print(f"\n=== {progress} ===", flush=True)
            bucket.append(run(n_alpha, tensors, seed=seed, job_progress=progress))

    results = {
        "seeds": seeds,
        "n_alpha_1_runs": r1_runs,
        "n_alpha_8_runs": r8_runs,
        "n_alpha_1_aggregate": {
            "mean_ic": _agg(r1_runs, "mean_ic"),
            "overall_ensemble_sharpe": _agg(r1_runs, "overall_ensemble_sharpe"),
            "overall_ensemble_sharpe_net": _agg(r1_runs, "overall_ensemble_sharpe_net"),
            "mean_turnover": _agg(r1_runs, "mean_turnover"),
        },
        "n_alpha_8_aggregate": {
            "mean_ic": _agg(r8_runs, "mean_ic"),
            "overall_ensemble_sharpe": _agg(r8_runs, "overall_ensemble_sharpe"),
            "overall_ensemble_sharpe_net": _agg(r8_runs, "overall_ensemble_sharpe_net"),
            "diversification_gain": _agg(r8_runs, "diversification_gain"),
            "mean_alpha_correlation": _agg(r8_runs, "mean_alpha_correlation"),
            "mean_turnover": _agg(r8_runs, "mean_turnover"),
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    agg1 = results["n_alpha_1_aggregate"]
    agg8 = results["n_alpha_8_aggregate"]

    try:
        from scipy import stats as _stats

        ic1 = [r["mean_ic"] for r in r1_runs]
        ic8 = [r["mean_ic"] for r in r8_runs]
        ic_ttest = _stats.ttest_ind(ic8, ic1)
        net1 = [r["overall_ensemble_sharpe_net"] for r in r1_runs]
        net8 = [r["overall_ensemble_sharpe_net"] for r in r8_runs]
        net_ttest = _stats.ttest_ind(net8, net1)
        stats_line = (
            f"- Independent-samples t-test (N_alpha=8 vs N_alpha=1, {args.n_seeds} seeds each): "
            f"IC diff p={ic_ttest.pvalue:.3f}, net Sharpe diff p={net_ttest.pvalue:.3f}"
        )
    except Exception as exc:  # noqa: BLE001
        stats_line = f"- Significance test unavailable ({exc})"

    md = [
        "# MAPLE-lite 0050-Top15 Shadow Evaluation (research diagnostic)",
        "",
        f"- Universe: {len(tickers)} tickers (`{cache_path.name}`, cached {tensors['dates'][0].date()}..{tensors['dates'][-1].date()})",
        f"- Horizon: {HORIZON}d forward return, lookback={LOOKBACK}d, top_k={TOP_K}, {N_SPLITS}-fold purged walk-forward",
        f"- Transaction cost: {TX_COST_ROUND_TRIP:.2%} per name replaced in the top-{TOP_K} basket "
        "(~0.1425% commission/side + 0.3% TW sell tax)",
        f"- Both configs run across the same {args.n_seeds} seeds ({seeds}) for a fair comparison "
        "(2026-08-11 fix: previously N_alpha=1 used only 1 seed and np.random.shuffle wasn't seeded at all)",
        stats_line,
        "",
        "| config | mean rank IC | ensemble Sharpe (gross) | ensemble Sharpe (net of cost) | mean turnover | diversification gain | mean alpha correlation |",
        "|---|---|---|---|---|---|---|",
        f"| N_alpha=1 ({args.n_seeds}-seed mean±std) | {agg1['mean_ic']['mean']:.4f}±{agg1['mean_ic']['std']:.4f} | "
        f"{agg1['overall_ensemble_sharpe']['mean']:.3f}±{agg1['overall_ensemble_sharpe']['std']:.3f} | "
        f"{agg1['overall_ensemble_sharpe_net']['mean']:.3f}±{agg1['overall_ensemble_sharpe_net']['std']:.3f} | "
        f"{agg1['mean_turnover']['mean']:.2f}±{agg1['mean_turnover']['std']:.2f} | n/a | n/a |",
        f"| N_alpha=8 ({args.n_seeds}-seed mean±std) | {agg8['mean_ic']['mean']:.4f}±{agg8['mean_ic']['std']:.4f} | "
        f"{agg8['overall_ensemble_sharpe']['mean']:.3f}±{agg8['overall_ensemble_sharpe']['std']:.3f} | "
        f"{agg8['overall_ensemble_sharpe_net']['mean']:.3f}±{agg8['overall_ensemble_sharpe_net']['std']:.3f} | "
        f"{agg8['mean_turnover']['mean']:.2f}±{agg8['mean_turnover']['std']:.2f} | "
        f"{agg8['diversification_gain']['mean']:.3f}±{agg8['diversification_gain']['std']:.3f} | "
        f"{agg8['mean_alpha_correlation']['mean']:.3f}±{agg8['mean_alpha_correlation']['std']:.3f} |",
        "",
        "Reference (2026-07-02 shadow, same top15 universe, different model/eval protocol -- not directly comparable, "
        "context only): StockMixer+ATFNet IC=0.0143, single-stock logistic baseline IC=0.0244.",
        "",
    ]
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nWritten to {output} and {args.output_md}")


if __name__ == "__main__":
    main()
