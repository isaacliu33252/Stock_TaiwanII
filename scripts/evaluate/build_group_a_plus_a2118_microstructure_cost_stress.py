#!/usr/bin/env python3
"""A21.18 microstructure cost stress test (not SciPhyRL/PINN).

User-directed 2026-08-26 follow-up to the 2607.15195 review: do not open an
RL main-line on SciPhyRL/HJB. Instead, replace the flat commission/slippage/tax
cost model with a liquidity-aware (linear ADV participation) and a quadratic
size/ADV impact model, estimated *separately* for 0050.TW / 00631L.TW /
00632R.TW / 00679B.TWO (their ADV differs by ~2-3x), and re-price:

  1. The live A21.18 regime-switch schedule itself (full history, same
     regime decisions -- this script changes cost accounting only, never the
     regime/weight logic).
  2. The raw A21.18 seed-ensemble target vs the guarded live target (the
     08-25 2607.15195 cost-aware target-holding shadow's two scenarios),
     which is the clearest still-open "small positive candidate" pending a
     cost re-check.

at three stress levels: 1x current cost (flat only, matches production),
2x realistic impact (linear/quadratic coefficients doubled vs the already
governance-approved 2607.15195 calibration), and stress liquidity (ADV
divided by 5 to simulate a liquidity crunch, e.g. a crash day).

TXO put overlay and seed-averaging-the-PPO-ensemble are NOT re-priced here:
the former trades TAIFEX options (no equity ADV to speak of), the latter is
a training-time artifact whose only tradeable output is the raw/guarded
target already covered by (2) above. BAWS is a VaR/ES forecaster, not a
strategy with its own turnover -- also out of scope.
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

from backtest_group_a_plus_defensive_basket import BOND_ETFS, _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR as TARGET_HOLDING_FORWARD_MONITOR,
    DEFAULT_LIVE_SNAPSHOT as TARGET_HOLDING_LIVE_SNAPSHOT,
    _load_adv as _load_adv_snapshot,
    _load_json as _load_target_holding_json,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_microstructure_cost_stress.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/a2118_microstructure_cost_stress/history"
DEFAULT_LIVE_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_FORWARD_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"

# Same base calibration already governance-approved in the 2607.15195
# cost-aware target-holding shadow (linear_cost_bps / quadratic_impact_bps).
# "2x realistic impact" doubles these; "stress liquidity" keeps them but
# divides effective ADV by ADV_STRESS_DIVISOR.
BASE_LINEAR_IMPACT_BPS = 5.0
BASE_QUADRATIC_IMPACT_BPS = 25.0
ADV_STRESS_DIVISOR = 5.0

COST_SCENARIOS: tuple[dict[str, Any], ...] = (
    {"name": "1x_current_cost", "cost_model": "flat", "impact_bps": 0.0, "adv_stress_divisor": 1.0},
    {
        "name": "realistic_impact_linear",
        "cost_model": "linear_liquidity",
        "impact_bps": BASE_LINEAR_IMPACT_BPS,
        "adv_stress_divisor": 1.0,
    },
    {
        "name": "2x_realistic_impact_linear",
        "cost_model": "linear_liquidity",
        "impact_bps": BASE_LINEAR_IMPACT_BPS * 2,
        "adv_stress_divisor": 1.0,
    },
    {
        "name": "stress_liquidity_linear",
        "cost_model": "linear_liquidity",
        "impact_bps": BASE_LINEAR_IMPACT_BPS,
        "adv_stress_divisor": ADV_STRESS_DIVISOR,
    },
    {
        "name": "realistic_impact_quadratic",
        "cost_model": "quadratic_impact",
        "impact_bps": BASE_QUADRATIC_IMPACT_BPS,
        "adv_stress_divisor": 1.0,
    },
    {
        "name": "2x_realistic_impact_quadratic",
        "cost_model": "quadratic_impact",
        "impact_bps": BASE_QUADRATIC_IMPACT_BPS * 2,
        "adv_stress_divisor": 1.0,
    },
    {
        "name": "stress_liquidity_quadratic",
        "cost_model": "quadratic_impact",
        "impact_bps": BASE_QUADRATIC_IMPACT_BPS,
        "adv_stress_divisor": ADV_STRESS_DIVISOR,
    },
)

DEFAULT_NAV_SCALES: tuple[float, ...] = (1_486_457.0, 10_000_000.0, 50_000_000.0, 200_000_000.0)


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_adv_history(db_path: Path, tickers: tuple[str, ...], start: str, end: str, window: int) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt <= ?
            ORDER BY dt
            """,
            [*tickers, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    rows["notional"] = rows["close"].astype(float) * rows["volume"].astype(float)
    pivot = rows.pivot(index="dt", columns="ticker", values="notional").sort_index()
    adv = pivot.rolling(window, min_periods=5).mean()
    return adv.loc[pd.Timestamp(start):]


def _trade_cost_with_impact(
    current_values: dict[str, float],
    target_values: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    adv_notional_today: dict[str, float],
    cost_model: str,
    impact_bps: float,
    adv_stress_divisor: float,
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    cost = 0.0
    turnover = 0.0
    extra_by_ticker: dict[str, float] = {}
    participation_by_ticker: dict[str, float] = {}
    for ticker in TICKERS:
        trade = float(target_values.get(ticker, 0.0)) - float(current_values.get(ticker, 0.0))
        notional = abs(trade)
        turnover += notional
        base = 0.0
        if trade > 0.0:
            base = notional * (commission_rate + slippage_rate)
        elif trade < 0.0:
            tax = 0.0 if ticker in BOND_ETFS else equity_etf_sell_tax
            base = notional * (commission_rate + slippage_rate + tax)
        extra = 0.0
        participation = 0.0
        if cost_model != "flat" and notional > 0.0:
            adv = float(adv_notional_today.get(ticker, 0.0) or 0.0) / adv_stress_divisor
            participation = notional / adv if adv > 0.0 else 0.0
            if cost_model == "linear_liquidity":
                extra = notional * impact_bps / 10000.0 * participation
            elif cost_model == "quadratic_impact":
                extra = notional * impact_bps / 10000.0 * participation * participation
        cost += base + extra
        extra_by_ticker[ticker] = extra_by_ticker.get(ticker, 0.0) + extra
        participation_by_ticker[ticker] = max(participation_by_ticker.get(ticker, 0.0), participation)
    return cost, turnover, extra_by_ticker, participation_by_ticker


def _simulate_costed_curve_with_impact(
    prices: pd.DataFrame,
    adv: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    cost_model: str,
    impact_bps: float,
    adv_stress_divisor: float,
) -> tuple[pd.Series, dict[str, Any]]:
    def _normalize(weights: dict[str, float]) -> dict[str, float]:
        total = sum(max(v, 0.0) for v in weights.values())
        if total <= 0:
            return {k: 0.0 for k in weights}
        return {k: max(v, 0.0) / total for k, v in weights.items()}

    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_regime: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    total_extra_by_ticker = {ticker: 0.0 for ticker in TICKERS}
    max_participation_by_ticker = {ticker: 0.0 for ticker in TICKERS}
    participation_sum_by_ticker = {ticker: 0.0 for ticker in TICKERS}
    participation_n_by_ticker = {ticker: 0 for ticker in TICKERS}

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:
            weights = _normalize(weights_by_regime[next_regime])
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            adv_today = {ticker: float(adv.loc[dt, ticker]) if dt in adv.index and pd.notna(adv.loc[dt, ticker]) else 0.0 for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            extra_by_ticker: dict[str, float] = {}
            participation_by_ticker: dict[str, float] = {}
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover, extra_by_ticker, participation_by_ticker = _trade_cost_with_impact(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                    adv_today,
                    cost_model,
                    impact_bps,
                    adv_stress_divisor,
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
            for ticker in TICKERS:
                total_extra_by_ticker[ticker] += extra_by_ticker.get(ticker, 0.0)
                p = participation_by_ticker.get(ticker, 0.0)
                if p > 0.0:
                    max_participation_by_ticker[ticker] = max(max_participation_by_ticker[ticker], p)
                    participation_sum_by_ticker[ticker] += p
                    participation_n_by_ticker[ticker] += 1
        values.append(gross_value)

    avg_participation_by_ticker = {
        ticker: (participation_sum_by_ticker[ticker] / participation_n_by_ticker[ticker])
        if participation_n_by_ticker[ticker] > 0
        else 0.0
        for ticker in TICKERS
    }
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "extra_impact_cost": float(sum(total_extra_by_ticker.values())),
        "extra_impact_cost_by_ticker": {t: _float(v) for t, v in total_extra_by_ticker.items()},
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "avg_participation_of_adv_by_ticker": {t: _float(v) for t, v in avg_participation_by_ticker.items()},
        "max_participation_of_adv_by_ticker": {t: _float(v) for t, v in max_participation_by_ticker.items()},
    }


def _reprice_target_holding(db_path: Path) -> dict[str, Any]:
    """Re-price the 2607.15195 raw-vs-guarded target-holding shadow's two
    scenarios under all 7 cost scenarios, at the *actual current* GroupA+
    AUM (~NT$1.49M) -- this is the concrete, decision-relevant question for
    the still-open raw A21.18 seed-ensemble target candidate, as opposed to
    the hypothetical NAV-scaling question answered by the full-history run.
    """
    live_snapshot = _load_target_holding_json(TARGET_HOLDING_LIVE_SNAPSHOT)
    forward_monitor = _load_target_holding_json(TARGET_HOLDING_FORWARD_MONITOR)
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    if not portfolio or not live_signal:
        return {"status": "unavailable", "reason": "live_snapshot_or_forward_monitor_missing"}

    current_shares = {str(k): float(v) for k, v in (portfolio.get("shares") or {}).items()}
    prices = {str(k): float(v) for k, v in (portfolio.get("latest_prices") or {}).items()}
    total_assets = float(portfolio.get("total_assets", 0.0) or 0.0)
    as_of = str(live_snapshot.get("as_of") or forward_monitor.get("as_of") or datetime.now().date())
    guarded_target = live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {}
    raw_target = (
        live_snapshot.get("target_weights_for_action")
        if isinstance(live_snapshot.get("target_weights_for_action"), dict)
        else {}
    )
    if not guarded_target or not raw_target or total_assets <= 0:
        return {"status": "unavailable", "reason": "target_weights_or_total_assets_missing"}

    adv = _load_adv_snapshot(db_path, tickers=TICKERS, as_of=as_of, adv_window=20)

    def _target_shares(weights: dict[str, float]) -> dict[str, int]:
        out = {}
        for ticker in TICKERS:
            price = float(prices.get(ticker, 0.0) or 0.0)
            out[ticker] = int(round(total_assets * float(weights.get(ticker, 0.0) or 0.0) / price)) if price > 0 else 0
        return out

    def _cost_for(target_weights: dict[str, float], scenario: dict[str, Any]) -> dict[str, Any]:
        current_values = {ticker: current_shares.get(ticker, 0.0) * prices.get(ticker, 0.0) for ticker in TICKERS}
        target_values = {ticker: total_assets * float(target_weights.get(ticker, 0.0) or 0.0) for ticker in TICKERS}
        cost, turnover, extra_by_ticker, participation_by_ticker = _trade_cost_with_impact(
            current_values,
            target_values,
            0.001425,
            0.0005,
            0.001,
            adv,
            scenario["cost_model"],
            scenario["impact_bps"],
            scenario["adv_stress_divisor"],
        )
        return {
            "scenario": scenario["name"],
            "total_estimated_cost": _float(cost),
            "total_estimated_cost_bps_of_assets": _float(cost / total_assets * 10000.0),
            "turnover_notional": _float(turnover),
            "extra_impact_cost_by_ticker": {t: _float(v) for t, v in extra_by_ticker.items()},
            "participation_of_adv_by_ticker": {t: _float(v) for t, v in participation_by_ticker.items()},
        }

    return {
        "status": "ok",
        "as_of": as_of,
        "portfolio_total_assets": _float(total_assets),
        "adv_notional_20d": {t: _float(v) for t, v in adv.items()},
        "guarded_live_target_weights": guarded_target,
        "raw_a2118_target_weights": raw_target,
        "guarded_live_target_by_scenario": [_cost_for(guarded_target, s) for s in COST_SCENARIOS],
        "raw_a2118_target_by_scenario": [_cost_for(raw_target, s) for s in COST_SCENARIOS],
    }


def build_report(
    *,
    start: str = "2020-01-02",
    end: str = "2026-08-24",
    db_path: Path = DB_PATH,
    nav_scales: tuple[float, ...] = DEFAULT_NAV_SCALES,
    ncf_panel_631l_path: str = "results/ncf_00631l_panel_latest_20260716.csv",
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> dict[str, Any]:
    # Run the live A21.18 decision logic ONCE at reference scale to obtain the
    # actual production regime/weight schedule (unchanged by this script).
    report, out_frame = run_a2118(
        start,
        end,
        nav_scales[0],
        db_path,
        180,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
        ncf_panel_631l_path=ncf_panel_631l_path,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=10,
        risk_score_lookback_days=5,
        momentum_fast_exit_min=0.1,
        momentum_fast_exit_ma_gap_min=-0.08,
    )
    weights_by_regime = report["base_weights"]
    execution_regime = out_frame["execution_regime"]
    prices, _coverage = _load_total_return_prices(db_path, execution_regime.index)
    adv = _load_adv_history(db_path, TICKERS, str(execution_regime.index[0].date()), end, window=20)
    adv = adv.reindex(execution_regime.index).ffill()

    per_nav: list[dict[str, Any]] = []
    for nav in nav_scales:
        baseline_curve, baseline_stats = _simulate_costed_curve_with_impact(
            prices,
            adv,
            execution_regime,
            weights_by_regime,
            nav,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
            "flat",
            0.0,
            1.0,
        )
        baseline_metrics = _metrics(baseline_curve, nav)
        scenario_rows: list[dict[str, Any]] = []
        for scenario in COST_SCENARIOS:
            curve, stats = _simulate_costed_curve_with_impact(
                prices,
                adv,
                execution_regime,
                weights_by_regime,
                nav,
                commission_rate,
                slippage_rate,
                equity_etf_sell_tax,
                scenario["cost_model"],
                scenario["impact_bps"],
                scenario["adv_stress_divisor"],
            )
            metrics = _metrics(curve, nav)
            scenario_rows.append(
                {
                    "scenario": scenario["name"],
                    "cost_model": scenario["cost_model"],
                    "impact_bps": scenario["impact_bps"],
                    "adv_stress_divisor": scenario["adv_stress_divisor"],
                    "final_value": _float(curve.iloc[-1]),
                    "sharpe_ratio": _float(metrics["sharpe_ratio"]),
                    "sharpe_delta_vs_flat": _float(metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
                    "max_drawdown": _float(metrics["max_drawdown"]),
                    "max_drawdown_delta_vs_flat": _float(metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
                    "total_transaction_cost": _float(stats["transaction_cost"]),
                    "total_extra_impact_cost": _float(stats["extra_impact_cost"]),
                    "extra_impact_cost_bps_of_nav": _float(stats["extra_impact_cost"] / nav * 10000.0),
                    "extra_impact_cost_by_ticker": stats["extra_impact_cost_by_ticker"],
                    "avg_participation_of_adv_by_ticker": stats["avg_participation_of_adv_by_ticker"],
                    "max_participation_of_adv_by_ticker": stats["max_participation_of_adv_by_ticker"],
                    "rebalance_count": stats["rebalance_count"],
                }
            )
        per_nav.append(
            {
                "nav": nav,
                "baseline_flat_final_value": _float(baseline_curve.iloc[-1]),
                "baseline_flat_sharpe": _float(baseline_metrics["sharpe_ratio"]),
                "baseline_flat_max_drawdown": _float(baseline_metrics["max_drawdown"]),
                "scenarios": scenario_rows,
            }
        )

    adv_summary = {
        ticker: {
            "mean_adv_notional": _float(adv[ticker].mean()),
            "median_adv_notional": _float(adv[ticker].median()),
            "min_adv_notional": _float(adv[ticker].min()),
        }
        for ticker in TICKERS
    }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_a2118_microstructure_cost_stress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "user_directive": (
            "2026-08-26: do not open an RL main-line on A21.19 SciPhyRL; instead "
            "re-price the already-live A21.18 turnover under liquidity-aware and "
            "quadratic ADV-impact cost models, per ticker, at 1x/2x/stress."
        ),
        "period": {"start": str(execution_regime.index[0].date()), "end": str(execution_regime.index[-1].date())},
        "tickers": list(TICKERS),
        "adv_summary": adv_summary,
        "base_calibration": {
            "linear_impact_bps": BASE_LINEAR_IMPACT_BPS,
            "quadratic_impact_bps": BASE_QUADRATIC_IMPACT_BPS,
            "adv_stress_divisor": ADV_STRESS_DIVISOR,
            "note": "same coefficients already used by report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json",
        },
        "nav_scale_results": per_nav,
        "raw_vs_guarded_target_reprice_at_current_aum": _reprice_target_holding(db_path),
        "decision": {
            "allow_sciphyrl_optimizer_research": False,
            "allow_a2118_regime_logic_change": False,
            "target_weight_change_allowed": False,
            "summary": (
                "This report changes cost accounting only, not the A21.18 regime/weight "
                "decision logic. See per-NAV scenario table for whether liquidity-aware / "
                "quadratic ADV impact costs are material at GroupA+'s current AUM."
            ),
        },
    }


def write_report(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("period", {}).get("end") or datetime.now().date())
    (history_dir / f"a2118_microstructure_cost_stress_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-08-24")
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(start=args.start, end=args.end, db_path=Path(args.db_path))
    write_report(report, Path(args.output), Path(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    for nav_row in report["nav_scale_results"]:
        print(f"\n=== NAV {nav_row['nav']:,.0f} ===")
        print(f"baseline flat: sharpe={nav_row['baseline_flat_sharpe']} mdd={nav_row['baseline_flat_max_drawdown']}")
        for row in nav_row["scenarios"]:
            print(
                f"  {row['scenario']:<32} sharpe_delta={row['sharpe_delta_vs_flat']:<10} "
                f"extra_cost_bps_nav={row['extra_impact_cost_bps_of_nav']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
