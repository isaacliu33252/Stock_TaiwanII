"""Split "fast crash" vs "persistent drawdown" risk mechanisms for GroupA+.

Motivation (2026-08-01 user proposal): a single composite score
(`total_risk_score` in daily_signal.py) is asked to recognize both a 2020-style
V-shaped crash and a 2022-style slow bear grind, even though the two need
different responses (crash: block new leverage / consider very-short-dated
00632R or options hedges without necessarily selling existing 00631L;
persistent drawdown: gradually rotate 0050/00631L into 00679B and cash). The
2026-07-26 SPO robustness checklist already flagged `total_risk_score`'s
>=9 threshold as fragile (13 real triggers, 81% stuck exactly on the
boundary, 51% simulated flip rate under small perturbations) -- this module
does not fix that score, it adds a second, independent diagnostic axis next
to it: *which kind* of risk episode is live right now.

This module does NOT re-derive the overnight/skew/margin feature engineering
the user's proposal called for -- that already exists:

- `group_a_plus.operations.market_state.classify_market_state` already
  separates a same-day `crash_risk` state (tail_risk_score, ma_gap +
  exit_momentum acceleration) from a `bear_breakdown` state (persistent
  ma_gap / total_risk_score trend), plus `recovery_early` /
  `recovery_confirmed`. This module reuses that classification rather than
  recomputing ma_gap/drawdown thresholds itself.
- `scripts.run.build_00631l_crash_risk_alert.build_crash_risk_alert` already
  implements the user's proposed Crash-policy feature list end to end:
  SOXX overnight return/vol (SOX ADR proxy), `us_taiwan_gap1` (SOXX vs TWII
  overnight gap -- the closest available proxy for a night-futures gap,
  since no direct TAIFEX night-session table exists yet), SOXX/TXO
  put-call skew, USD/TWD z-score, and margin/securities-lending stress
  (a forced-selling proxy for breadth deterioration). Its own
  `research_context` notes this 2-of-3 ensemble was already researched and
  NOT promoted to a trading rule (only local 2018 OOS value) -- this module
  therefore treats it as corroborating evidence, not a validated trigger.

Arbitration policy (mirrors `market_state.py`'s 2026-07-04 policy, extended
2026-08-01): this module is diagnostic and event-attribution only. Its
output (`mechanism`, `reasons`, `components`) must never be read by any
function that computes `target_weights`, `target_shares`,
`execution_regime`, or `base_regime`. Wiring a mechanism-conditioned action
(e.g. "block new leverage on FAST_CRASH", "ramp 00679B on
PERSISTENT_DRAWDOWN") requires (a) an explicit arbitration rule for
disagreement with whatever a2118 is actually doing, and (b) an
out-of-sample backtest of that rule -- same bar as `market_state.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# market_state.py buckets that indicate a non-bullish, elevated-risk regime.
# A single day landing in one of these does not by itself mean a persistent
# drawdown is underway -- it has to hold for `persistent_min_days` in a row.
DRAWDOWN_BUCKETS = frozenset({"bear_breakdown", "choppy_range_high_risk", "bull_pullback_deep"})

MECHANISMS = ("NORMAL", "FAST_CRASH", "PERSISTENT_DRAWDOWN", "RECOVERY")

DEFAULT_PERSISTENT_MIN_DAYS = 5


def _prior_drawdown_streak(history: list[dict[str, Any]]) -> int:
    """Count the trailing run of consecutive prior days with bucket in
    DRAWDOWN_BUCKETS, most-recent-first. `history` must be sorted ascending
    by date and must not include today's own row (callers slice their
    shadow log before passing it in). This is context only -- it does not
    require today's bucket to also qualify, so a crash day that interrupts
    an existing drawdown streak still reports how long that streak was."""
    count = 0
    for row in reversed(history):
        if row.get("bucket") in DRAWDOWN_BUCKETS:
            count += 1
        else:
            break
    return count


def classify_risk_mechanism(
    market_state: dict[str, Any],
    crash_alert: dict[str, Any] | None,
    history: list[dict[str, Any]] | None = None,
    *,
    persistent_min_days: int = DEFAULT_PERSISTENT_MIN_DAYS,
) -> dict[str, Any]:
    """Classify today into NORMAL / FAST_CRASH / PERSISTENT_DRAWDOWN / RECOVERY.

    Args:
        market_state: today's `classify_market_state(...)` output.
        crash_alert: today's `build_crash_risk_alert(...)` output, or None if
            unavailable (e.g. it has not run yet today -- see the pipeline
            wiring note in this module's docstring; a stale/prior-day
            crash_alert must not be passed in, since staleness masking is
            exactly the bug class this codebase has fixed before in
            ops_health and panel-drift checks).
        history: prior days' market_state shadow-log rows, sorted ascending
            by date, NOT including today. Used only to check whether a
            drawdown bucket has persisted for `persistent_min_days`.
        persistent_min_days: consecutive trading days (including today) a
            DRAWDOWN_BUCKETS bucket must hold before this is called
            PERSISTENT_DRAWDOWN rather than left as NORMAL-with-a-building
            count in `components`.
    """
    history = history or []
    state = str(market_state.get("state") or "")
    bucket = str(market_state.get("bucket") or "")

    crash_alert_available = crash_alert is not None and crash_alert.get("status") == "available"
    crash_alert_active = bool(crash_alert_available and crash_alert.get("alert_active"))
    market_state_crash = state == "crash_risk"
    fast_crash = crash_alert_active or market_state_crash

    prior_streak = _prior_drawdown_streak(history)
    drawdown_days = prior_streak + 1 if bucket in DRAWDOWN_BUCKETS else 0
    persistent_drawdown_confirmed = (not fast_crash) and bucket in DRAWDOWN_BUCKETS and drawdown_days >= persistent_min_days

    recovery = (not fast_crash) and bucket == "recovery"

    if fast_crash:
        mechanism = "FAST_CRASH"
    elif persistent_drawdown_confirmed:
        mechanism = "PERSISTENT_DRAWDOWN"
    elif recovery:
        mechanism = "RECOVERY"
    else:
        mechanism = "NORMAL"

    reasons: list[str] = [f"market_state.state={state}", f"market_state.bucket={bucket}"]
    if market_state_crash:
        reasons.append("market_state classified crash_risk (tail_risk_score/ma_gap acceleration)")
    if crash_alert_active:
        reasons.append(
            f"crash_risk_alert 2-of-3 stress score={crash_alert.get('category_score')} "
            f"active_families={sorted(k for k, v in (crash_alert.get('category_flags') or {}).items() if v)}"
        )
    elif crash_alert is not None and not crash_alert_available:
        reasons.append("crash_risk_alert unavailable/stale for this date; FAST_CRASH relied on market_state only")
    if drawdown_days > 0:
        reasons.append(
            f"drawdown-bucket streak={drawdown_days} trading day(s) "
            f"({'meets' if drawdown_days >= persistent_min_days else 'below'} "
            f"persistent_min_days={persistent_min_days})"
        )
    if fast_crash and prior_streak > 0:
        reasons.append(
            f"note: fast-crash event occurring on top of an already-building "
            f"{prior_streak}-day drawdown streak"
        )

    return {
        "mechanism": mechanism,
        "reasons": reasons,
        "components": {
            "market_state_state": state,
            "market_state_bucket": bucket,
            "market_state_crash": market_state_crash,
            "crash_alert_available": crash_alert_available,
            "crash_alert_active": crash_alert_active,
            "crash_alert_category_score": (crash_alert or {}).get("category_score"),
            "persistent_drawdown_days": drawdown_days,
            "prior_drawdown_streak_days": prior_streak,
            "persistent_min_days": persistent_min_days,
            "persistent_drawdown_confirmed": persistent_drawdown_confirmed,
        },
    }


def append_risk_mechanism_shadow_log(
    log_path: Path,
    result: dict[str, Any],
    *,
    date: str,
) -> None:
    """Append one day's risk-mechanism classification to a JSON-lines shadow
    log, idempotent per date (mirrors
    `market_state.append_market_state_shadow_log`). Measurement-only: does
    not change target_weights or execution_regime. This log is the
    prerequisite for any future out-of-sample evaluation of whether
    mechanism-conditioned actions would actually help -- do not wire this
    module's output into weights before that evaluation exists.
    """
    row = {
        "date": date,
        "mechanism": result.get("mechanism"),
        "reasons": result.get("reasons"),
        "components": result.get("components"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != row["date"]:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def load_market_state_history_before(log_path: Path, before_date: str) -> list[dict[str, Any]]:
    """Read market_state.py's shadow log and return rows strictly before
    `before_date`, sorted ascending -- the `history` input
    `classify_risk_mechanism` expects."""
    if not log_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("date") or "") < before_date:
            rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    return rows
