#!/usr/bin/env python3
"""arXiv:2501.16659 (Chen, Li, Saunders 2025, "Exploratory Mean-Variance
Portfolio Optimization with Regime-Switching Market Dynamics") applicability
test for GroupA+ -- fair, causal implementation on Taiwan data.

Desk analysis (before writing this script) flagged two specific,
identifiable methodological problems with the paper's own real-market study
that make its reported Sharpe ratios (up to 5.93) not credible as evidence
of a real edge:

1. Pseudo-replication: the paper's "24 independent 10-year rolling windows"
   (2006-2017) step by only 1 month, so adjacent windows share ~119/120
   months of data -- the true independent sample count is closer to 2-3,
   not 24. Matches a trap this codebase's own research has hit before (see
   project_2301_03186_quadratic_bound_regime_crosscheck_20260810's
   controlled-test correction, and the h20_calibration_drift_gate_deadlock
   memory's overlapping-window significance inflation).
2. Hindsight regime labeling: the paper applies the Viterbi algorithm
   (a smoothing algorithm using the WHOLE window's data) to label
   bullish/bearish regimes WITHIN each 10-year training window, then
   calibrates the model on those labels -- the regime classification used
   for calibration had access to information a live investor would not
   have had in real time.

Per feedback_verify_every_paper_independently, this is tested directly
rather than closed on desk analysis alone. This script implements the
paper's own core investment MECHANISM (regime-dependent Sharpe/variance-
scaled leveraged allocation, i.e. the classical Zhou & Yin (2003) MVRS
optimal control from the paper's Theorem 2.1/Eq 2.10, u*(t,x,i) =
-rho(t,i)/sigma(t,i) * (x + (lambda-z)H(t,i)), which reduces to the
classical Merton myopic allocation u* ~= (mu_i - r)/sigma_i^2 * x when the
target-wealth term is not dominant -- used here as a robust, transparent
simplification rather than risking a transcription error reproducing the
paper's full backward-ODE boundary-value system from a PDF-extracted,
partially garbled formula) -- but FIXES both identified flaws:

- Regime detection is fully CAUSAL: a rolling trend-following classifier
  (0050 price vs its own trailing 100-day MA, matching this codebase's own
  a2111/a2118 regime convention) using only data available up to and
  including day t, no full-window smoothing.
- Regime parameters (mu_i, sigma_i per regime) are estimated from an
  EXPANDING window of only past data, re-estimated monthly (matching the
  paper's own monthly-rebalancing convention), never using future data.
- Evaluation uses ONE continuous backtest over Taiwan's full available
  0050 history (2009-2026, ~17 years) plus the same 4 standard windows used
  throughout this session's LETF work, rather than artificially chopping a
  short history into fake "independent" overlapping windows.

Compared against: (a) 100% 0050 buy-and-hold, (b) a non-regime-switching
EMV baseline (same Merton-style formula, but mu/sigma estimated from the
full expanding window without any regime split -- the paper's own EMVRS-
vs-EMV comparison structure, just both made causal and non-overlapping).

Implemented as a continuous leveraged position on 0050 (synthetic margin-
style leverage, no daily-reset compounding drag) rather than via 00631L,
to avoid conflating this paper's regime-allocation-intelligence question
with the already-extensively-tested LETF daily-reset drag question
(letf_quadratic_bound.py and related closed research).

Research-only. Never touches production strategy files.
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

from backtest_group_a_plus_switch_policy import _metrics  # noqa: E402

RISK_FREE_ANNUAL = 0.012  # TWD short-rate proxy, simplification matching the paper's own use of a proxy risk-free series
ACTION_CONSTRAINT = 3.0  # matches the paper's own leverage cap
MA_WINDOW = 100  # matches a2111/a2118's own regime convention
MIN_ESTIMATION_DAYS = 252  # need at least ~1 year of causal history before estimating regime parameters
REBALANCE_FREQ_DAYS = 21  # ~monthly, matching the paper's own rebalancing convention
COMMISSION_RATE = 0.001425
SLIPPAGE_RATE = 0.0005

WINDOWS = (
    ("full_history_2009_2026", "2009-01-01", "latest"),
    ("full_2020_2026", "2020-01-02", "latest"),
    ("rate_hike_2022_2023", "2022-01-03", "2023-12-29"),
    ("live_2024_2026", "2024-01-02", "latest"),
    ("active_2025_2026", "2025-01-02", "latest"),
)


def _load_0050(db_path: Path) -> pd.Series:
    """2026-08-23: found (while debugging this script's regime-parameter
    estimates being backwards) a NEW, previously-uncaught unadjusted
    corporate-action breakpoint in the raw ohlcv table: 0050.TW's close
    drops from $58.70 (2013-12-31) to $14.64 (2014-01-02), a ~4:1 ratio --
    an unadjusted 2014-01-02 stock split, not a real -139% one-day return.
    Same class of bug as the 3 already-fixed breakpoints found in the
    2608.00127 review (2026-08-16), not caught by that fix. In-memory-only
    correction here (does not touch the shared production DB) so this
    script's own return-based estimation isn't corrupted; the underlying DB
    bug should be flagged separately for a proper fix, matching the earlier
    precedent."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = '0050.TW' ORDER BY dt").fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    close = rows.set_index("dt")["close"].astype(float)
    split_date = pd.Timestamp("2014-01-02")
    close.loc[close.index < split_date] = close.loc[close.index < split_date] / 4.0
    return close


def _resolve_end(db_path: Path, requested_end: str) -> str:
    if requested_end.lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = '0050.TW'").fetchone()[0]
    finally:
        con.close()
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _causal_regime_and_params(close: pd.Series) -> pd.DataFrame:
    """For every day, using only data up to and including that day: classify
    the regime (price vs trailing MA100, fully causal) and, on rebalance
    days only, estimate (mu, sigma) annualized for whichever regime is
    active from ALL prior days ever observed in that regime (expanding
    window, no future data)."""
    logret = np.log(close).diff()
    ma = close.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean()
    regime = (close > ma).astype(int)  # 1 = bull, 0 = bear; NaN-safe since ma is NaN before MA_WINDOW

    records = []
    bull_returns: list[float] = []
    bear_returns: list[float] = []
    last_estimate = {"bull": None, "bear": None}
    dates = close.index
    for i, dt in enumerate(dates):
        if i > 0 and not pd.isna(logret.iloc[i]):
            r = float(logret.iloc[i])
            prev_regime = regime.iloc[i - 1] if not pd.isna(ma.iloc[i - 1]) else None
            if prev_regime == 1:
                bull_returns.append(r)
            elif prev_regime == 0:
                bear_returns.append(r)

        is_rebalance_day = i % REBALANCE_FREQ_DAYS == 0
        if is_rebalance_day and i >= MIN_ESTIMATION_DAYS:
            if len(bull_returns) >= 60:
                last_estimate["bull"] = (float(np.mean(bull_returns) * 252), float(np.std(bull_returns) * np.sqrt(252)))
            if len(bear_returns) >= 60:
                last_estimate["bear"] = (float(np.mean(bear_returns) * 252), float(np.std(bear_returns) * np.sqrt(252)))

        current_regime = "bull" if (not pd.isna(ma.iloc[i]) and regime.iloc[i] == 1) else "bear"
        mu_sigma = last_estimate.get(current_regime)
        pooled_mu_sigma = None
        all_returns = bull_returns + bear_returns
        if len(all_returns) >= 60:
            pooled_mu_sigma = (float(np.mean(all_returns) * 252), float(np.std(all_returns) * np.sqrt(252)))

        records.append(
            {
                "date": dt,
                "regime": current_regime if i >= MA_WINDOW else None,
                "mu": mu_sigma[0] if mu_sigma else None,
                "sigma": mu_sigma[1] if mu_sigma else None,
                "pooled_mu": pooled_mu_sigma[0] if pooled_mu_sigma else None,
                "pooled_sigma": pooled_mu_sigma[1] if pooled_mu_sigma else None,
            }
        )
    return pd.DataFrame(records).set_index("date")


def _simulate(close: pd.Series, params: pd.DataFrame, *, use_regime: bool, initial_value: float) -> pd.Series:
    """2026-08-23 fix: an initial version rebalanced only every 21 days at up
    to 3x leverage, with no interim risk control -- a single violent day
    (e.g. COVID 2020-03) produced a -30% one-day portfolio move because the
    stale leveraged position rode uncorrected for up to 3 weeks. Real margin
    accounts get intraday margin calls (2103.10157's own paper explicitly
    models this via a 10% deviation buffer); this codebase's own deviation-
    band convention elsewhere this session uses 20%. Added a daily
    deviation-band check (also rebalances if current leverage drifts >20%
    from target, not just on the monthly schedule) so a fair comparison
    doesn't let leverage ride uncontrolled through a crash purely due to an
    unrealistic missing risk-management step."""
    r = RISK_FREE_ANNUAL
    cash = initial_value
    shares = 0.0  # can be negative (short) or > cash/price (leveraged, synthetic margin)
    values = []
    current_leverage_frac = None
    for i, (dt, price) in enumerate(close.items()):
        row = params.loc[dt]
        mu = row["mu"] if use_regime else row["pooled_mu"]
        sigma = row["sigma"] if use_regime else row["pooled_sigma"]
        portfolio_value = cash + shares * price

        if mu is None or sigma is None or sigma <= 0:
            target_frac = 1.0 if current_leverage_frac is None else current_leverage_frac
        else:
            target_frac = float(np.clip((mu - r) / (sigma**2), -ACTION_CONSTRAINT, ACTION_CONSTRAINT))

        is_rebalance_day = i % REBALANCE_FREQ_DAYS == 0
        actual_leverage = (shares * price / portfolio_value) if portfolio_value > 0 else current_leverage_frac
        deviation_triggered = (
            current_leverage_frac is not None
            and portfolio_value > 0
            and abs(actual_leverage - current_leverage_frac) > 0.20 * max(abs(current_leverage_frac), 1.0)
        )
        if is_rebalance_day or current_leverage_frac is None or deviation_triggered:
            target_stock_value = portfolio_value * target_frac
            trade_value = abs(target_stock_value - shares * price)
            cost = trade_value * (COMMISSION_RATE + SLIPPAGE_RATE)
            portfolio_value -= cost
            target_stock_value = portfolio_value * target_frac
            shares = target_stock_value / price
            cash = portfolio_value - target_stock_value
            current_leverage_frac = target_frac

        # accrue risk-free rate on cash (or margin cost on negative cash) daily
        if i > 0:
            days = (dt - close.index[i - 1]).days
            cash *= (1 + r) ** (days / 365.0)

        values.append(cash + shares * price)

    return pd.Series(values, index=close.index, dtype=float)


def run_window(*, db_path: Path, close_full: pd.Series, params_full: pd.DataFrame, label: str, start: str, end: str, initial_value: float) -> dict[str, Any]:
    end_resolved = _resolve_end(db_path, end)
    close = close_full.loc[start:end_resolved]
    params = params_full.loc[close.index]

    bh_shares = initial_value * (1 - COMMISSION_RATE - SLIPPAGE_RATE) / float(close.iloc[0])
    bh_curve = close * bh_shares

    regime_curve = _simulate(close, params, use_regime=True, initial_value=initial_value)
    emv_curve = _simulate(close, params, use_regime=False, initial_value=initial_value)

    return {
        "window": label,
        "start": start,
        "end": end_resolved,
        "rows": int(len(close)),
        "benchmark_0050_buy_hold": _metrics(bh_curve, initial_value),
        "emvrs_causal_regime_switching": _metrics(regime_curve, initial_value),
        "emv_no_regime_switching": _metrics(emv_curve, initial_value),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "emvrs_regime_switching_allocation_2501_16659.json"))
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
    close_full = _load_0050(db_path)
    print(f"Loaded 0050.TW: {close_full.index.min().date()} ~ {close_full.index.max().date()} ({len(close_full)} rows)")
    print("Computing causal regime detection + expanding-window parameter estimation...")
    params_full = _causal_regime_and_params(close_full)

    window_reports = []
    for label, start, end in WINDOWS:
        wr = run_window(
            db_path=db_path, close_full=close_full, params_full=params_full,
            label=label, start=start, end=end, initial_value=float(args.initial_value),
        )
        window_reports.append(wr)
        b = wr["benchmark_0050_buy_hold"]
        rs = wr["emvrs_causal_regime_switching"]
        emv = wr["emv_no_regime_switching"]
        print(f"\n=== {wr['window']} ({wr['start']} ~ {wr['end']}, {wr['rows']} rows) ===")
        print(f"  0050 buy&hold:              final={b['final_value']:,.0f} sharpe={b['sharpe_ratio']:.3f} mdd={b['max_drawdown']:.4f}")
        print(f"  EMVRS (causal regime):      final={rs['final_value']:,.0f} sharpe={rs['sharpe_ratio']:.3f} mdd={rs['max_drawdown']:.4f}")
        print(f"  EMV (no regime, pooled):    final={emv['final_value']:,.0f} sharpe={emv['sharpe_ratio']:.3f} mdd={emv['max_drawdown']:.4f}")

    report = {
        "schema_version": 1,
        "report_type": "emvrs_regime_switching_allocation_test",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_source": "arXiv:2501.16659 (Chen, Li, Saunders 2025) -- causal reimplementation fixing pseudo-replication and hindsight-regime-labeling flaws identified in the paper's own real-data study",
        "policy": "research_only_no_weight_change",
        "risk_free_annual": RISK_FREE_ANNUAL,
        "action_constraint": ACTION_CONSTRAINT,
        "window_reports": window_reports,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
