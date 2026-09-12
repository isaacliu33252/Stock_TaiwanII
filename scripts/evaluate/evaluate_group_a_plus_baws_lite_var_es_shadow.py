#!/usr/bin/env python3
"""BAWS-lite adaptive-window VaR/ES shadow diagnostic for GroupA+.

Research-only implementation inspired by arXiv:2603.01157v2, "Adaptive
Window Selection for Financial Risk Forecasting".  It tests whether an
adaptive historical window improves one-day loss VaR forecasts versus fixed
windows for the GroupA+ ETF universe.  It never changes target weights,
golden1_0531, latest strategy manifests, live signals, or execution plans.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/group_a_plus_baws_lite_var_es_shadow_latest.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "results/group_a_plus_baws_lite_var_es_shadow_forecasts_latest.csv"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/baws_lite_var_es_shadow.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize() - pd.Timedelta(days=warmup_days)
    end_ts = pd.Timestamp(end).normalize()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(tickers), str(start_ts.date()), str(end_ts.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows found for {tickers} from {start_ts.date()} to {end_ts.date()}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index().astype(float)


def quantile_score(loss: float, forecast_var: float, alpha: float) -> float:
    """Pinball/check loss for an alpha-quantile loss forecast."""
    if not (math.isfinite(loss) and math.isfinite(forecast_var)):
        return float("nan")
    return float((alpha - (1.0 if loss <= forecast_var else 0.0)) * (loss - forecast_var))


def historical_var_es(losses: pd.Series, window: int, alpha: float) -> tuple[float | None, float | None]:
    clean = pd.to_numeric(losses, errors="coerce").dropna().tail(window)
    if len(clean) < max(20, min(window, 20)):
        return None, None
    var = float(np.quantile(clean.to_numpy(dtype=float), alpha))
    tail = clean[clean >= var]
    es = float(tail.mean()) if len(tail) else var
    return var, es


def _moving_block_bootstrap_threshold(
    diffs: np.ndarray,
    *,
    beta: float,
    samples: int,
    seed: int,
) -> float:
    clean = diffs[np.isfinite(diffs)]
    if len(clean) < 8:
        return 0.0
    # Codex 2026-08-13: deterministic moving-block bootstrap approximation of
    # BAWS admissibility; this remains shadow-only until OOS evidence is strong.
    block_len = max(1, int(math.ceil(len(clean) ** (1.0 / 3.0))))
    rng = np.random.default_rng(seed)
    max_start = max(len(clean) - block_len + 1, 1)
    n_blocks = int(math.ceil(len(clean) / block_len))
    starts = rng.integers(0, max_start, size=(samples, n_blocks))
    offsets = np.arange(block_len, dtype=int)
    indices = (starts[:, :, None] + offsets[None, None, :]).reshape(samples, n_blocks * block_len)
    indices = np.minimum(indices[:, : len(clean)], len(clean) - 1)
    means = clean[indices].mean(axis=1)
    return float(max(0.0, np.quantile(means, beta)))


def _forecast_score_at(losses: pd.Series, pos: int, window: int, alpha: float) -> tuple[float | None, float | None, float | None]:
    var, es = historical_var_es(losses.iloc[:pos], window, alpha)
    if var is None:
        return None, None, None
    return var, es, quantile_score(float(losses.iloc[pos]), var, alpha)


def _rolling_tail_mean(values: np.ndarray, alpha: float) -> float:
    clean = values[np.isfinite(values)]
    if len(clean) == 0:
        return float("nan")
    var = float(np.quantile(clean, alpha))
    tail = clean[clean >= var]
    return float(np.mean(tail)) if len(tail) else var


def precompute_fixed_window_forecasts(
    losses: pd.Series,
    *,
    candidate_windows: tuple[int, ...],
    alpha: float,
) -> pd.DataFrame:
    """Precompute all fixed-window forecasts used by BAWS-lite selection."""
    out = pd.DataFrame({"realized_loss": losses.astype(float)})
    for window in candidate_windows:
        rolling = losses.rolling(window=window, min_periods=max(20, min(window, 20)))
        var = rolling.quantile(alpha).shift(1)
        es = rolling.apply(lambda arr: _rolling_tail_mean(arr, alpha), raw=True).shift(1)
        out[f"fixed_{window}_var"] = var
        out[f"fixed_{window}_es"] = es
        out[f"fixed_{window}_score"] = [
            quantile_score(float(loss), float(forecast), alpha)
            if pd.notna(loss) and pd.notna(forecast)
            else np.nan
            for loss, forecast in zip(out["realized_loss"], var, strict=False)
        ]
        out[f"fixed_{window}_breach"] = out["realized_loss"] > var
    return out


def select_baws_window(
    losses: pd.Series,
    *,
    pos: int,
    candidate_windows: tuple[int, ...],
    alpha: float,
    evaluation_window: int,
    beta: float,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    windows = tuple(sorted(int(w) for w in candidate_windows))
    reference = windows[0]
    start_eval = max(reference, pos - evaluation_window)
    eval_positions = range(start_eval, pos)
    admissible: list[int] = []
    diagnostics: dict[str, Any] = {}
    for window in windows:
        candidate_scores = []
        reference_scores = []
        for eval_pos in eval_positions:
            _, _, cand_score = _forecast_score_at(losses, eval_pos, window, alpha)
            _, _, ref_score = _forecast_score_at(losses, eval_pos, reference, alpha)
            if cand_score is None or ref_score is None:
                continue
            candidate_scores.append(cand_score)
            reference_scores.append(ref_score)
        diff = np.asarray(candidate_scores, dtype=float) - np.asarray(reference_scores, dtype=float)
        mean_diff = float(np.nanmean(diff)) if len(diff) else float("inf")
        threshold = _moving_block_bootstrap_threshold(
            diff,
            beta=beta,
            samples=bootstrap_samples,
            seed=seed + pos + window,
        )
        ok = bool(len(diff) >= max(10, evaluation_window // 3) and mean_diff <= threshold)
        if ok:
            admissible.append(window)
        diagnostics[str(window)] = {
            "evaluation_count": int(len(diff)),
            "mean_score_diff_vs_reference": None if not math.isfinite(mean_diff) else mean_diff,
            "bootstrap_threshold": threshold,
            "admissible": ok,
        }
    selected = max(admissible) if admissible else reference
    return {
        "selected_window": int(selected),
        "reference_window": int(reference),
        "candidate_diagnostics": diagnostics,
    }


def select_baws_window_from_precomputed(
    fixed: pd.DataFrame,
    *,
    pos: int,
    candidate_windows: tuple[int, ...],
    evaluation_window: int,
    beta: float,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    windows = tuple(sorted(int(w) for w in candidate_windows))
    reference = windows[0]
    start_eval = max(0, pos - evaluation_window)
    admissible: list[int] = []
    diagnostics: dict[str, Any] = {}
    reference_scores = pd.to_numeric(fixed.iloc[start_eval:pos][f"fixed_{reference}_score"], errors="coerce")
    for window in windows:
        candidate_scores = pd.to_numeric(fixed.iloc[start_eval:pos][f"fixed_{window}_score"], errors="coerce")
        aligned = pd.concat([candidate_scores.rename("candidate"), reference_scores.rename("reference")], axis=1).dropna()
        diff = aligned["candidate"].to_numpy(dtype=float) - aligned["reference"].to_numpy(dtype=float)
        mean_diff = float(np.nanmean(diff)) if len(diff) else float("inf")
        threshold = _moving_block_bootstrap_threshold(
            diff,
            beta=beta,
            samples=bootstrap_samples,
            seed=seed + pos + window,
        )
        ok = bool(len(diff) >= max(10, evaluation_window // 3) and mean_diff <= threshold)
        if ok:
            admissible.append(window)
        diagnostics[str(window)] = {
            "evaluation_count": int(len(diff)),
            "mean_score_diff_vs_reference": None if not math.isfinite(mean_diff) else mean_diff,
            "bootstrap_threshold": threshold,
            "admissible": ok,
        }
    selected = max(admissible) if admissible else reference
    return {
        "selected_window": int(selected),
        "reference_window": int(reference),
        "candidate_diagnostics": diagnostics,
    }


def build_forecasts(
    returns: pd.Series,
    *,
    start: str,
    candidate_windows: tuple[int, ...],
    alpha: float,
    evaluation_window: int,
    beta: float,
    bootstrap_samples: int,
    seed: int,
) -> pd.DataFrame:
    losses = (-pd.to_numeric(returns, errors="coerce")).dropna()
    start_ts = pd.Timestamp(start).normalize()
    fixed = precompute_fixed_window_forecasts(losses, candidate_windows=candidate_windows, alpha=alpha)
    rows: list[dict[str, Any]] = []
    min_pos = max(max(candidate_windows), evaluation_window) + 1
    for pos in range(min_pos, len(losses)):
        dt = losses.index[pos]
        if dt < start_ts:
            continue
        selected = select_baws_window_from_precomputed(
            fixed,
            pos=pos,
            candidate_windows=candidate_windows,
            evaluation_window=evaluation_window,
            beta=beta,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        baws_var = fixed.iloc[pos][f"fixed_{selected['selected_window']}_var"]
        baws_es = fixed.iloc[pos][f"fixed_{selected['selected_window']}_es"]
        realized = float(losses.iloc[pos])
        row = {
            "date": dt,
            "realized_loss": realized,
            "baws_window": int(selected["selected_window"]),
            "baws_var": baws_var,
            "baws_es": baws_es,
            "baws_score": quantile_score(realized, float(baws_var), alpha) if baws_var is not None else np.nan,
            "baws_breach": bool(baws_var is not None and realized > baws_var),
        }
        for window in candidate_windows:
            var = fixed.iloc[pos][f"fixed_{window}_var"]
            es = fixed.iloc[pos][f"fixed_{window}_es"]
            row[f"fixed_{window}_var"] = var
            row[f"fixed_{window}_es"] = es
            row[f"fixed_{window}_score"] = quantile_score(realized, float(var), alpha) if var is not None else np.nan
            row[f"fixed_{window}_breach"] = bool(var is not None and realized > var)
        rows.append(row)
    return pd.DataFrame(rows).set_index("date").sort_index()


def _summarize_forecasts(frame: pd.DataFrame, candidate_windows: tuple[int, ...], alpha: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    expected_breach = float(1.0 - alpha)
    methods = ["baws"] + [f"fixed_{w}" for w in candidate_windows]
    for method in methods:
        scores = pd.to_numeric(frame[f"{method}_score"], errors="coerce").dropna()
        breaches = frame.loc[scores.index, f"{method}_breach"].astype(bool) if len(scores) else pd.Series(dtype=bool)
        var_col = pd.to_numeric(frame.loc[scores.index, f"{method}_var"], errors="coerce") if len(scores) else pd.Series(dtype=float)
        es_col = pd.to_numeric(frame.loc[scores.index, f"{method}_es"], errors="coerce") if len(scores) else pd.Series(dtype=float)
        realized = pd.to_numeric(frame.loc[scores.index, "realized_loss"], errors="coerce") if len(scores) else pd.Series(dtype=float)
        tail_gap = realized[breaches] - es_col[breaches] if len(scores) else pd.Series(dtype=float)
        out[method] = {
            "forecast_count": int(len(scores)),
            "average_quantile_score": float(scores.mean()) if len(scores) else None,
            "breach_rate": float(breaches.mean()) if len(breaches) else None,
            "breach_rate_error_vs_nominal": float(abs(float(breaches.mean()) - expected_breach)) if len(breaches) else None,
            "average_var_loss": float(var_col.mean()) if len(var_col) else None,
            "average_es_loss": float(es_col.mean()) if len(es_col) else None,
            "average_tail_loss_minus_es_on_breach": float(tail_gap.mean()) if len(tail_gap) else None,
        }
    best_fixed = min(
        (f"fixed_{w}" for w in candidate_windows),
        key=lambda name: out[name]["average_quantile_score"]
        if out[name]["average_quantile_score"] is not None
        else float("inf"),
    )
    baws_score = out["baws"]["average_quantile_score"]
    best_score = out[best_fixed]["average_quantile_score"]
    out["comparison"] = {
        "best_fixed_method": best_fixed,
        "baws_minus_best_fixed_score": None if baws_score is None or best_score is None else float(baws_score - best_score),
        "baws_beats_best_fixed_score": bool(baws_score is not None and best_score is not None and baws_score < best_score),
    }
    out["selected_window_counts"] = {
        str(int(k)): int(v) for k, v in frame["baws_window"].value_counts().sort_index().items()
    }
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    tickers: tuple[str, ...],
    candidate_windows: tuple[int, ...],
    alpha: float,
    evaluation_window: int,
    beta: float,
    bootstrap_samples: int,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    prices = _load_close_panel(db_path, tickers, start, end, warmup_days=max(candidate_windows) * 3)
    returns = prices.pct_change().dropna(how="all")
    forecast_frames: list[pd.DataFrame] = []
    summaries: dict[str, Any] = {}
    for ticker in tickers:
        frame = build_forecasts(
            returns[ticker],
            start=start,
            candidate_windows=candidate_windows,
            alpha=alpha,
            evaluation_window=evaluation_window,
            beta=beta,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        if frame.empty:
            continue
        frame.insert(0, "ticker", ticker)
        forecast_frames.append(frame.reset_index())
        summaries[ticker] = _summarize_forecasts(frame, candidate_windows, alpha)
    forecasts = pd.concat(forecast_frames, ignore_index=True) if forecast_frames else pd.DataFrame()
    comparisons = [summary["comparison"] for summary in summaries.values()]
    beat_count = sum(1 for item in comparisons if item["baws_beats_best_fixed_score"])
    avg_delta = float(np.mean([item["baws_minus_best_fixed_score"] for item in comparisons if item["baws_minus_best_fixed_score"] is not None])) if comparisons else None
    latest = {}
    if not forecasts.empty:
        latest_rows = forecasts.sort_values("date").groupby("ticker").tail(1)
        latest = {
            str(row["ticker"]): {
                "date": str(pd.Timestamp(row["date"]).date()),
                "selected_window": int(row["baws_window"]),
                "var_loss": None if pd.isna(row["baws_var"]) else float(row["baws_var"]),
                "es_loss": None if pd.isna(row["baws_es"]) else float(row["baws_es"]),
                "realized_loss": None if pd.isna(row["realized_loss"]) else float(row["realized_loss"]),
                "breach": bool(row["baws_breach"]),
            }
            for _, row in latest_rows.iterrows()
        }
    promotion_ready = bool(beat_count == len(summaries) and len(summaries) > 0 and (avg_delta or 0.0) < 0.0)
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_baws_lite_var_es_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2603.01157v2 Adaptive Window Selection for Financial Risk Forecasting",
        "policy": "research_only_no_active_weight_or_order_change",
        "codex_note": "Codex 2026-08-13: BAWS-lite shadow diagnostic only; latest strategy and golden1_0531 are unchanged.",
        "inputs": {
            "db": str(db_path),
            "requested_window": {"start": start, "end": end},
            "actual_forecast_rows": int(len(forecasts)),
            "tickers": list(tickers),
            "candidate_windows": list(candidate_windows),
            "alpha": float(alpha),
            "nominal_breach_rate": float(1.0 - alpha),
            "evaluation_window": int(evaluation_window),
            "beta": float(beta),
            "bootstrap_samples": int(bootstrap_samples),
            "seed": int(seed),
        },
        "ticker_summaries": summaries,
        "latest_snapshot": latest,
        "aggregate_decision": {
            "tickers_evaluated": int(len(summaries)),
            "baws_beats_best_fixed_count": int(beat_count),
            "average_baws_minus_best_fixed_score": avg_delta,
            "promotion_ready": promotion_ready,
            "recommended_use": "promotion_gate_input_only" if promotion_ready else "keep_research_only",
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
        },
    }
    return report, forecasts


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    decision = report["aggregate_decision"]
    lines = [
        "# GroupA+ BAWS-lite VaR/ES Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source paper: `{report['source_paper']}`",
        f"- Policy: `{report['policy']}`",
        f"- Promotion ready: `{decision['promotion_ready']}`",
        f"- Average BAWS minus best fixed score: `{decision['average_baws_minus_best_fixed_score']}`",
        "",
        "## Ticker Results",
        "",
        "| Ticker | Best fixed | BAWS-best score delta | BAWS breach rate | Selected windows |",
        "|---|---:|---:|---:|---|",
    ]
    for ticker, summary in report["ticker_summaries"].items():
        comp = summary["comparison"]
        baws = summary["baws"]
        lines.append(
            f"| {ticker} | {comp['best_fixed_method']} | {comp['baws_minus_best_fixed_score']:.8f} | "
            f"{baws['breach_rate']:.6f} | {json.dumps(summary['selected_window_counts'], ensure_ascii=False)} |"
        )
    lines.extend(
        [
            "",
            "## Latest Snapshot",
            "",
            "| Ticker | Date | Window | VaR loss | ES loss | Latest realized loss | Breach |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for ticker, item in report["latest_snapshot"].items():
        lines.append(
            f"| {ticker} | {item['date']} | {item['selected_window']} | {item['var_loss']:.8f} | "
            f"{item['es_loss']:.8f} | {item['realized_loss']:.8f} | {item['breach']} |"
        )
    lines.extend(
        [
            "",
            "Codex 2026-08-13: research-only output; no active strategy, golden1_0531 artifact, live signal, execution plan, or order file is changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], forecasts: pd.DataFrame, *, output_json: Path, output_csv: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    forecasts.to_csv(output_csv, index=False, encoding="utf-8-sig")
    _write_markdown(report, output_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--tickers", default=",".join(TICKERS))
    parser.add_argument("--candidate-windows", default="63,126,252,504")
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--evaluation-window", type=int, default=63)
    parser.add_argument("--beta", type=float, default=0.90)
    parser.add_argument("--bootstrap-samples", type=int, default=200)
    parser.add_argument("--seed", type=int, default=260301157)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = tuple(item.strip() for item in args.tickers.split(",") if item.strip())
    candidate_windows = tuple(int(item.strip()) for item in args.candidate_windows.split(",") if item.strip())
    report, forecasts = build_report(
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        tickers=tickers,
        candidate_windows=candidate_windows,
        alpha=args.alpha,
        evaluation_window=args.evaluation_window,
        beta=args.beta,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    write_outputs(
        report,
        forecasts,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        output_md=_resolve(args.output_md),
    )
    print(
        json.dumps(
            {
                "promotion_ready": report["aggregate_decision"]["promotion_ready"],
                "baws_beats_best_fixed_count": report["aggregate_decision"]["baws_beats_best_fixed_count"],
                "tickers_evaluated": report["aggregate_decision"]["tickers_evaluated"],
                "average_baws_minus_best_fixed_score": report["aggregate_decision"]["average_baws_minus_best_fixed_score"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
