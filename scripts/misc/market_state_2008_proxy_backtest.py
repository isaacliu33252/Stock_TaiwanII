#!/usr/bin/env python3
"""Read-only research: replay market_state.py + N-day persistence filter on the
2008 TWII proxy. Does not modify market_state.py, daily_signal.py, a2118.py,
group_a_plus_config.json, or any production/report file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from twii_proxy_utils import build_group_a_twii_proxy_data  # noqa: E402
from backtest_group_a_plus_switch_policy import _regime_features  # noqa: E402
from group_a_plus.runners.a2111 import _build_switch_rule  # noqa: E402
from group_a_plus.operations.market_state import classify_market_state  # noqa: E402

START, END = "2007-07-01", "2010-12-31"


def main() -> None:
    stock_data, _market = build_group_a_twii_proxy_data(START, END)
    prices = pd.DataFrame(
        {
            t: pd.Series(
                stock_data[t]["close"].to_numpy(),
                index=pd.to_datetime(stock_data[t]["date"]).dt.normalize(),
            )
            for t in ("0050.TW", "00631L.TW", "00632R.TW")
        }
    ).dropna()
    prices = prices.sort_index()

    rule = _build_switch_rule()
    features = _regime_features(prices, rule, chip_features=None)

    # Data-quality note: chip_features=None -> every chip_*/derivative_* risk
    # flag is hardcoded 0 -> chip_score=derivative_score=total_risk_score=0
    # for the ENTIRE window. tail_risk_score is unaffected (pure price/vol/VaR).
    assert (features["total_risk_score"] == 0).all(), "expected total_risk_score stuck at 0"
    assert (features["chip_score"] == 0).all()
    assert (features["derivative_score"] == 0).all()

    # Rule-as-specified (a2111): enter requires total_risk_ok, which is
    # (total_risk_score >= require_total_risk_score=6) -> always False here.
    # So the *actual* a2111/a2118 switch rule can NEVER enter defensive on
    # this proxy -- regime is golden1 for the whole window. This itself is
    # the headline finding; report it, then also build a price-only regime
    # (drop the chip/derivative/total_risk gates) as a secondary, non-degenerate
    # comparison so the persistence-filter test isn't vacuous.
    real_rule_regime = pd.Series("golden1", index=features.index)  # proven below
    enter_gate_total_risk_ok = (features["total_risk_score"] >= rule.require_total_risk_score)
    never_enters = not bool(enter_gate_total_risk_ok.any())

    # Secondary, idealized regime: same MA100/drawdown thresholds, but drop
    # the chip/derivative/total_risk/tail_risk gating (since those inputs
    # don't exist for 2008). This is NOT what a2111 would actually do on
    # this proxy -- it's a labeled "what if the gate weren't chip-blocked"
    # comparison series, used only to get a non-degenerate execution_regime
    # for the persistence-filter test.
    price_enter = (features["ma_gap"] <= rule.enter_ma_gap) | (features["drawdown"] <= rule.enter_drawdown)
    price_exit = (features["ma_gap"] >= rule.exit_ma_gap) & (features["exit_momentum"] > 0.0)
    idealized = []
    in_def = False
    hold = 0
    for _, row in pd.concat([price_enter.rename("enter"), price_exit.rename("exit_")], axis=1).iterrows():
        if in_def:
            hold += 1
            if hold >= rule.min_hold_days and row["exit_"]:
                in_def = False
                hold = 0
        elif row["enter"]:
            in_def = True
            hold = 1
        idealized.append("group_a_plus_defensive" if in_def else "golden1")
    idealized_regime = pd.Series(idealized, index=features.index)

    # market_state replay under both regime series
    def replay(regime: pd.Series) -> pd.DataFrame:
        rows = []
        for dt, row in features.iterrows():
            feat = {
                "ma_gap": float(row["ma_gap"]),
                "drawdown": float(row["drawdown"]),
                "exit_momentum_5d": float(row["exit_momentum"]),
                "total_risk_score": int(row["total_risk_score"]),
                "tail_risk_score": int(row["tail_risk_score"]),
            }
            ms = classify_market_state(str(regime.loc[dt]), feat)
            rows.append({"date": dt, "execution_regime": regime.loc[dt], "state": ms["state"]})
        return pd.DataFrame(rows).set_index("date")

    replay_real = replay(real_rule_regime)
    replay_ideal = replay(idealized_regime)

    def state_counts(df: pd.DataFrame) -> dict:
        return df["state"].value_counts().to_dict()

    def crash_dates(df: pd.DataFrame) -> list[str]:
        return [str(d.date()) for d in df.index[df["state"] == "crash_risk"]]

    def crash_regime_breakdown(df: pd.DataFrame) -> dict:
        sub = df[df["state"] == "crash_risk"]
        return sub["execution_regime"].value_counts().to_dict()

    # N-day persistence filter on crash_risk, forward-20d return of
    # maintain-current-regime-weights vs cash vs 00632R, using REAL proxy prices.
    def confirmed_trigger_dates(df: pd.DataFrame, n: int) -> list[pd.Timestamp]:
        is_crash = (df["state"] == "crash_risk").astype(int)
        run = is_crash.rolling(n).sum()
        confirmed_days = df.index[run == n]
        # de-dup consecutive confirmations to first-confirmation day only
        out = []
        last = None
        for d in confirmed_days:
            if last is None or (d - last).days > 3 * n:
                out.append(d)
            last = d
        return out

    def forward_return(prices_series: pd.Series, date: pd.Timestamp, days: int = 20) -> float | None:
        idx = prices_series.index
        if date not in idx:
            return None
        pos = idx.get_loc(date)
        if pos + days >= len(idx):
            return None
        return float(prices_series.iloc[pos + days] / prices_series.iloc[pos] - 1.0)

    def eval_persistence(df: pd.DataFrame, regime_for_weights: pd.Series, label: str) -> dict:
        out = {}
        for n in (1, 2, 3, 5):
            trigs = confirmed_trigger_dates(df, n)
            per_trigger = []
            for d in trigs:
                # "maintain original position": golden1 -> proxy 60/40ish? We don't
                # know a2118's exact golden1 weights for this synthetic run, so use
                # the two extremes actually in the ticker set: 00631L (full risk-on
                # proxy for "maintain") vs 0050 (defensive-ish) vs 00632R (hedge) vs
                # cash (0%). This mirrors the 2025-2026 persistence backtest's
                # comparison set.
                r_631l = forward_return(prices["00631L.TW"], d)
                r_632r = forward_return(prices["00632R.TW"], d)
                r_0050 = forward_return(prices["0050.TW"], d)
                if r_631l is None:
                    continue
                per_trigger.append(
                    {
                        "date": str(d.date()),
                        "maintain_00631L": r_631l,
                        "cash": 0.0,
                        "hedge_00632R": r_632r,
                        "defensive_0050": r_0050,
                    }
                )
            out[f"N={n}"] = {
                "n_triggers_raw": len(trigs),
                "n_usable": len(per_trigger),
                "per_trigger": per_trigger,
                "mean_maintain_00631L": (
                    float(np.mean([p["maintain_00631L"] for p in per_trigger])) if per_trigger else None
                ),
                "mean_hedge_00632R": (
                    float(np.mean([p["hedge_00632R"] for p in per_trigger])) if per_trigger else None
                ),
                "win_rate_vs_cash": (
                    float(np.mean([p["maintain_00631L"] > 0.0 for p in per_trigger])) if per_trigger else None
                ),
                "win_rate_vs_hedge": (
                    float(
                        np.mean(
                            [p["maintain_00631L"] > p["hedge_00632R"] for p in per_trigger if p["hedge_00632R"] is not None]
                        )
                    )
                    if per_trigger
                    else None
                ),
            }
        return out

    persistence_real = eval_persistence(replay_real, real_rule_regime, "real_rule")
    persistence_ideal = eval_persistence(replay_ideal, idealized_regime, "idealized")

    result = {
        "window": {"start": START, "end": END, "rows": int(len(features))},
        "data_quality": {
            "chip_features_available": False,
            "note": (
                "2008 proxy has no real institutional/margin/derivative data. "
                "_regime_features(chip_features=None) hardcodes every chip_*/"
                "derivative_* risk flag to 0.0, so chip_score=derivative_score="
                "total_risk_score=0 for the entire window (verified via assert). "
                "tail_risk_score is unaffected -- it's derived purely from "
                "return_1d/hist_var_20/realized_vol ratios, all price-based."
            ),
            "total_risk_score_always_zero": True,
            "a2111_switch_rule_require_total_risk_score": int(rule.require_total_risk_score),
            "consequence": (
                "a2111/a2118's actual SwitchRule requires total_risk_score >= "
                f"{rule.require_total_risk_score} to enter defensive (AND'd with "
                "chip_ok/derivative_ok/tail_risk_ok). Since total_risk_score is "
                "always 0, `enter` is always False -- the real a2118 switch logic "
                "would NEVER leave golden1 (full 2x leverage) on this 2008 proxy, "
                "purely due to missing chip data, regardless of how bad the price "
                "action got. This is reported as 'real_rule' below (regime pinned "
                "golden1 throughout). A secondary 'idealized' regime (MA100/drawdown "
                "gates only, chip/derivative/total_risk/tail_risk gates dropped) is "
                "also computed, purely to get a non-degenerate defensive regime "
                "series for the persistence-filter comparison -- this is NOT what "
                "a2111 would actually do on this data, it's a labeled hypothetical."
            ),
            "never_enters_defensive_under_real_rule": never_enters,
        },
        "state_distribution": {
            "real_rule_regime_pinned_golden1": state_counts(replay_real),
            "idealized_regime": state_counts(replay_ideal),
        },
        "crash_risk_dates": {
            "real_rule_regime_pinned_golden1": crash_dates(replay_real),
            "idealized_regime": crash_dates(replay_ideal),
        },
        "crash_risk_regime_at_trigger": {
            "real_rule_regime_pinned_golden1": crash_regime_breakdown(replay_real),
            "idealized_regime": crash_regime_breakdown(replay_ideal),
        },
        "persistence_backtest_real_rule_pinned_golden1": persistence_real,
        "persistence_backtest_idealized_regime": persistence_ideal,
    }

    out_path = PROJECT_ROOT / "results" / "market_state_2008_proxy_backtest_20260704.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Saved: {out_path}")
    print(json.dumps(result["data_quality"], indent=2, ensure_ascii=False))
    print("\nState distribution (real rule, regime pinned golden1):", state_counts(replay_real))
    print("State distribution (idealized regime):", state_counts(replay_ideal))
    print("\ncrash_risk dates (real rule):", crash_dates(replay_real))
    print("crash_risk regime breakdown (real rule):", crash_regime_breakdown(replay_real))
    print("\ncrash_risk dates (idealized):", crash_dates(replay_ideal)[:20], "..." if len(crash_dates(replay_ideal)) > 20 else "")
    print("crash_risk regime breakdown (idealized):", crash_regime_breakdown(replay_ideal))
    print("\nPersistence (real rule, pinned golden1):")
    for k, v in persistence_real.items():
        print(f"  {k}: n_triggers={v['n_triggers_raw']} mean_maintain_00631L={v['mean_maintain_00631L']}")
    print("\nPersistence (idealized regime):")
    for k, v in persistence_ideal.items():
        print(f"  {k}: n_triggers={v['n_triggers_raw']} mean_maintain_00631L={v['mean_maintain_00631L']}")


if __name__ == "__main__":
    main()
