#!/usr/bin/env python3
"""Density-head tail-risk shadow evaluator for 00631L.

Research-only implementation inspired by 2606.30037v1 ("Heads, Not
Backbones"). This does not train a new deep backbone. It keeps the existing
NCF panel as the point/backbone signal and compares post-hoc residual heads:

* point: deterministic NCF mean proxy
* Gaussian: train-window residual Gaussian
* GMM: train-window residual Gaussian mixture

The goal is tail-risk calibration, not alpha. No live allocation, target
weight, or strategy manifest is changed.
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
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import TimeSeriesSplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260716.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "density_head_tail_risk_shadow_00631l_20250102_20260716.json"


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _pinball_loss(y: np.ndarray, q: np.ndarray, tau: float) -> float:
    diff = y - q
    return float(np.mean(np.maximum(tau * diff, (tau - 1.0) * diff)))


def _coverage(y: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> dict[str, Any]:
    inside = (y >= lower) & (y <= upper)
    return {
        "rows": int(len(y)),
        "coverage": float(np.mean(inside)) if len(y) else None,
        "below": int((y < lower).sum()),
        "above": int((y > upper).sum()),
    }


def _var_backtest(y: np.ndarray, var: np.ndarray, alpha: float) -> dict[str, Any]:
    breaches = y < var
    count = int(breaches.sum())
    rows = int(len(y))
    return {
        "alpha": float(alpha),
        "rows": rows,
        "breaches": count,
        "breach_rate": _safe_rate(count, rows),
        "expected_breaches": float(alpha * rows),
        "breach_rate_minus_alpha": None if rows == 0 else float(count / rows - alpha),
    }


def _expected_shortfall(samples: np.ndarray, alpha: float) -> np.ndarray:
    cutoff = np.quantile(samples, alpha, axis=1)
    out = []
    for row, q in zip(samples, cutoff, strict=False):
        tail = row[row <= q]
        out.append(float(np.mean(tail)) if len(tail) else float(q))
    return np.asarray(out, dtype=float)


def _crps_sample(y: np.ndarray, samples: np.ndarray) -> float:
    # Sample approximation of CRPS: E|X-y| - 0.5 E|X-X'|.
    first = np.mean(np.abs(samples - y[:, None]), axis=1)
    sorted_samples = np.sort(samples, axis=1)
    n = sorted_samples.shape[1]
    weights = (2 * np.arange(1, n + 1) - n - 1).astype(float)
    pairwise = (2.0 / (n * n)) * np.sum(sorted_samples * weights[None, :], axis=1)
    return float(np.mean(first - 0.5 * pairwise))


def _load_panel(path: Path, start: str | None, end: str | None) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    if start:
        frame = frame.loc[pd.Timestamp(start).normalize() :]
    if end:
        frame = frame.loc[: pd.Timestamp(end).normalize()]
    required = ["prob_up_h20", "prob_magnitude", "forward_gain_h20", "forward_mdd_h20"]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Panel missing required columns: {missing}")
    return frame


def _point_mu(panel: pd.DataFrame) -> pd.Series:
    prob = panel["prob_up_h20"].astype(float).clip(0.0, 1.0)
    mag = panel["prob_magnitude"].astype(float).clip(lower=0.0)
    return ((2.0 * prob - 1.0) * mag).rename("point_mu_h20")


def _fit_gmm_residuals(residuals: np.ndarray, n_components: int, seed: int) -> tuple[GaussianMixture | None, int]:
    clean = np.asarray(residuals, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 20 or np.std(clean) <= 1e-12:
        return None, 0
    k = int(min(max(1, n_components), max(1, len(clean) // 10)))
    if k < 2:
        return None, 0
    model = GaussianMixture(
        n_components=k,
        covariance_type="full",
        reg_covar=1e-6,
        random_state=seed,
        n_init=5,
        max_iter=500,
    )
    model.fit(clean.reshape(-1, 1))
    return model, k


def _draw_heads(
    *,
    mu: np.ndarray,
    train_resid: np.ndarray,
    n_samples: int,
    gmm_components: int,
    seed: int,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    clean = np.asarray(train_resid, dtype=float)
    clean = clean[np.isfinite(clean)]
    sigma = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    if not np.isfinite(sigma) or sigma <= 1e-9:
        sigma = 1e-6
    point_samples = np.repeat(mu[:, None], n_samples, axis=1)
    gaussian_samples = mu[:, None] + rng.normal(0.0, sigma, size=(len(mu), n_samples))
    gmm, used_k = _fit_gmm_residuals(clean, gmm_components, seed)
    if gmm is None:
        gmm_samples = gaussian_samples.copy()
    else:
        residual_draws = gmm.sample(len(mu) * n_samples)[0].reshape(len(mu), n_samples)
        gmm_samples = mu[:, None] + residual_draws
    return {
        "point": point_samples,
        "gaussian": gaussian_samples,
        "gmm": gmm_samples,
        "_metadata": np.asarray([sigma, used_k], dtype=float),
    }


def _summarize_distribution(y: np.ndarray, samples: np.ndarray) -> dict[str, Any]:
    quantiles = {
        "q01": np.quantile(samples, 0.01, axis=1),
        "q025": np.quantile(samples, 0.025, axis=1),
        "q05": np.quantile(samples, 0.05, axis=1),
        "q10": np.quantile(samples, 0.10, axis=1),
        "q50": np.quantile(samples, 0.50, axis=1),
        "q90": np.quantile(samples, 0.90, axis=1),
        "q95": np.quantile(samples, 0.95, axis=1),
        "q975": np.quantile(samples, 0.975, axis=1),
        "q99": np.quantile(samples, 0.99, axis=1),
    }
    mean = np.mean(samples, axis=1)
    return {
        "mae_mean": float(mean_absolute_error(y, mean)),
        "mse_mean": float(mean_squared_error(y, mean)),
        "crps_sample": _crps_sample(y, samples),
        "pinball": {
            "q01": _pinball_loss(y, quantiles["q01"], 0.01),
            "q025": _pinball_loss(y, quantiles["q025"], 0.025),
            "q05": _pinball_loss(y, quantiles["q05"], 0.05),
            "q10": _pinball_loss(y, quantiles["q10"], 0.10),
            "q50": _pinball_loss(y, quantiles["q50"], 0.50),
            "q90": _pinball_loss(y, quantiles["q90"], 0.90),
            "q95": _pinball_loss(y, quantiles["q95"], 0.95),
        },
        "coverage": {
            "central_90": _coverage(y, quantiles["q05"], quantiles["q95"]),
            "central_95": _coverage(y, quantiles["q025"], quantiles["q975"]),
            "central_98": _coverage(y, quantiles["q01"], quantiles["q99"]),
        },
        "var_backtest": {
            "var_01": _var_backtest(y, quantiles["q01"], 0.01),
            "var_025": _var_backtest(y, quantiles["q025"], 0.025),
            "var_05": _var_backtest(y, quantiles["q05"], 0.05),
            "var_10": _var_backtest(y, quantiles["q10"], 0.10),
        },
        "expected_shortfall": {
            "es_025_mean": float(np.mean(_expected_shortfall(samples, 0.025))),
            "es_05_mean": float(np.mean(_expected_shortfall(samples, 0.05))),
        },
        "mean_predicted_q05": float(np.mean(quantiles["q05"])),
        "mean_predicted_q025": float(np.mean(quantiles["q025"])),
    }


def _tail_alert_summary(y: np.ndarray, mdd: np.ndarray, var05: np.ndarray, train_var05_threshold: float) -> dict[str, Any]:
    active = var05 <= train_var05_threshold
    adverse_return = y <= -0.03
    adverse_mdd = mdd <= -0.05
    combined = adverse_return | adverse_mdd
    tp = int((active & combined).sum())
    fp = int((active & ~combined).sum())
    tn = int((~active & ~combined).sum())
    fn = int((~active & combined).sum())
    return {
        "active_days": int(active.sum()),
        "threshold": float(train_var05_threshold),
        "combined_adverse_precision": _safe_rate(tp, tp + fp),
        "combined_adverse_recall": _safe_rate(tp, tp + fn),
        "combined_adverse_fpr": _safe_rate(fp, fp + tn),
        "active_mean_forward_gain_h20": float(np.mean(y[active])) if active.any() else None,
        "inactive_mean_forward_gain_h20": float(np.mean(y[~active])) if (~active).any() else None,
        "active_mean_forward_mdd_h20": float(np.mean(mdd[active])) if active.any() else None,
        "inactive_mean_forward_mdd_h20": float(np.mean(mdd[~active])) if (~active).any() else None,
    }


def evaluate_density_heads(
    panel: pd.DataFrame,
    *,
    n_splits: int,
    gap: int,
    n_samples: int,
    gmm_components: int,
    alert_quantile: float,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    data = panel.copy()
    data["point_mu_h20"] = _point_mu(data)
    data = data.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["point_mu_h20", "forward_gain_h20", "forward_mdd_h20"]
    )
    if len(data) < n_splits + 20:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")
    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    fold_reports: list[dict[str, Any]] = []
    pred_rows: list[pd.DataFrame] = []
    head_samples: dict[str, list[np.ndarray]] = {"point": [], "gaussian": [], "gmm": []}

    for fold, (train_idx, test_idx) in enumerate(split.split(data), start=1):
        train = data.iloc[train_idx]
        test = data.iloc[test_idx]
        train_resid = (train["forward_gain_h20"] - train["point_mu_h20"]).to_numpy(dtype=float)
        y_test = test["forward_gain_h20"].to_numpy(dtype=float)
        mdd_test = test["forward_mdd_h20"].to_numpy(dtype=float)
        mu_test = test["point_mu_h20"].to_numpy(dtype=float)
        draws = _draw_heads(
            mu=mu_test,
            train_resid=train_resid,
            n_samples=n_samples,
            gmm_components=gmm_components,
            seed=seed + fold,
        )
        sigma, used_k = draws["_metadata"]
        fold_summary: dict[str, Any] = {
            "fold": fold,
            "train_start": str(train.index[0].date()),
            "train_end": str(train.index[-1].date()),
            "test_start": str(test.index[0].date()),
            "test_end": str(test.index[-1].date()),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_residual_sigma": float(sigma),
            "gmm_components_used": int(used_k),
            "heads": {},
        }
        pred = pd.DataFrame(
            {
                "date": test.index,
                "fold": fold,
                "forward_gain_h20": y_test,
                "forward_mdd_h20": mdd_test,
                "point_mu_h20": mu_test,
            }
        )
        for head in ("point", "gaussian", "gmm"):
            samples = draws[head]
            head_samples[head].append(samples)
            summary = _summarize_distribution(y_test, samples)
            var05 = np.quantile(samples, 0.05, axis=1)
            train_draws = _draw_heads(
                mu=train["point_mu_h20"].to_numpy(dtype=float),
                train_resid=train_resid,
                n_samples=n_samples,
                gmm_components=gmm_components,
                seed=seed + 1000 + fold,
            )[head]
            train_var05 = np.quantile(train_draws, 0.05, axis=1)
            threshold = float(np.quantile(train_var05, alert_quantile))
            summary["tail_alert"] = _tail_alert_summary(y_test, mdd_test, var05, threshold)
            fold_summary["heads"][head] = summary
            pred[f"{head}_mean"] = np.mean(samples, axis=1)
            pred[f"{head}_q05"] = var05
            pred[f"{head}_q025"] = np.quantile(samples, 0.025, axis=1)
            pred[f"{head}_q95"] = np.quantile(samples, 0.95, axis=1)
        fold_reports.append(fold_summary)
        pred_rows.append(pred)

    pred_frame = pd.concat(pred_rows, ignore_index=True)
    y_all = pred_frame["forward_gain_h20"].to_numpy(dtype=float)
    aggregate: dict[str, Any] = {}
    for head, chunks in head_samples.items():
        samples = np.vstack(chunks)
        summary = _summarize_distribution(y_all, samples)
        var05 = pred_frame[f"{head}_q05"].to_numpy(dtype=float)
        threshold = float(np.quantile(pred_frame[f"{head}_q05"].to_numpy(dtype=float), alert_quantile))
        summary["tail_alert_global_threshold"] = _tail_alert_summary(
            y_all,
            pred_frame["forward_mdd_h20"].to_numpy(dtype=float),
            var05,
            threshold,
        )
        aggregate[head] = summary
    best_by_crps = min(aggregate, key=lambda name: aggregate[name]["crps_sample"])
    best_by_pinball05 = min(aggregate, key=lambda name: aggregate[name]["pinball"]["q05"])
    promotion_decision = "research_only"
    if (
        best_by_pinball05 == "gmm"
        and aggregate["gmm"]["pinball"]["q05"] < aggregate["gaussian"]["pinball"]["q05"]
        and abs((aggregate["gmm"]["var_backtest"]["var_05"]["breach_rate"] or 0.0) - 0.05) <= 0.025
    ):
        promotion_decision = "candidate_for_deeper_tail_risk_review_not_live"
    report = {
        "report_type": "density_head_tail_risk_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.30037v1.pdf",
            "title": "Heads, Not Backbones: Output Heads Dominate Architectures on Fat-Tailed Returns",
            "implementation_note": "Residual density-head proxy on existing NCF panel; not a deep GMM head retrain.",
        },
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(data.index.min().date()),
            "end": str(data.index.max().date()),
            "rows": int(len(data)),
        },
        "parameters": {
            "target": "forward_gain_h20",
            "point_mu": "(2 * prob_up_h20 - 1) * prob_magnitude",
            "n_splits": int(n_splits),
            "gap": int(gap),
            "n_samples": int(n_samples),
            "gmm_components": int(gmm_components),
            "alert_quantile": float(alert_quantile),
        },
        "folds": fold_reports,
        "aggregate": aggregate,
        "best_by_crps": best_by_crps,
        "best_by_pinball_q05": best_by_pinball05,
        "promotion_decision": promotion_decision,
        "interpretation": (
            "Tests whether density heads improve 00631L H20 tail calibration. "
            "Distributional gains are risk-management evidence only, not trading alpha."
        ),
    }
    return report, pred_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=20)
    parser.add_argument("--n-samples", type=int, default=500)
    parser.add_argument("--gmm-components", type=int, default=4)
    parser.add_argument("--alert-quantile", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    panel = _load_panel(Path(args.panel), args.start, args.end)
    report, pred = evaluate_density_heads(
        panel,
        n_splits=int(args.n_splits),
        gap=int(args.gap),
        n_samples=int(args.n_samples),
        gmm_components=int(args.gmm_components),
        alert_quantile=float(args.alert_quantile),
        seed=int(args.seed),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pred_output = output.with_name(output.stem + "_predictions.csv")
    pred.to_csv(pred_output, index=False, encoding="utf-8-sig")
    report["prediction_output"] = str(pred_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        head: {
            "crps": values["crps_sample"],
            "pinball_q05": values["pinball"]["q05"],
            "var05_breach_rate": values["var_backtest"]["var_05"]["breach_rate"],
            "central90_coverage": values["coverage"]["central_90"]["coverage"],
            "tail_alert_precision": values["tail_alert_global_threshold"]["combined_adverse_precision"],
            "tail_alert_fpr": values["tail_alert_global_threshold"]["combined_adverse_fpr"],
        }
        for head, values in report["aggregate"].items()
    }
    print(f"Saved: {output}")
    print(f"Predictions: {pred_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    print(f"Promotion decision: {report['promotion_decision']}")


if __name__ == "__main__":
    main()
