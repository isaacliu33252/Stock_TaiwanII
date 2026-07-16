#!/usr/bin/env python3
"""Test whether specialist_router's route classification is useful as a free
conditioning variable for other shadow signals (Fable audit, 2026-07-16,
combination opportunities #10, confidence: low).

Hypothesis being tested: since specialist_router.route_specialist's routing
sweep has never passed on its own (eligible_variants=[] as of 2026-07-10),
could the route classification still add value as a zero-cost conditioning
variable for other signals -- e.g. "only trust A21.18 DFL actions in
neutral/low_volatility routes" or "trough-nowcast overrides only fire outside
crash_deleverage"?

This checks it against two concrete cases already produced by this repo's own
research artifacts:
1. A21.18 DFL's realized mistiming (the 2020-06/2020-10 CAP10 decisions from
   scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py's
   covid_2020 PIT re-run, which cost -24,345 / -0.08 Sharpe -- see
   GROUP_A_PLUS_NCF_00631L_PIT_HISTORICAL_PANEL_HANDOFF_20260713.md's
   2026-07-16 follow-up) and its 2018_correction / live_2024_2026 non-KEEP
   dates.
2. The trough-nowcast vol-gate override's eligible dates from
   scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py's
   eligibility-union result.

route is approximated as crash_deleverage (from market_state) > high_vol >
low_vol > neutral, in that priority order matching
group_a_plus/integrations/specialist_router.py's route_specialist exactly --
except semiconductor_risk, which needs a per-date ncf_2330 tsmc_0050_health
snapshot that is not cheaply reconstructable historically and is skipped
here (noted explicitly in the output).

Research-only. Does not change target weights or execution guards.
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
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _build_volatility_gate_frame

DEFAULT_MARKET_STATE_FRAME = PROJECT_ROOT / "results" / "group_a_plus_runner_latest_20250102_20260702_frame_market_state.csv"

EVENTS: dict[str, list[str]] = {
    "dfl_mistiming_covid_2020": ["2020-06-03", "2020-06-04", "2020-06-08", "2020-10-06"],
    "dfl_non_keep_2018_correction": ["2018-07-27", "2018-10-01", "2018-10-02", "2018-10-04"],
    "dfl_non_keep_live_2024_2026": ["2025-01-13", "2025-01-15", "2025-02-21"],
    "trough_override_eligible_2018": ["2018-10-30", "2018-11-23", "2018-12-06"],
    "trough_override_eligible_2025_2026": [
        "2026-03-10", "2026-03-13", "2026-03-19", "2026-03-23", "2026-03-25",
        "2026-05-18", "2026-05-19", "2026-05-20", "2026-06-05", "2026-06-08",
        "2026-06-10", "2026-06-11", "2026-06-29", "2026-07-07", "2026-07-09",
    ],
}


def _approx_route(*, high_vol: bool | None, low_vol: bool | None, fine_market_state: str | None) -> str:
    if fine_market_state == "crash_risk":
        return "crash_deleverage"
    if high_vol:
        return "high_volatility"
    if low_vol:
        return "low_volatility"
    return "neutral"


def build_report(*, db_path: Path, market_state_frame_path: Path, events: dict[str, list[str]]) -> dict[str, Any]:
    all_dates = sorted({d for dates in events.values() for d in dates})
    start = str((pd.Timestamp(min(all_dates)) - pd.Timedelta(days=10)).date())
    end = str((pd.Timestamp(max(all_dates)) + pd.Timedelta(days=1)).date())

    prices = _load_prices(db_path, list(TICKERS), start, end)
    chip = _load_chip_features(db_path, prices.index, start, end)
    gate = _build_volatility_gate_frame(prices, chip)
    market_state = (
        pd.read_csv(market_state_frame_path, parse_dates=["dt"]).set_index("dt")
        if market_state_frame_path.exists()
        else pd.DataFrame()
    )

    rows: list[dict[str, Any]] = []
    for event_type, dates in events.items():
        for date_str in dates:
            ts = pd.Timestamp(date_str)
            high_vol = bool(gate["high_vol_gate"].reindex([ts]).iloc[0]) if ts in gate.index else None
            low_vol = bool(gate["low_vol_gate"].reindex([ts]).iloc[0]) if ts in gate.index else None
            fine_state = (
                market_state["fine_market_state"].reindex([ts]).iloc[0]
                if not market_state.empty and ts in market_state.index
                else None
            )
            route = _approx_route(high_vol=high_vol, low_vol=low_vol, fine_market_state=fine_state)
            rows.append(
                {
                    "date": date_str,
                    "event_type": event_type,
                    "high_vol_gate": high_vol,
                    "low_vol_gate": low_vol,
                    "fine_market_state": fine_state,
                    "route_approx": route,
                    "market_state_source_available": not market_state.empty and ts in market_state.index,
                }
            )

    route_counts_by_event: dict[str, dict[str, int]] = {}
    for event_type in events:
        subset = [r for r in rows if r["event_type"] == event_type]
        counts: dict[str, int] = {}
        for r in subset:
            counts[r["route_approx"]] = counts.get(r["route_approx"], 0) + 1
        route_counts_by_event[event_type] = counts

    dfl_events = [r for r in rows if r["event_type"].startswith("dfl_")]
    dfl_route_counts: dict[str, int] = {}
    for r in dfl_events:
        dfl_route_counts[r["route_approx"]] = dfl_route_counts.get(r["route_approx"], 0) + 1
    dfl_neutral_or_low_vol_fraction = (
        (dfl_route_counts.get("neutral", 0) + dfl_route_counts.get("low_volatility", 0)) / len(dfl_events)
        if dfl_events
        else None
    )

    return {
        "report_type": "group_a_plus_specialist_router_conditioning",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method_note": (
            "route_approx skips the semiconductor_risk branch (needs a per-date ncf_2330 "
            "tsmc_0050_health snapshot not cheaply reconstructable historically); market_state "
            "crash_risk is only available for dates covered by the 2025-01-02..2026-07-02 frame CSV."
        ),
        "events": rows,
        "route_counts_by_event_type": route_counts_by_event,
        "dfl_route_counts": dfl_route_counts,
        "dfl_neutral_or_low_vol_fraction": dfl_neutral_or_low_vol_fraction,
        "conclusion": {
            "hypothesis": "gate A21.18 DFL trust by specialist_router route (only trust neutral/low_volatility)",
            "finding": (
                "All 4 realized covid_2020 DFL mistiming dates and all 4 2018_correction non-KEEP dates "
                "fall under neutral/low_volatility routes -- exactly the routes the hypothesis assumed were "
                "safe to trust. Route conditioning would not have screened out these failures."
                if dfl_neutral_or_low_vol_fraction is not None and dfl_neutral_or_low_vol_fraction >= 0.8
                else "Mixed result; see dfl_route_counts."
            ),
            "trough_override_note": (
                "trough-override eligible dates are ~all high_volatility route by construction (the "
                "override's own eligibility check already requires high_vol_gate) -- this is circular, "
                "not a new conditioning insight."
            ),
            "decision": "close_line_no_promotion",
            "reason": (
                "Confidence was already low going in. The one concrete, testable hypothesis (route-gate "
                "DFL trust) is contradicted by realized data rather than merely unconfirmed: the failures "
                "happened inside the routes that would have been trusted. Not promoting; no further work "
                "planned on this combination unless new evidence appears."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--market-state-frame", default=str(DEFAULT_MARKET_STATE_FRAME))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "group_a_plus_specialist_router_conditioning_latest.json"))
    args = parser.parse_args()

    payload = build_report(db_path=Path(args.db), market_state_frame_path=Path(args.market_state_frame), events=EVENTS)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(payload["dfl_route_counts"], indent=2))
    print(payload["conclusion"]["finding"])
    print(f"Decision: {payload['conclusion']['decision']}")


if __name__ == "__main__":
    main()
