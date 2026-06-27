#!/usr/bin/env python3
"""WF Select：使用舊8-feature環境評估已訓練的模型（不改train_segments.py）"""
import sys, json
from pathlib import Path
from datetime import datetime

# 在import前暫時覆蓋FEATURE_COLUMNS（只讀不寫）
OLD_FEATURES = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252", "rolling_mdd_63",
]

sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')

# 讀取train_segments的原始碼，置換FEATURE_COLUMNS後再導入
import importlib.util, types

spec = importlib.util.spec_from_file_location(
    "train_segments",
    "/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/train_segments.py"
)
ts = importlib.util.module_from_spec(spec)
# 置換FEATURE_COLUMNS
ts.FEATURE_COLUMNS = OLD_FEATURES
sys.modules["train_segments"] = ts
spec.loader.exec_module(ts)

from train_segments import (
    GROUP_A_TICKERS, GROUP_B_TICKERS,
    BACKTEST_START, BACKTEST_END, DOWNLOAD_END,
    _align_panel, _run_model_single, _buy_and_hold, _weights_for,
    load_stock_data, calculate_backtest_metrics,
    PortfolioEnv,
)
from stable_baselines3 import PPO

PROJECT_ROOT = Path('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')
MODEL_DIR = PROJECT_ROOT / "models" / "portfolio"

def load_panel():
    all_tickers = list(set(GROUP_A_TICKERS + GROUP_B_TICKERS))
    data = load_stock_data(all_tickers, BACKTEST_START, DOWNLOAD_END)
    panel_a = _align_panel(data, GROUP_A_TICKERS, BACKTEST_START, BACKTEST_END)
    panel_b = _align_panel(data, GROUP_B_TICKERS, BACKTEST_START, BACKTEST_END)
    return panel_a, panel_b

def eval_segment(name, model_path, panel, tickers):
    try:
        model = PPO.load(str(model_path))
        result = _run_model_single(model, panel, tickers)
        m = result["rl_metrics"]
        return {
            "name": name,
            "sharpe": m["sharpe"],
            "total_return": m["total_return"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m.get("win_rate", 0),
            "final_value": result["final_value"],
            "n_trades": result.get("num_trades", 0),
        }
    except Exception as e:
        return {"name": name, "error": str(e)}

def main():
    panel_a, panel_b = load_panel()

    bh_a = _buy_and_hold(panel_a, GROUP_A_TICKERS,
        _weights_for(GROUP_A_TICKERS, {t: 1.0/len(GROUP_A_TICKERS) for t in GROUP_A_TICKERS}))
    bh_b = _buy_and_hold(panel_b, GROUP_B_TICKERS,
        _weights_for(GROUP_B_TICKERS, {t: 1.0/len(GROUP_B_TICKERS) for t in GROUP_B_TICKERS}))

    print("=" * 72)
    print(f"WF 模型選擇（8-feature）| 回測區間: {BACKTEST_START} ~ {BACKTEST_END}")
    print("=" * 72)

    results_a, results_b = [], []
    for seg in range(1, 11):
        seg_name = f"s{seg:02d}"
        for group, panel, tickers, results, base_name in [
            ("A", panel_a, GROUP_A_TICKERS, results_a, "group_a_seg"),
            ("B", panel_b, GROUP_B_TICKERS, results_b, "group_b_seg"),
        ]:
            model_path = MODEL_DIR / f"{base_name}_{seg_name}.zip"
            r = eval_segment(f"{group}_{seg_name}", model_path, panel, tickers)
            results.append(r)
            status = f"OK" if "error" not in r else f"ERR: {r['error'][:50]}"
            sh = r.get("sharpe", 0)
            ret = r.get("total_return", 0)
            mdd = r.get("max_drawdown", 0)
            print(f"  [{group}_{seg_name}] Sharpe={sh:.3f} Return={ret*100:.1f}% MDD={mdd*100:.1f}% | {status}")

    m_bh_a = bh_a["metrics"]
    m_bh_b = bh_b["metrics"]

    valid_a = [x for x in results_a if "error" not in x]
    valid_b = [x for x in results_b if "error" not in x]
    best_a = max(valid_a, key=lambda x: x["sharpe"]) if valid_a else valid_a[0] if valid_a else {"name":"none","sharpe":0}
    best_b = max(valid_b, key=lambda x: x["sharpe"]) if valid_b else valid_b[0] if valid_b else {"name":"none","sharpe":0}

    print("\n" + "=" * 72)
    print("Group A 結果")
    print("=" * 72)
    print(f"{'Seg':<6} {'Sharpe':>8} {'Return':>8} {'MDD':>8} {'Trades':>7}")
    for r in sorted(results_a, key=lambda x: -x.get("sharpe", 0)):
        marker = " ◄" if r["name"] == best_a["name"] else ""
        print(f"  {r['name']:<6} {r.get('sharpe',0):>8.3f} {r.get('total_return',0)*100:>7.1f}% {r.get('max_drawdown',0)*100:>7.1f}% {r.get('n_trades',0):>7}{marker}")
    print(f"  {'B&H':<6} {m_bh_a['sharpe']:>8.3f} {m_bh_a['total_return']*100:>7.1f}% {m_bh_a['max_drawdown']*100:>7.1f}%")

    print("\n" + "=" * 72)
    print("Group B 結果")
    print("=" * 72)
    print(f"{'Seg':<6} {'Sharpe':>8} {'Return':>8} {'MDD':>8} {'Trades':>7}")
    for r in sorted(results_b, key=lambda x: -x.get("sharpe", 0)):
        marker = " ◄" if r["name"] == best_b["name"] else ""
        print(f"  {r['name']:<6} {r.get('sharpe',0):>8.3f} {r.get('total_return',0)*100:>7.1f}% {r.get('max_drawdown',0)*100:>7.1f}% {r.get('n_trades',0):>7}{marker}")
    print(f"  {'B&H':<6} {m_bh_b['sharpe']:>8.3f} {m_bh_b['total_return']*100:>7.1f}% {m_bh_b['max_drawdown']*100:>7.1f}%")

    print("\n" + "=" * 72)
    print(f"★ Best A: {best_a['name']}  Sharpe={best_a['sharpe']:.3f}")
    print(f"★ Best B: {best_b['name']}  Sharpe={best_b['sharpe']:.3f}")
    print("=" * 72)

    out = {
        "timestamp": datetime.now().isoformat(),
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "feature_version": "old_8_features",
        "best_a": best_a,
        "best_b": best_b,
        "all_a": results_a,
        "all_b": results_b,
        "bh_a": {"sharpe": m_bh_a["sharpe"], "total_return": m_bh_a["total_return"], "max_drawdown": m_bh_a["max_drawdown"]},
        "bh_b": {"sharpe": m_bh_b["sharpe"], "total_return": m_bh_b["total_return"], "max_drawdown": m_bh_b["max_drawdown"]},
    }
    out_path = PROJECT_ROOT / "results" / f"wf_select_old8_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n結果已儲存: {out_path}")

if __name__ == "__main__":
    main()
