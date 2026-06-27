#!/usr/bin/env python3
"""
golden_00631L V11：MA50 混合 + MA20 趨勢保護
============================================
V9（MA200→30%, MA200~MA50→80%, MA50之上→90~100%）的基礎上，
新增 MA20 趨勢保護：價格跌破 MA20 時降至 30%，相當於日內 ATR 止損。

邏輯（優先級由高到低）：
1. 跌破 MA200  →  30%  （空頭市場，系統性風險）
2. 跌破 MA20   →  30%  （上升趨勢中單日急跌的保護墊）
3. MA200~MA50  →  80%  （中性/過渡區）
4. MA50 之上   →  90~100%（多頭市場，根據 price_ma200_dist 映射）

背景：
- 2026-03-09: -10.0% 單日跌，回測 MDD -21.2%
- 2026-04-02: -4.8% 單日跌
- 2026-06-08: -7.8% 單日跌
MA20 保護預期能在這些日子將倉位降至 30%，降低當日損失。
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb
from stable_baselines3 import PPO

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

    df["ma200"] = close.rolling(200).mean()
    df["ma120"] = close.rolling(120).mean()
    df["ma60"] = close.rolling(60).mean()
    df["ma50"] = close.rolling(50).mean()
    df["ma20"] = close.rolling(20).mean()
    # MA20 斜率（5日變化 / MA20 值，反映趨勢方向）
    df["ma20_slope"] = df["ma20"].diff(5) / df["ma20"].shift(5)

    df["close_ma200_ratio"] = close / df["ma200"]
    df["close_ma120_ratio"] = close / df["ma120"]
    df["close_ma240_ratio"] = close / df["ma200"].rolling(240).mean()  # approx

    df["below_ma200"] = (close < df["ma200"]).astype(float)
    df["below_ma50"] = (close < df["ma50"]).astype(float)
    df["below_ma20"] = (close < df["ma20"]).astype(float)

    df["price_ma200_dist"] = (close - df["ma200"]) / df["ma200"]

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / close  # ATR as % of price

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

    return df.dropna(subset=["ma20", "ma20_slope", "price_ma200_dist", "below_ma200", "below_ma50", "below_ma20", "close"])


def compute_target_weight(row: dict) -> float:
    """V12 倉位規則（優先級由高到低）

    等級 1：空頭市場（跌破 MA200）
    等級 2：上升趨勢中 MA20 向下確認的急跌保護（below_ma20 + MA20 下降中）
    等級 3：中性/過渡區（MA200~MA50 之間）
    等級 4：多頭市場（MA50 之上）→ 90~100%
    """
    below_ma200 = row["below_ma200"]
    below_ma50 = row["below_ma50"]
    below_ma20 = row["below_ma20"]
    ma20_slope = row.get("ma20_slope", 0.0)  # MA20 斜率（可選欄位）
    price_ma200_dist = row["price_ma200_dist"]

    # 等級 1：空頭市場（跌破 MA200）
    if below_ma200 > 0.5:
        return 0.30

    # 等級 2：上升趨勢中 MA20 確認的急跌保護
    # 條件：價格在 MA20 之下，且 MA20 本身處於下行趨勢（斜率 < 0）
    if below_ma20 > 0.5 and ma20_slope < 0:
        return 0.30

    # 等級 3：中性/過渡區（MA200~MA50 之間）
    if below_ma50 > 0.5:
        return 0.80

    # 等級 4：多頭市場（MA50 之上）→ 90~100%
    raw = 0.90 + (price_ma200_dist / 0.10) * 0.10
    return float(np.clip(raw, 0.90, 1.00))


def backtest(df: pd.DataFrame, backtest_start: str, backtest_end: str) -> tuple[dict, pd.DataFrame]:
    bt = df.loc[backtest_start:backtest_end].copy()
    bt = bt.reset_index()
    n = len(bt)

    cash = INITIAL_CASH
    shares = 0.0
    portfolio_value = INITIAL_CASH  # 當前投資組合總值（不含 cash 用於交易的過渡）
    history = []

    for i in range(n - 1):
        row = bt.iloc[i]
        w = compute_target_weight(row)

        close_price = row["close"]
        next_open = bt.iloc[i + 1]["open"]

        # 用「前一天收盤時的投資組合總值」計算目標股數，避免複利疊加 bug
        prev_portfolio_value = portfolio_value
        target_shares = (prev_portfolio_value * w) / next_open if next_open > 0 else 0.0

        if target_shares > shares + 0.5:
            # 買入：用 prev_portfolio_value * (1-w) 的閒置現金買
            buy_cost = (target_shares - shares) * next_open
            cash -= buy_cost
            shares = target_shares
        elif target_shares < shares - 0.5:
            # 賣出：持有量降到 target_shares
            sell_proceeds = (shares - target_shares) * next_open
            cash += sell_proceeds
            shares = target_shares

        # 當日結束時的投資組合總值
        portfolio_value = cash + shares * bt.iloc[i + 1]["close"]
        ret = portfolio_value / INITIAL_CASH - 1

        history.append({
            "date": str(bt.iloc[i].name.date()) if hasattr(bt.iloc[i].name, "date") else str(bt.iloc[i].name)[:10],
            "close": close_price,
            "next_open": next_open,
            "below_ma200": row["below_ma200"],
            "below_ma50": row["below_ma50"],
            "below_ma20": row["below_ma20"],
            "price_ma200_dist": row["price_ma200_dist"],
            "ma20": row["ma20"],
            "ma20_slope": row["ma20_slope"],
            "ma50": row["ma50"],
            "ma200": row["ma200"],
            "target_weight": w,
            "cash": cash,
            "shares": shares,
            "total_value": portfolio_value,
            "return": ret,
        })

    frame = pd.DataFrame(history)

    # 計算 metrics
    rets = frame["total_value"].pct_change().dropna()
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0.0

    running_max = frame["total_value"].cummax()
    drawdown = (frame["total_value"] - running_max) / running_max
    mdd = drawdown.min()

    final_val = frame["total_value"].iloc[-1]
    cum_ret = final_val / INITIAL_CASH - 1
    ann_ret = (1 + cum_ret) ** (252 / len(frame)) - 1

    # Buy & Hold
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
        "avg_weight": float(frame["target_weight"].mean()),
    }

    return metrics, frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-start", default="2026-01-02")
    parser.add_argument("--backtest-end", default="2026-06-23")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"golden_00631L V12（MA50 + MA20 趨勢保護 V2）")
    print(f"回測：{args.backtest_start} ~ {args.backtest_end}")
    print(f"{'='*60}")

    # 載入足夠長的資料（需要 200 日 MA）
    rows = load_data(TICKER, "2020-01-01", args.backtest_end)
    feat = build_features(rows)
    print(f"\n特徵建好，最後日期：{feat.index[-1].date()}")

    metrics, frame = backtest(feat, args.backtest_start, args.backtest_end)

    print(f"\n=== V11 回測結果 ===")
    print(f"最終淨值：{metrics['final_value']:,.0f}（{metrics['cumulative_return']:+.2%}）")
    print(f"年化報酬：{metrics['annualized_return']:+.2%}")
    print(f"Sharpe：{metrics['sharpe_ratio']:.3f}")
    print(f"MDD：{metrics['max_drawdown']:.2%}")
    print(f"BH 報酬：{metrics['buy_hold_return']:+.2%}")
    print(f"超額報酬：{metrics['excess_return']:+.2%}")
    print(f"\n觸發天數：below_ma20={metrics['days_below_ma20']}, below_ma50={metrics['days_below_ma50']}, below_ma200={metrics['days_below_ma200']}")
    print(f"平均倉位：{metrics['avg_weight']:.2%}")

    # 對比 V9
    print(f"\n=== V9 對照（2026-01-02 ~ 2026-06-18）===")
    print(f"V9: 最終淨值=2,196,145, Sharpe=3.396, MDD=-21.22%, 倉位=90~100%")
    print(f"V11: 最終淨值={metrics['final_value']:,.0f}, Sharpe={metrics['sharpe_ratio']:.3f}, MDD={metrics['max_drawdown']:.2%}")

    # 存檔
    version = "v12"
    result_path = PROJECT_ROOT / "results" / f"golden_00631l_{version}_backtest_{args.backtest_start}_{args.backtest_end}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({"strategy": f"golden_00631L_{version}", "metrics": metrics}, ensure_ascii=False, indent=2))
    print(f"\n結果 JSON：{result_path}")

    frame_path = PROJECT_ROOT / "results" / f"golden_00631l_{version}_backtest_{args.backtest_start}_{args.backtest_end}_frame.csv"
    frame.to_csv(frame_path, encoding="utf-8-sig", index=False)
    print(f"Frame CSV：{frame_path}")


if __name__ == "__main__":
    main()
