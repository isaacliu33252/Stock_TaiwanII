#!/usr/bin/env python3
"""Evaluate the MFCF/HNN dependence-informed sparse architecture pilot
(arXiv:2608.14323) on 0050.TW volatility forecasting.

Adapts the paper's core architectural claim -- a Maximally Filtered Clique
Forest (MFCF) over feature dependence, mapped to a sparse Homological Neural
Network (HNN), matches a hand-tuned dense MLP's accuracy with far fewer
parameters and better cross-sectional ranking -- to the closest existing
GroupA+ analogue: forecasting 0050.TW future realized (Garman-Klass) variance
from the same 55 technical indicators already computed for the RL policy's
state vector (FinRL/v2/data/technical_indicators.py), instead of a
cross-sectional 94-firm-characteristic US equity panel.

Four forecasts per walk-forward window, all reusing the min_train_rows /
refit_every / rolling_window discipline already used by volatility_forecast.py:

  - base: unmodified production har_rv_walkforward_forecast (frozen)
  - nn3_dense: a fixed hand-tuned 3-hidden-layer MLP (32/16/8, matching GKX
    NN3) on all 55 indicators -- the paper's "hand-tuned dense" baseline
  - hnn_marginal: MFCF-derived sparse HNN on the same 55 indicators
  - hnn_shuffled: same HNN topology/parameter count, features permuted
    across graph nodes (paper's alignment ablation)

Research-only. Single horizon (h=5) to bound walk-forward NN retraining cost
-- ~31 refits x 3 trained networks on CPU. Does not touch target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.v2.data.technical_indicators import TechnicalIndicators
from group_a_plus.integrations.mfcf_hnn_volatility_shadow import (
    DEFAULT_MAX_CLIQUE_SIZE,
    build_hnn_from_correlation,
    train_hnn,
)
from group_a_plus.integrations.risk_sensitive_loss import qlike_loss
from group_a_plus.integrations.volatility_forecast import (
    GK_FLOOR,
    _future_avg_variance,
    garman_klass_variance,
    har_rv_walkforward_forecast,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_mfcf_hnn_volatility_pilot_latest.json"
HORIZON = 5
MIN_TRAIN_ROWS = 250
REFIT_EVERY = 63
ROLLING_WINDOW = 504


class NN3(nn.Module):
    """GKX-style 3-hidden-layer dense MLP (32/16/8), the paper's hand-tuned baseline."""

    def __init__(self, n_in: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 32), nn.LayerNorm(32), nn.ReLU(),
            nn.Linear(32, 16), nn.LayerNorm(16), nn.ReLU(),
            nn.Linear(16, 8), nn.LayerNorm(8), nn.ReLU(),
            nn.Linear(8, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)

    def param_count(self) -> int:
        return int(sum(p.numel() for p in self.parameters() if p.requires_grad))


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt as date, open, high, low, close, volume FROM ohlcv "
            "WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["date"] = pd.to_datetime(rows["date"])
    return rows


def _build_feature_frame(ohlc: pd.DataFrame) -> pd.DataFrame:
    ti = TechnicalIndicators(ohlc)
    df = ti.calculate_all(include_patterns=True)
    feats = [f for f in ti.get_feature_list() if f in df.columns]
    df = df.set_index("date")
    X = df[feats].apply(pd.to_numeric, errors="coerce")
    return X


def _log_r2(actual: pd.Series, forecast: pd.Series) -> float:
    y = np.log(actual.clip(lower=1e-12))
    yhat = np.log(forecast.clip(lower=1e-12))
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _score(actual: pd.Series, forecast: pd.Series, base_loss: pd.Series, mask: pd.Series) -> dict:
    idx = mask & forecast.notna() & actual.notna()
    n = int(idx.sum())
    if n < 20:
        return {"status": "insufficient_data", "n": n}
    loss = qlike_loss(actual[idx], forecast[idx])
    base = base_loss[idx]
    loss_mean = float(loss.mean())
    base_mean = float(base.mean())
    return {
        "n": n,
        "qlike_mean": loss_mean,
        "base_qlike_mean": base_mean,
        "qlike_improvement_pct": (base_mean - loss_mean) / base_mean * 100.0 if base_mean else None,
        "win_rate_vs_base": float((loss.to_numpy() < base.to_numpy()).mean()),
        "r2_log_variance": _log_r2(actual[idx], forecast[idx]),
    }


def evaluate(
    ticker: str, start: str, end: str, *,
    max_clique_size: int, seed: int,
) -> dict:
    ohlc = _load_ohlc(DB_PATH, ticker, start, end)
    gk_variance = garman_klass_variance(ohlc.set_index("date")[["open", "high", "low", "close"]])
    X = _build_feature_frame(ohlc)
    common_index = gk_variance.index.intersection(X.index)
    gk_variance = gk_variance.loc[common_index]
    X = X.loc[common_index]

    target = np.log(_future_avg_variance(gk_variance, HORIZON).clip(lower=GK_FLOOR))
    base_forecast = har_rv_walkforward_forecast(
        gk_variance, horizon=HORIZON, min_train_rows=130, refit_every=21, rolling_window=ROLLING_WINDOW,
    )

    valid_x = X.notna().all(axis=1)
    n = len(gk_variance)

    preds = {name: pd.Series(np.nan, index=gk_variance.index) for name in ("nn3_dense", "hnn_marginal", "hnn_shuffled")}
    param_counts: dict[str, list[int]] = {"nn3_dense": [], "hnn_marginal": [], "hnn_shuffled": []}
    n_refits = 0
    last_fit_idx = -10**9
    t_start = time.time()

    for i in range(n):
        if not bool(valid_x.iloc[i]):
            continue
        train_end = i - HORIZON
        if train_end < MIN_TRAIN_ROWS:
            continue

        if (i - last_fit_idx) >= REFIT_EVERY:
            train_start = max(0, train_end + 1 - ROLLING_WINDOW)
            mask = valid_x.iloc[train_start : train_end + 1] & target.iloc[train_start : train_end + 1].notna()
            train_idx = train_start + np.where(mask.to_numpy())[0]
            if len(train_idx) < MIN_TRAIN_ROWS:
                continue

            x_raw = X.iloc[train_idx].to_numpy(dtype=float)
            y = target.iloc[train_idx].to_numpy(dtype=float).astype(np.float32)
            feat_names = list(X.columns)
            mean = x_raw.mean(axis=0)
            std = x_raw.std(axis=0)
            std[std < 1e-8] = 1.0
            x_std = (x_raw - mean) / std
            corr = np.abs(np.corrcoef(x_std.T))

            hnn, ordered_names = build_hnn_from_correlation(corr, feat_names, max_clique_size=max_clique_size)
            hnn_shuf, shuf_names = build_hnn_from_correlation(
                corr, feat_names, max_clique_size=max_clique_size, shuffle_seed=seed,
            )
            nn3 = NN3(n_in=len(feat_names))

            hnn_col_idx = [feat_names.index(nm) for nm in ordered_names]
            shuf_col_idx = [feat_names.index(nm) for nm in shuf_names]

            hnn = train_hnn(hnn, x_std[:, hnn_col_idx], y, seed=seed)
            hnn_shuf = train_hnn(hnn_shuf, x_std[:, shuf_col_idx], y, seed=seed)
            nn3 = train_hnn(nn3, x_std, y, seed=seed)

            param_counts["hnn_marginal"].append(hnn.param_count())
            param_counts["hnn_shuffled"].append(hnn_shuf.param_count())
            param_counts["nn3_dense"].append(nn3.param_count())
            n_refits += 1
            last_fit_idx = i
            print(
                f"  refit @ {gk_variance.index[i].date()} (n_train={len(train_idx)}): "
                f"hnn_params={hnn.param_count()} nn3_params={nn3.param_count()} "
                f"elapsed={time.time() - t_start:.0f}s"
            )

        row_raw = X.iloc[i].to_numpy(dtype=float)
        row_std = (row_raw - mean) / std
        with torch.no_grad():
            x_hnn = torch.tensor(row_std[hnn_col_idx], dtype=torch.float32).unsqueeze(0)
            x_shuf = torch.tensor(row_std[shuf_col_idx], dtype=torch.float32).unsqueeze(0)
            x_nn3 = torch.tensor(row_std, dtype=torch.float32).unsqueeze(0)
            preds["hnn_marginal"].iloc[i] = float(torch.exp(hnn(x_hnn)[0]))
            preds["hnn_shuffled"].iloc[i] = float(torch.exp(hnn_shuf(x_shuf)[0]))
            preds["nn3_dense"].iloc[i] = float(torch.exp(nn3(x_nn3)[0]))

    actual = _future_avg_variance(gk_variance, HORIZON)
    common = base_forecast.notna() & actual.notna()
    for name in preds:
        common = common & preds[name].notna()
    base_loss = qlike_loss(actual[common], base_forecast[common]).reindex(gk_variance.index)

    years = sorted(gk_variance.index.year.unique())
    results: dict[str, Any] = {}
    for name, series in preds.items():
        per_year = {}
        for yr in years:
            year_mask = pd.Series(gk_variance.index.year == yr, index=gk_variance.index) & common
            if int(year_mask.sum()) < 15:
                continue
            per_year[str(yr)] = _score(actual, series, base_loss, year_mask)
        results[name] = {
            "pooled": _score(actual, series, base_loss, common),
            "per_year": per_year,
            "param_count_median": int(np.median(param_counts[name])) if param_counts[name] else None,
            "param_count_min_max": [int(min(param_counts[name])), int(max(param_counts[name]))] if param_counts[name] else None,
        }

    return {
        "ticker": ticker,
        "window": {"start": start, "end": end, "rows": int(n)},
        "horizon": HORIZON,
        "max_clique_size": max_clique_size,
        "refit_every": REFIT_EVERY,
        "rolling_window": ROLLING_WINDOW,
        "n_refits": n_refits,
        "policy": "research_only_no_weight_change",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-08-19")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-clique-size", type=int, default=DEFAULT_MAX_CLIQUE_SIZE)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end, max_clique_size=args.max_clique_size, seed=args.seed)

    print(f"\n=== h={HORIZON} pooled (n_refits={payload['n_refits']}) ===")
    for name, res in payload["results"].items():
        r = res["pooled"]
        if r.get("status") == "insufficient_data":
            print(f"  {name}: insufficient data (n={r['n']})")
            continue
        print(
            f"  {name}: n={r['n']} QLIKE={r['qlike_mean']:.4f} base_QLIKE={r['base_qlike_mean']:.4f} "
            f"improvement={r['qlike_improvement_pct']:.2f}% win_rate={r['win_rate_vs_base']:.3f} "
            f"R2={r['r2_log_variance']:.3f} median_params={res['param_count_median']}"
        )
    print("\nper-year improvement% (base=HAR-RV production):")
    years = sorted({yr for res in payload["results"].values() for yr in res["per_year"]})
    for yr in years:
        line = f"  {yr}:"
        for name, res in payload["results"].items():
            y = res["per_year"].get(yr)
            if y is None or y.get("status") == "insufficient_data":
                continue
            line += f" {name}={y['qlike_improvement_pct']:.1f}%(win={y['win_rate_vs_base']:.2f})"
        print(line)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
