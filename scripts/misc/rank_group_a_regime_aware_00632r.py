#!/usr/bin/env python3
"""Rank Group A 00632R variants across 2024-2026 and 2008 proxy evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RECENT = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604.csv"
DEFAULT_STRESS = PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_inverse_sweep_20070701_20101231.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_regime_aware_00632r_dual_ranking_20260605.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recent-csv", default=str(DEFAULT_RECENT))
    parser.add_argument("--stress-csv", default=str(DEFAULT_STRESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _norm_good(series: pd.Series) -> pd.Series:
    low = float(series.min())
    high = float(series.max())
    if abs(high - low) < 1e-12:
        return pd.Series(0.5, index=series.index)
    return (series - low) / (high - low)


def _norm_less_negative_drawdown(series: pd.Series) -> pd.Series:
    return _norm_good(series)


def main() -> None:
    args = _parse_args()
    recent_path = _resolve(args.recent_csv)
    stress_path = _resolve(args.stress_csv)
    output = _resolve(args.output)

    recent = pd.read_csv(recent_path)
    stress = pd.read_csv(stress_path)
    recent_baseline = recent.loc[recent["variant"] == "baseline_destination_primary"].iloc[0]
    stress_baseline = stress.loc[stress["variant"] == "baseline_payload"].iloc[0]

    candidates: list[dict[str, Any]] = [
        {
            "candidate": "current_baseline",
            "recent_variant": "baseline_destination_primary",
            "stress_variant": "baseline_payload",
            "implementation": "destination_primary only",
            "note": "Most conservative current Group A candidate.",
        },
        {
            "candidate": "balanced_hold10",
            "recent_variant": "hold_limit_00632r_10d_to_0050",
            "stress_variant": "baseline_payload",
            "implementation": "post-target 00632R hold <= 10 days, release to 0050",
            "note": "Recent replay improved final and Sharpe with unchanged MDD; 2008 uses baseline hedge allowance.",
        },
        {
            "candidate": "aggressive_disable_inverse",
            "recent_variant": "disable_00632r_to_0050",
            "stress_variant": "inverse_cap_0_to_0050",
            "implementation": "disable 00632R and release to 0050",
            "note": "Best recent return but failed 2008 proxy stress.",
        },
        {
            "candidate": "cap10_inverse",
            "recent_variant": "cap_00632r_10_to_0050",
            "stress_variant": "inverse_cap_010_to_0050",
            "implementation": "00632R cap 10%, release excess to 0050",
            "note": "Static cap compromise.",
        },
        {
            "candidate": "cap05_inverse",
            "recent_variant": "cap_00632r_05_to_0050",
            "stress_variant": "inverse_cap_005_to_0050",
            "implementation": "00632R cap 5%, release excess to 0050",
            "note": "More aggressive static cap.",
        },
        {
            "candidate": "conditional_below_ma60",
            "recent_variant": "conditional_00632r_below_ma60_to_0050",
            "stress_variant": "baseline_payload",
            "implementation": "allow 00632R only when 0050 was below MA60, release otherwise to 0050",
            "note": "Recent MDD improvement with little final gain; stress assumed baseline allowance.",
        },
        {
            "candidate": "conditional_below_ma60_with_dca",
            "recent_variant": "conditional_00632r_below_ma60_to_0050_dca_double_below_ma60",
            "stress_variant": "baseline_payload",
            "implementation": "conditional below MA60 plus DCA double below MA60",
            "note": "Best recent MDD, but DCA contribution is higher.",
        },
    ]

    rows: list[dict[str, Any]] = []
    for item in candidates:
        r = recent.loc[recent["variant"] == item["recent_variant"]].iloc[0]
        s = stress.loc[stress["variant"] == item["stress_variant"]].iloc[0]
        row = {
            **item,
            "recent_final": float(r["final_value"]),
            "recent_sharpe": float(r["sharpe_ratio"]),
            "recent_mdd": float(r["max_drawdown"]),
            "recent_contribution_return": float(r["contribution_return"]),
            "recent_delta_final": float(r["final_value"] - recent_baseline["final_value"]),
            "recent_delta_sharpe": float(r["sharpe_ratio"] - recent_baseline["sharpe_ratio"]),
            "recent_delta_mdd": float(r["max_drawdown"] - recent_baseline["max_drawdown"]),
            "recent_dca": float(r["dca_total_contributions"]),
            "stress_final": float(s["final_value"]),
            "stress_sharpe": float(s["sharpe"]),
            "stress_mdd": float(s["max_drawdown"]),
            "stress_contribution_return": float(s["contribution_return"]),
            "stress_delta_final": float(s["final_value"] - stress_baseline["final_value"]),
            "stress_delta_sharpe": float(s["sharpe"] - stress_baseline["sharpe"]),
            "stress_delta_mdd": float(s["max_drawdown"] - stress_baseline["max_drawdown"]),
        }
        rows.append(row)

    frame = pd.DataFrame(rows)
    frame["recent_score"] = (
        0.40 * _norm_good(frame["recent_contribution_return"])
        + 0.35 * _norm_good(frame["recent_sharpe"])
        + 0.25 * _norm_less_negative_drawdown(frame["recent_mdd"])
    )
    frame["stress_score"] = (
        0.40 * _norm_good(frame["stress_contribution_return"])
        + 0.35 * _norm_good(frame["stress_sharpe"])
        + 0.25 * _norm_less_negative_drawdown(frame["stress_mdd"])
    )
    frame["penalty"] = 0.0
    frame.loc[frame["stress_delta_final"] < -50_000, "penalty"] += 0.25
    frame.loc[frame["recent_mdd"] < recent_baseline["max_drawdown"] - 0.01, "penalty"] += 0.10
    frame.loc[frame["recent_dca"] > recent_baseline["dca_total_contributions"], "penalty"] += 0.05
    frame["dual_score"] = 0.58 * frame["recent_score"] + 0.42 * frame["stress_score"] - frame["penalty"]
    frame = frame.sort_values("dual_score", ascending=False)

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    report = {
        "experiment": "group_a_regime_aware_00632r_dual_ranking",
        "method_note": (
            "Ranks already-run recent 2024-2026 replay variants and 2008 TWII proxy stress variants. "
            "Stress mapping for hold/conditional variants uses baseline 2008 hedge allowance unless a direct cap variant exists."
        ),
        "sources": {"recent_csv": str(recent_path.resolve()), "stress_csv": str(stress_path.resolve())},
        "baseline": {
            "recent_variant": "baseline_destination_primary",
            "stress_variant": "baseline_payload",
            "recent_final": float(recent_baseline["final_value"]),
            "recent_sharpe": float(recent_baseline["sharpe_ratio"]),
            "recent_mdd": float(recent_baseline["max_drawdown"]),
            "stress_final": float(stress_baseline["final_value"]),
            "stress_sharpe": float(stress_baseline["sharpe"]),
            "stress_mdd": float(stress_baseline["max_drawdown"]),
        },
        "ranking": frame.to_dict(orient="records"),
        "best": frame.iloc[0].to_dict(),
        "outputs": {"json": str(output), "csv": str(csv_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(frame[["candidate", "dual_score", "recent_final", "recent_sharpe", "recent_mdd", "stress_final", "stress_sharpe", "stress_mdd", "penalty"]].to_string(index=False))


if __name__ == "__main__":
    main()
