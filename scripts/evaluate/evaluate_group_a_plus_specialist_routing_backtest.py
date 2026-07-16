#!/usr/bin/env python3
"""Costed shadow backtest for GroupA+ specialist routing.

This reconstructs route decisions historically, then tests conservative
weight translations on top of A21.18. Research-only: it does not update live
signals, strategy manifests, or production allocation rules.
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
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.garch_regime_shadow import volatility_gate_reference
from group_a_plus.integrations.risk_sensitive_loss import (
    risk_sensitive_loss,
    routing_regret_frame,
    summarize_routing_diagnostics,
    underprediction_loss,
)
from group_a_plus.integrations.specialist_router import route_specialist
from group_a_plus.operations.market_state import classify_market_state
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from group_a_plus.utils.tsmc_0050_weight import TSMC_0050_WEIGHT_ASSUMPTION
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_specialist_routing_backtest_latest.json"
DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]
SPECIALIST_HIGH_REGIME = "specialist_high_vol_half_00631l"
SPECIALIST_SEMI_REGIME = "specialist_semiconductor_half_00631l"
SPECIALIST_CRASH_REGIME = "specialist_crash_zero_00631l_cash"
SPECIALIST_NO_ADD_REGIME = "specialist_no_add_marker"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _parse_windows(raw: str | None) -> list[tuple[str, str, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    windows: list[tuple[str, str, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3 or not all(parts):
            raise ValueError("--windows items must be label:start:end")
        windows.append((parts[0], parts[1], parts[2]))
    return windows


def _scale_00631l(
    weights: dict[str, float],
    scale: float,
    *,
    destination: str = "0050.TW",
) -> dict[str, float]:
    out = dict(weights)
    scale = min(max(float(scale), 0.0), 1.0)
    current = float(out.get("00631L.TW", 0.0) or 0.0)
    target = current * scale
    shift = current - target
    out["00631L.TW"] = target
    out[destination] = float(out.get(destination, 0.0) or 0.0) + shift
    return _normalize(out)


def _load_external_closes(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ticker, dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance'
              AND ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt, ticker
            """.format(placeholders=", ".join(["?"] * len(tickers))),
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["date"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="date", columns="ticker", values="close").sort_index()


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close
            FROM ohlcv
            WHERE ticker = ?
              AND dt BETWEEN ? AND ?
              AND open IS NOT NULL
              AND high IS NOT NULL
              AND low IS NOT NULL
              AND close IS NOT NULL
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["date"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.set_index("date")[["open", "high", "low", "close"]].astype(float)


def _garman_klass_variance(ohlc: pd.DataFrame) -> pd.Series:
    high_low = (ohlc["high"] / ohlc["low"]).map(lambda value: math.log(float(value))) ** 2
    close_open = (ohlc["close"] / ohlc["open"]).map(lambda value: math.log(float(value))) ** 2
    return (0.5 * high_low - (2.0 * math.log(2.0) - 1.0) * close_open).clip(lower=1e-12)


def _risk_forecast_candidates(realized_variance: pd.Series) -> pd.DataFrame:
    rv = pd.to_numeric(realized_variance, errors="coerce").clip(lower=1e-12)
    neutral = rv.rolling(20, min_periods=10).mean()
    low = rv.rolling(20, min_periods=10).median()
    high = rv.rolling(20, min_periods=10).quantile(0.75)
    semi = rv.rolling(20, min_periods=10).quantile(0.70)
    crash = rv.rolling(20, min_periods=10).quantile(0.90)
    return pd.DataFrame(
        {
            "low_volatility": low,
            "neutral": neutral,
            "high_volatility": high,
            "semiconductor_risk": semi,
            "crash_deleverage": crash,
        },
        index=rv.index,
    ).clip(lower=1e-12)


def _routing_risk_diagnostics(
    route_frame: pd.DataFrame,
    *,
    db_path: Path,
    start: str,
    end: str,
    underprediction_weight: float = 1.0,
) -> dict[str, Any]:
    ohlc = _load_ohlc(db_path, "0050.TW", start, end)
    if ohlc.empty:
        return {"status": "unavailable", "reason": "missing_0050_ohlc"}
    realized = _garman_klass_variance(ohlc)
    target_next = realized.shift(-1).reindex(route_frame.index)
    forecasts = _risk_forecast_candidates(realized).reindex(route_frame.index)
    candidate_losses = pd.DataFrame(index=route_frame.index)
    candidate_under = pd.DataFrame(index=route_frame.index)
    for route in forecasts.columns:
        candidate_losses[route] = risk_sensitive_loss(
            target_next,
            forecasts[route],
            underprediction_weight=underprediction_weight,
        )
        candidate_under[route] = underprediction_loss(target_next, forecasts[route])
    regret = routing_regret_frame(
        selected_route=route_frame["route"],
        candidate_losses=candidate_losses,
    )
    selected_under: list[float | None] = []
    for dt, row in candidate_under.iterrows():
        route = str(route_frame.loc[dt, "route"])
        selected_under.append(float(row.get(route)) if route in row.index and pd.notna(row.get(route)) else None)
    regret["selected_underprediction_loss"] = selected_under
    summary = summarize_routing_diagnostics(regret)
    under = pd.to_numeric(regret["selected_underprediction_loss"], errors="coerce").dropna()
    summary.update(
        {
            "status": "available",
            "target": "0050.TW next-day squared Garman-Klass variance proxy",
            "forecast_proxy": "rolling 20-day GK variance branch forecasts by route",
            "underprediction_weight": float(underprediction_weight),
            "mean_selected_underprediction_loss": round(float(under.mean()), 8) if not under.empty else None,
            "underprediction_positive_rate": round(float((under > 0.0).mean()), 6) if not under.empty else None,
        }
    )
    return summary


def _semiconductor_health_frame(
    prices: pd.DataFrame,
    db_path: Path,
    *,
    tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION,
) -> pd.DataFrame:
    start = str((prices.index.min() - pd.Timedelta(days=90)).date())
    end = str(prices.index.max().date())
    external = _load_external_closes(db_path, ("2330.TW", "SOXX"), start, end)
    if external.empty or "2330.TW" not in external or "SOXX" not in external:
        return pd.DataFrame(index=prices.index)
    aligned = prices[["0050.TW"]].join(external[["2330.TW", "SOXX"]], how="left").ffill()
    out = pd.DataFrame(index=prices.index)
    ret_0050 = aligned["0050.TW"].pct_change(5)
    ret_2330 = aligned["2330.TW"].pct_change(5)
    ret_soxx = aligned["SOXX"].pct_change(5)
    ret_ex = (ret_0050 - float(tsmc_weight) * ret_2330) / max(1.0 - float(tsmc_weight), 1e-12)
    weak = ((ret_2330 <= -0.02) & (ret_soxx <= -0.02)) | (ret_soxx <= -0.04)
    narrow = (ret_2330 > 0.0) & (ret_ex <= 0.0) & ((ret_2330 - ret_0050) > 0.01)
    state = pd.Series("mixed", index=prices.index, dtype=object)
    state.loc[narrow.reindex(prices.index).fillna(False)] = "tsmc_led_narrow"
    state.loc[weak.reindex(prices.index).fillna(False)] = "tsmc_weak_confirmed"
    out["state"] = state
    out["ret_0050_5d"] = ret_0050.reindex(prices.index)
    out["ret_2330_5d"] = ret_2330.reindex(prices.index)
    out["ret_soxx_5d"] = ret_soxx.reindex(prices.index)
    out["ret_0050_ex_tsmc_5d"] = ret_ex.reindex(prices.index)
    out["available"] = True
    return out


def _latest_features(row: pd.Series) -> dict[str, Any]:
    return {
        "ma_gap": float(row.get("ma_gap", 0.0) or 0.0),
        "drawdown": float(row.get("drawdown", 0.0) or 0.0),
        "exit_momentum_5d": float(row.get("exit_momentum", 0.0) or 0.0),
        "total_risk_score": int(row.get("total_risk_score", 0) or 0),
        "tail_risk_score": int(row.get("tail_risk_score", 0) or 0),
    }


def _gate_payload(gate_row: pd.Series) -> dict[str, Any]:
    return volatility_gate_reference(
        high_vol=bool(gate_row.get("high_vol_gate", False)),
        ratio=float(gate_row.get("garch_proxy_vol_ratio", 0.0) or 0.0),
        percentile=float(gate_row.get("garch_proxy_vol_percentile", 0.0) or 0.0),
        return_5d=float(gate_row.get("return_0050_5d", 0.0) or 0.0),
    )


def _ncf_overlay_from_semiconductor(row: pd.Series | None) -> dict[str, Any]:
    if row is None or row.empty or not bool(row.get("available", False)):
        return {}
    state = str(row.get("state") or "mixed")
    if state not in {"tsmc_weak_confirmed", "tsmc_led_narrow"}:
        return {"tsmc_0050_health": {"status": "available", "state": state}}
    return {
        "tsmc_0050_health": {
            "status": "available",
            "state": state,
            "reference_guidance": {"allow_00631l_add": False},
            "returns": {
                "2330.TW": {"5d": round(float(row.get("ret_2330_5d", 0.0) or 0.0), 6)},
                "SOXX": {"5d": round(float(row.get("ret_soxx_5d", 0.0) or 0.0), 6)},
                "0050_ex_tsmc_proxy": {"5d": round(float(row.get("ret_0050_ex_tsmc_5d", 0.0) or 0.0), 6)},
            },
        }
    }


def build_specialist_route_frame(
    frame: pd.DataFrame,
    gate_frame: pd.DataFrame,
    semiconductor_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt, row in frame.iterrows():
        features = _latest_features(row)
        execution_regime = str(row.get("execution_regime", row.get("base_regime", "golden1")))
        market_state = classify_market_state(execution_regime, features)
        semi_row = semiconductor_frame.loc[dt] if dt in semiconductor_frame.index else None
        routing = route_specialist(
            volatility_gate=_gate_payload(gate_frame.loc[dt]),
            market_state=market_state,
            ncf_live_overlay=_ncf_overlay_from_semiconductor(semi_row),
            latest_features=features,
        )
        rows.append(
            {
                "date": dt,
                "route": routing["route"],
                "risk_level": routing["risk_level"],
                "recommended_action": routing["recommended_action"],
                "allow_00631l_add": routing["allow_00631l_add"],
                "market_state": market_state["state"],
                "volatility_gate": routing["inputs"]["volatility_gate"],
                "tsmc_state": routing["inputs"]["tsmc_0050_health_state"],
                "execution_regime": execution_regime,
            }
        )
    out = pd.DataFrame(rows).set_index("date")
    out.index = pd.to_datetime(out.index).normalize()
    return out


def _route_regime(
    execution_regime: pd.Series,
    route_frame: pd.DataFrame,
    *,
    mode: str,
) -> pd.Series:
    out = execution_regime.copy()
    eligible = out.astype(str).isin({"golden1"})
    route = route_frame["route"].reindex(out.index).fillna("neutral")
    if mode in {"high_vol_half", "combined"}:
        out.loc[eligible & (route == "high_volatility")] = SPECIALIST_HIGH_REGIME
    if mode in {"semiconductor_half", "combined"}:
        out.loc[eligible & (route == "semiconductor_risk")] = SPECIALIST_SEMI_REGIME
    if mode in {"crash_cash", "combined"}:
        out.loc[eligible & (route == "crash_deleverage")] = SPECIALIST_CRASH_REGIME
    return out


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    return {f"delta_{key}": float(candidate[key]) - float(baseline[key]) for key in keys}


def _route_counts(route_frame: pd.DataFrame, execution_regime: pd.Series) -> dict[str, int]:
    golden = execution_regime.astype(str) == "golden1"
    counts = {f"route_{route}_days": int((route_frame["route"] == route).sum()) for route in sorted(route_frame["route"].dropna().unique())}
    counts.update({f"golden_route_{route}_days": int((golden & (route_frame["route"] == route)).sum()) for route in sorted(route_frame["route"].dropna().unique())})
    return counts


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    db_path: Path,
    initial_value: float,
    ncf_panel_631l: str | None,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=ncf_panel_631l,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    )
    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip_features = _load_chip_features(db_path, prices.index, start, end)
    gate_frame = _build_volatility_gate_frame(prices, chip_features).reindex(frame.index)
    semiconductor_frame = _semiconductor_health_frame(prices, db_path).reindex(frame.index)
    route_frame = build_specialist_route_frame(frame, gate_frame, semiconductor_frame)
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)

    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])
    weights_by_regime = dict(report["base_weights"])
    weights_by_regime[SPECIALIST_HIGH_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_SEMI_REGIME] = _scale_00631l(golden_weights, 0.50, destination="0050.TW")
    weights_by_regime[SPECIALIST_CRASH_REGIME] = _scale_00631l(golden_weights, 0.0, destination="cash")

    variants: dict[str, Any] = {
        "baseline_a2118": {
            "metrics": baseline_metrics,
            "execution": baseline_execution,
            "delta_vs_baseline": {},
            "changed_days": 0,
        }
    }
    for mode in ("high_vol_half", "semiconductor_half", "crash_cash", "combined"):
        routed_regime = _route_regime(execution_regime, route_frame, mode=mode)
        curve, sim = _simulate_costed_curve(
            total_return_prices,
            routed_regime,
            weights_by_regime,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        variants[f"specialist_{mode}"] = {
            "metrics": metrics,
            "execution": sim,
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "changed_days": int((routed_regime != execution_regime).sum()),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "extra_turnover_value": float(sim["turnover_value"] - baseline_execution.get("turnover_value", 0.0)),
        }

    route_counts = _route_counts(route_frame, execution_regime)
    routing_risk_diagnostics = _routing_risk_diagnostics(
        route_frame,
        db_path=db_path,
        start=start,
        end=end,
    )
    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "route_counts": route_counts,
        "routing_risk_diagnostics": routing_risk_diagnostics,
        "semiconductor_proxy": {
            "status": "available" if not semiconductor_frame.empty and "available" in semiconductor_frame else "unavailable",
            "method": "5d 2330/SOXX/0050-ex-TSMC proxy",
            "tsmc_weight_assumption": TSMC_0050_WEIGHT_ASSUMPTION,
        },
        "variants": variants,
        "dividend_coverage": dividend_coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--windows", default=None, help="Comma-separated label:start:end windows.")
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = _resolve(args.db)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel = str(_resolve(args.ncf_panel_631l)) if args.ncf_panel_631l else None
    windows = []
    rows: list[dict[str, Any]] = []
    for label, start, end in _parse_windows(args.windows):
        result = evaluate_window(
            label=label,
            start=start,
            end=end,
            db_path=db_path,
            initial_value=args.initial_value,
            ncf_panel_631l=panel,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax,
        )
        windows.append(result)
        for variant, payload in result["variants"].items():
            diag = result.get("routing_risk_diagnostics") or {}
            rows.append(
                {
                    "window": label,
                    "variant": variant,
                    **payload["metrics"],
                    "transaction_cost": payload["execution"].get("transaction_cost"),
                    "turnover_value": payload["execution"].get("turnover_value"),
                    "rebalance_count": payload["execution"].get("rebalance_count"),
                    **payload.get("delta_vs_baseline", {}),
                    "changed_days": payload.get("changed_days", 0),
                    "extra_transaction_cost": payload.get("extra_transaction_cost", 0.0),
                    "extra_turnover_value": payload.get("extra_turnover_value", 0.0),
                    "routing_miss_best_rate": diag.get("miss_best_rate"),
                    "routing_mean_selected_regret": diag.get("mean_selected_regret"),
                    "routing_underprediction_positive_rate": diag.get("underprediction_positive_rate"),
                    "routing_mean_selected_underprediction_loss": diag.get("mean_selected_underprediction_loss"),
                    **result["route_counts"],
                }
            )

    report = {
        "experiment": "group_a_plus_specialist_routing_costed_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_allocation_change",
        "variants": {
            "specialist_high_vol_half": "high_volatility route halves golden1 00631L into 0050",
            "specialist_semiconductor_half": "semiconductor_risk route halves golden1 00631L into 0050",
            "specialist_crash_cash": "crash_deleverage route moves golden1 00631L to cash",
            "specialist_combined": "applies crash, semiconductor, and high-vol rules with router priority",
        },
        "cost_assumptions": {
            "commission_rate": args.commission_rate,
            "slippage_rate": args.slippage_rate,
            "equity_etf_sell_tax": args.equity_etf_sell_tax,
        },
        "windows": windows,
        "rows": rows,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in rows:
        if row["variant"] == "baseline_a2118":
            continue
        print(
            f"{row['window']} {row['variant']}: "
            f"final={row['final_value']:.0f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, "
            f"d_final={row.get('delta_final_value', 0.0):.0f}, "
            f"d_sharpe={row.get('delta_sharpe_ratio', 0.0):.4f}, "
            f"changed_days={row.get('changed_days', 0)}"
        )


if __name__ == "__main__":
    main()
