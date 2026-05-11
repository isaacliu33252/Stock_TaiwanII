#!/usr/bin/env python3
"""Grid-search the 4-ETF PPO portfolio strategy.

This is an orchestration layer around
train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py.
It keeps the trading environment in one place and makes parameter
optimization reproducible across seeds.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
TRAIN_SCRIPT = PROJECT_ROOT / "train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py"


@dataclass(frozen=True)
class SearchConfig:
    turnover_penalty: float
    min_rebalance_days: int
    min_weight: float
    max_weight: float
    enable_pva_sigmoid: bool
    pva_weight: float
    pva_drift_threshold: float
    enable_range_harvest: bool = False
    range_drift_threshold: float = 0.05
    use_rsi_features: bool = False

    @property
    def config_id(self) -> str:
        mode = "pva" if self.enable_pva_sigmoid else "base"
        if self.enable_range_harvest:
            mode += "_range"
        if self.use_rsi_features:
            mode += "_rsi"
        return (
            f"{mode}_turn{self.turnover_penalty:g}_reb{self.min_rebalance_days}"
            f"_minw{self.min_weight:g}_maxw{self.max_weight:g}"
            f"_pvaw{self.pva_weight:g}_pvad{self.pva_drift_threshold:g}"
        )


def _parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_result_path(stdout: str) -> Path:
    match = re.search(r"^Result:\s+(.+)$", stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to parse Result path from training output")
    return Path(match.group(1).strip())


def _load_result(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _base_train_args(args: argparse.Namespace) -> list[str]:
    cmd = [
        "--train-start",
        args.train_start,
        "--train-end",
        args.train_end,
        "--backtest-start",
        args.backtest_start,
        "--backtest-end",
        args.backtest_end,
        "--download-end",
        args.download_end,
        "--timesteps",
        str(args.timesteps),
        "--ppo-verbose",
        str(args.ppo_verbose),
    ]
    if args.enable_dca:
        cmd.extend(
            [
                "--enable-dca",
                "--dca-day",
                str(args.dca_day),
                "--dca-0050",
                str(args.dca_0050),
                "--dca-0056",
                str(args.dca_0056),
                "--dca-00713",
                str(args.dca_00713),
                "--dca-00878",
                str(args.dca_00878),
            ]
        )
    return cmd


def _config_args(config: SearchConfig) -> list[str]:
    cmd = [
        "--turnover-penalty",
        str(config.turnover_penalty),
        "--min-rebalance-days",
        str(config.min_rebalance_days),
        "--min-weight",
        str(config.min_weight),
        "--max-weight",
        str(config.max_weight),
    ]
    if config.use_rsi_features:
        cmd.append("--use-rsi-features")
    if config.enable_range_harvest:
        cmd.extend(["--enable-range-harvest", "--range-drift-threshold", str(config.range_drift_threshold)])
    if config.enable_pva_sigmoid:
        cmd.extend(
            [
                "--enable-pva-sigmoid",
                "--pva-weight",
                str(config.pva_weight),
                "--pva-drift-threshold",
                str(config.pva_drift_threshold),
            ]
        )
    return cmd


def _run_one(args: argparse.Namespace, config: SearchConfig, seed: int) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(TRAIN_SCRIPT),
        *_base_train_args(args),
        *_config_args(config),
        "--seed",
        str(seed),
    ]
    print(f"[run] {config.config_id} seed={seed}")
    if args.dry_run:
        print(" ".join(cmd))
        return {
            "config_id": config.config_id,
            "seed": seed,
            "dry_run": True,
            **asdict(config),
        }

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
        raise RuntimeError(f"Training failed: config={config.config_id}, seed={seed}")

    result_path = _parse_result_path(completed.stdout)
    payload = _load_result(result_path)
    metrics = payload["rl_metrics"]
    investment = payload.get("investment_summary", {})
    total_return_key = (
        "return_on_invested"
        if args.enable_dca
        else "total_return"
    )
    total_return = (
        float(investment["simple_return_on_total_invested"])
        if args.enable_dca
        else float(metrics["total_return"])
    )
    row = {
        "config_id": config.config_id,
        "seed": seed,
        "result_path": str(result_path),
        "score_metric": total_return_key,
        "score_return": total_return,
        "final_value": float(payload["final_value"]),
        "total_return": float(metrics["total_return"]),
        "annual_return": float(metrics["annual_return"]),
        "sharpe": float(metrics["sharpe"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "num_trades": int(payload["num_trades"]),
        "fees_paid_estimate": float(payload.get("fees_paid_estimate", 0.0)),
        "dca_purchase_count": int(payload.get("dca_purchase_count", 0)),
        "range_harvest_count": int(payload.get("range_harvest_count", 0)),
        "pva_sigmoid_count": int(payload.get("pva_sigmoid_count", 0)),
        "final_weight_0050": float(payload["final_weights"]["0050.TW"]),
        "final_weight_0056": float(payload["final_weights"]["0056.TW"]),
        "final_weight_00713": float(payload["final_weights"]["00713.TW"]),
        "final_weight_00878": float(payload["final_weights"]["00878.TW"]),
        **asdict(config),
    }
    if args.enable_dca:
        row.update(
            {
                "total_invested": float(investment["total_invested"]),
                "net_profit": float(investment["net_profit"]),
                "return_on_invested": float(investment["simple_return_on_total_invested"]),
            }
        )
    return row


def _build_configs(args: argparse.Namespace) -> list[SearchConfig]:
    turnovers = _parse_float_list(args.turnover_penalties)
    rebalance_days = _parse_int_list(args.min_rebalance_days)
    min_weights = _parse_float_list(args.min_weights)
    max_weights = _parse_float_list(args.max_weights)
    pva_weights = _parse_float_list(args.pva_weights)
    pva_drifts = _parse_float_list(args.pva_drift_thresholds)
    range_drifts = _parse_float_list(args.range_drift_thresholds)

    configs: list[SearchConfig] = []
    if args.include_baseline:
        for turnover, rebalance, min_weight, max_weight in itertools.product(
            turnovers, rebalance_days, min_weights, max_weights
        ):
            configs.append(
                SearchConfig(
                    turnover_penalty=turnover,
                    min_rebalance_days=rebalance,
                    min_weight=min_weight,
                    max_weight=max_weight,
                    enable_pva_sigmoid=False,
                    pva_weight=0.0,
                    pva_drift_threshold=0.0,
                    use_rsi_features=args.use_rsi_features,
                )
            )

    for turnover, rebalance, min_weight, max_weight, pva_weight, pva_drift in itertools.product(
        turnovers, rebalance_days, min_weights, max_weights, pva_weights, pva_drifts
    ):
        configs.append(
            SearchConfig(
                turnover_penalty=turnover,
                min_rebalance_days=rebalance,
                min_weight=min_weight,
                max_weight=max_weight,
                enable_pva_sigmoid=True,
                pva_weight=pva_weight,
                pva_drift_threshold=pva_drift,
                use_rsi_features=args.use_rsi_features,
            )
        )

    if args.include_range_harvest:
        for turnover, rebalance, min_weight, max_weight, range_drift in itertools.product(
            turnovers, rebalance_days, min_weights, max_weights, range_drifts
        ):
            configs.append(
                SearchConfig(
                    turnover_penalty=turnover,
                    min_rebalance_days=rebalance,
                    min_weight=min_weight,
                    max_weight=max_weight,
                    enable_pva_sigmoid=False,
                    pva_weight=0.0,
                    pva_drift_threshold=0.0,
                    enable_range_harvest=True,
                    range_drift_threshold=range_drift,
                    use_rsi_features=args.use_rsi_features,
                )
            )

    seen = set()
    unique = []
    for config in configs:
        if config.config_id in seen:
            continue
        seen.add(config.config_id)
        unique.append(config)
    return unique


def _summarize(rows: list[dict[str, Any]], objective: str) -> list[dict[str, Any]]:
    summaries = []
    for config_id in sorted({row["config_id"] for row in rows}):
        group = [row for row in rows if row["config_id"] == config_id and not row.get("dry_run")]
        if not group:
            continue
        returns = [float(row["score_return"]) for row in group]
        sharpes = [float(row["sharpe"]) for row in group]
        mdds = [float(row["max_drawdown"]) for row in group]
        trades = [int(row["num_trades"]) for row in group]
        summary = {
            "config_id": config_id,
            "runs": len(group),
            "objective": objective,
            "mean_score_return": mean(returns),
            "std_score_return": pstdev(returns) if len(returns) > 1 else 0.0,
            "mean_sharpe": mean(sharpes),
            "mean_max_drawdown": mean(mdds),
            "mean_trades": mean(trades),
            "worst_score_return": min(returns),
            "best_score_return": max(returns),
            **{key: group[0][key] for key in asdict(SearchConfig(0, 0, 0, 1, False, 0, 0)).keys()},
        }
        if objective == "robust_return":
            summary["rank_score"] = summary["mean_score_return"] - 0.5 * summary["std_score_return"]
        elif objective == "sharpe":
            summary["rank_score"] = summary["mean_sharpe"]
        else:
            summary["rank_score"] = summary["mean_score_return"]
        summaries.append(summary)

    return sorted(summaries, key=lambda item: item["rank_score"], reverse=True)


def _write_outputs(rows: list[dict[str, Any]], summaries: list[dict[str, Any]], args: argparse.Namespace) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = PROJECT_ROOT / "results" / f"optimize_portfolio_grid_{timestamp}.json"
    out_csv = PROJECT_ROOT / "results" / f"optimize_portfolio_grid_{timestamp}.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "rows": rows,
        "summary_ranked": summaries,
        "best": summaries[0] if summaries else None,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    fieldnames = list(summaries[0].keys()) if summaries else list(rows[0].keys())
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries if summaries else rows)

    return out_json, out_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-search the 4-ETF PPO portfolio strategy.")
    parser.add_argument("--train-start", default="2009-01-01")
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--backtest-start", default="2024-01-01")
    parser.add_argument("--backtest-end", default="2026-05-08")
    parser.add_argument("--download-end", default="2026-05-09")
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument("--seeds", default="42,7,123")
    parser.add_argument("--turnover-penalties", default="0.08")
    parser.add_argument("--min-rebalance-days", default="45,60")
    parser.add_argument("--min-weights", default="0.05")
    parser.add_argument("--max-weights", default="0.60,0.70")
    parser.add_argument("--pva-weights", default="0.20,0.30,0.45")
    parser.add_argument("--pva-drift-thresholds", default="0.03,0.05,0.08")
    parser.add_argument("--range-drift-thresholds", default="0.05")
    parser.add_argument("--include-baseline", action="store_true")
    parser.add_argument("--include-range-harvest", action="store_true")
    parser.add_argument("--use-rsi-features", action="store_true")
    parser.add_argument("--enable-dca", action="store_true", default=True)
    parser.add_argument("--disable-dca", dest="enable_dca", action="store_false")
    parser.add_argument("--dca-day", type=int, default=26)
    parser.add_argument("--dca-0050", type=float, default=5_000.0)
    parser.add_argument("--dca-0056", type=float, default=5_000.0)
    parser.add_argument("--dca-00713", type=float, default=5_000.0)
    parser.add_argument("--dca-00878", type=float, default=10_000.0)
    parser.add_argument("--objective", choices=["robust_return", "mean_return", "sharpe"], default="robust_return")
    parser.add_argument("--ppo-verbose", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    seeds = _parse_int_list(args.seeds)
    configs = _build_configs(args)
    print(f"Configs: {len(configs)}, seeds: {seeds}, total runs: {len(configs) * len(seeds)}")

    rows = [_run_one(args, config, seed) for config in configs for seed in seeds]
    if args.dry_run:
        return

    summaries = _summarize(rows, args.objective)
    out_json, out_csv = _write_outputs(rows, summaries, args)
    print("=" * 72)
    print("Portfolio grid optimization done")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")
    if summaries:
        print("Best:")
        print(json.dumps(summaries[0], ensure_ascii=False, indent=2))
    print("=" * 72)


if __name__ == "__main__":
    main()
