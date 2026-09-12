#!/usr/bin/env python3
"""Build a 2606.09104 risk-aversion forward shadow for GroupA+.

This tests whether transparent HIGH/EXTREME risk-aversion states have economic
value: after the state fires, does the guarded cash-heavy target beat the raw
A21.18 0050/00631L target over the next 20 trading days? It is shadow-only.
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
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


CORE_TICKERS = ("0050.TW", "00631L.TW", "00679B.TWO")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_risk_aversion_forward_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_risk_aversion_forward_shadow/history"


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


def _load_close(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _rolling_drawdown(series: pd.Series, window: int) -> pd.Series:
    equity = (1.0 + series.fillna(0.0)).cumprod()
    rolling_peak = equity.rolling(window, min_periods=window).max()
    return equity / rolling_peak - 1.0


def _portfolio_return(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=returns.index)
    for ticker, weight in weights.items():
        if ticker == "cash":
            continue
        if ticker in returns:
            out = out.add(returns[ticker].fillna(0.0) * float(weight), fill_value=0.0)
    return out


def _future_compound(port: pd.Series, idx: int, horizon: int) -> float | None:
    future = port.iloc[idx + 1 : idx + 1 + horizon]
    if len(future) < horizon:
        return None
    return float(np.prod(1.0 + future.to_numpy(dtype=float)) - 1.0)


def _state_from_score(score: int) -> str:
    if score >= 85:
        return "EXTREME"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _build_state_frame(returns: pd.DataFrame, *, lookback: int) -> pd.DataFrame:
    base = returns["0050.TW"].fillna(0.0)
    vol20 = base.rolling(20, min_periods=20).std(ddof=0) * np.sqrt(252.0)
    vol_pct = vol20.rolling(lookback, min_periods=126).rank(pct=True)
    dd63 = _rolling_drawdown(base, 63)
    dd252 = _rolling_drawdown(base, 252)
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    raw = _portfolio_return(returns, {"0050.TW": 0.7, "00631L.TW": 0.3})
    guarded_es = guarded.rolling(lookback, min_periods=126).apply(
        lambda x: np.mean(x[x <= np.quantile(x, 0.05)]) if len(x) else np.nan,
        raw=True,
    )
    raw_es = raw.rolling(lookback, min_periods=126).apply(
        lambda x: np.mean(x[x <= np.quantile(x, 0.05)]) if len(x) else np.nan,
        raw=True,
    )
    es_ratio = raw_es.abs() / guarded_es.abs()
    down_0050 = returns["0050.TW"].clip(upper=0.0)
    down_bond = returns["00679B.TWO"].clip(upper=0.0)
    downside_corr = down_0050.rolling(120, min_periods=60).corr(down_bond)
    rows = []
    for date in returns.index:
        score = 0
        reasons: list[str] = []
        vp = vol_pct.loc[date]
        d63 = dd63.loc[date]
        d252 = dd252.loc[date]
        ratio = es_ratio.loc[date]
        corr = downside_corr.loc[date]
        if pd.notna(vp):
            if vp >= 0.85:
                score += 30
                reasons.append("0050_vol20_percentile_ge_85")
            elif vp >= 0.65:
                score += 18
                reasons.append("0050_vol20_percentile_ge_65")
        if pd.notna(d63):
            if d63 <= -0.08:
                score += 25
                reasons.append("0050_drawdown63_le_minus_8pct")
            elif d63 <= -0.05:
                score += 15
                reasons.append("0050_drawdown63_le_minus_5pct")
        if pd.notna(d252):
            if d252 <= -0.15:
                score += 20
                reasons.append("0050_drawdown252_le_minus_15pct")
            elif d252 <= -0.10:
                score += 12
                reasons.append("0050_drawdown252_le_minus_10pct")
        if pd.notna(ratio):
            if ratio >= 3.0:
                score += 20
                reasons.append("raw_target_tail_es95_at_least_3x_guarded")
            elif ratio >= 2.0:
                score += 12
                reasons.append("raw_target_tail_es95_at_least_2x_guarded")
        if pd.notna(corr):
            if corr >= 0.45:
                score += 15
                reasons.append("defensive_diversification_failed")
            elif corr >= 0.25:
                score += 8
                reasons.append("defensive_diversification_weak")
        score = min(score, 100)
        rows.append(
            {
                "date": date,
                "risk_aversion_score": score,
                "risk_aversion_state": _state_from_score(score),
                "reasons": reasons,
                "vol20_percentile": _float(vp),
                "drawdown63": _float(d63),
                "drawdown252": _float(d252),
                "raw_vs_guarded_es95_ratio": _float(ratio),
                "downside_corr_0050_00679b": _float(corr),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def _summarize_events(events: pd.DataFrame) -> dict[str, Any]:
    if events.empty:
        return {
            "event_count": 0,
            "mean_guarded_minus_raw_20d": None,
            "hit_rate_guarded_beats_raw": None,
            "mean_guarded_20d_return": None,
            "mean_raw_20d_return": None,
            "mean_guarded_max_drawdown_20d": None,
            "mean_raw_max_drawdown_20d": None,
        }
    return {
        "event_count": int(len(events)),
        "mean_guarded_minus_raw_20d": _float(events["guarded_minus_raw_20d"].mean()),
        "hit_rate_guarded_beats_raw": _float(float((events["guarded_minus_raw_20d"] > 0).mean())),
        "mean_guarded_20d_return": _float(events["guarded_20d_return"].mean()),
        "mean_raw_20d_return": _float(events["raw_20d_return"].mean()),
        "mean_guarded_max_drawdown_20d": _float(events["guarded_mdd_20d"].mean()),
        "mean_raw_max_drawdown_20d": _float(events["raw_mdd_20d"].mean()),
    }


def _future_mdd(port: pd.Series, idx: int, horizon: int) -> float | None:
    future = port.iloc[idx + 1 : idx + 1 + horizon]
    if len(future) < horizon:
        return None
    equity = (1.0 + future).cumprod()
    dd = equity / equity.cummax() - 1.0
    return float(dd.min())


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    min_events: int = 20,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, CORE_TICKERS, start, str(end_resolved)).ffill(limit=3)
    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
    else:
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if len(returns) < lookback + horizon + 60:
        blockers.append("insufficient_history_for_forward_shadow")
    event_rows: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    latest_state: dict[str, Any] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
        raw = _portfolio_return(returns, {"0050.TW": 0.7, "00631L.TW": 0.3})
        state_counts = {str(k): int(v) for k, v in states["risk_aversion_state"].value_counts().to_dict().items()}
        for idx, date in enumerate(states.index):
            state = states.loc[date, "risk_aversion_state"]
            if state not in {"HIGH", "EXTREME"}:
                continue
            g = _future_compound(guarded, idx, horizon)
            r = _future_compound(raw, idx, horizon)
            gm = _future_mdd(guarded, idx, horizon)
            rm = _future_mdd(raw, idx, horizon)
            if g is None or r is None or gm is None or rm is None:
                continue
            event_rows.append(
                {
                    "date": str(pd.Timestamp(date).date()),
                    "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
                    "risk_aversion_state": state,
                    "guarded_20d_return": g,
                    "raw_20d_return": r,
                    "guarded_minus_raw_20d": g - r,
                    "guarded_mdd_20d": gm,
                    "raw_mdd_20d": rm,
                    "reasons": states.loc[date, "reasons"],
                }
            )
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
    events = pd.DataFrame(event_rows)
    summary = _summarize_events(events)
    if summary["event_count"] < min_events and not blockers:
        blockers.append("insufficient_high_extreme_forward_events")
    has_value = bool(
        not blockers
        and (summary.get("mean_guarded_minus_raw_20d") or 0.0) > 0.0
        and (summary.get("hit_rate_guarded_beats_raw") or 0.0) >= 0.55
    )
    if not has_value and not blockers:
        warnings.append("risk_aversion_forward_filter_has_weak_or_negative_value")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_risk_aversion_forward_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "forward_validation_of_dynamic_risk_aversion",
            "not_imported": ["CNN_risk_aversion_estimator", "TD3_actor_refinement", "live_black_litterman_optimizer"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "min_events": min_events,
            "guarded_weights": {"0050.TW": 0.3, "cash": 0.7},
            "raw_a2118_proxy_weights": {"0050.TW": 0.7, "00631L.TW": 0.3},
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "state_counts": state_counts,
        },
        "latest_state": latest_state,
        "high_extreme_event_summary": summary,
        "sample_events_tail": event_rows[-10:],
        "decision": {
            "risk_aversion_forward_filter_has_economic_value": has_value,
            "supports_cash_floor_when_high_or_extreme": has_value,
            "train_cnn_risk_aversion_now": False,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Forward shadow validates whether HIGH/EXTREME risk aversion favors guarded cash-heavy target; it cannot alter weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_risk_aversion_forward_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        min_events=args.min_events,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
