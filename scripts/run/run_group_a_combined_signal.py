#!/usr/bin/env python3
"""Run the unified Group A live signal with the local regime overlay enabled."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_NAME = "latest_group_a_improved_0050_step0300bp_stepgate105_ma60_brake30_631l0_tdcc18"
RELEASE_HANDOFF = PROJECT_ROOT / "GROUP_A_GOLDEN1_0531_RELEASE.md"
DEFAULT_TDCC_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config_destination_primary.json"
DEFAULT_RESULT_JSON = (
    PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260531_20260609_214023.json"
)
DEFAULT_LATEST_JSON = PROJECT_ROOT / "results" / "group_a_combined_live_latest.json"
DEFAULT_LATEST_CSV = PROJECT_ROOT / "results" / "group_a_combined_live_latest.csv"
DEFAULT_MANIFEST = PROJECT_ROOT / "results" / "group_a_combined_bundle_latest.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unified Group A signal: institutional-only PPO mainline plus "
            "local TWII/0050 regime defensive overlay."
        )
    )
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
    parser.add_argument(
        "--group-a-0050-max-weight-step",
        type=float,
        default=0.03,
        help="Latest Group A overlay: limit each 0050 target-weight move to +/- this amount.",
    )
    parser.add_argument(
        "--group-a-0050-step-active-max-ma-ratio",
        type=float,
        default=1.05,
        help="Latest Group A overlay: apply the 0050 step limit only when 0050 price <= MA * this ratio.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-window",
        type=int,
        default=60,
        help="Latest Group A overlay: moving-average window for the 0050 brake.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-ratio",
        type=float,
        default=1.0,
        help="Trigger the 0050 brake when price <= MA * ratio.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-max-weight",
        type=float,
        default=0.30,
        help="Latest Group A overlay: max 0050 target weight while the MA brake is active.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-00631l-max-weight",
        type=float,
        default=0.0,
        help="Latest Group A overlay: max 00631L target weight while the MA brake is active.",
    )
    parser.add_argument(
        "--group-a-tdcc-config",
        default=str(DEFAULT_TDCC_CONFIG),
        help="Latest Group A overlay: TDCC crowding config. Use empty string to disable.",
    )
    parser.add_argument(
        "--disable-group-a-tdcc-overlay",
        action="store_true",
        help="Disable the latest Group A TDCC crowding overlay.",
    )
    parser.add_argument(
        "--strategy-replay",
        action="store_true",
        help="Use strategy replay mode instead of the default live-start mapping.",
    )
    parser.add_argument(
        "--retrain-check",
        action="store_true",
        help=(
            "After signal generation, check promotion_gate from the latest "
            "backtest report. If decision is 'retrain_candidate', log a warning "
            "with the rationale. Requires --backtest-report to point to the "
            "backtest JSON. Skips if yfinance is unavailable."
        ),
    )
    parser.add_argument(
        "--backtest-report",
        default=None,
        help="Path to backtest_group_a_plus_overlay.py output JSON for retrain check.",
    )
    return parser.parse_args()


def _build_command(args: argparse.Namespace) -> list[str]:
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
    if args.group_a_0050_max_weight_step is not None:
        cmd.extend(
            [
                "--group-a-0050-max-weight-step",
                f"{float(args.group_a_0050_max_weight_step):.6f}",
            ]
        )
    if args.group_a_0050_step_active_max_ma_ratio is not None:
        cmd.extend(
            [
                "--group-a-0050-step-active-max-ma-ratio",
                f"{float(args.group_a_0050_step_active_max_ma_ratio):.6f}",
            ]
        )
    if args.group_a_0050_ma_brake_window is not None:
        cmd.extend(
            [
                "--group-a-0050-ma-brake-window",
                str(int(args.group_a_0050_ma_brake_window)),
            ]
        )
    cmd.extend(
        [
            "--group-a-0050-ma-brake-ratio",
            f"{float(args.group_a_0050_ma_brake_ratio):.6f}",
        ]
    )
    if args.group_a_0050_ma_brake_max_weight is not None:
        cmd.extend(
            [
                "--group-a-0050-ma-brake-max-weight",
                f"{float(args.group_a_0050_ma_brake_max_weight):.6f}",
            ]
        )
    if args.group_a_0050_ma_brake_00631l_max_weight is not None:
        cmd.extend(
            [
                "--group-a-0050-ma-brake-00631l-max-weight",
                f"{float(args.group_a_0050_ma_brake_00631l_max_weight):.6f}",
            ]
        )
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
    return cmd


def _action_hint(weight_diff: float, delta_shares: int, threshold: float, signal_status: str) -> str:
    if signal_status != "rebalance":
        return "hold"
    if weight_diff >= threshold or delta_shares > 0:
        return "buy"
    if weight_diff <= -threshold or delta_shares < 0:
        return "sell"
    return "hold"


def _rewrite_signal_csv(signal: dict[str, object], csv_path: Path, *, action_threshold: float) -> None:
    prices = {str(k): float(v) for k, v in dict(signal["latest_prices"]).items()}
    current_shares = {str(k): int(v) for k, v in dict(signal["current_shares"]).items()}
    current_weights = {str(k): float(v) for k, v in dict(signal["current_weights"]).items()}
    strategy_weights = {str(k): float(v) for k, v in dict(signal.get("strategy_weights", {})).items()}
    planned_weights = {str(k): float(v) for k, v in dict(signal["planned_target_weights"]).items()}
    target_weights = {str(k): float(v) for k, v in dict(signal["target_weights"]).items()}
    total_value = float(signal["current_total_portfolio_value"])
    status = str(signal["signal_status"])
    rows = []
    target_shares: dict[str, int] = {}
    planned_target_shares: dict[str, int] = {}
    for ticker in target_weights:
        price = float(prices[ticker])
        planned_shares = int(round(total_value * planned_weights.get(ticker, 0.0) / price)) if price > 0 else 0
        shares = int(round(total_value * target_weights[ticker] / price)) if price > 0 else 0
        delta_shares = int(shares - current_shares.get(ticker, 0))
        weight_diff = float(target_weights[ticker] - current_weights.get(ticker, 0.0))
        planned_target_shares[ticker] = planned_shares
        target_shares[ticker] = shares
        rows.append(
            {
                "date": signal["actual_data_date"],
                "ticker": ticker,
                "latest_price": price,
                "current_shares": current_shares.get(ticker, 0),
                "current_weight": current_weights.get(ticker, 0.0),
                "strategy_weight": strategy_weights.get(ticker, 0.0),
                "planned_target_weight": planned_weights.get(ticker, 0.0),
                "target_weight": target_weights[ticker],
                "planned_target_shares": planned_shares,
                "target_shares": shares,
                "delta_shares": delta_shares,
                "weight_diff": weight_diff,
                "action_hint": _action_hint(weight_diff, delta_shares, action_threshold, status),
                "signal_status": status,
            }
        )
    signal["planned_target_shares"] = planned_target_shares
    signal["target_shares"] = target_shares
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _apply_tdcc_overlay_to_signal(signal: dict[str, object], args: argparse.Namespace) -> dict[str, object]:
    if args.disable_group_a_tdcc_overlay or not str(args.group_a_tdcc_config).strip():
        signal["tdcc_overlay"] = {"enabled": False, "reason": "disabled"}
        return signal

    scripts_misc_dir = str(PROJECT_ROOT / "scripts" / "misc")
    if scripts_misc_dir not in sys.path:
        sys.path.insert(0, scripts_misc_dir)
    from run_group_a_tdcc_improved_signal import _build_tdcc_assessment, apply_tdcc_overlay

    config_path = Path(args.group_a_tdcc_config)
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assessment = _build_tdcc_assessment(
        config,
        db_path=PROJECT_ROOT / "FinRL" / "data" / "stock_data.db",
        as_of_date=str(args.as_of_date),
    )
    overlay = apply_tdcc_overlay(signal, assessment, config)
    signal["tdcc_assessment"] = assessment
    signal["tdcc_overlay"] = overlay
    signal["tdcc_config"] = {
        "path": str(config_path),
        "strategy_name": config.get("strategy_name"),
        "status": config.get("status"),
    }
    if overlay.get("changed"):
        signal["signal_status"] = overlay["signal_status"]
        signal["signal_reason"] = f"{signal.get('signal_reason')}; {overlay['signal_reason']}"
        signal["target_weights"] = overlay["target_weights"]
        signal["target_cash_weight"] = overlay["target_cash_weight"]
    return signal


def _extract_output_path(stdout: str, label: str) -> Path:
    match = re.search(rf"^{label}:\s+(.+)$", stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to parse {label} path from generate_dual_group_signal output")
    return Path(match.group(1).strip())


def _retrain_check(backtest_report_path: Path) -> None:
    """Check promotion_gate and warn if retrain is recommended."""
    try:
        report = json.loads(backtest_report_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[retrain-check] Cannot read backtest report: {e}", file=sys.stderr)
        return

    gate = report.get("summary", {}).get("promotion_gate", {})
    decision = str(gate.get("decision") or "")
    rationale = str(gate.get("rationale") or "")

    if decision == "retrain_candidate":
        print(
            f"[RETRAIN] {decision.upper()}: {rationale}",
            file=sys.stderr,
        )
        best = gate.get("best_return_variant", "unknown")
        print(f"[RETRAIN] Best return variant: {best}", file=sys.stderr)
        print(f"[RETRAIN] Recommendation: schedule new training run.", file=sys.stderr)
    elif decision == "promotion_candidate":
        print(f"[RETRAIN] {decision.upper()}: {rationale}", file=sys.stderr)
    else:
        print(f"[retrain-check] promotion_gate={decision} — no action needed.", file=sys.stderr)


def main() -> None:
    args = _parse_args()
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-group-a-combined")
    cmd = _build_command(args)
    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
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

    json_path = _extract_output_path(completed.stdout, "JSON")
    csv_path = _extract_output_path(completed.stdout, "CSV")

    shutil.copy2(json_path, DEFAULT_LATEST_JSON)
    shutil.copy2(csv_path, DEFAULT_LATEST_CSV)

    signal = json.loads(DEFAULT_LATEST_JSON.read_text(encoding="utf-8"))
    signal = _apply_tdcc_overlay_to_signal(signal, args)
    signal["release_name"] = RELEASE_NAME
    signal["release_handoff_md"] = str(RELEASE_HANDOFF.resolve())
    signal["live_mode"] = "strategy_replay" if args.strategy_replay else "live_start"
    signal["result_json"] = str(Path(args.result_json).resolve())
    signal["production_overlay_config"] = {
        "group_a_0050_max_weight_step": args.group_a_0050_max_weight_step,
        "group_a_0050_step_active_max_ma_ratio": args.group_a_0050_step_active_max_ma_ratio,
        "group_a_0050_ma_brake_window": args.group_a_0050_ma_brake_window,
        "group_a_0050_ma_brake_ratio": args.group_a_0050_ma_brake_ratio,
        "group_a_0050_ma_brake_max_weight": args.group_a_0050_ma_brake_max_weight,
        "group_a_0050_ma_brake_00631l_max_weight": args.group_a_0050_ma_brake_00631l_max_weight,
        "group_a_tdcc_overlay_enabled": not args.disable_group_a_tdcc_overlay
        and bool(str(args.group_a_tdcc_config).strip()),
        "group_a_tdcc_config": str(Path(args.group_a_tdcc_config).resolve())
        if str(args.group_a_tdcc_config).strip()
        else None,
    }
    _rewrite_signal_csv(signal, DEFAULT_LATEST_CSV, action_threshold=float(args.action_threshold))
    DEFAULT_LATEST_JSON.write_text(json.dumps(signal, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "bundle": "group_a_combined",
        "release_name": RELEASE_NAME,
        "release_handoff_md": str(RELEASE_HANDOFF.resolve()),
        "description": (
            "Institutional-only Group A PPO mainline with local TWII/0050 regime gate "
            "that can override into defensive templates."
        ),
        "result_json": str(Path(args.result_json).resolve()),
        "live_mode": "strategy_replay" if args.strategy_replay else "live_start",
        "stable_signal_json": str(DEFAULT_LATEST_JSON.resolve()),
        "stable_signal_csv": str(DEFAULT_LATEST_CSV.resolve()),
        "generated_signal_json": str(json_path.resolve()),
        "generated_signal_csv": str(csv_path.resolve()),
        "actual_data_date": signal.get("actual_data_date"),
        "signal_status": signal.get("signal_status"),
        "signal_reason": signal.get("signal_reason"),
        "tdcc_state": (signal.get("tdcc_assessment") or {}).get("state")
        if isinstance(signal.get("tdcc_assessment"), dict)
        else None,
        "tdcc_overlay_changed": (signal.get("tdcc_overlay") or {}).get("changed")
        if isinstance(signal.get("tdcc_overlay"), dict)
        else None,
        "target_shares": signal.get("target_shares"),
    }
    DEFAULT_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.retrain_check and args.backtest_report:
        report_path = Path(args.backtest_report)
        if report_path.is_absolute():
            pass
        else:
            report_path = (PROJECT_ROOT / report_path).resolve()
        _retrain_check(report_path)

    print("=" * 72)
    print("Unified Group A bundle ready")
    print(f"Stable JSON: {DEFAULT_LATEST_JSON}")
    print(f"Stable CSV:  {DEFAULT_LATEST_CSV}")
    print(f"Manifest:    {DEFAULT_MANIFEST}")
    print("=" * 72)


if __name__ == "__main__":
    main()
