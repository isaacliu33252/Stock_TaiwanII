#!/usr/bin/env python3
"""Test HAR-BAVAR prior as a direction filter for the 00631L 4% candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_00631l_micro_add_forward_shadow import (  # noqa: E402
    _future_es,
    _summary,
)
from scripts.evaluate.build_group_a_plus_2606_09104_har_bavar_prior_shadow import (  # noqa: E402
    CORE_TICKERS,
    _har_features,
    _load_close,
    _ridge_predict,
)
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import (  # noqa: E402
    _build_state_frame,
    _future_compound,
    _future_mdd,
    _portfolio_return,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_00631l_4pct_bavar_direction_filter.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_00631l_4pct_bavar_direction_filter/history"


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


def _bavar_priors(
    *,
    returns: pd.DataFrame,
    train_window: int,
    horizon: int,
    step: int,
    ridge_alphas: tuple[float, ...],
) -> dict[pd.Timestamp, dict[str, float]]:
    features = _har_features(returns).replace([np.inf, -np.inf], np.nan)
    valid = pd.concat([features, returns], axis=1).dropna()
    priors: dict[pd.Timestamp, dict[str, float]] = {}
    for row_idx in range(train_window, len(valid) - horizon, step):
        date = valid.index[row_idx]
        train_dates = valid.index[row_idx - train_window : row_idx]
        x_train = features.loc[train_dates].to_numpy(dtype=float)
        y_train = returns.loc[train_dates, list(CORE_TICKERS)].to_numpy(dtype=float)
        x_now = features.loc[date].to_numpy(dtype=float)
        preds = []
        mses = []
        for alpha in ridge_alphas:
            pred, mse = _ridge_predict(x_train, y_train, x_now, alpha)
            preds.append(pred)
            mses.append(max(mse, 1e-12))
        weights = np.asarray([1.0 / mse for mse in mses], dtype=float)
        weights = weights / weights.sum()
        pred_horizon = np.sum(np.asarray(preds) * weights[:, None], axis=0) * horizon
        priors[pd.Timestamp(date)] = {ticker: float(value) for ticker, value in zip(CORE_TICKERS, pred_horizon)}
    return priors


def _candidate_event(
    *,
    returns: pd.DataFrame,
    states: pd.DataFrame,
    date: pd.Timestamp,
    horizon: int,
) -> dict[str, Any] | None:
    idx = returns.index.get_loc(date)
    guarded = _portfolio_return(returns, {"0050.TW": 0.3, "cash": 0.7})
    candidate = _portfolio_return(returns, {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66})
    g = _future_compound(guarded, idx, horizon)
    c = _future_compound(candidate, idx, horizon)
    gm = _future_mdd(guarded, idx, horizon)
    cm = _future_mdd(candidate, idx, horizon)
    ge = _future_es(guarded, idx, horizon)
    ce = _future_es(candidate, idx, horizon)
    if any(value is None for value in (g, c, gm, cm, ge, ce)):
        return None
    return {
        "date": str(date.date()),
        "risk_aversion_score": int(states.loc[date, "risk_aversion_score"]),
        "risk_aversion_state": states.loc[date, "risk_aversion_state"],
        "guarded_20d_return": g,
        "micro_20d_return": c,
        "micro_minus_guarded_20d": c - g,
        "guarded_mdd_20d": gm,
        "micro_mdd_20d": cm,
        "guarded_es_20d": ge,
        "micro_es_20d": ce,
        "reasons": states.loc[date, "reasons"],
    }


def build_filter(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    horizon: int = 20,
    lookback: int = 252,
    train_window: int = 252,
    step: int = 5,
    ridge_alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0),
    min_filtered_events: int = 20,
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
    if len(returns) < train_window + horizon + 60:
        blockers.append("insufficient_history_for_bavar_direction_filter")

    baseline_rows: list[dict[str, Any]] = []
    filtered_rows: list[dict[str, Any]] = []
    prior_tail: list[dict[str, Any]] = []
    latest_state: dict[str, Any] = {}
    if not blockers:
        states = _build_state_frame(returns, lookback=lookback)
        priors = _bavar_priors(
            returns=returns[list(CORE_TICKERS)],
            train_window=train_window,
            horizon=horizon,
            step=step,
            ridge_alphas=ridge_alphas,
        )
        for date, prior in priors.items():
            if date not in states.index:
                continue
            event = _candidate_event(returns=returns, states=states, date=date, horizon=horizon)
            if event is None:
                continue
            event["bavar_predicted_00631l_20d_return"] = prior.get("00631L.TW")
            event["bavar_allows_00631l_micro_add"] = bool((prior.get("00631L.TW") or 0.0) > 0.0)
            baseline_rows.append(event)
            if event["bavar_allows_00631l_micro_add"]:
                filtered_rows.append(event)
        if len(filtered_rows) < min_filtered_events:
            blockers.append("insufficient_bavar_allowed_events")
        latest = states.iloc[-1]
        latest_state = {
            "date": str(pd.Timestamp(states.index[-1]).date()),
            "risk_aversion_score": int(latest["risk_aversion_score"]),
            "risk_aversion_state": latest["risk_aversion_state"],
            "reasons": latest["reasons"],
        }
        prior_tail = [
            {
                "date": str(date.date()),
                "predicted_00631l_20d_return": _float(prior.get("00631L.TW")),
                "allows_00631l_micro_add": bool((prior.get("00631L.TW") or 0.0) > 0.0),
            }
            for date, prior in list(priors.items())[-10:]
        ]
    baseline_summary = _summary(pd.DataFrame(baseline_rows))
    filtered_summary = _summary(pd.DataFrame(filtered_rows))
    improves_es = bool(
        filtered_summary.get("event_count", 0) >= min_filtered_events
        and (filtered_summary.get("mean_es_extra_loss") or -999.0) > (baseline_summary.get("mean_es_extra_loss") or 0.0)
    )
    improves_return = bool(
        filtered_summary.get("event_count", 0) >= min_filtered_events
        and (filtered_summary.get("mean_micro_minus_guarded_20d") or -999.0)
        > (baseline_summary.get("mean_micro_minus_guarded_20d") or 0.0)
    )
    has_filter_value = bool(improves_es and improves_return and not blockers)
    if not has_filter_value and not blockers:
        warnings.append("bavar_direction_filter_does_not_improve_return_and_tail_together")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_00631l_4pct_bavar_direction_filter",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "bavar_direction_filter_shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "HAR_BAVAR_prior_as_micro_add_direction_filter",
            "not_imported": ["unconstrained_BLED_optimizer", "short_selling", "TD3_actor_refinement"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "lookback": lookback,
            "train_window": train_window,
            "step": step,
            "ridge_alphas": list(ridge_alphas),
            "filter_rule": "allow 00631L 4pct only when predicted_00631L_20d_return > 0",
            "candidate_weights": {"0050.TW": 0.3, "00631L.TW": 0.04, "cash": 0.66},
        },
        "coverage": {
            "baseline_event_count": len(baseline_rows),
            "filtered_event_count": len(filtered_rows),
        },
        "latest_state": latest_state,
        "latest_bavar_priors_tail": prior_tail,
        "baseline_prediction_date_summary": baseline_summary,
        "bavar_allowed_summary": filtered_summary,
        "filtered_events_tail": filtered_rows[-10:],
        "decision": {
            "bavar_filter_improves_es": improves_es,
            "bavar_filter_improves_return": improves_return,
            "bavar_direction_filter_has_value": has_filter_value,
            "allow_00631l_micro_add_from_filter": False,
            "advance_to_promotion_gate": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "BAVAR prior is tested only as a direction filter; it cannot authorize live exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_filter(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_00631l_4pct_bavar_direction_filter_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--train-window", type=int, default=252)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--min-filtered-events", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_filter(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        lookback=args.lookback,
        train_window=args.train_window,
        step=args.step,
        min_filtered_events=args.min_filtered_events,
    )
    write_filter(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
