#!/usr/bin/env python3
"""Full-model walk-forward comparison: NCF TSM-ADR dynamic lag (arXiv 2511.00390 follow-up).

Research-only. Follows up on evaluate_group_a_plus_2511_00390_dynamic_lag_diagnostic.py,
which found (via rolling cross-correlation only) that the fixed lag=1 NCF
uses for `us_tsm_adr_ret` is the best lag in only 66-77% of rolling windows
against 0050.TW/2330.TW -- much less stable than QQQ/SOXX (92-99%). This
script asks the real question: does replacing the fixed lag with a causal,
day-by-day adaptive lag (chosen from trailing correlation only, no
lookahead) actually improve the full NCF classifier ensemble's walk-forward
AUC, or does the signal get diluted the way the institutional-flow
normalization feature did (see
evaluate_group_a_plus_ncf_flow_zscore_walkforward.py)?

Method: identical harness to the flow z-score follow-up. Two EXT_FEATURES
panels, identical except for `us_tsm_adr_ret`:
  - baseline: production panel from load_external_df (fixed shift=1).
  - dynamic_lag: for each trading day t, using only TSM/0050 returns strictly
    before t (rolling 126-day window, causal), pick whichever lag in {0,1,2,3}
    has the highest trailing |correlation| with 0050.TW returns, then use
    TSM's return at that lag as the feature value for day t.

Never modifies ncf_0050.py, never retrains the production model artifact,
never changes target weights or the daily pipeline.
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
SCRIPTS_MISC = PROJECT_ROOT / "scripts" / "misc"
if str(SCRIPTS_MISC) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_MISC))

from FinRL.data.stock_db import DB_PATH
from ncf_0050 import build_dataset, load_data, load_external_df, train_classifier
from ncf_external_cache import fetch_yf_close_cached

TICKER = "0050.TW"
LEADER = "TSM"
FEATURE_COLUMN = "us_tsm_adr_ret"
CANDIDATE_LAGS = (0, 1, 2, 3)
CURRENT_PRODUCTION_LAG = 1
ROLLING_WINDOW_DAYS = 126
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ncf_tsm_dynamic_lag_walkforward_diagnostic.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ncf_tsm_dynamic_lag_walkforward_diagnostic.md"
MODEL_NAMES = ("rf", "et", "hgb", "gb", "ensemble")


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def build_dynamic_lag_column(main_df: pd.DataFrame, db_path: Path) -> pd.Series:
    """Causal, no-lookahead adaptive-lag version of us_tsm_adr_ret.

    At each trading day t, uses only TSM/0050 returns strictly before t
    (a trailing ROLLING_WINDOW_DAYS window) to pick the candidate lag with
    the highest trailing |correlation| against 0050.TW returns, then reads
    TSM's return at that lag as of day t. This mirrors the causal design of
    rolling_optimal_lag() in evaluate_group_a_plus_2511_00390_dynamic_lag_diagnostic.py,
    but is shifted one extra step relative to that diagnostic script (lag
    selection uses data up to t-1, applied at t) so it is safe to use as a
    live feature and not just a descriptive diagnostic.
    """
    idx = main_df.index
    start_ext = (idx[0] - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    end_ext = (idx[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    tsm_close = fetch_yf_close_cached(LEADER, start_ext, end_ext, db_path, allow_download=False)
    tsm_ret = tsm_close.pct_change().reindex(idx, method="ffill")
    target_ret = main_df["close"].pct_change()

    lagged = pd.DataFrame({lag: tsm_ret.shift(lag) for lag in CANDIDATE_LAGS})
    joined = lagged.join(target_ret.rename("target"))

    out = pd.Series(index=idx, dtype=float)
    for i in range(len(idx)):
        if i < ROLLING_WINDOW_DAYS + 1:
            out.iloc[i] = joined[CURRENT_PRODUCTION_LAG].iloc[i]
            continue
        # Trailing window strictly before day i (no lookahead): rows [i-1-W, i-1).
        block = joined.iloc[max(0, i - 1 - ROLLING_WINDOW_DAYS) : i - 1].dropna()
        if len(block) < ROLLING_WINDOW_DAYS // 2:
            out.iloc[i] = joined[CURRENT_PRODUCTION_LAG].iloc[i]
            continue
        corrs = {lag: block[lag].corr(block["target"]) for lag in CANDIDATE_LAGS}
        best_lag = max(corrs, key=lambda k: abs(corrs[k]) if corrs[k] == corrs[k] else -1.0)
        out.iloc[i] = joined[best_lag].iloc[i]
    return out


def expanding_walk_forward(
    X: pd.DataFrame,
    y_return: pd.Series,
    y_direction: pd.Series,
    n_windows: int,
) -> list[dict[str, Any]]:
    n_total = len(X)
    min_train = 300
    remaining = n_total - min_train
    step = max(remaining // n_windows, 50)

    windows: list[dict[str, Any]] = []
    for i in range(n_windows):
        train_end = min_train + i * step
        test_start = train_end
        test_end = min(test_start + step, n_total)
        if train_end >= n_total - 20 or test_start >= n_total:
            break

        X_train, X_test = X.iloc[:train_end], X.iloc[test_start:test_end]
        y_train_dir = y_direction.iloc[:train_end].to_numpy()
        y_return_test = y_return.iloc[test_start:test_end]
        y_test_bin = (y_return_test.to_numpy() > 0).astype(int)

        nonneutral = y_train_dir != -1
        X_fit = X_train[nonneutral]
        y_fit = y_train_dir[nonneutral]
        if len(X_fit) < 30 or len(np.unique(y_fit)) < 2 or len(X_test) < 20:
            continue
        if len(np.unique(y_test_bin)) < 2:
            continue

        print(f"    [walk-forward] window {i}: train={len(X_fit)} test={len(X_test)} ...", flush=True)
        clf = train_classifier(X_fit, y_fit, X_test, y_test_bin, do_feature_selection=False)
        window_result = {"window": i, "train_rows": int(len(X_fit)), "test_rows": int(len(X_test))}
        for name in MODEL_NAMES:
            if name in clf:
                window_result[f"{name}_auc"] = _finite(clf[name].get("auc"))
                window_result[f"{name}_accuracy"] = _finite(clf[name].get("accuracy"))
        windows.append(window_result)
    return windows


def build_report(*, db_path: Path, start: str, end: str, horizon: int, n_windows: int) -> dict[str, Any]:
    main_df = load_data(db_path, TICKER, start, end)
    baseline_ext = load_external_df(main_df, db_path)
    dynamic_ext = baseline_ext.copy()
    dynamic_ext[FEATURE_COLUMN] = build_dynamic_lag_column(main_df, db_path).reindex(dynamic_ext.index)

    results: dict[str, Any] = {}
    for variant_name, ext_df in [("baseline_fixed_lag1", baseline_ext), ("dynamic_lag", dynamic_ext)]:
        X, y_return, y_direction, available_features = build_dataset(main_df, horizon=horizon, ext_df=ext_df)
        windows = expanding_walk_forward(X, y_return, y_direction, n_windows=n_windows)
        avg: dict[str, Any] = {}
        for name in MODEL_NAMES:
            aucs = [w[f"{name}_auc"] for w in windows if w.get(f"{name}_auc") is not None]
            accs = [w[f"{name}_accuracy"] for w in windows if w.get(f"{name}_accuracy") is not None]
            avg[f"{name}_avg_auc"] = float(np.mean(aucs)) if aucs else None
            avg[f"{name}_avg_accuracy"] = float(np.mean(accs)) if accs else None
        results[variant_name] = {
            "n_features": len(available_features),
            "n_windows_run": len(windows),
            "windows": windows,
            "averages": avg,
        }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ncf_tsm_dynamic_lag_walkforward_diagnostic",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2511.00390.pdf",
            "follow_up_of": "scripts/evaluate/evaluate_group_a_plus_2511_00390_dynamic_lag_diagnostic.py",
        },
        "policy": "research_only_full_model_walk_forward_comparison_no_production_model_change",
        "status": "diagnostic_available",
        "parameters": {"start": start, "end": end, "ticker": TICKER, "horizon": horizon, "n_windows": n_windows},
        "results": results,
        "decision": {"review_complete": True, "changes_ncf_production_model": False, "changes_target_weights": False},
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# NCF TSM-ADR Dynamic Lag Walk-Forward Comparison",
        "",
        f"- Status: `{report['status']}`",
        f"- Horizon: `{report['parameters']['horizon']}`d, windows: `{report['parameters']['n_windows']}`",
        "",
        "| variant | model | avg AUC | avg accuracy | windows |",
        "|---|---|---:|---:|---:|",
    ]
    for variant_name, row in report["results"].items():
        for name in MODEL_NAMES:
            avg = row["averages"]
            lines.append(
                "| {v} | {m} | {auc} | {acc} | {n} |".format(
                    v=variant_name,
                    m=name,
                    auc=_fmt(avg.get(f"{name}_avg_auc")),
                    acc=_fmt(avg.get(f"{name}_avg_accuracy")),
                    n=row["n_windows_run"],
                )
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Research-only full-model walk-forward comparison.",
            "- Does not modify scripts/misc/ncf_0050.py or retrain the production NCF model artifact.",
            "- Does not change target weights, orders, or the daily pipeline.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2019-01-02")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--n-windows", type=int, default=6)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(
        db_path=Path(args.db), start=args.start, end=args.end, horizon=args.horizon, n_windows=args.n_windows
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"NCF TSM dynamic lag walk-forward diagnostic: {output}")
    for variant_name, row in report["results"].items():
        print(variant_name, json.dumps(row["averages"], ensure_ascii=False))


if __name__ == "__main__":
    main()
