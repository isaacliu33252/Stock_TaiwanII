#!/usr/bin/env python3
"""Build a GroupA+ LETF tracking-error / effective-fee readiness review.

Inspired by 1610.09404. This is a research-only governance artifact for
00631L/00632R holding-horizon and hedge-neutrality risk; it never promotes a
pair trade or changes target weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/letf_tracking_error_effective_fee_readiness/history"
DEFAULT_INTERVENTION_FATIGUE = (
    PROJECT_ROOT / "report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json"
)
SOURCE_PAPER = "C:/Users/isaac/Downloads/1610.09404.pdf"
DEFAULT_PARAMETER_THRESHOLDS = {
    "00631l_30d_mean_tracking_error_floor": -0.003,
    "00631l_30d_latest_tracking_error_floor": -0.02,
    "00631l_30d_p05_tracking_error_floor": -0.05,
    "00631l_30d_latest_realized_variance_ceiling": 0.01,
    "00632r_60d_abs_beta_error_ceiling": 0.10,
    "00632r_60d_correlation_ceiling": -0.95,
    "00632r_30d_p05_tracking_error_floor": -0.03,
    "minimum_30d_observations": 500,
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _series_summary(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "p05": None,
            "p50": None,
            "p95": None,
            "latest": None,
        }
    return {
        "count": int(clean.shape[0]),
        "mean": _finite(clean.mean()),
        "std": _finite(clean.std(ddof=0)),
        "p05": _finite(clean.quantile(0.05)),
        "p50": _finite(clean.quantile(0.50)),
        "p95": _finite(clean.quantile(0.95)),
        "latest": _finite(clean.iloc[-1]),
    }


def _load_close_panel(
    db_path: Path,
    *,
    tickers: list[str],
    start: str,
    as_of: str | None,
) -> pd.DataFrame:
    end_clause = "AND dt <= ?" if as_of else ""
    params: list[Any] = [tickers, start]
    if as_of:
        params.append(as_of)
    query = f"""
        SELECT ticker, dt, close
        FROM ohlcv
        WHERE ticker IN ?
          AND dt >= ?
          {end_clause}
        ORDER BY dt, ticker
    """
    with duckdb.connect(str(db_path), read_only=True) as conn:
        df = conn.execute(query, params).fetchdf()
    if df.empty:
        return pd.DataFrame()
    df["dt"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
    return df.pivot(index="dt", columns="ticker", values="close").sort_index()


def _horizon_metrics(
    panel: pd.DataFrame,
    *,
    reference_ticker: str,
    letf_ticker: str,
    beta: float,
    horizons: list[int],
) -> dict[str, Any]:
    close = panel[[reference_ticker, letf_ticker]].dropna()
    ref_log = np.log(close[reference_ticker] / close[reference_ticker].shift(1))
    metrics: dict[str, Any] = {}
    for horizon in horizons:
        ref_h = np.log(close[reference_ticker] / close[reference_ticker].shift(horizon))
        letf_h = np.log(close[letf_ticker] / close[letf_ticker].shift(horizon))
        realized_variance = ref_log.pow(2).rolling(horizon).sum()
        variance_decay_proxy = ((beta - beta**2) / 2.0) * realized_variance
        tracking_error = letf_h - beta * ref_h
        effective_drag_proxy = tracking_error - variance_decay_proxy
        clean_te = tracking_error.dropna()
        recent_te = clean_te.tail(60)
        recent_drag = effective_drag_proxy.dropna().tail(60)
        metrics[str(horizon)] = {
            "horizon_days": horizon,
            "tracking_error": _series_summary(tracking_error),
            "effective_drag_proxy": _series_summary(effective_drag_proxy),
            "realized_variance": _series_summary(realized_variance),
            "variance_decay_proxy": _series_summary(variance_decay_proxy),
            "negative_tracking_error_rate": _finite((clean_te < 0).mean()) if not clean_te.empty else None,
            "recent_60_observations": {
                "mean_tracking_error": _finite(recent_te.mean()) if not recent_te.empty else None,
                "p05_tracking_error": _finite(recent_te.quantile(0.05)) if not recent_te.empty else None,
                "mean_effective_drag_proxy": _finite(recent_drag.mean()) if not recent_drag.empty else None,
            },
        }
    return metrics


def _hedge_neutrality(
    panel: pd.DataFrame,
    *,
    reference_ticker: str,
    inverse_ticker: str,
    expected_beta: float,
    lookback: int = 60,
) -> dict[str, Any]:
    close = panel[[reference_ticker, inverse_ticker]].dropna()
    returns = close.pct_change().dropna().tail(lookback)
    if returns.shape[0] < 2:
        return {
            "status": "insufficient_data",
            "lookback_days": lookback,
            "realized_beta": None,
            "expected_beta": expected_beta,
            "beta_error": None,
            "correlation": None,
        }
    ref = returns[reference_ticker]
    inv = returns[inverse_ticker]
    ref_var = float(ref.var(ddof=0))
    realized_beta = float(inv.cov(ref, ddof=0) / ref_var) if ref_var else np.nan
    corr = float(inv.corr(ref))
    beta_error = realized_beta - expected_beta
    return {
        "status": "review_only",
        "lookback_days": lookback,
        "realized_beta": _finite(realized_beta),
        "expected_beta": expected_beta,
        "beta_error": _finite(beta_error),
        "absolute_beta_error": _finite(abs(beta_error)),
        "correlation": _finite(corr),
    }


def _metric(
    tracking_error_summary: dict[str, Any],
    ticker: str,
    horizon: str,
    block: str,
    field: str,
) -> float | None:
    value = (
        (((tracking_error_summary.get(ticker) or {}).get("horizon_metrics") or {}).get(horizon) or {})
        .get(block, {})
        .get(field)
    )
    return _finite(value)


def _build_parameter_threshold_review(
    tracking_error_summary: dict[str, Any],
    hedge_neutrality: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    l31_h30_count = _metric(tracking_error_summary, "00631L.TW", "30", "tracking_error", "count")
    l31_mean_te = _metric(tracking_error_summary, "00631L.TW", "30", "tracking_error", "mean")
    l31_latest_te = _metric(tracking_error_summary, "00631L.TW", "30", "tracking_error", "latest")
    l31_p05_te = _metric(tracking_error_summary, "00631L.TW", "30", "tracking_error", "p05")
    l31_latest_rv = _metric(tracking_error_summary, "00631L.TW", "30", "realized_variance", "latest")
    r32_h30_count = _metric(tracking_error_summary, "00632R.TW", "30", "tracking_error", "count")
    r32_p05_te = _metric(tracking_error_summary, "00632R.TW", "30", "tracking_error", "p05")
    r32_hedge = hedge_neutrality.get("00632R.TW") or {}
    r32_abs_beta_error = _finite(r32_hedge.get("absolute_beta_error"))
    r32_corr = _finite(r32_hedge.get("correlation"))

    checks = {
        "00631l_30d_mean_tracking_error_floor": {
            "value": l31_mean_te,
            "threshold": thresholds["00631l_30d_mean_tracking_error_floor"],
            "passed": l31_mean_te is not None and l31_mean_te >= thresholds["00631l_30d_mean_tracking_error_floor"],
        },
        "00631l_30d_latest_tracking_error_floor": {
            "value": l31_latest_te,
            "threshold": thresholds["00631l_30d_latest_tracking_error_floor"],
            "passed": l31_latest_te is not None and l31_latest_te >= thresholds["00631l_30d_latest_tracking_error_floor"],
        },
        "00631l_30d_p05_tracking_error_floor": {
            "value": l31_p05_te,
            "threshold": thresholds["00631l_30d_p05_tracking_error_floor"],
            "passed": l31_p05_te is not None and l31_p05_te >= thresholds["00631l_30d_p05_tracking_error_floor"],
        },
        "00631l_30d_latest_realized_variance_ceiling": {
            "value": l31_latest_rv,
            "threshold": thresholds["00631l_30d_latest_realized_variance_ceiling"],
            "passed": l31_latest_rv is not None
            and l31_latest_rv <= thresholds["00631l_30d_latest_realized_variance_ceiling"],
        },
        "00631l_minimum_30d_observations": {
            "value": l31_h30_count,
            "threshold": thresholds["minimum_30d_observations"],
            "passed": l31_h30_count is not None and l31_h30_count >= thresholds["minimum_30d_observations"],
        },
        "00632r_60d_abs_beta_error_ceiling": {
            "value": r32_abs_beta_error,
            "threshold": thresholds["00632r_60d_abs_beta_error_ceiling"],
            "passed": r32_abs_beta_error is not None
            and r32_abs_beta_error <= thresholds["00632r_60d_abs_beta_error_ceiling"],
        },
        "00632r_60d_correlation_ceiling": {
            "value": r32_corr,
            "threshold": thresholds["00632r_60d_correlation_ceiling"],
            "passed": r32_corr is not None and r32_corr <= thresholds["00632r_60d_correlation_ceiling"],
        },
        "00632r_30d_p05_tracking_error_floor": {
            "value": r32_p05_te,
            "threshold": thresholds["00632r_30d_p05_tracking_error_floor"],
            "passed": r32_p05_te is not None and r32_p05_te >= thresholds["00632r_30d_p05_tracking_error_floor"],
        },
        "00632r_minimum_30d_observations": {
            "value": r32_h30_count,
            "threshold": thresholds["minimum_30d_observations"],
            "passed": r32_h30_count is not None and r32_h30_count >= thresholds["minimum_30d_observations"],
        },
        "effective_fee_proxy_independently_validated": {
            "value": False,
            "threshold": True,
            "passed": False,
        },
        "live_hedge_policy_validated": {
            "value": False,
            "threshold": True,
            "passed": False,
        },
    }
    failed = [name for name, check in checks.items() if not check["passed"]]
    return {
        "policy": "manual_review_thresholds_only_no_live_unlock",
        "thresholds": thresholds,
        "checks": checks,
        "failed_checks": failed,
        "all_thresholds_passed": not failed,
        "can_consider_00631l_add_after_manual_review": False,
        "can_consider_00632r_open_after_manual_review": False,
        "notes": [
            "Thresholds are deliberately conservative and advisory-only.",
            "Passing these thresholds would only permit manual review, not automatic orders.",
            "Effective-fee proxy and live hedge policy remain hard validation requirements.",
        ],
    }


def build_review(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    start: str = "2020-01-01",
    reference_ticker: str = "0050.TW",
    letf_betas: dict[str, float] | None = None,
    horizons: list[int] | None = None,
    intervention_fatigue_path: Path = DEFAULT_INTERVENTION_FATIGUE,
) -> dict[str, Any]:
    betas = letf_betas or {"00631L.TW": 2.0, "00632R.TW": -1.0}
    horizon_values = horizons or [1, 5, 10, 20, 30]
    tickers = [reference_ticker, *betas.keys()]
    panel = _load_close_panel(db_path, tickers=tickers, start=start, as_of=as_of)
    if panel.empty:
        data_end = None
        available_tickers: list[str] = []
    else:
        available_tickers = [ticker for ticker in tickers if ticker in panel.columns and panel[ticker].notna().any()]
        common = panel[tickers].dropna() if all(ticker in panel.columns for ticker in tickers) else pd.DataFrame()
        data_end = str(common.index.max()) if not common.empty else str(panel.index.max())

    intervention_fatigue = _load_optional(intervention_fatigue_path)
    tracking_error_summary: dict[str, Any] = {}
    for ticker, beta in betas.items():
        if reference_ticker in panel.columns and ticker in panel.columns:
            tracking_error_summary[ticker] = {
                "expected_daily_beta": beta,
                "horizon_metrics": _horizon_metrics(
                    panel,
                    reference_ticker=reference_ticker,
                    letf_ticker=ticker,
                    beta=beta,
                    horizons=horizon_values,
                ),
            }
        else:
            tracking_error_summary[ticker] = {
                "expected_daily_beta": beta,
                "horizon_metrics": {},
                "status": "missing_ohlcv",
            }

    hedge_neutrality = {}
    if "00632R.TW" in betas and reference_ticker in panel.columns and "00632R.TW" in panel.columns:
        hedge_neutrality["00632R.TW"] = _hedge_neutrality(
            panel,
            reference_ticker=reference_ticker,
            inverse_ticker="00632R.TW",
            expected_beta=betas["00632R.TW"],
        )

    blockers = [
        "research_only_letf_tracking_error_review",
        "realized_effective_fee_proxy_not_validated",
        "00632r_hedge_neutrality_not_promoted",
        "letf_pair_strategy_not_imported",
    ]
    if len(available_tickers) < len(tickers):
        blockers.append("missing_required_letf_ohlcv")
    if intervention_fatigue.get("status") == "blocked":
        blockers.append("intervention_fatigue_risk_budget_readiness_blocked")
    for ticker, summary in tracking_error_summary.items():
        h30 = ((summary.get("horizon_metrics") or {}).get("30") or {}).get("tracking_error") or {}
        if h30.get("mean") is not None and h30.get("mean") < 0:
            blockers.append(f"{ticker.lower().replace('.', '_')}_mean_30d_tracking_error_drag_present")
    parameter_threshold_review = _build_parameter_threshold_review(
        tracking_error_summary,
        hedge_neutrality,
        DEFAULT_PARAMETER_THRESHOLDS,
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_letf_tracking_error_effective_fee_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": data_end,
        "source_paper": {
            "path": SOURCE_PAPER,
            "title": "Understanding the Tracking Errors of Commodity Leveraged ETFs",
            "imported_concept": "holding-horizon tracking error, realized-variance decay, realized effective-fee proxy",
        },
        "policy": "research_only_letf_tracking_error_effective_fee_no_pair_trade_no_weight_change",
        "status": "blocked",
        "data": {
            "db_path": str(db_path),
            "start": start,
            "reference_ticker": reference_ticker,
            "available_tickers": available_tickers,
            "required_tickers": tickers,
            "horizons": horizon_values,
        },
        "tracking_error_summary": tracking_error_summary,
        "hedge_neutrality": hedge_neutrality,
        "parameter_threshold_review": parameter_threshold_review,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "tracking_error_readiness_ready": False,
            "realized_effective_fee_proxy_ready": False,
            "hedge_neutrality_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "letf_pair_trade_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "intervention_fatigue_risk_budget_readiness": str(intervention_fatigue_path),
        },
    }


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(review.get("as_of") or review.get("actual_data_end") or datetime.now().strftime("%Y-%m-%d"))
    history_path = history_dir / f"letf_tracking_error_effective_fee_readiness_{stamp.replace('-', '')}.json"
    history_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--horizons", default="1,5,10,20,30")
    parser.add_argument("--intervention-fatigue", default=str(DEFAULT_INTERVENTION_FATIGUE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    horizons = [int(item.strip()) for item in str(args.horizons).split(",") if item.strip()]
    review = build_review(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        start=args.start,
        horizons=horizons,
        intervention_fatigue_path=_resolve(args.intervention_fatigue),
    )
    write_review(review, _resolve(args.output), _resolve(args.history_dir))
    print(f"LETF tracking-error/effective-fee readiness review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "actual_data_end": review["actual_data_end"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
