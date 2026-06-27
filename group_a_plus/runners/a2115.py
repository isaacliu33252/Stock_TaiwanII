"""A21.15 runner — A21.11 + Dual-Mode NCF Gate (near-MA + late-bull).

Fixes two problems with A21.14:

Problem 1 — A21.14 gate never fires in deep bull:
  A21.14 requires ma_gap < 3% to trigger. In 2025-2026 the market stayed
  >10% above MA100 during all golden1 periods → gate never activated.

Problem 2 — A21.14 uses 00632R in late-bull where it is unreliable:
  00632R retraining (2026-06-26) revealed that its direction AUC in late-bull
  (ma_gap > 15%) is 0.46 and 0.44 for H=5 and H=20 — WORSE than random.
  Using 00632R signal there adds noise and can SUPPRESS a valid 00631L signal.

A21.15 solution — Two-mode gate:

  Mode A: Near-MA gate (ma_gap < NCF_NEAR_MA_GAP_MAX)
    Same as A21.14: dual-confirm (631L H20 bearish + 632R H20 bullish),
    requires 3 consecutive days, switches regime to group_a_plus_defensive.
    Rationale: near MA100 the market is likely to cross below; full exit makes sense.

  Mode B: Late-bull gate (ma_gap > NCF_LB_MA_GAP_MIN)
    Single-confirm using ONLY 00631L H20 (00632R excluded because AUC < 0.5).
    Condition: prob_up_h20 < 0.45 AND confidence > 0.55.
    No consecutive requirement (high late-bull H20 AUC = 0.85 supports single day).
    Action: de-leverage to {0050: 70%, 00631L: 10%, cash: 20%} for that day.
    Rationale: 75% MDD>5% precision in late-bull; market usually recovers,
    so de-leverage (not full exit) preserves upside participation.

NCF data requirements:
  Mode A: both 00631L and 00632R panels
  Mode B: only 00631L panel (00632R panel ignored in late-bull)
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
from group_a_plus.integrations.ncf import load_ncf_signal, ncf_overlay_summary
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2111 import _build_switch_rule
from tw_output_standard import OutputStandardizer, write_standard_output


A2115_ID = "a2115_a2111_ncf_dual_mode_gate"

# ── Mode A: Near-MA dual-confirm (A21.14 logic, now with wider gap tolerance) ──
NCF_NEAR_MA_GAP_MAX = 0.05    # only consider dual-confirm when ≤ 5% above MA100
NCF_NEAR_DUAL_LT = 0.40       # 631L H20 prob_up < this (bearish)
NCF_NEAR_DUAL_RT = 0.60       # 632R H20 prob_up > this (inverse bullish = market bearish)
NCF_NEAR_SIGNAL_THR = 0.35    # combined signal must exceed this
NCF_NEAR_CONSECUTIVE = 3      # sustained signal: ≥ 3 consecutive days
NCF_NEAR_RECOVERY_THR = 0.25  # gate clears when signal < this for ≥ 2 days
NCF_NEAR_REENTRY_THR = 0.30   # delay re-entry if signal ≥ this

# ── Mode B: Late-bull single-confirm (00631L only) ──────────────────────────
NCF_LB_MA_GAP_MIN = 0.15      # only consider in late-bull (> 15% above MA100)
NCF_LB_H20_MAX = 0.45         # 631L H20 prob_up < this (bearish)
NCF_LB_CONF_MIN = 0.55        # 631L confidence > this

# De-leverage basket: half of 00631L moved to 0050
# Base golden1: {0050: 60%, 00631L: 20%, cash: 20%}
LATE_BULL_HEDGE_WEIGHTS = {
    "0050.TW": 0.70,
    "00631L.TW": 0.10,
    "00632R.TW": 0.00,
    "00679B.TWO": 0.00,
    "cash": 0.20,
}
NCF_LB_REGIME = "ncf_late_bull_hedge"


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


def _near_ma_dual_signal(
    d: pd.Timestamp,
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
    lt: float = NCF_NEAR_DUAL_LT,
    rt: float = NCF_NEAR_DUAL_RT,
) -> float:
    """Mode A dual-confirm signal. Returns 0 unless BOTH ETFs agree (bearish market)."""
    if panel_631l is None or panel_632r is None:
        return 0.0
    if d not in panel_631l.index or d not in panel_632r.index:
        return 0.0
    l_h20 = float(panel_631l.loc[d, "prob_up_h20"])
    r_col = "prob_up_h20" if "prob_up_h20" in panel_632r.columns else "h20_prob_up"
    r_h20 = float(panel_632r.loc[d, r_col])
    if l_h20 < lt and r_h20 > rt:
        return 0.6 * max(0.0, 0.5 - l_h20) * 2.0 + 0.4 * max(0.0, r_h20 - 0.5) * 2.0
    return 0.0


def _late_bull_single_trigger(
    d: pd.Timestamp,
    panel_631l: pd.DataFrame | None,
    ma_gap: float,
) -> bool:
    """Mode B single-confirm (00631L only). True when all late-bull conditions met."""
    if panel_631l is None or d not in panel_631l.index:
        return False
    if ma_gap <= NCF_LB_MA_GAP_MIN:
        return False
    h20 = float(panel_631l.loc[d, "prob_up_h20"])
    conf = float(panel_631l.loc[d, "confidence"])
    return h20 < NCF_LB_H20_MAX and conf > NCF_LB_CONF_MIN


def _apply_dual_mode_gate(
    execution_regime: pd.Series,
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
    ma_gap_series: pd.Series,
    near_ma_gap_max: float = NCF_NEAR_MA_GAP_MAX,
    near_signal_thr: float = NCF_NEAR_SIGNAL_THR,
    near_consecutive: int = NCF_NEAR_CONSECUTIVE,
    near_recovery_thr: float = NCF_NEAR_RECOVERY_THR,
    near_reentry_thr: float = NCF_NEAR_REENTRY_THR,
) -> tuple[pd.Series, dict]:
    """Pre-process execution_regime with two-mode NCF gate.

    Mode A (near-MA): dual-confirm → group_a_plus_defensive
    Mode B (late-bull): single-confirm (631L only) → ncf_late_bull_hedge

    Reuses _simulate_costed_curve unchanged — only execution_regime changes.
    """
    if panel_631l is None:
        return execution_regime.copy(), {
            "mode_a_activations": 0,
            "mode_b_activations": 0,
            "mode_a_events": [],
            "mode_b_events": [],
            "ncf_recovery_gates": 0,
        }

    modified = execution_regime.copy()
    consec_signal = 0
    consec_clear = 0
    near_gate_active = False
    mode_a_events: list[dict] = []
    mode_b_events: list[dict] = []
    recovery_gates = 0
    prev_effective: str | None = None

    for d in execution_regime.index:
        a2111_regime = str(execution_regime.loc[d])
        ma_gap = float(ma_gap_series.get(d, 0.0))

        # ── Mode A signal (near-MA dual-confirm) ──
        near_dual = _near_ma_dual_signal(d, panel_631l, panel_632r)
        near_eligible = ma_gap < near_ma_gap_max

        if near_eligible and near_dual > near_signal_thr:
            consec_signal += 1
            consec_clear = 0
        else:
            consec_signal = 0
            if near_dual < near_recovery_thr:
                consec_clear += 1
            else:
                consec_clear = 0

        # Gate ON
        if (
            not near_gate_active
            and a2111_regime == "golden1"
            and consec_signal >= near_consecutive
            and near_eligible
        ):
            near_gate_active = True
            mode_a_events.append({
                "date": str(d.date()), "event": "mode_a_gate_ON",
                "dual_signal": round(near_dual, 4), "ma_gap": round(ma_gap, 4),
                "consecutive_days": consec_signal,
            })

        # Gate OFF (hysteresis: 2 clear days)
        if near_gate_active and consec_clear >= 2:
            near_gate_active = False
            mode_a_events.append({
                "date": str(d.date()), "event": "mode_a_gate_OFF",
                "dual_signal": round(near_dual, 4),
            })

        # ── Mode B trigger (late-bull single-confirm) ──
        lb_triggered = (
            a2111_regime == "golden1"
            and not near_gate_active
            and _late_bull_single_trigger(d, panel_631l, ma_gap)
        )

        # ── Determine effective regime ──
        if a2111_regime == "golden1" and near_gate_active:
            effective = "group_a_plus_defensive"
        elif lb_triggered:
            effective = NCF_LB_REGIME
            mode_b_events.append({
                "date": str(d.date()),
                "ma_gap": round(ma_gap, 4),
                "prob_up_h20": round(float(panel_631l.loc[d, "prob_up_h20"]), 4),
                "confidence": round(float(panel_631l.loc[d, "confidence"]), 4),
            })
        elif (
            a2111_regime == "golden1"
            and near_dual > near_reentry_thr
            and prev_effective in ("group_a_plus_defensive", "group_a_plus_recovery")
        ):
            # Delay re-entry if Mode A signal still elevated
            effective = prev_effective
            recovery_gates += 1
            mode_a_events.append({
                "date": str(d.date()), "event": "mode_a_recovery_gate",
                "dual_signal": round(near_dual, 4), "held_in": prev_effective,
            })
        else:
            effective = a2111_regime

        modified.loc[d] = effective
        prev_effective = effective

    return modified, {
        "mode_a_activations": sum(1 for e in mode_a_events if e.get("event") == "mode_a_gate_ON"),
        "mode_b_activations": len(mode_b_events),
        "mode_a_events": mode_a_events,
        "mode_b_events": mode_b_events,
        "ncf_recovery_gates": recovery_gates,
    }


def run_a2115(
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
) -> tuple[dict, pd.DataFrame]:
    """Run A21.15: A21.11 + dual-mode NCF gate."""
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
        NCF_LB_REGIME: _normalize(LATE_BULL_HEDGE_WEIGHTS),
    }

    panel_631l = _load_ncf_panel(Path(ncf_panel_631l_path) if ncf_panel_631l_path else None)
    panel_632r = _load_ncf_panel(Path(ncf_panel_632r_path) if ncf_panel_632r_path else None)
    ma_gap_series = frame["ma_gap"].reindex(execution_regime.index).fillna(0.0)

    if panel_631l is not None:
        modified_regime, gate_info = _apply_dual_mode_gate(
            execution_regime, panel_631l, panel_632r, ma_gap_series,
        )
        curve, sim_result = _simulate_costed_curve(
            total_return_prices, modified_regime, weights_by_regime,
            initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
        )
        backtest_mode = "ncf_dual_mode_gate"
        ncf_panel_coverage = {
            "panel_631l_rows": int(len(panel_631l)),
            "panel_632r_rows": int(len(panel_632r)) if panel_632r is not None else 0,
        }
    else:
        modified_regime = execution_regime
        gate_info = {"mode_a_activations": 0, "mode_b_activations": 0,
                     "mode_a_events": [], "mode_b_events": [], "ncf_recovery_gates": 0}
        curve, sim_result = _simulate_costed_curve(
            total_return_prices, execution_regime, weights_by_regime,
            initial_value, commission_rate, slippage_rate, equity_etf_sell_tax,
        )
        backtest_mode = "base_a2111_no_ncf_panel"
        ncf_panel_coverage = {"status": "no_panel_provided"}

    recovery_dates = [
        str(dt.date()) for dt in modified_regime.index
        if modified_regime.loc[dt] == "group_a_plus_recovery"
        and (dt == modified_regime.index[0] or modified_regime.shift(1).loc[dt] != "group_a_plus_recovery")
    ]
    out_frame = frame.copy()
    out_frame = out_frame.rename(columns={"regime": "base_regime"})
    out_frame["execution_regime"] = modified_regime
    out_frame["portfolio_value"] = curve

    # Live NCF signal
    today_regime = str(modified_regime.iloc[-1])
    ncf_live: dict = {}
    path_631l = _resolve_ncf_path(ncf_00631l_path, "00631l")
    path_632r = _resolve_ncf_path(ncf_00632r_path, "00632r")
    today_ma_gap = float(ma_gap_series.iloc[-1]) if len(ma_gap_series) > 0 else 0.0

    if path_631l and path_632r:
        sig_631l = load_ncf_signal(path_631l)
        sig_632r = load_ncf_signal(path_632r)
        h20_prob = float(sig_631l.get("prob_up_h20", sig_631l.get("calibrated_prob_up", 0.5)))
        conf = float(sig_631l.get("confidence", 0.0))
        lb_live = today_ma_gap > NCF_LB_MA_GAP_MIN and h20_prob < NCF_LB_H20_MAX and conf > NCF_LB_CONF_MIN
        ncf_live = ncf_overlay_summary(sig_631l, sig_632r, golden_weights, today_regime)
        ncf_live.update({
            "ncf_00631l_file": str(path_631l.relative_to(PROJECT_ROOT)),
            "ncf_00632r_file": str(path_632r.relative_to(PROJECT_ROOT)),
            "today_ma_gap": round(today_ma_gap, 4),
            "mode_b_late_bull_triggered": lb_live,
            "note": (
                f"Mode A (near-MA ma_gap<{NCF_NEAR_MA_GAP_MAX}): dual-confirm → defensive. "
                f"Mode B (late-bull ma_gap>{NCF_LB_MA_GAP_MIN}): 631L-only → de-leverage."
                + (" [Mode B ACTIVE today]" if lb_live else "")
            ),
        })
    else:
        ncf_live = {"status": "unavailable"}

    live_weights = weights_by_regime.get(today_regime, basket)

    report = {
        "experiment": "group_a_plus_a2115_ncf_dual_mode_gate",
        "strategy": A2115_ID,
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
            "ncf_integration": "dual_mode_gate",
            "mode_a_near_ma": {
                "ma_gap_max": NCF_NEAR_MA_GAP_MAX,
                "dual_lt": NCF_NEAR_DUAL_LT,
                "dual_rt": NCF_NEAR_DUAL_RT,
                "signal_thr": NCF_NEAR_SIGNAL_THR,
                "consecutive": NCF_NEAR_CONSECUTIVE,
                "action": "switch_to_group_a_plus_defensive",
            },
            "mode_b_late_bull": {
                "ma_gap_min": NCF_LB_MA_GAP_MIN,
                "h20_max": NCF_LB_H20_MAX,
                "conf_min": NCF_LB_CONF_MIN,
                "etf_used": "00631L_only (00632R excluded: AUC<0.5 in late-bull)",
                "action": "switch_to_ncf_late_bull_hedge",
                "hedge_weights": _normalize(LATE_BULL_HEDGE_WEIGHTS),
            },
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
            "vs_a2114": (
                "A21.14 required ma_gap < 3% (never fired in 2025-2026). "
                "A21.15 Mode A uses ma_gap < 5%; Mode B adds late-bull (ma_gap > 15%) "
                "using 00631L only (00632R excluded: H20 AUC 0.44-0.46 in late-bull)."
            ),
            "vs_a2118": (
                "A21.18 is Mode B only. A21.15 combines Mode A (near-MA full exit) "
                "and Mode B (late-bull de-leverage) in a single runner."
            ),
            "00632r_late_bull_note": (
                "00632R retraining 2026-06-26 confirmed: direction AUC in late-bull "
                "(ma_gap>15%) = 0.46 (H=5), 0.44 (H=20) — worse than random. "
                "Mode B therefore ignores 00632R direction signal entirely."
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
    parser.add_argument("--output", default="results/group_a_plus_runner_a2115.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2115_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2115")
    try:
        report, frame = run_a2115(
            args.start, args.end, args.initial_value, Path(args.db),
            args.warmup_days, args.commission_rate, args.slippage_rate,
            args.equity_etf_sell_tax,
            ncf_00631l_path=args.ncf_00631l,
            ncf_00632r_path=args.ncf_00632r,
            ncf_panel_631l_path=args.ncf_panel_631l,
            ncf_panel_632r_path=args.ncf_panel_632r,
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
