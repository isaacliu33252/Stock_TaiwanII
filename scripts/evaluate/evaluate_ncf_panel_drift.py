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

# Probability-of-event columns paired with the resolved binary/threshold
# label that scores them. Used only when --outcome-aware is passed -- lets a
# large baseline/candidate delta be checked against which side actually was
# closer to the realized outcome, rather than treated as pure risk by
# magnitude alone. `confidence` has no direct pairing (it is |prob_magnitude|,
# not itself a probability of a labeled event) and is intentionally excluded.
DEFAULT_OUTCOME_PAIRS = {
    "prob_up_h1": "actual_up_h1",
    "prob_up_h5": "actual_up_h5",
    "prob_up_h20": "actual_up_h20",
    "h20_prob_up": "actual_up_h20",
    "ensemble_prob_up": "actual_up_h20",
    "prob_fwd_mdd_gt5_h20": "actual_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20": "actual_fwd_gain_gt5_h20",
}


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


def _resolve_outcome_column(baseline: pd.DataFrame, candidate: pd.DataFrame, actual_col: str) -> pd.Series | None:
    """Ground truth for outcome-awareness -- prefer the candidate panel
    (usually the more recently backfilled one), fall back to baseline."""
    if actual_col in candidate.columns:
        return candidate[actual_col]
    if actual_col in baseline.columns:
        return baseline[actual_col]
    return None


def evaluate_panel_drift(
    baseline_panel: str | Path,
    candidate_panel: str | Path,
    *,
    columns: list[str] | None = None,
    focus_dates: list[str] | None = None,
    top_n: int = 20,
    window_start: str | None = None,
    outcome_aware: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame]:
    baseline = _load_panel(baseline_panel)
    candidate = _load_panel(candidate_panel)
    common_idx = baseline.index.intersection(candidate.index).sort_values()
    if common_idx.empty:
        raise ValueError("panels have no overlapping dates")
    full_overlap_start = str(common_idx.min())
    full_overlap_end = str(common_idx.max())
    full_overlap_rows = int(len(common_idx))
    if window_start is not None:
        cutoff = pd.Timestamp(window_start).strftime("%Y-%m-%d")
        common_idx = common_idx[common_idx >= cutoff]
        if common_idx.empty:
            raise ValueError(f"no overlapping dates on or after --window-start {cutoff}")

    cols = _available_columns(baseline, candidate, columns)
    if not cols:
        raise ValueError("panels have no overlapping requested numeric columns")

    outcome_series: dict[str, pd.Series] = {}
    if outcome_aware:
        for col in cols:
            actual_col = DEFAULT_OUTCOME_PAIRS.get(col)
            if actual_col is None:
                continue
            actual = _resolve_outcome_column(baseline, candidate, actual_col)
            if actual is not None:
                outcome_series[col] = actual

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
            if col in outcome_series:
                actual_val = pd.to_numeric(
                    pd.Series([outcome_series[col].get(date, float("nan"))]), errors="coerce"
                ).iloc[0]
                favor = None
                if pd.notna(actual_val) and pd.notna(before) and pd.notna(after):
                    baseline_err = (float(before) - float(actual_val)) ** 2
                    candidate_err = (float(after) - float(actual_val)) ** 2
                    if candidate_err < baseline_err:
                        favor = "candidate"
                    elif baseline_err < candidate_err:
                        favor = "baseline"
                    else:
                        favor = "tie"
                row[f"{col}_actual"] = float(actual_val) if pd.notna(actual_val) else None
                row[f"{col}_outcome_favor"] = favor
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

        if col in outcome_series:
            favor_col = f"{col}_outcome_favor"
            favor = drift[favor_col]
            resolved_mask = favor.notna()
            candidate_favorable_mask = favor == "candidate"
            # "Risk-relevant" excludes only rows where the candidate (with
            # the change being audited) was demonstrably *closer* to the
            # realized outcome than the baseline -- those deltas are
            # evidence the change helped, not risk. Unresolved rows (no
            # label yet) are conservatively kept in the risk-relevant pool.
            risk_relevant_mask = ~candidate_favorable_mask.fillna(False)
            risk_relevant_delta = delta[risk_relevant_mask.reindex(delta.index, fill_value=True)]
            outcome_summary: dict[str, Any] = {
                "actual_column": DEFAULT_OUTCOME_PAIRS[col],
                "resolved_rows": int(resolved_mask.sum()),
                "candidate_favorable_rows": int((favor == "candidate").sum()),
                "baseline_favorable_rows": int((favor == "baseline").sum()),
                "tie_rows": int((favor == "tie").sum()),
            }
            if not risk_relevant_delta.empty:
                risk_idx = risk_relevant_delta.abs().idxmax()
                outcome_summary["risk_relevant_max_abs_delta"] = float(risk_relevant_delta.abs().max())
                outcome_summary["risk_relevant_max_abs_delta_date"] = str(drift.loc[risk_idx, "date"])
            else:
                outcome_summary["risk_relevant_max_abs_delta"] = None
                outcome_summary["risk_relevant_max_abs_delta_date"] = None
            column_summary[col]["outcome_aware"] = outcome_summary

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
        "window_start": window_start,
        "full_overlap_start": full_overlap_start,
        "full_overlap_end": full_overlap_end,
        "full_overlap_rows": full_overlap_rows,
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
    parser.add_argument(
        "--window-start",
        default=None,
        help=(
            "Restrict max_abs_delta/column_summary to dates on or after this "
            "ISO date (e.g. a trailing window). Default: full overlap "
            "history, unchanged from prior behavior. Use this for any "
            "'stability' check that should be able to converge over time -- "
            "a full-history max can never be superseded by a future "
            "observation once its worst date is in the past."
        ),
    )
    parser.add_argument(
        "--outcome-aware",
        action="store_true",
        help=(
            "For probability-of-event columns with a resolved label "
            "(h20_prob_up/prob_up_h1/prob_up_h5/prob_up_h20/ensemble_prob_up/ "
            "prob_fwd_mdd_gt5_h20/prob_fwd_gain_gt5_h20), also report a "
            "'risk_relevant_max_abs_delta' that excludes dates where the "
            "candidate panel was demonstrably closer to the realized "
            "outcome than the baseline -- so a large delta the candidate "
            "got *right* isn't counted the same as one it got wrong. "
            "Default off (unchanged prior behavior); does not affect "
            "'confidence' (no direct probability-of-event pairing)."
        ),
    )
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
        window_start=args.window_start,
        outcome_aware=args.outcome_aware,
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
    if args.outcome_aware:
        risk_lines = []
        for col, info in summary["column_summary"].items():
            oa = info.get("outcome_aware")
            if not oa or oa["risk_relevant_max_abs_delta"] is None:
                continue
            risk_lines.append(
                f"{col}={oa['risk_relevant_max_abs_delta']:.6f}@{oa['risk_relevant_max_abs_delta_date']} "
                f"(candidate_favorable={oa['candidate_favorable_rows']}/{oa['resolved_rows']} resolved)"
            )
        if risk_lines:
            print("Risk-relevant drift (excludes candidate-favorable dates): " + ", ".join(risk_lines))


if __name__ == "__main__":
    main()
