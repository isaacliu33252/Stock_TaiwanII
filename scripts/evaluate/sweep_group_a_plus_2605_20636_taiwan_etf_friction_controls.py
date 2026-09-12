#!/usr/bin/env python3
"""Friction-control sweep for the 2605.20636 Taiwan ETF sensitivity.

Research-only. Tests whether wider no-trade bands or slower tilt updates can
repair the failed A21.19/2605.20636 Taiwan ETF endpoint result.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_a2119_continuous_defensive_tilt_shadow import evaluate

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_taiwan_etf_friction_controls.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_20636_taiwan_etf_friction_controls/history"

BEST_ENDPOINT = {"0050.TW": 0.50, "00631L.TW": 0.10, "cash": 0.40}
WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("full_available", "2017-01-03", "2026-08-28"),
    ("covid_2020", "2020-01-02", "2020-12-31"),
    ("rate_hike_2022", "2022-01-03", "2022-12-30"),
    ("recent_2024_2026", "2024-01-02", "2026-08-28"),
)
NO_TRADE_BANDS = (0.005, 0.02, 0.05, 0.10)
TILT_UPDATE_FREQ_DAYS = (1, 5, 10)


def _score(row: dict[str, Any]) -> dict[str, Any]:
    deltas = row["metric_deltas"]
    cont_exec = row["continuous_execution"]
    base_exec = row["baseline_execution"]
    initial_value = float(row.get("parameters", {}).get("initial_value", 1_000_000.0))
    cont_turnover = float(cont_exec.get("turnover", cont_exec.get("turnover_value", 0.0) / initial_value))
    base_turnover = float(base_exec.get("turnover", base_exec.get("turnover_value", 0.0) / initial_value))
    return {
        "window": row["window_label"],
        "no_trade_band": row["no_trade_band"],
        "tilt_update_freq_days": row["tilt_update_freq_days"],
        "delta_final_value": float(deltas["final_value"]),
        "delta_annual_return": float(deltas["annual_return"]),
        "delta_sharpe_ratio": float(deltas["sharpe_ratio"]),
        "delta_max_drawdown": float(deltas["max_drawdown"]),
        "turnover_delta": cont_turnover - base_turnover,
        "rebalance_count_delta": int(cont_exec.get("rebalance_count", 0)) - int(base_exec.get("rebalance_count", 0)),
        "triple_pass": (
            float(deltas["final_value"]) > 0.0
            and float(deltas["sharpe_ratio"]) > 0.0
            and float(deltas["max_drawdown"]) >= 0.0
        ),
    }


def build_sweep(
    *,
    db_path: Path = DB_PATH,
    initial_value: float = 1_000_000.0,
    warmup_days: int = 756,
    cost_multiplier: float = 1.0,
    windows: tuple[tuple[str, str, str], ...] = WINDOWS,
    no_trade_bands: tuple[float, ...] = NO_TRADE_BANDS,
    tilt_update_freq_days: tuple[int, ...] = TILT_UPDATE_FREQ_DAYS,
) -> dict[str, Any]:
    raw_rows: list[dict[str, Any]] = []
    scored_rows: list[dict[str, Any]] = []
    for label, start, end in windows:
        for band in no_trade_bands:
            for freq in tilt_update_freq_days:
                result = evaluate(
                    start=start,
                    end=end,
                    initial_value=initial_value,
                    db_path=db_path,
                    no_trade_band=band,
                    warmup_days=warmup_days,
                    cost_multiplier=cost_multiplier,
                    tilt_update_freq_days=freq,
                    defensive_endpoint=BEST_ENDPOINT,
                    defensive_endpoint_name="0050_00631l_cash",
                )
                result["window_label"] = label
                raw_rows.append(result)
                scored_rows.append(_score(result))

    combo_summary: dict[str, dict[str, Any]] = {}
    for band in no_trade_bands:
        for freq in tilt_update_freq_days:
            key = f"band{band:g}_freq{freq}"
            subset = [
                row for row in scored_rows
                if row["no_trade_band"] == band and row["tilt_update_freq_days"] == freq
            ]
            combo_summary[key] = {
                "no_trade_band": band,
                "tilt_update_freq_days": freq,
                "windows": len(subset),
                "triple_pass_windows": sum(1 for row in subset if row["triple_pass"]),
                "avg_delta_final_value": sum(row["delta_final_value"] for row in subset) / len(subset),
                "avg_delta_sharpe_ratio": sum(row["delta_sharpe_ratio"] for row in subset) / len(subset),
                "min_delta_max_drawdown": min(row["delta_max_drawdown"] for row in subset),
                "avg_turnover_delta": sum(row["turnover_delta"] for row in subset) / len(subset),
            }

    best_combo = max(
        combo_summary,
        key=lambda key: (
            combo_summary[key]["triple_pass_windows"],
            combo_summary[key]["avg_delta_final_value"],
            combo_summary[key]["avg_delta_sharpe_ratio"],
            -combo_summary[key]["avg_turnover_delta"],
        ),
    )
    best = combo_summary[best_combo]
    best_combo_window_rows = [
        row for row in scored_rows
        if row["no_trade_band"] == best["no_trade_band"]
        and row["tilt_update_freq_days"] == best["tilt_update_freq_days"]
    ]
    positive_final_windows = [
        row["window"] for row in best_combo_window_rows if row["delta_final_value"] > 0.0
    ]
    negative_final_windows = [
        row["window"] for row in best_combo_window_rows if row["delta_final_value"] <= 0.0
    ]
    negative_sharpe_windows = [
        row["window"] for row in best_combo_window_rows if row["delta_sharpe_ratio"] <= 0.0
    ]
    worse_drawdown_windows = [
        row["window"] for row in best_combo_window_rows if row["delta_max_drawdown"] < 0.0
    ]
    promote = (
        best["triple_pass_windows"] == len(windows)
        and best["avg_delta_final_value"] > 0.0
        and best["avg_delta_sharpe_ratio"] > 0.0
        and best["avg_turnover_delta"] <= 0.0
        and best["min_delta_max_drawdown"] >= 0.0
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_20636_taiwan_etf_friction_controls",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "promotable" if promote else "blocked_for_live_promotion",
        "research_only": True,
        "production_effect": "none",
        "source_paper": "2605.20636v2",
        "endpoint": "0050_00631l_cash",
        "endpoint_weights": BEST_ENDPOINT,
        "parameters": {
            "initial_value": initial_value,
            "warmup_days": warmup_days,
            "cost_multiplier": cost_multiplier,
            "no_trade_bands": list(no_trade_bands),
            "tilt_update_freq_days": list(tilt_update_freq_days),
        },
        "windows": [{"label": label, "start": start, "end": end} for label, start, end in windows],
        "combo_summary": combo_summary,
        "best_combo": best_combo,
        "best_combo_window_rows": best_combo_window_rows,
        "failure_diagnosis": {
            "positive_final_value_windows": positive_final_windows,
            "negative_final_value_windows": negative_final_windows,
            "negative_sharpe_windows": negative_sharpe_windows,
            "worse_drawdown_windows": worse_drawdown_windows,
            "primary_reason": (
                "Best combo's average final-value gain is concentrated in the recent 2024-2026 window; "
                "full-history/COVID/2022 final-value deltas remain negative and Sharpe deltas are negative "
                "in every best-combo window."
            ),
        },
        "scored_rows": scored_rows,
        "decision": {
            "friction_controls_repair_signal": promote,
            "promote_to_live": promote,
            "target_weight_change_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "raw_rows": raw_rows,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 2605.20636 Taiwan ETF Friction Controls",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: `{payload['status']}`",
        f"Endpoint: `{payload['endpoint']}`",
        "",
        "## Decision",
        "",
        f"- Friction controls repair signal: `{payload['decision']['friction_controls_repair_signal']}`",
        f"- Promote to live: `{payload['decision']['promote_to_live']}`",
        "- Production effect: `none`",
        "",
        "## Combo Summary",
        "",
        "| Combo | Triple-pass windows | Avg final value delta | Avg Sharpe delta | Min MaxDD delta | Avg turnover delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for combo, summary in payload["combo_summary"].items():
        lines.append(
            "| {combo} | {tp}/{windows} | {dfv:.2f} | {dsh:.6f} | {dmdd:.6f} | {dto:.6f} |".format(
                combo=combo,
                tp=summary["triple_pass_windows"],
                windows=summary["windows"],
                dfv=summary["avg_delta_final_value"],
                dsh=summary["avg_delta_sharpe_ratio"],
                dmdd=summary["min_delta_max_drawdown"],
                dto=summary["avg_turnover_delta"],
            )
        )
    best_combo = payload["best_combo"]
    lines.extend(
        [
            "",
            f"Best combo: `{best_combo}`",
            "",
            "## Best Combo Window Rows",
            "",
            "| Window | Final value delta | Annual return delta | Sharpe delta | MaxDD delta | Turnover delta | Triple pass |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    best = payload["combo_summary"][best_combo]
    for row in payload["scored_rows"]:
        if (
            row["no_trade_band"] == best["no_trade_band"]
            and row["tilt_update_freq_days"] == best["tilt_update_freq_days"]
        ):
            lines.append(
                "| {window} | {dfv:.2f} | {dar:.6f} | {dsh:.6f} | {dmdd:.6f} | {dto:.6f} | `{tp}` |".format(
                    window=row["window"],
                    dfv=row["delta_final_value"],
                    dar=row["delta_annual_return"],
                    dsh=row["delta_sharpe_ratio"],
                    dmdd=row["delta_max_drawdown"],
                    dto=row["turnover_delta"],
                    tp=row["triple_pass"],
                )
            )
    diagnosis = payload.get("failure_diagnosis") or {}
    if diagnosis:
        lines.extend(
            [
                "",
                "## Failure Diagnosis",
                "",
                f"- Positive final-value windows: `{diagnosis.get('positive_final_value_windows')}`",
                f"- Negative final-value windows: `{diagnosis.get('negative_final_value_windows')}`",
                f"- Negative Sharpe windows: `{diagnosis.get('negative_sharpe_windows')}`",
                f"- Worse drawdown windows: `{diagnosis.get('worse_drawdown_windows')}`",
                f"- Primary reason: {diagnosis.get('primary_reason')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (history_dir / f"2605_20636_taiwan_etf_friction_controls_{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--warmup-days", type=int, default=756)
    parser.add_argument("--cost-multiplier", type=float, default=1.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_sweep(
        db_path=Path(args.db),
        initial_value=args.initial_value,
        warmup_days=args.warmup_days,
        cost_multiplier=args.cost_multiplier,
    )
    write_outputs(
        payload,
        Path(args.output),
        Path(args.output_md),
        None if args.no_history else Path(args.history_dir),
    )
    print(f"Output: {Path(args.output).resolve()}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "best_combo": payload["best_combo"],
                "best_summary": payload["combo_summary"][payload["best_combo"]],
                "promote_to_live": payload["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
