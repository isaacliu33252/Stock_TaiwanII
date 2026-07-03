"""Standardized runner for A21.11 candidate — Tight Entry + Bond Defensive Basket.

Combines A21.7 (tight entry / wide MA) with A21.4 (bond30_cash30 defensive basket):
  - entry_gap: 0.003  — stricter entry, reduces whipsaw in bull markets
  - ma_window: 100    — smoother trend signal
  - exit_gap:  0.010  — requires clear recovery before leaving defensive
  - basket:    bond30_cash30 (0050 40% / 00679B 30% / cash 30%)
               → lower MDD when defensive is triggered (vs cash30)

Rationale: A21.7 improvements and A21.4 improvements are orthogonal.
  A21.7 reduces FALSE defensive entries (whipsaw protection).
  A21.4 reduces DAMAGE when defensive is correctly triggered (bond cushion).
  Combining both should give additive benefit.

Baseline comparisons (2025-01-02 ~ 2026-06-18):
  A21.3 (baseline): Sharpe=2.449  MDD=-22.84%  Worst20d=-16.89%
  A21.4 (bond30c30 only): Sharpe=2.600  MDD=-14.76%  Worst20d=-9.72%
  A21.7 (tight entry only): Sharpe=2.66  MDD=-19.54%  rebal 8→2
  A21.11 (both): TBD — run this runner to evaluate
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import duckdb
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
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


A2111_ID = "a2111_tight_entry_bond30c30"
LATEST_GROUP_A_SIGNAL = PROJECT_ROOT / "results" / "group_a_combined_live_latest.json"


def _resolve_golden_signal_path() -> Path:
    candidates = []
    if LATEST_GROUP_A_SIGNAL.exists():
        candidates.append(LATEST_GROUP_A_SIGNAL)
    candidates.extend((PROJECT_ROOT / "results").glob("signal_group_a_*.json"))
    candidates = [
        path
        for path in candidates
        if path.exists()
        and not path.name.startswith("signal_group_a_tdcc")
        and "shareholding" not in path.name
    ]
    if not candidates:
        return _resolve(DEFAULT_GOLDEN_SIGNAL)
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _golden_signal_metadata(path: Path, golden_weights: dict[str, float]) -> dict:
    """Reproducibility metadata for the golden1 weights a backtest actually used.

    H3 (2026-07-02 Fable 5 audit): `_resolve_golden_signal_path()` picks
    whichever `signal_group_a_*.json` file has the newest mtime, so a
    backtest run today replays the *entire* history under *today's* golden1
    weights, not the weights that were actually in force on each historical
    date -- a drift channel distinct from (and in addition to) the known NCF
    panel weight drift. This does not change that resolution behavior (doing
    so would change live signal generation); it only makes the choice
    auditable, mirroring the existing `ncf_panel_coverage` sha256/mtime guard.
    """
    stat = path.stat()
    return {
        "golden_signal_path": str(path.resolve()),
        "golden_signal_sha256": _file_sha256(path),
        "golden_signal_modified_at": datetime.fromtimestamp(
            stat.st_mtime,
            timezone.utc,
        ).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "golden_weights": dict(golden_weights),
        "caveat": (
            "golden1 weights are resolved by newest-mtime among "
            "results/signal_group_a_*.json at backtest run time, not the "
            "weights actually in force on each historical date -- see H3 in "
            "GROUP_A_PLUS_FABLE5_AUDIT_A214_REVERT_HANDOFF_20260702.md."
        ),
    }


def _build_switch_rule() -> SwitchRule:
    """A21.11: tight entry gap (0.003) + wide MA window (100) + exit gap (0.010).
    Identical to A21.7 switch rule — only the defensive basket differs."""
    return SwitchRule(
        "risk_ma100_dd11_total3_eg3_xg10",
        100,    # ma_window
        0.003,  # entry_gap — tight: only genuine trend breaks trigger defensive
        0.010,  # exit_gap  — require 1% above MA100 before returning to golden1
        100,    # ma_window (for drawdown monitoring)
        -0.11,  # dd_threshold
        5, 5, 0, None, 0, None, 6, 6,
    )


def run_a2111(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.11: A21.7 tight-entry switch rule + A21.4 bond30_cash30 defensive basket."""
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve_golden_signal_path()
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
    curve, execution = _simulate_costed_curve(
        total_return_prices,
        execution_regime,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
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
    report = {
        "experiment": "group_a_plus_a2111_tight_entry_bond30c30",
        "strategy": A2111_ID,
        "status": "research_candidate",
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
            "recovery_trigger": "base defensive and ma_gap >= 0 and exit_momentum > 0",
            "recovery_is_one_shot": True,
            "trend_vol_threshold": None,
            "trend_ma_gap_persist_days": None,
            "basket_name": "bond30_cash30",
            "vol_enter_threshold": None,
            "ma_window": 100,
            "entry_gap": 0.003,
            "exit_gap": 0.010,
        },
        "cost_assumptions": {
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "equity_etf_sell_tax": equity_etf_sell_tax,
            "bond_etf_sell_tax": 0.0,
        },
        "dividend_coverage": dividend_coverage,
        "weights": weights_by_regime,
        "golden_signal_coverage": _golden_signal_metadata(golden_signal_path, golden_weights),
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
    }
    return report, out_frame


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    """Resolve 'latest' to the newest available OHLCV date for this ticker."""
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="latest",
                        help="'latest' resolves to the newest OHLCV date in --db (default)")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2111.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2111_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2111")
    try:
        resolved_end = _resolve_end_date(Path(args.db), args.end)
        report, frame = run_a2111(
            args.start,
            resolved_end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
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
