#!/usr/bin/env python3
"""Backtest adaptive quantile risk gate on a full GroupA+ runner frame.

Research-only. This is the longer-sample companion to
`backtest_group_a_plus_adaptive_quantile_risk_gate_shadow.py`: it uses the
runner's historical execution_regime frame plus report base_weights to replay
raw versus adaptive-quantile-limited target weights.
"""

from __future__ import annotations

import argparse
import json
import math
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

from group_a_plus.integrations.adaptive_quantile_risk_gate import classify_adaptive_quantile_risk_gate  # noqa: E402


DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_REPORT = PROJECT_ROOT / "results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate.json"
DEFAULT_FRAME = PROJECT_ROOT / "results/group_a_plus_runner_latest_20240101_20260806_for_aq_gate_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_risk_gate_frame_backtest_latest.json"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
COMMISSION_RATE = 0.001425
SELL_TAX_RATE = 0.001


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _load_report(path: Path) -> dict[str, Any]:
    return _unwrap(json.loads(path.read_text(encoding="utf-8-sig")))


def _load_close(db_path: Path, tickers: tuple[str, ...]) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({})
            ORDER BY dt, ticker
            """.format(",".join(["?"] * len(tickers))),
            list(tickers),
        ).fetchdf()
    finally:
        con.close()
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.normalize()
    return frame.pivot(index="dt", columns="ticker", values="close").sort_index().astype(float)


def _normalize(weights: dict[str, Any], tickers: tuple[str, ...]) -> dict[str, float]:
    out = {ticker: max(float(weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in tickers}
    out["cash"] = max(float(weights.get("cash", 0.0) or 0.0), 0.0)
    total = sum(out.values())
    if total > 1.0:
        out = {key: value / total for key, value in out.items()}
    return out


def _signal_from_frame_row(row: pd.Series, weights: dict[str, float]) -> dict[str, Any]:
    total_risk = int(float(row.get("total_risk_score", 0.0) or 0.0))
    tail_risk = int(float(row.get("tail_risk_score", 0.0) or 0.0))
    vol_ratio = float(row.get("realized_vol_ratio_20_60", 0.0) or 0.0)
    execution_regime = str(row.get("execution_regime") or "")
    alignment = "mixed" if total_risk >= 6 else "bullish_alignment"
    leverage_tier = 1 if total_risk >= 4 or tail_risk >= 1 or execution_regime == "group_a_plus_defensive" else 2
    tail_state = "TAIL_RISK_ELEVATED" if tail_risk >= 2 else "TAIL_RISK_NORMAL"

    return {
        "actual_data_date": str(pd.Timestamp(row["dt"]).date()),
        "business_stale_days": 0,
        "calendar_stale_days": 0,
        "execution_allowed": True,
        "execution_regime": execution_regime,
        "base_regime": row.get("base_regime"),
        "target_weights": weights,
        "ncf_live_overlay": {"status": "not_applicable"},
        "signal_alignment": {
            "alignment": alignment,
            "divergent_sources": [],
            "leverage_suitability": {"tier": leverage_tier},
        },
        "tail_conformal": {"state": tail_state, "allow_00631l_add": tail_risk < 2},
        "garch_regime_shadow": {"volatility_gate": {"high_vol_gate": bool(vol_ratio >= 1.35 and float(row.get("return_0050_1d", 0.0) or 0.0) < 0)}},
    }


def _apply_shadow_limits(weights: dict[str, float], gate: dict[str, Any], tickers: tuple[str, ...]) -> tuple[dict[str, float], list[str]]:
    adjusted = dict(weights)
    limits = gate.get("recommended_shadow_limits") or {}
    max_631l = float(limits.get("max_00631l_weight", adjusted.get("00631L.TW", 0.0)) or 0.0)
    min_cash = float(limits.get("min_cash_weight", adjusted.get("cash", 0.0)) or 0.0)
    actions: list[str] = []

    if adjusted.get("00631L.TW", 0.0) > max_631l:
        released = adjusted["00631L.TW"] - max_631l
        adjusted["00631L.TW"] = max_631l
        adjusted["cash"] = adjusted.get("cash", 0.0) + released
        actions.append("cap_00631l")

    gap = min_cash - adjusted.get("cash", 0.0)
    if gap > 1e-12:
        risk_tickers = [ticker for ticker in tickers if adjusted.get(ticker, 0.0) > 0]
        total_risk = sum(adjusted[ticker] for ticker in risk_tickers)
        if total_risk > 0:
            take = min(gap, total_risk)
            for ticker in risk_tickers:
                adjusted[ticker] -= take * adjusted[ticker] / total_risk
            adjusted["cash"] += take
            actions.append("raise_cash_floor")

    return _normalize(adjusted, tickers), actions


def _next_return(close: pd.DataFrame, dt: pd.Timestamp, weights: dict[str, float], tickers: tuple[str, ...]) -> tuple[float | None, str | None]:
    dt = pd.Timestamp(dt).normalize()
    if dt not in close.index:
        return None, None
    pos = close.index.get_loc(dt)
    if not isinstance(pos, int) or pos + 1 >= len(close.index):
        return None, None
    next_dt = close.index[pos + 1]
    ret = 0.0
    for ticker in tickers:
        today = close.at[dt, ticker]
        nxt = close.at[next_dt, ticker]
        if pd.isna(today) or pd.isna(nxt) or today <= 0:
            return None, None
        ret += weights.get(ticker, 0.0) * (float(nxt) / float(today) - 1.0)
    return float(ret), str(next_dt.date())


def _turnover_cost(prev: dict[str, float] | None, current: dict[str, float], tickers: tuple[str, ...]) -> float:
    if prev is None:
        return 0.0
    buy = 0.0
    sell = 0.0
    for ticker in tickers:
        delta = current.get(ticker, 0.0) - prev.get(ticker, 0.0)
        if delta > 0:
            buy += delta
        else:
            sell += -delta
    return buy * COMMISSION_RATE + sell * (COMMISSION_RATE + SELL_TAX_RATE)


def _metrics(rows: list[dict[str, Any]], column: str) -> dict[str, Any]:
    returns = pd.Series([row[column] for row in rows], dtype=float)
    equity = (1.0 + returns).cumprod()
    std = returns.std(ddof=0)
    peak = equity.cummax()
    return {
        "n": int(len(returns)),
        "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "mean_daily_return": float(returns.mean()) if len(returns) else 0.0,
        "sharpe_ratio": float(returns.mean() / std * math.sqrt(252)) if std > 0 else 0.0,
        "max_drawdown": float((equity / peak - 1.0).min()) if len(equity) else 0.0,
        "positive_day_rate": float((returns > 0).mean()) if len(returns) else 0.0,
        "worst_day": float(returns.min()) if len(returns) else 0.0,
        "best_day": float(returns.max()) if len(returns) else 0.0,
    }


def evaluate_frame(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> dict[str, Any]:
    weights_by_regime = report.get("base_weights") or report.get("weights") or {}
    rows: list[dict[str, Any]] = []
    prev_raw: dict[str, float] | None = None
    prev_gated: dict[str, float] | None = None

    work = frame.copy()
    work["dt"] = pd.to_datetime(work["dt"]).dt.normalize()
    for _, row in work.iterrows():
        regime = str(row.get("execution_regime") or row.get("base_regime") or "")
        if regime not in weights_by_regime:
            continue
        raw_weights = _normalize(dict(weights_by_regime[regime]), tickers)
        signal = _signal_from_frame_row(row, raw_weights)
        gate = classify_adaptive_quantile_risk_gate(signal)
        gated_weights, actions = _apply_shadow_limits(raw_weights, gate, tickers)
        raw_ret, next_date = _next_return(close, row["dt"], raw_weights, tickers)
        gated_ret, _ = _next_return(close, row["dt"], gated_weights, tickers)
        if raw_ret is None or gated_ret is None:
            continue

        raw_net = raw_ret - _turnover_cost(prev_raw, raw_weights, tickers)
        gated_net = gated_ret - _turnover_cost(prev_gated, gated_weights, tickers)
        changed = any(abs(raw_weights.get(k, 0.0) - gated_weights.get(k, 0.0)) > 1e-10 for k in set(raw_weights) | set(gated_weights))
        rows.append(
            {
                "date": str(pd.Timestamp(row["dt"]).date()),
                "next_date": next_date,
                "execution_regime": regime,
                "risk_posture": gate["risk_posture"],
                "quantile_level": gate["quantile_level"],
                "uncertainty_score": gate["uncertainty_score"],
                "raw_net_return": raw_net,
                "gated_net_return": gated_net,
                "delta_net_return": gated_net - raw_net,
                "changed": changed,
                "actions": actions,
                "raw_00631l_weight": raw_weights.get("00631L.TW", 0.0),
                "gated_00631l_weight": gated_weights.get("00631L.TW", 0.0),
                "raw_cash_weight": raw_weights.get("cash", 0.0),
                "gated_cash_weight": gated_weights.get("cash", 0.0),
                "total_risk_score": int(float(row.get("total_risk_score", 0.0) or 0.0)),
                "tail_risk_score": int(float(row.get("tail_risk_score", 0.0) or 0.0)),
                "reason_codes": gate.get("reason_codes"),
            }
        )
        prev_raw = raw_weights
        prev_gated = gated_weights

    raw = _metrics(rows, "raw_net_return")
    gated = _metrics(rows, "gated_net_return")
    delta = {
        "total_return_delta": gated["total_return"] - raw["total_return"],
        "sharpe_delta": gated["sharpe_ratio"] - raw["sharpe_ratio"],
        "max_drawdown_delta": gated["max_drawdown"] - raw["max_drawdown"],
        "worst_day_delta": gated["worst_day"] - raw["worst_day"],
    }
    decision = "shadow_pass_candidate" if delta["max_drawdown_delta"] > 0 and delta["total_return_delta"] >= -0.002 else "do_not_promote"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_risk_gate_frame_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ok" if rows else "no_rows",
        "method": "GroupA+ latest runner frame replay, execution_regime mapped to report base_weights, adaptive quantile shadow limits applied daily.",
        "sample": {
            "rows": len(rows),
            "start": rows[0]["date"] if rows else None,
            "end": rows[-1]["date"] if rows else None,
        },
        "raw_metrics": raw,
        "gated_metrics": gated,
        "delta": delta,
        "gate_activity": {
            "changed_days": sum(row["changed"] for row in rows),
            "cap_00631l_days": sum("cap_00631l" in row["actions"] for row in rows),
            "raise_cash_floor_days": sum("raise_cash_floor" in row["actions"] for row in rows),
            "avoided_bad_00631l_days": sum(row["raw_00631l_weight"] > row["gated_00631l_weight"] and row["delta_net_return"] > 0 for row in rows),
        },
        "posture_counts": dict(pd.Series([row["risk_posture"] for row in rows]).value_counts().sort_index()) if rows else {},
        "regime_counts": dict(pd.Series([row["execution_regime"] for row in rows]).value_counts().sort_index()) if rows else {},
        "decision": {
            "promotion_decision": decision,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "reason": "frame replay is useful shadow evidence but still requires signed promotion review before live use",
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--frame", default=str(DEFAULT_FRAME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = _load_report(Path(args.report))
    frame = pd.read_csv(args.frame)
    close = _load_close(Path(args.db), DEFAULT_TICKERS)
    result = evaluate_frame(report, frame, close)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    pd.DataFrame(result["rows"]).to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")

    print(f"status={result['status']} rows={result['sample']['rows']} window={result['sample']['start']}..{result['sample']['end']}")
    print(
        "raw_total={raw:.4%} gated_total={gated:.4%} delta={delta:.4%}".format(
            raw=result["raw_metrics"]["total_return"],
            gated=result["gated_metrics"]["total_return"],
            delta=result["delta"]["total_return_delta"],
        )
    )
    print(
        "raw_mdd={raw:.4%} gated_mdd={gated:.4%} delta={delta:.4%}".format(
            raw=result["raw_metrics"]["max_drawdown"],
            gated=result["gated_metrics"]["max_drawdown"],
            delta=result["delta"]["max_drawdown_delta"],
        )
    )
    print(f"changed_days={result['gate_activity']['changed_days']} decision={result['decision']['promotion_decision']}")
    print(f"JSON: {output}")
    print(f"CSV:  {output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
