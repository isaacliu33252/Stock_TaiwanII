#!/usr/bin/env python3
"""Full-model walk-forward comparison: NCF institutional-flow normalization (arXiv 2601.07131 follow-up).

Research-only. Follows up on the single-feature diagnostic in
evaluate_group_a_plus_2601_07131_flow_normalization.py, which found that an
expanding z-score of 0050.TW institutional/foreign net-buy flow is the only
normalization variant with above-chance AUC in BOTH the pre-2024 and
post-2024 (large scale-shift) periods, at every horizon tested (5/10/20d),
as a single feature. This script asks the real question: does that hold up
once the feature is fed into the actual NCF classifier ensemble alongside
every other production feature, evaluated by expanding walk-forward AUC and
direction accuracy (not just a single-feature IC)?

Method: reuse `scripts/misc/ncf_0050.py`'s own `load_data`,
`load_external_df`, `build_dataset`, and `train_classifier` unchanged. Build
two EXT_FEATURES panels that are IDENTICAL except for `inst_foreign_net`,
`inst_total_net`, `inst_foreign_ma5`:
  - baseline: production panel from `load_external_df` (net_buy / (close * 1e6)).
  - zscore:   same three columns recomputed as an expanding (no-lookahead) z-
    score of the raw net_buy series, using the identical reindex/ffill/shift(1)
    convention `load_external_df` already uses for these columns.
Then run a plain expanding-window walk-forward loop (simpler than
`walk_forward_evaluate`'s regime-split logic, to keep the two variants
directly comparable) and compare AUC/accuracy per model, per window.

Never modifies ncf_0050.py, never retrains or overwrites the production NCF
model artifact, never changes target weights or the daily pipeline.
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
SCRIPTS_MISC = PROJECT_ROOT / "scripts" / "misc"
if str(SCRIPTS_MISC) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_MISC))

from FinRL.data.stock_db import DB_PATH
from ncf_0050 import build_dataset, load_data, load_external_df, train_classifier

TICKER = "0050.TW"
FLOW_COLUMNS = ("inst_foreign_net", "inst_total_net", "inst_foreign_ma5")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ncf_flow_zscore_walkforward_diagnostic.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/ncf_flow_zscore_walkforward_diagnostic.md"
MODEL_NAMES = ("rf", "et", "hgb", "gb", "ensemble")


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def build_zscore_flow_columns(main_df: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """Recompute inst_foreign_net/inst_total_net/inst_foreign_ma5 as an
    expanding, no-lookahead z-score of the raw net-buy series, using the same
    reindex(ffill)+shift(1) convention `load_external_df` uses for these
    columns (T-1 information as of trading day T)."""
    idx = main_df.index
    start_ext = (idx[0] - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    end_ext = (idx[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        inst = con.execute(
            "SELECT dt, foreign_net_buy, institutional_total_net_buy FROM institutional_data "
            "WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [TICKER, start_ext, end_ext],
        ).fetchdf()
    finally:
        con.close()

    out = pd.DataFrame(index=idx)
    if inst.empty:
        out["inst_foreign_net"] = 0.0
        out["inst_total_net"] = 0.0
        out["inst_foreign_ma5"] = 0.0
        return out

    inst["dt"] = pd.to_datetime(inst["dt"])
    inst = inst.set_index("dt").sort_index()

    def _expanding_z(raw: pd.Series) -> pd.Series:
        exp_mean = raw.expanding(min_periods=252).mean()
        exp_std = raw.expanding(min_periods=252).std()
        return (raw - exp_mean) / exp_std.replace(0.0, np.nan)

    z_foreign = _expanding_z(inst["foreign_net_buy"])
    z_total = _expanding_z(inst["institutional_total_net_buy"])

    zg = pd.DataFrame({"z_foreign": z_foreign, "z_total": z_total}).reindex(idx, method="ffill").shift(1)
    out["inst_foreign_net"] = zg["z_foreign"].values
    out["inst_total_net"] = zg["z_total"].values
    z_foreign_ma5 = z_foreign.reindex(idx, method="ffill").rolling(5).mean().shift(1)
    out["inst_foreign_ma5"] = z_foreign_ma5.values
    return out


def expanding_walk_forward(
    X: pd.DataFrame,
    y_return: pd.Series,
    y_direction: pd.Series,
    n_windows: int,
) -> list[dict[str, Any]]:
    """Simple expanding-window walk-forward (combined, no regime split) so
    the baseline and zscore variants are directly comparable window-for-window."""
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


def regime_split_walk_forward(
    X: pd.DataFrame,
    y_return: pd.Series,
    y_direction: pd.Series,
    n_windows: int,
) -> list[dict[str, Any]]:
    """Regime-split expanding walk-forward, mirroring ncf_0050.py's own
    walk_forward_evaluate() bull/bear branching exactly (same above_ma200
    split, same fallback-to-combined conditions), but additionally captures
    AUC per model (walk_forward_evaluate only tracks accuracy) so this can be
    compared against evaluate_group_a_plus_ncf_flow_zscore_walkforward.py's
    simplified combined-only harness. This is the production promotion-bar
    evaluation protocol, not a simplified stand-in for it."""
    n_total = len(X)
    min_train = 300
    remaining = n_total - min_train
    step = max(remaining // n_windows, 50)

    windows: list[dict[str, Any]] = []
    for i in range(n_windows):
        train_end = min_train + i * step
        test_start = train_end
        test_end = min(test_start + step, n_total)
        if train_end >= n_total - 50 or test_start >= n_total:
            break

        X_train, X_test = X.iloc[:train_end], X.iloc[test_start:test_end]
        y_train_ret, y_test_ret = y_return.iloc[:train_end], y_return.iloc[test_start:test_end]
        y_train_dir = y_direction.iloc[:train_end].to_numpy()

        if len(X_test) < 20:
            continue
        y_test_dir = y_direction.iloc[test_start:test_end].to_numpy()
        n_up_test = (y_test_dir == 1).sum()
        n_down_test = (y_test_dir == 0).sum()
        if n_up_test == 0 or n_down_test == 0:
            continue

        above_ma200_train = X_train["above_ma200"] >= 0.5
        above_ma200_test = X_test["above_ma200"] >= 0.5

        bull_nonneutral = y_train_dir[above_ma200_train.values] != -1
        bear_nonneutral = y_train_dir[(~above_ma200_train).values] != -1
        X_bull_fit = X_train[above_ma200_train][bull_nonneutral]
        y_bull_fit = y_train_dir[above_ma200_train.values][bull_nonneutral]
        X_bear_fit = X_train[~above_ma200_train][bear_nonneutral]
        y_bear_fit = y_train_dir[(~above_ma200_train).values][bear_nonneutral]

        both_test_regimes = above_ma200_test.sum() >= 1 and (~above_ma200_test).sum() >= 1
        bull_fit_ok = len(X_bull_fit) >= 5 and len(np.unique(y_bull_fit)) >= 2
        bear_fit_ok = len(X_bear_fit) >= 5 and len(np.unique(y_bear_fit)) >= 2
        use_regime_split = both_test_regimes and bull_fit_ok and bear_fit_ok

        window_result: dict[str, Any] = {"window": i, "train_rows": int(len(X_train)), "test_rows": int(len(X_test))}
        collected: dict[str, dict[str, list[float]]] = {name: {"auc": [], "accuracy": []} for name in MODEL_NAMES}

        if use_regime_split:
            y_bull_test_bin = (y_test_ret.values[above_ma200_test.values] > 0).astype(int)
            y_bear_test_bin = (y_test_ret.values[(~above_ma200_test).values] > 0).astype(int)
            print(
                f"    [walk-forward regime-split] window {i}: bull_train={len(X_bull_fit)} "
                f"bear_train={len(X_bear_fit)} test={len(X_test)} ...",
                flush=True,
            )
            clf_bull = train_classifier(X_bull_fit, y_bull_fit, X_test[above_ma200_test], y_bull_test_bin, do_feature_selection=False)
            clf_bear = train_classifier(X_bear_fit, y_bear_fit, X_test[~above_ma200_test], y_bear_test_bin, do_feature_selection=False)
            window_result["mode"] = "regime-split"
            for clf in (clf_bull, clf_bear):
                for name in MODEL_NAMES:
                    if name in clf:
                        auc = _finite(clf[name].get("auc"))
                        acc = _finite(clf[name].get("accuracy"))
                        if auc is not None:
                            collected[name]["auc"].append(auc)
                        if acc is not None:
                            collected[name]["accuracy"].append(acc)
        else:
            nonneutral_all = y_train_dir != -1
            X_combined = X_train[nonneutral_all]
            y_combined = y_train_dir[nonneutral_all]
            y_test_bin_all = (y_test_ret.values > 0).astype(int)
            if len(X_combined) < 10 or len(np.unique(y_combined)) < 2 or len(np.unique(y_test_bin_all)) < 2:
                continue
            print(f"    [walk-forward combined-fallback] window {i}: train={len(X_combined)} test={len(X_test)} ...", flush=True)
            clf_combined = train_classifier(X_combined, y_combined, X_test, y_test_bin_all, do_feature_selection=False)
            window_result["mode"] = "combined-fallback"
            for name in MODEL_NAMES:
                if name in clf_combined:
                    auc = _finite(clf_combined[name].get("auc"))
                    acc = _finite(clf_combined[name].get("accuracy"))
                    if auc is not None:
                        collected[name]["auc"].append(auc)
                    if acc is not None:
                        collected[name]["accuracy"].append(acc)

        for name in MODEL_NAMES:
            window_result[f"{name}_auc"] = float(np.mean(collected[name]["auc"])) if collected[name]["auc"] else None
            window_result[f"{name}_accuracy"] = (
                float(np.mean(collected[name]["accuracy"])) if collected[name]["accuracy"] else None
            )
        windows.append(window_result)
    return windows


def build_report(*, db_path: Path, start: str, end: str, horizon: int, n_windows: int, regime_split: bool = False) -> dict[str, Any]:
    main_df = load_data(db_path, TICKER, start, end)
    baseline_ext = load_external_df(main_df, db_path)
    zscore_ext = baseline_ext.copy()
    zscore_flow = build_zscore_flow_columns(main_df, db_path)
    for col in FLOW_COLUMNS:
        zscore_ext[col] = zscore_flow[col].reindex(zscore_ext.index)

    walk_forward_fn = regime_split_walk_forward if regime_split else expanding_walk_forward

    results: dict[str, Any] = {}
    for variant_name, ext_df in [("baseline_price_scaled", baseline_ext), ("expanding_zscore", zscore_ext)]:
        X, y_return, y_direction, available_features = build_dataset(main_df, horizon=horizon, ext_df=ext_df)
        windows = walk_forward_fn(X, y_return, y_direction, n_windows=n_windows)
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
        "report_type": "group_a_plus_ncf_flow_zscore_walkforward_diagnostic",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2601.07131.pdf",
            "follow_up_of": "scripts/evaluate/evaluate_group_a_plus_2601_07131_flow_normalization.py",
        },
        "policy": "research_only_full_model_walk_forward_comparison_no_production_model_change",
        "status": "diagnostic_available",
        "parameters": {
            "start": start,
            "end": end,
            "ticker": TICKER,
            "horizon": horizon,
            "n_windows": n_windows,
            "regime_split": regime_split,
        },
        "results": results,
        "decision": {
            "review_complete": True,
            "changes_ncf_production_model": False,
            "changes_target_weights": False,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# NCF Institutional-Flow Z-Score Walk-Forward Comparison",
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
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--n-windows", type=int, default=8)
    parser.add_argument(
        "--regime-split",
        action="store_true",
        help="Use ncf_0050.py's own bull/bear regime-split walk-forward protocol (the real promotion bar) instead of the simplified combined-only harness.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        n_windows=args.n_windows,
        regime_split=args.regime_split,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"NCF flow z-score walk-forward diagnostic: {output}")
    for variant_name, row in report["results"].items():
        print(variant_name, json.dumps(row["averages"], ensure_ascii=False))


if __name__ == "__main__":
    main()
