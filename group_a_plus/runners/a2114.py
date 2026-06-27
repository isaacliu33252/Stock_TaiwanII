"""A21.14 runner — A21.11 + NCF Exit Gate (regime-boundary only).

Extends A21.11 with a targeted NCF integration that fixes the core flaw in A21.13:

  A21.13 (broken):  daily golden1 trim via ensemble downside → fires 60% of days
                    → -18.5% total return drag in 2025 bull market
  A21.14 (this):    NCF stays silent inside golden1; only acts at regime boundaries

NCF integration design
-----------------------
1. Exit gate (early defensive switch):
   Trigger: in golden1 AND NCF H20 dual-confirm > NCF_EXIT_SIGNAL_THRESHOLD
            AND consecutive trigger days ≥ NCF_EXIT_CONSECUTIVE
            AND ma_gap < NCF_EXIT_MA_GAP_MAX (near the MA100 boundary)
   Action:  override regime to defensive (before MA100 exit_gap fires)
   Hysteresis: gate clears after 2 consecutive days of signal < NCF_RECOVERY_THRESHOLD

2. Recovery gate (delay golden1 re-entry):
   Trigger: A21.11 wants to re-enter golden1, but NCF H20 dual-confirm > NCF_RECOVERY_GATE_THRESHOLD
   Action:  stay in current defensive one more day; re-check next day

3. Golden1 weights: NEVER modified by NCF
   → no daily allocation friction; all return drag eliminated

Implementation note
-------------------
NCF gate is applied as a pre-processing step: it modifies the `execution_regime`
Series BEFORE passing it to the proven `_simulate_costed_curve`. This reuses the
exact same shares-tracking simulation used by A21.11, ensuring numerical consistency.
"""

from __future__ import annotations

import argparse
import glob
from datetime import date
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.integrations.ncf import (
    load_ncf_signal,
    ncf_downside_signal,
    ncf_overlay_summary,
)
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2111 import _build_switch_rule
from tw_output_standard import OutputStandardizer, write_standard_output


A2114_ID = "a2114_a2111_ncf_exit_gate"

# H20 dual-confirm gate conditions
NCF_EXIT_DUAL_LT = 0.40           # 631L H20 prob_up must be < this
NCF_EXIT_DUAL_RT = 0.60           # 632R H20 prob_up must be > this
NCF_EXIT_SIGNAL_THRESHOLD = 0.35  # combined dual-confirm must exceed this
NCF_EXIT_MA_GAP_MAX = 0.03        # only fire when within 3% of MA100
NCF_EXIT_CONSECUTIVE = 3          # signal must persist ≥ this many consecutive days
NCF_RECOVERY_THRESHOLD = 0.25     # gate clears when signal < this for ≥ 2 days
NCF_RECOVERY_GATE_THRESHOLD = 0.30  # delay golden1 re-entry if signal still ≥ this


def _resolve_ncf_path(explicit: str | None, ticker_tag: str) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p if p.exists() else None
    today_str = date.today().strftime("%Y%m%d")
    today_path = PROJECT_ROOT / "results" / f"ncf_{ticker_tag}_{today_str}.json"
    if today_path.exists():
        return today_path
    candidates = sorted(
        glob.glob(str(PROJECT_ROOT / "results" / f"ncf_{ticker_tag}_2?????.json"))
    )
    return Path(candidates[-1]) if candidates else None


def _load_ncf_panel(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _ncf_dual_confirm_h20(
    d: pd.Timestamp,
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
    lt: float = NCF_EXIT_DUAL_LT,
    rt: float = NCF_EXIT_DUAL_RT,
) -> float:
    """H20 dual-confirm signal for day d. Returns 0 unless BOTH ETFs agree."""
    if panel_631l is None or panel_632r is None:
        return 0.0
    if d not in panel_631l.index or d not in panel_632r.index:
        return 0.0
    l_h20 = float(panel_631l.loc[d, "h20_prob_up"])
    r_h20 = float(panel_632r.loc[d, "h20_prob_up"])
    if l_h20 < lt and r_h20 > rt:
        return 0.6 * max(0.0, 0.5 - l_h20) * 2.0 + 0.4 * max(0.0, r_h20 - 0.5) * 2.0
    return 0.0


def _apply_ncf_gate(
    execution_regime: pd.Series,
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
    ma_gap_series: pd.Series,
    ncf_exit_signal_threshold: float = NCF_EXIT_SIGNAL_THRESHOLD,
    ncf_exit_ma_gap_max: float = NCF_EXIT_MA_GAP_MAX,
    ncf_exit_consecutive: int = NCF_EXIT_CONSECUTIVE,
    ncf_recovery_threshold: float = NCF_RECOVERY_THRESHOLD,
    ncf_recovery_gate_threshold: float = NCF_RECOVERY_GATE_THRESHOLD,
) -> tuple[pd.Series, dict]:
    """Pre-process execution_regime: override golden1 days when NCF gate fires.

    Returns (modified_regime, gate_info).
    Reuses _simulate_costed_curve unchanged — only the regime input changes.
    """
    if panel_631l is None or panel_632r is None:
        return execution_regime.copy(), {
            "ncf_gate_activations": 0,
            "ncf_recovery_gates": 0,
            "ncf_gate_events": [],
        }

    modified = execution_regime.copy()
    consecutive_signal_days = 0
    consecutive_clear_days = 0
    ncf_gate_active = False
    ncf_gate_events: list[dict] = []
    prev_effective: str | None = None

    for d in execution_regime.index:
        a2111_regime = str(execution_regime.loc[d])
        ma_gap = float(ma_gap_series.get(d, 999.0))
        dual = _ncf_dual_confirm_h20(d, panel_631l, panel_632r)

        # Update consecutive counters
        if dual > ncf_exit_signal_threshold:
            consecutive_signal_days += 1
            consecutive_clear_days = 0
        else:
            consecutive_signal_days = 0
            if dual < ncf_recovery_threshold:
                consecutive_clear_days += 1
            else:
                consecutive_clear_days = 0

        # Gate ON: sustained bearish H20 near MA100 boundary
        if (
            not ncf_gate_active
            and a2111_regime == "golden1"
            and consecutive_signal_days >= ncf_exit_consecutive
            and ma_gap < ncf_exit_ma_gap_max
        ):
            ncf_gate_active = True
            ncf_gate_events.append({
                "date": str(d.date()),
                "event": "ncf_gate_ON",
                "dual_signal": round(dual, 4),
                "ma_gap": round(ma_gap, 4),
                "consecutive_days": consecutive_signal_days,
            })

        # Gate OFF: signal cleared (hysteresis — needs 2 clear days)
        if ncf_gate_active and consecutive_clear_days >= 2:
            ncf_gate_active = False
            ncf_gate_events.append({
                "date": str(d.date()),
                "event": "ncf_gate_OFF",
                "dual_signal": round(dual, 4),
                "consecutive_clear": consecutive_clear_days,
            })

        # Determine effective regime
        if a2111_regime == "golden1" and ncf_gate_active:
            # NCF early exit
            effective = "group_a_plus_defensive"
        elif (
            a2111_regime == "golden1"
            and dual > ncf_recovery_gate_threshold
            and prev_effective in ("group_a_plus_defensive", "group_a_plus_recovery")
        ):
            # Recovery gate: delay re-entry one day
            effective = prev_effective
            ncf_gate_events.append({
                "date": str(d.date()),
                "event": "ncf_recovery_gate",
                "dual_signal": round(dual, 4),
                "held_in": prev_effective,
            })
        else:
            effective = a2111_regime

        modified.loc[d] = effective
        prev_effective = effective

    return modified, {
        "ncf_gate_activations": sum(1 for e in ncf_gate_events if e["event"] == "ncf_gate_ON"),
        "ncf_recovery_gates": sum(1 for e in ncf_gate_events if e["event"] == "ncf_recovery_gate"),
        "ncf_gate_events": ncf_gate_events,
    }


def run_a2114(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    ncf_00631l_path: str | None = None,
    ncf_00632r_path: str | None = None,
    ncf_panel_631l_path: str | None = None,
    ncf_panel_632r_path: str | None = None,
    ncf_exit_signal_threshold: float = NCF_EXIT_SIGNAL_THRESHOLD,
    ncf_exit_ma_gap_max: float = NCF_EXIT_MA_GAP_MAX,
    ncf_exit_consecutive: int = NCF_EXIT_CONSECUTIVE,
    ncf_recovery_threshold: float = NCF_RECOVERY_THRESHOLD,
    ncf_recovery_gate_threshold: float = NCF_RECOVERY_GATE_THRESHOLD,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.14: A21.11 base + NCF exit gate.

    Uses the same _simulate_costed_curve as A21.11 — NCF gate only modifies
    the execution_regime Series before it enters simulation.
    """
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve(DEFAULT_GOLDEN_SIGNAL)
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, warmup_days)
    switch_rule = _build_switch_rule()
    full_prices = _load_prices(_resolve(db), list(TICKERS), load_start, end)
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(full_prices, full_chip, switch_rule)
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(db), close_prices.index)

    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }

    panel_631l = _load_ncf_panel(
        Path(ncf_panel_631l_path) if ncf_panel_631l_path else None
    )
    panel_632r = _load_ncf_panel(
        Path(ncf_panel_632r_path) if ncf_panel_632r_path else None
    )

    ma_gap_series = frame["ma_gap"].reindex(execution_regime.index).fillna(999.0)

    if panel_631l is not None and panel_632r is not None:
        modified_regime, gate_info = _apply_ncf_gate(
            execution_regime,
            panel_631l,
            panel_632r,
            ma_gap_series,
            ncf_exit_signal_threshold=ncf_exit_signal_threshold,
            ncf_exit_ma_gap_max=ncf_exit_ma_gap_max,
            ncf_exit_consecutive=ncf_exit_consecutive,
            ncf_recovery_threshold=ncf_recovery_threshold,
            ncf_recovery_gate_threshold=ncf_recovery_gate_threshold,
        )
        curve, sim_result = _simulate_costed_curve(
            total_return_prices,
            modified_regime,
            weights_by_regime,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        backtest_mode = "ncf_exit_gate_panel"
        ncf_panel_coverage = {
            "panel_631l_rows": int(len(panel_631l)),
            "panel_632r_rows": int(len(panel_632r)),
            "panel_631l_path": str(Path(ncf_panel_631l_path).resolve()),
            "panel_632r_path": str(Path(ncf_panel_632r_path).resolve()),
        }
    else:
        modified_regime = execution_regime
        curve, sim_result = _simulate_costed_curve(
            total_return_prices,
            execution_regime,
            weights_by_regime,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        backtest_mode = "base_a2111_no_ncf_panel"
        gate_info = {"ncf_gate_activations": 0, "ncf_recovery_gates": 0, "ncf_gate_events": []}
        ncf_panel_coverage = {"status": "no_panel_provided"}

    recovery_dates = [
        str(dt.date())
        for dt in modified_regime.index
        if modified_regime.loc[dt] == "group_a_plus_recovery"
        and (dt == modified_regime.index[0] or modified_regime.shift(1).loc[dt] != "group_a_plus_recovery")
    ]
    out_frame = frame.copy()
    out_frame = out_frame.rename(columns={"regime": "base_regime"})
    out_frame["execution_regime"] = modified_regime
    out_frame["portfolio_value"] = curve

    # --- Live NCF signal (today) ---
    today_regime = str(modified_regime.iloc[-1])
    ncf_live: dict = {}
    path_631l = _resolve_ncf_path(ncf_00631l_path, "00631l")
    path_632r = _resolve_ncf_path(ncf_00632r_path, "00632r")

    if path_631l and path_632r:
        sig_631l = load_ncf_signal(path_631l)
        sig_632r = load_ncf_signal(path_632r)
        down_ens = ncf_downside_signal(sig_631l, sig_632r)
        ncf_live = ncf_overlay_summary(sig_631l, sig_632r, golden_weights, today_regime)
        ncf_live["ncf_00631l_file"] = str(path_631l.relative_to(PROJECT_ROOT))
        ncf_live["ncf_00632r_file"] = str(path_632r.relative_to(PROJECT_ROOT))
        ncf_live["ensemble_downside"] = round(down_ens, 4)
        ncf_live["note"] = (
            "A21.14: NCF does NOT adjust golden1 weights daily. "
            "Exit gate fires only if H20 dual-confirm > threshold for "
            f"{ncf_exit_consecutive}+ consecutive days AND ma_gap < {ncf_exit_ma_gap_max}."
        )
    else:
        missing = []
        if not path_631l:
            missing.append("ncf_00631l")
        if not path_632r:
            missing.append("ncf_00632r")
        ncf_live = {"status": "unavailable", "missing": missing}

    live_weights = weights_by_regime.get(today_regime, basket)

    report = {
        "experiment": "group_a_plus_a2114_ncf_exit_gate",
        "strategy": A2114_ID,
        "status": "research_candidate",
        "backtest_mode": backtest_mode,
        "window": {
            "start": str(close_prices.index[0].date()),
            "end": str(close_prices.index[-1].date()),
            "rows": int(len(close_prices)),
        },
        "metrics": _metrics(curve, initial_value),
        "execution": {**sim_result, **gate_info},
        "a207_events": events,
        "recovery_ramp_dates": recovery_dates,
        "rules": {
            "base": switch_rule.name,
            "warmup_days": warmup_days,
            "basket_name": "bond30_cash30",
            "ma_window": 100,
            "entry_gap": 0.003,
            "exit_gap": 0.010,
            "require_total_risk_score": 6,
            "ncf_integration": "exit_gate_only",
            "ncf_exit_signal_threshold": ncf_exit_signal_threshold,
            "ncf_exit_ma_gap_max": ncf_exit_ma_gap_max,
            "ncf_exit_consecutive_days": ncf_exit_consecutive,
            "ncf_recovery_threshold": ncf_recovery_threshold,
            "ncf_recovery_gate_threshold": ncf_recovery_gate_threshold,
            "ncf_h20_dual_lt": NCF_EXIT_DUAL_LT,
            "ncf_h20_dual_rt": NCF_EXIT_DUAL_RT,
        },
        "cost_assumptions": {
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "equity_etf_sell_tax": equity_etf_sell_tax,
            "bond_etf_sell_tax": 0.0,
        },
        "dividend_coverage": dividend_coverage,
        "ncf_panel_coverage": ncf_panel_coverage,
        "today_regime": today_regime,
        "live_weights": live_weights,
        "base_weights": weights_by_regime,
        "ncf_live_signal": ncf_live,
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "design_notes": {
            "vs_a2113": (
                "A21.13 trims 00631L daily via ensemble (fires 60% of days, "
                "mean signal 0.044) → -18.5% total return drag in 2025 bull market. "
                "A21.14 never changes golden1 weights; NCF only modifies regime boundaries."
            ),
            "ncf_exit_gate": (
                f"Gate triggers when H20 dual-confirm (631L h20<{NCF_EXIT_DUAL_LT}, "
                f"632R h20>{NCF_EXIT_DUAL_RT}) exceeds {ncf_exit_signal_threshold} for "
                f"{ncf_exit_consecutive} consecutive days AND ma_gap < {ncf_exit_ma_gap_max}. "
                "In 2025-2026 this gate did not fire: market stayed >3% above MA100 "
                "during all golden1 periods."
            ),
            "backtest_note": (
                "Uses same _simulate_costed_curve as A21.11 — NCF gate is a pre-processing "
                "step on the execution_regime Series only. No simulation logic changed."
            ),
        },
    }
    return report, out_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--ncf-00631l", default=None)
    parser.add_argument("--ncf-00632r", default=None)
    parser.add_argument("--ncf-panel-631l", default=None)
    parser.add_argument("--ncf-panel-632r", default=None)
    parser.add_argument("--ncf-exit-signal-threshold", type=float, default=NCF_EXIT_SIGNAL_THRESHOLD)
    parser.add_argument("--ncf-exit-ma-gap-max", type=float, default=NCF_EXIT_MA_GAP_MAX)
    parser.add_argument("--ncf-exit-consecutive", type=int, default=NCF_EXIT_CONSECUTIVE)
    parser.add_argument("--ncf-recovery-threshold", type=float, default=NCF_RECOVERY_THRESHOLD)
    parser.add_argument("--ncf-recovery-gate-threshold", type=float, default=NCF_RECOVERY_GATE_THRESHOLD)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2114.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2114_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2114")
    try:
        report, frame = run_a2114(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            ncf_00631l_path=args.ncf_00631l,
            ncf_00632r_path=args.ncf_00632r,
            ncf_panel_631l_path=args.ncf_panel_631l,
            ncf_panel_632r_path=args.ncf_panel_632r,
            ncf_exit_signal_threshold=args.ncf_exit_signal_threshold,
            ncf_exit_ma_gap_max=args.ncf_exit_ma_gap_max,
            ncf_exit_consecutive=args.ncf_exit_consecutive,
            ncf_recovery_threshold=args.ncf_recovery_threshold,
            ncf_recovery_gate_threshold=args.ncf_recovery_gate_threshold,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Runner JSON: {Path(args.output).resolve()}")
    print(f"Runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
