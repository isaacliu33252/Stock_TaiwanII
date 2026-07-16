#!/usr/bin/env python3
"""A22 bad-vol overlay evaluation (2026-07-10).

User-specified rule, tiered by trend (not vol alone):

  IF trend_good:    ignore vol forecast (00631L unrestricted, golden1 weights as-is)
  IF trend_neutral: vol high -> cap 00631L at --neutral-cap (default 10%)
  IF trend_bad:     vol high -> cap 00631L at --bad-cap (default 0%, i.e. full de-risk)

If vol is not high, weights are always left at golden1 defaults regardless of trend.

Motivation: the 00631L downside-race classifier line (see
GROUP_A_PLUS_00631L_DOWNSIDE_RISK_RACE_CLASSIFIER_HANDOFF_20260710.md) found that
classifier AUC kept improving across four tuning axes (adaptive threshold, deeper
model, relabeled horizon/thresholds, graduated de-risk sizing) without ever
translating into a positive final-value delta. This overlay tests a structurally
different idea: gate the (already-production) GARCH-proxy volatility-high flag on
trend state first, instead of using vol alone or an ML probability threshold alone.
This project's "symmetric volatility" phase (phase 1 of that same handoff) and
group_a_plus/runners/a2118.py's existing (untested) golden1 leverage-cap shadow
overlay both point at the same idea: high vol is not equivalent to downside risk,
especially inside an already-good trend.

trend_good/neutral/bad are derived from a2118's own ma_gap/drawdown frame columns
(the same proxies a2126's _apply_golden_leverage_cap_overlay already uses), not a
new feature. vol_high reuses the exact frozen production definition from
group_a_plus/integrations/garch_regime_shadow.py (ratio>=1.05 OR percentile>=0.70,
AND return_5d<0) -- the same flag that already drives the live pre-trade guard.

Note: golden1's baseline 00631L weight is ~10.9% (constant across windows), so a
--neutral-cap of 0.10 is only a ~0.9pp trim; --bad-cap of 0.0 is the meaningful
lever (full de-risk, same mechanism as the earlier all-or-nothing race-classifier
rule).

Research-only. Does not touch any live signal or target weight.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices, _metrics
from group_a_plus.integrations.garch_regime_shadow import (
    PERCENTILE_THRESHOLD,
    RATIO_THRESHOLD,
    REQUIRE_NEGATIVE_5D,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.backtest.backtest_group_a_plus_financial_econometrics import _garch_features

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_a22_bad_vol_overlay_latest.json"
TSMC_CHIP_CACHE = PROJECT_ROOT / "results" / "finmind_2330_institutional_buysell_cache.csv"

DEFAULT_WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("inflation_2022", "2022-01-03", "2022-12-30"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
]


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _classify_trend(
    ma_gap: pd.Series,
    drawdown: pd.Series,
    *,
    good_ma_gap_min: float,
    good_drawdown_min: float,
    bad_ma_gap_max: float,
    bad_drawdown_max: float,
) -> pd.Series:
    is_bad = (ma_gap <= bad_ma_gap_max) | (drawdown <= bad_drawdown_max)
    is_good = (~is_bad) & (ma_gap >= good_ma_gap_min) & (drawdown > good_drawdown_min)
    trend = pd.Series("neutral", index=ma_gap.index)
    trend[is_bad] = "bad"
    trend[is_good] = "good"
    return trend


def _require_bad_persistence(
    trend: pd.Series, min_streak: int, severe_bad: pd.Series | None = None
) -> pd.Series:
    """Demote 'bad' days back to 'neutral' until 'bad' has held for `min_streak`
    consecutive trading days (inclusive of today). Filters single-day whipsaws
    without look-ahead -- purely a backward-looking run-length count.

    `severe_bad` (if given) bypasses the persistence requirement entirely: a day
    that is both 'bad' and 'severe' stays confirmed-bad even on day 1 of the
    streak. This exists to keep the persistence filter (tuned for reducing
    live-market whipsaws) from also slowing the response to acute, fast-moving
    crashes like covid_2020.
    """
    if min_streak <= 1:
        return trend
    is_bad = trend.eq("bad")
    streak = is_bad.astype(int).groupby((~is_bad).cumsum()).cumsum()
    confirmed_bad = is_bad & (streak >= min_streak)
    if severe_bad is not None:
        confirmed_bad = confirmed_bad | (is_bad & severe_bad.reindex(trend.index).fillna(False))
    result = trend.copy()
    result[is_bad & ~confirmed_bad] = "neutral"
    return result


def _vol_high_series(prices: pd.DataFrame, chip_features: pd.DataFrame) -> pd.Series:
    features = _garch_features(prices, chip_features)
    high_vol = (features["garch_proxy_vol_ratio"] >= RATIO_THRESHOLD) | (
        features["garch_proxy_vol_percentile"] >= PERCENTILE_THRESHOLD
    )
    if REQUIRE_NEGATIVE_5D:
        high_vol = high_vol & (features["return_0050_5d"] < 0.0)
    return high_vol


def _chip_bad_series(
    chip_features: pd.DataFrame, *, window: int = 252, percentile: float = 0.10
) -> pd.Series:
    """Flag extreme 0050 foreign net-selling: 5d foreign flow in the bottom
    `percentile` of its own trailing `window`-day rolling distribution.

    Uses a rolling percentile (not a fixed absolute threshold) so it adapts to
    whatever period has real institutional-flow coverage, mirroring how
    vol_high itself is a rolling-percentile flag rather than an absolute
    level. ~38% of foreign_0050_5d is exactly 0.0 (data gaps / no-flow days),
    so the explicit `< 0.0` guard prevents those from ever qualifying as
    "bad" purely from rank position in a stretch of zeros.
    """
    foreign_flow = chip_features["foreign_0050_5d"]
    pct_rank = foreign_flow.rolling(window, min_periods=60).rank(pct=True)
    return (pct_rank <= percentile) & (foreign_flow < 0.0)


def _load_tsmc_foreign_flow_5d(cache_path: Path = TSMC_CHIP_CACHE) -> pd.Series:
    """Daily 5-session rolling foreign net buy/sell for 2330.TW (TSMC).

    Mirrors scripts/report/build_ncf_2330_checklist.py's `_chip_layer` exactly
    (Foreign_Investor + Foreign_Dealer_Self, tail(5).sum()) so this reuses the
    same definition already computed daily for the diagnostic-only
    ncf_2330_checklist report, just applied across the full cached history
    (2012-05-02 onward) instead of a single as-of snapshot. There is no
    2330.TW row in the `institutional_data` DB table (that table only covers
    the ETF universe) -- this FinMind cache CSV is the only source with
    multi-year TSMC institutional-flow history.
    """
    inst = pd.read_csv(cache_path, parse_dates=["date"])
    inst["net"] = pd.to_numeric(inst["buy"], errors="coerce") - pd.to_numeric(inst["sell"], errors="coerce")
    piv = inst.pivot_table(index="date", columns="name", values="net", aggfunc="sum").sort_index()
    foreign = piv.get("Foreign_Investor", pd.Series(0.0, index=piv.index)) + piv.get(
        "Foreign_Dealer_Self", pd.Series(0.0, index=piv.index)
    )
    return foreign.rolling(5, min_periods=5).sum()


def _tsmc_chip_bad_series(
    foreign_flow_5d: pd.Series, *, window: int = 252, percentile: float = 0.10
) -> pd.Series:
    """Flag extreme TSMC foreign net-selling, same rolling-percentile design as
    `_chip_bad_series` but keyed on 2330.TW's own institutional flow instead
    of 0050's. Motivation: 00631L's underlying (0050) is ~55-58% TSMC by
    weight, so TSMC-specific foreign selling pressure is a more targeted
    proxy for the position that actually dominates 00631L's risk than the
    blended 0050-level flow tested in direction 1.
    """
    pct_rank = foreign_flow_5d.rolling(window, min_periods=60).rank(pct=True)
    return (pct_rank <= percentile) & (foreign_flow_5d < 0.0)


def _weights_capped(golden_weights: dict[str, float], cap: float) -> dict[str, float]:
    weights = dict(golden_weights)
    original = float(weights.get("00631L.TW", 0.0) or 0.0)
    new_631l = min(original, cap)
    shift = original - new_631l
    weights["00631L.TW"] = new_631l
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0) or 0.0) + shift
    return _normalize(weights)


def _simulate_a22_curve(
    prices: pd.DataFrame,
    execution_regime: pd.Series,
    trend: pd.Series,
    vol_high: pd.Series,
    golden_weights: dict[str, float],
    weights_by_regime: dict[str, dict[str, float]],
    neutral_cap: float,
    bad_cap: float,
    bad_no_vol_cap: float | None,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict]:
    shares = {t: 0.0 for t in TICKERS}
    cash = float(initial_value)
    applied_key: str | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    tier_days = {
        "good": 0, "neutral_capped": 0, "neutral_uncapped": 0,
        "bad_capped": 0, "bad_uncapped": 0, "bad_uncapped_lightcapped": 0,
    }

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[t] * float(price_row[t]) for t in TICKERS)
        regime = str(execution_regime.loc[dt])
        if regime == "golden1":
            trend_state = str(trend.loc[dt]) if dt in trend.index else "neutral"
            is_high_vol = bool(vol_high.loc[dt]) if dt in vol_high.index and pd.notna(vol_high.loc[dt]) else False
            cap = None
            if trend_state == "good":
                tier_days["good"] += 1
            elif trend_state == "bad":
                if is_high_vol:
                    cap = bad_cap
                    tier_days["bad_capped"] += 1
                elif bad_no_vol_cap is not None:
                    cap = bad_no_vol_cap
                    tier_days["bad_uncapped_lightcapped"] += 1
                else:
                    tier_days["bad_uncapped"] += 1
            else:
                if is_high_vol:
                    cap = neutral_cap
                    tier_days["neutral_capped"] += 1
                else:
                    tier_days["neutral_uncapped"] += 1

            if cap is None:
                key = "golden1"
                target_weights = golden_weights
            else:
                key = f"golden1_a22_cap_{cap:.4f}"
                target_weights = _weights_capped(golden_weights, cap)
        else:
            key = regime
            target_weights = weights_by_regime.get(regime, golden_weights)

        if key != applied_key:
            weights = _normalize(target_weights)
            current_values = {t: shares[t] * float(price_row[t]) for t in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _ in range(3):
                target_values = {t: net_value * weights.get(t, 0.0) for t in TICKERS}
                cost, turnover = _trade_cost(
                    current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {t: net_value * weights.get(t, 0.0) / max(float(price_row[t]), 1e-12) for t in TICKERS}
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            applied_key = key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "tier_days": tier_days,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260707.csv")
    parser.add_argument("--feature-start", default="2016-01-04")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--good-ma-gap-min", type=float, default=0.02)
    parser.add_argument("--good-drawdown-min", type=float, default=-0.05)
    parser.add_argument("--bad-ma-gap-max", type=float, default=-0.02)
    parser.add_argument("--bad-drawdown-max", type=float, default=-0.08)
    parser.add_argument("--neutral-cap", type=float, default=0.10)
    parser.add_argument("--bad-cap", type=float, default=0.0)
    parser.add_argument(
        "--bad-no-vol-cap", type=float, default=None,
        help="Cap applied when trend=bad but vol is NOT confirmed high (default: None, i.e. leave golden1 weights unchanged, matching the original rule as first specified).",
    )
    parser.add_argument(
        "--bad-persistence-days", type=int, default=1,
        help="Require trend=bad to hold this many consecutive days before treating it as confirmed bad (default: 1, i.e. no filtering).",
    )
    parser.add_argument(
        "--bad-severe-ma-gap-max", type=float, default=None,
        help="If set, a day with ma_gap <= this value bypasses --bad-persistence-days entirely (immediate confirmed-bad, for acute crashes).",
    )
    parser.add_argument(
        "--bad-severe-drawdown-max", type=float, default=None,
        help="If set, a day with drawdown <= this value bypasses --bad-persistence-days entirely (immediate confirmed-bad, for acute crashes).",
    )
    parser.add_argument(
        "--bad-vol-confirms-immediately", action="store_true",
        help="If set, a day with trend=bad AND vol_high bypasses --bad-persistence-days entirely (independent vol confirmation skips the wait; persistence only applies when vol is NOT confirmed high).",
    )
    parser.add_argument(
        "--chip-bad-confirms-immediately", action="store_true",
        help="If set, a day with trend=bad AND extreme 0050 foreign net-selling (bottom "
        "--chip-bad-percentile of its own trailing --chip-bad-window rolling distribution) "
        "bypasses --bad-persistence-days entirely, mirroring --bad-vol-confirms-immediately "
        "but keyed on institutional flow instead of the GARCH-proxy vol flag.",
    )
    parser.add_argument("--chip-bad-window", type=int, default=252)
    parser.add_argument("--chip-bad-percentile", type=float, default=0.10)
    parser.add_argument(
        "--tsmc-chip-bad-confirms-immediately", action="store_true",
        help="Same as --chip-bad-confirms-immediately but keyed on 2330.TW (TSMC) foreign "
        "net-selling instead of 0050-level flow (see _load_tsmc_foreign_flow_5d).",
    )
    parser.add_argument("--tsmc-chip-bad-window", type=int, default=252)
    parser.add_argument("--tsmc-chip-bad-percentile", type=float, default=0.10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    overall_end = _resolve_end_date(db_path, "latest")

    prices_0050 = _load_prices(db_path, ["0050.TW"], args.feature_start, overall_end)
    chip_features_all = _load_chip_features(db_path, prices_0050.index, args.feature_start, overall_end)
    vol_high_series = _vol_high_series(prices_0050, chip_features_all)
    chip_bad_series = _chip_bad_series(
        chip_features_all, window=args.chip_bad_window, percentile=args.chip_bad_percentile
    )
    tsmc_foreign_flow_5d = _load_tsmc_foreign_flow_5d()
    tsmc_chip_bad_series = _tsmc_chip_bad_series(
        tsmc_foreign_flow_5d, window=args.tsmc_chip_bad_window, percentile=args.tsmc_chip_bad_percentile
    )

    results = []
    for win_label, start, end in DEFAULT_WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        report, frame = run_a2118(
            start=start, end=end_resolved, initial_value=args.initial_value, db=db_path,
            commission_rate=args.commission_rate, slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax, ncf_panel_631l_path=args.ncf_panel_631l,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
            risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
            momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
            momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        )
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        golden_weights = dict(report["base_weights"]["golden1"])
        weights_by_regime = dict(report["base_weights"])
        baseline_metrics = dict(report["metrics"])
        baseline_execution = dict(report["execution"])

        trend = _classify_trend(
            frame["ma_gap"], frame["drawdown"],
            good_ma_gap_min=args.good_ma_gap_min, good_drawdown_min=args.good_drawdown_min,
            bad_ma_gap_max=args.bad_ma_gap_max, bad_drawdown_max=args.bad_drawdown_max,
        )
        win_vol_high = vol_high_series.reindex(frame.index).fillna(False)
        win_chip_bad = chip_bad_series.reindex(frame.index).fillna(False)
        win_tsmc_chip_bad = tsmc_chip_bad_series.reindex(frame.index).fillna(False)
        severe_bad = None
        if args.bad_severe_ma_gap_max is not None or args.bad_severe_drawdown_max is not None:
            ma_gap_max = args.bad_severe_ma_gap_max if args.bad_severe_ma_gap_max is not None else float("-inf")
            drawdown_max = args.bad_severe_drawdown_max if args.bad_severe_drawdown_max is not None else float("-inf")
            severe_bad = (frame["ma_gap"] <= ma_gap_max) | (frame["drawdown"] <= drawdown_max)
        if args.bad_vol_confirms_immediately:
            severe_bad = win_vol_high if severe_bad is None else (severe_bad | win_vol_high)
        if args.chip_bad_confirms_immediately:
            severe_bad = win_chip_bad if severe_bad is None else (severe_bad | win_chip_bad)
        if args.tsmc_chip_bad_confirms_immediately:
            severe_bad = win_tsmc_chip_bad if severe_bad is None else (severe_bad | win_tsmc_chip_bad)
        trend = _require_bad_persistence(trend, args.bad_persistence_days, severe_bad=severe_bad)

        curve, sim = _simulate_a22_curve(
            total_return_prices, execution_regime, trend, win_vol_high, golden_weights, weights_by_regime,
            args.neutral_cap, args.bad_cap, args.bad_no_vol_cap, args.initial_value,
            args.commission_rate, args.slippage_rate, args.equity_etf_sell_tax,
        )
        metrics = _metrics(curve, args.initial_value)

        result = {
            "label": win_label,
            "window": {"start": start, "end": end_resolved},
            "tier_days": sim["tier_days"],
            "chip_bad_days": int(win_chip_bad.reindex(frame.index).fillna(False).sum()),
            "tsmc_chip_bad_days": int(win_tsmc_chip_bad.reindex(frame.index).fillna(False).sum()),
            "delta_vs_baseline": {
                "final_value": metrics["final_value"] - baseline_metrics["final_value"],
                "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
            },
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        }
        results.append(result)
        d = result["delta_vs_baseline"]
        print(
            f"{start}..{end_resolved}: tier_days={sim['tier_days']} chip_bad_days={result['chip_bad_days']} "
            f"tsmc_chip_bad_days={result['tsmc_chip_bad_days']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f} delta_mdd={d['max_drawdown']:.4f}"
        )

    payload = {
        "experiment": "group_a_plus_a22_bad_vol_overlay",
        "policy": "research_only_no_lookahead",
        "trend_thresholds": {
            "good_ma_gap_min": args.good_ma_gap_min,
            "good_drawdown_min": args.good_drawdown_min,
            "bad_ma_gap_max": args.bad_ma_gap_max,
            "bad_drawdown_max": args.bad_drawdown_max,
            "bad_persistence_days": args.bad_persistence_days,
            "bad_severe_ma_gap_max": args.bad_severe_ma_gap_max,
            "bad_severe_drawdown_max": args.bad_severe_drawdown_max,
        },
        "vol_high_definition": {
            "source": "group_a_plus.integrations.garch_regime_shadow (frozen production thresholds)",
            "ratio_threshold": RATIO_THRESHOLD,
            "percentile_threshold": PERCENTILE_THRESHOLD,
            "require_negative_5d": REQUIRE_NEGATIVE_5D,
        },
        "chip_bad_definition": {
            "source": "foreign_0050_5d (backtest_group_a_plus_switch_policy._load_chip_features)",
            "window": args.chip_bad_window,
            "percentile": args.chip_bad_percentile,
            "confirms_immediately": args.chip_bad_confirms_immediately,
        },
        "caps": {
            "neutral_cap": args.neutral_cap,
            "bad_cap": args.bad_cap,
            "bad_no_vol_cap": args.bad_no_vol_cap,
        },
        "golden1_baseline_00631l_weight": golden_weights.get("00631L.TW"),
        "windows": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
