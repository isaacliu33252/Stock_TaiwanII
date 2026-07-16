#!/usr/bin/env python3
"""Does serial correlation of 00631L returns predict future drawdown breach?

Research-only. Goldberg & Mahmoud, "Drawdown: From Practice to Theory and
Back Again", formalizes Conditional Expected Drawdown (CED) -- the average
severity of drawdowns that breach a threshold -- and specifically notes CED
is sensitive to serial correlation in returns in a way plain volatility is
not: a sequence of losses that trend together compounds into a deeper
drawdown than the same total variance spread across uncorrelated up/down
days. None of the existing 00631L downside-risk features (see
evaluate_group_a_plus_00631l_downside_race_classifier.py's feature set:
ma_gap/drawdown/multi-period returns/realized_vol_ratio/downside_semivar/
up-day fraction, later + chip features + HAR-RV h10) explicitly measure
serial correlation -- this is the genuinely new angle from the CED paper,
tested standalone before considering whether to feed it into that (already
paused, per 2026-07-10 conclusions) classifier line.

Two candidate features, both purely backward-looking (no look-ahead):
  1. `autocorr_20d`: rolling 20-day lag-1 autocorrelation of daily returns.
  2. `down_streak`: current run length of consecutive negative-return days.

Both regressed (linear probability model, i.e. plain OLS on a 0/1 label --
valid for a significance test even though the label is binary) against the
same two CED-style labels tested in
evaluate_group_a_plus_00631l_ced_drawdown_oracle.py (10d MDD < -5%, 20d MDD
< -8%), using the same Newey-West/Bartlett-HAC t-statistic used throughout
this session's other return/label-timing tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import _hac_ols_slope_tstat, _load_close
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_oracle_ceiling import _label_max_drawdown

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_serial_correlation_drawdown_predictability_latest.json"

CED_LABELS = [
    ("A_10d_mdd_lt_5pct", 10, -0.05),
    ("B_20d_mdd_lt_8pct", 20, -0.08),
]
AUTOCORR_WINDOW = 20


def _autocorr_20d(returns: pd.Series, window: int = AUTOCORR_WINDOW) -> pd.Series:
    def _lag1_autocorr(x: np.ndarray) -> float:
        if len(x) < 3:
            return np.nan
        return float(np.corrcoef(x[:-1], x[1:])[0, 1])

    return returns.rolling(window, min_periods=window).apply(_lag1_autocorr, raw=True)


def _down_streak(returns: pd.Series) -> pd.Series:
    is_down = returns < 0.0
    return is_down.astype(int).groupby((~is_down).cumsum()).cumsum()


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker)
    close = close.loc[start:end]
    returns = close.pct_change().fillna(0.0)

    autocorr = _autocorr_20d(returns)
    down_streak = _down_streak(returns).astype(float)

    results: dict[str, dict] = {}
    for label_name, horizon, threshold in CED_LABELS:
        label = (_label_max_drawdown(close, horizon) < threshold).astype(float)
        lag = max(horizon - 1, 1)

        lagged_autocorr = autocorr.shift(1)
        lagged_streak = down_streak.shift(1)

        valid = label.notna() & lagged_autocorr.notna() & lagged_streak.notna()
        n = int(valid.sum())
        if n < 60:
            results[label_name] = {"status": "insufficient_data", "n": n}
            continue

        y = label[valid].to_numpy(dtype=float)
        x_autocorr = lagged_autocorr[valid].to_numpy(dtype=float)
        x_streak = lagged_streak[valid].to_numpy(dtype=float)

        autocorr_fit = _hac_ols_slope_tstat(x_autocorr, y, lag=lag)
        streak_fit = _hac_ols_slope_tstat(x_streak, y, lag=lag)
        results[label_name] = {
            "n": n,
            "base_rate": float(y.mean()),
            "autocorr_20d": autocorr_fit,
            "down_streak": streak_fit,
        }
    return {"ticker": ticker, "window": {"start": start, "end": end}, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end)
    for label_name, res in payload["results"].items():
        if res.get("status") == "insufficient_data":
            print(f"{label_name}: insufficient data (n={res['n']})")
            continue
        a = res["autocorr_20d"]
        s = res["down_streak"]
        print(
            f"{label_name}: n={res['n']} base_rate={res['base_rate']:.3f} | "
            f"autocorr_20d slope={a['slope']:+.4f} t={a['t_stat']:+.2f} p={a['p_value']:.3f} | "
            f"down_streak slope={s['slope']:+.4f} t={s['t_stat']:+.2f} p={s['p_value']:.3f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
