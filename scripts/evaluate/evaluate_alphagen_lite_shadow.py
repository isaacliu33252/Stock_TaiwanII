#!/usr/bin/env python3
"""Research-only AlphaGen-lite shadow benchmark for Group A+.

Imports the two ideas from alphagen-master (KDD 2023 "Generating Synergistic
Formulaic Alpha Collections via Reinforcement Learning") that are portable
without the full RL/PPO/Qlib stack:

1. A compact time-series operator algebra (Delta/Mean/Std/WMA/EMA/rolling
   Corr) used to generate candidate formulaic features from the existing
   panel and OHLCV leaves.
2. A greedy linear alpha-pool builder: candidates are ranked by single-alpha
   IC, added one at a time subject to a mutual-IC diversity constraint
   against the current pool, and combined with least-squares weights.

Cross-sectional operators (CSRank/Rank/pairwise Cov-Corr across a large
stock universe) are intentionally excluded: Group A+ only trades 4 highly
correlated Taiwan ETFs, so cross-sectional ranking carries near-zero signal.
Full RL search over the expression tree is also skipped in this v1 -- the
candidate set below is generated deterministically and exhaustively scored,
which is tractable at this scale without a learned search policy.

This script is research-only and does not change live allocation logic.
"""

from __future__ import annotations

import argparse
import itertools
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "alphagen_lite_shadow_latest_20260701.json"

PANEL_LEAF_COLUMNS = (
    "prob_up_h20",
    "h20_prob_up",
    "confidence",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "tail_reward_risk_score_h20",
)
WINDOWS = (5, 10, 20)
CORR_PAIRS = (("0050.TW", "00631L.TW"), ("0050.TW", "00632R.TW"))


def load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        raise ValueError("NCF panel is missing date column")
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").set_index("date")
    if "is_live" in frame.columns:
        frame = frame[~frame["is_live"].astype(bool)]
    for required in ("forward_gain_h20", *PANEL_LEAF_COLUMNS):
        if required not in frame.columns:
            raise ValueError(f"NCF panel is missing {required}")
    return frame


def load_ohlcv(db_path: Path, tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    return {
        field: rows.pivot(index="dt", columns="ticker", values=field).sort_index().astype(float)
        for field in ("close", "volume")
    }


def build_leaf_frame(panel: pd.DataFrame, ohlcv: dict[str, pd.DataFrame], tickers: list[str]) -> pd.DataFrame:
    close = ohlcv["close"][tickers].add_prefix("close_")
    volume = ohlcv["volume"][tickers].add_prefix("volume_")
    leaves = panel[list(PANEL_LEAF_COLUMNS)].join(close, how="inner").join(volume, how="inner")
    return leaves.replace([np.inf, -np.inf], np.nan).dropna()


def generate_candidates(leaves: pd.DataFrame) -> pd.DataFrame:
    """AlphaGen-style operator expansion: Delta / Div(x, Mean) / Std / WMA / EMA bias terms."""
    candidates: dict[str, pd.Series] = {}
    for col in leaves.columns:
        series = leaves[col]
        candidates[f"raw__{col}"] = series
        for window in WINDOWS:
            candidates[f"delta{window}__{col}"] = series.pct_change(window)
            rolling = series.rolling(window)
            mean = rolling.mean()
            candidates[f"mean_bias{window}__{col}"] = series / mean.replace(0.0, np.nan) - 1.0
            candidates[f"std_norm{window}__{col}"] = rolling.std() / mean.replace(0.0, np.nan).abs()

            weights = np.arange(1, window + 1, dtype=float)
            weights /= weights.sum()
            wma = rolling.apply(lambda x, w=weights: float(np.dot(x, w)), raw=True)
            candidates[f"wma_bias{window}__{col}"] = series / wma.replace(0.0, np.nan) - 1.0

            ema = series.ewm(span=window, adjust=False).mean()
            candidates[f"ema_bias{window}__{col}"] = series / ema.replace(0.0, np.nan) - 1.0

    for left, right in CORR_PAIRS:
        left_ret = leaves[f"close_{left}"].pct_change()
        right_ret = leaves[f"close_{right}"].pct_change()
        for window in (10, 20):
            candidates[f"corr{window}__{left}_x_{right}"] = left_ret.rolling(window).corr(right_ret)

    frame = pd.DataFrame(candidates, index=leaves.index)
    return frame.replace([np.inf, -np.inf], np.nan)


def _ic(x: pd.Series, y: pd.Series) -> float | None:
    joined = pd.concat([x, y], axis=1).dropna()
    if len(joined) < 5 or joined.iloc[:, 0].std() < 1e-12:
        return None
    value = joined.iloc[:, 0].corr(joined.iloc[:, 1], method="pearson")
    return None if pd.isna(value) else float(value)


def _rank_ic(x: pd.Series, y: pd.Series) -> float | None:
    joined = pd.concat([x, y], axis=1).dropna()
    if len(joined) < 5 or joined.iloc[:, 0].std() < 1e-12:
        return None
    value = joined.iloc[:, 0].corr(joined.iloc[:, 1], method="spearman")
    return None if pd.isna(value) else float(value)


def greedy_pool_select(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    capacity: int,
    ic_lower_bound: float,
    mutual_ic_threshold: float,
) -> tuple[list[str], np.ndarray, pd.Series, pd.Series]:
    single_ic = {col: _ic(features[col], target) for col in features.columns}
    ranked = sorted(
        (col for col, ic in single_ic.items() if ic is not None),
        key=lambda col: abs(single_ic[col]),
        reverse=True,
    )
    strong = [col for col in ranked if abs(single_ic[col]) >= ic_lower_bound]
    candidates_order = strong if strong else ranked[:capacity]

    selected: list[str] = []
    for col in candidates_order:
        if len(selected) >= capacity:
            break
        if selected:
            corr = features[selected + [col]].dropna().corr().loc[col, selected]
            if corr.abs().max() >= mutual_ic_threshold:
                continue
        selected.append(col)

    if not selected:
        return [], np.zeros(0), pd.Series(dtype=float), pd.Series(dtype=float)

    train = features[selected].join(target.rename("__target__")).dropna()
    if len(train) < len(selected) + 2:
        return [], np.zeros(0), pd.Series(dtype=float), pd.Series(dtype=float)
    means = train[selected].mean()
    stds = train[selected].std().replace(0.0, 1.0)
    x = ((train[selected] - means) / stds).to_numpy()
    y = train["__target__"].to_numpy()
    weights, *_ = np.linalg.lstsq(x, y, rcond=None)
    return selected, weights, means, stds  # type: ignore[return-value]


def evaluate(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    n_splits: int,
    gap: int,
    capacity: int,
    ic_lower_bound: float,
    mutual_ic_threshold: float,
) -> dict[str, Any]:
    if len(features) < n_splits + 10:
        raise ValueError("Not enough rows for requested TimeSeriesSplit")

    split = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    folds: list[dict[str, Any]] = []
    baseline_ics: list[float] = []
    baseline_rics: list[float] = []
    pool_ics: list[float] = []
    pool_rics: list[float] = []
    selected_counter: dict[str, int] = {}

    for fold, (train_idx, test_idx) in enumerate(split.split(features), start=1):
        x_train, x_test = features.iloc[train_idx], features.iloc[test_idx]
        y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]

        baseline_ic = _ic(x_test["raw__prob_up_h20"], y_test)
        baseline_ric = _rank_ic(x_test["raw__prob_up_h20"], y_test)

        result = greedy_pool_select(
            x_train,
            y_train,
            capacity=capacity,
            ic_lower_bound=ic_lower_bound,
            mutual_ic_threshold=mutual_ic_threshold,
        )
        selected, weights = result[0], result[1]
        pool_ic = pool_ric = None
        if selected:
            means, stds = result[2], result[3]
            for name in selected:
                selected_counter[name] = selected_counter.get(name, 0) + 1
            x_test_norm = (x_test[selected] - means) / stds
            score = (x_test_norm * weights).sum(axis=1)
            pool_ic = _ic(score, y_test)
            pool_ric = _rank_ic(score, y_test)

        if baseline_ic is not None:
            baseline_ics.append(baseline_ic)
        if baseline_ric is not None:
            baseline_rics.append(baseline_ric)
        if pool_ic is not None:
            pool_ics.append(pool_ic)
        if pool_ric is not None:
            pool_rics.append(pool_ric)

        folds.append({
            "fold": fold,
            "train_start": str(x_train.index[0].date()),
            "train_end": str(x_train.index[-1].date()),
            "test_start": str(x_test.index[0].date()),
            "test_end": str(x_test.index[-1].date()),
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
            "baseline_ic": baseline_ic,
            "baseline_rank_ic": baseline_ric,
            "pool_size": len(selected),
            "pool_alphas": selected,
            "pool_ic": pool_ic,
            "pool_rank_ic": pool_ric,
        })

    baseline_ic_mean = float(np.mean(baseline_ics)) if baseline_ics else None
    baseline_ric_mean = float(np.mean(baseline_rics)) if baseline_rics else None
    pool_ic_mean = float(np.mean(pool_ics)) if pool_ics else None
    pool_ric_mean = float(np.mean(pool_rics)) if pool_rics else None
    ic_delta = (
        pool_ic_mean - baseline_ic_mean if pool_ic_mean is not None and baseline_ic_mean is not None else None
    )
    most_selected = sorted(selected_counter.items(), key=lambda kv: kv[1], reverse=True)[:10]

    promotion_decision = (
        "candidate_for_deeper_ablation"
        if ic_delta is not None and ic_delta >= 0.03
        else "research_only"
    )

    return {
        "folds": folds,
        "aggregate": {
            "baseline": {"feature": "prob_up_h20", "ic": baseline_ic_mean, "rank_ic": baseline_ric_mean},
            "alphagen_lite_pool": {
                "ic": pool_ic_mean,
                "rank_ic": pool_ric_mean,
                "ic_delta_vs_baseline": ic_delta,
                "rank_ic_delta_vs_baseline": (
                    pool_ric_mean - baseline_ric_mean
                    if pool_ric_mean is not None and baseline_ric_mean is not None
                    else None
                ),
                "most_selected_alphas": most_selected,
            },
            "promotion_decision": promotion_decision,
        },
    }


def build_report(
    *,
    panel_path: Path,
    db_path: Path,
    start: str,
    end: str,
    n_splits: int,
    gap: int,
    capacity: int,
    ic_lower_bound: float,
    mutual_ic_threshold: float,
) -> dict[str, Any]:
    panel = load_panel(panel_path)
    ohlcv = load_ohlcv(db_path, list(TICKERS), start, end)
    leaves = build_leaf_frame(panel, ohlcv, list(TICKERS))
    candidates = generate_candidates(leaves)
    target = panel["forward_gain_h20"].astype(float)
    valid_index = candidates.dropna().index.intersection(target.index)
    features = candidates.loc[valid_index]
    target = target.loc[valid_index]

    evaluation = evaluate(
        features,
        target,
        n_splits=n_splits,
        gap=gap,
        capacity=capacity,
        ic_lower_bound=ic_lower_bound,
        mutual_ic_threshold=mutual_ic_threshold,
    )

    return {
        "schema_version": 1,
        "report_type": "alphagen_lite_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "alphagen_source": "C:\\Users\\isaac\\Downloads\\alphagen-master\\alphagen-master",
            "panel": str(panel_path),
            "db_path": str(db_path),
            "requested_window": {"start": start, "end": end},
            "tickers": list(TICKERS),
            "panel_leaves": list(PANEL_LEAF_COLUMNS),
            "operator_windows": list(WINDOWS),
            "corr_pairs": [f"{a}_x_{b}" for a, b in CORR_PAIRS],
            "candidate_count": int(candidates.shape[1]),
            "feature_rows": int(len(features)),
            "target": "forward_gain_h20 (continuous IC, not binarized)",
            "pool_capacity": capacity,
            "ic_lower_bound": ic_lower_bound,
            "mutual_ic_threshold": mutual_ic_threshold,
        },
        "evaluation": evaluation,
        "method_note": (
            "Research-only import of alphagen-master's operator algebra and greedy "
            "linear alpha-pool selection (mutual-IC diversity constraint + "
            "least-squares combination). Cross-sectional operators (CSRank/Rank) "
            "and the full RL/PPO search are excluded because Group A+ only trades "
            "4 correlated Taiwan ETFs. Does not affect live allocation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--gap", type=int, default=5)
    parser.add_argument("--capacity", type=int, default=5)
    parser.add_argument("--ic-lower-bound", type=float, default=0.05)
    parser.add_argument("--mutual-ic-threshold", type=float, default=0.7)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_alphagen_lite_shadow")
    try:
        report = build_report(
            panel_path=Path(args.panel),
            db_path=Path(args.db),
            start=args.start,
            end=args.end,
            n_splits=args.n_splits,
            gap=args.gap,
            capacity=args.capacity,
            ic_lower_bound=args.ic_lower_bound,
            mutual_ic_threshold=args.mutual_ic_threshold,
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"alphagen-lite shadow: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
