#!/usr/bin/env python3
"""Research-only backtest: does an N-day persistence filter on market_state's
`crash_risk` classification produce a meaningfully different, more defensible
set of trigger days than the raw (N=1) classification?

Read-only against production code -- does not modify market_state.py,
daily_signal.py, a2118.py, or group_a_plus_config.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.operations.market_state import classify_market_state  # noqa: E402

FRAME_PATH = PROJECT_ROOT / "results" / "group_a_plus_runner_latest_20250102_20260702_frame.csv"
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
FORWARD_DAYS = 20


def load_frame() -> pd.DataFrame:
    df = pd.read_csv(FRAME_PATH, index_col=0, parse_dates=True)
    df.index.name = "dt"
    return df


def classify_all(df: pd.DataFrame) -> pd.Series:
    states = []
    for _, row in df.iterrows():
        features = {
            "ma_gap": row["ma_gap"],
            "drawdown": row["drawdown"],
            "exit_momentum_5d": row["exit_momentum"],
            "total_risk_score": row["total_risk_score"],
            "tail_risk_score": row["tail_risk_score"],
        }
        result = classify_market_state(row["execution_regime"], features)
        states.append(result["state"])
    return pd.Series(states, index=df.index, name="market_state")


def persistence_triggers(is_crash: pd.Series, n: int) -> list[pd.Timestamp]:
    """First day a run of `n` consecutive crash_risk days completes."""
    triggers = []
    run = 0
    for dt, flag in is_crash.items():
        run = run + 1 if flag else 0
        if run == n:
            triggers.append(dt)
    return triggers


def load_00632r(dates: pd.DatetimeIndex) -> pd.Series:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker='00632R.TW' ORDER BY dt"
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    s = rows.set_index("dt")["close"]
    return s.reindex(s.index.union(dates)).sort_index()


def forward_return(series: pd.Series, trigger_date: pd.Timestamp, days: int) -> float | None:
    idx = series.index
    if trigger_date not in idx:
        return None
    pos = idx.get_loc(trigger_date)
    if pos + days >= len(idx):
        return None
    start = series.iloc[pos]
    end = series.iloc[pos + days]
    if start == 0 or pd.isna(start) or pd.isna(end):
        return None
    return float(end / start - 1.0)


def evaluate_triggers(
    label: str,
    trigger_dates: list[pd.Timestamp],
    portfolio_value: pd.Series,
    r632r: pd.Series,
    execution_regime: pd.Series,
) -> dict:
    rows = []
    for dt in trigger_dates:
        actual_fwd = forward_return(portfolio_value, dt, FORWARD_DAYS)
        r632r_fwd = forward_return(r632r, dt, FORWARD_DAYS)
        rows.append(
            {
                "date": str(dt.date()),
                "execution_regime_that_day": str(execution_regime.get(dt)),
                "actual_path_fwd20": actual_fwd,
                "cash_fwd20": 0.0,
                "inv00632r_fwd20": r632r_fwd,
                "actual_beats_cash": (actual_fwd is not None and actual_fwd > 0.0),
                "actual_beats_00632r": (
                    actual_fwd is not None and r632r_fwd is not None and actual_fwd > r632r_fwd
                ),
            }
        )
    usable = [r for r in rows if r["actual_path_fwd20"] is not None]
    n_usable = len(usable)
    summary = {
        "label": label,
        "n_triggers": len(trigger_dates),
        "n_usable_for_fwd20": n_usable,
        "trigger_rows": rows,
    }
    if n_usable:
        summary["mean_actual_fwd20"] = sum(r["actual_path_fwd20"] for r in usable) / n_usable
        summary["mean_00632r_fwd20"] = (
            sum(r["inv00632r_fwd20"] for r in usable if r["inv00632r_fwd20"] is not None)
            / max(1, sum(1 for r in usable if r["inv00632r_fwd20"] is not None))
        )
        summary["pct_actual_beats_cash"] = sum(r["actual_beats_cash"] for r in usable) / n_usable
        summary["pct_actual_beats_00632r"] = sum(
            1 for r in usable if r["actual_beats_00632r"]
        ) / n_usable
    return summary


def main() -> None:
    df = load_frame()
    states = classify_all(df)
    is_crash = states == "crash_risk"

    n_crash_total = int(is_crash.sum())
    golden1_and_crash = df.index[is_crash & (df["execution_regime"] == "golden1")]
    n_golden1_and_crash = len(golden1_and_crash)

    r632r = load_00632r(df.index)
    portfolio_value = df["portfolio_value"]
    execution_regime = df["execution_regime"]

    results = {
        "generated_at": "2026-07-04",
        "audit_replay_check": {
            "n_crash_risk_total_replayed": n_crash_total,
            "n_crash_risk_during_golden1_replayed": n_golden1_and_crash,
            "audit_claimed_total": 23,
            "audit_claimed_during_golden1": 9,
            "matches_audit": (n_crash_total == 23 and n_golden1_and_crash == 9),
        },
        "n1_raw_during_golden1": evaluate_triggers(
            "N=1 raw, crash_risk AND execution_regime==golden1",
            list(golden1_and_crash),
            portfolio_value,
            r632r,
            execution_regime,
        ),
    }

    for n in (2, 3, 5):
        triggers = persistence_triggers(is_crash, n)
        results[f"n{n}_persistence_all_regimes"] = evaluate_triggers(
            f"N={n} persistence, all regimes",
            triggers,
            portfolio_value,
            r632r,
            execution_regime,
        )
        triggers_golden1 = [
            dt for dt in triggers if execution_regime.get(dt) == "golden1"
        ]
        results[f"n{n}_persistence_during_golden1"] = evaluate_triggers(
            f"N={n} persistence, execution_regime==golden1 subset",
            triggers_golden1,
            portfolio_value,
            r632r,
            execution_regime,
        )

    out_path = PROJECT_ROOT / "results" / "market_state_persistence_backtest_20260704.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"n_crash_risk_total_replayed={n_crash_total} (audit said 23)")
    print(f"n_crash_risk_during_golden1_replayed={n_golden1_and_crash} (audit said 9)")
    for key in ("n1_raw_during_golden1", "n2_persistence_all_regimes", "n2_persistence_during_golden1",
                "n3_persistence_all_regimes", "n3_persistence_during_golden1",
                "n5_persistence_all_regimes", "n5_persistence_during_golden1"):
        s = results[key]
        print(
            f"{key}: n_triggers={s['n_triggers']} n_usable={s['n_usable_for_fwd20']} "
            f"mean_actual_fwd20={s.get('mean_actual_fwd20')} "
            f"mean_00632r_fwd20={s.get('mean_00632r_fwd20')} "
            f"pct_actual_beats_cash={s.get('pct_actual_beats_cash')} "
            f"pct_actual_beats_00632r={s.get('pct_actual_beats_00632r')}"
        )
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
