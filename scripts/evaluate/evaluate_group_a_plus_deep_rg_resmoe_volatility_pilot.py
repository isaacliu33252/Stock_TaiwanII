#!/usr/bin/env python3
"""Evaluate a small Deep RG-ResMoE volatility shadow for GroupA+.

Research-only follow-up to arXiv:2608.12251. The production HAR-RV forecast
remains frozen; this script trains a small neural residual mixture-of-experts
on top of that base forecast and compares it with the existing RG-ResMoE-lite
pathway pilot. It never writes target weights.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.rg_resmoe_volatility_gate_shadow import (
    GATE_PERCENTILE_WINDOW,
    rg_resmoe_pathways,
    regime_scalar,
)
from group_a_plus.integrations.volatility_forecast import (
    DEFAULT_ROLLING_WINDOW,
    GK_FLOOR,
    _future_avg_variance,
    garman_klass_variance,
    har_features,
)
from scripts.evaluate.evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot import (
    DB_PATH,
    DEFAULT_HIGH_VOL_GATE_QUANTILE,
    DEFAULT_RESIDUAL_VAR_BUFFER_1PCT,
    DEFAULT_RESIDUAL_VAR_BUFFER_5PCT,
    DEFAULT_RESIDUAL_VAR_MIN_ROWS,
    DEFAULT_RESIDUAL_VAR_WINDOW,
    _load_ohlc,
    _promotion_decision,
    _residual_var_suite,
    _score,
    _var_suite,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_deep_rg_resmoe_volatility_pilot_latest.json"


class TinyResidualMoE(nn.Module):
    def __init__(self, expert_dim: int, gate_dim: int, *, hidden: int, n_experts: int, dropout: float) -> None:
        super().__init__()
        self.experts = nn.Sequential(
            nn.Linear(expert_dim, hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, n_experts),
        )
        self.gate = nn.Sequential(
            nn.Linear(gate_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_experts),
        )

    def forward(self, expert_x: torch.Tensor, gate_x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        expert_out = self.experts(expert_x)
        weights = torch.softmax(self.gate(gate_x), dim=1)
        return (expert_out * weights).sum(dim=1), weights


def _standardize(train: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = train.mean(axis=0)
    std = train.std(axis=0, ddof=0)
    std[std == 0.0] = 1.0
    return (values - mean) / std, mean, std


def _fit_deep_moe(
    x_expert: np.ndarray,
    x_gate: np.ndarray,
    y: np.ndarray,
    *,
    hidden: int,
    n_experts: int,
    dropout: float,
    lr: float,
    weight_decay: float,
    epochs: int,
    patience: int,
    seed: int,
) -> tuple[TinyResidualMoE, dict[str, float]]:
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    n = len(y)
    val_n = max(40, int(n * 0.20))
    val_n = min(val_n, max(1, n // 3))
    train_n = n - val_n

    x_exp_tr, x_exp_mean, x_exp_std = _standardize(x_expert[:train_n], x_expert)
    x_gate_tr, x_gate_mean, x_gate_std = _standardize(x_gate[:train_n], x_gate)
    y_mean = float(y[:train_n].mean())
    y_std = float(y[:train_n].std(ddof=0) or 1.0)
    y_stdized = (y - y_mean) / y_std

    model = TinyResidualMoE(
        x_expert.shape[1],
        x_gate.shape[1],
        hidden=hidden,
        n_experts=n_experts,
        dropout=dropout,
    )
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    x_exp_t = torch.tensor(x_exp_tr, dtype=torch.float32)
    x_gate_t = torch.tensor(x_gate_tr, dtype=torch.float32)
    y_t = torch.tensor(y_stdized, dtype=torch.float32)
    best_state = None
    best_val = float("inf")
    stale = 0
    for _epoch in range(epochs):
        model.train()
        opt.zero_grad()
        pred, weights = model(x_exp_t[:train_n], x_gate_t[:train_n])
        balance = ((weights.mean(dim=0) - (1.0 / n_experts)) ** 2).mean()
        loss = torch.nn.functional.mse_loss(pred, y_t[:train_n]) + 0.01 * balance
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        model.eval()
        with torch.no_grad():
            val_pred, _ = model(x_exp_t[train_n:], x_gate_t[train_n:])
            val = torch.nn.functional.mse_loss(val_pred, y_t[train_n:]).item()
        if val < best_val - 1e-5:
            best_val = val
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    meta = {
        "x_exp_mean": x_exp_mean,
        "x_exp_std": x_exp_std,
        "x_gate_mean": x_gate_mean,
        "x_gate_std": x_gate_std,
        "y_mean": y_mean,
        "y_std": y_std,
        "best_val_mse": float(best_val),
    }
    return model, meta


def _predict_one(
    model: TinyResidualMoE,
    meta: dict[str, Any],
    row_expert: np.ndarray,
    row_gate: np.ndarray,
) -> tuple[float, float, float]:
    x_exp = (row_expert - meta["x_exp_mean"]) / meta["x_exp_std"]
    x_gate = (row_gate - meta["x_gate_mean"]) / meta["x_gate_std"]
    with torch.no_grad():
        pred, weights = model(
            torch.tensor(x_exp[None, :], dtype=torch.float32),
            torch.tensor(x_gate[None, :], dtype=torch.float32),
        )
    w = weights.numpy()[0]
    entropy = float(-(w * np.log(np.clip(w, 1e-12, 1.0))).sum())
    return float(pred.item() * meta["y_std"] + meta["y_mean"]), float(w.max()), entropy


def deep_rg_resmoe_pathway(
    gk_variance: pd.Series,
    *,
    horizon: int,
    rolling_window: int | None,
    refit_every: int,
    min_train_rows: int,
    hidden: int,
    n_experts: int,
    dropout: float,
    lr: float,
    weight_decay: float,
    epochs: int,
    patience: int,
    residual_shrinkage: float,
    seed: int,
) -> pd.DataFrame:
    lite = rg_resmoe_pathways(gk_variance, horizon=horizon, rolling_window=rolling_window)
    features = har_features(gk_variance)
    z = regime_scalar(gk_variance)
    gate_weight = z.rolling(GATE_PERCENTILE_WINDOW, min_periods=60).rank(pct=True)
    z_delta = z.diff(5)
    target = np.log(_future_avg_variance(gk_variance, horizon).clip(lower=GK_FLOOR))
    base = lite[f"base_pathway_h{horizon}"]
    residual = target - np.log(base.clip(lower=GK_FLOOR))

    expert_cols = ["log_rv_d", "log_rv_w", "log_rv_m"]
    x_expert = features[expert_cols]
    x_gate = pd.DataFrame(
        {
            "regime_scalar": z,
            "gate_weight": gate_weight,
            "regime_delta_5d": z_delta,
        },
        index=gk_variance.index,
    )
    valid = x_expert.notna().all(axis=1) & x_gate.notna().all(axis=1) & residual.notna() & base.notna()
    out = lite.copy()
    out[f"deep_gate_pathway_h{horizon}"] = np.nan
    out[f"deep_gate_max_weight_h{horizon}"] = np.nan
    out[f"deep_gate_entropy_h{horizon}"] = np.nan

    model: TinyResidualMoE | None = None
    meta: dict[str, Any] | None = None
    last_fit_idx = -1
    for i, _dt in enumerate(gk_variance.index):
        if not bool(valid.iloc[i]):
            continue
        train_end = i - horizon
        if train_end < min_train_rows:
            continue
        if model is None or (i - last_fit_idx) >= refit_every:
            train_start = 0 if rolling_window is None else max(0, train_end + 1 - rolling_window)
            mask = valid.iloc[train_start : train_end + 1]
            train_idx = train_start + np.where(mask.to_numpy())[0]
            if len(train_idx) < min_train_rows:
                continue
            model, meta = _fit_deep_moe(
                x_expert.iloc[train_idx].to_numpy(dtype=float),
                x_gate.iloc[train_idx].to_numpy(dtype=float),
                residual.iloc[train_idx].to_numpy(dtype=float),
                hidden=hidden,
                n_experts=n_experts,
                dropout=dropout,
                lr=lr,
                weight_decay=weight_decay,
                epochs=epochs,
                patience=patience,
                seed=seed + i + horizon,
            )
            last_fit_idx = i

        if model is None or meta is None:
            continue
        pred_resid, max_w, entropy = _predict_one(
            model,
            meta,
            x_expert.iloc[i].to_numpy(dtype=float),
            x_gate.iloc[i].to_numpy(dtype=float),
        )
        deep_log_forecast = float(np.log(max(float(base.iloc[i]), GK_FLOOR)) + float(residual_shrinkage) * pred_resid)
        out.iloc[i, out.columns.get_loc(f"deep_gate_pathway_h{horizon}")] = float(np.exp(deep_log_forecast))
        out.iloc[i, out.columns.get_loc(f"deep_gate_max_weight_h{horizon}")] = max_w
        out.iloc[i, out.columns.get_loc(f"deep_gate_entropy_h{horizon}")] = entropy
    return out


def evaluate(
    ticker: str,
    start: str,
    end: str,
    *,
    horizons: tuple[int, ...],
    rolling_window: int | None,
    refit_every: int,
    min_train_rows: int,
    residual_var_window: int,
    residual_var_min_rows: int,
    residual_var_buffer_5pct: float,
    residual_var_buffer_1pct: float,
    high_vol_gate_quantile: float,
    hidden: int,
    n_experts: int,
    dropout: float,
    lr: float,
    weight_decay: float,
    epochs: int,
    patience: int,
    residual_shrinkage: float,
    seed: int,
) -> dict[str, Any]:
    ohlc = _load_ohlc(DB_PATH, ticker, start, end)
    gk_variance = garman_klass_variance(ohlc)
    years = sorted(ohlc.index.year.unique())
    tail_buffers = {0.05: residual_var_buffer_5pct, 0.01: residual_var_buffer_1pct}
    results: dict[str, Any] = {}
    for h in horizons:
        frame = deep_rg_resmoe_pathway(
            gk_variance,
            horizon=h,
            rolling_window=rolling_window,
            refit_every=refit_every,
            min_train_rows=min_train_rows,
            hidden=hidden,
            n_experts=n_experts,
            dropout=dropout,
            lr=lr,
            weight_decay=weight_decay,
            epochs=epochs,
            patience=patience,
            residual_shrinkage=residual_shrinkage,
            seed=seed,
        )
        actual = _future_avg_variance(gk_variance, h)
        forward_return = ohlc["close"].shift(-h) / ohlc["close"] - 1.0
        base_fc = frame[f"base_pathway_h{h}"]
        lite_soft_fc = frame[f"gate_pathway_soft_h{h}"]
        deep_fc = frame[f"deep_gate_pathway_h{h}"]
        common = base_fc.notna() & lite_soft_fc.notna() & deep_fc.notna() & actual.notna()
        regime_state = gk_variance.rolling(20, min_periods=20).mean()
        high_vol_cutoff = float(regime_state[common].quantile(float(high_vol_gate_quantile))) if int(common.sum()) else float("nan")
        high_vol_mask = common & (regime_state >= high_vol_cutoff)
        recent_mask = common & pd.Series(frame.index >= pd.Timestamp("2025-01-01"), index=frame.index)
        high_vol_only_deep_fc = deep_fc.where(high_vol_mask, base_fc)
        forecasts = {
            "base_pathway": base_fc,
            "gate_pathway_soft": lite_soft_fc,
            "deep_gate_pathway": deep_fc,
            "high_vol_only_deep_gate_pathway": high_vol_only_deep_fc,
        }
        per_year = {}
        for yr in years:
            year_mask = pd.Series(frame.index.year == yr, index=frame.index) & common
            if int(year_mask.sum()) < 20:
                continue
            per_year[str(yr)] = {
                "gate_pathway_soft": _score(actual, lite_soft_fc, base_fc, year_mask, horizon=h),
                "deep_gate_pathway": _score(actual, deep_fc, base_fc, year_mask, horizon=h),
            }
        results[str(h)] = {
            "pooled": {
                "gate_pathway_soft": _score(actual, lite_soft_fc, base_fc, common, horizon=h),
                "deep_gate_pathway": _score(actual, deep_fc, base_fc, common, horizon=h),
                "high_vol_only_deep_gate_pathway": _score(actual, high_vol_only_deep_fc, base_fc, common, horizon=h),
            },
            "slices": {
                "top_realized_vol_decile": {
                    "gate_pathway_soft": _score(actual, lite_soft_fc, base_fc, high_vol_mask, horizon=h),
                    "deep_gate_pathway": _score(actual, deep_fc, base_fc, high_vol_mask, horizon=h),
                    "high_vol_only_deep_gate_pathway": _score(actual, high_vol_only_deep_fc, base_fc, high_vol_mask, horizon=h),
                },
                "recent_2025_2026": {
                    "gate_pathway_soft": _score(actual, lite_soft_fc, base_fc, recent_mask, horizon=h),
                    "deep_gate_pathway": _score(actual, deep_fc, base_fc, recent_mask, horizon=h),
                    "high_vol_only_deep_gate_pathway": _score(actual, high_vol_only_deep_fc, base_fc, recent_mask, horizon=h),
                },
            },
            "var_calibration": {
                "pooled": _var_suite(forward_return, forecasts, common, horizon=h),
                "top_realized_vol_decile": _var_suite(forward_return, forecasts, high_vol_mask, horizon=h),
                "recent_2025_2026": _var_suite(forward_return, forecasts, recent_mask, horizon=h),
            },
            "residual_var_calibration": {
                "pooled": _residual_var_suite(
                    forward_return,
                    forecasts,
                    common,
                    horizon=h,
                    calibration_window=residual_var_window,
                    min_calibration_rows=residual_var_min_rows,
                    tail_buffers=tail_buffers,
                ),
                "top_realized_vol_decile": _residual_var_suite(
                    forward_return,
                    forecasts,
                    high_vol_mask,
                    horizon=h,
                    calibration_window=residual_var_window,
                    min_calibration_rows=residual_var_min_rows,
                    tail_buffers=tail_buffers,
                ),
                "recent_2025_2026": _residual_var_suite(
                    forward_return,
                    forecasts,
                    recent_mask,
                    horizon=h,
                    calibration_window=residual_var_window,
                    min_calibration_rows=residual_var_min_rows,
                    tail_buffers=tail_buffers,
                ),
            },
            "diagnostics": {
                "common_rows": int(common.sum()),
                "high_vol_rows": int(high_vol_mask.sum()),
                "deep_gate_max_weight_mean": float(frame.loc[common, f"deep_gate_max_weight_h{h}"].mean()),
                "deep_gate_entropy_mean": float(frame.loc[common, f"deep_gate_entropy_h{h}"].mean()),
            },
            "per_year": per_year,
        }
    payload = {
        "ticker": ticker,
        "window": {"start": start, "end": end, "rows": int(len(ohlc))},
        "policy": "research_only_no_weight_change",
        "model": {
            "name": "tiny_deep_rg_resmoe_residual_shadow",
            "hidden": int(hidden),
            "n_experts": int(n_experts),
            "dropout": float(dropout),
            "lr": float(lr),
            "weight_decay": float(weight_decay),
            "epochs": int(epochs),
            "patience": int(patience),
            "residual_shrinkage": float(residual_shrinkage),
            "refit_every": int(refit_every),
            "min_train_rows": int(min_train_rows),
            "rolling_window": rolling_window,
            "seed": int(seed),
        },
        "high_vol_gate_quantile": float(high_vol_gate_quantile),
        "residual_var_window": int(residual_var_window),
        "residual_var_min_rows": int(residual_var_min_rows),
        "residual_var_tail_buffers": {
            "var_5pct": float(residual_var_buffer_5pct),
            "var_1pct": float(residual_var_buffer_1pct),
        },
        "results": results,
    }
    payload["promotion_decision"] = _promotion_decision(results, promoted_pathway="deep_gate_pathway")
    payload["high_vol_only_promotion_decision"] = _promotion_decision(
        results,
        promoted_pathway="high_vol_only_deep_gate_pathway",
    )
    return payload


def evaluate_many(tickers: list[str], **kwargs: Any) -> dict[str, Any]:
    by_ticker = {ticker: evaluate(ticker, **kwargs) for ticker in tickers}
    return {
        "tickers": tickers,
        "window": {"start": kwargs["start"], "end": kwargs["end"]},
        "policy": "research_only_no_weight_change",
        "by_ticker": by_ticker,
        "promotion_decision": {
            "decision": (
                "eligible_for_manual_review_not_auto_promote"
                if all(v["promotion_decision"]["decision"] == "eligible_for_manual_review_not_auto_promote" for v in by_ticker.values())
                else "do_not_promote_keep_shadow"
            ),
            "ticker_decisions": {ticker: payload["promotion_decision"]["decision"] for ticker, payload in by_ticker.items()},
            "high_vol_only_ticker_decisions": {
                ticker: payload["high_vol_only_promotion_decision"]["decision"]
                for ticker, payload in by_ticker.items()
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default="0050.TW,00631L.TW")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-08-20")
    parser.add_argument("--horizons", default="5,10,20")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_WINDOW)
    parser.add_argument("--refit-every", type=int, default=63)
    parser.add_argument("--min-train-rows", type=int, default=252)
    parser.add_argument("--hidden", type=int, default=8)
    parser.add_argument("--n-experts", type=int, default=3)
    parser.add_argument("--dropout", type=float, default=0.10)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--residual-shrinkage", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=260812251)
    parser.add_argument("--residual-var-window", type=int, default=DEFAULT_RESIDUAL_VAR_WINDOW)
    parser.add_argument("--residual-var-min-rows", type=int, default=DEFAULT_RESIDUAL_VAR_MIN_ROWS)
    parser.add_argument("--residual-var-buffer-5pct", type=float, default=DEFAULT_RESIDUAL_VAR_BUFFER_5PCT)
    parser.add_argument("--residual-var-buffer-1pct", type=float, default=DEFAULT_RESIDUAL_VAR_BUFFER_1PCT)
    parser.add_argument("--high-vol-gate-quantile", type=float, default=DEFAULT_HIGH_VOL_GATE_QUANTILE)
    args = parser.parse_args()

    tickers = [ticker.strip() for ticker in args.tickers.split(",") if ticker.strip()]
    horizons = tuple(int(h.strip()) for h in args.horizons.split(",") if h.strip())
    payload = evaluate_many(
        tickers,
        start=args.start,
        end=args.end,
        horizons=horizons,
        rolling_window=args.rolling_window,
        refit_every=args.refit_every,
        min_train_rows=args.min_train_rows,
        residual_var_window=args.residual_var_window,
        residual_var_min_rows=args.residual_var_min_rows,
        residual_var_buffer_5pct=args.residual_var_buffer_5pct,
        residual_var_buffer_1pct=args.residual_var_buffer_1pct,
        high_vol_gate_quantile=args.high_vol_gate_quantile,
        hidden=args.hidden,
        n_experts=args.n_experts,
        dropout=args.dropout,
        lr=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        patience=args.patience,
        residual_shrinkage=args.residual_shrinkage,
        seed=args.seed,
    )

    for ticker, ticker_payload in payload["by_ticker"].items():
        print(f"\n### {ticker} ###")
        for h, res in ticker_payload["results"].items():
            print(f"\n=== horizon={h} (pooled) ===")
            for pathway in ("gate_pathway_soft", "deep_gate_pathway", "high_vol_only_deep_gate_pathway"):
                r = res["pooled"][pathway]
                dm = r.get("dm_qlike_vs_base") or {}
                print(
                    f"  {pathway}: n={r.get('n')} improvement={r.get('qlike_improvement_pct'):.2f}% "
                    f"win_rate={r.get('win_rate_vs_base'):.3f} "
                    f"DM_p={dm.get('p_value'):.4f} DM_better={dm.get('a_more_accurate')}"
                )
            hv = res["slices"]["top_realized_vol_decile"]["deep_gate_pathway"]
            recent = res["slices"]["recent_2025_2026"]["deep_gate_pathway"]
            diag = res["diagnostics"]
            print(
                "  deep slices/diag: "
                f"top_vol_decile={hv.get('qlike_improvement_pct'):.2f}% "
                f"recent_2025_2026={recent.get('qlike_improvement_pct'):.2f}% "
                f"gate_max_mean={diag.get('deep_gate_max_weight_mean'):.3f} "
                f"entropy_mean={diag.get('deep_gate_entropy_mean'):.3f}"
            )
        print(f"  promotion: {ticker_payload['promotion_decision']['decision']}")
        if ticker_payload["promotion_decision"].get("blockers"):
            print(f"  blockers: {', '.join(ticker_payload['promotion_decision']['blockers'])}")
        print(f"  high-vol-only promotion: {ticker_payload['high_vol_only_promotion_decision']['decision']}")
        if ticker_payload["high_vol_only_promotion_decision"].get("blockers"):
            print(f"  high-vol-only blockers: {', '.join(ticker_payload['high_vol_only_promotion_decision']['blockers'])}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
