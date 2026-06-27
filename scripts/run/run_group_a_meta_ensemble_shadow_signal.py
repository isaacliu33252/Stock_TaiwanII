#!/usr/bin/env python3
"""Generate a live shadow signal for the Group A real meta ensemble."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_meta_ensemble_real_config.json"
DEFAULT_SWEEP = PROJECT_ROOT / "results" / "group_a_meta_real_vote_tune_sweep_20250101_20260603_llmfilled.json"
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"
LATEST_JSON = DEFAULT_OUTPUT_DIR / "group_a_meta_ensemble_shadow_live_latest.json"
LATEST_CSV = DEFAULT_OUTPUT_DIR / "group_a_meta_ensemble_shadow_live_latest.csv"
LATEST_MANIFEST = DEFAULT_OUTPUT_DIR / "group_a_meta_ensemble_shadow_bundle_latest.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--sweep-json", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--base-signal-json", default=None)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--xlsx", default=None)
    parser.add_argument("--holdings-row-label", default="即時庫存")
    parser.add_argument("--simulation-start", default=None)
    parser.add_argument("--history-start", default=None)
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--as-of-date", default=str(date.today()))
    parser.add_argument("--extra-cash", type=float, default=1_000_000.0)
    parser.add_argument("--override-holdings-json", default=None)
    parser.add_argument("--action-threshold", type=float, default=0.01)
    parser.add_argument("--max-stale-days", type=int, default=3)
    parser.add_argument("--max-strategy-drawdown", type=float, default=0.27)
    parser.add_argument("--max-underperformance-vs-0050", type=float, default=0.10)
    parser.add_argument("--strategy-replay", action="store_true")
    return parser.parse_args()


def _extract_output_path(stdout: str, label: str) -> Path:
    match = re.search(rf"^{label}:\s+(.+)$", stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to parse {label} path from base signal output")
    return Path(match.group(1).strip())


def _generate_base_signal(args: argparse.Namespace) -> Path:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "generate_dual_group_signal.py"),
        "--group",
        "group_a",
        "--result-json",
        str(Path(args.result_json).resolve()),
        "--holdings-row-label",
        str(args.holdings_row_label),
        "--as-of-date",
        str(args.as_of_date),
        "--extra-cash",
        f"{float(args.extra_cash):.6f}",
        "--action-threshold",
        f"{float(args.action_threshold):.6f}",
        "--max-stale-days",
        str(int(args.max_stale_days)),
        "--max-strategy-drawdown",
        f"{float(args.max_strategy_drawdown):.6f}",
        "--max-underperformance-vs-0050",
        f"{float(args.max_underperformance_vs_0050):.6f}",
    ]
    if not args.strategy_replay:
        cmd.append("--live-start")
    if args.xlsx:
        cmd.extend(["--xlsx", str(args.xlsx)])
    if args.simulation_start:
        cmd.extend(["--simulation-start", str(args.simulation_start)])
    if args.history_start:
        cmd.extend(["--history-start", str(args.history_start)])
    if args.download_end:
        cmd.extend(["--download-end", str(args.download_end)])
    if args.override_holdings_json:
        cmd.extend(["--override-holdings-json", str(args.override_holdings_json)])

    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return _extract_output_path(completed.stdout, "JSON")


def _selected_profile(config: dict[str, Any], requested: str | None) -> str:
    profile = requested or str(
        config.get("selected_signal_profile")
        or config.get("selected_allocator_profile")
        or ""
    )
    if not profile:
        raise RuntimeError("No allocator profile selected")
    return profile


def _latest_profile_target(sweep: dict[str, Any], profile: str) -> tuple[dict[str, float], float, dict[str, Any]]:
    details = dict(sweep.get("details", {}))
    if profile not in details:
        available = ", ".join(sorted(details))
        raise RuntimeError(f"Profile {profile!r} not found in sweep details. Available: {available}")
    replay = dict(details[profile]["replay"])
    events = list(replay.get("events", []))
    if events:
        event = dict(events[-1])
        weights = {ticker: float(event["target_weights"].get(ticker, 0.0)) for ticker in TICKERS}
        cash_weight = float(event.get("target_cash_weight", 0.0))
        return weights, cash_weight, event

    weights = {ticker: float(replay.get("final_weights", {}).get(ticker, 0.0)) for ticker in TICKERS}
    cash_weight = float(replay.get("final_cash_weight", max(0.0, 1.0 - sum(weights.values()))))
    return weights, cash_weight, {"date": None, "target_weights": weights, "target_cash_weight": cash_weight}


def _stale_days(base_signal: dict[str, Any], sweep: dict[str, Any]) -> int | None:
    actual_data_date = base_signal.get("actual_data_date")
    sweep_end = dict(sweep.get("actual_window", {})).get("end")
    if not actual_data_date or not sweep_end:
        return None
    return abs((pd.Timestamp(actual_data_date).date() - pd.Timestamp(sweep_end).date()).days)


def _action_hint(delta_shares: int, signal_status: str) -> str:
    if signal_status != "rebalance" or delta_shares == 0:
        return "hold"
    return "buy" if delta_shares > 0 else "sell"


def _write_shadow_signal(
    *,
    config: dict[str, Any],
    sweep: dict[str, Any],
    sweep_path: Path,
    profile: str,
    base_signal_path: Path,
    base_signal: dict[str, Any],
    target_weights: dict[str, float],
    target_cash_weight: float,
    source_event: dict[str, Any],
    stale_days: int | None,
    action_threshold: float,
) -> tuple[Path, Path, dict[str, Any]]:
    prices = {ticker: float(dict(base_signal["latest_prices"])[ticker]) for ticker in TICKERS}
    current_shares = {ticker: int(dict(base_signal["current_shares"])[ticker]) for ticker in TICKERS}
    current_weights = {ticker: float(dict(base_signal.get("current_weights", {})).get(ticker, 0.0)) for ticker in TICKERS}
    base_weights = {ticker: float(dict(base_signal["target_weights"]).get(ticker, 0.0)) for ticker in TICKERS}
    total_value = float(base_signal["current_total_portfolio_value"])
    target_shares: dict[str, int] = {}
    max_current_delta = max(abs(target_weights[ticker] - current_weights.get(ticker, 0.0)) for ticker in TICKERS)
    signal_status = "rebalance" if max_current_delta >= action_threshold else "hold"
    signal_reason = f"meta_ensemble_shadow_{profile}" if signal_status == "rebalance" else "meta_ensemble_shadow_no_trade"

    rows = []
    for ticker in TICKERS:
        shares = int(round(total_value * target_weights[ticker] / prices[ticker])) if prices[ticker] > 0 else 0
        delta_shares = shares - current_shares[ticker]
        target_shares[ticker] = shares
        rows.append(
            {
                "date": base_signal["actual_data_date"],
                "ticker": ticker,
                "latest_price": prices[ticker],
                "current_shares": current_shares[ticker],
                "current_weight": current_weights[ticker],
                "base_target_weight": base_weights[ticker],
                "meta_target_weight": target_weights[ticker],
                "target_shares": shares,
                "delta_shares": delta_shares,
                "action_hint": _action_hint(delta_shares, signal_status),
                "signal_status": signal_status,
                "signal_reason": signal_reason,
                "allocator_profile": profile,
            }
        )

    stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    prefix = DEFAULT_OUTPUT_DIR / f"group_a_meta_ensemble_shadow_signal_{stamp}"
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    variant_metrics = next((row for row in sweep.get("variants", []) if row.get("variant") == profile), {})
    summary = {
        "strategy_name": config["strategy_name"],
        "strategy_status": config["status"],
        "base_strategy": config["base_strategy"],
        "advisory_only": True,
        "production_release_unchanged": True,
        "allocator_profile": profile,
        "base_signal_json": str(base_signal_path.resolve()),
        "sweep_json": str(sweep_path.resolve()),
        "requested_as_of_date": base_signal["requested_as_of_date"],
        "actual_data_date": base_signal["actual_data_date"],
        "sweep_actual_window": sweep.get("actual_window"),
        "stale_days_vs_sweep": stale_days,
        "signal_status": signal_status,
        "signal_reason": signal_reason,
        "latest_prices": prices,
        "current_shares": current_shares,
        "current_total_portfolio_value": total_value,
        "base_target_weights": base_weights,
        "base_target_cash_weight": base_signal["target_cash_weight"],
        "target_weights": target_weights,
        "target_cash_weight": target_cash_weight,
        "target_shares": target_shares,
        "source_event": source_event,
        "selected_profile_metrics": variant_metrics,
        "promotion_decision": config.get("promotion_decision"),
        "promotion_blockers": config.get("promotion_blockers", []),
        "output_csv": str(csv_path.resolve()),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(json_path, LATEST_JSON)
    shutil.copy2(csv_path, LATEST_CSV)
    return json_path, csv_path, summary


def main() -> None:
    args = _parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sweep_path = Path(args.sweep_json or config.get("selected_signal_sweep") or DEFAULT_SWEEP).resolve()
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    profile = _selected_profile(config, args.profile)
    base_signal_path = (
        Path(args.base_signal_json).resolve()
        if args.base_signal_json
        else _generate_base_signal(args).resolve()
    )
    base_signal = json.loads(base_signal_path.read_text(encoding="utf-8"))
    stale_days = _stale_days(base_signal, sweep)
    if stale_days is not None and stale_days > int(args.max_stale_days):
        raise SystemExit(
            f"Meta ensemble sweep is stale by {stale_days} days versus base actual_data_date; "
            "rerun backtest_group_a_meta_ensemble_real.py and evaluate_group_a_meta_real_allocator_sweep.py first."
        )

    target_weights, target_cash_weight, source_event = _latest_profile_target(sweep, profile)
    json_path, csv_path, summary = _write_shadow_signal(
        config=config,
        sweep=sweep,
        sweep_path=sweep_path,
        profile=profile,
        base_signal_path=base_signal_path,
        base_signal=base_signal,
        target_weights=target_weights,
        target_cash_weight=target_cash_weight,
        source_event=source_event,
        stale_days=stale_days,
        action_threshold=float(args.action_threshold),
    )
    manifest = {
        "strategy_name": config["strategy_name"],
        "strategy_status": config["status"],
        "advisory_only": True,
        "production_release_unchanged": True,
        "allocator_profile": profile,
        "stable_signal_json": str(LATEST_JSON.resolve()),
        "stable_signal_csv": str(LATEST_CSV.resolve()),
        "generated_signal_json": str(json_path.resolve()),
        "generated_signal_csv": str(csv_path.resolve()),
        "actual_data_date": summary["actual_data_date"],
        "signal_status": summary["signal_status"],
        "signal_reason": summary["signal_reason"],
        "target_shares": summary["target_shares"],
        "promotion_decision": config.get("promotion_decision"),
    }
    LATEST_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"Strategy:      {config['strategy_name']} ({config['status']})")
    print(f"Profile:       {profile}")
    print(f"Signal status: {summary['signal_status']}")
    print(f"Reason:        {summary['signal_reason']}")
    print(f"JSON:          {json_path}")
    print(f"CSV:           {csv_path}")
    print(f"Stable JSON:   {LATEST_JSON}")
    print(f"Manifest:      {LATEST_MANIFEST}")
    print("=" * 72)


if __name__ == "__main__":
    main()
