#!/usr/bin/env python3
"""Build A21.18 downside-DCC forecast shadow.

This third-stage diagnostic is enabled only after simple semi-covariance
forecasts show OOS bucket value. It uses a fixed asymmetric/downside DCC proxy
and never changes live weights.
"""

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
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402
from scripts.evaluate.build_group_a_plus_a2118_downside_diversification_forecast_shadow import (  # noqa: E402
    BASE,
    DEFAULT_FIFTH_CANDIDATES,
    DEFAULT_WINDOWS,
    DEFENSIVE_ASSET,
    _cum_return,
    _economic_filter,
    _evaluate_predictions,
    _float,
    _future_mdd,
    _latest_signals,
    _load_close,
    _state,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_dcc_forecast_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/a2118_downside_dcc_forecast_shadow/history"
DEFAULT_STAGE2_REPORT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_stage2(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _downside_dcc_forecast(
    history: pd.DataFrame,
    left: str,
    right: str,
    *,
    qbar_window: int,
    alpha: float,
    beta: float,
) -> dict[str, float | None]:
    pair = history[[left, right]].dropna().tail(qbar_window)
    if len(pair) < 20:
        return {"semi_corr": None, "semi_cov": None}
    down = pair.clip(upper=0.0)
    scale = down.std(ddof=0).replace(0.0, np.nan)
    z = down.div(scale, axis=1).fillna(0.0)
    qbar = z.cov(ddof=0).to_numpy(dtype=float)
    qbar = np.nan_to_num(qbar, nan=0.0, posinf=0.0, neginf=0.0)
    q = qbar.copy()
    z_values = z.to_numpy(dtype=float)
    for row in z_values:
        shock = np.outer(row, row)
        q = (1.0 - alpha - beta) * qbar + alpha * shock + beta * q
    denom = float(np.sqrt(max(q[0, 0], 0.0) * max(q[1, 1], 0.0)))
    corr = q[0, 1] / denom if denom > 0 else np.nan
    semi_cov = corr * float(scale[left] * scale[right]) if np.isfinite(corr) and scale.notna().all() else np.nan
    return {"semi_corr": _float(corr), "semi_cov": _float(semi_cov, 10)}


def _realized_downside_stats(future: pd.DataFrame, left: str, right: str) -> dict[str, float | None]:
    pair = future[[left, right]].dropna()
    if len(pair) < 3:
        return {"semi_corr": None, "semi_cov": None}
    down = pair.clip(upper=0.0)
    cov = (down[left] * down[right]).mean()
    var_l = (down[left] * down[left]).mean()
    var_r = (down[right] * down[right]).mean()
    denom = float(np.sqrt(var_l * var_r)) if var_l > 0 and var_r > 0 else np.nan
    corr = cov / denom if np.isfinite(denom) and denom > 0 else np.nan
    return {"semi_corr": _float(corr), "semi_cov": _float(cov, 10)}


def _best_simple(stage2: dict[str, Any]) -> dict[str, Any]:
    rows = stage2.get("model_comparison") if isinstance(stage2.get("model_comparison"), list) else []
    valid = [row for row in rows if isinstance(row.get("rank_ic_mean"), (int, float))]
    if not valid:
        return {}
    return max(valid, key=lambda row: float(row["rank_ic_mean"]))


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    fifth_candidates: tuple[str, ...] = DEFAULT_FIFTH_CANDIDATES,
    qbar_windows: tuple[int, ...] = DEFAULT_WINDOWS,
    forecast_horizon: int = 20,
    oos_lookback_days: int = 252,
    min_history: int = 160,
    alpha: float = 0.03,
    beta: float = 0.94,
    good_threshold: float = 0.25,
    failed_threshold: float = 0.55,
    failure_base_mdd: float = -0.05,
    stage2_report_path: Path = DEFAULT_STAGE2_REPORT,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if alpha <= 0 or beta <= 0 or alpha + beta >= 1.0:
        blockers.append("invalid_fixed_dcc_parameters")

    stage2 = _load_stage2(_resolve(stage2_report_path))
    stage2_decision = stage2.get("decision") if isinstance(stage2.get("decision"), dict) else {}
    if stage2 and stage2_decision.get("simple_models_have_oos_bucket_value") is not True:
        warnings.append("stage2_simple_models_did_not_pass_in_latest_report")
    elif not stage2:
        warnings.append("stage2_report_missing_dcc_run_is_standalone")

    tickers = tuple(dict.fromkeys([BASE, DEFENSIVE_ASSET, *fifth_candidates]))
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, str(end_resolved))
    if close.empty or BASE not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    available = tuple(ticker for ticker in tickers if ticker in returns.columns and int(returns[ticker].notna().sum()) >= min_history)
    pairs = [(BASE, asset) for asset in available if asset != BASE]
    if BASE not in available:
        blockers.append("base_has_insufficient_history")
    if not pairs:
        blockers.append("no_pairs_with_sufficient_history")

    rows: list[dict[str, Any]] = []
    max_window = max(qbar_windows)
    if not blockers:
        first_oos_idx = max(max_window, len(returns) - forecast_horizon - oos_lookback_days)
        for idx in range(first_oos_idx, len(returns) - forecast_horizon):
            date = returns.index[idx]
            future = returns.iloc[idx + 1 : idx + 1 + forecast_horizon]
            for qbar_window in qbar_windows:
                history = returns.iloc[:idx].tail(qbar_window)
                for left, right in pairs:
                    pred = _downside_dcc_forecast(
                        history,
                        left,
                        right,
                        qbar_window=qbar_window,
                        alpha=alpha,
                        beta=beta,
                    )
                    realized = _realized_downside_stats(future, left, right)
                    base_mdd = _future_mdd(future[left].dropna())
                    asset_return = _cum_return(future[right].dropna())
                    failure = (
                        base_mdd is not None
                        and base_mdd <= failure_base_mdd
                        and asset_return is not None
                        and asset_return < 0.0
                    )
                    rows.append(
                        {
                            "date": date,
                            "pair": f"{left}_{right}",
                            "asset": right,
                            "model": "downside_dcc",
                            "window": qbar_window,
                            "predicted_20d_semicorr": pred["semi_corr"],
                            "predicted_20d_semicov": pred["semi_cov"],
                            "realized_20d_semicorr": realized["semi_corr"],
                            "realized_20d_semicov": realized["semi_cov"],
                            "downside_diversification_failure": int(failure),
                            "base_future_20d_mdd": base_mdd,
                            "asset_future_20d_return": asset_return,
                            "diversification_state": _state(pred["semi_corr"], good_threshold, failed_threshold),
                        }
                    )

    predictions = pd.DataFrame(rows)
    model_comparison = _evaluate_predictions(predictions)
    economic = _economic_filter(predictions)
    latest = _latest_signals(predictions)
    best_dcc = _best_simple({"model_comparison": model_comparison})
    best_simple = _best_simple(stage2)
    dcc_rank_ic = best_dcc.get("rank_ic_mean")
    simple_rank_ic = best_simple.get("rank_ic_mean")
    dcc_improves_rank_ic = (
        isinstance(dcc_rank_ic, (int, float))
        and isinstance(simple_rank_ic, (int, float))
        and float(dcc_rank_ic) > float(simple_rank_ic)
    )
    any_bucket_value = any(row.get("bucket_ordering_pass") for row in model_comparison)
    any_positive_economic = any(
        isinstance(row.get("net_filter_value"), (int, float)) and float(row["net_filter_value"]) > 0
        for row in economic
    )

    return {
        "schema_version": 1,
        "report_type": "a2118_downside_dcc_forecast_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": str(end_resolved),
        "method_scope": {
            "stage": "stage_3_downside_dcc_forecast_shadow",
            "model": "fixed_parameter_asymmetric_downside_dcc_proxy",
            "parameter_sweep_allowed": False,
            "deep_models_allowed": False,
            "target_weight_change_allowed": False,
        },
        "parameters": {
            "base": BASE,
            "defensive_asset": DEFENSIVE_ASSET,
            "fifth_candidates": list(fifth_candidates),
            "qbar_windows": list(qbar_windows),
            "forecast_horizon": forecast_horizon,
            "oos_lookback_days": oos_lookback_days,
            "alpha": alpha,
            "beta": beta,
            "good_threshold": good_threshold,
            "failed_threshold": failed_threshold,
            "failure_base_mdd": failure_base_mdd,
        },
        "coverage": {
            "available_tickers": list(available),
            "pairs": [f"{left}_{right}" for left, right in pairs],
            "prediction_rows": int(len(predictions)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "stage2_baseline": {
            "report_found": bool(stage2),
            "best_simple_model": best_simple,
        },
        "latest_daily_signals": latest,
        "model_comparison": model_comparison,
        "economic_filter_review": economic,
        "decision": {
            "downside_dcc_has_oos_bucket_value": any_bucket_value,
            "downside_dcc_improves_best_simple_rank_ic": dcc_improves_rank_ic,
            "downside_dcc_has_positive_economic_filter_value": any_positive_economic,
            "promote_to_live_weights": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "advance_to_transformer_research": bool(dcc_improves_rank_ic and any_positive_economic),
            "summary": (
                "DCC remains shadow-only. Transformer research is allowed only if fixed DCC improves the best simple "
                "OOS rank IC and also shows positive economic filter value."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(shadow: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(shadow, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(shadow.get("as_of") or datetime.now().date())
    history_name = f"a2118_downside_dcc_forecast_shadow_{as_of.replace('-', '')}.json"
    (history_dir / history_name).write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--fifth-candidates", nargs="*", default=list(DEFAULT_FIFTH_CANDIDATES))
    parser.add_argument("--qbar-windows", nargs="*", type=int, default=list(DEFAULT_WINDOWS))
    parser.add_argument("--forecast-horizon", type=int, default=20)
    parser.add_argument("--oos-lookback-days", type=int, default=252)
    parser.add_argument("--min-history", type=int, default=160)
    parser.add_argument("--alpha", type=float, default=0.03)
    parser.add_argument("--beta", type=float, default=0.94)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shadow = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        fifth_candidates=tuple(args.fifth_candidates),
        qbar_windows=tuple(args.qbar_windows),
        forecast_horizon=args.forecast_horizon,
        oos_lookback_days=args.oos_lookback_days,
        min_history=args.min_history,
        alpha=args.alpha,
        beta=args.beta,
    )
    write_shadow(shadow, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(shadow["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
