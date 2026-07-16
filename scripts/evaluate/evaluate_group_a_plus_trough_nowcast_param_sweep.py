#!/usr/bin/env python3
"""Small parameter sweep for GroupA+ trough-nowcast PARTIAL_REENTRY.

Research-only. FULL_REENTRY remains disabled; this script only tests whether
PARTIAL_REENTRY can be made more selective without losing all event coverage.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_group_a_plus_trough_nowcast_shadow import (
    TROUGH_STATES,
    _context_overlay,
    _frame_features,
    _has_warning_context,
    _load_external_rebound_frame,
    _load_ohlcv_frame,
    _parse_windows,
    build_multisource_features,
    classify_market_state,
    run_a2118,
    summarize_forward_returns,
    _load_total_return_prices,
    COMMON_A2118_KW,
)


@dataclass(frozen=True)
class SweepParams:
    cap_min: int = 3
    reentry_min: int = 3
    rebound_0050_min: float = 0.02
    rebound_00631l_min: float = 0.04
    breadth_min: float = 0.50
    risk_unwind_chg_max: float = -0.5


def _val(series: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        out = float(series.get(key, default))
        return default if pd.isna(out) else out
    except Exception:
        return default


def build_param_state_frame(
    *,
    strategy_frame: pd.DataFrame,
    market_proxy: pd.DataFrame,
    multisource: pd.DataFrame,
    external: pd.DataFrame,
    params: SweepParams,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt, row in strategy_frame.iterrows():
        features = _frame_features(row)
        regime = str(row.get("execution_regime", row.get("regime", "golden1")))
        market_state = classify_market_state(regime, features)
        overlay = _context_overlay(row, market_state)
        if not _has_warning_context(features, market_state, overlay):
            rows.append(
                {
                    "date": pd.Timestamp(dt),
                    "state": "NO_TROUGH",
                    "context_active": False,
                    "capitulation_score": 0,
                    "reentry_confirmation_score": 0,
                    "market_state": market_state.get("state"),
                    "execution_regime": regime,
                    "capitulation_reasons": "",
                    "reentry_confirmation_reasons": "",
                }
            )
            continue

        mp = market_proxy.loc[dt] if dt in market_proxy.index else pd.Series(dtype=float)
        ms = multisource.loc[dt] if dt in multisource.index else pd.Series(dtype=float)
        ex = external.loc[dt] if dt in external.index else pd.Series(dtype=float)

        cap_reasons: list[str] = []
        reentry_reasons: list[str] = []

        def cap(condition: bool, reason: str) -> None:
            if condition:
                cap_reasons.append(reason)

        def reentry(condition: bool, reason: str) -> None:
            if condition:
                reentry_reasons.append(reason)

        cap(float(features.get("drawdown", 0.0)) <= -0.06, "0050_strategy_drawdown_le_6pct")
        cap(int(features.get("tail_risk_score", 0)) >= 2, "tail_risk_score_ge_2")
        cap((overlay.get("a2118_extreme_risk_warning") or {}).get("active") is True, "h20_extreme_warning_active")
        cap(_val(mp, "volume_z60") >= 1.0, "0050_volume_z60_ge_1")
        cap(_val(mp, "amihud_z60") >= 1.0, "0050_amihud_z60_ge_1")
        cap(bool(mp.get("panic_volume_contracting", False)), "panic_volume_expanded_then_contracting")
        cap(_val(ms, "txo_pcr_volume_z20") >= 1.0, "txo_pcr_volume_z20_ge_1")
        cap(_val(ms, "txo_pcr_oi_z20") >= 1.0, "txo_pcr_oi_z20_ge_1")
        cap(_val(ms, "txo_foreign_put_call_net_oi_chg5_z60") >= 1.0, "foreign_txo_put_call_oi_chg5_z60_ge_1")
        cap(_val(ms, "market_margin_forced_repay_z60") >= 1.0, "market_margin_forced_repay_z60_ge_1")
        cap(_val(ms, "market_margin_balance_chg20_z252") <= -1.0, "market_margin_balance_chg20_z252_le_minus_1")
        cap(_val(ms, "soxx_put_call_iv_skew_z252") >= 1.0, "soxx_put_call_iv_skew_z252_ge_1")
        cap(_val(ms, "usdtwd_ret5_z60") >= 1.0, "usdtwd_ret5_z60_ge_1")

        reentry(_val(mp, "ret_0050_1d") >= 0.01, "0050_1d_rebound_ge_1pct")
        reentry(_val(mp, "rebound_0050_from_5d_low") >= params.rebound_0050_min, "0050_rebound_from_5d_low")
        reentry(_val(mp, "rebound_00631l_from_5d_low") >= params.rebound_00631l_min, "00631l_rebound_from_5d_low")
        reentry(_val(mp, "breadth_up_fraction_groupa") >= params.breadth_min, "groupa_breadth_up_fraction")
        reentry(_val(ex, "soxx_rebound_from_5d_low") >= 0.03, "soxx_rebound_from_5d_low_ge_3pct")
        reentry(_val(ex, "tsm_adr_rebound_from_5d_low") >= 0.03, "tsm_adr_rebound_from_5d_low_ge_3pct")
        reentry(_val(ex, "tw_2330_rebound_from_5d_low") >= 0.02, "2330_rebound_from_5d_low_ge_2pct")
        reentry(_val(ex, "usdtwd_ret1") <= -0.002, "usdtwd_1d_turns_lower")
        reentry(_val(ms, "txo_pcr_volume_z20_chg5") <= params.risk_unwind_chg_max, "txo_pcr_volume_z20_falling")
        reentry(_val(ms, "usdtwd_ret5_z60_chg5") <= params.risk_unwind_chg_max, "usdtwd_riskoff_z_falling")

        local_price_confirm = bool(
            ("0050_1d_rebound_ge_1pct" in reentry_reasons or "0050_rebound_from_5d_low" in reentry_reasons)
            and "groupa_breadth_up_fraction" in reentry_reasons
        )
        risk_unwind_confirm = bool(
            "txo_pcr_volume_z20_falling" in reentry_reasons
            or "usdtwd_riskoff_z_falling" in reentry_reasons
            or "usdtwd_1d_turns_lower" in reentry_reasons
        )
        cross_market_confirm = bool(
            "soxx_rebound_from_5d_low_ge_3pct" in reentry_reasons
            or "tsm_adr_rebound_from_5d_low_ge_3pct" in reentry_reasons
            or "2330_rebound_from_5d_low_ge_2pct" in reentry_reasons
        )
        full_candidate = bool(
            len(cap_reasons) >= 4
            and len(reentry_reasons) >= 6
            and local_price_confirm
            and risk_unwind_confirm
            and cross_market_confirm
            and "00631l_rebound_from_5d_low" in reentry_reasons
        )
        partial = bool(
            len(cap_reasons) >= params.cap_min
            and len(reentry_reasons) >= params.reentry_min
            and local_price_confirm
            and (risk_unwind_confirm or cross_market_confirm)
            and not full_candidate
        )
        state = "PARTIAL_REENTRY" if partial else ("CAPITULATION_WARNING" if len(cap_reasons) >= 2 else "NO_TROUGH")
        rows.append(
            {
                "date": pd.Timestamp(dt),
                "state": state,
                "context_active": True,
                "capitulation_score": len(cap_reasons),
                "reentry_confirmation_score": len(reentry_reasons),
                "market_state": market_state.get("state"),
                "execution_regime": regime,
                "capitulation_reasons": ";".join(cap_reasons),
                "reentry_confirmation_reasons": ";".join(reentry_reasons),
            }
        )
    return pd.DataFrame(rows).set_index("date").sort_index()


def prepare_window_cache(
    *,
    db_path: Path,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    initial_value: float,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        **COMMON_A2118_KW,
    )
    prices, _coverage = _load_total_return_prices(db_path, frame.index)
    prices = prices.reindex(frame.index).dropna()
    frame = frame.reindex(prices.index)
    index = pd.DatetimeIndex(frame.index)
    market_proxy = _load_ohlcv_frame(db_path, index)
    external = _load_external_rebound_frame(db_path, index)
    try:
        multisource = build_multisource_features(db_path, pd.bdate_range(index.min() - pd.Timedelta(days=420), index.max()))
    except Exception:
        multisource = pd.DataFrame(index=index)
    multisource = multisource.reindex(index)
    if "txo_pcr_volume_z20" in multisource:
        multisource["txo_pcr_volume_z20_chg5"] = multisource["txo_pcr_volume_z20"].diff(5)
    if "usdtwd_ret5_z60" in multisource:
        multisource["usdtwd_ret5_z60_chg5"] = multisource["usdtwd_ret5_z60"].diff(5)
    return {
        "label": label,
        "kind": kind,
        "frame": frame,
        "prices": prices,
        "market_proxy": market_proxy,
        "external": external,
        "multisource": multisource,
    }


def evaluate_params_on_cache(cache: dict[str, Any], params: SweepParams) -> dict[str, Any]:
    state_frame = build_param_state_frame(
        strategy_frame=cache["frame"],
        market_proxy=cache["market_proxy"],
        multisource=cache["multisource"],
        external=cache["external"],
        params=params,
    )
    prices = cache["prices"]
    forward = summarize_forward_returns(state_frame, prices)
    counts = {state: int((state_frame["state"] == state).sum()) for state in TROUGH_STATES}
    partial = forward["by_state"]["PARTIAL_REENTRY"]
    return {
        "label": cache["label"],
        "kind": cache["kind"],
        "state_counts": counts,
        "false_reentry_event_count": int(forward["false_reentry_event_count"]),
        "partial_days": counts["PARTIAL_REENTRY"],
        "partial_00631l_fwd_return_5d_mean": partial.get("00631L.TW_fwd_return_5d_mean"),
        "partial_00631l_false_rate_mdd_lt_3pct": partial.get("00631L.TW_false_reentry_rate_mdd_lt_3%"),
    }


def _candidate_grid() -> list[SweepParams]:
    values = {
        "cap_min": [3, 4],
        "reentry_min": [3, 4],
        "rebound_0050_min": [0.015, 0.02, 0.025],
        "rebound_00631l_min": [0.03, 0.04, 0.05],
        "breadth_min": [0.50, 0.60],
        "risk_unwind_chg_max": [-0.3, -0.5, -0.7],
    }
    keys = list(values)
    return [SweepParams(**dict(zip(keys, combo))) for combo in itertools.product(*(values[k] for k in keys))]


def _score_candidate(windows: list[dict[str, Any]]) -> dict[str, Any]:
    partial_days = sum(int(w["partial_days"]) for w in windows)
    false_events = sum(int(w["false_reentry_event_count"]) for w in windows)
    means = [
        float(w["partial_00631l_fwd_return_5d_mean"])
        for w in windows
        if w["partial_00631l_fwd_return_5d_mean"] is not None
    ]
    min_mean = min(means) if means else None
    weighted_mean = None
    denom = sum(int(w["partial_days"]) for w in windows if w["partial_00631l_fwd_return_5d_mean"] is not None)
    if denom:
        weighted_mean = sum(
            int(w["partial_days"]) * float(w["partial_00631l_fwd_return_5d_mean"])
            for w in windows
            if w["partial_00631l_fwd_return_5d_mean"] is not None
        ) / denom
    return {
        "partial_days": partial_days,
        "false_reentry_event_count": false_events,
        "partial_00631l_fwd_return_5d_weighted_mean": weighted_mean,
        "partial_00631l_fwd_return_5d_min_window_mean": min_mean,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--max-candidates", type=int, default=0, help="Optional cap for quick smoke tests; 0 means full grid.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "group_a_plus_trough_nowcast_param_sweep_20260714.json"))
    args = parser.parse_args()

    db_path = Path(args.db)
    windows = _parse_windows(args.windows)
    candidates = _candidate_grid()
    if args.max_candidates > 0:
        candidates = candidates[: args.max_candidates]

    caches = []
    for label, start, end, panel, kind in windows:
        print(f"Preparing {label}: {start}..{end}")
        caches.append(
            prepare_window_cache(
                db_path=db_path,
                label=label,
                start=start,
                end=end,
                panel=panel,
                kind=kind,
                initial_value=args.initial_value,
            )
        )

    rows = []
    for idx, params in enumerate(candidates, start=1):
        print(f"[{idx}/{len(candidates)}] {params}")
        window_rows = [evaluate_params_on_cache(cache, params) for cache in caches]
        score = _score_candidate(window_rows)
        rows.append({"params": asdict(params), **score, "windows": window_rows})

    rows.sort(
        key=lambda row: (
            row["false_reentry_event_count"],
            -(row["partial_00631l_fwd_return_5d_min_window_mean"] or -999.0),
            -(row["partial_00631l_fwd_return_5d_weighted_mean"] or -999.0),
            -row["partial_days"],
        )
    )
    payload = {
        "experiment": "group_a_plus_trough_nowcast_param_sweep",
        "research_only": True,
        "full_reentry": "disabled",
        "candidate_count": len(rows),
        "baseline_v6_reference": {
            "partial_days": 40,
            "false_reentry_event_count": 17,
        },
        "rows": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {out}")
    print("Top candidates:")
    for row in rows[:10]:
        print(
            row["params"],
            "days=",
            row["partial_days"],
            "false=",
            row["false_reentry_event_count"],
            "wmean=",
            row["partial_00631l_fwd_return_5d_weighted_mean"],
            "minmean=",
            row["partial_00631l_fwd_return_5d_min_window_mean"],
        )


if __name__ == "__main__":
    main()
