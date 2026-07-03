#!/usr/bin/env python3
"""XGBoost Feature Importance Audit for NCF 00631L / 00632R.

Inspired by stockpredictionai's XGBoost importance approach, adapted for
quarterly auditing of the NCF feature set to prune low-signal features.

What this does
--------------
1. Loads OHLCV + builds all features (FEATURES, EXT_FEATURES, INTERACTION_FEATURES,
   and optional FOURIER_FEATURES / GLOBAL_FEATURES / TBRAIN_FEATURES).
2. Trains an XGBoost classifier for each horizon (H=1, H=5, H=20).
3. Computes three importance signals per feature:
     gain  — average XGBoost gain per split (primary)
     IC    — |Spearman ρ| between feature and forward return (prediction value)
     cover — average data coverage of splits using this feature
4. Grades each feature A/B/C/D by composite score = 0.5 × gain_rank + 0.5 × IC_rank.
5. Outputs a JSON summary and a ranked console table.

Grades
------
  A = top 25%      → keep, high priority
  B = 25–50%       → keep
  C = 50–75%       → monitor, may prune in next cycle
  D = bottom 25%   → prune candidate (especially if IC < 0.02)

Typical usage
-------------
    # Quarterly audit for 00631L with all feature groups enabled
    PYTHONPATH=. .venv/bin/python scripts/misc/xgb_feature_audit.py \\
        --ticker 00631L \\
        --train-start 2020-01-01 \\
        --output results/xgb_audit_00631l.json

    # Audit with Fourier + Global features
    PYTHONPATH=. .venv/bin/python scripts/misc/xgb_feature_audit.py \\
        --ticker 00631L --fourier-features --global-features \\
        --output results/xgb_audit_00631l_full.json

    # Audit 00632R (all ext features on by default)
    PYTHONPATH=. .venv/bin/python scripts/misc/xgb_feature_audit.py \\
        --ticker 00632R \\
        --output results/xgb_audit_00632r.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed.  Run:  .venv/bin/pip install xgboost")
    sys.exit(1)

TICKER_SCRIPT_MAP = {
    "00631L": ROOT / "scripts" / "misc" / "ncf_00631l.py",
    "00632R": ROOT / "ncf_00632r.py",
}

HORIZONS = [1, 5, 20]
GRADE_THRESHOLDS = [0.75, 0.50, 0.25]   # percentile cut-offs for A / B / C / D

_XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": -1,
}


def _load_ncf_module(ticker: str):
    """Dynamically import the NCF script for the given ticker."""
    import importlib.util
    script_path = TICKER_SCRIPT_MAP[ticker]
    spec = importlib.util.spec_from_file_location(f"ncf_{ticker.lower()}", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_feature_matrix(
    mod,
    ticker: str,
    train_start: str,
    train_end: str,
    db_path: Path,
    horizon: int,
    use_external: bool,
    use_fourier: bool,
    use_global: bool,
    use_tbrain: bool,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Load data, build full feature matrix for one horizon."""
    raw = mod.load_data(db_path, f"{ticker}.TW", train_start, train_end)

    ext_df = None
    if use_external:
        ext_df = mod.load_external_df(raw, db_path)
        # Append optional feature groups
        if use_global and ext_df is not None and hasattr(mod, "add_global_features"):
            _idx = raw.index
            _s = (_idx[0] - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
            _e = (_idx[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
            mod.add_global_features(ext_df, _idx, mod._fetch_yf, _s, _e)

    # Dynamically adjust feature lists (same logic as main())
    if use_fourier and hasattr(mod, "FOURIER_FEATURES"):
        if hasattr(mod, "FEATURES"):
            mod.FEATURES[:] = mod.FEATURES + [
                f for f in mod.FOURIER_FEATURES if f not in mod.FEATURES
            ]
    if use_tbrain and hasattr(mod, "TBRAIN_FEATURES"):
        if hasattr(mod, "FEATURES"):
            mod.FEATURES[:] = mod.FEATURES + [
                f for f in mod.TBRAIN_FEATURES if f not in mod.FEATURES
            ]
    if use_global and hasattr(mod, "GLOBAL_FEATURES") and ext_df is not None:
        global_all = mod.GLOBAL_FEATURES + mod.GLOBAL_INTERACTION_FEATURES
        if hasattr(mod, "EXT_FEATURES"):
            mod.EXT_FEATURES[:] = mod.EXT_FEATURES + [
                f for f in global_all if f not in mod.EXT_FEATURES
            ]

    X, y_return, y_direction, feature_list = mod.build_dataset(
        raw,
        horizon=horizon,
        ext_df=ext_df,
        direction_threshold=0.005,
        labeling="simple",
    )

    # Keep only binary (UP=1 / DOWN=0) samples for XGBoost classifier
    mask = y_direction != -1
    X_bin = X[mask]
    y_bin = y_direction[mask]
    y_ret_bin = y_return[mask]

    return X_bin, y_ret_bin, y_bin, feature_list


def _xgb_importances(
    X: pd.DataFrame,
    y: pd.Series,
    feature_list: list[str],
) -> dict[str, dict[str, float]]:
    """Train XGBoost and return gain/weight/cover per feature."""
    X_clean = X[feature_list].fillna(0.0)
    clf = xgb.XGBClassifier(**_XGB_PARAMS)
    clf.fit(X_clean, y.astype(int))

    booster = clf.get_booster()
    gain   = booster.get_score(importance_type="gain")
    weight = booster.get_score(importance_type="weight")
    cover  = booster.get_score(importance_type="cover")

    result: dict[str, dict[str, float]] = {}
    for feat in feature_list:
        result[feat] = {
            "gain":   gain.get(feat, 0.0),
            "weight": weight.get(feat, 0.0),
            "cover":  cover.get(feat, 0.0),
        }
    return result


def _information_coefficient(
    X: pd.DataFrame,
    y_return: pd.Series,
    feature_list: list[str],
) -> dict[str, float]:
    """Compute |Spearman IC| between each feature and forward return."""
    ic: dict[str, float] = {}
    ret = y_return.values
    for feat in feature_list:
        col = X[feat].fillna(0.0).values
        if col.std() < 1e-10:
            ic[feat] = 0.0
            continue
        rho, _ = spearmanr(col, ret)
        ic[feat] = abs(float(rho)) if np.isfinite(rho) else 0.0
    return ic


def _grade(rank_0_to_1: float) -> str:
    """Convert percentile rank (0=worst, 1=best) to A/B/C/D grade."""
    if rank_0_to_1 >= GRADE_THRESHOLDS[0]:
        return "A"
    if rank_0_to_1 >= GRADE_THRESHOLDS[1]:
        return "B"
    if rank_0_to_1 >= GRADE_THRESHOLDS[2]:
        return "C"
    return "D"


def _rank_normalise(values: dict[str, float]) -> dict[str, float]:
    """Return 0–1 rank-normalised scores (higher is better).

    Uses average-rank for ties so equal-importance features get the same score.
    """
    feats = list(values.keys())
    vals = np.array([values[f] for f in feats], dtype=float)
    n = len(vals)
    if n == 0:
        return {}
    # rankdata 'average' assigns tied elements the mean of their ranks (1-based)
    raw_ranks = rankdata(vals, method="average")   # 1 … n
    normalised = (raw_ranks - 1.0) / max(n - 1, 1)
    return {feats[i]: float(normalised[i]) for i in range(n)}


def _audit_horizon(
    mod,
    ticker: str,
    horizon: int,
    train_start: str,
    train_end: str,
    db_path: Path,
    use_external: bool,
    use_fourier: bool,
    use_global: bool,
    use_tbrain: bool,
) -> dict:
    """Full audit for one horizon — returns per-feature gain/IC/grade."""
    print(f"\n  [H={horizon}] Building feature matrix...", flush=True)
    X, y_ret, y_dir, feature_list = _build_feature_matrix(
        mod, ticker, train_start, train_end, db_path, horizon,
        use_external, use_fourier, use_global, use_tbrain,
    )
    print(f"  [H={horizon}] Samples: {len(X)}  Features: {len(feature_list)}", flush=True)

    print(f"  [H={horizon}] Training XGBoost...", flush=True)
    imps = _xgb_importances(X, y_dir, feature_list)

    print(f"  [H={horizon}] Computing IC (Spearman)...", flush=True)
    ics = _information_coefficient(X, y_ret, feature_list)

    # Rank-normalise both signals then average for composite score
    gain_rank = _rank_normalise({f: imps[f]["gain"] for f in feature_list})
    ic_rank   = _rank_normalise(ics)

    features_out = {}
    for feat in feature_list:
        composite = 0.5 * gain_rank.get(feat, 0.0) + 0.5 * ic_rank.get(feat, 0.0)
        features_out[feat] = {
            "gain":        round(imps[feat]["gain"],   6),
            "weight":      round(imps[feat]["weight"], 2),
            "cover":       round(imps[feat]["cover"],  4),
            "ic":          round(ics[feat],            6),
            "gain_rank":   round(gain_rank.get(feat, 0.0), 4),
            "ic_rank":     round(ic_rank.get(feat, 0.0),   4),
            "composite":   round(composite, 4),
            "grade":       _grade(composite),
        }

    return {
        "horizon": horizon,
        "n_samples": len(X),
        "n_features": len(feature_list),
        "feature_list": feature_list,
        "features": features_out,
    }


def _aggregate_grades(horizon_results: list[dict]) -> dict[str, dict]:
    """Average composite scores across horizons and re-grade."""
    all_feats: set[str] = set()
    for hr in horizon_results:
        all_feats.update(hr["features"].keys())

    agg: dict[str, dict] = {}
    for feat in all_feats:
        composites = [
            hr["features"][feat]["composite"]
            for hr in horizon_results
            if feat in hr["features"]
        ]
        mean_composite = float(np.mean(composites)) if composites else 0.0
        mean_ic = float(np.mean([
            hr["features"][feat]["ic"]
            for hr in horizon_results
            if feat in hr["features"]
        ]))
        mean_gain = float(np.mean([
            hr["features"][feat]["gain"]
            for hr in horizon_results
            if feat in hr["features"]
        ]))
        per_h = {
            f"h{hr['horizon']}_grade": hr["features"].get(feat, {}).get("grade", "?")
            for hr in horizon_results
        }
        agg[feat] = {
            "mean_composite": round(mean_composite, 4),
            "mean_ic": round(mean_ic, 6),
            "mean_gain": round(mean_gain, 6),
            **per_h,
        }

    # Re-grade on mean_composite
    composites = {f: agg[f]["mean_composite"] for f in agg}
    ranks = _rank_normalise(composites)
    for feat in agg:
        agg[feat]["overall_grade"] = _grade(ranks[feat])
        agg[feat]["rank"] = round(ranks[feat], 4)

    return agg


def _print_table(agg: dict[str, dict], top_n: int = 30, show_prune: bool = True) -> None:
    ranked = sorted(agg.items(), key=lambda kv: kv[1]["rank"], reverse=True)

    print(f"\n{'='*100}")
    print(f"  XGBoost Feature Audit — Top {min(top_n, len(ranked))} features")
    print(f"{'='*100}")
    hdr = f"  {'Feature':<32} {'Grade':>5} {'Rank%':>6} {'MeanIC':>8} {'MeanGain':>10} {'H1':>4} {'H5':>4} {'H20':>5}"
    print(hdr)
    print(f"  {'-'*98}")

    for feat, info in ranked[:top_n]:
        print(
            f"  {feat:<32} {info['overall_grade']:>5} {info['rank']:>6.1%} "
            f"{info['mean_ic']:>8.4f} {info['mean_gain']:>10.2f} "
            f"{info.get('h1_grade', '?'):>4} {info.get('h5_grade', '?'):>4} {info.get('h20_grade', '?'):>5}"
        )

    if show_prune:
        prune = [
            (f, i) for f, i in ranked
            if i["overall_grade"] == "D" and i["mean_ic"] < 0.02
        ]
        if prune:
            print(f"\n  ── Prune candidates (Grade D + IC < 0.02) ─────────────")
            for feat, info in prune:
                print(f"    {feat:<32}  IC={info['mean_ic']:.4f}  gain={info['mean_gain']:.2f}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ticker", choices=["00631L", "00632R"], default="00631L")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end", default="latest",
                        help="Training end date ('latest' = newest DB date)")
    parser.add_argument("--horizons", type=int, nargs="+", default=HORIZONS,
                        help="Horizons to audit (default: 1 5 20)")
    parser.add_argument("--db",
                        default=str(ROOT / "FinRL" / "data" / "stock_data.db"))
    parser.add_argument("--no-external-features", action="store_true")
    parser.add_argument("--fourier-features", action="store_true",
                        help="Include Fourier features in audit")
    parser.add_argument("--global-features", action="store_true",
                        help="Include global correlated asset features in audit")
    parser.add_argument("--tbrain-features", action="store_true",
                        help="Include TBrain features in audit")
    parser.add_argument("--top-n", type=int, default=30,
                        help="Print top-N features in console table (default: 30)")
    parser.add_argument("--output", default=None,
                        help="Save audit JSON to this path (optional)")
    args = parser.parse_args()

    print(f"[XGB Audit] Ticker: {args.ticker}")
    print(f"[XGB Audit] Train: {args.train_start} → {args.train_end}")
    print(f"[XGB Audit] Horizons: {args.horizons}")
    print(f"[XGB Audit] Features: external={not args.no_external_features}, "
          f"fourier={args.fourier_features}, global={args.global_features}, "
          f"tbrain={args.tbrain_features}")

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        sys.exit(1)

    print(f"\nLoading NCF module for {args.ticker}...")
    mod = _load_ncf_module(args.ticker)

    # Resolve 'latest' end date
    train_end = args.train_end
    if train_end.lower() == "latest":
        train_end = mod.resolve_end_date(db_path, f"{args.ticker}.TW", "latest")
    print(f"  Resolved train end: {train_end}")

    horizon_results = []
    for h in args.horizons:
        # Re-load module for each horizon to reset mutable module-level lists
        mod_h = _load_ncf_module(args.ticker)
        try:
            hr = _audit_horizon(
                mod_h, args.ticker, h,
                args.train_start, train_end, db_path,
                use_external=not args.no_external_features,
                use_fourier=args.fourier_features,
                use_global=args.global_features,
                use_tbrain=args.tbrain_features,
            )
            horizon_results.append(hr)
        except Exception as e:
            print(f"  ✗ H={h} failed: {e}")
            import traceback
            traceback.print_exc()

    if not horizon_results:
        print("ERROR: all horizons failed — nothing to report")
        sys.exit(1)

    print(f"\nAggregating grades across {len(horizon_results)} horizons...")
    agg = _aggregate_grades(horizon_results)
    _print_table(agg, top_n=args.top_n)

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for info in agg.values():
        grade_counts[info["overall_grade"]] += 1
    prune_list = [
        f for f, i in agg.items()
        if i["overall_grade"] == "D" and i["mean_ic"] < 0.02
    ]
    print(f"Grade distribution: {grade_counts}")
    print(f"Prune candidates ({len(prune_list)}): {prune_list}")

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now().isoformat(),
            "ticker": args.ticker,
            "train_start": args.train_start,
            "train_end": train_end,
            "horizons": args.horizons,
            "features_used": {
                "external": not args.no_external_features,
                "fourier": args.fourier_features,
                "global": args.global_features,
                "tbrain": args.tbrain_features,
            },
            "grade_distribution": grade_counts,
            "prune_candidates": prune_list,
            "aggregate": {
                feat: info
                for feat, info in sorted(
                    agg.items(),
                    key=lambda kv: kv[1]["rank"],
                    reverse=True,
                )
            },
            "per_horizon": [
                {
                    "horizon": hr["horizon"],
                    "n_samples": hr["n_samples"],
                    "n_features": hr["n_features"],
                    "features": {
                        feat: {k: v for k, v in data.items() if k != "grade" or True}
                        for feat, data in sorted(
                            hr["features"].items(),
                            key=lambda kv: kv[1]["composite"],
                            reverse=True,
                        )
                    },
                }
                for hr in horizon_results
            ],
        }
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nAudit saved to {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
