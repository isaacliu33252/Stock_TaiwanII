"""Fine-grained market state classification for GroupA+ live signals.

Arbitration policy (2026-07-04, following the Fable audit's decision item A):
this module is diagnostic-only. `classify_market_state`'s output (`state`,
`bucket`, `allocation_bias`, `risk_level`) must never be read by any function
that computes `target_weights`, `target_shares`, `execution_regime`, or
`base_regime`. When this module's suggested action disagrees with what
a2118 (or any other active runner) is actually doing -- e.g. `crash_risk`
recommending "00632R hedge or full defense" while `execution_regime` is
still `golden1` -- a2118's live decision wins by default, simply because
nothing wires this module's output back into weight calculation. This is
intentional, not an oversight: a2118's "don't fully exit late-bull" design
is backtested (see NCF_2330 handoffs and the 2026-06/07 GroupA+ handoffs),
while this classifier's thresholds are not yet validated out of a
bull-dominated sample (see the 2026-07-04 Fable audit's replay: 361 days,
`recovery_confirmed` never observed). Do not add code that feeds
`allocation_bias` or `state` into `target_weights` without first (a) an
explicit, documented arbitration rule for the a2118-vs-market_state
disagreement case, and (b) an out-of-sample backtest of that rule -- see
`test_crash_risk_can_fire_while_execution_regime_stays_golden1_by_design` in
`tests/test_group_a_plus_market_state.py` for a pinned example of the known
disagreement case this guards against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_PROFILES: dict[str, dict[str, Any]] = {
    "bull_acceleration": {
        "bucket": "bull_trend",
        "label_zh": "多頭加速",
        "allocation_bias": "00631L high weight",
        "risk_level": "risk_on",
    },
    "bull_trend": {
        "bucket": "bull_trend",
        "label_zh": "多頭趨勢",
        "allocation_bias": "00631L high weight",
        "risk_level": "risk_on",
    },
    "late_bull_overheat": {
        "bucket": "bull_trend",
        "label_zh": "多頭末段過熱",
        "allocation_bias": "0050 core with reduced 00631L",
        "risk_level": "medium",
    },
    "bull_pullback_shallow": {
        "bucket": "bull_pullback",
        "label_zh": "多頭淺回檔",
        "allocation_bias": "0050 plus small 00631L",
        "risk_level": "medium",
    },
    "bull_pullback_deep": {
        "bucket": "bull_pullback",
        "label_zh": "多頭深回檔",
        "allocation_bias": "0050 core, keep cash buffer",
        "risk_level": "medium_high",
    },
    "recovery_early": {
        "bucket": "recovery",
        "label_zh": "復甦初期",
        "allocation_bias": "gradual ramp from cash to 0050",
        "risk_level": "medium",
    },
    "recovery_confirmed": {
        "bucket": "recovery",
        "label_zh": "復甦確認",
        "allocation_bias": "gradual ramp up; add 00631L only after confirmation",
        "risk_level": "medium",
    },
    "choppy_range_low_risk": {
        "bucket": "choppy_range",
        "label_zh": "低風險盤整",
        "allocation_bias": "0050 with cash buffer",
        "risk_level": "medium",
    },
    "choppy_range_high_risk": {
        "bucket": "choppy_range",
        "label_zh": "高風險盤整",
        "allocation_bias": "cash first, small 0050 only",
        "risk_level": "medium_high",
    },
    "bear_breakdown": {
        "bucket": "bear_breakdown",
        "label_zh": "空頭跌破",
        "allocation_bias": "cash",
        "risk_level": "risk_off",
    },
    "crash_risk": {
        "bucket": "crash_risk",
        "label_zh": "崩跌風險",
        "allocation_bias": "00632R hedge or full defense",
        "risk_level": "severe",
    },
}


def _num(features: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(features.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def classify_market_state(
    execution_regime: str,
    latest_features: dict[str, Any],
    *,
    signal_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify the live regime into a finer action-oriented market state.

    The coarse execution regimes stay untouched. This classifier only adds
    explainable state metadata for reporting, alerting, and future allocation
    gates.
    """
    regime = str(execution_regime)
    ma_gap = _num(latest_features, "ma_gap")
    drawdown = _num(latest_features, "drawdown")
    exit_momentum = _num(latest_features, "exit_momentum_5d", _num(latest_features, "exit_momentum"))
    total_risk_score = int(_num(latest_features, "total_risk_score"))
    tail_risk_score = int(_num(latest_features, "tail_risk_score"))
    alignment = (signal_alignment or {}).get("alignment")
    dominant = (signal_alignment or {}).get("dominant_direction")

    reasons: list[str] = [
        f"execution_regime={regime}",
        f"ma_gap={ma_gap:.4f}",
        f"drawdown={drawdown:.4f}",
        f"exit_momentum_5d={exit_momentum:.4f}",
        f"total_risk_score={total_risk_score}",
        f"tail_risk_score={tail_risk_score}",
    ]
    if alignment:
        reasons.append(f"signal_alignment={alignment}")
    if dominant:
        reasons.append(f"dominant_direction={dominant}")

    if (
        tail_risk_score >= 2
        or (total_risk_score >= 9 and drawdown <= -0.05)
        or (ma_gap <= -0.08 and exit_momentum <= -0.03)
    ):
        state = "crash_risk"
    elif regime in {"group_a_plus_severe", "group_a_plus_defensive"}:
        state = "bear_breakdown" if total_risk_score >= 7 or ma_gap < -0.02 else "choppy_range_high_risk"
    elif regime == "group_a_plus_recovery":
        state = "recovery_confirmed" if ma_gap >= 0.01 and exit_momentum > 0 else "recovery_early"
    elif ma_gap >= 0.12 or regime.startswith("ncf_late_bull"):
        # An active ncf_late_bull hedge regime always classifies as
        # late_bull_overheat (2026-07-04 audit): previously a hedge day with
        # ma_gap in (0.10, 0.12) and total_risk_score < 6 fell through to the
        # bull_acceleration / bull_trend branches, whose allocation_bias
        # ("00631L high weight") directly contradicts the de-leverage the
        # strategy is executing that day. Diagnosis must never recommend the
        # opposite of the live action.
        state = "late_bull_overheat"
    elif ma_gap >= 0.04 and drawdown > -0.03 and total_risk_score <= 4 and dominant != "bearish":
        state = "bull_acceleration"
    elif ma_gap >= 0.02 and drawdown > -0.05 and total_risk_score <= 6:
        state = "bull_trend"
    elif ma_gap >= 0.0 and drawdown > -0.06:
        state = "bull_pullback_shallow"
    elif ma_gap >= -0.03 and drawdown > -0.10:
        state = "bull_pullback_deep" if exit_momentum < 0 else "choppy_range_low_risk"
    elif total_risk_score >= 7 or dominant == "bearish":
        state = "choppy_range_high_risk"
    else:
        state = "choppy_range_low_risk"

    profile = STATE_PROFILES[state]
    return {
        "state": state,
        "bucket": profile["bucket"],
        "label_zh": profile["label_zh"],
        "allocation_bias": profile["allocation_bias"],
        "risk_level": profile["risk_level"],
        "inputs": {
            "execution_regime": regime,
            "ma_gap": ma_gap,
            "drawdown": drawdown,
            "exit_momentum_5d": exit_momentum,
            "total_risk_score": total_risk_score,
            "tail_risk_score": tail_risk_score,
            "signal_alignment": alignment,
            "dominant_direction": dominant,
        },
        "reason": "; ".join(reasons),
    }


def append_market_state_shadow_log(
    log_path: Path,
    market_state: dict[str, Any],
    *,
    date: str,
    execution_regime: str | None = None,
) -> None:
    """Append one day's market_state classification to a JSON-lines log for
    later forward-return evaluation of the a2118-vs-market_state arbitration
    question documented in this module's docstring.

    2026-07-09: the 2026-07-04 audit kept a2118 as the sole decision-maker
    based on only 9-10 real `crash_risk` trigger days (2025-2026 real data)
    plus a 2008 TWII proxy replay that disagreed with it in direction --
    too small a sample either way to settle the question, and
    classify_market_state's output was never logged historically so no
    larger sample could accumulate. This log closes that gap. Idempotent
    per date and measurement-only, mirroring
    garch_regime_shadow.append_garch_regime_shadow_log and
    signal_alignment.append_signal_alignment_shadow_log: it does not change
    target_weights or execution_regime.
    """
    row = {
        "date": date,
        "state": market_state.get("state"),
        "bucket": market_state.get("bucket"),
        "allocation_bias": market_state.get("allocation_bias"),
        "risk_level": market_state.get("risk_level"),
        "logged_execution_regime": execution_regime,
        "inputs": market_state.get("inputs"),
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
