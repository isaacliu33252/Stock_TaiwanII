"""多 seed 比較 DCA+PPO baseline 與 DCA+PPO+PVA/SJM。

用途：
- 避免只看單一 seed 42 就判定 PVA/SJM 有效。
- 直接呼叫現有訓練腳本，確保比較使用同一套資料、環境與輸出格式。
- 產出 JSON/CSV 彙總，方便後續貼到 README 或畫圖。

注意：
- 這個腳本會重新訓練模型；`--seeds 42 7 123` 代表 baseline 與 PVA/SJM
  各跑 3 次，共 6 次。
- 預設 timesteps=20000，完整多 seed 會花時間。快速 smoke test 可用
  `--timesteps 1024 --seeds 42`，但該結果不能當正式結論。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
TRAIN_SCRIPT = PROJECT_ROOT / "train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py"


BASE_ARGS = [
    "--train-start",
    "2009-01-01",
    "--train-end",
    "2023-12-31",
    "--backtest-start",
    "2024-01-01",
    "--backtest-end",
    "2026-05-08",
    "--download-end",
    "2026-05-09",
    "--turnover-penalty",
    "0.08",
    "--min-rebalance-days",
    "60",
    "--min-weight",
    "0.05",
    "--max-weight",
    "0.60",
    "--enable-dca",
    "--dca-day",
    "26",
    "--dca-0050",
    "5000",
    "--dca-0056",
    "5000",
    "--dca-00713",
    "5000",
    "--dca-00878",
    "10000",
    "--ppo-verbose",
    "0",
]


def _parse_result_path(stdout: str) -> Path:
    match = re.search(r"^Result:\s+(.+)$", stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("無法從訓練輸出解析 Result 路徑")
    return Path(match.group(1).strip())


def _load_result(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _row(strategy: str, seed: int, result_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    investment = payload["investment_summary"]
    metrics = payload["rl_metrics"]
    return {
        "strategy": strategy,
        "seed": seed,
        "result_path": str(result_path),
        "final_value": float(payload["final_value"]),
        "total_invested": float(investment["total_invested"]),
        "net_profit": float(investment["net_profit"]),
        "return_on_invested": float(investment["simple_return_on_total_invested"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe": float(metrics["sharpe"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "num_trades": int(payload["num_trades"]),
        "dca_purchase_count": int(payload.get("dca_purchase_count", 0)),
        "pva_sigmoid_count": int(payload.get("pva_sigmoid_count", 0)),
        "final_weight_0050": float(payload["final_weights"]["0050.TW"]),
        "final_weight_0056": float(payload["final_weights"]["0056.TW"]),
        "final_weight_00713": float(payload["final_weights"]["00713.TW"]),
        "final_weight_00878": float(payload["final_weights"]["00878.TW"]),
    }


def _run_one(strategy: str, seed: int, timesteps: int) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(TRAIN_SCRIPT),
        *BASE_ARGS,
        "--timesteps",
        str(timesteps),
        "--seed",
        str(seed),
    ]
    if strategy == "dca_ppo_pva_sjm":
        cmd.extend(["--enable-pva-sigmoid", "--pva-weight", "0.30", "--pva-drift-threshold", "0.05"])

    print(f"[run] strategy={strategy} seed={seed} timesteps={timesteps}")
    completed = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout)
    if completed.returncode != 0:
        raise RuntimeError(f"訓練失敗：strategy={strategy}, seed={seed}, returncode={completed.returncode}")

    result_path = _parse_result_path(completed.stdout)
    payload = _load_result(result_path)
    return _row(strategy, seed, result_path, payload)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for strategy in sorted({row["strategy"] for row in rows}):
        group = [row for row in rows if row["strategy"] == strategy]
        returns = [row["return_on_invested"] for row in group]
        sharpes = [row["sharpe"] for row in group]
        mdds = [row["max_drawdown"] for row in group]
        summary[strategy] = {
            "runs": len(group),
            "mean_return_on_invested": mean(returns),
            "std_return_on_invested": pstdev(returns) if len(returns) > 1 else 0.0,
            "mean_sharpe": mean(sharpes),
            "mean_max_drawdown": mean(mdds),
            "mean_pva_sigmoid_count": mean([row["pva_sigmoid_count"] for row in group]),
        }

    baseline = summary.get("dca_ppo")
    pva = summary.get("dca_ppo_pva_sjm")
    if baseline and pva:
        summary["comparison"] = {
            "mean_return_delta_pva_minus_baseline": (
                pva["mean_return_on_invested"] - baseline["mean_return_on_invested"]
            ),
            "mean_sharpe_delta_pva_minus_baseline": pva["mean_sharpe"] - baseline["mean_sharpe"],
        }
    return summary


def _write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = PROJECT_ROOT / "results" / f"compare_dca_ppo_pva_sjm_multiseed_{timestamp}.json"
    out_csv = PROJECT_ROOT / "results" / f"compare_dca_ppo_pva_sjm_multiseed_{timestamp}.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "summary": summary}, f, ensure_ascii=False, indent=2)

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return out_json, out_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare DCA+PPO vs DCA+PPO+PVA/SJM across seeds.")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 7, 123])
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-pva", action="store_true")
    args = parser.parse_args()

    strategies = []
    if not args.skip_baseline:
        strategies.append("dca_ppo")
    if not args.skip_pva:
        strategies.append("dca_ppo_pva_sjm")
    if not strategies:
        raise SystemExit("至少要保留 baseline 或 PVA/SJM 其中一個策略")

    rows = [_run_one(strategy, seed, args.timesteps) for seed in args.seeds for strategy in strategies]
    summary = _summarize(rows)
    out_json, out_csv = _write_outputs(rows, summary)

    print("=" * 72)
    print("Multi-seed comparison done")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 72)


if __name__ == "__main__":
    main()
