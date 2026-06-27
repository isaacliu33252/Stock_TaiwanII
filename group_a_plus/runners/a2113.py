"""A21.13 runner — A21.11 + NCF Live Overlay.

Extends A21.11 (MA100 + bond30_cash30 + tight entry) with a real-time NCF
(Next Close Forecast) overlay on the 00631L allocation within the golden1 regime.

Architecture
------------
Historical regime backtesting:  identical to A21.11 (Switch Rule + bond30_cash30)
Live signal enhancement (today): NCF overlay adjusts golden1 weights

The NCF overlay cannot be applied historically because ncf_00631l / ncf_00632r are
point-in-time model outputs — they are not stored as a daily panel for the full
backtest window.  The backtest metrics in this runner therefore match A21.11 exactly.
The value-add is in the *live daily signal*: when both NCF models agree that 00631L
is heading down, the system trims the 2x-leverage allocation before the MA100 rule
would trigger a full defensive switch.

Golden1 weight adjustment logic
--------------------------------
downside_signal = 0.6 × l_bear + 0.4 × r_bull
  l_bear = max(0, 0.5 − P(00631L UP)) × 2 × conf(00631L)
  r_bull = max(0, P(00632R UP) − 0.5) × 2 × conf(00632R)

adjusted_00631l = base_00631l × (1 − 0.5 × downside_signal)
freed_budget    → cash

Example: base golden1 = {0050: 60%, 00631L: 20%, cash: 20%}
  If downside_signal = 0.6:
    00631L = 20% × (1 − 0.5 × 0.6) = 20% × 0.7 = 14%
    cash   = 20% + 6% = 26%

Required NCF files (resolved in priority order):
  1. Explicit --ncf-00631l / --ncf-00632r CLI arguments
  2. results/ncf_00631l_YYYYMMDD.json (today's date)
  3. Most-recent ncf_00631l_YYYYMMDD.json in results/
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
    adjust_golden1_weights,
    load_ncf_signal,
    ncf_downside_signal,
    ncf_overlay_summary,
)
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2111 import _build_switch_rule
from tw_output_standard import OutputStandardizer, write_standard_output


A2113_ID = "a2113_a2111_ncf_overlay"

_EQUITY_TICKERS = {"0050.TW", "00631L.TW", "00632R.TW"}


def _resolve_ncf_path(explicit: str | None, ticker_tag: str) -> Path | None:
    """Find the best NCF file for a given ticker tag (e.g. '00631l' or '00632r').

    Priority:
      1. Explicit path from CLI
      2. results/ncf_{ticker_tag}_{today}.json
      3. Most-recent results/ncf_{ticker_tag}_YYYYMMDD.json
    """
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
    """Load a val-prediction panel CSV produced by ncf_00631l/ncf_00632r --val-predictions-output."""
    if path is None or not path.exists():
        return None
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _ncf_weights_for_day(
    d: pd.Timestamp,
    base_golden1: dict[str, float],
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
) -> dict[str, float]:
    """Return NCF-adjusted golden1 weights for a single day; falls back to base weights if signal unavailable."""
    if panel_631l is None or panel_632r is None:
        return base_golden1
    if d not in panel_631l.index or d not in panel_632r.index:
        return base_golden1
    row_l = panel_631l.loc[d]
    row_r = panel_632r.loc[d]
    sig_l = {
        "calibrated_prob_up": float(row_l["ensemble_prob_up"]),
        "confidence": float(row_l["confidence"]),
    }
    sig_r = {
        "calibrated_prob_up": float(row_r["ensemble_prob_up"]),
        "confidence": float(row_r["confidence"]),
    }
    down = ncf_downside_signal(sig_l, sig_r)
    return adjust_golden1_weights(base_golden1, down)


def _simulate_ncf_overlay_curve(
    total_return_prices: pd.DataFrame,
    execution_regime: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    panel_631l: pd.DataFrame | None,
    panel_632r: pd.DataFrame | None,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict]:
    """Per-day portfolio simulation with NCF overlay on golden1 weights.

    Transaction costs are charged on regime switches only. NCF micro-rebalances
    within golden1 incur no additional cost (approximation; error is negligible for
    small daily allocation changes).
    """
    aligned_dates = execution_regime.index[execution_regime.index.isin(total_return_prices.index)]

    values = [initial_value]
    prev_w: dict[str, float] = {}
    prev_regime: str | None = None
    tx_events: list[dict] = []

    for i, d in enumerate(aligned_dates[:-1]):
        d_next = aligned_dates[i + 1]
        regime = str(execution_regime.loc[d])

        if regime == "golden1":
            w = _ncf_weights_for_day(d, weights_by_regime["golden1"], panel_631l, panel_632r)
        else:
            w = weights_by_regime.get(regime, weights_by_regime["group_a_plus_defensive"])

        if prev_regime is not None and regime != prev_regime:
            cost = 0.0
            for ticker, wt in prev_w.items():
                if ticker == "cash" or wt <= 0:
                    continue
                rate = commission_rate + slippage_rate
                if ticker in _EQUITY_TICKERS:
                    rate += equity_etf_sell_tax
                cost += wt * rate
            for ticker, wt in w.items():
                if ticker == "cash" or wt <= 0:
                    continue
                cost += wt * (commission_rate + slippage_rate)
            values[-1] *= (1.0 - cost)
            tx_events.append({
                "date": str(d.date()),
                "from_regime": prev_regime,
                "to_regime": regime,
                "estimated_cost": round(cost, 6),
            })

        day_ret = 0.0
        for ticker, wt in w.items():
            if ticker == "cash" or wt <= 0:
                continue
            if ticker in total_return_prices.columns:
                p0 = total_return_prices.at[d, ticker]
                p1 = total_return_prices.at[d_next, ticker]
                if p0 > 0:
                    day_ret += wt * (p1 / p0 - 1.0)

        values.append(values[-1] * (1.0 + day_ret))
        prev_w = dict(w)
        prev_regime = regime

    curve = pd.Series(values, index=aligned_dates[: len(values)])
    return curve, {"transaction_events": tx_events, "total_switches": len(tx_events)}


def run_a2113(
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
    """Run A21.13: A21.11 regime logic + NCF live overlay on golden1 weights.

    When ncf_panel_631l_path and ncf_panel_632r_path are provided, the historical
    backtest uses per-day NCF-adjusted golden1 weights (true A21.13 backtest).
    Otherwise the historical backtest is identical to A21.11.
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

    if panel_631l is not None and panel_632r is not None:
        curve, execution = _simulate_ncf_overlay_curve(
            total_return_prices,
            execution_regime,
            weights_by_regime,
            panel_631l,
            panel_632r,
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        backtest_mode = "ncf_panel_overlay"
        ncf_panel_coverage = {
            "panel_631l_rows": int(len(panel_631l)),
            "panel_632r_rows": int(len(panel_632r)),
            "panel_631l_path": str(Path(ncf_panel_631l_path).resolve()),
            "panel_632r_path": str(Path(ncf_panel_632r_path).resolve()),
        }
    else:
        curve, execution = _simulate_costed_curve(
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
        for dt in execution_regime.index
        if execution_regime.loc[dt] == "group_a_plus_recovery"
        and (dt == execution_regime.index[0] or execution_regime.shift(1).loc[dt] != "group_a_plus_recovery")
    ]
    out_frame = frame.copy()
    out_frame = out_frame.rename(columns={"regime": "base_regime"})
    out_frame["execution_regime"] = execution_regime
    out_frame["portfolio_value"] = curve

    # --- NCF overlay: today's adjusted golden1 weights ---
    today_regime = str(execution_regime.iloc[-1])
    ncf_overlay: dict = {}
    ncf_adjusted_golden1: dict = dict(golden_weights)

    path_631l = _resolve_ncf_path(ncf_00631l_path, "00631l")
    path_632r = _resolve_ncf_path(ncf_00632r_path, "00632r")

    if path_631l and path_632r:
        sig_631l = load_ncf_signal(path_631l)
        sig_632r = load_ncf_signal(path_632r)
        down = ncf_downside_signal(sig_631l, sig_632r)
        ncf_adjusted_golden1 = adjust_golden1_weights(golden_weights, down)
        ncf_overlay = ncf_overlay_summary(sig_631l, sig_632r, golden_weights, today_regime)
        ncf_overlay["ncf_00631l_file"] = str(path_631l.relative_to(PROJECT_ROOT))
        ncf_overlay["ncf_00632r_file"] = str(path_632r.relative_to(PROJECT_ROOT))
    else:
        missing = []
        if not path_631l:
            missing.append("ncf_00631l")
        if not path_632r:
            missing.append("ncf_00632r")
        ncf_overlay = {"status": "unavailable", "missing": missing}

    # Effective live weights (what to hold today)
    if today_regime == "golden1":
        live_weights = ncf_adjusted_golden1
    elif today_regime == "group_a_plus_defensive":
        live_weights = basket
    else:
        live_weights = current_defensive

    report = {
        "experiment": "group_a_plus_a2113_a2111_ncf_overlay",
        "strategy": A2113_ID,
        "status": "research_candidate",
        "backtest_mode": backtest_mode,
        "window": {
            "start": str(close_prices.index[0].date()),
            "end": str(close_prices.index[-1].date()),
            "rows": int(len(close_prices)),
        },
        "metrics": _metrics(curve, initial_value),
        "execution": execution,
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
            "ncf_overlay": "00631L weight trimmed in golden1 when downside_signal > 0",
            "ncf_max_reduction_fraction": 0.5,
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
        "ncf_overlay": ncf_overlay,
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
        "design_notes": {
            "backtest_note": (
                "When NCF panels are provided (--ncf-panel-631l / --ncf-panel-632r), "
                "the historical backtest uses per-day NCF-adjusted golden1 weights "
                "(backtest_mode=ncf_panel_overlay). Without panels, backtest == A21.11 "
                "(backtest_mode=base_a2111_no_ncf_panel)."
            ),
            "live_value": (
                "When both NCF models signal downside (downside_signal > 0), 00631L is trimmed "
                "by up to 50% of its base allocation and the freed budget moves to cash. "
                "This acts as an early partial hedge before the MA100 rule triggers a full switch."
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
    parser.add_argument("--ncf-00631l", default=None, help="path to ncf_00631l JSON (default: auto-detect)")
    parser.add_argument("--ncf-00632r", default=None, help="path to ncf_00632r JSON (default: auto-detect)")
    parser.add_argument("--ncf-panel-631l", default=None, help="val-prediction panel CSV for 00631L (enables NCF historical backtest)")
    parser.add_argument("--ncf-panel-632r", default=None, help="val-prediction panel CSV for 00632R (enables NCF historical backtest)")
    parser.add_argument("--output", default="results/group_a_plus_runner_a2113.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2113_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2113")
    try:
        report, frame = run_a2113(
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
