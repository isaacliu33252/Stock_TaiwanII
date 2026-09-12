#!/usr/bin/env python3
"""Build a 2606.09104 dynamic risk-aversion gate for GroupA+.

The paper estimates state-dependent risk aversion with a CNN. GroupA+ imports
only the governance idea: compute a transparent risk-aversion state from local
volatility, drawdown, tail, and diversification reports. It never changes
weights or emits orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    _load_json,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_BLED_TAIL_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_bled_tail_adjustment_review.json"
DEFAULT_DOWNSIDE_DIVERSIFICATION = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_dynamic_risk_aversion_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_dynamic_risk_aversion_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_0050_returns(db_path: Path, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["dt"] = pd.to_datetime(df["dt"])
    close = df.set_index("dt")["close"].astype(float)
    return close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()


def _drawdown(close_returns: pd.Series, window: int) -> float | None:
    if len(close_returns) < window:
        return None
    equity = (1.0 + close_returns.tail(window)).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return _float(dd.min())


def _vol_percentile(returns: pd.Series, window: int = 20, lookback: int = 756) -> dict[str, Any]:
    vol = returns.rolling(window).std(ddof=0) * np.sqrt(252.0)
    sample = vol.dropna().tail(lookback)
    if sample.empty:
        return {"status": "insufficient_data"}
    latest = float(sample.iloc[-1])
    pct = float((sample <= latest).mean())
    return {"status": "available", "latest_annual_vol": _float(latest), "lookback_percentile": _float(pct)}


def _tail_es_ratio(bled_review: dict[str, Any]) -> float | None:
    rows = bled_review.get("target_tail_reviews") if isinstance(bled_review.get("target_tail_reviews"), list) else []
    by_name = {row.get("target_name"): row for row in rows if isinstance(row, dict)}
    raw = by_name.get("raw_a2118_seed_ensemble_target") or {}
    guarded = by_name.get("guarded_live_target") or {}
    raw_es = abs(float(raw.get("student_t_adjusted_daily_es95") or 0.0))
    guarded_es = abs(float(guarded.get("student_t_adjusted_daily_es95") or 0.0))
    if guarded_es <= 0:
        return None
    return raw_es / guarded_es


def _defensive_diversification_state(payload: dict[str, Any]) -> str | None:
    signals = payload.get("latest_pair_signals")
    if isinstance(signals, list):
        for row in signals:
            if not isinstance(row, dict):
                continue
            pair = str(row.get("pair") or "")
            if pair == "0050.TW_00679B.TWO":
                return row.get("diversification_state")
    # Keep compatibility with older report layouts.
    text = json.dumps(payload, ensure_ascii=False)
    if "DIVERSIFICATION_FAILED" in text:
        return "DIVERSIFICATION_FAILED"
    if "DIVERSIFICATION_WEAK" in text:
        return "DIVERSIFICATION_WEAK"
    if "DIVERSIFICATION_GOOD" in text:
        return "DIVERSIFICATION_GOOD"
    return None


def _state_from_score(score: int) -> str:
    if score >= 85:
        return "EXTREME"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def build_gate(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    bled_tail_review_path: Path = DEFAULT_BLED_TAIL_REVIEW,
    downside_diversification_path: Path = DEFAULT_DOWNSIDE_DIVERSIFICATION,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        returns = pd.Series(dtype=float)
    else:
        returns = _load_0050_returns(db_path, start, str(end_resolved))
    if len(returns) < 252:
        blockers.append("insufficient_0050_history")
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    bled_review = _load_json(_resolve(bled_tail_review_path))
    downside = _load_json(_resolve(downside_diversification_path))
    if not forward_monitor:
        blockers.append("forward_monitor_missing")
    if not bled_review:
        warnings.append("bled_tail_review_missing")
    if not downside:
        warnings.append("downside_diversification_shadow_missing")

    vol_info = _vol_percentile(returns) if not returns.empty else {"status": "insufficient_data"}
    dd63 = _drawdown(returns, 63) if not returns.empty else None
    dd252 = _drawdown(returns, 252) if not returns.empty else None
    es_ratio = _tail_es_ratio(bled_review) if bled_review else None
    div_state = _defensive_diversification_state(downside) if downside else None
    score = 0
    reasons: list[str] = []
    vol_pct = vol_info.get("lookback_percentile")
    if isinstance(vol_pct, (int, float)):
        if float(vol_pct) >= 0.85:
            score += 30
            reasons.append("0050_vol20_percentile_ge_85")
        elif float(vol_pct) >= 0.65:
            score += 18
            reasons.append("0050_vol20_percentile_ge_65")
    if dd63 is not None and dd63 <= -0.08:
        score += 25
        reasons.append("0050_drawdown63_le_minus_8pct")
    elif dd63 is not None and dd63 <= -0.05:
        score += 15
        reasons.append("0050_drawdown63_le_minus_5pct")
    if dd252 is not None and dd252 <= -0.15:
        score += 20
        reasons.append("0050_drawdown252_le_minus_15pct")
    elif dd252 is not None and dd252 <= -0.10:
        score += 12
        reasons.append("0050_drawdown252_le_minus_10pct")
    if es_ratio is not None and es_ratio >= 3.0:
        score += 20
        reasons.append("raw_target_tail_es95_at_least_3x_guarded")
    elif es_ratio is not None and es_ratio >= 2.0:
        score += 12
        reasons.append("raw_target_tail_es95_at_least_2x_guarded")
    if div_state == "DIVERSIFICATION_FAILED":
        score += 15
        reasons.append("defensive_diversification_failed")
    elif div_state == "DIVERSIFICATION_WEAK":
        score += 8
        reasons.append("defensive_diversification_weak")
    score = min(score, 100)
    state = _state_from_score(score)
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    target = live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {}
    cash_weight = float(target.get("cash", 0.0) or 0.0)
    supports_current_cash_floor = state in {"HIGH", "EXTREME"} and cash_weight >= 0.5
    if state in {"HIGH", "EXTREME"} and cash_weight < 0.5:
        warnings.append("risk_aversion_high_but_live_cash_weight_below_50pct")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_dynamic_risk_aversion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "state_dependent_dynamic_risk_aversion",
            "not_imported": ["CNN_risk_aversion_estimator", "TD3_actor_refinement", "live_black_litterman_optimizer"],
        },
        "inputs_snapshot": {
            "vol20": vol_info,
            "drawdown63": dd63,
            "drawdown252": dd252,
            "raw_vs_guarded_tail_adjusted_es95_ratio": _float(es_ratio),
            "defensive_diversification_state": div_state,
            "live_target_weights": target,
            "market_state": live_signal.get("market_state"),
        },
        "risk_aversion": {
            "score": score,
            "state": state,
            "reasons": reasons,
        },
        "decision": {
            "supports_current_cash_floor": supports_current_cash_floor,
            "allow_increase_risky_weight": False if state in {"HIGH", "EXTREME"} else None,
            "train_cnn_risk_aversion_now": False,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Risk-aversion gate is a transparent shadow check; it can support review of cash floors but cannot alter weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_gate(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_dynamic_risk_aversion_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--bled-tail-review", default=str(DEFAULT_BLED_TAIL_REVIEW))
    parser.add_argument("--downside-diversification", default=str(DEFAULT_DOWNSIDE_DIVERSIFICATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_gate(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        forward_monitor_path=_resolve(args.forward_monitor),
        bled_tail_review_path=_resolve(args.bled_tail_review),
        downside_diversification_path=_resolve(args.downside_diversification),
    )
    write_gate(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
