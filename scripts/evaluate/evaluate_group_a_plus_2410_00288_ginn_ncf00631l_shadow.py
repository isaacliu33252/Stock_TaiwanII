#!/usr/bin/env python3
"""GARCH-informed NCF00631L shadow evaluation for arXiv 2410.00288.

This is a research-only transfer test. It asks whether point-in-time
GARCH/GJR volatility features improve the existing NCF00631L H20 direction
probability in purged walk-forward validation. It never changes live weights,
strategy manifests, golden artifacts, or order generation.
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.gjr_garch_shadow import _fit_garch, _forecast_next_variance  # noqa: E402
from group_a_plus.validation import PurgedWalkForwardSplit  # noqa: E402

DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_ncf00631l_shadow.md"
DEFAULT_PREDICTIONS = PROJECT_ROOT / "results/2410_00288_ginn_ncf00631l_shadow_predictions.csv"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_close(db_path: Path, ticker: str, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ?
              AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No OHLCV rows for {ticker} from {start} to {end}")
    frame["dt"] = pd.to_datetime(frame["dt"]).dt.normalize()
    return frame.set_index("dt")["close"].astype(float).sort_index()


def _logit(prob: pd.Series) -> pd.Series:
    clipped = pd.to_numeric(prob, errors="coerce").clip(1e-5, 1.0 - 1e-5)
    return np.log(clipped / (1.0 - clipped))


def _base_vol_features(returns: pd.Series) -> pd.DataFrame:
    ret = pd.to_numeric(returns, errors="coerce").astype(float)
    out = pd.DataFrame(index=ret.index)
    out["return_1d"] = ret
    out["abs_return_1d"] = ret.abs()
    out["neg_return_flag"] = (ret < 0.0).astype(float)
    out["realized_var_5"] = ret.rolling(5, min_periods=3).var()
    out["realized_var_20"] = ret.rolling(20, min_periods=10).var()
    out["realized_var_60"] = ret.rolling(60, min_periods=20).var()
    out["realized_vol_ratio_20_60"] = out["realized_var_20"] / out["realized_var_60"].replace(0.0, np.nan)
    out["ewma_var_94"] = (ret.pow(2).ewm(alpha=0.06, adjust=False).mean()).shift(0)
    out["vol_cluster_score"] = (
        ret.abs().rolling(5, min_periods=3).mean()
        / ret.abs().rolling(60, min_periods=20).mean().replace(0.0, np.nan)
    )
    return out


def _recursive_variance(params: dict[str, float], returns: pd.Series, *, asymmetric: bool) -> pd.Series:
    values = pd.to_numeric(returns, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if len(values) == 0:
        return pd.Series(dtype=float, index=returns.index)
    variances = np.empty(len(values), dtype=float)
    variances[0] = max(float(np.var(values)), 1e-12)
    for idx in range(1, len(values)):
        variances[idx] = _forecast_next_variance(params, values[idx - 1], variances[idx - 1], asymmetric=asymmetric)
    return pd.Series(variances, index=returns.index)


def _fit_fold_garch_features(train_returns: pd.Series, all_returns: pd.Series) -> pd.DataFrame:
    resid = pd.to_numeric(train_returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(resid) < 120:
        raise RuntimeError(f"Not enough returns for fold GARCH fit: {len(resid)}")
    sym = _fit_garch(resid, asymmetric=False)
    gjr = _fit_garch(resid, asymmetric=True)
    sym_var = _recursive_variance(sym["params"], all_returns, asymmetric=False)
    gjr_var = _recursive_variance(gjr["params"], all_returns, asymmetric=True)
    out = pd.DataFrame(index=all_returns.index)
    out["garch_sym_var"] = sym_var
    out["garch_gjr_var"] = gjr_var
    out["garch_gjr_over_sym"] = gjr_var / sym_var.replace(0.0, np.nan)
    out["garch_sym_persistence"] = float(sym.get("persistence") or np.nan)
    out["garch_gjr_persistence"] = float(gjr.get("persistence") or np.nan)
    out["garch_gjr_gamma"] = float((gjr.get("params") or {}).get("gamma") or 0.0)
    out["garch_disagreement_abs_log"] = np.log(out["garch_gjr_over_sym"].clip(lower=1e-12)).abs()
    return out


def _safe_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float | None:
    if len(np.unique(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, y_prob))


def _metric_row(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, Any]:
    y_pred = (y_prob >= 0.5).astype(int)
    return {
        "rows": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "auc": _safe_auc(y_true, y_prob),
        "brier": float(brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))),
        "positive_rate": float(np.mean(y_true)),
        "predicted_positive_rate": float(np.mean(y_pred)),
    }


def _delta(enhanced: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "accuracy": None if enhanced.get("accuracy") is None else float(enhanced["accuracy"] - baseline["accuracy"]),
        "auc": None
        if enhanced.get("auc") is None or baseline.get("auc") is None
        else float(enhanced["auc"] - baseline["auc"]),
        "brier": None if enhanced.get("brier") is None else float(enhanced["brier"] - baseline["brier"]),
    }


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [row[key] for row in rows if row.get(key) is not None]
    if not vals:
        return None
    return float(np.mean(vals))


def _load_model_frame(panel_path: Path, db_path: Path, ticker: str) -> tuple[pd.DataFrame, pd.Series]:
    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    if "date" not in panel.columns:
        raise ValueError("panel is missing date column")
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel = panel.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if "is_live" in panel.columns:
        panel = panel[~panel["is_live"].astype(bool)].reset_index(drop=True)
    needed = {"prob_up_h20", "actual_up_h20"}
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise ValueError(f"panel missing required columns: {missing}")
    start = str((panel["date"].min() - pd.Timedelta(days=1000)).date())
    end = str(panel["date"].max().date())
    close = _load_close(db_path, ticker, start, end)
    returns = close.pct_change().dropna()
    vol = _base_vol_features(returns)
    frame = panel.set_index("date").join(vol, how="left")
    frame["baseline_prob_up_h20"] = pd.to_numeric(frame["prob_up_h20"], errors="coerce").clip(0.0, 1.0)
    frame["baseline_logit_h20"] = _logit(frame["baseline_prob_up_h20"])
    frame["target_up_h20"] = pd.to_numeric(frame["actual_up_h20"], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame, returns


def evaluate_shadow(
    panel_path: Path,
    db_path: Path,
    *,
    ticker: str = "00631L.TW",
    n_splits: int = 4,
    purge: int = 20,
    min_train_size: int = 160,
) -> tuple[dict[str, Any], pd.DataFrame]:
    frame, returns = _load_model_frame(panel_path, db_path, ticker)
    feature_cols = [
        "baseline_logit_h20",
        "return_1d",
        "abs_return_1d",
        "neg_return_flag",
        "realized_var_5",
        "realized_var_20",
        "realized_var_60",
        "realized_vol_ratio_20_60",
        "ewma_var_94",
        "vol_cluster_score",
        "garch_sym_var",
        "garch_gjr_var",
        "garch_gjr_over_sym",
        "garch_sym_persistence",
        "garch_gjr_persistence",
        "garch_gjr_gamma",
        "garch_disagreement_abs_log",
    ]
    base_feature_cols = [col for col in feature_cols if not col.startswith("garch_")]
    valid = frame.dropna(subset=["target_up_h20", "baseline_prob_up_h20", *base_feature_cols]).copy()
    valid["target_up_h20"] = (valid["target_up_h20"] > 0.0).astype(int)
    splitter = PurgedWalkForwardSplit(n_splits=n_splits, purge=purge, min_train_size=min_train_size)
    folds = list(splitter.split(valid))
    fold_rows: list[dict[str, Any]] = []
    prediction_rows: list[pd.DataFrame] = []

    for fold_id, (train_idx, test_idx) in enumerate(folds, start=1):
        train = valid.iloc[train_idx].copy()
        test = valid.iloc[test_idx].copy()
        train_end = train.index.max()
        all_dates = valid.index
        returns_to_fit = returns.loc[:train_end]
        garch_features = _fit_fold_garch_features(returns_to_fit.tail(756), returns.reindex(all_dates).fillna(0.0))
        train = train.join(garch_features, how="left", rsuffix="_garch")
        test = test.join(garch_features, how="left", rsuffix="_garch")
        train = train.dropna(subset=feature_cols)
        test = test.dropna(subset=feature_cols)
        if train.empty or test.empty or train["target_up_h20"].nunique() < 2:
            fold_rows.append(
                {
                    "fold": fold_id,
                    "status": "skipped",
                    "reason": "empty_train_or_test_or_single_class_train",
                    "train_rows": int(len(train)),
                    "test_rows": int(len(test)),
                }
            )
            continue

        scaler = StandardScaler()
        x_train = scaler.fit_transform(train[feature_cols].astype(float))
        x_test = scaler.transform(test[feature_cols].astype(float))
        y_train = train["target_up_h20"].to_numpy(dtype=int)
        y_test = test["target_up_h20"].to_numpy(dtype=int)
        model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=241000288)
        model.fit(x_train, y_train)
        enhanced_prob = model.predict_proba(x_test)[:, 1]
        baseline_prob = test["baseline_prob_up_h20"].to_numpy(dtype=float)
        baseline_metrics = _metric_row(y_test, baseline_prob)
        enhanced_metrics = _metric_row(y_test, enhanced_prob)
        fold_rows.append(
            {
                "fold": fold_id,
                "status": "ok",
                "train_start": str(train.index.min().date()),
                "train_end": str(train.index.max().date()),
                "test_start": str(test.index.min().date()),
                "test_end": str(test.index.max().date()),
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "baseline": baseline_metrics,
                "garch_informed": enhanced_metrics,
                "delta_garch_informed_minus_baseline": _delta(enhanced_metrics, baseline_metrics),
                "garch_fit_train_end": str(train_end.date()),
            }
        )
        pred = pd.DataFrame(
            {
                "date": [str(idx.date()) for idx in test.index],
                "fold": fold_id,
                "target_up_h20": y_test,
                "baseline_prob_up_h20": baseline_prob,
                "garch_informed_prob_up_h20": enhanced_prob,
            }
        )
        prediction_rows.append(pred)

    ok_rows = [row for row in fold_rows if row.get("status") == "ok"]
    baseline_summary = {
        "folds": int(len(ok_rows)),
        "accuracy": _mean_metric([row["baseline"] for row in ok_rows], "accuracy"),
        "auc": _mean_metric([row["baseline"] for row in ok_rows], "auc"),
        "brier": _mean_metric([row["baseline"] for row in ok_rows], "brier"),
    }
    enhanced_summary = {
        "folds": int(len(ok_rows)),
        "accuracy": _mean_metric([row["garch_informed"] for row in ok_rows], "accuracy"),
        "auc": _mean_metric([row["garch_informed"] for row in ok_rows], "auc"),
        "brier": _mean_metric([row["garch_informed"] for row in ok_rows], "brier"),
    }
    delta_summary = _delta(enhanced_summary, baseline_summary)
    acc_passes = sum((row["delta_garch_informed_minus_baseline"].get("accuracy") or 0.0) > 0.0 for row in ok_rows)
    auc_passes = sum((row["delta_garch_informed_minus_baseline"].get("auc") or 0.0) > 0.0 for row in ok_rows)
    brier_passes = sum((row["delta_garch_informed_minus_baseline"].get("brier") or 0.0) < 0.0 for row in ok_rows)
    promotion_like_pass = (
        bool(ok_rows)
        and delta_summary["accuracy"] is not None
        and delta_summary["brier"] is not None
        and delta_summary["accuracy"] > 0.0
        and delta_summary["brier"] < 0.0
        and acc_passes >= max(1, int(np.ceil(len(ok_rows) * 0.75)))
        and brier_passes >= max(1, int(np.ceil(len(ok_rows) * 0.75)))
    )
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_2410_00288_ginn_ncf00631l_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2410.00288",
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "inputs": {
            "panel": str(panel_path),
            "db_path": str(db_path),
            "ticker": ticker,
            "baseline_probability_column": "prob_up_h20",
            "target_column": "actual_up_h20",
        },
        "window": {
            "date_start": str(valid.index.min().date()) if not valid.empty else None,
            "date_end": str(valid.index.max().date()) if not valid.empty else None,
            "rows": int(len(valid)),
            "non_live_only": True,
        },
        "split": {
            "n_splits": n_splits,
            "purge": purge,
            "min_train_size": min_train_size,
        },
        "feature_sets": {
            "baseline": ["prob_up_h20"],
            "garch_informed": feature_cols,
            "paper_transfer": "GARCH variance teacher/proxy features plus logistic calibration, not full production GINN retraining.",
        },
        "summary": {
            "baseline": baseline_summary,
            "garch_informed": enhanced_summary,
            "delta_garch_informed_minus_baseline": delta_summary,
            "fold_pass_counts": {
                "accuracy_improved": int(acc_passes),
                "auc_improved": int(auc_passes),
                "brier_improved": int(brier_passes),
                "ok_folds": int(len(ok_rows)),
            },
            "promotion_like_metric_passed": promotion_like_pass,
        },
        "folds": fold_rows,
        "decision": {
            "promotion_allowed": False,
            "decision": "shadow_only",
            "reason": (
                "Even if fold metrics improve, this is a lightweight GARCH-informed calibration shadow. "
                "A production change requires full NCF retraining, ablation, cost/portfolio replay, and live-forward evidence."
            ),
            "next_step": "train_candidate_ncf00631l_with_garch_volatility_features_and_auxiliary_volatility_head",
        },
    }
    predictions = pd.concat(prediction_rows, ignore_index=True) if prediction_rows else pd.DataFrame()
    return report, predictions


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "NA"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# 2410.00288 GARCH-Informed NCF00631L Shadow",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Promotion allowed: `{report['decision']['promotion_allowed']}`",
        f"- Window: `{report['window']['date_start']}` to `{report['window']['date_end']}` rows=`{report['window']['rows']}`",
        "",
        "## Aggregate Metrics",
        "",
        "| model | folds | accuracy | auc | brier |",
        "|---|---:|---:|---:|---:|",
        (
            f"| baseline NCF prob_up_h20 | {summary['baseline']['folds']} | "
            f"{_fmt(summary['baseline']['accuracy'])} | {_fmt(summary['baseline']['auc'])} | "
            f"{_fmt(summary['baseline']['brier'])} |"
        ),
        (
            f"| GARCH-informed calibration | {summary['garch_informed']['folds']} | "
            f"{_fmt(summary['garch_informed']['accuracy'])} | {_fmt(summary['garch_informed']['auc'])} | "
            f"{_fmt(summary['garch_informed']['brier'])} |"
        ),
        (
            f"| delta |  | {_fmt(summary['delta_garch_informed_minus_baseline']['accuracy'])} | "
            f"{_fmt(summary['delta_garch_informed_minus_baseline']['auc'])} | "
            f"{_fmt(summary['delta_garch_informed_minus_baseline']['brier'])} |"
        ),
        "",
        "## Fold Pass Counts",
        "",
        f"- Accuracy improved: `{summary['fold_pass_counts']['accuracy_improved']}/{summary['fold_pass_counts']['ok_folds']}`",
        f"- AUC improved: `{summary['fold_pass_counts']['auc_improved']}/{summary['fold_pass_counts']['ok_folds']}`",
        f"- Brier improved: `{summary['fold_pass_counts']['brier_improved']}/{summary['fold_pass_counts']['ok_folds']}`",
        f"- Promotion-like metric passed: `{summary['promotion_like_metric_passed']}`",
        "",
        "## Fold Details",
        "",
        "| fold | test | baseline acc | enhanced acc | dAcc | baseline brier | enhanced brier | dBrier |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["folds"]:
        if row.get("status") != "ok":
            lines.append(f"| {row['fold']} | skipped |  |  |  |  |  |  |")
            continue
        delta = row["delta_garch_informed_minus_baseline"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["fold"]),
                    f"{row['test_start']} to {row['test_end']}",
                    _fmt(row["baseline"]["accuracy"]),
                    _fmt(row["garch_informed"]["accuracy"]),
                    _fmt(delta["accuracy"]),
                    _fmt(row["baseline"]["brier"]),
                    _fmt(row["garch_informed"]["brier"]),
                    _fmt(delta["brier"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "此結果只支持 research/shadow。若要導入最新策略，下一步必須重訓 NCF00631L candidate，做 feature ablation、portfolio replay、交易成本與 live-forward 觀察。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=160)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS))
    args = parser.parse_args()

    report, predictions = evaluate_shadow(
        _resolve(args.panel),
        _resolve(args.db),
        ticker=args.ticker,
        n_splits=args.n_splits,
        purge=args.purge,
        min_train_size=args.min_train_size,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    pred_path = _resolve(args.predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    if not predictions.empty:
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(pred_path, index=False)
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"promotion_like_metric_passed={report['summary']['promotion_like_metric_passed']}")
    print(f"delta={report['summary']['delta_garch_informed_minus_baseline']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")
    print(f"Predictions: {pred_path if not predictions.empty else 'none'}")


if __name__ == "__main__":
    main()
