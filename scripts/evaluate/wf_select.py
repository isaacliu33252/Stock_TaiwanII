#!/usr/bin/env python3
"""Walk-forward 模型選擇：每個 segment checkpoint 跑回測，選 Sharpe 最高"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')

from train_segments import (
    GROUP_A_TICKERS, GROUP_B_TICKERS,
    BACKTEST_START, BACKTEST_END, DOWNLOAD_END,
    _align_panel, _run_model_single, _buy_and_hold, _weights_for,
    _feature_columns_from_obs_dim, _load_model_without_cloudpickle,
    load_stock_data, calculate_backtest_metrics
)

PROJECT_ROOT = Path('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')
MODEL_DIR = PROJECT_ROOT / "models" / "portfolio"

def load_backtest_data():
    all_tickers = list(set(GROUP_A_TICKERS + GROUP_B_TICKERS))
    return load_stock_data(all_tickers, BACKTEST_START, DOWNLOAD_END)

def eval_segment(name, model_path, stock_data, tickers):
    try:
        model, obs_dim = _load_model_without_cloudpickle(model_path)
        feature_columns = _feature_columns_from_obs_dim(obs_dim, tickers)
        panel = _align_panel(
            stock_data,
            tickers,
            BACKTEST_START,
            BACKTEST_END,
            feature_columns=feature_columns,
        )
        result = _run_model_single(model, panel, tickers, feature_columns=feature_columns)
        m = result["rl_metrics"]
        return {
            "name": name,
            "obs_dim": obs_dim,
            "feature_columns": feature_columns,
            "sharpe": m["sharpe"],
            "total_return": m["total_return"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m.get("win_rate", 0),
            "final_value": result["final_value"],
            "n_trades": m.get("n_trades", 0),
        }
    except Exception as e:
        return {"name": name, "error": str(e)}

def main():
    stock_data = load_backtest_data()
    panel_a = _align_panel(stock_data, GROUP_A_TICKERS, BACKTEST_START, BACKTEST_END)
    panel_b = _align_panel(stock_data, GROUP_B_TICKERS, BACKTEST_START, BACKTEST_END)

    # Buy & Hold 參考
    bh_a = _buy_and_hold(panel_a, GROUP_A_TICKERS, _weights_for(GROUP_A_TICKERS, {t: 1.0/len(GROUP_A_TICKERS) for t in GROUP_A_TICKERS}))
    bh_b = _buy_and_hold(panel_b, GROUP_B_TICKERS, _weights_for(GROUP_B_TICKERS, {t: 1.0/len(GROUP_B_TICKERS) for t in GROUP_B_TICKERS}))

    print("=" * 72)
    print(f"Walk-forward 模型選擇 | 回測區間: {BACKTEST_START} ~ {BACKTEST_END}")
    print("=" * 72)

    results_a, results_b = [], []

    for seg in range(1, 11):
        seg_name = f"s{seg:02d}"
        for group, panel, tickers, results, base_name in [
            ("A", panel_a, GROUP_A_TICKERS, results_a, "group_a_seg"),
            ("B", panel_b, GROUP_B_TICKERS, results_b, "group_b_seg"),
        ]:
            model_path = MODEL_DIR / f"{base_name}_{seg_name}.zip"
            r = eval_segment(f"{group}_{seg_name}", model_path, stock_data, tickers)
            results.append(r)
            status = f"OK" if "error" not in r else f"ERR: {r['error'][:40]}"
            print(f"  [{group}_{seg_name}] Sharpe={r.get('sharpe', 0):.3f} Return={r.get('total_return',0)*100:.1f}% MDD={r.get('max_drawdown',0)*100:.1f}% | {status}")

    # B&H
    m_bh_a = bh_a["metrics"]
    m_bh_b = bh_b["metrics"]

    # 選最好的
    valid_a = [x for x in results_a if "error" not in x]
    valid_b = [x for x in results_b if "error" not in x]
    best_a = max(valid_a, key=lambda x: x["sharpe"]) if valid_a else {"name": "none", "sharpe": 0.0}
    best_b = max(valid_b, key=lambda x: x["sharpe"]) if valid_b else {"name": "none", "sharpe": 0.0}

    print("\n" + "=" * 72)
    print("Group A 結果")
    print("=" * 72)
    print(f"{'Seg':<6} {'Sharpe':>8} {'Return':>8} {'MDD':>8} {'Trades':>7}")
    for r in sorted(results_a, key=lambda x: -x.get("sharpe", 0)):
        marker = " ◄" if r["name"] == best_a["name"] else ""
        print(f"  {r['name']:<6} {r.get('sharpe',0):>8.3f} {r.get('total_return',0)*100:>7.1f}% {r.get('max_drawdown',0)*100:>7.1f}% {r.get('n_trades',0):>7}{marker}")
    print(f"  {'B&H':<6} {m_bh_a['sharpe']:>8.3f} {m_bh_a['total_return']*100:>7.1f}% {m_bh_a['max_drawdown']*100:>7.1f}% {m_bh_a.get('n_trades',0):>7}")

    print("\n" + "=" * 72)
    print("Group B 結果")
    print("=" * 72)
    print(f"{'Seg':<6} {'Sharpe':>8} {'Return':>8} {'MDD':>8} {'Trades':>7}")
    for r in sorted(results_b, key=lambda x: -x.get("sharpe", 0)):
        marker = " ◄" if r["name"] == best_b["name"] else ""
        print(f"  {r['name']:<6} {r.get('sharpe',0):>8.3f} {r.get('total_return',0)*100:>7.1f}% {r.get('max_drawdown',0)*100:>7.1f}% {r.get('n_trades',0):>7}{marker}")
    print(f"  {'B&H':<6} {m_bh_b['sharpe']:>8.3f} {m_bh_b['total_return']*100:>7.1f}% {m_bh_b['max_drawdown']*100:>7.1f}% {m_bh_b.get('n_trades',0):>7}")

    print("\n" + "=" * 72)
    print(f"★ Best A: {best_a['name']}  Sharpe={best_a['sharpe']:.3f}")
    print(f"★ Best B: {best_b['name']}  Sharpe={best_b['sharpe']:.3f}")
    print("=" * 72)

    out = {
        "timestamp": datetime.now().isoformat(),
        "backtest_start": BACKTEST_START,
        "backtest_end": BACKTEST_END,
        "best_a": best_a,
        "best_b": best_b,
        "all_a": results_a,
        "all_b": results_b,
        "bh_a": {"sharpe": m_bh_a["sharpe"], "total_return": m_bh_a["total_return"], "max_drawdown": m_bh_a["max_drawdown"]},
        "bh_b": {"sharpe": m_bh_b["sharpe"], "total_return": m_bh_b["total_return"], "max_drawdown": m_bh_b["max_drawdown"]},
    }
    out_path = PROJECT_ROOT / "results" / f"wf_select_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n結果已儲存: {out_path}")

if __name__ == "__main__":
    main()
