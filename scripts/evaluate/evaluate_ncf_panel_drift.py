#!/usr/bin/env python3
"""Audit prediction drift between two NCF validation panels.

The NCF panel can change for historical dates when a later run recomputes
global ensemble weights. This tool quantifies that drift without changing any
model or live allocation logic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COLUMNS = (
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "ensemble_prob_up",
    "h20_prob_up",
    "confidence",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "tail_reward_risk_score_h20",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_panel(path: str | Path) -> pd.DataFrame:
    panel = pd.read_csv(_resolve(path), encoding="utf-8-sig")
    if "date" not in panel.columns:
        raise ValueError(f"{path} is missing required 'date' column")
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    return panel.set_index("date").sort_index()


def _available_columns(left: pd.DataFrame, right: pd.DataFrame, requested: list[str] | None) -> list[str]:
    candidates = requested or list(DEFAULT_COLUMNS)
    return [col for col in candidates if col in left.columns and col in right.columns]


def evaluate_panel_drift(
    baseline_panel: str | Path,
    candidate_panel: str | Path,
    *,
    columns: list[str] | None = None,
    focus_dates: list[str] | None = None,
    top_n: int = 20,
) -> tuple[dict[str, Any], pd.DataFrame]:
    baseline = _load_panel(baseline_panel)
    candidate = _load_panel(candidate_panel)
    common_idx = baseline.index.intersection(candidate.index).sort_values()
    if common_idx.empty:
        raise ValueError("panels have no overlapping dates")

    cols = _available_columns(baseline, candidate, columns)
    if not cols:
        raise ValueError("panels have no overlapping requested numeric columns")

    rows: list[dict[str, Any]] = []
    for date in common_idx:
        row: dict[str, Any] = {"date": date}
        abs_values = []
        for col in cols:
            before = pd.to_numeric(pd.Series([baseline.at[date, col]]), errors="coerce").iloc[0]
            after = pd.to_numeric(pd.Series([candidate.at[date, col]]), errors="coerce").iloc[0]
            delta = after - before if pd.notna(before) and pd.notna(after) else float("nan")
            row[f"{col}_baseline"] = float(before) if pd.notna(before) else None
            row[f"{col}_candidate"] = float(after) if pd.notna(after) else None
            row[f"{col}_delta"] = float(delta) if pd.notna(delta) else None
            if pd.notna(delta):
                abs_values.append(abs(float(delta)))
        row["max_abs_delta"] = max(abs_values) if abs_values else None
        rows.append(row)

    drift = pd.DataFrame(rows)
    drift = drift.sort_values("max_abs_delta", ascending=False, na_position="last").reset_index(drop=True)

    column_summary: dict[str, Any] = {}
    for col in cols:
        delta = pd.to_numeric(drift[f"{col}_delta"], errors="coerce").dropna()
        if delta.empty:
            continue
        max_abs_idx = delta.abs().idxmax()
        column_summary[col] = {
            "mean_abs_delta": float(delta.abs().mean()),
            "median_abs_delta": float(delta.abs().median()),
            "max_abs_delta": float(delta.abs().max()),
            "max_abs_delta_date": str(drift.loc[max_abs_idx, "date"]),
            "signed_delta_at_max_abs": float(drift.loc[max_abs_idx, f"{col}_delta"]),
        }

    focus = []
    for date in focus_dates or []:
        normalized = pd.Timestamp(date).strftime("%Y-%m-%d")
        match = drift[drift["date"] == normalized]
        if not match.empty:
            focus.append(match.iloc[0].to_dict())

    summary = {
        "report_type": "ncf_panel_drift_audit",
        "baseline_panel": str(_resolve(baseline_panel)),
        "candidate_panel": str(_resolve(candidate_panel)),
        "overlap_start": str(common_idx.min()),
        "overlap_end": str(common_idx.max()),
        "overlap_rows": int(len(common_idx)),
        "baseline_rows": int(len(baseline)),
        "candidate_rows": int(len(candidate)),
        "columns": cols,
        "column_summary": column_summary,
        "top_drift_rows": drift.head(int(top_n)).to_dict(orient="records"),
        "focus_rows": focus,
    }
    return summary, drift


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-panel", required=True)
    parser.add_argument("--candidate-panel", required=True)
    parser.add_argument("--columns", nargs="*", default=None)
    parser.add_argument("--focus-date", action="append", default=[])
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output", default="results/ncf_panel_drift_audit_latest.json")
    parser.add_argument("--csv-output", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary, drift = evaluate_panel_drift(
        args.baseline_panel,
        args.candidate_panel,
        columns=args.columns,
        focus_dates=args.focus_date,
        top_n=args.top_n,
    )

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.csv_output:
        csv_output = _resolve(args.csv_output)
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        drift.to_csv(csv_output, index=False, encoding="utf-8-sig")
        print(f"CSV:  {csv_output}")
    print(f"JSON: {output}")
    print(
        "Max drift: "
        + ", ".join(
            f"{col}={info['max_abs_delta']:.6f}@{info['max_abs_delta_date']}"
            for col, info in summary["column_summary"].items()
        )
    )


if __name__ == "__main__":
    main()
