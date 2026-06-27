"""A21.18 runner — A21.11 + NCF Late-Bull De-Leverage Overlay.

Problem solved
--------------
A21.14 (NCF exit gate) required ma_gap < 3% to fire — the OPPOSITE of where NCF
is most informative. Retraining revealed that NCF H20 AUC is highest in the
late-bull regime (ma_gap > 10%): AUC 0.70 at H=5, AUC 0.85 at H=20.

In 336 historical days (2025-01-02 ~ 2026-05-27), the late-bull bearish trigger
(ma_gap > 10%, prob_up_h20 < 0.45, confidence > 0.55) fired 4 times:
  - 75% had MDD > 5% (vs 35.4% baseline in late-bull)
  - 75% ALSO had gain > 5% at 20d (sharp drop then rally)
  - Mean forward MDD: -8.85%  Mean forward gain: +15.89%

The correct response to this pattern is de-leverage (reduce 00631L risk), NOT exit
to cash (which would miss the recovery rally).

Architecture
------------
Historical regime: identical to A21.11 (MA100 switch + bond30_cash30 basket).
Late-bull overlay: when trigger fires inside golden1, override execution_regime to
  "ncf_late_bull_hedge" (shares-tracked by _simulate_costed_curve).
  LATE_BULL_HEDGE = {0050: 70%, 00631L: 10%, cash: 20%}

Implementation approach (important design note)
------------------------------------------------
Uses SAME _simulate_costed_curve as A21.11. Pre-processing step modifies the
execution_regime Series: trigger days inside golden1 become "ncf_late_bull_hedge".
This ensures share-tracking (not daily-rebalanced returns), which matches the
A21.11 simulation baseline exactly on non-trigger days.

Transaction costs ARE charged for golden1 → ncf_late_bull_hedge switches (~0.048%
round-trip per trigger day). This is conservative and accurate.

Trigger conditions:
  ma_gap > NCF_LB_MA_GAP_MIN (default 0.10)   — deep into late-bull
  prob_up_h20 < NCF_LB_H20_MAX   (default 0.45) — NCF expects 20d down
  confidence > NCF_LB_CONF_MIN   (default 0.55) — model is confident

vs A21.13: fires 60% of days (continuous ensemble signal, -18.5% drag in 2025)
vs A21.14: exit gate near MA100 only (ma_gap < 3%); never fired in 2025-2026
vs A21.18: fires 1.2% of days (4/336), targets deep late-bull bearish only

Design choice — 0050 not cash:
  Since 75% of trigger days also had gain>5% at 20d, staying partially in
  equities (via 0050) captures the recovery while reducing 2x-leverage exposure.
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


A2118_ID = "a2118_a2111_ncf_late_bull_deleverage"

# Late-bull NCF trigger conditions (confirmed from panel analysis 2025-01 ~ 2026-05)
NCF_LB_MA_GAP_MIN = 0.10    # price > 10% above MA100 (late-bull regime)
NCF_LB_H20_MAX = 0.45       # NCF H20 prob_up < 45% (expects drop)
NCF_LB_CONF_MIN = 0.55      # model confidence > 55%

# De-leveraged golden1 basket: replace half of 00631L weight with 0050
# Base golden1: {0050: 60%, 00631L: 20%, cash: 20%}
# Hedge:        {0050: 70%, 00631L: 10%, cash: 20%}
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


def _apply_late_bull_overlay(
    execution_regime: pd.Series,
    panel_631l: pd.DataFrame | None,
    ma_gap_series: pd.Series,
    ma_gap_min: float = NCF_LB_MA_GAP_MIN,
    h20_max: float = NCF_LB_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
) -> tuple[pd.Series, dict]:
    """Pre-process execution_regime: override golden1 trigger days to ncf_late_bull_hedge.

    Reuses _simulate_costed_curve unchanged — only the regime input changes.
    This ensures share-tracking simulation identical to A21.11 on non-trigger days.
    """
    if panel_631l is None:
        return execution_regime.copy(), {
            "late_bull_trigger_days": 0,
            "late_bull_trigger_events": [],
        }

    modified = execution_regime.copy()
    trigger_events: list[dict] = []

    for d in execution_regime.index:
        if str(execution_regime.loc[d]) != "golden1":
            continue
        if d not in panel_631l.index:
            continue
        ma_gap = float(ma_gap_series.get(d, 0.0))
        if ma_gap <= ma_gap_min:
            continue
        h20_prob = float(panel_631l.loc[d, "prob_up_h20"])
        conf = float(panel_631l.loc[d, "confidence"])
        if h20_prob < h20_max and conf > conf_min:
            modified.loc[d] = NCF_LB_REGIME
            trigger_events.append({
                "date": str(d.date()),
                "ma_gap": round(ma_gap, 4),
                "prob_up_h20": round(h20_prob, 4),
                "confidence": round(conf, 4),
            })

    return modified, {
        "late_bull_trigger_days": len(trigger_events),
        "late_bull_trigger_events": trigger_events,
    }


def run_a2118(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    ncf_00631l_path: str | None = None,
    ncf_panel_631l_path: str | None = None,
    ma_gap_min: float = NCF_LB_MA_GAP_MIN,
    h20_max: float = NCF_LB_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.18: A21.11 base + NCF late-bull de-leverage overlay on golden1.

    When ncf_panel_631l_path is provided, the historical backtest uses the same
    _simulate_costed_curve as A21.11, with trigger days pre-converted to
    "ncf_late_bull_hedge" regime (share-tracked, not daily-rebalanced).
    Without the panel, backtest is identical to A21.11.
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
        NCF_LB_REGIME: _normalize(LATE_BULL_HEDGE_WEIGHTS),
    }

    panel_631l = _load_ncf_panel(
        Path(ncf_panel_631l_path) if ncf_panel_631l_path else None
    )
    ma_gap_series = frame["ma_gap"].reindex(execution_regime.index).fillna(0.0)

    if panel_631l is not None:
        modified_regime, overlay_info = _apply_late_bull_overlay(
            execution_regime,
            panel_631l,
            ma_gap_series,
            ma_gap_min=ma_gap_min,
            h20_max=h20_max,
            conf_min=conf_min,
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
        backtest_mode = "ncf_late_bull_regime_overlay"
        ncf_panel_coverage = {
            "panel_631l_rows": int(len(panel_631l)),
            "panel_631l_path": str(Path(ncf_panel_631l_path).resolve()),
        }
    else:
        modified_regime = execution_regime
        overlay_info = {"late_bull_trigger_days": 0, "late_bull_trigger_events": []}
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
    today_ma_gap = float(ma_gap_series.iloc[-1]) if len(ma_gap_series) > 0 else 0.0

    if path_631l:
        sig_631l = load_ncf_signal(path_631l)
        h20_prob = float(sig_631l.get("prob_up_h20", sig_631l.get("calibrated_prob_up", 0.5)))
        conf = float(sig_631l.get("confidence", 0.0))
        late_bull_triggered = (
            today_ma_gap > ma_gap_min
            and h20_prob < h20_max
            and conf > conf_min
        )
        ncf_live = {
            "ncf_00631l_file": str(path_631l.relative_to(PROJECT_ROOT)),
            "today_ma_gap": round(today_ma_gap, 4),
            "h20_prob_up": round(h20_prob, 4),
            "confidence": round(conf, 4),
            "late_bull_triggered": late_bull_triggered,
            "trigger_conditions": {
                "ma_gap_min": ma_gap_min,
                "h20_max": h20_max,
                "conf_min": conf_min,
            },
            "effective_weights": (
                _normalize(LATE_BULL_HEDGE_WEIGHTS)
                if today_regime == "golden1" and late_bull_triggered
                else dict(golden_weights)
            ),
        }
    else:
        ncf_live = {"status": "unavailable", "missing": "ncf_00631l"}

    live_weights = weights_by_regime.get(today_regime, basket)

    report = {
        "experiment": "group_a_plus_a2118_ncf_late_bull_deleverage",
        "strategy": A2118_ID,
        "status": "research_candidate",
        "backtest_mode": backtest_mode,
        "window": {
            "start": str(close_prices.index[0].date()),
            "end": str(close_prices.index[-1].date()),
            "rows": int(len(close_prices)),
        },
        "metrics": _metrics(curve, initial_value),
        "execution": {**sim_result, **overlay_info},
        "a207_events": events,
        "recovery_ramp_dates": recovery_dates,
        "rules": {
            "base": switch_rule.name,
            "warmup_days": warmup_days,
            "basket_name": "bond30_cash30",
            "ma_window": 100,
            "entry_gap": 0.003,
            "exit_gap": 0.010,
            "ncf_integration": "late_bull_deleverage_regime",
            "ncf_late_bull_ma_gap_min": ma_gap_min,
            "ncf_late_bull_h20_max": h20_max,
            "ncf_late_bull_conf_min": conf_min,
            "late_bull_hedge_regime": NCF_LB_REGIME,
            "late_bull_hedge_weights": _normalize(LATE_BULL_HEDGE_WEIGHTS),
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
            "simulation_note": (
                "Uses identical _simulate_costed_curve as A21.11. NCF overlay is a "
                "pre-processing step on execution_regime only: trigger days in golden1 "
                "become 'ncf_late_bull_hedge' regime. Share-tracked, not daily-rebalanced. "
                "Transaction costs charged on every regime switch (including hedge days)."
            ),
            "vs_a2114": (
                "A21.14 NCF gate fires near MA100 (ma_gap < 3%). "
                "A21.18 fires in deep late-bull (ma_gap > 10%) where NCF H20 AUC is highest. "
                "These are complementary: A21.14 catches regime-boundary risk, "
                "A21.18 catches in-regime late-bull corrections."
            ),
            "vs_a2113": (
                "A21.13 trims 00631L daily via ensemble (fires 60% of days). "
                "A21.18 fires only on extreme late-bull bearish (1.2% of days), "
                "and redirects freed weight to 0050 (not cash) to capture subsequent rallies."
            ),
            "signal_quality": (
                "Late-bull trigger (ma_gap>10%, h20<0.45, conf>0.55): 4 events in 336 days. "
                "75% MDD>5% (vs 35.4% base), 75% gain>5% at 20d. "
                "Confirms sharp-drop-then-rally pattern in late-bull corrections."
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
    parser.add_argument("--ncf-panel-631l", default=None,
                        help="val-prediction panel CSV for 00631L (enables NCF historical backtest)")
    parser.add_argument("--ma-gap-min", type=float, default=NCF_LB_MA_GAP_MIN)
    parser.add_argument("--h20-max", type=float, default=NCF_LB_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2118.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2118_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2118")
    try:
        report, frame = run_a2118(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            ncf_00631l_path=args.ncf_00631l,
            ncf_panel_631l_path=args.ncf_panel_631l,
            ma_gap_min=args.ma_gap_min,
            h20_max=args.h20_max,
            conf_min=args.conf_min,
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
