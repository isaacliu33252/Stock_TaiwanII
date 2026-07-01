#!/usr/bin/env python3
"""Run the daily NCF refresh, signal, and advisory-panel pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"
DEFAULT_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "0056.TW",
    "00646.TW",
    "00679B.TWO",
    "00713.TW",
    "00751B.TWO",
    "00878.TW",
)


def _result_path(name: str) -> Path:
    return RESULTS_DIR / name


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str], *, dry_run: bool, env_extra: dict[str, str] | None = None, log_fh=None) -> None:
    if log_fh:
        log_fh.write("$ " + " ".join(cmd) + "\n")
        log_fh.flush()
    if dry_run:
        print("$ " + " ".join(cmd))
        return
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-ncf")
    if env_extra:
        env.update(env_extra)
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, env=env,
                   stdout=log_fh, stderr=log_fh)


def _signal_summary(path: Path) -> dict[str, Any]:
    payload = _json_load(path)
    ensemble = payload.get("horizon_ensemble", {})
    freshness = payload.get("data_freshness", {})
    return {
        "ticker": payload.get("ticker"),
        "last_close_date": payload.get("last_close_date"),
        "last_close": payload.get("last_close"),
        "current_regime": payload.get("current_regime"),
        "direction": ensemble.get("direction"),
        "probability_up": ensemble.get("combined_probability_up"),
        "calibrated_probability_up": ensemble.get("calibrated_probability_up"),
        "confidence": ensemble.get("confidence"),
        "weighted_return": ensemble.get("weighted_return"),
        "data_freshness_status": freshness.get("status"),
        "data_sources": freshness.get("sources"),
        "missing_sources": freshness.get("missing_sources"),
        "stale_sources": freshness.get("stale_sources"),
        "sources_ahead_of_ohlcv": freshness.get("sources_ahead_of_ohlcv"),
    }


def build_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    stamp = args.date_stamp
    chip_start = args.chip_start
    chip_end = args.chip_end
    tickers = ",".join(DEFAULT_TICKERS)

    only_refresh = getattr(args, "only_refresh", False)
    commands: dict[str, list[str]] = {}
    if not args.skip_refresh:
        refresh_cmd = [
            sys.executable,
            "refresh_group_data.py",
            "--group",
            "both",
            "--summary-path",
            str(_result_path(f"data_refresh_{stamp}.json")),
        ]
        if args.force_refresh:
            refresh_cmd.append("--force")
        commands["refresh_group_data"] = refresh_cmd
        commands["refresh_taifex"] = [sys.executable, "taifex_futures_data.py", "--refresh-latest"]
        commands["refresh_institutional"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-institutional",
            tickers,
            "--start",
            chip_start,
            "--end",
            chip_end,
        ]
        commands["refresh_margin"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-margin",
            tickers,
            "--start",
            chip_start,
            "--end",
            chip_end,
        ]
        commands["refresh_market_margin"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-market-margin",
            "--start",
            chip_start,
            "--end",
            chip_end,
        ]
        commands["refresh_derivative_institutional"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "derivative_institutional",
            "--futures-ids",
            "TX",
            "--option-ids",
            "TXO",
            "--start",
            chip_start,
            "--end",
            chip_end,
        ]
        if not args.skip_shareholding:
            commands["refresh_shareholding"] = [
                sys.executable,
                "FinRL/data/stock_db.py",
                "--add-shareholding",
            ]

    commands["ohlcv_freshness"] = [
        sys.executable,
        "scripts/misc/check_ohlcv_freshness.py",
        "--target-date",
        args.ohlcv_target_date,
        "--max-db-lag-days",
        str(args.max_ohlcv_lag_days),
        "--output",
        str(_result_path(f"ohlcv_freshness_{stamp}.json")),
    ]
    if args.fail_on_ohlcv_warning:
        commands["ohlcv_freshness"].append("--fail-on-warning")

    if only_refresh:
        return commands

    commands["ncf_00631l"] = [
        sys.executable,
        "scripts/misc/ncf_00631l.py",
        "--train-start",
        args.train_start_00631l,
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_00631l_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--full-panel",
    ]
    commands["ncf_00632r"] = [
        sys.executable,
        "ncf_00632r.py",
        "--train-start",
        args.train_start_00632r,
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_00632r_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
    ]
    if args.no_external_features:
        commands["ncf_00631l"].append("--no-external-features")
        commands["ncf_00632r"].append("--no-external-features")

    commands["advisory_panel"] = [
        sys.executable,
        "scripts/misc/build_ncf_advisory_panel.py",
        "--panel-00631l",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--panel-00632r",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_advisory_panel_latest_{stamp}.csv")),
    ]
    commands["factor_lens"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_factor_lens.py",
        "--output",
        str(_result_path(f"group_a_plus_factor_lens_{stamp}.json")),
    ]
    commands["daily_signal"] = [
        sys.executable,
        "group_a_plus/operations/daily_signal.py",
        "--as-of",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--output",
        str(_result_path(f"group_a_plus_live_signal_v2_{stamp}.json")),
    ]
    return commands


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-stamp", default=today.strftime("%Y%m%d"))
    parser.add_argument("--skip-refresh", action="store_true", help="Only run NCF signals and advisory panel.")
    parser.add_argument("--force-refresh", action="store_true", help="Pass --force to refresh_group_data.py.")
    parser.add_argument("--skip-shareholding", action="store_true", help="Skip TDCC shareholding refresh.")
    parser.add_argument("--chip-start", default=(today - timedelta(days=21)).isoformat())
    parser.add_argument("--chip-end", default=today.isoformat())
    parser.add_argument("--val-start", default="2025-01-02")
    parser.add_argument("--val-end", default="latest")
    parser.add_argument("--ohlcv-target-date", default="auto")
    parser.add_argument("--max-ohlcv-lag-days", type=int, default=3)
    parser.add_argument("--fail-on-ohlcv-warning", action="store_true")
    parser.add_argument("--train-start-00631l", default="2020-01-01")
    parser.add_argument("--train-start-00632r", default="2015-01-01")
    parser.add_argument("--no-external-features", action="store_true")
    parser.add_argument(
        "--refresh-external-cache",
        action="store_true",
        help="Allow NCF scripts to download missing yfinance external features; default is cache-only.",
    )
    parser.add_argument("--only-refresh", action="store_true", help="Only run data refresh steps, skip NCF models.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--skip-commentary", action="store_true", help="Skip LLM commentary generation.")
    parser.add_argument("--commentary-provider", default="auto",
                        choices=["auto", "minimax", "anthropic", "template"],
                        help="Commentary provider (default: auto → minimax → anthropic → template).")
    parser.add_argument("--commentary-api-key", default=None,
                        help="API key for commentary provider (overrides env vars).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    commands = build_commands(args)

    log_path = PROJECT_ROOT / "logs" / "daily.log"
    log_path.parent.mkdir(exist_ok=True)
    total = len(commands)
    with open(log_path, "a", encoding="utf-8") as log_fh:
        for i, (name, cmd) in enumerate(commands.items(), 1):
            pct_start = int((i - 1) / total * 100)
            pct_done  = int(i / total * 100)
            msg_start = f"[{i}/{total}] {name}  ({pct_start}%)"
            msg_done  = f"  ✓ 完成 ({pct_done}%)"
            print(msg_start, flush=True)
            log_fh.write(msg_start + "\n"); log_fh.flush()
            env_extra = {"NCF_EXTERNAL_ALLOW_DOWNLOAD": "1"} if args.refresh_external_cache and name.startswith("ncf_") else None
            _run(cmd, dry_run=args.dry_run, env_extra=env_extra, log_fh=log_fh)
            print(msg_done, flush=True)
            log_fh.write(msg_done + "\n"); log_fh.flush()

    manifest_path = _result_path(f"ncf_daily_pipeline_{args.date_stamp}.json")
    if args.dry_run:
        print(f"\nDry run only. Manifest would be written to: {manifest_path}")
        return

    summary = {
        "date_stamp": args.date_stamp,
        "outputs": {
            "ohlcv_freshness": str(_result_path(f"ohlcv_freshness_{args.date_stamp}.json")),
            "ncf_00631l": str(_result_path(f"ncf_00631l_latest_{args.date_stamp}.json")),
            "ncf_00632r": str(_result_path(f"ncf_00632r_latest_{args.date_stamp}.json")),
            "panel_00631l": str(_result_path(f"ncf_00631l_panel_latest_{args.date_stamp}.csv")),
            "panel_00632r": str(_result_path(f"ncf_00632r_panel_latest_{args.date_stamp}.csv")),
            "advisory_panel": str(_result_path(f"ncf_advisory_panel_latest_{args.date_stamp}.csv")),
            "factor_lens": str(_result_path(f"group_a_plus_factor_lens_{args.date_stamp}.json")),
            "live_signal": str(_result_path(f"group_a_plus_live_signal_v2_{args.date_stamp}.json")),
        },
        "signals": {
            "00631L": _signal_summary(_result_path(f"ncf_00631l_latest_{args.date_stamp}.json")),
            "00632R": _signal_summary(_result_path(f"ncf_00632r_latest_{args.date_stamp}.json")),
        },
    }
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\nNCF daily pipeline complete")
    for ticker, signal in summary["signals"].items():
        print(
            f"  {ticker}: {signal['direction']} "
            f"prob_up={signal['probability_up']} "
            f"freshness={signal['data_freshness_status']} "
            f"date={signal['last_close_date']}"
        )
    print(f"Manifest: {manifest_path}")

    print("\n[env-health]")
    try:
        from group_a_plus.operations.strategy_env import DEFAULT_OUTPUT_PATH, build_strategy_env_health

        env_health = build_strategy_env_health()
        DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(env_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "  "
            f"status={env_health.get('status')} "
            f"missing_files={len(env_health.get('missing_files', []))} "
            f"warnings={len(env_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/strategy_env_health.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Environment health check failed (non-fatal): {exc}")

    print("\n[ops-health]")
    try:
        from group_a_plus.operations.ops_health import DEFAULT_OUTPUT_PATH, build_ops_health

        ops_health = build_ops_health()
        DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(ops_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "  "
            f"status={ops_health.get('status')} "
            f"errors={len(ops_health.get('errors', []))} "
            f"warnings={len(ops_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/ops_health.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Ops health check failed (non-fatal): {exc}")

    # --- LLM commentary (optional) ---
    if not args.skip_commentary:
        print("\n[commentary]")
        try:
            from group_a_plus.integrations.llm_commentary import generate_commentary
            ncf_path = _result_path(f"ncf_00631l_latest_{args.date_stamp}.json")
            commentary = generate_commentary(
                ncf_signal_path=ncf_path,
                provider=args.commentary_provider,
                api_key=args.commentary_api_key,
                signal_date=args.date_stamp[:4] + "-" + args.date_stamp[4:6] + "-" + args.date_stamp[6:],
            )
            mode = commentary.get("mode", "?")
            print(f"  [{mode}] {commentary.get('headline', '')}")
            print(f"  去槓桿: {commentary.get('signal_interpretation', {}).get('deleverage_status', '?')}")
            if "_saved_to" in commentary:
                print(f"  Saved → {commentary['_saved_to']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARNING] Commentary failed (non-fatal): {exc}")

    print("\n[watchlist-news]")
    try:
        from group_a_plus.integrations.watchlist_news import write_watchlist_news_summary

        news_summary = write_watchlist_news_summary(
            signal_date=args.date_stamp[:4] + "-" + args.date_stamp[4:6] + "-" + args.date_stamp[6:]
        )
        print(
            "  "
            f"articles={news_summary.get('article_count', 0)} "
            f"fallback={news_summary.get('fallback_used', False)}"
        )
        print("  Saved → report/group_a_plus/latest/watchlist_news.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Watchlist news summary failed (non-fatal): {exc}")

    print("\n[signal-alignment]")
    try:
        from group_a_plus.integrations.signal_alignment import (
            DEFAULT_LIVE_SIGNAL_PATH,
            DEFAULT_OUTPUT_PATH,
            build_signal_alignment_from_file,
        )

        alignment = build_signal_alignment_from_file(DEFAULT_LIVE_SIGNAL_PATH, output_path=DEFAULT_OUTPUT_PATH)
        print(
            "  "
            f"alignment={alignment.get('alignment')} "
            f"dominant={alignment.get('dominant_direction')} "
            f"penalty={alignment.get('confidence_penalty')}"
        )
        print("  Saved → report/group_a_plus/latest/signal_alignment.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Signal alignment failed (non-fatal): {exc}")

    print("\n[alert-state]")
    try:
        from group_a_plus.operations.alert_state import update_alert_state_from_files

        alert_state = update_alert_state_from_files()
        alert_summary = alert_state.get("summary", {})
        print(
            "  "
            f"emitted={alert_summary.get('emitted_count', 0)} "
            f"suppressed={alert_summary.get('suppressed_count', 0)} "
            f"resolved={alert_summary.get('resolved_count', 0)}"
        )
        print("  Saved → report/group_a_plus/latest/alert_state.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Alert state update failed (non-fatal): {exc}")


if __name__ == "__main__":
    main()
