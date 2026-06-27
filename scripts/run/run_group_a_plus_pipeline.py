#!/usr/bin/env python3
"""依固定順序執行 GroupA+ A20 pipeline，避免 latest pointer 污染。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def _assert_pointer(pointer_path: str, *, profile: str, actual_data_date: str | None = None) -> dict[str, Any]:
    pointer = _load(pointer_path)
    if pointer.get("profile") and pointer["profile"] != profile:
        raise RuntimeError(f"{pointer_path} profile 不一致：{pointer['profile']} != {profile}")
    json_path = pointer.get("json")
    if json_path:
        payload = _load(json_path)
        if payload.get("profile") and payload["profile"] != profile:
            raise RuntimeError(f"{json_path} profile 不一致：{payload['profile']} != {profile}")
        signal = payload.get("signal") or {}
        report_date = signal.get("actual_data_date") or payload.get("actual_data_date")
        if actual_data_date and report_date and report_date != actual_data_date:
            raise RuntimeError(f"{json_path} actual_data_date 不一致：{report_date} != {actual_data_date}")
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-json", default="results/signal_group_a_20260617_230855.json")
    parser.add_argument("--config", default="group_a_plus_config.json")
    parser.add_argument("--total-assets", type=float, default=None)
    parser.add_argument("--current-00679b-shares", type=int, default=None)
    parser.add_argument("--check-date", default="2026-06-18")
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-17")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--target-total-assets", type=float, default=1_000_000.0)
    parser.add_argument("--output-prefix", default="results/group_a_plus_final_signal_a20_pipeline")
    args = parser.parse_args()

    signal = _load(args.signal_json)
    profile = str(_load(args.config).get("recommended_profile", {}).get("name") or _load(args.config).get("name"))
    actual_data_date = str(signal.get("actual_data_date") or signal.get("requested_as_of_date") or "")
    total_assets = float(args.total_assets or signal.get("current_total_portfolio_value") or signal.get("total_assets") or 0.0)
    current_00679b_shares = int(
        args.current_00679b_shares
        if args.current_00679b_shares is not None
        else (signal.get("current_shares") or {}).get("00679B.TWO", 0)
    )
    if not total_assets:
        raise RuntimeError("無法從 signal 推得 total_assets，請手動指定 --total-assets")

    final_prefix = f"{args.output_prefix}_{actual_data_date.replace('-', '')}"

    _run([
        sys.executable,
        "group_a_00679b_continuous_shadow.py",
        "--signal-json",
        args.signal_json,
        "--group-a-plus-config",
        args.config,
        "--total-assets",
        str(total_assets),
        "--current-00679b-shares",
        str(current_00679b_shares),
        "--dynamic-overlay",
        "--min-trade-value",
        "0",
        "--output-prefix",
        final_prefix,
    ])

    # 讓 baseline generator 自動選最新 actual_data_date 的 Group A 與 GroupA+ signal。
    _run([sys.executable, "set_group_a_plus_formal_baseline.py"])
    baseline = _load("GROUP_A_PLUS_CURRENT_BASELINE.json")
    if baseline.get("profile") != profile:
        raise RuntimeError(f"baseline profile 不一致：{baseline.get('profile')} != {profile}")
    if baseline.get("latest_group_a_signal") != args.signal_json:
        raise RuntimeError(f"baseline latest_group_a_signal 未指向本次 signal：{baseline.get('latest_group_a_signal')}")
    if str((baseline.get("group_a_plus_final_signal") or {}).get("actual_data_date")) != actual_data_date:
        raise RuntimeError("baseline GroupA+ final signal 日期不一致")

    _run([
        sys.executable,
        "check_group_a_plus_daily_status.py",
        "--check-date",
        args.check_date,
        "--max-business-stale-days",
        "1",
    ])
    _assert_pointer("report/group_a_plus/latest/daily_status.json", profile=profile, actual_data_date=actual_data_date)

    # compare 先用 baseline final signal 產生，decision 後再重跑一次，讓 review 讀到 policy-adjusted compare。
    _run([sys.executable, "generate_group_a_strategy_compare_html.py", "--latest-signal", baseline["latest_group_a_plus_final_signal"]])
    _run([sys.executable, "group_a_plus_review_pipeline.py"])
    _assert_pointer("report/group_a_plus/latest/review.json", profile=profile)

    _run([
        sys.executable,
        "group_a_plus_decision_policy.py",
        "--target-total-assets",
        str(args.target_total_assets),
    ])
    _assert_pointer("report/group_a_plus/latest/decision.json", profile=profile)

    _run([sys.executable, "generate_group_a_strategy_compare_html.py"])
    _run([sys.executable, "group_a_plus_review_pipeline.py"])
    review = _assert_pointer("report/group_a_plus/latest/review.json", profile=profile)
    review_payload = _load(review["json"])

    _run([
        sys.executable,
        "group_a_plus_decision_policy.py",
        "--target-total-assets",
        str(args.target_total_assets),
    ])
    decision = _assert_pointer("report/group_a_plus/latest/decision.json", profile=profile)

    _run([
        sys.executable,
        "backtest_group_a_plus_policy_signal.py",
        "--start",
        args.start,
        "--end",
        args.end,
        "--initial-value",
        str(args.initial_value),
        "--output-prefix",
        "results/group_a_plus_policy_signal_backtest_a20_pipeline",
    ])
    _run([
        sys.executable,
        "backtest_group_a_plus_switch_policy.py",
        "--start",
        args.start,
        "--end",
        args.end,
        "--initial-value",
        str(args.initial_value),
        "--output-prefix",
        "results/group_a_plus_switch_policy_backtest_a20_pipeline",
    ])

    decision_payload = _load(decision["json"])
    print("\n完成 GroupA+ pipeline")
    print(f"profile: {profile}")
    print(f"actual_data_date: {actual_data_date}")
    print(f"review decision: {review_payload.get('vote', {}).get('decision')}")
    print(f"policy decision: {decision_payload.get('decision')}")
    print(f"allowed_for_execution: {decision_payload.get('allowed_for_execution')}")
    print(f"signal_json: {decision.get('signal_json')}")


if __name__ == "__main__":
    main()
