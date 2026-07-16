#!/usr/bin/env python3
"""Cross-tabulate GroupA+'s crash/de-risk detectors over a shared window.

Research-only. Fable audit (2026-07-16, combination opportunities #5): GroupA+
now has several independent crash/stress detectors -- some are wired as
blocking pre-trade guards (group_a_plus/operations/execution_guard.py:
volatility gate, tail-conformal, A21.18 extreme-risk warning, compounding
regime MEAN_REVERTING), others are alert-only (multisource crash_risk_alert
2-of-3, market_state crash-like states, specialist_router's crash_deleverage
route). The one overlap analysis that has been done (DFL vs. vol-gate vs.
extreme-warning, in evaluate_a2118_decision_focused_overlap.py) found ~0%
overlap -- these detectors fire on different days. Nobody has checked whether
that pattern holds for the *other* detector pairs, or which alert-only
detector would be the best candidate to promote to a blocking guard because it
covers days the existing blocking guards miss.

This script builds six detector series over a common historical window
(2025-01-02..2026-07-02, bounded by the reusable market_state frame CSV) and
reports pairwise overlap (Jaccard) plus each detector's "unique coverage":
days it alone is active while every existing blocking guard is inactive.

Two detectors from Fable's original list of five are intentionally NOT
included here:
- cross-market NO_ADD (evaluate_cross_market_directed_graph_shadow.py): no
  saved per-date prediction series exists; regenerating one requires
  retraining its walk-forward model, which is out of scope for this pass.
- tail_conformal: no saved per-date series exists either; a full historical
  loop is possible but was left out of this first pass to keep runtime
  reasonable. Worth adding in a follow-up.

Never changes target weights, execution guards, or live decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_chip_features, _load_prices
from group_a_plus.integrations.leveraged_compounding_regime import (
    TREND_PERSISTENT,  # noqa: F401  (imported for readers cross-referencing MEAN_REVERTING)
    MEAN_REVERTING,
    build_compounding_features,
    classify_compounding_regime,
)
from scripts.evaluate.evaluate_00631l_multisource_crash_risk import build_multisource_features, _stress_veto_fraction
from scripts.evaluate.evaluate_a2118_decision_focused_overlap import _extreme_warning_proxy, _load_panel
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow import TUNED_COMPOUNDING_THRESHOLDS
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame

DEFAULT_MARKET_STATE_FRAME = PROJECT_ROOT / "results" / "group_a_plus_runner_latest_20250102_20260702_frame_market_state.csv"
DEFAULT_NCF_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260707.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_crash_detector_overlap_latest.json"

# Blocking pre-trade guards (see group_a_plus/operations/execution_guard.py).
BLOCKING_DETECTORS = ("volatility_gate", "extreme_warning_proxy", "compounding_mean_reverting")
# Alert-only detectors (advisory; no automatic weight change).
ALERT_ONLY_DETECTORS = ("crash_risk_alert_2of3", "market_state_crash_like", "specialist_router_crash_deleverage")


def _load_market_state_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    frame = frame.set_index("dt").sort_index()
    return frame


def build_detector_frame(
    *,
    db_path: Path,
    market_state_frame_path: Path,
    ncf_panel_path: Path,
    h20_max: float,
    mdd_min: float,
) -> pd.DataFrame:
    market_state = _load_market_state_frame(market_state_frame_path)
    index = market_state.index
    start, end = str(index.min().date()), str(index.max().date())

    prices = _load_prices(db_path, list(TICKERS), start, end).reindex(index)
    chip = _load_chip_features(db_path, index, start, end)
    gate_frame = _build_volatility_gate_frame(prices, chip).reindex(index)

    features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
    compounding = classify_compounding_regime(features, thresholds=TUNED_COMPOUNDING_THRESHOLDS).reindex(index)

    panel = _load_panel(str(ncf_panel_path))
    extreme_warning = _extreme_warning_proxy(panel, index, h20_max=h20_max, mdd_min=mdd_min)

    multisource = build_multisource_features(db_path, index)
    crash_alert = _stress_veto_fraction(multisource).reindex(index).fillna(0.0) >= 1.0

    market_state_crash_like = market_state["fine_market_state"].isin(["crash_risk", "bear_breakdown"])

    # Mirrors group_a_plus/integrations/specialist_router.py's route_specialist
    # crash_risk condition exactly (market_state == "crash_risk" OR
    # tail_risk_score >= 2 OR (total_risk_score >= 9 AND drawdown <= -0.05)),
    # derived from the same per-date features rather than recomputing routing.
    specialist_crash = (
        (market_state["fine_market_state"] == "crash_risk")
        | (market_state["tail_risk_score"] >= 2)
        | ((market_state["total_risk_score"] >= 9) & (market_state["drawdown"] <= -0.05))
    )

    detectors = pd.DataFrame(
        {
            "volatility_gate": gate_frame["high_vol_gate"].fillna(False).astype(bool),
            "extreme_warning_proxy": extreme_warning.astype(bool),
            "compounding_mean_reverting": (compounding["compounding_regime"] == MEAN_REVERTING).fillna(False),
            "crash_risk_alert_2of3": crash_alert.astype(bool),
            "market_state_crash_like": market_state_crash_like.fillna(False),
            "specialist_router_crash_deleverage": specialist_crash.fillna(False),
        },
        index=index,
    )
    return detectors


def _jaccard(a: pd.Series, b: pd.Series) -> float | None:
    union = int((a | b).sum())
    if union == 0:
        return None
    return float((a & b).sum() / union)


def build_overlap_report(detectors: pd.DataFrame) -> dict[str, Any]:
    names = list(detectors.columns)
    active_days = {name: int(detectors[name].sum()) for name in names}

    pairwise = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairwise[f"{a}__vs__{b}"] = {
                "jaccard": _jaccard(detectors[a], detectors[b]),
                "both_active_days": int((detectors[a] & detectors[b]).sum()),
                "only_a_days": int((detectors[a] & ~detectors[b]).sum()),
                "only_b_days": int((~detectors[a] & detectors[b]).sum()),
            }

    any_blocking = detectors[list(BLOCKING_DETECTORS)].any(axis=1)
    unique_coverage = {
        name: {
            "active_days": active_days[name],
            "days_active_while_no_blocking_guard_active": int((detectors[name] & ~any_blocking).sum()),
        }
        for name in ALERT_ONLY_DETECTORS
    }

    return {
        "report_type": "group_a_plus_crash_detector_overlap",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {"start": str(detectors.index.min().date()), "end": str(detectors.index.max().date()), "rows": int(len(detectors))},
        "blocking_detectors": list(BLOCKING_DETECTORS),
        "alert_only_detectors": list(ALERT_ONLY_DETECTORS),
        "excluded_detectors": {
            "cross_market_no_add": "no saved per-date series; requires retraining the walk-forward model",
            "tail_conformal": "no saved per-date series; full historical loop deferred to a follow-up",
        },
        "active_days": active_days,
        "any_blocking_guard_active_days": int(any_blocking.sum()),
        "pairwise_overlap": pairwise,
        "alert_only_unique_coverage": unique_coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--market-state-frame", default=str(DEFAULT_MARKET_STATE_FRAME))
    parser.add_argument("--ncf-panel", default=str(DEFAULT_NCF_PANEL))
    parser.add_argument("--h20-max", type=float, default=0.22)
    parser.add_argument("--mdd-min", type=float, default=0.85)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    detectors = build_detector_frame(
        db_path=Path(args.db),
        market_state_frame_path=Path(args.market_state_frame),
        ncf_panel_path=Path(args.ncf_panel),
        h20_max=float(args.h20_max),
        mdd_min=float(args.mdd_min),
    )
    payload = build_overlap_report(detectors)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(payload["active_days"], indent=2))
    print("Unique coverage (active while no blocking guard active):")
    for name, info in payload["alert_only_unique_coverage"].items():
        print(f"  {name}: {info['days_active_while_no_blocking_guard_active']}/{info['active_days']}")


if __name__ == "__main__":
    main()
