"""Evaluate A21.18 opportunity-cost labels.

The A21.18 overlay moves half of the golden1 00631L allocation into 0050.
This script labels whether that de-leverage decision beats the base golden1
allocation over the next N trading days:

    hedge_beats_base = fwd_return_0050 > fwd_return_00631L

The label is intentionally simple. It targets the actual portfolio decision
more directly than asking whether 00631L is merely up or down.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_FRAME = PROJECT_ROOT / "results" / "group_a_plus_runner_a2118_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_opportunity_cost_a2118.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_opportunity_cost_a2118.csv"


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path, parse_dates=["date"])
    panel["date"] = pd.to_datetime(panel["date"]).dt.normalize()
    return panel.set_index("date").sort_index()


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["dt"])
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.normalize()
    return frame.set_index("dt").sort_index()


def _forward_returns(prices: pd.DataFrame, horizon: int) -> pd.DataFrame:
    out = pd.DataFrame(index=prices.index)
    for ticker in ("0050.TW", "00631L.TW"):
        out[f"fwd_{ticker}_ret_{horizon}d"] = prices[ticker].shift(-horizon) / prices[ticker] - 1.0
    return out


def _rate(series: pd.Series) -> float | None:
    valid = series.dropna()
    if valid.empty:
        return None
    return float(valid.mean())


def _summarize_slice(name: str, df: pd.DataFrame) -> dict[str, Any]:
    labeled = df.dropna(subset=["hedge_beats_base_20d"])
    if labeled.empty:
        return {
            "name": name,
            "rows": int(len(df)),
            "labeled_rows": 0,
            "hedge_win_rate": None,
        }

    return {
        "name": name,
        "rows": int(len(df)),
        "labeled_rows": int(len(labeled)),
        "hedge_win_rate": _rate(labeled["hedge_beats_base_20d"]),
        "mean_delta_portfolio_return_20d": float(labeled["delta_portfolio_return_20d"].mean()),
        "median_delta_portfolio_return_20d": float(labeled["delta_portfolio_return_20d"].median()),
        "mean_fwd_0050_return_20d": float(labeled["fwd_0050.TW_ret_20d"].mean()),
        "mean_fwd_00631l_return_20d": float(labeled["fwd_00631L.TW_ret_20d"].mean()),
        "mean_forward_mdd_h20": (
            float(labeled["forward_mdd_h20"].mean())
            if "forward_mdd_h20" in labeled and labeled["forward_mdd_h20"].notna().any()
            else None
        ),
        "mean_forward_gain_h20": (
            float(labeled["forward_gain_h20"].mean())
            if "forward_gain_h20" in labeled and labeled["forward_gain_h20"].notna().any()
            else None
        ),
    }


def _grid_eval(df: pd.DataFrame, h20_values: list[float], conf_values: list[float]) -> list[dict[str, Any]]:
    labeled = df.dropna(subset=["hedge_beats_base_20d"])
    rows: list[dict[str, Any]] = []
    for h20_max in h20_values:
        for conf_min in conf_values:
            mask = (
                (labeled["base_regime"].astype(str) == "golden1")
                & (labeled["ma_gap"] > 0.10)
                & (labeled["prob_up_h20"] < h20_max)
                & (labeled["confidence"] > conf_min)
            )
            picked = labeled.loc[mask]
            if picked.empty:
                rows.append({
                    "h20_max": h20_max,
                    "conf_min": conf_min,
                    "trigger_count": 0,
                    "hedge_win_rate": None,
                    "mean_delta_portfolio_return_20d": None,
                })
                continue
            rows.append({
                "h20_max": h20_max,
                "conf_min": conf_min,
                "trigger_count": int(len(picked)),
                "hedge_win_rate": _rate(picked["hedge_beats_base_20d"]),
                "mean_delta_portfolio_return_20d": float(picked["delta_portfolio_return_20d"].mean()),
                "median_delta_portfolio_return_20d": float(picked["delta_portfolio_return_20d"].median()),
                "trigger_dates": [str(d.date()) for d in picked.index],
            })
    return sorted(
        rows,
        key=lambda r: (
            int(r["trigger_count"]) < 2,
            -1 if r["hedge_win_rate"] is None else -float(r["hedge_win_rate"]),
            0 if r["mean_delta_portfolio_return_20d"] is None else -float(r["mean_delta_portfolio_return_20d"]),
            int(r["trigger_count"]),
        ),
    )


def _best_grid_with_min_count(grid: list[dict[str, Any]], min_count: int) -> list[dict[str, Any]]:
    candidates = [row for row in grid if int(row["trigger_count"]) >= min_count and row["hedge_win_rate"] is not None]
    return sorted(
        candidates,
        key=lambda r: (
            -float(r["hedge_win_rate"]),
            -float(r["mean_delta_portfolio_return_20d"]),
            int(r["trigger_count"]),
        ),
    )


def _recovery_gate_grid(df: pd.DataFrame) -> list[dict[str, Any]]:
    labeled = df.dropna(subset=["hedge_beats_base_20d"])
    trigger = labeled[labeled["a2118_initial_trigger"]].copy()
    gain_thresholds = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    tail_thresholds = [-0.65, -0.55, -0.45, -0.35, -0.25]
    rows: list[dict[str, Any]] = []

    for gain_max in gain_thresholds:
        picked = trigger[trigger["prob_fwd_gain_gt5_h20"] <= gain_max]
        rows.append(_recovery_gate_row(f"gain_prob<={gain_max:.2f}", picked, len(trigger)))

    for tail_max in tail_thresholds:
        picked = trigger[trigger["tail_reward_risk_score_h20"] <= tail_max]
        rows.append(_recovery_gate_row(f"tail_score<={tail_max:.2f}", picked, len(trigger)))

    for gain_max in gain_thresholds:
        for tail_max in tail_thresholds:
            picked = trigger[
                (trigger["prob_fwd_gain_gt5_h20"] <= gain_max)
                & (trigger["tail_reward_risk_score_h20"] <= tail_max)
            ]
            rows.append(_recovery_gate_row(f"gain_prob<={gain_max:.2f}&tail_score<={tail_max:.2f}", picked, len(trigger)))

    return sorted(
        rows,
        key=lambda r: (
            int(r["kept_trigger_count"]) == 0,
            -1 if r["hedge_win_rate"] is None else -float(r["hedge_win_rate"]),
            0 if r["mean_delta_portfolio_return_20d"] is None else -float(r["mean_delta_portfolio_return_20d"]),
            int(r["suppressed_trigger_count"]),
        ),
    )


def _recovery_gate_row(name: str, picked: pd.DataFrame, total_current_triggers: int) -> dict[str, Any]:
    if picked.empty:
        return {
            "gate": name,
            "kept_trigger_count": 0,
            "suppressed_trigger_count": total_current_triggers,
            "hedge_win_rate": None,
            "mean_delta_portfolio_return_20d": None,
        }
    return {
        "gate": name,
        "kept_trigger_count": int(len(picked)),
        "suppressed_trigger_count": int(total_current_triggers - len(picked)),
        "hedge_win_rate": _rate(picked["hedge_beats_base_20d"]),
        "mean_delta_portfolio_return_20d": float(picked["delta_portfolio_return_20d"].mean()),
        "median_delta_portfolio_return_20d": float(picked["delta_portfolio_return_20d"].median()),
        "kept_dates": [str(d.date()) for d in picked.index],
    }


def _tiered_deleverage_profiles(df: pd.DataFrame) -> list[dict[str, Any]]:
    hedge = df[
        (df["execution_regime"].astype(str) == "ncf_late_bull_hedge")
        & df["delta_portfolio_return_20d"].notna()
    ].copy()
    if hedge.empty:
        return []

    profiles: dict[str, pd.Series] = {
        "current_full_half_cut": pd.Series(1.0, index=hedge.index),
        "soft_all_half_intensity": pd.Series(0.5, index=hedge.index),
        "skip_when_gain_prob_gt_0.35": (hedge["prob_fwd_gain_gt5_h20"] <= 0.35).astype(float),
        "soft_when_gain_prob_gt_0.35": pd.Series(
            [1.0 if v <= 0.35 else 0.5 for v in hedge["prob_fwd_gain_gt5_h20"]],
            index=hedge.index,
        ),
        "gain_prob_tier_030_040": pd.Series(
            [
                1.0 if v <= 0.30 else 0.5 if v <= 0.40 else 0.25
                for v in hedge["prob_fwd_gain_gt5_h20"]
            ],
            index=hedge.index,
        ),
        "h20_prob_tier_025_033": pd.Series(
            [
                1.0 if v <= 0.25 else 0.5 if v <= 0.33 else 0.25
                for v in hedge["prob_up_h20"]
            ],
            index=hedge.index,
        ),
    }

    rows: list[dict[str, Any]] = []
    drawdown_days = hedge["forward_mdd_h20"] <= -0.05
    for name, scale in profiles.items():
        scaled_delta = hedge["delta_portfolio_return_20d"] * scale
        rows.append({
            "profile": name,
            "hedge_days": int(len(hedge)),
            "mean_intensity": float(scale.mean()),
            "mean_delta_portfolio_return_20d": float(scaled_delta.mean()),
            "median_delta_portfolio_return_20d": float(scaled_delta.median()),
            "positive_delta_rate": _rate((scaled_delta > 0.0).astype(float)),
            "mean_intensity_on_drawdown_days": (
                float(scale.loc[drawdown_days].mean()) if drawdown_days.any() else None
            ),
            "drawdown_day_count": int(drawdown_days.sum()),
        })
    return sorted(
        rows,
        key=lambda r: (
            -float(r["mean_delta_portfolio_return_20d"]),
            -float(r["mean_intensity_on_drawdown_days"] or 0.0),
        ),
    )


def _hold_exit_profiles(df: pd.DataFrame) -> list[dict[str, Any]]:
    hedge = df[
        (df["execution_regime"].astype(str) == "ncf_late_bull_hedge")
        & df["delta_portfolio_return_20d"].notna()
    ].copy()
    if hedge.empty:
        return []

    profiles: dict[str, pd.Series] = {
        "current_h5_exit": pd.Series(1.0, index=hedge.index),
    }
    for threshold in [0.30, 0.35, 0.40, 0.45]:
        profiles[f"exit_after_gain_prob>={threshold:.2f}"] = _stateful_exit_scale(
            hedge,
            exit_signal=hedge["prob_fwd_gain_gt5_h20"] >= threshold,
        )
    for threshold in [0.35, 0.40, 0.45, 0.50]:
        profiles[f"exit_after_h5_prob>={threshold:.2f}"] = _stateful_exit_scale(
            hedge,
            exit_signal=hedge["prob_up_h5"] >= threshold,
        )

    rows: list[dict[str, Any]] = []
    drawdown_days = hedge["forward_mdd_h20"] <= -0.05
    for name, scale in profiles.items():
        scaled_delta = hedge["delta_portfolio_return_20d"] * scale
        rows.append({
            "profile": name,
            "hedge_days": int(len(hedge)),
            "active_days_after_exit_rule": int((scale > 0.0).sum()),
            "mean_intensity": float(scale.mean()),
            "mean_delta_portfolio_return_20d": float(scaled_delta.mean()),
            "median_delta_portfolio_return_20d": float(scaled_delta.median()),
            "positive_delta_rate": _rate((scaled_delta > 0.0).astype(float)),
            "mean_intensity_on_drawdown_days": (
                float(scale.loc[drawdown_days].mean()) if drawdown_days.any() else None
            ),
            "drawdown_day_count": int(drawdown_days.sum()),
        })
    return sorted(
        rows,
        key=lambda r: (
            -float(r["mean_delta_portfolio_return_20d"]),
            -float(r["mean_intensity_on_drawdown_days"] or 0.0),
        ),
    )


def _stateful_exit_scale(hedge: pd.DataFrame, exit_signal: pd.Series) -> pd.Series:
    scale = pd.Series(1.0, index=hedge.index)
    exited = False
    previous: pd.Timestamp | None = None
    for dt in hedge.index:
        if previous is not None and (dt - previous).days > 4:
            exited = False
        if exited:
            scale.loc[dt] = 0.0
        if bool(exit_signal.loc[dt]):
            exited = True
        previous = dt
    return scale


def evaluate(
    panel_path: Path,
    frame_path: Path,
    db_path: Path,
    horizon: int = 20,
    shifted_00631l_weight: float = 0.05264130224629131,
) -> tuple[dict[str, Any], pd.DataFrame]:
    panel = _load_panel(panel_path)
    frame = _load_frame(frame_path)

    start = str(min(panel.index.min(), frame.index.min()).date())
    end = str(max(panel.index.max(), frame.index.max()).date())
    prices = _load_prices(db_path, ["0050.TW", "00631L.TW"], start, end)
    fwd = _forward_returns(prices, horizon)

    merged = frame.join(panel, how="inner").join(fwd, how="left")
    merged["late_bull_eligible"] = (
        (merged["base_regime"].astype(str) == "golden1")
        & (merged["ma_gap"] > 0.10)
    )
    merged["a2118_initial_trigger"] = (
        merged["late_bull_eligible"]
        & (merged["prob_up_h20"] < 0.33)
        & (merged["confidence"] > 0.55)
    )
    incomplete = merged[[f"fwd_0050.TW_ret_{horizon}d", f"fwd_00631L.TW_ret_{horizon}d"]].isna().any(axis=1)
    merged["hedge_beats_base_20d"] = (
        merged[f"fwd_0050.TW_ret_{horizon}d"] > merged[f"fwd_00631L.TW_ret_{horizon}d"]
    ).astype(float)
    merged.loc[incomplete, "hedge_beats_base_20d"] = pd.NA
    merged["return_spread_0050_minus_00631l_20d"] = (
        merged[f"fwd_0050.TW_ret_{horizon}d"] - merged[f"fwd_00631L.TW_ret_{horizon}d"]
    )
    merged["delta_portfolio_return_20d"] = (
        shifted_00631l_weight * merged["return_spread_0050_minus_00631l_20d"]
    )

    h20_values = [0.25, 0.28, 0.30, 0.33, 0.35, 0.38, 0.40, 0.45]
    conf_values = [0.45, 0.50, 0.55, 0.60, 0.65]
    grid = _grid_eval(merged, h20_values, conf_values)
    summary = {
        "label_definition": "hedge_beats_base_20d = fwd_return_0050_20d > fwd_return_00631L_20d",
        "horizon_days": horizon,
        "shifted_00631l_weight": shifted_00631l_weight,
        "inputs": {
            "panel": str(panel_path),
            "frame": str(frame_path),
            "db": str(db_path),
        },
        "slices": [
            _summarize_slice("all_labeled", merged),
            _summarize_slice("golden1", merged[merged["base_regime"].astype(str) == "golden1"]),
            _summarize_slice("late_bull_eligible", merged[merged["late_bull_eligible"]]),
            _summarize_slice("a2118_initial_trigger", merged[merged["a2118_initial_trigger"]]),
            _summarize_slice("a2118_hedge_execution_days", merged[merged["execution_regime"].astype(str) == "ncf_late_bull_hedge"]),
        ],
        "grid": grid,
        "best_grid_min_2_triggers": _best_grid_with_min_count(grid, 2)[:10],
        "best_grid_min_3_triggers": _best_grid_with_min_count(grid, 3)[:10],
        "recovery_gate_grid": _recovery_gate_grid(merged),
        "tiered_deleverage_profiles": _tiered_deleverage_profiles(merged),
        "hold_exit_profiles": _hold_exit_profiles(merged),
    }
    return summary, merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--frame", default=str(DEFAULT_FRAME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--shifted-00631l-weight", type=float, default=0.05264130224629131)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    summary, frame = evaluate(
        _resolve(args.panel),
        _resolve(args.frame),
        _resolve(args.db),
        horizon=args.horizon,
        shifted_00631l_weight=args.shifted_00631l_weight,
    )

    output = _resolve(args.output)
    csv_output = _resolve(args.csv_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    frame.to_csv(csv_output, encoding="utf-8-sig")
    print(f"Opportunity-cost JSON: {output.resolve()}")
    print(f"Opportunity-cost CSV: {csv_output.resolve()}")
    print(json.dumps(summary["slices"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
