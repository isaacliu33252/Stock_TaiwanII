"""
Backtest: cash_to_bond conversion in Group A+
Compares production logic vs cash→00679B during risk_on.

Usage:
  python backtest_cash_to_bond.py
"""

import json, sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _run_simple(signal, cash_to_bond):
    """Simplified: compute final weights without full shadow overhead."""
    tw = dict(signal["target_weights"])
    tcw = float(signal["target_cash_weight"])

    # group_a_sleeve = 1.0 - overlay_00679b_weight
    # In production (risk_on): overlay_00679b_weight = 0
    # In risk_off: overlay adds ~2-5% 00679B
    regime = str(signal.get("source_event", {}).get("regime", "risk_on"))

    # Normalize group weights (this mimics what shadow does)
    raw = {t: float(w) for t, w in tw.items()}
    raw["cash"] = tcw
    total = sum(raw.values())
    if total > 0:
        raw = {t: v / total for t, v in raw.items()}

    # Apply cash→bond conversion during risk_on
    if cash_to_bond and regime == "risk_on":
        cash_w = raw.get("cash", 0.0)
        if cash_w > 0:
            raw["cash"] = 0.0
            raw["00679B.TWO"] = raw.get("00679B.TWO", 0.0) + cash_w
            # Re-normalize
            total = sum(max(0, v) for v in raw.values())
            if total > 0:
                raw = {t: max(0, v) / total for t, v in raw.items()}

    # Overlay: risk_on=0%, caution=2%, risk_off=5%, severe=8%
    overlay_pct = {"risk_on": 0.0, "caution": 0.02,
                   "risk_off": 0.05, "severe": 0.08}.get(regime, 0.0)

    # Redistribute: (1-overlay) to group A, overlay to 00679B
    for t in list(raw.keys()):
        if t != "cash" and t != "00679B.TWO":
            raw[t] = raw.get(t, 0.0) * (1 - overlay_pct)
    raw["00679B.TWO"] = raw.get("00679B.TWO", 0.0) + overlay_pct

    # Final normalize
    total = sum(max(0, v) for v in raw.values())
    if total > 0:
        final_weights = {t: max(0, v) / total for t, v in raw.items()}
    else:
        final_weights = {"cash": 1.0}

    return final_weights


def run_backtest(signals, cash_to_bond):
    records = []
    for sig in signals:
        try:
            fw = _run_simple(sig, cash_to_bond)
            records.append({
                "date": sig["actual_data_date"],
                "final_weights": fw,
                "prices": sig.get("latest_prices", {}),
            })
        except Exception as e:
            continue

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    init_value = 1_000_000.0
    portfolio_values = [init_value]

    for i in range(1, len(df)):
        prev_w = df.iloc[i - 1]["final_weights"]
        curr_w = df.iloc[i]["final_weights"]
        prev_p = df.iloc[i - 1]["prices"]
        curr_p = df.iloc[i]["prices"]

        port_ret = 0.0
        all_tickers = set(list(prev_w.keys()) + list(curr_w.keys()))
        for t in all_tickers:
            p_prev = prev_p.get(t)
            p_curr = curr_p.get(t)
            w = curr_w.get(t, 0.0)
            if p_prev and p_curr and p_prev > 0 and w > 0:
                ret = (p_curr - p_prev) / p_prev
                port_ret += w * ret

        turnover = sum(abs(curr_w.get(t, 0) - prev_w.get(t, 0)) for t in all_tickers) / 2
        cost = turnover * 0.0015
        portfolio_values.append(portfolio_values[-1] * (1 + port_ret - cost))

    df["portfolio_value"] = portfolio_values
    return df


def _generate_synthetic_signals():
    """Generate regime-based synthetic signals for 2020-2026 backtest."""
    cache_dir = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"

    tickers = ["0050", "00631L", "00632R", "00679B"]
    tw_tickers = {"0050": "0050.TW", "00631L": "00631L.TW",
                  "00632R": "00632R.TW", "00679B": "00679B.TWO"}
    series = {}
    for t in tickers:
        suffix = "TWO" if t == "00679B" else "TW"
        stem = f"{t}_{suffix}"
        files = sorted(cache_dir.glob(f"{stem}_20200101_*_1d_raw_v1.parquet"))
        if not files:
            continue
        df = pd.read_parquet(files[-1])
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df[df["date"] >= "2020-01-01"].copy()
        df = df.set_index("date").sort_index()
        series[tw_tickers[t]] = df["close"]

    prices_df = pd.concat(series.values(), axis=1).sort_index().ffill().dropna()
    prices_df.columns = list(series.keys())
    lookback = 60

    for i, date in enumerate(prices_df.index):
        if i < lookback:
            continue
        window = prices_df.loc[:date]
        ma20 = window["0050.TW"].rolling(20).mean().iloc[-1]
        ma60 = window["0050.TW"].rolling(60).mean().iloc[-1]
        ma_gap = (ma20 - ma60) / ma60 if ma60 != 0 else 0

        # Production: holds cash in risk_on; 00679B only in risk_off+
        # Cash level reflects approximate FinRL behavior
        if ma_gap > 0.05:
            regime = "risk_on"
            tcw = 0.30  # FinRL holds ~30% cash when uncertain
            etw_split = 0.85
        elif ma_gap > 0:
            regime = "risk_on"
            tcw = 0.20
            etw_split = 0.85
        elif ma_gap > -0.07:
            regime = "caution"
            tcw = 0.05
            etw_split = 0.80
        else:
            regime = "risk_off"
            tcw = 0.02
            etw_split = 0.75

        total_etw = 1.0 - tcw
        tw = {
            "0050.TW":   total_etw * etw_split,
            "00631L.TW": total_etw * (1 - etw_split),
            "00632R.TW": 0.0,
        }

        latest = {t: float(window[t].iloc[-1]) for t in tickers if t in window.columns}

        yield {
            "target_weights": tw,
            "target_cash_weight": tcw,
            "actual_data_date": date.strftime("%Y-%m-%d"),
            "latest_prices": latest,
            "current_shares": {t: 0 for t in tickers},
            "source_event": {"regime": regime},
        }


def compute_metrics(df):
    if len(df) < 10:
        return {}
    rets = df["portfolio_value"].pct_change().dropna()
    total_ret = (df["portfolio_value"].iloc[-1] / df["portfolio_value"].iloc[0]) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    running_max = df["portfolio_value"].cummax()
    drawdown = (df["portfolio_value"] - running_max) / running_max
    mdd = drawdown.min()
    years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.25
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    return {
        "final":     df["portfolio_value"].iloc[-1],
        "total_ret": total_ret,
        "cagr":      cagr,
        "sharpe":    sharpe,
        "mdd":       mdd,
        "num_trades": len(df),
        "date_start": df["date"].min().date(),
        "date_end":   df["date"].max().date(),
    }


if __name__ == "__main__":
    print("=" * 65)
    print("BACKTEST: cash_to_bond Group A+ (Synthetic 2020-2026)")
    print("=" * 65)

    print("Generating synthetic signals...")
    signals = list(_generate_synthetic_signals())
    print(f"  {len(signals)} trading days generated")
    if not signals:
        print("ERROR: No signals generated. Check cache files.")
        sys.exit(1)

    print("Running backtest A (production — cash held in risk_on)...")
    df_a = run_backtest(iter(signals), cash_to_bond=False)
    m_a = compute_metrics(df_a)

    print("Running backtest B (cash_to_bond — cash→00679B in risk_on)...")
    df_b = run_backtest(iter(signals), cash_to_bond=True)
    m_b = compute_metrics(df_b)

    print()
    print(f"{'Metric':<18} {'Production (A)':>16} {'Cash→Bond (B)':>16} {'B − A':>14}")
    print("-" * 66)
    for key, fmt in [("final", ",.0f"), ("total_ret", ".4f"),
                      ("cagr", ".4f"), ("sharpe", ".4f"), ("mdd", ".2%")]:
        v_a = m_a.get(key, 0)
        v_b = m_b.get(key, 0)
        diff = v_b - v_a
        if key == "mdd":
            print(f"  {key:<16} {v_a:>16.2%} {v_b:>16.2%} {diff:>+14.2%}")
        else:
            print(f"  {key:<16} {v_a:>16{fmt}} {v_b:>16{fmt}} {diff:>+14{fmt}}")

    print()
    print(f"  {'num_trades':<16} {m_a.get('num_trades', 0):>16} {m_b.get('num_trades', 0):>16}")
    print()
    print(f"  Period: {m_a.get('date_start')} → {m_a.get('date_end')}")
    print()

    winner = "B (cash→bond)" if m_b["final"] > m_a["final"] else "A (production)"
    print(f"  → Better: {winner}  (Final {max(m_a['final'], m_b['final']):,.0f} vs {min(m_a['final'], m_b['final']):,.0f})")
