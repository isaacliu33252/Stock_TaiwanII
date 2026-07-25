#!/usr/bin/env python3
"""Compare two existing tail-risk diagnostics' own-alpha calibration.

Research-only, diagnostic-only. Fable independent review of six arXiv papers
(2026-07-17) flagged this gap: 2606.30037v1 ("Heads, Not Backbones") found
that a GARCH/mixture residual density head is the best short-horizon tail
calibrator, and GroupA+ already has two unrelated, never-compared tail-bound
diagnostics that could be checked against each other with zero new modeling:

* Gaussian residual head, h20, on the 00631L NCF panel
  (scripts/evaluate/evaluate_density_head_tail_risk_shadow.py, itself a
  research-only proxy inspired by the same paper -- not a GARCH/GMM retrain).
* Conformal lower-tail bound, h5/h10, backing the live tail_conformal
  advisory alert in daily_signal.py
  (group_a_plus/integrations/tail_conformal.py).

tail_conformal has never had a saved historical per-date series --
evaluate_group_a_plus_crash_detector_overlap.py explicitly notes this as a
gap left for "a follow-up". This script is that follow-up: it walks
compute_tail_conformal_diagnostic forward day by day over the density-head
evaluator's own out-of-sample test dates and reports each diagnostic's
breach rate against its own nominal alpha (calibration error), plus how
often the two would have flagged elevated tail risk on the same day. It does
not change either diagnostic's implementation, thresholds, or any live
decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.governance.latest import resolve_ncf_00631l_panel_path  # noqa: E402
from group_a_plus.integrations.tail_conformal import compute_tail_conformal_diagnostic  # noqa: E402
from scripts.evaluate.evaluate_density_head_tail_risk_shadow import (  # noqa: E402
    _load_panel,
    evaluate_density_heads,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "density_head_vs_tail_conformal_coverage_shadow.json"
TAIL_CONFORMAL_HORIZON_KEY = "h10"
TAIL_CONFORMAL_ALPHA = 0.10
GAUSSIAN_ALPHA = 0.05
ELEVATED_MDD_PROB_THRESHOLD = 0.35


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _gaussian_head_series(panel_path: Path, n_splits: int, gap: int, n_samples: int, seed: int) -> pd.DataFrame:
    panel = _load_panel(panel_path, None, None)
    _report, pred = evaluate_density_heads(
        panel,
        n_splits=n_splits,
        gap=gap,
        n_samples=n_samples,
        gmm_components=4,
        alert_quantile=0.20,
        seed=seed,
    )
    out = pred[["date", "forward_gain_h20", "gaussian_q05"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["gaussian_breach"] = out["forward_gain_h20"] < out["gaussian_q05"]
    # Ex-ante flag (uses only the forecast, not the realized outcome), so the
    # day-level agreement table below compares two forward-looking signals --
    # not a forecast against an outcome. Threshold matches tail_conformal's
    # own high_tail trigger (lower_tail_confidence_bound <= -0.08).
    out["gaussian_elevated"] = out["gaussian_q05"] <= -0.08
    return out.sort_values("date").reset_index(drop=True)


def _tail_conformal_series(db_path: Path, dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for d in dates:
        diag = compute_tail_conformal_diagnostic(db_path=db_path, actual_date=d)
        if diag.get("status") != "ok":
            continue
        h = (diag.get("diagnostics") or {}).get(TAIL_CONFORMAL_HORIZON_KEY)
        if not h:
            continue
        rows.append(
            {
                "date": pd.Timestamp(d).normalize(),
                "point_forecast_return": h.get("point_forecast_return"),
                "lower_tail_confidence_bound": h.get("lower_tail_confidence_bound"),
                "prob_mdd_lt_8pct": h.get("prob_mdd_lt_8pct"),
                "state": diag.get("state"),
            }
        )
    return pd.DataFrame(rows)


def _attach_realized_h10_return(db_path: Path, frame: pd.DataFrame, ticker: str = "00631L.TW") -> pd.DataFrame:
    import duckdb

    if frame.empty:
        frame["forward_return_h10"] = pd.Series(dtype=float)
        return frame
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, str((frame["date"].min() - pd.Timedelta(days=5)).date()), str((frame["date"].max() + pd.Timedelta(days=30)).date())],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = rows.set_index("dt")["close"].astype(float).sort_index()
    fwd = (close.shift(-10) / close - 1.0).rename("forward_return_h10")
    return frame.merge(fwd.reset_index().rename(columns={"dt": "date"}), on="date", how="left")


def build_comparison(
    *,
    db_path: Path,
    panel_path: Path,
    n_splits: int,
    gap: int,
    n_samples: int,
    seed: int,
) -> dict[str, Any]:
    gaussian = _gaussian_head_series(panel_path, n_splits, gap, n_samples, seed)
    conformal = _tail_conformal_series(db_path, pd.DatetimeIndex(gaussian["date"].unique()))
    conformal = _attach_realized_h10_return(db_path, conformal)

    g_rows = int(len(gaussian))
    g_breach = int(gaussian["gaussian_breach"].sum())
    g_breach_rate = _safe_rate(g_breach, g_rows)

    c_valid = conformal.dropna(subset=["lower_tail_confidence_bound", "forward_return_h10"])
    c_rows = int(len(c_valid))
    c_breach = int((c_valid["forward_return_h10"] < c_valid["lower_tail_confidence_bound"]).sum())
    c_breach_rate = _safe_rate(c_breach, c_rows)

    merged = gaussian.merge(conformal, on="date", how="inner")
    merged["conformal_elevated"] = (
        (merged["prob_mdd_lt_8pct"] >= ELEVATED_MDD_PROB_THRESHOLD)
        | (merged["lower_tail_confidence_bound"] <= -0.08)
    )
    both = int((merged["gaussian_elevated"] & merged["conformal_elevated"]).sum())
    gaussian_only = int((merged["gaussian_elevated"] & ~merged["conformal_elevated"]).sum())
    conformal_only = int((~merged["gaussian_elevated"] & merged["conformal_elevated"]).sum())
    neither = int((~merged["gaussian_elevated"] & ~merged["conformal_elevated"]).sum())

    report = {
        "report_type": "density_head_vs_tail_conformal_coverage_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "inspired_by": "2606.30037v1 (Heads, Not Backbones) h-split finding",
            "note": "Compares two pre-existing GroupA+ tail diagnostics; introduces no new model.",
        },
        "policy": "diagnostic_only_no_weight_change_no_threshold_change",
        "gaussian_head": {
            "horizon": "h20",
            "alpha": GAUSSIAN_ALPHA,
            "rows": g_rows,
            "breaches": g_breach,
            "breach_rate": g_breach_rate,
            "breach_rate_minus_alpha": None if g_breach_rate is None else g_breach_rate - GAUSSIAN_ALPHA,
            "window": {
                "start": str(gaussian["date"].min().date()) if g_rows else None,
                "end": str(gaussian["date"].max().date()) if g_rows else None,
            },
        },
        "tail_conformal": {
            "horizon": TAIL_CONFORMAL_HORIZON_KEY,
            "alpha": TAIL_CONFORMAL_ALPHA,
            "rows": c_rows,
            "breaches": c_breach,
            "breach_rate": c_breach_rate,
            "breach_rate_minus_alpha": None if c_breach_rate is None else c_breach_rate - TAIL_CONFORMAL_ALPHA,
            "window": {
                "start": str(c_valid["date"].min().date()) if c_rows else None,
                "end": str(c_valid["date"].max().date()) if c_rows else None,
            },
        },
        "day_level_agreement": {
            "matched_days": int(len(merged)),
            "both_elevated": both,
            "gaussian_only_elevated": gaussian_only,
            "conformal_only_elevated": conformal_only,
            "neither_elevated": neither,
            "jaccard": _safe_rate(both, both + gaussian_only + conformal_only),
        },
        "interpretation": (
            "Both diagnostics are already research_only/advisory. This report only asks "
            "which is better calibrated on its own nominal alpha and how often they agree; "
            "it does not promote either one or change any live threshold."
        ),
        "caveats": (
            "breach_rate_minus_alpha for the two heads IS a fair comparison: each is checked "
            "only against its own horizon's realized return and own nominal alpha. "
            "day_level_agreement is NOT a fair comparison: it applies the same -8% absolute "
            "threshold to both a 20-trading-day forecast (naturally wider dispersion) and a "
            "10-trading-day forecast, so the h20 side trips far more often "
            "(gaussian_elevated fired on {gaussian_elevated_days}/{matched_days} days here) "
            "purely from horizon length, not from being a more sensitive detector. Treat "
            "day_level_agreement as a first pass only; a fair version would need horizon-"
            "matched or rank-based (e.g. same-percentile) elevated thresholds."
        ).format(
            gaussian_elevated_days=both + gaussian_only,
            matched_days=len(merged),
        ),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel", default=resolve_ncf_00631l_panel_path(PROJECT_ROOT))
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=20)
    parser.add_argument("--n-samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_comparison(
        db_path=Path(args.db),
        panel_path=Path(args.panel),
        n_splits=int(args.n_splits),
        gap=int(args.gap),
        n_samples=int(args.n_samples),
        seed=int(args.seed),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(
        {
            "gaussian_breach_rate_minus_alpha": report["gaussian_head"]["breach_rate_minus_alpha"],
            "conformal_breach_rate_minus_alpha": report["tail_conformal"]["breach_rate_minus_alpha"],
            "day_level_jaccard": report["day_level_agreement"]["jaccard"],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
