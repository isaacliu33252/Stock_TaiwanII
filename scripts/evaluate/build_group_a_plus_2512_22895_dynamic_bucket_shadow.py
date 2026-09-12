#!/usr/bin/env python3
"""Build a dynamic two-bucket shadow inspired by arXiv 2512.22895 SAMP-HDRL."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import TICKERS, _float  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import _load_close  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_dynamic_bucket_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_dynamic_bucket_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _sortino(ret: pd.Series, mar: float = 0.0) -> float:
    excess = ret.dropna() - mar
    if excess.empty:
        return np.nan
    downside = excess[excess < 0.0]
    denom = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
    if denom <= 1e-12:
        return np.nan
    return float(excess.mean() / denom)


def _stress_corr(asset_ret: pd.Series, anchor_ret: pd.Series, threshold: float = 0.0) -> float:
    frame = pd.concat([asset_ret, anchor_ret], axis=1).dropna()
    if frame.shape[0] < 10:
        return np.nan
    stressed = frame[frame.iloc[:, 1] < threshold]
    if stressed.shape[0] < 5:
        return np.nan
    return float(stressed.iloc[:, 0].corr(stressed.iloc[:, 1]))


def _feature_frame(window_returns: pd.DataFrame) -> pd.DataFrame:
    anchor = window_returns["0050.TW"] if "0050.TW" in window_returns.columns else window_returns.iloc[:, 0]
    rows: list[dict[str, Any]] = []
    for ticker in window_returns.columns:
        ret = window_returns[ticker].dropna()
        rows.append(
            {
                "ticker": ticker,
                "sortino": _sortino(ret),
                "downside_vol": float(np.sqrt(np.mean(np.square(ret[ret < 0.0])))) if (ret < 0.0).any() else 0.0,
                "momentum_20": float(ret.tail(20).sum()) if len(ret) >= 20 else np.nan,
                "momentum_60": float(ret.tail(60).sum()) if len(ret) >= 60 else np.nan,
                "stress_corr_0050_down": 1.0 if ticker == "0050.TW" else _stress_corr(window_returns[ticker], anchor),
            }
        )
    return pd.DataFrame(rows).set_index("ticker")


def _quality_score(features: pd.DataFrame) -> pd.Series:
    # Higher is better: stronger downside-adjusted return/momentum and lower downside co-movement.
    return (
        features["sortino"].rank(pct=True)
        + features["momentum_20"].rank(pct=True)
        + features["momentum_60"].rank(pct=True)
        + (-features["downside_vol"]).rank(pct=True)
        + (-features["stress_corr_0050_down"]).rank(pct=True)
    ) / 5.0


def _cluster(features: pd.DataFrame, *, random_state: int = 22895) -> tuple[pd.DataFrame, dict[str, Any]]:
    filled = features.copy()
    for col in filled.columns:
        median = filled[col].median()
        filled[col] = filled[col].fillna(0.0 if pd.isna(median) else median)
    if len(filled) < 2:
        out = filled.copy()
        out["bucket"] = "quality"
        out["quality_score"] = 1.0
        return out, {"method": "single_bucket_fallback"}
    scaled = StandardScaler().fit_transform(filled)
    labels = KMeans(n_clusters=2, n_init=20, random_state=random_state).fit_predict(scaled)
    scored = filled.copy()
    scored["cluster"] = labels
    scored["quality_score"] = _quality_score(filled)
    cluster_scores = scored.groupby("cluster")["quality_score"].mean().sort_values(ascending=False)
    quality_cluster = int(cluster_scores.index[0])
    scored["bucket"] = np.where(scored["cluster"] == quality_cluster, "quality", "ordinary")
    return scored, {
        "method": "kmeans_k2_scaled_features",
        "quality_cluster": quality_cluster,
        "cluster_quality_scores": {str(k): _float(v) for k, v in cluster_scores.items()},
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    window: int = 75,
    step: int = 75,
) -> dict[str, Any]:
    blockers: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="all")
    if returns.empty or len(returns) < window:
        blockers.append("insufficient_return_history")
    snapshots: list[dict[str, Any]] = []
    if not blockers:
        positions = list(range(window, len(returns) + 1, step))
        if positions[-1] != len(returns):
            positions.append(len(returns))
        for pos in positions:
            win = returns.iloc[pos - window : pos]
            features = _feature_frame(win)
            clustered, meta = _cluster(features)
            snapshots.append(
                {
                    "as_of": str(returns.index[pos - 1].date()),
                    "window_start": str(win.index[0].date()),
                    "window_end": str(win.index[-1].date()),
                    "cluster_meta": meta,
                    "buckets": {
                        ticker: {
                            "bucket": str(row["bucket"]),
                            "cluster": int(row["cluster"]) if "cluster" in row and not pd.isna(row["cluster"]) else None,
                            "quality_score": _float(row["quality_score"]),
                            "sortino": _float(row["sortino"]),
                            "downside_vol": _float(row["downside_vol"]),
                            "momentum_20": _float(row["momentum_20"]),
                            "momentum_60": _float(row["momentum_60"]),
                            "stress_corr_0050_down": _float(row["stress_corr_0050_down"]),
                        }
                        for ticker, row in clustered.iterrows()
                    },
                }
            )
    latest = snapshots[-1] if snapshots else {}
    latest_buckets = latest.get("buckets", {}) if isinstance(latest.get("buckets"), dict) else {}
    quality_assets = [ticker for ticker, row in latest_buckets.items() if row.get("bucket") == "quality"]
    ordinary_assets = [ticker for ticker, row in latest_buckets.items() if row.get("bucket") == "ordinary"]
    supports_00631l_add = "00631L.TW" in quality_assets
    supports_00632r_hedge = "00632R.TW" in quality_assets or (
        latest_buckets.get("00632R.TW", {}).get("stress_corr_0050_down") is not None
        and latest_buckets.get("00632R.TW", {}).get("stress_corr_0050_down") < 0.0
    )
    ambiguous_leverage_inverse_mix = bool(supports_00631l_add and supports_00632r_hedge)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_dynamic_bucket_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "imported_concept": "dynamic_kmeans_two_bucket_shadow",
            "not_imported": ["hierarchical_DRL_training", "DDPG_allocator", "live_target_weight_generation"],
        },
        "parameters": {
            "tickers": list(TICKERS),
            "start": start,
            "end": str(end_resolved),
            "window": window,
            "step": step,
            "features": ["sortino", "downside_vol", "momentum_20", "momentum_60", "stress_corr_0050_down"],
        },
        "latest_bucket_snapshot": latest,
        "bucket_history_tail": snapshots[-8:],
        "decision": {
            "quality_assets_latest": quality_assets,
            "ordinary_assets_latest": ordinary_assets,
            "supports_new_00631l_add": bool(supports_00631l_add),
            "supports_00632r_hedge": bool(supports_00632r_hedge),
            "ambiguous_leverage_inverse_mix": bool(ambiguous_leverage_inverse_mix),
            "target_weight_change_allowed": False,
            "production_effect": "none",
            "summary": (
                "Dynamic buckets are diagnostic only. They can flag whether 00631L add or 00632R hedge is "
                "structurally supported, but cannot override A21.18 regime constraints."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_dynamic_bucket_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--window", type=int, default=75)
    parser.add_argument("--step", type=int, default=75)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        window=args.window,
        step=args.step,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
