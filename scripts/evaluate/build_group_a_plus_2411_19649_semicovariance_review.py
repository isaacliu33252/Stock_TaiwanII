#!/usr/bin/env python3
"""Build a constrained semi-covariance diagnostic for GroupA+.

This first-stage review is inspired by arXiv 2411.19649 but deliberately does
not replace A21.18 or run an unconstrained optimizer. It compares ordinary
covariance, historical semi-covariance, EWMA semi-covariance, and conditional
downside correlations inside A21.18-compatible regime constraints.
"""

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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_FIFTH_CANDIDATES = ("0056.TW", "00713.TW", "00878.TW", "00646.TW")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2411_19649_semicovariance_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2411_19649_semicovariance_review/history"
DEFAULT_A2118_LIVE_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_A2118_FORWARD_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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


def _corr_from_cov(cov: pd.DataFrame) -> pd.DataFrame:
    diag = np.sqrt(np.diag(cov.to_numpy(dtype=float)))
    denom = np.outer(diag, diag)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = cov.to_numpy(dtype=float) / denom
    corr[~np.isfinite(corr)] = np.nan
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def _semi_cov(returns: pd.DataFrame, mar: pd.Series, ewma_halflife: int | None = None) -> pd.DataFrame:
    aligned_mar = mar.reindex(returns.index).fillna(0.0)
    down = returns.sub(aligned_mar, axis=0).clip(upper=0.0).fillna(0.0)
    if ewma_halflife is None:
        matrix = down.to_numpy(dtype=float).T @ down.to_numpy(dtype=float) / max(len(down), 1)
    else:
        age = np.arange(len(down) - 1, -1, -1, dtype=float)
        weights = np.exp(np.log(0.5) * age / float(ewma_halflife))
        weights = weights / weights.sum()
        weighted = down.to_numpy(dtype=float) * np.sqrt(weights[:, None])
        matrix = weighted.T @ weighted
    return pd.DataFrame(matrix, index=returns.columns, columns=returns.columns)


def _pair_metric(corr: pd.DataFrame, left: str, right: str) -> float | None:
    if left not in corr.index or right not in corr.columns:
        return None
    return _float(corr.loc[left, right])


def _conditional_corr(
    returns: pd.DataFrame,
    *,
    base: str,
    asset: str,
    threshold: float,
    min_rows: int,
) -> dict[str, Any]:
    pair = returns[[base, asset]].dropna()
    if pair.empty:
        return {"asset": asset, "threshold": threshold, "status": "insufficient_data", "observations": 0}
    sample = pair[pair[base] < threshold]
    if len(sample) < min_rows:
        return {
            "asset": asset,
            "threshold": threshold,
            "status": "insufficient_conditional_rows",
            "observations": int(len(sample)),
            "min_rows": min_rows,
        }
    return {
        "asset": asset,
        "threshold": threshold,
        "status": "available",
        "observations": int(len(sample)),
        "corr_vs_0050": _float(sample[base].corr(sample[asset])),
    }


def _matrix_pairs(corr: pd.DataFrame, tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, left in enumerate(tickers):
        for right in tickers[idx + 1 :]:
            rows.append({"left": left, "right": right, "corr": _pair_metric(corr, left, right)})
    return rows


def _regime_constraints() -> dict[str, dict[str, Any]]:
    return {
        "golden1": {
            "allowed_assets": ["0050.TW", "00631L.TW", "cash"],
            "forbidden_assets": ["00632R.TW", "00679B.TWO"],
            "rule": "00632R is zero; semi-covariance can only compare 0050 and 00631L within the existing golden sleeve.",
        },
        "defensive": {
            "allowed_assets": ["0050.TW", "00679B.TWO", "cash"],
            "forbidden_assets": ["00631L.TW", "00632R.TW"],
            "rule": "00631L and 00632R are zero; semi-covariance can only rank downside diversification among defensive assets.",
        },
        "bear_inverse_eligible": {
            "allowed_assets": ["0050.TW", "00632R.TW", "cash"],
            "forbidden_assets": ["00631L.TW", "00679B.TWO"],
            "rule": "00632R is only eligible when the existing A21.18 state permits inverse exposure.",
        },
    }


def _infer_current_context(live_snapshot: dict[str, Any], forward_monitor: dict[str, Any]) -> dict[str, Any]:
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    current_weights = live_signal.get("target_weights")
    if not isinstance(current_weights, dict):
        current_weights = forward_monitor.get("target_weights") if isinstance(forward_monitor.get("target_weights"), dict) else {}
    raw_weights = (
        live_snapshot.get("target_weights_for_action")
        if isinstance(live_snapshot.get("target_weights_for_action"), dict)
        else live_snapshot.get("target_weights")
        if isinstance(live_snapshot.get("target_weights"), dict)
        else {}
    )
    market_state = live_signal.get("market_state") if isinstance(live_signal.get("market_state"), dict) else {}
    dominant_direction = market_state.get("dominant_direction") or live_signal.get("dominant_direction")
    risk_level = market_state.get("risk_level") or live_signal.get("risk_level")
    execution_regime = live_signal.get("execution_regime")
    if dominant_direction == "bearish" or float(current_weights.get("cash", 0.0) or 0.0) >= 0.5:
        inferred_regime = "defensive"
    elif float(raw_weights.get("00632R.TW", 0.0) or 0.0) > 0:
        inferred_regime = "bear_inverse_eligible"
    else:
        inferred_regime = "golden1"
    return {
        "live_snapshot_found": bool(live_snapshot),
        "forward_monitor_found": bool(forward_monitor),
        "raw_a2118_target_weights": raw_weights,
        "current_live_target_weights": current_weights,
        "market_state": market_state,
        "execution_regime": execution_regime,
        "dominant_direction": dominant_direction,
        "risk_level": risk_level,
        "inferred_constraint_regime": inferred_regime,
    }


def _available_tickers(returns: pd.DataFrame, tickers: tuple[str, ...], min_history: int) -> tuple[str, ...]:
    return tuple(ticker for ticker in tickers if ticker in returns.columns and int(returns[ticker].notna().sum()) >= min_history)


def _build_mar_series(
    returns: pd.DataFrame,
    *,
    cash_daily_return: float,
    risk_free_annual: float,
) -> dict[str, dict[str, Any]]:
    rf_daily = (1.0 + risk_free_annual) ** (1.0 / 252.0) - 1.0
    return {
        "zero": {
            "series": pd.Series(0.0, index=returns.index),
            "daily_value": 0.0,
            "source": "constant_zero",
            "limitation": None,
        },
        "cash_return": {
            "series": pd.Series(cash_daily_return, index=returns.index),
            "daily_value": cash_daily_return,
            "source": "user_or_default_cash_daily_return",
            "limitation": None,
        },
        "rolling_risk_free_rate": {
            "series": pd.Series(rf_daily, index=returns.index),
            "daily_value": rf_daily,
            "source": "constant_daily_proxy_from_annual_rate",
            "limitation": "local_database_has_no_rolling_risk_free_series",
        },
    }


def build_review(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    fifth_candidates: tuple[str, ...] = DEFAULT_FIFTH_CANDIDATES,
    base: str = "0050.TW",
    lookback_days: int = 756,
    min_history: int = 252,
    min_conditional_rows: int = 8,
    ewma_halflife: int = 60,
    cash_daily_return: float = 0.0,
    risk_free_annual: float = 0.015,
    low_ordinary_corr_threshold: float = 0.30,
    high_downside_corr_threshold: float = 0.60,
    a2118_live_snapshot_path: Path = DEFAULT_A2118_LIVE_SNAPSHOT,
    a2118_forward_monitor_path: Path = DEFAULT_A2118_FORWARD_MONITOR,
) -> dict[str, Any]:
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    blockers: list[str] = []
    warnings: list[str] = []
    tickers = tuple(dict.fromkeys([*core_tickers, *fifth_candidates]))

    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, str(end_resolved))

    if close.empty or base not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        returns = returns.tail(lookback_days)

    available = _available_tickers(returns, tickers, min_history) if not returns.empty else ()
    if base not in available:
        blockers.append("base_has_insufficient_history")
    if len(available) < 2:
        blockers.append("too_few_assets_with_sufficient_history")

    live_snapshot = _load_json(_resolve(a2118_live_snapshot_path))
    forward_monitor = _load_json(_resolve(a2118_forward_monitor_path))
    current_context = _infer_current_context(live_snapshot, forward_monitor)

    if blockers:
        analysis_returns = pd.DataFrame()
        ordinary_corr = pd.DataFrame()
        mar_reviews: dict[str, Any] = {}
        candidate_ranking: list[dict[str, Any]] = []
        conditional_rows: list[dict[str, Any]] = []
        regime_reviews: dict[str, Any] = {}
        information_findings: list[dict[str, Any]] = []
    else:
        analysis_returns = returns[list(available)].dropna(how="all")
        ordinary_cov = analysis_returns.cov()
        ordinary_corr = analysis_returns.corr()
        mar_inputs = _build_mar_series(
            analysis_returns,
            cash_daily_return=cash_daily_return,
            risk_free_annual=risk_free_annual,
        )
        mar_reviews = {}
        for name, payload in mar_inputs.items():
            hist_semi_cov = _semi_cov(analysis_returns, payload["series"], ewma_halflife=None)
            ewma_semi_cov = _semi_cov(analysis_returns, payload["series"], ewma_halflife=ewma_halflife)
            hist_semi_corr = _corr_from_cov(hist_semi_cov)
            ewma_semi_corr = _corr_from_cov(ewma_semi_cov)
            mar_reviews[name] = {
                "source": payload["source"],
                "daily_value": _float(payload["daily_value"], 10),
                "limitation": payload["limitation"],
                "historical_semi_corr_pairs": _matrix_pairs(hist_semi_corr, tuple(available)),
                "ewma_semi_corr_pairs": _matrix_pairs(ewma_semi_corr, tuple(available)),
            }

        conditional_rows = []
        for asset in available:
            if asset == base:
                continue
            for threshold in (0.0, -0.01, -0.02):
                conditional_rows.append(
                    _conditional_corr(
                        analysis_returns,
                        base=base,
                        asset=asset,
                        threshold=threshold,
                        min_rows=min_conditional_rows,
                    )
                )

        zero_hist_semi_corr = _corr_from_cov(_semi_cov(analysis_returns, mar_inputs["zero"]["series"], None))
        zero_ewma_semi_corr = _corr_from_cov(_semi_cov(analysis_returns, mar_inputs["zero"]["series"], ewma_halflife))
        candidate_ranking = []
        for asset in fifth_candidates:
            if asset not in available:
                candidate_ranking.append({"asset": asset, "status": "insufficient_history_or_missing"})
                continue
            cond_available = [
                row
                for row in conditional_rows
                if row.get("asset") == asset and row.get("status") == "available" and isinstance(row.get("corr_vs_0050"), (int, float))
            ]
            max_cond = max((float(row["corr_vs_0050"]) for row in cond_available), default=None)
            ordinary = _pair_metric(ordinary_corr, base, asset)
            hist_semi = _pair_metric(zero_hist_semi_corr, base, asset)
            ewma_semi = _pair_metric(zero_ewma_semi_corr, base, asset)
            reasons: list[str] = []
            if ordinary is not None and max_cond is not None:
                if ordinary <= low_ordinary_corr_threshold and max_cond >= high_downside_corr_threshold:
                    reasons.append("ordinary_corr_low_but_downside_corr_high")
            if ordinary is not None and hist_semi is not None and abs(hist_semi - ordinary) >= 0.20:
                reasons.append("historical_semi_corr_differs_from_ordinary_corr")
            if ordinary is not None and ewma_semi is not None and abs(ewma_semi - ordinary) >= 0.20:
                reasons.append("ewma_semi_corr_differs_from_ordinary_corr")
            candidate_ranking.append(
                {
                    "asset": asset,
                    "status": "available",
                    "ordinary_corr_vs_0050": ordinary,
                    "historical_semi_corr_vs_0050_mar0": hist_semi,
                    "ewma_semi_corr_vs_0050_mar0": ewma_semi,
                    "max_conditional_downside_corr_vs_0050": _float(max_cond),
                    "diversification_disappears_in_stress": bool(reasons),
                    "warning_reasons": reasons,
                }
            )

        constraints = _regime_constraints()
        regime_reviews = {}
        information_findings = []
        for regime, policy in constraints.items():
            allowed = tuple(asset for asset in policy["allowed_assets"] if asset != "cash" and asset in available)
            hist_pairs = _matrix_pairs(zero_hist_semi_corr, allowed)
            ewma_pairs = _matrix_pairs(zero_ewma_semi_corr, allowed)
            regime_reviews[regime] = {
                **policy,
                "ordinary_corr_pairs": _matrix_pairs(ordinary_corr, allowed),
                "historical_semi_corr_pairs_mar0": hist_pairs,
                "ewma_semi_corr_pairs_mar0": ewma_pairs,
                "contains_forbidden_leverage_inverse_offset": "00631L.TW" in allowed and "00632R.TW" in allowed,
            }
            for left, right in zip(allowed, allowed[1:]):
                ordinary = _pair_metric(ordinary_corr, left, right)
                hist = _pair_metric(zero_hist_semi_corr, left, right)
                ewma = _pair_metric(zero_ewma_semi_corr, left, right)
                if ordinary is None:
                    continue
                hist_diff = None if hist is None else abs(hist - ordinary)
                ewma_diff = None if ewma is None else abs(ewma - ordinary)
                if (hist_diff is not None and hist_diff >= 0.20) or (ewma_diff is not None and ewma_diff >= 0.20):
                    information_findings.append(
                        {
                            "regime": regime,
                            "left": left,
                            "right": right,
                            "ordinary_corr": ordinary,
                            "historical_semi_corr_mar0": hist,
                            "ewma_semi_corr_mar0": ewma,
                            "max_abs_diff_vs_ordinary": _float(max(hist_diff or 0.0, ewma_diff or 0.0)),
                            "finding": "semi_covariance_differs_materially_from_ordinary_correlation_inside_regime_constraints",
                        }
                    )

        if any(row.get("diversification_disappears_in_stress") for row in candidate_ranking):
            warnings.append("at_least_one_fifth_candidate_loses_diversification_in_stress")
        if any(row.get("limitation") for row in mar_reviews.values()):
            warnings.append("rolling_risk_free_rate_unavailable_using_proxy")

    semi_adds_info = bool(information_findings) or any(
        row.get("diversification_disappears_in_stress") for row in candidate_ranking if isinstance(row, dict)
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2411_19649_semicovariance_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "diagnostic_only_no_optimizer_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "arxiv_id": "2411.19649",
            "implemented_stage": "stage_1_covariance_vs_semicovariance_information_test",
            "paper_equivalent": False,
        },
        "guardrails": {
            "unconstrained_minimum_semicovariance_optimizer_allowed": False,
            "optimizer_replacement_for_a2118_allowed": False,
            "forbid_simultaneous_00631l_00632r_offset": True,
            "semi_covariance_role": "diagnostic_filter_inside_existing_a2118_regime_constraints",
        },
        "parameters": {
            "core_tickers": list(core_tickers),
            "fifth_candidates": list(fifth_candidates),
            "base": base,
            "lookback_days": lookback_days,
            "min_history": min_history,
            "min_conditional_rows": min_conditional_rows,
            "ewma_halflife": ewma_halflife,
            "cash_daily_return": cash_daily_return,
            "risk_free_annual": risk_free_annual,
            "low_ordinary_corr_threshold": low_ordinary_corr_threshold,
            "high_downside_corr_threshold": high_downside_corr_threshold,
        },
        "coverage": {
            "available_tickers": list(available),
            "return_observations": int(len(analysis_returns)),
            "actual_data_start": str(analysis_returns.index.min().date()) if not analysis_returns.empty else None,
            "actual_data_end": str(analysis_returns.index.max().date()) if not analysis_returns.empty else None,
        },
        "latest_a2118_context": current_context,
        "ordinary_covariance": {
            "ordinary_corr_pairs": _matrix_pairs(ordinary_corr, tuple(available)) if not ordinary_corr.empty else [],
        },
        "semicovariance_by_mar": mar_reviews,
        "conditional_downside_correlation_vs_0050": conditional_rows,
        "regime_constraint_reviews": regime_reviews,
        "semicovariance_information_findings": information_findings,
        "fifth_asset_candidate_ranking": candidate_ranking,
        "decision": {
            "semi_covariance_adds_information_vs_ordinary_covariance": semi_adds_info,
            "promote_to_live_weights": False,
            "target_weight_change_allowed": False,
            "replace_a2118_optimizer": False,
            "use_as_fifth_asset_filter": bool(not blockers),
            "summary": (
                "Semi-covariance/conditional downside correlation can be used as a shadow fifth-asset filter, "
                "but it is not allowed to override A21.18 or create unconstrained leverage/inverse offsets."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_review(review: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(review.get("as_of") or datetime.now().date())
    history_name = f"2411_19649_semicovariance_review_{as_of.replace('-', '')}.json"
    (history_dir / history_name).write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--lookback-days", type=int, default=756)
    parser.add_argument("--min-history", type=int, default=252)
    parser.add_argument("--min-conditional-rows", type=int, default=8)
    parser.add_argument("--ewma-halflife", type=int, default=60)
    parser.add_argument("--cash-daily-return", type=float, default=0.0)
    parser.add_argument("--risk-free-annual", type=float, default=0.015)
    parser.add_argument("--fifth-candidates", nargs="*", default=list(DEFAULT_FIFTH_CANDIDATES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review = build_review(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        fifth_candidates=tuple(args.fifth_candidates),
        lookback_days=args.lookback_days,
        min_history=args.min_history,
        min_conditional_rows=args.min_conditional_rows,
        ewma_halflife=args.ewma_halflife,
        cash_daily_return=args.cash_daily_return,
        risk_free_annual=args.risk_free_annual,
    )
    write_review(review, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(review["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
