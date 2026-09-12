#!/usr/bin/env python3
"""Extended BAWS experiments for GroupA+.

Research-only follow-up for arXiv:2603.01157v2.  This script does not change
latest strategy, golden1_0531, live signals, execution plans, or orders.
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

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402

BAWS_PATH = PROJECT_ROOT / "scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/group_a_plus_baws_extended_experiments_latest.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results/group_a_plus_baws_extended_portfolio_curve_latest.csv"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/baws_extended_experiments.md"


def _load_baws_module():
    spec = importlib.util.spec_from_file_location("_baws_lite_shadow", BAWS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load BAWS module: {BAWS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BAWS = _load_baws_module()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def _parse_float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def fz0_score(loss: float, var: float, es: float, alpha: float) -> float:
    """A scale-free FZ-style joint VaR/ES score for positive losses.

    Lower is better.  This is used only as a robustness diagnostic; it is not
    wired to BAWS selection or any trading decision.
    """

    if not all(math.isfinite(float(x)) for x in (loss, var, es)) or es <= 1e-12:
        return float("nan")
    indicator = 1.0 if loss <= var else 0.0
    tail = (1.0 - indicator) * (loss - var) / max(1.0 - alpha, 1e-12)
    return float(math.log(es) + (var + tail) / es)


def _method_fz_summary(forecasts: pd.DataFrame, candidate_windows: tuple[int, ...], alpha: float) -> dict[str, Any]:
    methods = ["baws"] + [f"fixed_{window}" for window in candidate_windows]
    out: dict[str, Any] = {}
    for method in methods:
        scores: list[float] = []
        for row in forecasts.itertuples(index=False):
            loss = float(getattr(row, "realized_loss"))
            var = float(getattr(row, f"{method}_var"))
            es = float(getattr(row, f"{method}_es"))
            score = fz0_score(loss, var, es, alpha)
            if math.isfinite(score):
                scores.append(score)
        out[method] = {
            "count": len(scores),
            "average_fz0_score": float(np.mean(scores)) if scores else None,
        }
    fixed_scores = {
        method: detail["average_fz0_score"]
        for method, detail in out.items()
        if method.startswith("fixed_") and detail["average_fz0_score"] is not None
    }
    best_fixed = min(fixed_scores, key=fixed_scores.get) if fixed_scores else None
    baws_score = out["baws"]["average_fz0_score"]
    best_score = fixed_scores.get(best_fixed) if best_fixed is not None else None
    out["comparison"] = {
        "best_fixed_method": best_fixed,
        "baws_minus_best_fixed_fz0_score": (
            None if baws_score is None or best_score is None else float(baws_score - best_score)
        ),
        "baws_beats_best_fixed_fz0": bool(
            baws_score is not None and best_score is not None and baws_score < best_score
        ),
    }
    return out


def _saws_lite_selected_windows(
    ticker_forecasts: pd.DataFrame,
    candidate_windows: tuple[int, ...],
    *,
    evaluation_window: int,
    scale: float,
) -> pd.Series:
    """Deterministic-threshold adaptive-window comparator.

    This is intentionally labelled SAWS-like instead of exact SAWS: it uses the
    same fixed-window score panel as the BAWS-lite evaluator and a transparent
    standard-error threshold.
    """

    frame = ticker_forecasts.reset_index(drop=True).copy()
    windows = tuple(sorted(candidate_windows))
    reference = windows[0]
    selected: list[int] = []
    for pos in range(len(frame)):
        start = max(0, pos - evaluation_window)
        ref = pd.to_numeric(frame.iloc[start:pos][f"fixed_{reference}_score"], errors="coerce")
        admissible: list[int] = []
        for window in windows:
            cand = pd.to_numeric(frame.iloc[start:pos][f"fixed_{window}_score"], errors="coerce")
            aligned = pd.concat([cand.rename("candidate"), ref.rename("reference")], axis=1).dropna()
            if len(aligned) < max(10, evaluation_window // 3):
                continue
            diff = aligned["candidate"].to_numpy(dtype=float) - aligned["reference"].to_numpy(dtype=float)
            mean_diff = float(np.mean(diff))
            se = float(np.std(diff, ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else 0.0
            threshold = max(0.0, scale * se * math.sqrt(max(math.log(len(diff) + 1.0), 1e-12)))
            if mean_diff <= threshold:
                admissible.append(window)
        selected.append(max(admissible) if admissible else reference)
    return pd.Series(selected, index=ticker_forecasts.index, dtype=int)


def _saws_lite_summary(forecasts: pd.DataFrame, candidate_windows: tuple[int, ...], evaluation_window: int, scale: float) -> dict[str, Any]:
    by_ticker: dict[str, Any] = {}
    for ticker, group in forecasts.sort_values("date").groupby("ticker"):
        group = group.copy()
        selected = _saws_lite_selected_windows(group, candidate_windows, evaluation_window=evaluation_window, scale=scale)
        scores = []
        for pos, row in enumerate(group.itertuples(index=False)):
            window = int(selected.iloc[pos])
            score = float(getattr(row, f"fixed_{window}_score"))
            if math.isfinite(score):
                scores.append(score)
        fixed_scores = {
            f"fixed_{window}": pd.to_numeric(group[f"fixed_{window}_score"], errors="coerce").mean()
            for window in candidate_windows
        }
        best_fixed = min(fixed_scores, key=fixed_scores.get)
        avg_score = float(np.mean(scores)) if scores else None
        best_score = float(fixed_scores[best_fixed])
        by_ticker[str(ticker)] = {
            "average_quantile_score": avg_score,
            "best_fixed_method": best_fixed,
            "saws_lite_minus_best_fixed_score": None if avg_score is None else float(avg_score - best_score),
            "saws_lite_beats_best_fixed": bool(avg_score is not None and avg_score < best_score),
            "selected_window_counts": {str(int(k)): int(v) for k, v in selected.value_counts().sort_index().items()},
        }
    beat_count = sum(1 for item in by_ticker.values() if item["saws_lite_beats_best_fixed"])
    deltas = [item["saws_lite_minus_best_fixed_score"] for item in by_ticker.values() if item["saws_lite_minus_best_fixed_score"] is not None]
    return {
        "method": "saws_lite_deterministic_threshold",
        "scale": float(scale),
        "ticker_summaries": by_ticker,
        "beats_best_fixed_count": int(beat_count),
        "average_minus_best_fixed_score": float(np.mean(deltas)) if deltas else None,
    }


def _zero_00631l_to_0050(weights: dict[str, float]) -> dict[str, float]:
    shifted = dict(weights)
    amount = float(shifted.get("00631L.TW", 0.0) or 0.0)
    shifted["00631L.TW"] = 0.0
    shifted["0050.TW"] = float(shifted.get("0050.TW", 0.0) or 0.0) + amount
    return _normalize(shifted)


def _weights_by_regime(latest_report: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = latest_report.get("base_weights") or latest_report.get("weights") or {}
    out = {str(name): _normalize(dict(weights or {})) for name, weights in raw.items()}
    if "golden1" not in out:
        raise ValueError("latest report does not include golden1 base weights")
    return out


def _portfolio_replay(
    *,
    db_path: Path,
    start: str,
    end: str,
    initial_value: float,
    baws_report: dict[str, Any],
    forecasts: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    latest_report, frame = run_latest(start, end, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    weights = _weights_by_regime(latest_report)
    guarded_weights = dict(weights)
    guarded_name = "golden1__baws_no_00631l_add_proxy"
    guarded_weights[guarded_name] = _zero_00631l_to_0050(weights["golden1"])

    signal = forecasts[forecasts["ticker"] == "00631L.TW"].copy()
    signal["date"] = pd.to_datetime(signal["date"]).dt.normalize()
    signal = signal.set_index("date").sort_index()
    warning_today = (signal["baws_breach"].astype(bool)) | (
        pd.to_numeric(signal["baws_window"], errors="coerce")
        <= min(baws_report["inputs"]["candidate_windows"])
    )
    warning_next_day = warning_today.shift(1, fill_value=False).astype(bool)
    warning_next_day = warning_next_day.reindex(frame.index, fill_value=False).astype(bool)

    guarded_regime = frame["execution_regime"].astype(str).copy()
    mask = (guarded_regime == "golden1") & warning_next_day
    guarded_regime.loc[mask] = guarded_name

    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    baseline_curve, baseline_exec = _simulate_costed_curve(
        total_return_prices,
        frame["execution_regime"].astype(str),
        weights,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    guarded_curve, guarded_exec = _simulate_costed_curve(
        total_return_prices,
        guarded_regime,
        guarded_weights,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    guarded_metrics = _metrics(guarded_curve, initial_value)
    delta = {
        key: float(guarded_metrics[key] - baseline_metrics[key])
        for key in ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    }
    curves = pd.DataFrame(
        {
            "baseline_latest": baseline_curve,
            "baws_no_00631l_add_proxy": guarded_curve,
            "execution_regime": frame["execution_regime"].astype(str),
            "proxy_execution_regime": guarded_regime.astype(str),
            "baws_00631l_warning_prev_day": warning_next_day.astype(int),
        }
    )
    return {
        "policy": "previous_day_baws_breach_or_short_window_shifts_00631l_to_0050_in_golden1",
        "active_strategy_id": latest_report.get("active_strategy_id"),
        "guard_days": int(mask.sum()),
        "baseline_execution": baseline_exec,
        "proxy_execution": guarded_exec,
        "dividend_coverage": dividend_coverage,
        "metrics": {
            "baseline_latest": baseline_metrics,
            "baws_no_00631l_add_proxy": guarded_metrics,
            "delta_proxy_minus_baseline": delta,
        },
        "promotion_ready": bool(delta["final_value"] > 0 and delta["sortino_ratio"] > 0 and delta["max_drawdown"] >= 0),
    }, curves


def _run_baws_variant(
    *,
    db_path: Path,
    start: str,
    end: str,
    candidate_windows: tuple[int, ...],
    alpha: float,
    evaluation_window: int,
    beta: float,
    bootstrap_samples: int,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    return BAWS.build_report(
        db_path=db_path,
        start=start,
        end=end,
        tickers=tuple(TICKERS),
        candidate_windows=candidate_windows,
        alpha=alpha,
        evaluation_window=evaluation_window,
        beta=beta,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )


def build_extended_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    initial_value: float,
    candidate_windows: tuple[int, ...],
    alpha: float,
    evaluation_window: int,
    betas: tuple[float, ...],
    bootstrap_samples_grid: tuple[int, ...],
    saws_scale: float,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    base_beta = betas[0]
    base_bootstrap = bootstrap_samples_grid[-1]
    base_report, base_forecasts = _run_baws_variant(
        db_path=db_path,
        start=start,
        end=end,
        candidate_windows=candidate_windows,
        alpha=alpha,
        evaluation_window=evaluation_window,
        beta=base_beta,
        bootstrap_samples=base_bootstrap,
        seed=seed,
    )

    robustness = []
    for beta in betas:
        for samples in bootstrap_samples_grid:
            report, _ = _run_baws_variant(
                db_path=db_path,
                start=start,
                end=end,
                candidate_windows=candidate_windows,
                alpha=alpha,
                evaluation_window=evaluation_window,
                beta=beta,
                bootstrap_samples=samples,
                seed=seed,
            )
            decision = report["aggregate_decision"]
            robustness.append(
                {
                    "beta": float(beta),
                    "bootstrap_samples": int(samples),
                    "baws_beats_best_fixed_count": decision["baws_beats_best_fixed_count"],
                    "average_baws_minus_best_fixed_score": decision["average_baws_minus_best_fixed_score"],
                    "promotion_ready": decision["promotion_ready"],
                    "selected_window_counts": {
                        ticker: summary["selected_window_counts"]
                        for ticker, summary in report["ticker_summaries"].items()
                    },
                }
            )

    fz_summary_by_ticker = {}
    for ticker, group in base_forecasts.groupby("ticker"):
        fz_summary_by_ticker[str(ticker)] = _method_fz_summary(group, candidate_windows, alpha)
    fz_beat_count = sum(1 for item in fz_summary_by_ticker.values() if item["comparison"]["baws_beats_best_fixed_fz0"])
    fz_deltas = [
        item["comparison"]["baws_minus_best_fixed_fz0_score"]
        for item in fz_summary_by_ticker.values()
        if item["comparison"]["baws_minus_best_fixed_fz0_score"] is not None
    ]

    saws_summary = _saws_lite_summary(base_forecasts, candidate_windows, evaluation_window, saws_scale)
    portfolio, curves = _portfolio_replay(
        db_path=db_path,
        start=start,
        end=end,
        initial_value=initial_value,
        baws_report=base_report,
        forecasts=base_forecasts,
    )

    promotion_ready = bool(
        base_report["aggregate_decision"]["promotion_ready"]
        and fz_beat_count == len(fz_summary_by_ticker)
        and saws_summary["beats_best_fixed_count"] > 0
        and portfolio["promotion_ready"]
    )
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_baws_extended_experiments",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting",
        "policy": "research_only_no_active_weight_or_order_change",
        "inputs": {
            "db": str(db_path),
            "window": {"start": start, "end": end},
            "initial_value": float(initial_value),
            "candidate_windows": list(candidate_windows),
            "alpha": float(alpha),
            "evaluation_window": int(evaluation_window),
            "base_beta": float(base_beta),
            "base_bootstrap_samples": int(base_bootstrap),
            "betas": list(betas),
            "bootstrap_samples_grid": list(bootstrap_samples_grid),
            "saws_scale": float(saws_scale),
            "seed": int(seed),
        },
        "base_baws_decision": base_report["aggregate_decision"],
        "base_baws_ticker_summaries": base_report["ticker_summaries"],
        "fz0_joint_var_es_summary": {
            "ticker_summaries": fz_summary_by_ticker,
            "baws_beats_best_fixed_count": int(fz_beat_count),
            "average_baws_minus_best_fixed_fz0_score": float(np.mean(fz_deltas)) if fz_deltas else None,
        },
        "saws_lite_comparison": saws_summary,
        "robustness_grid": robustness,
        "portfolio_replay": portfolio,
        "decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "promotion_ready": promotion_ready,
            "recommended_use": "keep_research_only",
            "reason": (
                "BAWS must improve quantile score, FZ-style joint score, comparator robustness, "
                "and portfolio replay before promotion; current evidence does not clear that bar."
            ),
        },
    }
    return report, curves


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    base = report["base_baws_decision"]
    fz = report["fz0_joint_var_es_summary"]
    saws = report["saws_lite_comparison"]
    port = report["portfolio_replay"]
    delta = port["metrics"]["delta_proxy_minus_baseline"]
    lines = [
        "# GroupA+ BAWS Extended Experiments",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source paper: `{report['source_paper']}`",
        f"- Policy: `{report['policy']}`",
        f"- Promotion ready: `{report['decision']['promotion_ready']}`",
        "",
        "## Summary",
        "",
        f"- BAWS quantile-score wins: `{base['baws_beats_best_fixed_count']}/{base['tickers_evaluated']}`",
        f"- BAWS average quantile-score delta vs best fixed: `{base['average_baws_minus_best_fixed_score']}`",
        f"- BAWS FZ-style wins: `{fz['baws_beats_best_fixed_count']}/{base['tickers_evaluated']}`",
        f"- BAWS average FZ-style delta vs best fixed: `{fz['average_baws_minus_best_fixed_fz0_score']}`",
        f"- SAWS-like wins: `{saws['beats_best_fixed_count']}/{base['tickers_evaluated']}`",
        f"- Portfolio guard days: `{port['guard_days']}`",
        "",
        "## Portfolio Replay",
        "",
        "| Metric | Delta proxy - baseline |",
        "|---|---:|",
        f"| final_value | {delta['final_value']:.2f} |",
        f"| annual_return | {delta['annual_return']:.6f} |",
        f"| sharpe_ratio | {delta['sharpe_ratio']:.6f} |",
        f"| sortino_ratio | {delta['sortino_ratio']:.6f} |",
        f"| max_drawdown | {delta['max_drawdown']:.6f} |",
        "",
        "## Decision",
        "",
        report["decision"]["reason"],
        "",
        "Research-only. No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], curves: pd.DataFrame, *, output_json: Path, output_csv: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    curves.to_csv(output_csv, encoding="utf-8-sig")
    _write_markdown(report, output_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--candidate-windows", default="63,126,252,504")
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--evaluation-window", type=int, default=63)
    parser.add_argument("--betas", default="0.80,0.90,0.95")
    parser.add_argument("--bootstrap-samples-grid", default="200,1000")
    parser.add_argument("--saws-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=260301157)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report, curves = build_extended_report(
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        initial_value=args.initial_value,
        candidate_windows=_parse_int_tuple(args.candidate_windows),
        alpha=args.alpha,
        evaluation_window=args.evaluation_window,
        betas=_parse_float_tuple(args.betas),
        bootstrap_samples_grid=_parse_int_tuple(args.bootstrap_samples_grid),
        saws_scale=args.saws_scale,
        seed=args.seed,
    )
    write_outputs(
        report,
        curves,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        output_md=_resolve(args.output_md),
    )
    print(
        json.dumps(
            {
                "promotion_ready": report["decision"]["promotion_ready"],
                "baws_quantile_wins": report["base_baws_decision"]["baws_beats_best_fixed_count"],
                "baws_fz0_wins": report["fz0_joint_var_es_summary"]["baws_beats_best_fixed_count"],
                "saws_lite_wins": report["saws_lite_comparison"]["beats_best_fixed_count"],
                "portfolio_guard_days": report["portfolio_replay"]["guard_days"],
                "portfolio_final_value_delta": report["portfolio_replay"]["metrics"]["delta_proxy_minus_baseline"]["final_value"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
