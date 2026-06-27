#!/usr/bin/env python3
"""
golden_00631L V13：MA50 混合 + ATR Volatility-Scaled 倉位
=========================================================
V9（MA200→30%, MA200~MA50→80%, MA50之上→90~100%）的基礎上，
新增 ATR 波動度動態調整：在高波動期將倉位上限壓低，在低波動期接近 100%。

邏輯：
- 等級 1：跌破 MA200  →  30%
- 等級 2：MA50~MA200  →  80%
- 等級 3：MA50 之上：
    - ATR > 75th percentile（歷史 63 日）→ cap = 0.80
    - ATR 處於歷史高位（> 90th pct）→ cap = 0.60
    - 否則 → cap = 1.00（全倉）
- 等級 4（特殊情況）：MA20 快速殺盤保護（below_ma20 + MA20急降，單獨判斷）

V13 與 V9 的核心差異：ATR scaling 不依賴預測，而是在事後根據波動度自然降倉。
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
from FinRL.data.stock_db import DB_PATH

TICKER = "00631L.TW"
INITIAL_CASH = 1_000_000.0


def load_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT dt, ticker, close, open, high, low, volume
            FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
        """, [ticker, start, end]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt").sort_index()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    high, low = df["high"], df["low"]

    # MA
    df["ma200"] = close.rolling(200).mean()
    df["ma120"] = close.rolling(120).mean()
    df["ma60"] = close.rolling(60).mean()
    df["ma50"] = close.rolling(50).mean()
    df["ma20"] = close.rolling(20).mean()

    # Trend
    df["below_ma200"] = (close < df["ma200"]).astype(float)
    df["below_ma50"] = (close < df["ma50"]).astype(float)
    df["below_ma20"] = (close < df["ma20"]).astype(float)
    df["price_ma200_dist"] = (close - df["ma200"]) / df["ma200"]

    # MA20 slope
    df["ma20_slope"] = df["ma20"].diff(5) / df["ma20"].shift(5).clip(lower=1e-8)

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / close  # ATR as % of price

    # ATR percentile (rolling 63-day lookback)
    df["atr_pct_roll75"] = df["atr_pct"].rolling(63).quantile(0.75)
    df["atr_pct_roll90"] = df["atr_pct"].rolling(63).quantile(0.90)

    # Daily return volatility (21-day)
    df["vol_21"] = close.pct_change().rolling(21).std()

    # ADX
    high_diff = high.diff()
    low_diff = -low.diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    atr = df["atr_14"]
    plus_di = 100 * plus_dm.rolling(14).mean() / atr
    minus_di = 100 * minus_dm.rolling(14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)
    df["adx_14"] = dx.rolling(14).mean()

    return df.dropna(subset=[
        "ma20", "ma20_slope", "price_ma200_dist",
        "below_ma200", "below_ma50", "below_ma20",
        "atr_pct", "atr_pct_roll75", "atr_pct_roll90",
        "vol_21", "close",
    ])


def compute_target_weight(row: dict) -> float:
    """V13 ATR-Scaled 倉位規則"""
    below_ma200 = row["below_ma200"]
    below_ma50 = row["below_ma50"]
    below_ma20 = row["below_ma20"]
    ma20_slope = row.get("ma20_slope", 0.0)
    price_ma200_dist = row["price_ma200_dist"]
    atr_pct = row["atr_pct"]
    atr_pct_roll75 = row["atr_pct_roll75"]
    atr_pct_roll90 = row["atr_pct_roll90"]

    # 等級 1：空頭市場
    if below_ma200 > 0.5:
        return 0.30

    # 等級 2：MA20 確認的急殺保護（only in uptrend）
    # 條件：價格在 MA20 之下，且 MA20 處於下行（上升趨勢中的回調）
    if below_ma20 > 0.5 and ma20_slope < -0.01:
        return 0.30

    # 等級 3：中性/過渡區（MA200~MA50 之間）
    if below_ma50 > 0.5:
        return 0.80

    # 等級 4：MA50 之上 → ATR-based 動態 cap
    if atr_pct > atr_pct_roll90:
        cap = 0.60  # 極度高波動 → 最多 60%
    elif atr_pct > atr_pct_roll75:
        cap = 0.80  # 高波動 → 最多 80%
    else:
        cap = 1.00  # 正常波動 → 全倉

    # 基礎倉位：根據 price_ma200_dist 映射至 0.90~1.00
    raw = 0.90 + (price_ma200_dist / 0.10) * 0.10
    base_weight = float(np.clip(raw, 0.90, 1.00))

    # ATR cap 限制（只在 cap < 1.00 時才需要降 cap）
    if cap < 1.0 and base_weight > cap:
        return cap
    return base_weight


def backtest(df: pd.DataFrame, backtest_start: str, backtest_end: str) -> tuple[dict, pd.DataFrame]:
    bt = df.loc[backtest_start:backtest_end].copy()
    bt = bt.reset_index()
    n = len(bt)

    cash = INITIAL_CASH
    shares = 0.0
    portfolio_value = INITIAL_CASH
    history = []

    for i in range(n - 1):
        row = bt.iloc[i]
        w = compute_target_weight(row)

        next_open = bt.iloc[i + 1]["open"]

        prev_portfolio_value = portfolio_value
        target_shares = (prev_portfolio_value * w) / next_open if next_open > 0 else 0.0

        if target_shares > shares + 0.5:
            buy_cost = (target_shares - shares) * next_open
            cash -= buy_cost
            shares = target_shares
        elif target_shares < shares - 0.5:
            sell_proceeds = (shares - target_shares) * next_open
            cash += sell_proceeds
            shares = target_shares

        portfolio_value = cash + shares * bt.iloc[i + 1]["close"]
        ret = portfolio_value / INITIAL_CASH - 1

        history.append({
            "date": str(bt.iloc[i].name.date()) if hasattr(bt.iloc[i].name, "date") else str(bt.iloc[i].name)[:10],
            "close": row["close"],
            "next_open": next_open,
            "below_ma200": row["below_ma200"],
            "below_ma50": row["below_ma50"],
            "below_ma20": row["below_ma20"],
            "price_ma200_dist": row["price_ma200_dist"],
            "atr_pct": row["atr_pct"],
            "atr_pct_roll75": row["atr_pct_roll75"],
            "atr_pct_roll90": row["atr_pct_roll90"],
            "vol_21": row["vol_21"],
            "ma20_slope": row["ma20_slope"],
            "target_weight": w,
            "cash": cash,
            "shares": shares,
            "total_value": portfolio_value,
            "return": ret,
        })

    frame = pd.DataFrame(history)

    rets = frame["total_value"].pct_change().dropna()
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0.0
    running_max = frame["total_value"].cummax()
    drawdown = (frame["total_value"] - running_max) / running_max
    mdd = drawdown.min()

    final_val = frame["total_value"].iloc[-1]
    cum_ret = final_val / INITIAL_CASH - 1
    ann_ret = (1 + cum_ret) ** (252 / len(frame)) - 1

    bh_col = df.loc[backtest_start:backtest_end]["close"]
    bh_ret = bh_col.iloc[-1] / bh_col.iloc[0] - 1

    metrics = {
        "final_value": float(final_val),
        "cumulative_return": float(cum_ret),
        "annualized_return": float(ann_ret),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(mdd),
        "buy_hold_return": float(bh_ret),
        "excess_return": float(cum_ret - bh_ret),
        "trading_days": int(len(frame)),
        "days_below_ma20": int(frame["below_ma20"].sum()),
        "days_below_ma50": int(frame["below_ma50"].sum()),
        "days_below_ma200": int(frame["below_ma200"].sum()),
        "days_atr_cap_60": int(((frame["atr_pct"] > frame["atr_pct_roll90"]) & (frame["target_weight"] <= 0.6)).sum()),
        "days_atr_cap_80": int(((frame["atr_pct"] > frame["atr_pct_roll75"]) & (frame["atr_pct"] <= frame["atr_pct_roll90"]) & (frame["target_weight"] <= 0.8) & (frame["target_weight"] > 0.6)).sum()),
        "avg_weight": float(frame["target_weight"].mean()),
    }
    return metrics, frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-start", default="2026-01-02")
    parser.add_argument("--backtest-end", default="2026-06-23")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"golden_00631L V13（MA50 + ATR Volatility-Scaled）")
    print(f"回測：{args.backtest_start} ~ {args.backtest_end}")
    print(f"{'='*60}")

    rows = load_data(TICKER, "2020-01-01", args.backtest_end)
    feat = build_features(rows)
    print(f"\n特徵建好，最後日期：{feat.index[-1].date()}")

    metrics, frame = backtest(feat, args.backtest_start, args.backtest_end)

    print(f"\n=== V13 回測結果 ===")
    print(f"最終淨值：{metrics['final_value']:,.0f}（{metrics['cumulative_return']:+.2%}）")
    print(f"年化報酬：{metrics['annualized_return']:+.2%}")
    print(f"Sharpe：{metrics['sharpe_ratio']:.3f}")
    print(f"MDD：{metrics['max_drawdown']:.2%}")
    print(f"BH 報酬：{metrics['buy_hold_return']:+.2%}")
    print(f"超額報酬：{metrics['excess_return']:+.2%}")
    print(f"ATR cap 60觸發：{metrics['days_atr_cap_60']} 天")
    print(f"ATR cap 80觸發：{metrics['days_atr_cap_80']} 天")
    print(f"平均倉位：{metrics['avg_weight']:.2%}")

    print(f"\n=== 版本對照（2026-01-02 ~ 2026-06-18）===")
    print(f"V9:  +119.61%, Sharpe=3.396, MDD=-21.22%, 全程 90~100%")
    print(f"V12: +107.18%, Sharpe=3.167, MDD=-19.82%, MA20 slope觸發6天")
    print(f"V13: {metrics['cumulative_return']:+6.2%}, Sharpe={metrics['sharpe_ratio']:.3f}, MDD={metrics['max_drawdown']:.2%}")

    version = "v13"
    result_path = PROJECT_ROOT / "results" / f"golden_00631l_{version}_backtest_{args.backtest_start}_{args.backtest_end}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({"strategy": f"golden_00631L_{version}", "metrics": metrics}, ensure_ascii=False, indent=2))

    frame_path = PROJECT_ROOT / "results" / f"golden_00631l_{version}_backtest_{args.backtest_start}_{args.backtest_end}_frame.csv"
    frame.to_csv(frame_path, encoding="utf-8-sig", index=False)
    print(f"\n結果：{result_path}")
    print(f"Frame：{frame_path}")


if __name__ == "__main__":
    main()
