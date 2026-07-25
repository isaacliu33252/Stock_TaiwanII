#!/usr/bin/env python3
"""Parameter sweep for heterogeneous volatility-regime shadow signals.

Research-only. This scans transparent threshold variants for the proxy built
from arXiv 2603.16035 ideas. It must not be used as a live allocation rule.
"""

from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from evaluate_heterogeneous_vol_regime_shadow import (
    DB_PATH,
    _add_forward_labels,
    _confusion,
    _load_source_panel,
    _source_diagnostics,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_param_sweep_20250102_20260717.json"


def _parse_int_grid(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_grid(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _score_candidate(row: dict[str, Any], *, base_event_rate: float | None) -> float:
    precision = row.get("h10_precision")
    recall = row.get("h10_recall")
    fpr = row.get("h10_fpr")
    active_days = int(row.get("active_days") or 0)
    if precision is None or recall is None or fpr is None or active_days < 20:
        return -1.0
    lift = precision - (base_event_rate or 0.0)
    return float((0.42 * precision) + (0.20 * recall) + (0.28 * (1.0 - fpr)) + (0.10 * lift))


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series, *, base_event_rate: float | None) -> dict[str, Any]:
    pred = signal.reindex(frame.index).fillna(False).astype(bool)
    confusion = _confusion(pred, frame["no_add_label_h10"])
    active = int(pred.sum())
    return {
        "active_days": active,
        "latest_active": bool(pred.iloc[-1]) if len(pred) else False,
        "h10_precision": confusion["precision"],
        "h10_recall": confusion["recall"],
        "h10_fpr": confusion["false_positive_rate"],
        "h10_tp": confusion["tp"],
        "h10_fp": confusion["fp"],
        "h10_tn": confusion["tn"],
        "h10_fn": confusion["fn"],
        "score": _score_candidate(
            {
                "active_days": active,
                "h10_precision": confusion["precision"],
                "h10_recall": confusion["recall"],
                "h10_fpr": confusion["false_positive_rate"],
            },
            base_event_rate=base_event_rate,
        ),
    }


def _build_base_frame(
    prices: pd.DataFrame,
    *,
    start: str,
    end: str,
    vol_window: int,
    percentile_window: int,
    min_active_share: float,
    underperform_threshold: float,
    mdd_threshold: float,
) -> tuple[pd.DataFrame, list[str]]:
    frame = pd.DataFrame(index=prices.index)
    verified_sources: list[str] = []
    source_stress_cols: list[str] = []
    source_crisis_cols: list[str] = []
    source_hetero_cols: list[str] = []

    for source in prices.columns:
        diag_frame, diagnostic = _source_diagnostics(
            prices[source].pct_change(fill_method=None),
            vol_window=vol_window,
            percentile_window=percentile_window,
            min_active_share=min_active_share,
        )
        prefix = f"src_{source}"
        frame[f"{prefix}_stress_active"] = diag_frame["regime_code"].ge(3).fillna(False)
        frame[f"{prefix}_crisis_active"] = diag_frame["regime_code"].ge(4).fillna(False)
        frame[f"{prefix}_heteroskedastic_active"] = diag_frame["heteroskedastic_active"].fillna(False)
        source_stress_cols.append(f"{prefix}_stress_active")
        source_crisis_cols.append(f"{prefix}_crisis_active")
        source_hetero_cols.append(f"{prefix}_heteroskedastic_active")
        if bool(diagnostic["passes_shadow_verification"]):
            verified_sources.append(source)

    frame = frame.loc[pd.Timestamp(start).normalize() : pd.Timestamp(end).normalize()].copy()
    prices = prices.reindex(frame.index)
    verified_stress_cols = [f"src_{source}_stress_active" for source in verified_sources]
    verified_crisis_cols = [f"src_{source}_crisis_active" for source in verified_sources]

    frame["heterogeneous_stress_count"] = frame[source_stress_cols].sum(axis=1).astype(int)
    frame["heterogeneous_crisis_count"] = frame[source_crisis_cols].sum(axis=1).astype(int)
    frame["heteroskedastic_source_count"] = frame[source_hetero_cols].sum(axis=1).astype(int)
    frame["verified_stress_count"] = frame[verified_stress_cols].sum(axis=1).astype(int) if verified_stress_cols else 0
    frame["verified_crisis_count"] = frame[verified_crisis_cols].sum(axis=1).astype(int) if verified_crisis_cols else 0
    frame = _add_forward_labels(
        frame,
        prices,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )
    return frame, verified_sources


def run_sweep(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    vol_windows: list[int],
    percentile_windows: list[int],
    min_active_shares: list[float],
    hetero_source_min_counts: list[int],
    crisis_source_min_counts: list[int],
    underperform_threshold: float,
    mdd_threshold: float,
) -> dict[str, Any]:
    prices = _load_source_panel(db_path, start, end, warmup_days)
    rows: list[dict[str, Any]] = []
    base_event_rate: float | None = None

    for vol_window, percentile_window, min_active_share in itertools.product(
        vol_windows,
        percentile_windows,
        min_active_shares,
    ):
        frame, verified_sources = _build_base_frame(
            prices,
            start=start,
            end=end,
            vol_window=vol_window,
            percentile_window=percentile_window,
            min_active_share=min_active_share,
            underperform_threshold=underperform_threshold,
            mdd_threshold=mdd_threshold,
        )
        if base_event_rate is None:
            base_event_rate = float(frame["no_add_label_h10"].dropna().mean())

        for hetero_min, crisis_min in itertools.product(hetero_source_min_counts, crisis_source_min_counts):
            stress_signal = (
                (frame["verified_stress_count"] >= int(hetero_min))
                & (frame["heteroskedastic_source_count"] >= int(hetero_min))
            )
            crisis_signal = frame["verified_crisis_count"] >= int(crisis_min)
            for signal_name, signal in (
                ("heterogeneous_stress_active", stress_signal),
                ("sparse_crisis_active", crisis_signal),
            ):
                metrics = _summarize_signal(frame, signal, base_event_rate=base_event_rate)
                rows.append(
                    {
                        "signal": signal_name,
                        "vol_window": int(vol_window),
                        "percentile_window": int(percentile_window),
                        "min_active_share": float(min_active_share),
                        "hetero_source_min_count": int(hetero_min),
                        "crisis_source_min_count": int(crisis_min),
                        "verified_source_count": int(len(verified_sources)),
                        "verified_sources": ",".join(verified_sources),
                        **metrics,
                    }
                )

    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            ["score", "h10_fpr", "active_days"],
            ascending=[False, True, False],
        ).reset_index(drop=True)

    recommended = candidates[
        (candidates["signal"].eq("sparse_crisis_active"))
        & (candidates["active_days"].ge(20))
        & (candidates["h10_fpr"].le(0.12))
        & (candidates["h10_precision"].ge((base_event_rate or 0.0) + 0.10))
    ].head(10)

    return {
        "report_type": "heterogeneous_vol_regime_param_sweep",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": start,
            "end": end,
            "rows": int(len(prices.loc[pd.Timestamp(start).normalize() : pd.Timestamp(end).normalize()])),
        },
        "parameters": {
            "warmup_days": int(warmup_days),
            "vol_windows": vol_windows,
            "percentile_windows": percentile_windows,
            "min_active_shares": min_active_shares,
            "hetero_source_min_counts": hetero_source_min_counts,
            "crisis_source_min_counts": crisis_source_min_counts,
            "underperform_threshold": float(underperform_threshold),
            "mdd_threshold": float(mdd_threshold),
        },
        "base_event_rate_h10": base_event_rate,
        "top_candidates": candidates.head(25).to_dict(orient="records"),
        "recommended_research_candidates": recommended.to_dict(orient="records"),
        "decision": (
            "Parameter tuning can improve the research dashboard threshold, but this "
            "sweep is not sufficient evidence for live allocation or execution guards."
        ),
        "all_candidates": candidates.to_dict(orient="records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-17")
    parser.add_argument("--warmup-days", type=int, default=500)
    parser.add_argument("--vol-windows", default="10,20,30")
    parser.add_argument("--percentile-windows", default="126,252")
    parser.add_argument("--min-active-shares", default="0.03")
    parser.add_argument("--hetero-source-min-counts", default="3,4")
    parser.add_argument("--crisis-source-min-counts", default="2,3,4,5")
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = run_sweep(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        warmup_days=int(args.warmup_days),
        vol_windows=_parse_int_grid(args.vol_windows),
        percentile_windows=_parse_int_grid(args.percentile_windows),
        min_active_shares=_parse_float_grid(args.min_active_shares),
        hetero_source_min_counts=_parse_int_grid(args.hetero_source_min_counts),
        crisis_source_min_counts=_parse_int_grid(args.crisis_source_min_counts),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_output = output.with_name(output.stem + "_candidates.csv")
    pd.DataFrame(report["all_candidates"]).to_csv(csv_output, index=False, encoding="utf-8-sig")
    report["csv_output"] = str(csv_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    compact = {
        "base_event_rate_h10": report["base_event_rate_h10"],
        "recommended_research_candidates": report["recommended_research_candidates"][:5],
    }
    print(f"Saved: {output}")
    print(f"CSV: {csv_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
