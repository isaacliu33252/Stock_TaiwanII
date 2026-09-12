#!/usr/bin/env python3
"""Build GroupA+ SCR readiness review for arXiv:2602.24037."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

DEFAULT_PDF = Path("/mnt/c/Users/isaac/Downloads/2602.24037.pdf")
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2602_24037_scr_readiness_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2602_24037_scr_readiness_review/history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _read_pdf_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    try:
        reader = PdfReader(str(path))
        metadata = reader.metadata or {}
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        pages = len(reader.pages)
        extract_error = None
    except Exception as exc:
        metadata = {}
        text = ""
        pages = None
        extract_error = type(exc).__name__
    return {
        "path": str(path),
        "exists": True,
        "pages": pages,
        "title": str(metadata.get("/Title") or "Portfolio Reinforcement Learning with Scenario-Context Rollout"),
        "authors": str(metadata.get("/Author") or "Vanya Priscillia Bendatu; Yao Lu"),
        "arxiv": str(metadata.get("/arXivID") or "https://arxiv.org/abs/2602.24037v1"),
        "doi": str(metadata.get("/DOI") or "https://doi.org/10.48550/arXiv.2602.24037"),
        "text_chars": len(text),
        "text_extract_error": extract_error,
        "key_claims": [
            "macro-conditioned scenario-context rollout generates plausible next-day multivariate return scenarios",
            "scenario rewards with tape-realized continuations create reward-transition mismatch in TD learning",
            "counterfactual continuation mixing gives a bias-variance tradeoff for the critic target",
            "paper reports higher Sharpe, lower max drawdown, and much lower turnover across U.S. stock/ETF universes",
        ],
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _target_weights(live_signal_path: Path, tickers: tuple[str, ...]) -> dict[str, float]:
    payload = _load_json(live_signal_path)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw = data.get("target_weights") if isinstance(data, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    return {ticker: float(raw.get(ticker) or 0.0) for ticker in tickers}


def _load_close(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _feature_frame(returns: pd.DataFrame, base: str) -> pd.DataFrame:
    features = pd.DataFrame(index=returns.index)
    features["base_ret_1d"] = returns[base]
    features["base_vol_20d"] = returns[base].rolling(20).std()
    features["base_mom_5d"] = returns[base].rolling(5).sum()
    base_equity = (1.0 + returns[base].fillna(0.0)).cumprod()
    features["base_drawdown_60d"] = base_equity / base_equity.rolling(60).max() - 1.0
    for ticker in returns.columns:
        if ticker == base:
            continue
        features[f"corr_{ticker}_60d"] = returns[base].rolling(60).corr(returns[ticker])
    return features.replace([np.inf, -np.inf], np.nan)


def _portfolio_returns(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=returns.index)
    for ticker, weight in weights.items():
        if ticker in returns.columns:
            out = out.add(returns[ticker].fillna(0.0) * float(weight), fill_value=0.0)
    return out


def _scenario_audit(
    returns: pd.DataFrame,
    features: pd.DataFrame,
    portfolio_returns: pd.Series,
    *,
    eval_start: str,
    min_history: int,
    k_neighbors: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    usable = features.dropna()
    if usable.empty:
        return rows
    dates = [idx for idx in usable.index if str(idx.date()) >= eval_start]
    next_returns = portfolio_returns.shift(-1)
    for dt in dates:
        loc = usable.index.get_loc(dt)
        if isinstance(loc, slice) or isinstance(loc, np.ndarray) or int(loc) < min_history:
            continue
        history = usable.iloc[: int(loc)].dropna()
        history = history.loc[next_returns.loc[history.index].dropna().index]
        if len(history) < min_history:
            continue
        current = usable.loc[dt]
        sigma = history.std(ddof=0).replace(0.0, np.nan)
        normalized_history = (history - history.mean()) / sigma
        normalized_current = (current - history.mean()) / sigma
        distances = ((normalized_history - normalized_current) ** 2).sum(axis=1).pow(0.5).dropna()
        if len(distances) < k_neighbors:
            continue
        selected = distances.nsmallest(k_neighbors).index
        scenario = next_returns.loc[selected].dropna()
        realized = next_returns.loc[dt]
        if scenario.empty or not np.isfinite(realized):
            continue
        scenario_mean = float(scenario.mean())
        scenario_var = float(scenario.var(ddof=0))
        gap = scenario_mean - float(realized)
        rows.append(
            {
                "date": str(dt.date()),
                "scenario_mean_next_return": _float(scenario_mean),
                "realized_next_return": _float(realized),
                "scenario_variance": _float(scenario_var, digits=10),
                "abs_gap": _float(abs(gap)),
                "signed_gap": _float(gap),
                "neighbor_count": int(len(scenario)),
            }
        )
    return rows


def _summarize_rows(rows: list[dict[str, Any]], *, gap_limit: float) -> dict[str, Any]:
    if not rows:
        return {"status": "insufficient_data", "oos_days": 0}
    gaps = np.array([float(row["abs_gap"]) for row in rows if row.get("abs_gap") is not None], dtype=float)
    variances = np.array(
        [float(row["scenario_variance"]) for row in rows if row.get("scenario_variance") is not None],
        dtype=float,
    )
    mse = float(np.mean(gaps**2)) if len(gaps) else np.nan
    mean_var = float(np.mean(variances)) if len(variances) else np.nan
    beta_cf = mse / (mse + mean_var) if np.isfinite(mse + mean_var) and (mse + mean_var) > 0 else None
    pass_gap = bool(np.isfinite(np.mean(gaps)) and float(np.mean(gaps)) <= gap_limit)
    return {
        "status": "available",
        "oos_days": int(len(rows)),
        "mean_abs_scenario_real_gap": _float(np.mean(gaps)),
        "median_abs_scenario_real_gap": _float(np.median(gaps)),
        "p90_abs_scenario_real_gap": _float(np.quantile(gaps, 0.90)),
        "mean_scenario_variance": _float(mean_var, digits=10),
        "mismatch_mse": _float(mse, digits=10),
        "beta_cf_from_bias_variance_proxy": _float(beta_cf) if beta_cf is not None else None,
        "gap_limit": gap_limit,
        "scenario_real_gap_gate_passed": pass_gap,
    }


def build_review(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    start: str = "2018-01-02",
    end: str = "latest",
    eval_start: str = "2024-01-02",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    min_history: int = 504,
    k_neighbors: int = 30,
    gap_limit: float = 0.01,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    pdf = _read_pdf_summary(pdf_path)
    if not pdf.get("exists"):
        blockers.append("source_pdf_missing")
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
        end_resolved = end
    else:
        end_resolved = _resolve_end_date(db_path, end) if end == "latest" else end
        close = _load_close(db_path, tickers, start, end_resolved)
    if close.empty or base not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    weights = _target_weights(live_signal_path, tickers)
    if not live_signal_path.exists():
        warnings.append("live_signal_missing_using_zero_weights")
    if sum(abs(value) for value in weights.values()) <= 0:
        blockers.append("target_weights_missing")

    available = tuple(ticker for ticker in tickers if ticker in returns.columns and returns[ticker].notna().sum() > min_history)
    if base not in available:
        blockers.append("base_has_insufficient_history")
    features = _feature_frame(returns[list(available)], base) if base in available else pd.DataFrame()
    port_rets = _portfolio_returns(returns[list(available)], weights) if available else pd.Series(dtype=float)
    rows = _scenario_audit(
        returns[list(available)] if available else returns,
        features,
        port_rets,
        eval_start=eval_start,
        min_history=min_history,
        k_neighbors=k_neighbors,
    )
    summary = _summarize_rows(rows, gap_limit=gap_limit)

    if summary.get("scenario_real_gap_gate_passed") is not True:
        warnings.append("scenario_real_gap_gate_not_passed")
    beta = summary.get("beta_cf_from_bias_variance_proxy")
    beta_in_paper_sweet_spot = isinstance(beta, (int, float)) and 0.25 <= float(beta) <= 0.75
    if not beta_in_paper_sweet_spot:
        warnings.append("beta_cf_proxy_outside_paper_moderate_range")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2602_24037_scr_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked_for_live_promotion" if blockers else "available_for_shadow_review",
        "policy": "research_shadow_only_no_rl_training_no_live_weight_change",
        "source_paper": pdf,
        "groupa_plus_mapping": {
            "importable_advantage": "scenario_context_rollout_readiness_and_reward_transition_mismatch_guard",
            "implemented_as": "nearest_neighbor_scenario_to_real_gap_audit_for_current_groupa_plus_weights",
            "paper_equivalent": False,
            "reason_not_exact": "The paper trains SCR-PPO on U.S. universes; this review only audits whether Taiwan ETF data support future SCR-style shadow training.",
        },
        "parameters": {
            "start": start,
            "end": end_resolved,
            "eval_start": eval_start,
            "tickers": list(tickers),
            "available_tickers": list(available),
            "base": base,
            "min_history": min_history,
            "k_neighbors": k_neighbors,
            "gap_limit": gap_limit,
            "live_signal_path": str(live_signal_path),
            "reference_weights": weights,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "feature_observations": int(len(features.dropna())) if not features.empty else 0,
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "summary": summary,
        "recent_rows_tail": rows[-10:],
        "paper_result_context": {
            "reported_oos_split": "train 2009-2017, validation 2018-2019, test 2020-2023",
            "reported_universes": 31,
            "reported_beta_cf_sweet_spot": 0.50,
            "reported_market_proxy_sharpe_historical_ppo_to_scr_full": "0.492 -> 1.004",
            "reported_market_proxy_maxdd_historical_ppo_to_scr_full": "0.370 -> 0.179",
            "reported_ablation_gap_final_historical_ppo_to_scr_full": "0.526 -> 0.0001",
        },
        "decision": {
            "review_complete": True,
            "has_importable_advantage": True,
            "best_import": "scr_readiness_and_mismatch_guard_only",
            "scr_shadow_training_allowed_by_this_review": False,
            "ppo_training_allowed": False,
            "model_training_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "allow_00679b_add": False,
            "counterfactual_bootstrap_beta_cf_candidate": beta,
            "beta_cf_candidate_in_paper_moderate_range": beta_in_paper_sweet_spot,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def render_markdown(review: dict[str, Any]) -> str:
    summary = review["summary"]
    lines = [
        "# 2602.24037 SCR Readiness Review",
        "",
        f"Generated: `{review['generated_at']}`",
        f"Status: `{review['status']}`",
        "",
        "## Decision",
        "",
        "- Best import: `scr_readiness_and_mismatch_guard_only`.",
        "- Do not train SCR-PPO from this review.",
        "- Do not change target weights or rebalance.",
        "- Do not add `00631L.TW`, open `00632R.TW`, or add `00679B.TWO` from this paper.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Scenario-To-Real Audit",
        "",
        f"- OOS days: `{summary.get('oos_days')}`",
        f"- Mean abs gap: `{summary.get('mean_abs_scenario_real_gap')}`",
        f"- Median abs gap: `{summary.get('median_abs_scenario_real_gap')}`",
        f"- P90 abs gap: `{summary.get('p90_abs_scenario_real_gap')}`",
        f"- Mean scenario variance: `{summary.get('mean_scenario_variance')}`",
        f"- Beta cf proxy: `{summary.get('beta_cf_from_bias_variance_proxy')}`",
        f"- Gap gate passed: `{summary.get('scenario_real_gap_gate_passed')}`",
        "",
        "## Interpretation",
        "",
        (
            "This is a Taiwan ETF shadow audit of the paper's reward-transition mismatch warning. "
            "It checks whether nearest-neighbor scenario returns are close enough to realized tape returns "
            "before any future SCR-style RL training could be considered."
        ),
        "",
    ]
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2602_24037_scr_readiness_review_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(review) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = str(review.get("parameters", {}).get("end") or datetime.now().strftime("%Y-%m-%d"))
        _history_path(history_dir, as_of).write_text(
            json.dumps(review, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--eval-start", default="2024-01-02")
    parser.add_argument("--min-history", type=int, default=504)
    parser.add_argument("--k-neighbors", type=int, default=30)
    parser.add_argument("--gap-limit", type=float, default=0.01)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        pdf_path=_resolve(args.pdf),
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        start=args.start,
        end=args.end,
        eval_start=args.eval_start,
        min_history=args.min_history,
        k_neighbors=args.k_neighbors,
        gap_limit=args.gap_limit,
    )
    write_review(
        review,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"2602.24037 SCR readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "summary": review["summary"],
                "decision": review["decision"],
                "warnings": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
