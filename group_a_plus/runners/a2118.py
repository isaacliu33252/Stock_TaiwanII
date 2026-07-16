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
import hashlib
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _delayed_regime,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
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
from group_a_plus.runners.a2111 import (
    _build_switch_rule,
    _golden_signal_metadata,
    _resolve_golden_signal_path,
)
from tw_output_standard import OutputStandardizer, write_standard_output


A2118_ID = "a2118_a2111_ncf_late_bull_deleverage"

# Late-bull NCF trigger conditions (confirmed from panel analysis 2025-01 ~ 2026-05)
NCF_LB_MA_GAP_MIN = 0.10    # price > 10% above MA100 (late-bull regime)
NCF_LB_H20_MAX = 0.45       # NCF H20 prob_up < 45% (expects drop)
NCF_LB_CONF_MIN = 0.55      # model confidence > 55%

# De-leveraged golden1 basket: halve 00631L's weight, moving it to 0050.
# Actual hedge weights are computed dynamically from the *current* golden1
# basket by _late_bull_hedge_weights() below -- golden1 itself drifts daily
# (see [[project_group_a_plus_fable5_audit_20260702]] H3), so a static
# example here would go stale. (Removed a dead LATE_BULL_HEDGE_WEIGHTS
# constant that assumed a fixed 60/20/20 golden1 and was never referenced.)

NCF_LB_REGIME = "ncf_late_bull_hedge"
NCF_LB_SOFT_REGIME = "ncf_late_bull_hedge_soft"
GOLDEN_TAIL_TRIM_REGIME = "golden1_tail_risk_trim"
GOLDEN_FOLLOW_THROUGH_TRIM_REGIME = "golden1_follow_through_trim"
GOLDEN_REBOUND_RECAPTURE_REGIME = "golden1_rebound_recapture"
GOLDEN_LEVERAGE_CAP_REGIME = "golden1_leverage_cap"
RECOVERY_00631L_BOOST_REGIME = "group_a_plus_recovery_00631l_boost"
CHIP_DATA_FALLBACK_MAX_STALE_DAYS = 10

# 2020 V-shaped-crash switch-rule fix (2026-07-06). See
# GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md for the full
# derivation and validation (multi-window gate 6/6 pass, promotion_ready).
# Entry-side: total_risk_score and price/drawdown crossed their thresholds on
# different days during the 2020 crash (total_risk_score peaked 2020-03-06,
# drawdown didn't clear -11% until 2020-03-09) -- a rolling lookback fixes
# the misalignment. Exit-side: exit_momentum recovered three weeks before
# ma_gap during the March-April 2020 rebound; a guarded fast-exit path
# (momentum burst + ma_gap not too deep below trend) releases exposure
# without also firing on 2008-11-03's larger-magnitude dead-cat bounce.
RISK_SCORE_LOOKBACK_DAYS = 5
MOMENTUM_FAST_EXIT_MIN = 0.10
MOMENTUM_FAST_EXIT_MA_GAP_MIN = -0.08


def _late_bull_hedge_weights(golden_weights: dict[str, float], intensity: float = 1.0) -> dict[str, float]:
    weights = dict(golden_weights)
    intensity = min(max(float(intensity), 0.0), 1.0)
    shift = float(weights.get("00631L.TW", 0.0)) * 0.5 * intensity
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) - shift
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) + shift
    return _normalize(weights)


def _golden_tail_trim_weights(golden_weights: dict[str, float], trim_fraction: float = 0.5) -> dict[str, float]:
    weights = dict(golden_weights)
    trim_fraction = min(max(float(trim_fraction), 0.0), 1.0)
    shift = float(weights.get("00631L.TW", 0.0)) * trim_fraction
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) - shift
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) + shift
    return _normalize(weights)


def _golden_rebound_recapture_weights(golden_weights: dict[str, float], boost_fraction: float = 0.25) -> dict[str, float]:
    weights = dict(golden_weights)
    boost_fraction = min(max(float(boost_fraction), 0.0), 1.0)
    shift = float(weights.get("0050.TW", 0.0)) * boost_fraction
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) - shift
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) + shift
    return _normalize(weights)


def _recovery_boost_weights(recovery_weights: dict[str, float], boost_fraction: float = 0.0) -> dict[str, float]:
    weights = dict(recovery_weights)
    boost_fraction = min(max(float(boost_fraction), 0.0), 1.0)
    shift = float(weights.get("0050.TW", 0.0)) * boost_fraction
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) - shift
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) + shift
    return _normalize(weights)


def _apply_recovery_boost_age_guard(
    execution_regime: pd.Series,
    *,
    max_age_days: int,
    boosted_regime: str = RECOVERY_00631L_BOOST_REGIME,
) -> tuple[pd.Series, dict]:
    modified = execution_regime.copy()
    age = 0
    events: list[dict] = []
    boosted_days = 0
    recovery_days = 0
    max_age_days = max(int(max_age_days), 0)

    for dt, state in execution_regime.astype(str).items():
        if state != "group_a_plus_recovery":
            age = 0
            continue
        age += 1
        recovery_days += 1
        if age <= max_age_days:
            modified.loc[dt] = boosted_regime
            boosted_days += 1
            if age == 1:
                events.append({"date": str(pd.Timestamp(dt).date()), "recovery_age": age})

    return modified, {
        "recovery_00631l_boost_regime": boosted_regime,
        "recovery_00631l_boost_max_age_days": max_age_days,
        "recovery_00631l_boost_recovery_days": recovery_days,
        "recovery_00631l_boost_days": boosted_days,
        "recovery_00631l_boost_events": events,
    }


def _golden_leverage_cap_weights(golden_weights: dict[str, float], max_00631l_weight: float = 0.15) -> dict[str, float]:
    weights = dict(golden_weights)
    current = float(weights.get("00631L.TW", 0.0))
    cap = min(max(float(max_00631l_weight), 0.0), current)
    shift = max(current - cap, 0.0)
    weights["00631L.TW"] = current - shift
    weights["0050.TW"] = float(weights.get("0050.TW", 0.0)) + shift
    return _normalize(weights)


def _apply_golden_tail_trim_overlay(
    execution_regime: pd.Series,
    frame: pd.DataFrame,
    tail_risk_score_min: int = 2,
    drawdown_max: float = -0.08,
    return_var_breach: bool = True,
    exit_momentum_max: float | None = None,
) -> tuple[pd.Series, dict]:
    """Trim leverage inside golden1 during acute, already-observable stress.

    This is intentionally regime-local: it does not force a defensive state and
    does not change recovery logic. It only maps stressed golden1 days to a
    reduced-leverage golden1 basket so _simulate_costed_curve can charge costs
    through the normal share-tracking path.
    """
    required = {"tail_risk_score", "drawdown", "return_0050_1d", "hist_var_0050_20d_5pct"}
    missing = sorted(required - set(frame.columns))
    if missing:
        return execution_regime.copy(), {
            "golden_tail_trim_days": 0,
            "golden_tail_trim_events": [],
            "skipped_reason": "missing_required_frame_columns",
            "missing_columns": missing,
        }

    modified = execution_regime.copy()
    events: list[dict] = []
    for dt in execution_regime.index:
        if str(execution_regime.loc[dt]) != "golden1" or dt not in frame.index:
            continue
        row = frame.loc[dt]
        tail_score = int(row.get("tail_risk_score", 0))
        if tail_score < int(tail_risk_score_min):
            continue
        drawdown = float(row.get("drawdown", 0.0))
        ret_1d = float(row.get("return_0050_1d", 0.0))
        hist_var = float(row.get("hist_var_0050_20d_5pct", -1.0))
        exit_momentum = float(row.get("exit_momentum", 0.0))
        drawdown_trigger = drawdown <= float(drawdown_max)
        var_trigger = bool(return_var_breach and ret_1d <= hist_var)
        momentum_trigger = exit_momentum_max is not None and exit_momentum <= float(exit_momentum_max)
        if not (drawdown_trigger or var_trigger or momentum_trigger):
            continue

        modified.loc[dt] = GOLDEN_TAIL_TRIM_REGIME
        events.append({
            "date": str(dt.date()),
            "tail_risk_score": tail_score,
            "drawdown": round(drawdown, 4),
            "return_0050_1d": round(ret_1d, 4),
            "hist_var_0050_20d_5pct": round(hist_var, 4),
            "exit_momentum": round(exit_momentum, 4),
            "trigger": {
                "drawdown": drawdown_trigger,
                "var_breach": var_trigger,
                "exit_momentum": momentum_trigger,
            },
        })

    return modified, {
        "golden_tail_trim_days": len(events),
        "golden_tail_trim_events": events,
    }


def _apply_golden_follow_through_trim_overlay(
    execution_regime: pd.Series,
    frame: pd.DataFrame,
    previous_return_max: float = -0.03,
    previous_return_floor: float | None = None,
    previous_tail_risk_score_min: int = 2,
    previous_drawdown_max: float = -0.08,
    hold_days: int = 1,
) -> tuple[pd.Series, dict]:
    """Trim golden1 after a prior-day shock, using only prior close data."""
    required = {"tail_risk_score", "drawdown", "return_0050_1d", "hist_var_0050_20d_5pct"}
    missing = sorted(required - set(frame.columns))
    if missing:
        return execution_regime.copy(), {
            "golden_follow_through_trim_days": 0,
            "golden_follow_through_trim_events": [],
            "skipped_reason": "missing_required_frame_columns",
            "missing_columns": missing,
        }

    modified = execution_regime.copy()
    events: list[dict] = []
    trim_until_position = -1
    index = list(execution_regime.index)
    hold_days = max(int(hold_days), 1)

    for pos, dt in enumerate(index):
        if str(execution_regime.loc[dt]) != "golden1" or dt not in frame.index:
            continue

        active_from_prior = pos <= trim_until_position
        triggered_today = False
        previous_date: pd.Timestamp | None = None
        if pos > 0:
            previous_date = pd.Timestamp(index[pos - 1])
            if previous_date in frame.index:
                prev = frame.loc[previous_date]
                prev_return = float(prev.get("return_0050_1d", 0.0))
                prev_hist_var = float(prev.get("hist_var_0050_20d_5pct", -1.0))
                prev_tail_score = int(prev.get("tail_risk_score", 0))
                prev_drawdown = float(prev.get("drawdown", 0.0))
                not_capitulation = previous_return_floor is None or prev_return >= float(previous_return_floor)
                shock_trigger = not_capitulation and (
                    prev_return <= float(previous_return_max) or prev_return <= prev_hist_var
                )
                risk_trigger = (
                    prev_tail_score >= int(previous_tail_risk_score_min)
                    and prev_drawdown <= float(previous_drawdown_max)
                )
                triggered_today = bool(shock_trigger and risk_trigger)
                if triggered_today:
                    trim_until_position = max(trim_until_position, pos + hold_days - 1)

        if not (active_from_prior or triggered_today or pos <= trim_until_position):
            continue

        modified.loc[dt] = GOLDEN_FOLLOW_THROUGH_TRIM_REGIME
        event: dict = {
            "date": str(dt.date()),
            "source_date": str(previous_date.date()) if previous_date is not None else None,
            "hold_days": hold_days,
            "triggered_today": triggered_today,
        }
        if previous_date is not None and previous_date in frame.index:
            prev = frame.loc[previous_date]
            event.update({
                "previous_return_0050_1d": round(float(prev.get("return_0050_1d", 0.0)), 4),
                "previous_hist_var_0050_20d_5pct": round(float(prev.get("hist_var_0050_20d_5pct", -1.0)), 4),
                "previous_tail_risk_score": int(prev.get("tail_risk_score", 0)),
                "previous_drawdown": round(float(prev.get("drawdown", 0.0)), 4),
            })
        events.append(event)

    return modified, {
        "golden_follow_through_trim_days": len(events),
        "golden_follow_through_trim_events": events,
    }


def _apply_golden_rebound_recapture_overlay(
    execution_regime: pd.Series,
    frame: pd.DataFrame,
    previous_return_min: float = 0.03,
    previous_drawdown_max: float = -0.08,
    lookback_days: int = 3,
    hold_days: int = 1,
    shock_tail_risk_score_min: int = 2,
    shock_return_max: float = -0.03,
) -> tuple[pd.Series, dict]:
    """Briefly boost 00631L after a rebound confirms shock stabilization."""
    required = {"tail_risk_score", "drawdown", "return_0050_1d"}
    missing = sorted(required - set(frame.columns))
    if missing:
        return execution_regime.copy(), {
            "golden_rebound_recapture_days": 0,
            "golden_rebound_recapture_events": [],
            "skipped_reason": "missing_required_frame_columns",
            "missing_columns": missing,
        }

    modified = execution_regime.copy()
    index = list(execution_regime.index)
    events: list[dict] = []
    recapture_until_position = -1
    lookback_days = max(int(lookback_days), 1)
    hold_days = max(int(hold_days), 1)

    for pos, dt in enumerate(index):
        if str(execution_regime.loc[dt]) != "golden1" or dt not in frame.index:
            continue

        active_from_prior = pos <= recapture_until_position
        triggered_today = False
        previous_date: pd.Timestamp | None = None
        recent_shock_date: pd.Timestamp | None = None
        if pos > 0:
            previous_date = pd.Timestamp(index[pos - 1])
            if previous_date in frame.index:
                prev = frame.loc[previous_date]
                rebound_ok = (
                    float(prev.get("return_0050_1d", 0.0)) >= float(previous_return_min)
                    and float(prev.get("drawdown", 0.0)) <= float(previous_drawdown_max)
                )
                lookback_start = max(0, pos - lookback_days - 1)
                for shock_pos in range(pos - 2, lookback_start - 1, -1):
                    shock_dt = pd.Timestamp(index[shock_pos])
                    if shock_dt not in frame.index:
                        continue
                    shock = frame.loc[shock_dt]
                    if (
                        int(shock.get("tail_risk_score", 0)) >= int(shock_tail_risk_score_min)
                        and float(shock.get("return_0050_1d", 0.0)) <= float(shock_return_max)
                    ):
                        recent_shock_date = shock_dt
                        break
                triggered_today = bool(rebound_ok and recent_shock_date is not None)
                if triggered_today:
                    recapture_until_position = max(recapture_until_position, pos + hold_days - 1)

        if not (active_from_prior or triggered_today or pos <= recapture_until_position):
            continue

        modified.loc[dt] = GOLDEN_REBOUND_RECAPTURE_REGIME
        event: dict = {
            "date": str(dt.date()),
            "source_date": str(previous_date.date()) if previous_date is not None else None,
            "recent_shock_date": str(recent_shock_date.date()) if recent_shock_date is not None else None,
            "hold_days": hold_days,
            "triggered_today": triggered_today,
        }
        if previous_date is not None and previous_date in frame.index:
            prev = frame.loc[previous_date]
            event.update({
                "previous_return_0050_1d": round(float(prev.get("return_0050_1d", 0.0)), 4),
                "previous_drawdown": round(float(prev.get("drawdown", 0.0)), 4),
                "previous_tail_risk_score": int(prev.get("tail_risk_score", 0)),
            })
        events.append(event)

    return modified, {
        "golden_rebound_recapture_days": len(events),
        "golden_rebound_recapture_events": events,
    }


def _apply_golden_leverage_cap_overlay(
    execution_regime: pd.Series,
    frame: pd.DataFrame,
    tail_risk_score_min: int = 1,
    realized_vol_ratio_min: float = 1.25,
    drawdown_max: float | None = -0.08,
) -> tuple[pd.Series, dict]:
    """Cap 00631L inside golden1 during elevated volatility, without going defensive."""
    required = {"tail_risk_score", "realized_vol_ratio_20_60", "drawdown"}
    missing = sorted(required - set(frame.columns))
    if missing:
        return execution_regime.copy(), {
            "golden_leverage_cap_days": 0,
            "golden_leverage_cap_events": [],
            "skipped_reason": "missing_required_frame_columns",
            "missing_columns": missing,
        }

    modified = execution_regime.copy()
    events: list[dict] = []
    for dt in execution_regime.index:
        if str(execution_regime.loc[dt]) != "golden1" or dt not in frame.index:
            continue
        row = frame.loc[dt]
        tail_ok = int(row.get("tail_risk_score", 0)) >= int(tail_risk_score_min)
        vol_ok = float(row.get("realized_vol_ratio_20_60", 0.0)) >= float(realized_vol_ratio_min)
        drawdown_ok = drawdown_max is None or float(row.get("drawdown", 0.0)) <= float(drawdown_max)
        if not (tail_ok and vol_ok and drawdown_ok):
            continue
        modified.loc[dt] = GOLDEN_LEVERAGE_CAP_REGIME
        events.append({
            "date": str(dt.date()),
            "tail_risk_score": int(row.get("tail_risk_score", 0)),
            "realized_vol_ratio_20_60": round(float(row.get("realized_vol_ratio_20_60", 0.0)), 4),
            "drawdown": round(float(row.get("drawdown", 0.0)), 4),
        })
    return modified, {
        "golden_leverage_cap_days": len(events),
        "golden_leverage_cap_events": events,
    }


def _resolve_ncf_path(explicit: str | None, ticker_tag: str) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p if p.exists() else None
    results = PROJECT_ROOT / "results"
    candidates: list[Path] = []
    for pattern in (f"ncf_{ticker_tag}_latest_*.json", f"ncf_{ticker_tag}_2*.json"):
        candidates.extend(results.glob(pattern))
    candidates = [p for p in candidates if p.is_file() and "panel" not in p.name]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _load_ncf_panel(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ncf_panel_metadata(path: Path, panel: pd.DataFrame) -> dict:
    stat = path.stat()
    return {
        "panel_631l_rows": int(len(panel)),
        "panel_631l_path": str(path.resolve()),
        "panel_631l_sha256": _file_sha256(path),
        "panel_631l_modified_at": datetime.fromtimestamp(
            stat.st_mtime,
            timezone.utc,
        ).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "panel_631l_first_date": str(panel.index.min().date()) if len(panel) else None,
        "panel_631l_last_date": str(panel.index.max().date()) if len(panel) else None,
    }


def _signal_date_matches(signal: dict, frame_data_date: pd.Timestamp) -> bool:
    signal_date_raw = signal.get("date")
    if not signal_date_raw:
        return False
    return pd.Timestamp(signal_date_raw).normalize() == pd.Timestamp(frame_data_date).normalize()


def _apply_late_bull_overlay(
    execution_regime: pd.Series,
    panel_631l: pd.DataFrame | None,
    ma_gap_series: pd.Series,
    ma_gap_min: float = NCF_LB_MA_GAP_MIN,
    h20_max: float = NCF_LB_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = 0.0,
    gain_prob_soft_min: float | None = None,
    rally_suppress_min: float | None = None,
) -> tuple[pd.Series, dict]:
    """Pre-process execution_regime: override golden1 trigger days to ncf_late_bull_hedge.

    Reuses _simulate_costed_curve unchanged — only the regime input changes.
    This ensures share-tracking simulation identical to A21.11 on non-trigger days.

    h5_reentry_min > 0: enables hold mechanism — once triggered, stays in hedge
    until prob_up_h5 >= h5_reentry_min (H=5 confirms reversal). Set to 0 (default)
    to use original stateless day-by-day logic.

    rally_suppress_min: when prob_fwd_gain_gt5_h20 >= this threshold, suppress the
    hedge entirely (stay in golden1). Checked before gain_prob_soft_min. Default None
    (no suppression) preserves original A21.18 behaviour.
    """
    if panel_631l is None:
        return execution_regime.copy(), {
            "late_bull_trigger_days": 0,
            "late_bull_trigger_events": [],
        }
    missing_cols = sorted({"prob_up_h20", "confidence"} - set(panel_631l.columns))
    if missing_cols:
        return execution_regime.copy(), {
            "late_bull_trigger_days": 0,
            "late_bull_trigger_events": [],
            "skipped_reason": "missing_required_panel_columns",
            "missing_columns": missing_cols,
        }

    modified = execution_regime.copy()
    trigger_events: list[dict] = []
    hold_days: list[str] = []
    soft_hedge_days: list[str] = []
    suppressed_days: list[str] = []
    skipped_days: list[str] = []
    in_hedge = False

    def _gain_prob(day: pd.Timestamp) -> float | None:
        if "prob_fwd_gain_gt5_h20" not in panel_631l.columns:
            return None
        val = panel_631l.loc[day, "prob_fwd_gain_gt5_h20"]
        return float(val) if pd.notna(val) else None

    def hedge_regime_for_day(day: pd.Timestamp) -> str | None:
        """Return hedge regime string, or None to suppress hedge entirely."""
        gp = _gain_prob(day)
        if rally_suppress_min is not None and gp is not None and gp >= rally_suppress_min:
            suppressed_days.append(str(day.date()))
            return None
        if gain_prob_soft_min is not None and gp is not None and gp >= gain_prob_soft_min:
            soft_hedge_days.append(str(day.date()))
            return NCF_LB_SOFT_REGIME
        return NCF_LB_REGIME

    for d in execution_regime.index:
        if str(execution_regime.loc[d]) != "golden1":
            in_hedge = False  # regime changed — reset hold state
            continue
        if d not in panel_631l.index:
            continue

        ma_gap = float(ma_gap_series.get(d, 0.0))
        h20_raw = panel_631l.loc[d, "prob_up_h20"]
        conf_raw = panel_631l.loc[d, "confidence"]
        if pd.isna(h20_raw) or pd.isna(conf_raw):
            skipped_days.append(str(d.date()))
            continue
        h20_prob = float(h20_raw)
        conf = float(conf_raw)
        h5_raw = panel_631l.loc[d, "prob_up_h5"] if "prob_up_h5" in panel_631l.columns else 1.0
        h5_prob = float(h5_raw) if pd.notna(h5_raw) else 1.0

        is_trigger = ma_gap > ma_gap_min and h20_prob < h20_max and conf > conf_min

        if h5_reentry_min > 0:
            # Stateful hold logic with optional rally suppression.
            # Rally suppression is evaluated at entry: if the initial trigger fires
            # but gain_prob >= rally_suppress_min, skip entering hedge entirely.
            if is_trigger and not in_hedge:
                init_regime = hedge_regime_for_day(d)
                if init_regime is not None:
                    in_hedge = True
                    modified.loc[d] = init_regime
                    trigger_events.append({
                        "date": str(d.date()),
                        "ma_gap": round(ma_gap, 4),
                        "prob_up_h20": round(h20_prob, 4),
                        "confidence": round(conf, 4),
                        "trigger_type": "initial",
                    })
                # else: rally_suppress fired — trigger condition met but hedge not entered
            elif in_hedge:
                if is_trigger:
                    # Still triggering inside hold window
                    hold_days.append(str(d.date()))
                else:
                    # Check hold-exit conditions
                    gp = _gain_prob(d)
                    rally_exit = (
                        rally_suppress_min is not None
                        and gp is not None
                        and gp >= rally_suppress_min
                    )
                    if h5_prob >= h5_reentry_min or rally_exit:
                        in_hedge = False  # reversal confirmed or rally suppression
                    else:
                        hold_days.append(str(d.date()))

                if in_hedge:
                    regime = hedge_regime_for_day(d)
                    if regime is not None:
                        modified.loc[d] = regime
        else:
            # Original stateless logic (h5_reentry_min == 0)
            if is_trigger:
                regime = hedge_regime_for_day(d)
                if regime is not None:
                    modified.loc[d] = regime
                trigger_events.append({
                    "date": str(d.date()),
                    "ma_gap": round(ma_gap, 4),
                    "prob_up_h20": round(h20_prob, 4),
                    "confidence": round(conf, 4),
                })

    return modified, {
        "late_bull_trigger_days": len(trigger_events),
        "late_bull_trigger_events": trigger_events,
        "hold_days": hold_days,
        "soft_hedge_days": soft_hedge_days,
        "suppressed_days": suppressed_days,
        "skipped_days": skipped_days,
        "total_hedge_days": len(trigger_events) + len(hold_days),
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
    h5_reentry_min: float = 0.0,
    gain_prob_soft_min: float | None = None,
    soft_hedge_intensity: float = 0.5,
    rally_suppress_min: float | None = None,
    regime_execution_delay_days: int = 0,
    chip_data_fallback_max_stale_days: int | None = CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    risk_score_lookback_days: int | None = RISK_SCORE_LOOKBACK_DAYS,
    momentum_fast_exit_min: float | None = MOMENTUM_FAST_EXIT_MIN,
    momentum_fast_exit_ma_gap_min: float | None = MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    low_risk_exit_ma_gap: float | None = None,
    low_risk_exit_score_threshold: int = 1,
    override_tail_risk_score: int = 0,
    override_tail_drawdown_threshold: float = -0.10,
    override_tail_use_var_breach: bool = True,
    golden_tail_trim_enabled: bool = False,
    golden_tail_trim_fraction: float = 0.5,
    golden_tail_trim_tail_risk_score_min: int = 2,
    golden_tail_trim_drawdown_max: float = -0.08,
    golden_tail_trim_return_var_breach: bool = True,
    golden_tail_trim_exit_momentum_max: float | None = None,
    golden_follow_through_trim_enabled: bool = False,
    golden_follow_through_trim_fraction: float = 0.5,
    golden_follow_through_previous_return_max: float = -0.03,
    golden_follow_through_previous_return_floor: float | None = None,
    golden_follow_through_previous_tail_risk_score_min: int = 2,
    golden_follow_through_previous_drawdown_max: float = -0.08,
    golden_follow_through_hold_days: int = 1,
    golden_rebound_recapture_enabled: bool = False,
    golden_rebound_recapture_boost_fraction: float = 0.25,
    golden_rebound_recapture_previous_return_min: float = 0.03,
    golden_rebound_recapture_previous_drawdown_max: float = -0.08,
    golden_rebound_recapture_lookback_days: int = 3,
    golden_rebound_recapture_hold_days: int = 1,
    golden_rebound_recapture_shock_tail_risk_score_min: int = 2,
    golden_rebound_recapture_shock_return_max: float = -0.03,
    golden_leverage_cap_enabled: bool = False,
    golden_leverage_cap_max_00631l_weight: float = 0.15,
    golden_leverage_cap_tail_risk_score_min: int = 1,
    golden_leverage_cap_realized_vol_ratio_min: float = 1.25,
    golden_leverage_cap_drawdown_max: float | None = -0.08,
    recovery_00631l_boost_fraction: float = 0.0,
    recovery_00631l_boost_max_age_days: int | None = None,
    exclude_zero_volume_rows: bool = False,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.18: A21.11 base + NCF late-bull de-leverage overlay on golden1.

    When ncf_panel_631l_path is provided, the historical backtest uses the same
    _simulate_costed_curve as A21.11, with trigger days pre-converted to
    "ncf_late_bull_hedge" regime (share-tracked, not daily-rebalanced).
    Without the panel, backtest is identical to A21.11.

    regime_execution_delay_days: H4 (2026-07-02 Fable 5 audit) analysis knob,
    default 0 (no behavior change). The panel's prediction for day t needs
    day t's close, which isn't available live until ~23:30 that night, so
    live execution can only act on it starting day t+1 -- the default
    same-day backtest has a 1-trading-day look-ahead versus live. Set to 1
    to shift `modified_regime` by that many trading days (via
    `_delayed_regime`) before simulating, to see the same-day-lookahead-free
    comparison. Left off by default so no existing caller's numbers change.

    exclude_zero_volume_rows: 2026-07-12 fix, opt-in, default False (no
    behavior change for existing backtest/evaluation callers). Some
    non-trading days get a spurious ohlcv row (prior close carried forward,
    volume=0) instead of being skipped. `daily_signal.py` treats this
    module's frame.index[-1] as "actual_data_date" -- a phantom row there
    makes chip/derivative sources look falsely one day stale, incorrectly
    blocking execution. See
    GROUP_A_PLUS_A2118_CHIP_DATA_CORE_CLOCK_AUDIT_HANDOFF_20260712.md. The
    live manifest (report/group_a_plus/latest/strategy.json's
    runner_params) opts into this; historical backtests are intentionally
    left as-is pending a separate audit of how many/which historical
    windows this affects.
    """
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve_golden_signal_path()
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, warmup_days)
    switch_rule = _build_switch_rule()
    if low_risk_exit_ma_gap is not None:
        switch_rule = replace(
            switch_rule,
            low_risk_exit_ma_gap=float(low_risk_exit_ma_gap),
            low_risk_exit_score_threshold=int(low_risk_exit_score_threshold),
        )
    if override_tail_risk_score > 0:
        switch_rule = replace(
            switch_rule,
            override_tail_risk_score=int(override_tail_risk_score),
            override_tail_drawdown_threshold=float(override_tail_drawdown_threshold),
            override_tail_use_var_breach=bool(override_tail_use_var_breach),
        )
    full_prices = _load_prices(
        _resolve(db), list(TICKERS), load_start, end, exclude_zero_volume=exclude_zero_volume_rows
    )
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(
        full_prices,
        full_chip,
        switch_rule,
        chip_data_fallback_max_stale_days=chip_data_fallback_max_stale_days,
        risk_score_lookback_days=risk_score_lookback_days,
        momentum_fast_exit_min=momentum_fast_exit_min,
        momentum_fast_exit_ma_gap_min=momentum_fast_exit_ma_gap_min,
    )
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(db), close_prices.index)

    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": (
            current_defensive
            if recovery_00631l_boost_max_age_days is not None
            else _recovery_boost_weights(current_defensive, recovery_00631l_boost_fraction)
        ),
        RECOVERY_00631L_BOOST_REGIME: _recovery_boost_weights(current_defensive, recovery_00631l_boost_fraction),
        NCF_LB_REGIME: _late_bull_hedge_weights(golden_weights),
        NCF_LB_SOFT_REGIME: _late_bull_hedge_weights(golden_weights, intensity=soft_hedge_intensity),
        GOLDEN_TAIL_TRIM_REGIME: _golden_tail_trim_weights(golden_weights, golden_tail_trim_fraction),
        GOLDEN_FOLLOW_THROUGH_TRIM_REGIME: _golden_tail_trim_weights(
            golden_weights,
            golden_follow_through_trim_fraction,
        ),
        GOLDEN_REBOUND_RECAPTURE_REGIME: _golden_rebound_recapture_weights(
            golden_weights,
            golden_rebound_recapture_boost_fraction,
        ),
        GOLDEN_LEVERAGE_CAP_REGIME: _golden_leverage_cap_weights(
            golden_weights,
            golden_leverage_cap_max_00631l_weight,
        ),
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
            h5_reentry_min=h5_reentry_min,
            gain_prob_soft_min=gain_prob_soft_min,
            rally_suppress_min=rally_suppress_min,
        )
        backtest_mode = "ncf_late_bull_regime_overlay"
        ncf_panel_coverage = _ncf_panel_metadata(Path(ncf_panel_631l_path), panel_631l)
    else:
        modified_regime = execution_regime
        overlay_info = {"late_bull_trigger_days": 0, "late_bull_trigger_events": []}
        backtest_mode = "base_a2111_no_ncf_panel"
        ncf_panel_coverage = {"status": "no_panel_provided"}

    # Golden1-regime shadow overlays apply the same way regardless of
    # whether a late-bull panel was available above -- previously
    # duplicated verbatim in both branches (fixed 2026-07-06).
    if golden_tail_trim_enabled:
        modified_regime, tail_trim_info = _apply_golden_tail_trim_overlay(
            modified_regime,
            frame,
            tail_risk_score_min=golden_tail_trim_tail_risk_score_min,
            drawdown_max=golden_tail_trim_drawdown_max,
            return_var_breach=golden_tail_trim_return_var_breach,
            exit_momentum_max=golden_tail_trim_exit_momentum_max,
        )
        overlay_info = {**overlay_info, **tail_trim_info}
    if golden_follow_through_trim_enabled:
        modified_regime, follow_through_info = _apply_golden_follow_through_trim_overlay(
            modified_regime,
            frame,
            previous_return_max=golden_follow_through_previous_return_max,
            previous_return_floor=golden_follow_through_previous_return_floor,
            previous_tail_risk_score_min=golden_follow_through_previous_tail_risk_score_min,
            previous_drawdown_max=golden_follow_through_previous_drawdown_max,
            hold_days=golden_follow_through_hold_days,
        )
        overlay_info = {**overlay_info, **follow_through_info}
    if golden_rebound_recapture_enabled:
        modified_regime, recapture_info = _apply_golden_rebound_recapture_overlay(
            modified_regime,
            frame,
            previous_return_min=golden_rebound_recapture_previous_return_min,
            previous_drawdown_max=golden_rebound_recapture_previous_drawdown_max,
            lookback_days=golden_rebound_recapture_lookback_days,
            hold_days=golden_rebound_recapture_hold_days,
            shock_tail_risk_score_min=golden_rebound_recapture_shock_tail_risk_score_min,
            shock_return_max=golden_rebound_recapture_shock_return_max,
        )
        overlay_info = {**overlay_info, **recapture_info}
    if golden_leverage_cap_enabled:
        modified_regime, leverage_cap_info = _apply_golden_leverage_cap_overlay(
            modified_regime,
            frame,
            tail_risk_score_min=golden_leverage_cap_tail_risk_score_min,
            realized_vol_ratio_min=golden_leverage_cap_realized_vol_ratio_min,
            drawdown_max=golden_leverage_cap_drawdown_max,
        )
        overlay_info = {**overlay_info, **leverage_cap_info}
    if recovery_00631l_boost_max_age_days is not None and recovery_00631l_boost_fraction > 0.0:
        modified_regime, recovery_boost_info = _apply_recovery_boost_age_guard(
            modified_regime,
            max_age_days=recovery_00631l_boost_max_age_days,
        )
        overlay_info = {**overlay_info, **recovery_boost_info}

    # H4: by default (regime_execution_delay_days=0) this simulates as if
    # the panel's day-t prediction were tradable at day-t's own close --
    # in live trading the NCF signal isn't produced until ~23:30 that
    # night, so execution can only start day t+1. See docstring above.
    executed_regime = _delayed_regime(modified_regime, regime_execution_delay_days)
    curve, sim_result = _simulate_costed_curve(
        total_return_prices,
        executed_regime,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )

    recovery_dates = [
        str(dt.date())
        for dt in executed_regime.index
        if executed_regime.loc[dt] in {"group_a_plus_recovery", RECOVERY_00631L_BOOST_REGIME}
        and (
            dt == executed_regime.index[0]
            or executed_regime.shift(1).loc[dt] not in {"group_a_plus_recovery", RECOVERY_00631L_BOOST_REGIME}
        )
    ]
    out_frame = frame.copy()
    out_frame = out_frame.rename(columns={"regime": "base_regime"})
    out_frame["execution_regime"] = executed_regime
    out_frame["portfolio_value"] = curve

    # --- Live NCF signal (today) ---
    today_regime = str(executed_regime.iloc[-1])
    ncf_live: dict = {}
    path_631l = _resolve_ncf_path(ncf_00631l_path, "00631l")
    today_ma_gap = float(ma_gap_series.iloc[-1]) if len(ma_gap_series) > 0 else 0.0
    frame_data_date = pd.Timestamp(modified_regime.index[-1]).normalize()

    if path_631l:
        sig_631l = load_ncf_signal(path_631l)
        signal_date_raw = sig_631l.get("date")
        signal_date = pd.Timestamp(signal_date_raw).normalize() if signal_date_raw else None
        date_matches = _signal_date_matches(sig_631l, frame_data_date)
        # Use raw H=20 probability (horizon_prob_up["20"]) to match panel backtest behavior.
        # calibrated_prob_up is the AUC-weighted ensemble across all horizons — different metric.
        # `is None` (not `or`) so a genuine 0.0 probability isn't discarded in favor
        # of the calibrated fallback -- `or` treats 0.0 as falsy and silently
        # substitutes the ensemble value, diluting an extreme bearish reading.
        raw_h20 = (sig_631l.get("horizon_prob_up") or {}).get("20")
        h20_prob = float(raw_h20 if raw_h20 is not None else sig_631l.get("calibrated_prob_up", 0.5))
        raw_h5 = (sig_631l.get("horizon_prob_up") or {}).get("5")
        h5_prob = float(raw_h5 if raw_h5 is not None else sig_631l.get("calibrated_prob_up", 0.5))
        # H2 (2026-07-02 Fable 5 audit, Option A): use confidence_panel_aligned
        # (same expanding-AUC prob_magnitude computation as the panel CSV
        # this strategy's conf_min was actually swept/calibrated against),
        # not the composite `confidence` field -- those two were observed
        # to differ by ~18x on the same day (different formula AND
        # different underlying ensemble weighting). Falls back to 0.0 (never
        # triggers) rather than silently reading the differently-scaled
        # composite value for JSON payloads generated before this field
        # existed.
        conf_aligned = sig_631l.get("confidence_panel_aligned")
        conf = float(conf_aligned) if conf_aligned is not None else 0.0
        late_bull_triggered = bool(
            date_matches
            and
            today_ma_gap > ma_gap_min
            and h20_prob < h20_max
            and conf > conf_min
        )
        gain_prob = sig_631l.get("prob_fwd_gain_gt5_h20")
        gain_prob_f = float(gain_prob) if gain_prob is not None else None
        rally_suppressed = (
            late_bull_triggered
            and rally_suppress_min is not None
            and gain_prob_f is not None
            and gain_prob_f >= rally_suppress_min
        )
        soft_hedge_triggered = (
            late_bull_triggered
            and not rally_suppressed
            and gain_prob_soft_min is not None
            and gain_prob_f is not None
            and gain_prob_f >= gain_prob_soft_min
        )
        effective_hedge_active = late_bull_triggered and not rally_suppressed
        ncf_live = {
            "status": "ok" if date_matches else "stale",
            "reason": None if date_matches else "ncf_date_mismatch",
            "ncf_00631l_file": str(path_631l.relative_to(PROJECT_ROOT)),
            "signal_date": str(signal_date.date()) if signal_date is not None else None,
            "frame_data_date": str(frame_data_date.date()),
            "today_ma_gap": round(today_ma_gap, 4),
            "h20_prob_up": round(h20_prob, 4),
            "h5_prob_up": round(h5_prob, 4),
            "confidence": round(conf, 4),
            "prob_fwd_mdd_gt5_h20": sig_631l.get("prob_fwd_mdd_gt5_h20"),
            "prob_fwd_gain_gt5_h20": gain_prob,
            "late_bull_triggered": late_bull_triggered,
            "rally_suppressed": rally_suppressed,
            "soft_hedge_triggered": soft_hedge_triggered,
            "effective_hedge_active": effective_hedge_active,
            "trigger_conditions": {
                "ma_gap_min": ma_gap_min,
                "h20_max": h20_max,
                "conf_min": conf_min,
                "gain_prob_soft_min": gain_prob_soft_min,
                "rally_suppress_min": rally_suppress_min,
            },
            "effective_weights": (
                _late_bull_hedge_weights(
                    golden_weights,
                    intensity=soft_hedge_intensity if soft_hedge_triggered else 1.0,
                )
                if date_matches and today_regime == "golden1" and effective_hedge_active
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
        "regime_execution_delay_days": regime_execution_delay_days,
        "metrics": _metrics(curve, initial_value),
        "execution": {**sim_result, **overlay_info},
        "backtest_live_discrepancy": {
            "trim_layer": "bearish_high_risk_trim",
            "trim_condition": "total_risk_score>=9 AND signal_alignment bearish/wide_divergence",
            # Matches _apply_bearish_high_risk_trim's live default in
            # daily_signal.py (trim_fraction=0.20) -- this field previously
            # said 0.25, which didn't match the actual live behavior.
            "trim_fraction": 0.20,
            "in_backtest": False,
            "reason": "signal_alignment requires real-time multi-source inputs, not reconstructable historically",
            "high_chip_golden1_days": int(
                ((frame["chip_score"] >= 9) & (frame["regime"] == "golden1")).sum()
                if "chip_score" in frame.columns and "regime" in frame.columns
                else -1
            ),
            "high_chip_golden1_fraction": round(float(
                ((frame["chip_score"] >= 9) & (frame["regime"] == "golden1")).mean()
                if "chip_score" in frame.columns and "regime" in frame.columns
                else float("nan")
            ), 4),
        },
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
            "ncf_late_bull_h5_reentry_min": h5_reentry_min,
            "ncf_late_bull_gain_prob_soft_min": gain_prob_soft_min,
            "ncf_late_bull_soft_hedge_intensity": soft_hedge_intensity,
            "ncf_late_bull_rally_suppress_min": rally_suppress_min,
            "chip_data_fallback_max_stale_days": chip_data_fallback_max_stale_days,
            "chip_data_fallback_source_clock": "chip_data_core_days_since_source_update",
            "risk_score_lookback_days": risk_score_lookback_days,
            "momentum_fast_exit_min": momentum_fast_exit_min,
            "momentum_fast_exit_ma_gap_min": momentum_fast_exit_ma_gap_min,
            "low_risk_exit_ma_gap": low_risk_exit_ma_gap,
            "low_risk_exit_score_threshold": low_risk_exit_score_threshold,
            "override_tail_risk_score": override_tail_risk_score,
            "override_tail_drawdown_threshold": override_tail_drawdown_threshold,
            "override_tail_use_var_breach": override_tail_use_var_breach,
            "recovery_00631l_boost_fraction": recovery_00631l_boost_fraction,
            "recovery_00631l_boost_max_age_days": recovery_00631l_boost_max_age_days,
            "recovery_00631l_boost_regime": RECOVERY_00631L_BOOST_REGIME,
            "recovery_boost_weights": _recovery_boost_weights(current_defensive, recovery_00631l_boost_fraction),
            "late_bull_hedge_regime": NCF_LB_REGIME,
            "late_bull_hedge_weights": _late_bull_hedge_weights(golden_weights),
            "late_bull_soft_hedge_regime": NCF_LB_SOFT_REGIME,
            "late_bull_soft_hedge_weights": _late_bull_hedge_weights(
                golden_weights,
                intensity=soft_hedge_intensity,
            ),
            "golden_tail_trim_enabled": golden_tail_trim_enabled,
            "golden_tail_trim_regime": GOLDEN_TAIL_TRIM_REGIME,
            "golden_tail_trim_fraction": golden_tail_trim_fraction,
            "golden_tail_trim_tail_risk_score_min": golden_tail_trim_tail_risk_score_min,
            "golden_tail_trim_drawdown_max": golden_tail_trim_drawdown_max,
            "golden_tail_trim_return_var_breach": golden_tail_trim_return_var_breach,
            "golden_tail_trim_exit_momentum_max": golden_tail_trim_exit_momentum_max,
            "golden_tail_trim_weights": _golden_tail_trim_weights(golden_weights, golden_tail_trim_fraction),
            "golden_follow_through_trim_enabled": golden_follow_through_trim_enabled,
            "golden_follow_through_trim_regime": GOLDEN_FOLLOW_THROUGH_TRIM_REGIME,
            "golden_follow_through_trim_fraction": golden_follow_through_trim_fraction,
            "golden_follow_through_previous_return_max": golden_follow_through_previous_return_max,
            "golden_follow_through_previous_return_floor": golden_follow_through_previous_return_floor,
            "golden_follow_through_previous_tail_risk_score_min": golden_follow_through_previous_tail_risk_score_min,
            "golden_follow_through_previous_drawdown_max": golden_follow_through_previous_drawdown_max,
            "golden_follow_through_hold_days": golden_follow_through_hold_days,
            "golden_follow_through_trim_weights": _golden_tail_trim_weights(
                golden_weights,
                golden_follow_through_trim_fraction,
            ),
            "golden_rebound_recapture_enabled": golden_rebound_recapture_enabled,
            "golden_rebound_recapture_regime": GOLDEN_REBOUND_RECAPTURE_REGIME,
            "golden_rebound_recapture_boost_fraction": golden_rebound_recapture_boost_fraction,
            "golden_rebound_recapture_previous_return_min": golden_rebound_recapture_previous_return_min,
            "golden_rebound_recapture_previous_drawdown_max": golden_rebound_recapture_previous_drawdown_max,
            "golden_rebound_recapture_lookback_days": golden_rebound_recapture_lookback_days,
            "golden_rebound_recapture_hold_days": golden_rebound_recapture_hold_days,
            "golden_rebound_recapture_shock_tail_risk_score_min": golden_rebound_recapture_shock_tail_risk_score_min,
            "golden_rebound_recapture_shock_return_max": golden_rebound_recapture_shock_return_max,
            "golden_rebound_recapture_weights": _golden_rebound_recapture_weights(
                golden_weights,
                golden_rebound_recapture_boost_fraction,
            ),
            "golden_leverage_cap_enabled": golden_leverage_cap_enabled,
            "golden_leverage_cap_regime": GOLDEN_LEVERAGE_CAP_REGIME,
            "golden_leverage_cap_max_00631l_weight": golden_leverage_cap_max_00631l_weight,
            "golden_leverage_cap_tail_risk_score_min": golden_leverage_cap_tail_risk_score_min,
            "golden_leverage_cap_realized_vol_ratio_min": golden_leverage_cap_realized_vol_ratio_min,
            "golden_leverage_cap_drawdown_max": golden_leverage_cap_drawdown_max,
            "golden_leverage_cap_weights": _golden_leverage_cap_weights(
                golden_weights,
                golden_leverage_cap_max_00631l_weight,
            ),
        },
        "cost_assumptions": {
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "equity_etf_sell_tax": equity_etf_sell_tax,
            "bond_etf_sell_tax": 0.0,
        },
        "dividend_coverage": dividend_coverage,
        "ncf_panel_coverage": ncf_panel_coverage,
        "golden_signal_coverage": _golden_signal_metadata(golden_signal_path, golden_weights),
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
            "bearish_trim_discrepancy": (
                "LIVE vs BACKTEST: daily_signal.py applies an additional 25% trim to 00631L "
                "when total_risk_score>=9 AND signal_alignment is bearish/wide_divergence. "
                "This trim is NOT included in this backtest simulation because signal_alignment "
                "requires real-time multi-source inputs (finbert, factor_lens, NCF, chip_score) "
                "that cannot be reconstructed historically without lookahead bias. "
                "Impact estimate: trim fires on days with chip_score>=9 in golden1 regime; "
                "see backtest_live_discrepancy field for historical chip_score>=9 day count. "
                "When comparing backtest Sharpe/Sortino to live performance, note that live "
                "returns are conservatively biased relative to backtest on high-chip days."
            ),
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
    parser.add_argument("--ncf-00631l", default=None)
    parser.add_argument("--ncf-panel-631l", default=None,
                        help="val-prediction panel CSV for 00631L (enables NCF historical backtest)")
    parser.add_argument("--ma-gap-min", type=float, default=NCF_LB_MA_GAP_MIN)
    parser.add_argument("--h20-max", type=float, default=NCF_LB_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=0.0)
    parser.add_argument("--gain-prob-soft-min", type=float, default=None)
    parser.add_argument("--soft-hedge-intensity", type=float, default=0.5)
    parser.add_argument("--rally-suppress-min", type=float, default=None,
                        help="suppress hedge when prob_fwd_gain_gt5_h20 >= threshold (rally too likely)")
    parser.add_argument("--regime-execution-delay-days", type=int, default=0,
                        help="H4 analysis: shift regime by N trading days before simulating, "
                             "to model the real 1-day gap between NCF signal generation (23:30) "
                             "and live execution (default 0 = same-day, i.e. existing behavior)")
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int,
                        default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
                        help="Bypass chip/derivative/total-risk entry gates after N trading days "
                             "without core chip/derivative source updates.")
    parser.add_argument("--risk-score-lookback-days", type=int, default=RISK_SCORE_LOOKBACK_DAYS,
                        help="Entry-side 2020 fix: use a rolling max of total_risk_score over this "
                             "many trading days instead of only today's value. None/0 to disable.")
    parser.add_argument("--momentum-fast-exit-min", type=float, default=MOMENTUM_FAST_EXIT_MIN,
                        help="Exit-side 2020 fix: exit defensive immediately once exit_momentum "
                             "reaches this threshold, regardless of ma_gap. None to disable.")
    parser.add_argument("--momentum-fast-exit-ma-gap-min", type=float, default=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
                        help="Guard for --momentum-fast-exit-min: also require ma_gap >= this value, "
                             "so a bear-market dead-cat bounce (e.g. 2008-11-03) doesn't trigger the "
                             "fast exit the way a genuine V-shaped recovery (2020-03-26) does.")
    parser.add_argument("--low-risk-exit-ma-gap", type=float, default=None,
                        help="Use this lower exit MA gap when total_risk_score is low.")
    parser.add_argument("--low-risk-exit-score-threshold", type=int, default=1)
    parser.add_argument("--override-tail-risk-score", type=int, default=0)
    parser.add_argument("--override-tail-drawdown-threshold", type=float, default=-0.10)
    parser.add_argument("--override-tail-use-var-breach", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--golden-tail-trim-enabled", action="store_true",
                        help="Enable shadow golden1 tail-risk trim overlay.")
    parser.add_argument("--golden-tail-trim-fraction", type=float, default=0.5)
    parser.add_argument("--golden-tail-trim-tail-risk-score-min", type=int, default=2)
    parser.add_argument("--golden-tail-trim-drawdown-max", type=float, default=-0.08)
    parser.add_argument("--golden-tail-trim-return-var-breach", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--golden-tail-trim-exit-momentum-max", type=float, default=None)
    parser.add_argument("--golden-follow-through-trim-enabled", action="store_true",
                        help="Enable prior-day shock follow-through trim overlay.")
    parser.add_argument("--golden-follow-through-trim-fraction", type=float, default=0.5)
    parser.add_argument("--golden-follow-through-previous-return-max", type=float, default=-0.03)
    parser.add_argument("--golden-follow-through-previous-return-floor", type=float, default=None)
    parser.add_argument("--golden-follow-through-previous-tail-risk-score-min", type=int, default=2)
    parser.add_argument("--golden-follow-through-previous-drawdown-max", type=float, default=-0.08)
    parser.add_argument("--golden-follow-through-hold-days", type=int, default=1)
    parser.add_argument("--golden-rebound-recapture-enabled", action="store_true",
                        help="Enable rebound recapture overlay after recent shock stabilization.")
    parser.add_argument("--golden-rebound-recapture-boost-fraction", type=float, default=0.25)
    parser.add_argument("--golden-rebound-recapture-previous-return-min", type=float, default=0.03)
    parser.add_argument("--golden-rebound-recapture-previous-drawdown-max", type=float, default=-0.08)
    parser.add_argument("--golden-rebound-recapture-lookback-days", type=int, default=3)
    parser.add_argument("--golden-rebound-recapture-hold-days", type=int, default=1)
    parser.add_argument("--golden-rebound-recapture-shock-tail-risk-score-min", type=int, default=2)
    parser.add_argument("--golden-rebound-recapture-shock-return-max", type=float, default=-0.03)
    parser.add_argument("--golden-leverage-cap-enabled", action="store_true",
                        help="Enable golden1 00631L cap under elevated volatility.")
    parser.add_argument("--golden-leverage-cap-max-00631l-weight", type=float, default=0.15)
    parser.add_argument("--golden-leverage-cap-tail-risk-score-min", type=int, default=1)
    parser.add_argument("--golden-leverage-cap-realized-vol-ratio-min", type=float, default=1.25)
    parser.add_argument("--golden-leverage-cap-drawdown-max", type=float, default=-0.08)
    parser.add_argument("--recovery-00631l-boost-fraction", type=float, default=0.0)
    parser.add_argument("--recovery-00631l-boost-max-age-days", type=int, default=None,
                        help="Only apply recovery 00631L boost to the first N days of each recovery episode.")
    parser.add_argument("--output", default="results/group_a_plus_runner_a2118.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2118_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2118")
    try:
        resolved_end = _resolve_end_date(Path(args.db), args.end)
        report, frame = run_a2118(
            args.start,
            resolved_end,
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
            h5_reentry_min=args.h5_reentry_min,
            gain_prob_soft_min=args.gain_prob_soft_min,
            soft_hedge_intensity=args.soft_hedge_intensity,
            rally_suppress_min=args.rally_suppress_min,
            regime_execution_delay_days=args.regime_execution_delay_days,
            chip_data_fallback_max_stale_days=args.chip_data_fallback_max_stale_days,
            risk_score_lookback_days=args.risk_score_lookback_days,
            momentum_fast_exit_min=args.momentum_fast_exit_min,
            momentum_fast_exit_ma_gap_min=args.momentum_fast_exit_ma_gap_min,
            low_risk_exit_ma_gap=args.low_risk_exit_ma_gap,
            low_risk_exit_score_threshold=args.low_risk_exit_score_threshold,
            override_tail_risk_score=args.override_tail_risk_score,
            override_tail_drawdown_threshold=args.override_tail_drawdown_threshold,
            override_tail_use_var_breach=args.override_tail_use_var_breach,
            golden_tail_trim_enabled=args.golden_tail_trim_enabled,
            golden_tail_trim_fraction=args.golden_tail_trim_fraction,
            golden_tail_trim_tail_risk_score_min=args.golden_tail_trim_tail_risk_score_min,
            golden_tail_trim_drawdown_max=args.golden_tail_trim_drawdown_max,
            golden_tail_trim_return_var_breach=args.golden_tail_trim_return_var_breach,
            golden_tail_trim_exit_momentum_max=args.golden_tail_trim_exit_momentum_max,
            golden_follow_through_trim_enabled=args.golden_follow_through_trim_enabled,
            golden_follow_through_trim_fraction=args.golden_follow_through_trim_fraction,
            golden_follow_through_previous_return_max=args.golden_follow_through_previous_return_max,
            golden_follow_through_previous_return_floor=args.golden_follow_through_previous_return_floor,
            golden_follow_through_previous_tail_risk_score_min=args.golden_follow_through_previous_tail_risk_score_min,
            golden_follow_through_previous_drawdown_max=args.golden_follow_through_previous_drawdown_max,
            golden_follow_through_hold_days=args.golden_follow_through_hold_days,
            golden_rebound_recapture_enabled=args.golden_rebound_recapture_enabled,
            golden_rebound_recapture_boost_fraction=args.golden_rebound_recapture_boost_fraction,
            golden_rebound_recapture_previous_return_min=args.golden_rebound_recapture_previous_return_min,
            golden_rebound_recapture_previous_drawdown_max=args.golden_rebound_recapture_previous_drawdown_max,
            golden_rebound_recapture_lookback_days=args.golden_rebound_recapture_lookback_days,
            golden_rebound_recapture_hold_days=args.golden_rebound_recapture_hold_days,
            golden_rebound_recapture_shock_tail_risk_score_min=args.golden_rebound_recapture_shock_tail_risk_score_min,
            golden_rebound_recapture_shock_return_max=args.golden_rebound_recapture_shock_return_max,
            golden_leverage_cap_enabled=args.golden_leverage_cap_enabled,
            golden_leverage_cap_max_00631l_weight=args.golden_leverage_cap_max_00631l_weight,
            golden_leverage_cap_tail_risk_score_min=args.golden_leverage_cap_tail_risk_score_min,
            golden_leverage_cap_realized_vol_ratio_min=args.golden_leverage_cap_realized_vol_ratio_min,
            golden_leverage_cap_drawdown_max=args.golden_leverage_cap_drawdown_max,
            recovery_00631l_boost_fraction=args.recovery_00631l_boost_fraction,
            recovery_00631l_boost_max_age_days=args.recovery_00631l_boost_max_age_days,
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
