#!/usr/bin/env python3
"""Paper-style replication for arXiv:2603.01157v2 BAWS experiments.

This is a local, configurable replication harness.  It covers the paper's
simulation scenarios A1-A3, B1-B3, an approximate GARCH volatility-shift
scenario, and the available local S&P500 empirical cache.  It does not alter
GroupA+ strategy, live signals, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402

BAWS_PATH = PROJECT_ROOT / "scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/2603_01157_baws_paper_replication_latest.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2603_01157_baws_paper_replication.md"


def _load_baws_module():
    spec = importlib.util.spec_from_file_location("_baws_lite_shadow", BAWS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load BAWS module: {BAWS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BAWS = _load_baws_module()
METHODS = ("baws", "saws_lite", "fixed_250", "fixed_500", "fixed_750", "full")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _normal_expected_check_loss(v: float, mu: float, sigma: float, alpha: float) -> float:
    z = (v - mu) / sigma
    cdf = norm.cdf(z)
    pdf = norm.pdf(z)
    e_left_minus_v = (mu - v) * cdf - sigma * pdf
    e_right_minus_v = (mu - v) * (1.0 - cdf) + sigma * pdf
    return float((alpha - 1.0) * e_left_minus_v + alpha * e_right_minus_v)


def _check_loss(x: float, v: float, alpha: float) -> float:
    return float((alpha - (1.0 if x <= v else 0.0)) * (x - v))


def _series_params(setting: str, t_len: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(1, t_len + 1)
    if setting == "A1":
        mu = np.where(t <= t_len / 2, 1.0, 2.0)
        var = np.full(t_len, 0.25)
    elif setting == "A2":
        mu = np.where(t <= 800, 1.0, np.where(t <= 1400, 0.0, 2.0))
        var = np.full(t_len, 0.25)
    elif setting == "A3":
        mu = np.where(t <= 800, 1.0, np.where(t <= 1400, 0.0, 2.0))
        var = np.where(t <= 800, 0.25, np.where(t <= 1400, 1.0, 0.49))
    elif setting == "B1":
        mu = np.sin(2.0 * math.pi * t / t_len)
        var = np.full(t_len, 0.25)
    elif setting == "B2":
        mu = np.cumsum(rng.normal(0.0, math.sqrt(1.0 / t_len), size=t_len))
        var = np.full(t_len, 0.25)
    elif setting == "B3":
        w = np.cumsum(rng.normal(0.0, math.sqrt(1.0 / t_len), size=t_len))
        mu0 = 1.0
        drift = 0.5
        sigma = math.sqrt(0.25)
        mu = mu0 * np.exp((drift - 0.5 * sigma**2) * t / t_len + sigma * w)
        var = np.full(t_len, 0.25)
    else:
        raise ValueError(f"Unknown setting: {setting}")
    return mu.astype(float), var.astype(float)


def _fixed_forecasts(values: pd.Series, windows: tuple[int, ...], alpha: float) -> pd.DataFrame:
    fixed = BAWS.precompute_fixed_window_forecasts(values, candidate_windows=windows, alpha=alpha)
    full_var = values.expanding(min_periods=20).quantile(alpha).shift(1)
    fixed["full_var"] = full_var
    fixed["full_score"] = [
        _check_loss(float(loss), float(var), alpha) if pd.notna(loss) and pd.notna(var) else np.nan
        for loss, var in zip(fixed["realized_loss"], full_var, strict=False)
    ]
    return fixed


def _saws_lite_window(fixed: pd.DataFrame, pos: int, windows: tuple[int, ...], scale: float) -> int:
    reference = windows[0]
    start = max(0, pos - reference)
    ref = pd.to_numeric(fixed.iloc[start:pos][f"fixed_{reference}_score"], errors="coerce")
    admissible: list[int] = []
    for window in windows:
        cand = pd.to_numeric(fixed.iloc[start:pos][f"fixed_{window}_score"], errors="coerce")
        aligned = pd.concat([cand.rename("candidate"), ref.rename("reference")], axis=1).dropna()
        if len(aligned) < 20:
            continue
        diff = aligned["candidate"].to_numpy(dtype=float) - aligned["reference"].to_numpy(dtype=float)
        threshold = max(0.0, scale * float(np.std(diff, ddof=1)) / math.sqrt(len(diff)))
        if float(np.mean(diff)) <= threshold:
            admissible.append(window)
    return max(admissible) if admissible else reference


def _simulate_normal_setting(
    setting: str,
    *,
    reps: int,
    t_len: int,
    t0: int,
    alpha: float,
    beta: float,
    bootstrap_samples: int,
    forecast_stride: int,
    seed: int,
) -> dict[str, Any]:
    windows = (250, 500, 750)
    rng = np.random.default_rng(seed)
    forecasts = {method: [] for method in METHODS}
    true_vars: list[np.ndarray] = []
    realized_by_rep: list[np.ndarray] = []
    cr_by_method = {method: [] for method in METHODS}
    cl_by_method = {method: [] for method in METHODS}
    selected_counts = {"baws": {str(w): 0 for w in windows}, "saws_lite": {str(w): 0 for w in windows}}
    for rep in range(reps):
        mu, var = _series_params(setting, t_len, rng)
        sigma = np.sqrt(var)
        x = rng.normal(mu, sigma)
        true_var = mu + sigma * norm.ppf(alpha)
        series = pd.Series(x, index=pd.RangeIndex(1, t_len + 1), dtype=float)
        fixed = _fixed_forecasts(series, windows, alpha)
        rep_forecasts = {method: [] for method in METHODS}
        rep_cr = {method: 0.0 for method in METHODS}
        rep_cl = {method: 0.0 for method in METHODS}
        eval_positions = list(range(t0 - 1, t_len, forecast_stride))
        for pos in eval_positions:
            baws = BAWS.select_baws_window_from_precomputed(
                fixed,
                pos=pos,
                candidate_windows=windows,
                evaluation_window=windows[0],
                beta=beta,
                bootstrap_samples=bootstrap_samples,
                seed=seed + rep * 100_003,
            )["selected_window"]
            saws = _saws_lite_window(fixed, pos, windows, scale=0.5)
            selected_counts["baws"][str(baws)] += 1
            selected_counts["saws_lite"][str(saws)] += 1
            values = {
                "baws": float(fixed.iloc[pos][f"fixed_{baws}_var"]),
                "saws_lite": float(fixed.iloc[pos][f"fixed_{saws}_var"]),
                "fixed_250": float(fixed.iloc[pos]["fixed_250_var"]),
                "fixed_500": float(fixed.iloc[pos]["fixed_500_var"]),
                "fixed_750": float(fixed.iloc[pos]["fixed_750_var"]),
                "full": float(fixed.iloc[pos]["full_var"]),
            }
            for method, forecast in values.items():
                if not math.isfinite(forecast):
                    forecast = values["fixed_250"]
                rep_forecasts[method].append(forecast)
                rep_cl[method] += _check_loss(float(x[pos]), forecast, alpha)
                rep_cr[method] += _normal_expected_check_loss(forecast, float(mu[pos]), float(sigma[pos]), alpha) - _normal_expected_check_loss(float(true_var[pos]), float(mu[pos]), float(sigma[pos]), alpha)
        true_vars.append(true_var[eval_positions])
        realized_by_rep.append(x[eval_positions])
        for method in METHODS:
            forecasts[method].append(np.asarray(rep_forecasts[method], dtype=float))
            cr_by_method[method].append(rep_cr[method])
            cl_by_method[method].append(rep_cl[method])

    true_matrix = np.vstack(true_vars)
    result = {
        "setting": setting,
        "replications": reps,
        "forecast_stride": int(forecast_stride),
        "metrics": {},
        "selected_window_counts": selected_counts,
    }
    for method in METHODS:
        arr = np.vstack(forecasts[method])
        mean_forecast = arr.mean(axis=0)
        result["metrics"][method] = {
            "MAB": float(np.mean(np.abs(mean_forecast - true_matrix.mean(axis=0)))),
            "Var": float(np.mean(arr.var(axis=0, ddof=1))) if reps > 1 else 0.0,
            "MSE": float(np.mean((arr - true_matrix) ** 2)),
            "CR": float(np.mean(cr_by_method[method])),
            "CL": float(np.mean(cl_by_method[method])),
        }
    result["winners"] = {
        metric: min(METHODS, key=lambda m: result["metrics"][m][metric])
        for metric in ("MAB", "Var", "MSE", "CR", "CL")
    }
    return result


def _simulate_garch(
    *,
    reps: int,
    t_len: int,
    t0: int,
    alpha: float,
    beta: float,
    bootstrap_samples: int,
    forecast_stride: int,
    seed: int,
) -> dict[str, Any]:
    windows = (250, 500, 750)
    rng = np.random.default_rng(seed)
    q = student_t.ppf(alpha, df=5) / math.sqrt(5 / 3)
    forecasts = {method: [] for method in METHODS}
    true_vars: list[np.ndarray] = []
    cl_by_method = {method: [] for method in METHODS}
    selected_counts = {"baws": {str(w): 0 for w in windows}, "saws_lite": {str(w): 0 for w in windows}}
    for rep in range(reps):
        losses = np.zeros(t_len)
        sigma2 = np.zeros(t_len)
        sigma2[0] = 0.00001 / (1.0 - 0.04 - 0.7)
        eps = student_t.rvs(df=5, size=t_len, random_state=rng) / math.sqrt(5 / 3)
        for pos in range(1, t_len):
            gamma = 0.7 + (0.25 if pos + 1 > 1000 else 0.0)
            sigma2[pos] = 0.00001 + 0.04 * losses[pos - 1] ** 2 + gamma * sigma2[pos - 1]
            losses[pos] = -math.sqrt(max(sigma2[pos], 1e-12)) * eps[pos]
        true_var = np.sqrt(np.maximum(sigma2, 1e-12)) * q
        series = pd.Series(losses, index=pd.RangeIndex(1, t_len + 1), dtype=float)
        fixed = _fixed_forecasts(series, windows, alpha)
        rep_forecasts = {method: [] for method in METHODS}
        rep_cl = {method: 0.0 for method in METHODS}
        eval_positions = list(range(t0 - 1, t_len, forecast_stride))
        for pos in eval_positions:
            baws = BAWS.select_baws_window_from_precomputed(
                fixed,
                pos=pos,
                candidate_windows=windows,
                evaluation_window=windows[0],
                beta=beta,
                bootstrap_samples=bootstrap_samples,
                seed=seed + rep * 100_003,
            )["selected_window"]
            saws = _saws_lite_window(fixed, pos, windows, scale=0.5)
            selected_counts["baws"][str(baws)] += 1
            selected_counts["saws_lite"][str(saws)] += 1
            values = {
                "baws": float(fixed.iloc[pos][f"fixed_{baws}_var"]),
                "saws_lite": float(fixed.iloc[pos][f"fixed_{saws}_var"]),
                "fixed_250": float(fixed.iloc[pos]["fixed_250_var"]),
                "fixed_500": float(fixed.iloc[pos]["fixed_500_var"]),
                "fixed_750": float(fixed.iloc[pos]["fixed_750_var"]),
                "full": float(fixed.iloc[pos]["full_var"]),
            }
            for method, forecast in values.items():
                if not math.isfinite(forecast):
                    forecast = values["fixed_250"]
                rep_forecasts[method].append(forecast)
                rep_cl[method] += _check_loss(float(losses[pos]), forecast, alpha)
        true_vars.append(true_var[eval_positions])
        for method in METHODS:
            forecasts[method].append(np.asarray(rep_forecasts[method], dtype=float))
            cl_by_method[method].append(rep_cl[method])
    true_matrix = np.vstack(true_vars)
    result = {
        "setting": "GARCH_approx_student_t_not_fernandez_steel_skew_t",
        "replications": reps,
        "forecast_stride": int(forecast_stride),
        "metrics": {},
        "selected_window_counts": selected_counts,
        "caveat": "Uses standardized Student-t innovations; paper uses Fernandez-Steel skewed-t with r=0.95.",
    }
    for method in METHODS:
        arr = np.vstack(forecasts[method])
        mean_forecast = arr.mean(axis=0)
        result["metrics"][method] = {
            "MAB": float(np.mean(np.abs(mean_forecast - true_matrix.mean(axis=0)))),
            "Var": float(np.mean(arr.var(axis=0, ddof=1))) if reps > 1 else 0.0,
            "MSE": float(np.mean((arr - true_matrix) ** 2)),
            "CR": None,
            "CL": float(np.mean(cl_by_method[method])),
        }
    result["winners"] = {
        metric: min(METHODS, key=lambda m: result["metrics"][m][metric] if result["metrics"][m][metric] is not None else float("inf"))
        for metric in ("MAB", "Var", "MSE", "CL")
    }
    return result


def _load_external_losses(db_path: Path, ticker: str, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance' AND ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.Series(dtype=float)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = pd.Series(rows["close"].astype(float).to_numpy(), index=rows["dt"])
    return -np.log(close / close.shift(1)).dropna()


def _empirical_sp500_subset(
    db_path: Path,
    alpha: float,
    beta: float,
    bootstrap_samples: int,
    forecast_stride: int,
    seed: int,
) -> dict[str, Any]:
    losses = _load_external_losses(db_path, "^GSPC", "2005-01-04", "2026-08-13")
    if losses.empty:
        return {"status": "unavailable", "reason": "missing_local_^GSPC_cache"}
    windows = (250, 500, 750)
    start = max(pd.Timestamp("2006-12-28"), losses.index[min(len(losses) - 1, 1000)])
    fixed = _fixed_forecasts(losses, windows, alpha)
    rows = []
    for pos, dt in enumerate(losses.index):
        if dt < start or pos < 501:
            continue
        if (pos - 501) % forecast_stride != 0:
            continue
        baws = BAWS.select_baws_window_from_precomputed(
            fixed,
            pos=pos,
            candidate_windows=windows,
            evaluation_window=250,
            beta=beta,
            bootstrap_samples=bootstrap_samples,
            seed=seed + pos,
        )["selected_window"]
        saws = _saws_lite_window(fixed, pos, windows, scale=0.05)
        row = {"date": dt, "loss": float(losses.iloc[pos]), "baws_window": baws, "saws_lite_window": saws}
        for method, window in {"baws": baws, "saws_lite": saws, "fixed_250": 250, "fixed_500": 500, "fixed_750": 750}.items():
            row[f"{method}_var"] = float(fixed.iloc[pos][f"fixed_{window}_var"])
            row[f"{method}_es"] = float(fixed.iloc[pos][f"fixed_{window}_es"])
            row[f"{method}_score"] = _check_loss(float(losses.iloc[pos]), row[f"{method}_var"], alpha)
        row["full_var"] = float(fixed.iloc[pos]["full_var"])
        row["full_score"] = _check_loss(float(losses.iloc[pos]), row["full_var"], alpha)
        rows.append(row)
    frame = pd.DataFrame(rows)
    methods = ("baws", "saws_lite", "fixed_250", "fixed_500", "fixed_750", "full")
    scores = {method: float(pd.to_numeric(frame[f"{method}_score"], errors="coerce").mean()) for method in methods}
    cache_start = str(losses.index.min().date())
    cache_end = str(losses.index.max().date())
    # Losses are one row shorter than closes, so a close cache beginning on
    # 2005-01-04 naturally yields its first return on 2005-01-05.
    has_paper_start = losses.index.min() <= pd.Timestamp("2005-01-05")
    caveat = (
        "Local cache covers the paper's requested S&P 500 start date. "
        "This is still a local reproduction, not the paper's full Table 4, because the run uses local bootstrap/stride settings."
        if has_paper_start
        else "Local cache starts after the paper's 2005-01-04 start; this is not the full Table 4 replication."
    )
    return {
        "status": "available_full_local_cache" if has_paper_start else "available_partial",
        "ticker": "^GSPC",
        "cache_window": {"start": cache_start, "end": cache_end, "rows": int(len(losses))},
        "evaluation_window": {"start": str(frame["date"].min().date()) if not frame.empty else None, "end": str(frame["date"].max().date()) if not frame.empty else None, "rows": int(len(frame))},
        "caveat": caveat,
        "average_quantile_scores": scores,
        "best_method": min(scores, key=scores.get) if scores else None,
        "selected_window_counts": {
            "baws": {str(int(k)): int(v) for k, v in frame["baws_window"].value_counts().sort_index().items()} if not frame.empty else {},
            "saws_lite": {str(int(k)): int(v) for k, v in frame["saws_lite_window"].value_counts().sort_index().items()} if not frame.empty else {},
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    settings = [item.strip() for item in args.settings.split(",") if item.strip()]
    simulations = {}
    for setting in settings:
        if setting == "GARCH":
            simulations[setting] = _simulate_garch(
                reps=args.reps,
                t_len=args.t_len,
                t0=args.t0,
                alpha=args.alpha,
                beta=args.beta,
                bootstrap_samples=args.bootstrap_samples,
                forecast_stride=args.forecast_stride,
                seed=args.seed + 99_999,
            )
        else:
            simulations[setting] = _simulate_normal_setting(
                setting,
                reps=args.reps,
                t_len=args.t_len,
                t0=args.t0,
                alpha=args.alpha,
                beta=args.beta,
                bootstrap_samples=args.bootstrap_samples,
                forecast_stride=args.forecast_stride,
                seed=args.seed + hash(setting) % 10_000,
            )
    empirical = _empirical_sp500_subset(
        _resolve(args.db),
        args.alpha,
        args.beta,
        args.empirical_bootstrap_samples,
        args.forecast_stride,
        args.seed,
    )
    return {
        "schema_version": 1,
        "report_type": "2603_01157_baws_paper_replication",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting",
        "policy": "research_only_no_groupa_plus_live_change",
        "paper_target_config": {
            "simulation": {"T": 2000, "t0": 501, "replications": 1000, "bootstrap_samples": 500, "beta": 0.9, "fixed_windows": [250, 500, 750]},
            "empirical": {"ticker": "^GSPC", "data_start": "2005-01-04", "forecast_start": "2006-12-28", "end": "2025-10-30", "bootstrap_samples": 1000, "max_baws_window": 1000},
        },
        "local_run_config": {
            "T": args.t_len,
            "t0": args.t0,
            "replications": args.reps,
            "bootstrap_samples": args.bootstrap_samples,
            "beta": args.beta,
            "alpha": args.alpha,
            "settings": settings,
            "forecast_stride": int(args.forecast_stride),
        },
        "simulations": simulations,
        "empirical_sp500_subset": empirical,
        "decision_for_groupa_plus": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "recommended_use": "research_only",
            "reason": "Paper-style simulations may show BAWS advantages in synthetic settings, but GroupA+ ETF and portfolio tests do not support live promotion.",
        },
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2603.01157v2 BAWS Paper-Style Replication",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Local reps: `{report['local_run_config']['replications']}`",
        f"- Local bootstrap samples: `{report['local_run_config']['bootstrap_samples']}`",
        "",
        "## Simulation Winners",
        "",
        "| Setting | MAB | Var | MSE | CR | CL |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for setting, result in report["simulations"].items():
        winners = result["winners"]
        lines.append(
            f"| {setting} | {winners.get('MAB')} | {winners.get('Var')} | {winners.get('MSE')} | {winners.get('CR')} | {winners.get('CL')} |"
        )
    empirical = report["empirical_sp500_subset"]
    lines.extend(["", "## Empirical S&P500 Subset", ""])
    if empirical.get("status") in {"available_partial", "available_full_local_cache"}:
        lines.extend(
            [
                f"- Cache window: `{empirical['cache_window']}`",
                f"- Evaluation window: `{empirical['evaluation_window']}`",
                f"- Best method by quantile score: `{empirical['best_method']}`",
                f"- Caveat: {empirical['caveat']}",
            ]
        )
    else:
        lines.append(f"- Status: `{empirical.get('status')}` / `{empirical.get('reason')}`")
    lines.extend(
        [
            "",
            "## GroupA+ Decision",
            "",
            report["decision_for_groupa_plus"]["reason"],
            "",
            "No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--settings", default="A1,A2,A3,B1,B2,B3,GARCH")
    parser.add_argument("--reps", type=int, default=50)
    parser.add_argument("--t-len", type=int, default=2000)
    parser.add_argument("--t0", type=int, default=501)
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--beta", type=float, default=0.90)
    parser.add_argument("--bootstrap-samples", type=int, default=100)
    parser.add_argument("--empirical-bootstrap-samples", type=int, default=1000)
    parser.add_argument("--forecast-stride", type=int, default=1)
    parser.add_argument("--seed", type=int, default=260301157)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(report, output_md)
    print(
        json.dumps(
            {
                "settings": list(report["simulations"]),
                "reps": report["local_run_config"]["replications"],
                "bootstrap_samples": report["local_run_config"]["bootstrap_samples"],
                "empirical_status": report["empirical_sp500_subset"].get("status"),
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
