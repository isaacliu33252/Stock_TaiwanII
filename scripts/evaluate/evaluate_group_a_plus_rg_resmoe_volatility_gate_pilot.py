#!/usr/bin/env python3
"""Evaluate the RG-ResMoE regime-integration-pathway pilot (arXiv:2608.12251).

Compares three walk-forward forecasts of GroupA+ risk tickers' future realized variance
against the existing production HAR-RV forecast (the "base" pathway, which
is byte-for-byte reused/frozen):

  - input_pathway: regime scalar appended directly as a 4th OLS regressor
    (the paper's "bad" pathway -- expected to be flat-to-worse)
  - gate_pathway: frozen base + small ridge residual correction gated by
    the regime scalar's trailing percentile (the paper's proposed pathway)

Reports pooled QLIKE/R2 across the full 2018-2026 sample AND per-year splits,
since a single pooled window can hide a result that only holds in one
sub-period (see feedback_overfitting_fixed_window_tuning). Research-only --
does not touch target weights.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.risk_sensitive_loss import qlike_loss
from group_a_plus.integrations.risk_sensitive_loss import diebold_mariano_test
from group_a_plus.integrations.rg_resmoe_volatility_gate_shadow import (
    DEFAULT_RIDGE_LAMBDA,
    rg_resmoe_pathways,
)
from group_a_plus.integrations.volatility_forecast import HORIZONS, _future_avg_variance, garman_klass_variance

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_rg_resmoe_volatility_gate_pilot_latest.json"
VAR_LEVELS = (0.05, 0.01)
DEFAULT_RESIDUAL_VAR_WINDOW = 756
DEFAULT_RESIDUAL_VAR_MIN_ROWS = 130
DEFAULT_RESIDUAL_VAR_BUFFER_5PCT = 1.0
DEFAULT_RESIDUAL_VAR_BUFFER_1PCT = 1.35
DEFAULT_HIGH_VOL_GATE_QUANTILE = 0.80


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, open, high, low, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def _log_r2(actual: pd.Series, forecast: pd.Series) -> float:
    y = np.log(actual.clip(lower=1e-12))
    yhat = np.log(forecast.clip(lower=1e-12))
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _score(
    actual: pd.Series,
    forecast: pd.Series,
    base_forecast: pd.Series,
    mask: pd.Series,
    *,
    horizon: int,
) -> dict:
    idx = mask & forecast.notna() & actual.notna()
    n = int(idx.sum())
    if n < 20:
        return {"status": "insufficient_data", "n": n}
    loss = qlike_loss(actual[idx], forecast[idx])
    base = qlike_loss(actual[idx], base_forecast[idx])
    loss_mean = float(loss.mean())
    base_mean = float(base.mean())
    return {
        "n": n,
        "qlike_mean": loss_mean,
        "base_qlike_mean": base_mean,
        "qlike_improvement_pct": (base_mean - loss_mean) / base_mean * 100.0 if base_mean else None,
        "win_rate_vs_base": float((loss.to_numpy() < base.to_numpy()).mean()),
        "r2_log_variance": _log_r2(actual[idx], forecast[idx]),
        "dm_qlike_vs_base": diebold_mariano_test(loss, base, h=horizon),
    }


def _kupiec_test(exceptions: pd.Series, *, alpha: float) -> dict[str, Any]:
    clean = exceptions.dropna().astype(bool)
    n = int(len(clean))
    x = int(clean.sum())
    if n < 30:
        return {"status": "insufficient_data", "n": n, "exceptions": x}
    p_hat = x / n
    if x == 0 or x == n:
        # Limit form: one side of the Bernoulli MLE is degenerate.
        log_l_uncond = 0.0
    else:
        log_l_uncond = x * math.log(p_hat) + (n - x) * math.log(1.0 - p_hat)
    log_l_nominal = x * math.log(alpha) + (n - x) * math.log(1.0 - alpha)
    lr_uc = max(0.0, -2.0 * (log_l_nominal - log_l_uncond))
    p_value = float(scipy_stats.chi2.sf(lr_uc, df=1))
    return {
        "status": "ok",
        "n": n,
        "exceptions": x,
        "nominal_alpha": float(alpha),
        "breach_rate": float(p_hat),
        "coverage_error": float(abs(p_hat - alpha)),
        "kupiec_lr_uc": float(lr_uc),
        "kupiec_p_value": p_value,
        "kupiec_reject_5pct": bool(p_value < 0.05),
    }


def _var_calibration(
    forward_return: pd.Series,
    forecast_variance: pd.Series,
    mask: pd.Series,
    *,
    horizon: int,
) -> dict[str, Any]:
    idx = mask & forward_return.notna() & forecast_variance.notna()
    out: dict[str, Any] = {}
    for alpha in VAR_LEVELS:
        z = float(scipy_stats.norm.ppf(alpha))
        horizon_sigma = np.sqrt((forecast_variance[idx].clip(lower=1e-12) * horizon).astype(float))
        var_threshold = z * horizon_sigma
        exceptions = forward_return[idx].astype(float) <= var_threshold
        out[f"var_{int(alpha * 100)}pct"] = _kupiec_test(exceptions, alpha=alpha)
    return out


def _residual_calibrated_var_calibration(
    forward_return: pd.Series,
    forecast_variance: pd.Series,
    mask: pd.Series,
    *,
    horizon: int,
    calibration_window: int = DEFAULT_RESIDUAL_VAR_WINDOW,
    min_calibration_rows: int = DEFAULT_RESIDUAL_VAR_MIN_ROWS,
    tail_buffers: dict[float, float] | None = None,
) -> dict[str, Any]:
    sigma = np.sqrt((forecast_variance.clip(lower=1e-12) * horizon).astype(float))
    standardized = forward_return.astype(float) / sigma
    out: dict[str, Any] = {}
    for alpha in VAR_LEVELS:
        exceptions = pd.Series(index=forward_return.index, dtype=object)
        thresholds = pd.Series(index=forward_return.index, dtype=float)
        for i, dt in enumerate(forward_return.index):
            if not bool(mask.iloc[i]) or pd.isna(forward_return.iloc[i]) or pd.isna(sigma.iloc[i]):
                continue
            train_end = i - horizon
            if train_end < min_calibration_rows:
                continue
            train_start = max(0, train_end + 1 - calibration_window)
            train = standardized.iloc[train_start : train_end + 1].dropna()
            if len(train) < min_calibration_rows:
                continue
            q = float(train.quantile(alpha, interpolation="lower"))
            # q is negative for lower-tail VaR. buffer > 1.0 makes the threshold
            # more negative and therefore more conservative.
            threshold = q * float(sigma.iloc[i]) * float((tail_buffers or {}).get(alpha, 1.0))
            thresholds.iloc[i] = threshold
            exceptions.iloc[i] = bool(float(forward_return.iloc[i]) <= threshold)
        key = f"var_{int(alpha * 100)}pct"
        calibration = _kupiec_test(exceptions.dropna().astype(bool), alpha=alpha)
        calibration["method"] = "causal_residual_quantile"
        calibration["calibration_window"] = int(calibration_window)
        calibration["min_calibration_rows"] = int(min_calibration_rows)
        calibration["tail_buffer"] = float((tail_buffers or {}).get(alpha, 1.0))
        clean_thresholds = thresholds.dropna()
        calibration["mean_var_threshold"] = float(clean_thresholds.mean()) if not clean_thresholds.empty else None
        out[key] = calibration
    return out


def _var_suite(
    forward_return: pd.Series,
    forecasts: dict[str, pd.Series],
    mask: pd.Series,
    *,
    horizon: int,
) -> dict[str, Any]:
    return {
        name: _var_calibration(forward_return, forecast, mask, horizon=horizon)
        for name, forecast in forecasts.items()
    }


def _residual_var_suite(
    forward_return: pd.Series,
    forecasts: dict[str, pd.Series],
    mask: pd.Series,
    *,
    horizon: int,
    calibration_window: int,
    min_calibration_rows: int,
    tail_buffers: dict[float, float],
) -> dict[str, Any]:
    return {
        name: _residual_calibrated_var_calibration(
            forward_return,
            forecast,
            mask,
            horizon=horizon,
            calibration_window=calibration_window,
            min_calibration_rows=min_calibration_rows,
            tail_buffers=tail_buffers,
        )
        for name, forecast in forecasts.items()
    }


def _promotion_decision(results: dict[str, Any], *, promoted_pathway: str = "gate_pathway_soft") -> dict[str, Any]:
    blockers: list[str] = []
    soft_pooled = {
        h: res.get("pooled", {}).get(promoted_pathway, {})
        for h, res in results.items()
    }
    for h, res in soft_pooled.items():
        improvement = res.get("qlike_improvement_pct")
        dm = res.get("dm_qlike_vs_base") or {}
        if improvement is None or improvement <= 0.0:
            blockers.append(f"h{h}_soft_gate_pooled_not_positive")
        elif dm.get("status") == "ok" and not (dm.get("a_more_accurate") and dm.get("significant_at_5pct")):
            blockers.append(f"h{h}_soft_gate_not_dm_significant")

    input_bad_or_flat = 0
    for h, res in results.items():
        improvement = (res.get("pooled", {}).get("input_pathway", {}) or {}).get("qlike_improvement_pct")
        if improvement is not None and improvement <= 0.0:
            input_bad_or_flat += 1

    if input_bad_or_flat < max(1, len(results) - 1):
        blockers.append("input_pathway_not_consistently_worse_than_base")

    for h, res in results.items():
        soft_var = (((res.get("residual_var_calibration") or {}).get("pooled") or {}).get(promoted_pathway) or {})
        if not soft_var:
            soft_var = (((res.get("var_calibration") or {}).get("pooled") or {}).get(promoted_pathway) or {})
        for var_key in ("var_5pct", "var_1pct"):
            calibration = soft_var.get(var_key) or {}
            if calibration.get("status") == "ok" and calibration.get("kupiec_reject_5pct") is True:
                blockers.append(f"h{h}_soft_gate_residual_{var_key}_kupiec_reject")

    return {
        "decision": "do_not_promote_keep_shadow" if blockers else "eligible_for_manual_review_not_auto_promote",
        "policy": "research_only_no_weight_change",
        "evaluated_pathway": promoted_pathway,
        "blockers": blockers,
        "required_before_live_use": [
            "positive pooled QLIKE improvement for soft gate on all horizons",
            "DM test confirms lower QLIKE than frozen HAR-RV base",
            "no target-weight wiring without a separate signed promotion review",
        ],
    }


def evaluate(
    ticker: str,
    start: str,
    end: str,
    *,
    rolling_window: int | None,
    ridge_lambda: float,
    residual_var_window: int,
    residual_var_min_rows: int,
    residual_var_buffer_5pct: float,
    residual_var_buffer_1pct: float,
    high_vol_gate_quantile: float,
) -> dict:
    ohlc = _load_ohlc(DB_PATH, ticker, start, end)
    gk_variance = garman_klass_variance(ohlc)
    years = sorted(ohlc.index.year.unique())

    results: dict[str, Any] = {}
    tail_buffers = {
        0.05: float(residual_var_buffer_5pct),
        0.01: float(residual_var_buffer_1pct),
    }
    for h in HORIZONS:
        frame = rg_resmoe_pathways(gk_variance, horizon=h, rolling_window=rolling_window, ridge_lambda=ridge_lambda)
        actual = _future_avg_variance(gk_variance, h)
        forward_return = ohlc["close"].shift(-h) / ohlc["close"] - 1.0
        base_fc = frame[f"base_pathway_h{h}"]
        input_fc = frame[f"input_pathway_h{h}"]
        gate_fc = frame[f"gate_pathway_h{h}"]
        gate_soft_fc = frame[f"gate_pathway_soft_h{h}"]
        common = base_fc.notna() & input_fc.notna() & gate_fc.notna() & gate_soft_fc.notna() & actual.notna()
        regime_state = gk_variance.rolling(20, min_periods=20).mean()
        high_vol_cutoff = float(regime_state[common].quantile(float(high_vol_gate_quantile))) if int(common.sum()) else float("nan")
        high_vol_mask = common & (regime_state >= high_vol_cutoff)
        recent_mask = common & pd.Series(frame.index >= pd.Timestamp("2025-01-01"), index=frame.index)
        high_vol_only_gate_soft_fc = gate_soft_fc.where(high_vol_mask, base_fc)
        forecasts = {
            "base_pathway": base_fc,
            "input_pathway": input_fc,
            "gate_pathway": gate_fc,
            "gate_pathway_soft": gate_soft_fc,
            "high_vol_only_gate_pathway_soft": high_vol_only_gate_soft_fc,
        }

        per_year = {}
        for yr in years:
            year_mask = pd.Series(frame.index.year == yr, index=frame.index) & common
            if int(year_mask.sum()) < 20:
                continue
            per_year[str(yr)] = {
                "input_pathway": _score(actual, input_fc, base_fc, year_mask, horizon=h),
                "gate_pathway": _score(actual, gate_fc, base_fc, year_mask, horizon=h),
                "gate_pathway_soft": _score(actual, gate_soft_fc, base_fc, year_mask, horizon=h),
            }

        results[str(h)] = {
            "pooled": {
                "input_pathway": _score(actual, input_fc, base_fc, common, horizon=h),
                "gate_pathway": _score(actual, gate_fc, base_fc, common, horizon=h),
                "gate_pathway_soft": _score(actual, gate_soft_fc, base_fc, common, horizon=h),
                "high_vol_only_gate_pathway_soft": _score(actual, high_vol_only_gate_soft_fc, base_fc, common, horizon=h),
            },
            "slices": {
                "top_realized_vol_decile": {
                    "input_pathway": _score(actual, input_fc, base_fc, high_vol_mask, horizon=h),
                    "gate_pathway": _score(actual, gate_fc, base_fc, high_vol_mask, horizon=h),
                    "gate_pathway_soft": _score(actual, gate_soft_fc, base_fc, high_vol_mask, horizon=h),
                    "high_vol_only_gate_pathway_soft": _score(actual, high_vol_only_gate_soft_fc, base_fc, high_vol_mask, horizon=h),
                },
                "recent_2025_2026": {
                    "input_pathway": _score(actual, input_fc, base_fc, recent_mask, horizon=h),
                    "gate_pathway": _score(actual, gate_fc, base_fc, recent_mask, horizon=h),
                    "gate_pathway_soft": _score(actual, gate_soft_fc, base_fc, recent_mask, horizon=h),
                    "high_vol_only_gate_pathway_soft": _score(actual, high_vol_only_gate_soft_fc, base_fc, recent_mask, horizon=h),
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
            "per_year": per_year,
        }
    payload = {
        "ticker": ticker,
        "window": {"start": start, "end": end, "rows": int(len(ohlc))},
        "rolling_window": rolling_window,
        "ridge_lambda": ridge_lambda,
        "residual_var_window": int(residual_var_window),
        "residual_var_min_rows": int(residual_var_min_rows),
        "residual_var_tail_buffers": {
            "var_5pct": float(residual_var_buffer_5pct),
            "var_1pct": float(residual_var_buffer_1pct),
        },
        "high_vol_gate_quantile": float(high_vol_gate_quantile),
        "policy": "research_only_no_weight_change",
        "results": results,
    }
    payload["promotion_decision"] = _promotion_decision(results, promoted_pathway="gate_pathway_soft")
    payload["high_vol_only_promotion_decision"] = _promotion_decision(
        results,
        promoted_pathway="high_vol_only_gate_pathway_soft",
    )
    return payload


def evaluate_many(
    tickers: list[str],
    start: str,
    end: str,
    *,
    rolling_window: int | None,
    ridge_lambda: float,
    residual_var_window: int,
    residual_var_min_rows: int,
    residual_var_buffer_5pct: float,
    residual_var_buffer_1pct: float,
    high_vol_gate_quantile: float,
) -> dict:
    by_ticker = {
        ticker: evaluate(
            ticker,
            start,
            end,
            rolling_window=rolling_window,
            ridge_lambda=ridge_lambda,
            residual_var_window=residual_var_window,
            residual_var_min_rows=residual_var_min_rows,
            residual_var_buffer_5pct=residual_var_buffer_5pct,
            residual_var_buffer_1pct=residual_var_buffer_1pct,
            high_vol_gate_quantile=high_vol_gate_quantile,
        )
        for ticker in tickers
    }
    return {
        "tickers": tickers,
        "window": {"start": start, "end": end},
        "rolling_window": rolling_window,
        "ridge_lambda": ridge_lambda,
        "residual_var_window": int(residual_var_window),
        "residual_var_min_rows": int(residual_var_min_rows),
        "residual_var_tail_buffers": {
            "var_5pct": float(residual_var_buffer_5pct),
            "var_1pct": float(residual_var_buffer_1pct),
        },
        "policy": "research_only_no_weight_change",
        "by_ticker": by_ticker,
        "promotion_decision": {
            "decision": (
                "eligible_for_manual_review_not_auto_promote"
                if all(v["promotion_decision"]["decision"] == "eligible_for_manual_review_not_auto_promote" for v in by_ticker.values())
                else "do_not_promote_keep_shadow"
            ),
            "ticker_decisions": {
                ticker: payload["promotion_decision"]["decision"]
                for ticker, payload in by_ticker.items()
            },
            "high_vol_only_ticker_decisions": {
                ticker: payload["high_vol_only_promotion_decision"]["decision"]
                for ticker, payload in by_ticker.items()
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--tickers", default="0050.TW,00631L.TW")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-08-19")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rolling-window", type=int, default=504)
    parser.add_argument("--ridge-lambda", type=float, default=DEFAULT_RIDGE_LAMBDA)
    parser.add_argument("--residual-var-window", type=int, default=DEFAULT_RESIDUAL_VAR_WINDOW)
    parser.add_argument("--residual-var-min-rows", type=int, default=DEFAULT_RESIDUAL_VAR_MIN_ROWS)
    parser.add_argument("--residual-var-buffer-5pct", type=float, default=DEFAULT_RESIDUAL_VAR_BUFFER_5PCT)
    parser.add_argument("--residual-var-buffer-1pct", type=float, default=DEFAULT_RESIDUAL_VAR_BUFFER_1PCT)
    parser.add_argument("--high-vol-gate-quantile", type=float, default=DEFAULT_HIGH_VOL_GATE_QUANTILE)
    args = parser.parse_args()

    tickers_arg = args.ticker or args.tickers
    tickers = [ticker.strip() for ticker in tickers_arg.split(",") if ticker.strip()]
    payload = evaluate_many(
        tickers, args.start, args.end,
        rolling_window=args.rolling_window,
        ridge_lambda=args.ridge_lambda,
        residual_var_window=args.residual_var_window,
        residual_var_min_rows=args.residual_var_min_rows,
        residual_var_buffer_5pct=args.residual_var_buffer_5pct,
        residual_var_buffer_1pct=args.residual_var_buffer_1pct,
        high_vol_gate_quantile=args.high_vol_gate_quantile,
    )

    for ticker, ticker_payload in payload["by_ticker"].items():
        print(f"\n### {ticker} ###")
        for h, res in ticker_payload["results"].items():
            print(f"\n=== horizon={h} (pooled) ===")
            for pathway in ("input_pathway", "gate_pathway", "gate_pathway_soft"):
                r = res["pooled"][pathway]
                if r.get("status") == "insufficient_data":
                    print(f"  {pathway}: insufficient data (n={r['n']})")
                    continue
                dm = r.get("dm_qlike_vs_base") or {}
                dm_note = ""
                if dm.get("status") == "ok":
                    dm_note = f" DM_p={dm.get('p_value'):.4f} DM_better={dm.get('a_more_accurate')}"
                print(
                    f"  {pathway}: n={r['n']} QLIKE={r['qlike_mean']:.4f} base_QLIKE={r['base_qlike_mean']:.4f} "
                    f"improvement={r['qlike_improvement_pct']:.2f}% win_rate={r['win_rate_vs_base']:.3f} "
                    f"R2={r['r2_log_variance']:.3f}{dm_note}"
                )
            hv_only = res["pooled"]["high_vol_only_gate_pathway_soft"]
            hv_dm = hv_only.get("dm_qlike_vs_base") or {}
            print(
                f"  high_vol_only_gate_pathway_soft: n={hv_only['n']} "
                f"improvement={hv_only['qlike_improvement_pct']:.2f}% "
                f"win_rate={hv_only['win_rate_vs_base']:.3f} "
                f"DM_p={hv_dm.get('p_value'):.4f} DM_better={hv_dm.get('a_more_accurate')}"
            )
            hv = res["slices"]["top_realized_vol_decile"]["gate_pathway_soft"]
            recent = res["slices"]["recent_2025_2026"]["gate_pathway_soft"]
            print(
                "  gate_soft slices: "
                f"top_vol_decile={hv.get('qlike_improvement_pct'):.2f}% "
                f"recent_2025_2026={recent.get('qlike_improvement_pct'):.2f}%"
            )
            var5 = res["var_calibration"]["pooled"]["gate_pathway_soft"]["var_5pct"]
            var1 = res["var_calibration"]["pooled"]["gate_pathway_soft"]["var_1pct"]
            cal_var5 = res["residual_var_calibration"]["pooled"]["gate_pathway_soft"]["var_5pct"]
            cal_var1 = res["residual_var_calibration"]["pooled"]["gate_pathway_soft"]["var_1pct"]
            print(
                "  gate_soft VaR: "
                f"5pct breach={var5.get('breach_rate'):.3f} Kupiec_p={var5.get('kupiec_p_value'):.4f} "
                f"1pct breach={var1.get('breach_rate'):.3f} Kupiec_p={var1.get('kupiec_p_value'):.4f}"
            )
            print(
                "  gate_soft residual-calibrated VaR: "
                f"5pct breach={cal_var5.get('breach_rate'):.3f} Kupiec_p={cal_var5.get('kupiec_p_value'):.4f} "
                f"1pct breach={cal_var1.get('breach_rate'):.3f} Kupiec_p={cal_var1.get('kupiec_p_value'):.4f}"
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
