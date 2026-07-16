#!/usr/bin/env python3
"""Shadow-evaluate volatility-gated 00631L scaling on top of active A21.18.

Research-only. This script does not update the latest strategy, live signal, or
any allocation file. It tests whether the shadow volatility gate from
group_a_plus.integrations.garch_regime_shadow would have helped if translated
into 00631L exposure scaling after transaction costs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.garch_regime_shadow import (
    HIGH_VOL_REFERENCE_SCALE,
    LOW_VOL_PERCENTILE_THRESHOLD,
    LOW_VOL_RATIO_MAX,
    NEUTRAL_VOL_REFERENCE_SCALE,
    PERCENTILE_THRESHOLD,
    RATIO_THRESHOLD,
    REQUIRE_NEGATIVE_5D,
    volatility_gate_reference,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.backtest.backtest_group_a_plus_financial_econometrics import _garch_features


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_volatility_gate_shadow_latest.json"
CONFIRMED_TOTAL_RISK_SCORE_MIN = 6
CONFIRMED_NCF_H20_MAX = 0.45
CONFIRMED_NCF_MDD_MIN = 0.50
CONFIRMED_NO_TRADE_BAND = 0.05
DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    import duckdb

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


def _scaled_00631l_to_0050(golden_weights: dict[str, float], scale: float) -> dict[str, float]:
    weights = dict(golden_weights)
    scale = min(max(float(scale), 0.0), 1.0)
    current = float(weights.get("00631L.TW", 0.0) or 0.0)
    target = current * scale
    shift = current - target
    weights["00631L.TW"] = target
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0) or 0.0) + shift
    return _normalize(weights)


def _load_panel(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    panel_path = _resolve(path)
    if not panel_path.exists():
        return None
    panel = pd.read_csv(panel_path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    panel.index = pd.to_datetime(panel.index).normalize()
    return panel


def _build_volatility_gate_frame(prices: pd.DataFrame, chip_features: pd.DataFrame) -> pd.DataFrame:
    features = _garch_features(prices, chip_features)
    high_vol = (
        (features["garch_proxy_vol_ratio"] >= RATIO_THRESHOLD)
        | (features["garch_proxy_vol_percentile"] >= PERCENTILE_THRESHOLD)
    )
    if REQUIRE_NEGATIVE_5D:
        high_vol = high_vol & (features["return_0050_5d"] < 0.0)
    low_vol = (
        ~high_vol
        & (features["garch_proxy_vol_percentile"] <= LOW_VOL_PERCENTILE_THRESHOLD)
        & (features["garch_proxy_vol_ratio"] <= LOW_VOL_RATIO_MAX)
    )
    gate = pd.Series("neutral_vol", index=features.index, dtype=object)
    gate.loc[low_vol] = "low_vol_participation"
    gate.loc[high_vol] = "high_vol_defensive"
    out = features.copy()
    out["volatility_gate"] = gate
    out["high_vol_gate"] = high_vol.astype(bool)
    out["low_vol_gate"] = low_vol.astype(bool)
    return out


def _regime_with_vol_gate(
    execution_regime: pd.Series,
    gate_frame: pd.DataFrame,
    *,
    mode: str,
) -> pd.Series:
    out = execution_regime.copy()
    aligned_gate = gate_frame["volatility_gate"].reindex(out.index).fillna("neutral_vol")
    golden = out.astype(str) == "golden1"
    high = aligned_gate == "high_vol_defensive"
    neutral = aligned_gate == "neutral_vol"
    out.loc[golden & high] = "golden1_vol_gate_high"
    if mode == "tiered":
        out.loc[golden & neutral] = "golden1_vol_gate_neutral"
    return out


def _confirmed_high_vol_mask(
    execution_regime: pd.Series,
    gate_frame: pd.DataFrame,
    frame: pd.DataFrame,
    panel_631l: pd.DataFrame | None,
    *,
    total_risk_score_min: int = CONFIRMED_TOTAL_RISK_SCORE_MIN,
    ncf_h20_max: float = CONFIRMED_NCF_H20_MAX,
    ncf_mdd_min: float = CONFIRMED_NCF_MDD_MIN,
) -> pd.Series:
    high_vol = gate_frame["volatility_gate"].reindex(execution_regime.index).fillna("neutral_vol") == "high_vol_defensive"
    golden = execution_regime.astype(str) == "golden1"
    total_risk = pd.to_numeric(frame.get("total_risk_score"), errors="coerce").reindex(execution_regime.index).fillna(0)
    risk_confirmed = total_risk >= int(total_risk_score_min)

    if panel_631l is None:
        ncf_confirmed = pd.Series(False, index=execution_regime.index)
    else:
        h20 = pd.to_numeric(panel_631l.get("prob_up_h20"), errors="coerce").reindex(execution_regime.index)
        mdd = pd.to_numeric(panel_631l.get("prob_fwd_mdd_gt5_h20"), errors="coerce").reindex(execution_regime.index)
        ncf_confirmed = (h20 <= float(ncf_h20_max)) | (mdd >= float(ncf_mdd_min))
        ncf_confirmed = ncf_confirmed.fillna(False)

    return (golden & high_vol & risk_confirmed & ncf_confirmed).astype(bool)


def _regime_with_confirmed_high_vol_gate(
    execution_regime: pd.Series,
    gate_frame: pd.DataFrame,
    frame: pd.DataFrame,
    panel_631l: pd.DataFrame | None,
) -> pd.Series:
    out = execution_regime.copy()
    confirmed = _confirmed_high_vol_mask(execution_regime, gate_frame, frame, panel_631l)
    out.loc[confirmed] = "golden1_vol_gate_high_confirmed"
    return out


def _current_weights(value: float, price_row: pd.Series, shares: dict[str, float], cash: float) -> dict[str, float]:
    if value <= 0:
        return {ticker: 0.0 for ticker in TICKERS} | {"cash": 1.0}
    weights = {
        ticker: float(shares.get(ticker, 0.0) or 0.0) * float(price_row[ticker]) / value
        for ticker in TICKERS
    }
    weights["cash"] = float(cash) / value
    return _normalize(weights)


def _simulate_costed_curve_with_no_trade_band(
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    no_trade_band: float,
) -> tuple[pd.Series, dict[str, float]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    skipped_rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            weights = _normalize(weights_by_regime[next_regime])
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            current_w = _current_weights(gross_value, price_row, shares, cash)
            turnover_ratio = sum(abs(float(weights.get(ticker, 0.0)) - float(current_w.get(ticker, 0.0))) for ticker in TICKERS)
            if current_regime is not None and turnover_ratio < float(no_trade_band):
                skipped_rebalance_count += 1
                current_regime = next_regime
                values.append(gross_value)
                continue

            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "skipped_rebalance_count": int(skipped_rebalance_count),
        "no_trade_band": float(no_trade_band),
    }


def _cap_00631l_add(
    target: dict[str, float],
    current: dict[str, float],
    destination: str = "0050.TW",
) -> tuple[dict[str, float], bool, float]:
    target_w = _normalize(dict(target))
    current_631l = float(current.get("00631L.TW", 0.0) or 0.0)
    target_631l = float(target_w.get("00631L.TW", 0.0) or 0.0)
    excess_add = max(target_631l - current_631l, 0.0)
    if excess_add <= 1e-12:
        return target_w, False, 0.0
    target_w["00631L.TW"] = current_631l
    target_w[destination] = float(target_w.get(destination, 0.0) or 0.0) + excess_add
    return _normalize(target_w), True, float(excess_add)


def _simulate_costed_curve_with_no_add_gate(
    prices: pd.DataFrame,
    regimes: pd.Series,
    gate_frame: pd.DataFrame,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    no_trade_band: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    skipped_rebalance_count = 0
    no_add_days = 0
    capped_weight_sum = 0.0

    aligned_gate = gate_frame["volatility_gate"].reindex(regimes.index).fillna("neutral_vol")
    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        high_vol = str(aligned_gate.loc[dt]) == "high_vol_defensive"
        if next_regime != current_regime:
            current_w = _current_weights(gross_value, price_row, shares, cash)
            weights = _normalize(weights_by_regime[next_regime])
            if high_vol:
                weights, capped, capped_weight = _cap_00631l_add(weights, current_w)
                if capped:
                    no_add_days += 1
                    capped_weight_sum += capped_weight

            turnover_ratio = sum(abs(float(weights.get(ticker, 0.0)) - float(current_w.get(ticker, 0.0))) for ticker in TICKERS)
            if current_regime is not None and turnover_ratio < float(no_trade_band):
                skipped_rebalance_count += 1
                current_regime = next_regime
                values.append(gross_value)
                continue

            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "skipped_rebalance_count": int(skipped_rebalance_count),
        "no_add_days": int(no_add_days),
        "capped_00631l_weight_sum": round(float(capped_weight_sum), 6),
        "no_trade_band": float(no_trade_band),
        "policy": "high_vol_no_add_00631l_shadow",
    }


def _gate_counts(execution_regime: pd.Series, gate_frame: pd.DataFrame) -> dict[str, int]:
    aligned_gate = gate_frame["volatility_gate"].reindex(execution_regime.index).fillna("neutral_vol")
    golden = execution_regime.astype(str) == "golden1"
    return {
        "golden_low_vol_days": int((golden & (aligned_gate == "low_vol_participation")).sum()),
        "golden_neutral_vol_days": int((golden & (aligned_gate == "neutral_vol")).sum()),
        "golden_high_vol_days": int((golden & (aligned_gate == "high_vol_defensive")).sum()),
        "all_high_vol_days": int((aligned_gate == "high_vol_defensive").sum()),
    }


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    return {f"delta_{key}": float(candidate[key]) - float(baseline[key]) for key in keys}


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
    total_return_prices, dividend_coverage = _load_total_return_prices(db_path, prices.index)
    gate_frame = _build_volatility_gate_frame(prices, chip_features).reindex(frame.index)
    execution_regime = frame["execution_regime"].astype(str)
    baseline_metrics = dict(report["metrics"])
    baseline_execution = dict(report["execution"])
    golden_weights = dict(report["base_weights"]["golden1"])

    weights_by_regime = dict(report["base_weights"])
    weights_by_regime["golden1_vol_gate_high"] = _scaled_00631l_to_0050(
        golden_weights,
        HIGH_VOL_REFERENCE_SCALE,
    )
    weights_by_regime["golden1_vol_gate_neutral"] = _scaled_00631l_to_0050(
        golden_weights,
        NEUTRAL_VOL_REFERENCE_SCALE,
    )
    weights_by_regime["golden1_vol_gate_high_confirmed"] = _scaled_00631l_to_0050(
        golden_weights,
        HIGH_VOL_REFERENCE_SCALE,
    )

    variants: dict[str, Any] = {
        "baseline_a2118": {
            "metrics": baseline_metrics,
            "execution": baseline_execution,
            "delta_vs_baseline": {},
        }
    }
    for mode in ("high_only", "tiered"):
        gated_regime = _regime_with_vol_gate(execution_regime, gate_frame, mode=mode)
        curve, sim = _simulate_costed_curve(
            total_return_prices,
            gated_regime,
            weights_by_regime,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        variants[f"vol_gate_{mode}"] = {
            "metrics": metrics,
            "execution": sim,
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "changed_days": int((gated_regime != execution_regime).sum()),
            "extra_rebalances": int(sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
            "extra_turnover_value": float(sim["turnover_value"] - baseline_execution.get("turnover_value", 0.0)),
        }
    panel_631l = _load_panel(ncf_panel_631l)
    confirmed_regime = _regime_with_confirmed_high_vol_gate(
        execution_regime,
        gate_frame,
        frame,
        panel_631l,
    )
    confirmed_curve, confirmed_sim = _simulate_costed_curve_with_no_trade_band(
        total_return_prices,
        confirmed_regime,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
        CONFIRMED_NO_TRADE_BAND,
    )
    confirmed_metrics = _metrics(confirmed_curve, initial_value)
    confirmed_mask = confirmed_regime != execution_regime
    variants["vol_gate_confirmed_high_no_trade"] = {
        "metrics": confirmed_metrics,
        "execution": confirmed_sim,
        "delta_vs_baseline": _metric_delta(confirmed_metrics, baseline_metrics),
        "changed_days": int(confirmed_mask.sum()),
        "extra_rebalances": int(confirmed_sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
        "extra_transaction_cost": float(confirmed_sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        "extra_turnover_value": float(confirmed_sim["turnover_value"] - baseline_execution.get("turnover_value", 0.0)),
        "confirmation_policy": {
            "total_risk_score_min": CONFIRMED_TOTAL_RISK_SCORE_MIN,
            "ncf_h20_max": CONFIRMED_NCF_H20_MAX,
            "ncf_mdd_min": CONFIRMED_NCF_MDD_MIN,
            "no_trade_band": CONFIRMED_NO_TRADE_BAND,
        },
    }
    no_add_curve, no_add_sim = _simulate_costed_curve_with_no_add_gate(
        total_return_prices,
        execution_regime,
        gate_frame,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
        0.0,
    )
    no_add_metrics = _metrics(no_add_curve, initial_value)
    variants["vol_gate_high_no_add"] = {
        "metrics": no_add_metrics,
        "execution": no_add_sim,
        "delta_vs_baseline": _metric_delta(no_add_metrics, baseline_metrics),
        "changed_days": int(no_add_sim["no_add_days"]),
        "extra_rebalances": int(no_add_sim["rebalance_count"] - baseline_execution.get("rebalance_count", 0)),
        "extra_transaction_cost": float(no_add_sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        "extra_turnover_value": float(no_add_sim["turnover_value"] - baseline_execution.get("turnover_value", 0.0)),
        "confirmation_policy": {
            "no_trade_band": 0.0,
            "action": "cap_00631l_add_only_when_high_vol_gate_active",
            "destination": "0050.TW",
        },
    }

    latest_gate = gate_frame.iloc[-1]
    latest_gate_reference = volatility_gate_reference(
        high_vol=bool(latest_gate["high_vol_gate"]),
        ratio=float(latest_gate["garch_proxy_vol_ratio"]),
        percentile=float(latest_gate["garch_proxy_vol_percentile"]),
        return_5d=float(latest_gate["return_0050_5d"]),
    )
    return {
        "label": label,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "gate_counts": _gate_counts(execution_regime, gate_frame),
        "latest_volatility_gate": latest_gate_reference,
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
            row = {
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
                **result["gate_counts"],
            }
            rows.append(row)

    report = {
        "experiment": "group_a_plus_volatility_gate_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_allocation_change",
        "source_idea": "volatility/regime gating and scaling; inspired by 2606.09478v1.pdf",
        "params": {
            "high_vol_ratio_threshold": RATIO_THRESHOLD,
            "high_vol_percentile_threshold": PERCENTILE_THRESHOLD,
            "require_negative_5d": REQUIRE_NEGATIVE_5D,
            "low_vol_percentile_threshold": LOW_VOL_PERCENTILE_THRESHOLD,
            "low_vol_ratio_max": LOW_VOL_RATIO_MAX,
            "high_vol_reference_00631l_scale": HIGH_VOL_REFERENCE_SCALE,
            "neutral_vol_reference_00631l_scale": NEUTRAL_VOL_REFERENCE_SCALE,
            "confirmed_total_risk_score_min": CONFIRMED_TOTAL_RISK_SCORE_MIN,
            "confirmed_ncf_h20_max": CONFIRMED_NCF_H20_MAX,
            "confirmed_ncf_mdd_min": CONFIRMED_NCF_MDD_MIN,
            "confirmed_no_trade_band": CONFIRMED_NO_TRADE_BAND,
            "scale_destination": "0050.TW",
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
            f"delta_final={row.get('delta_final_value', 0.0):,.0f}, "
            f"delta_sharpe={row.get('delta_sharpe_ratio', 0.0):.4f}, "
            f"delta_mdd={row.get('delta_max_drawdown', 0.0):.2%}, "
            f"extra_cost={row.get('extra_transaction_cost', 0.0):,.0f}, "
            f"changed_days={row.get('changed_days', 0)}"
        )


if __name__ == "__main__":
    main()
