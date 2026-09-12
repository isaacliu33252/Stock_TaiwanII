#!/usr/bin/env python3
"""arXiv:2104.03667 (Bucci & Ciciretti -- "Market Regime Detection via
Realized Covariances: A Comparison between Unsupervised Learning and
Nonlinear Models") applicability test for Group A+.

The paper detects two market regimes (calm / highly volatile) from monthly
realized correlation matrices of 9 futures, using two competing methods:

1. VLSTAR: a vector logistic smooth-transition autoregression whose
   diagonal transition matrix G_t is a logistic function of a single
   exogenous transition variable (selected by a linearity test), bounded in
   [0, 1]; regime = "volatile" when G_t > 0.5.
2. Agglomerative hierarchical clustering (AGNES, Ward linkage, Manhattan
   distance) on features extracted from the realized correlation matrices,
   K=2 clusters.

The paper validates both models two ways: (a) on synthetic data with known
regimes, and (b) by comparing a naive momentum strategy against a
regime-filtered version of the same strategy that goes flat whenever a
transition to the volatile regime is detected. VLSTAR is reported as the
best-performing model.

ADAPTATION FOR GROUP A+: the paper uses 9 CME futures at hourly frequency
(2010-2020) sourced from Bloomberg, which Group A+ does not have. This
review substitutes Group A+'s actual core ETF universe (0050/00631L/
00632R/00679B.TWO) at daily frequency, and evaluates the paper's own
momentum-filter validation on 0050 (Group A+'s core growth asset), plus a
Group A+-specific check: does either regime detector track (or improve on)
the existing switch_risk_ma80_dd11_total6_hold5_eg015_xg015 golden1/
defensive trigger.

SIMPLIFICATIONS, stated explicitly (same standard as prior papers in this
project -- see 2411.19649 DCC proxy, 2606.23492 CHMM):

- VLSTAR-lite: rather than estimating a full nonlinear VAR via NLS with a
  linearity-test-selected transition variable, this uses trailing 21d
  realized volatility of 0050 as the (single) transition variable, with an
  expanding-window causal median as the location parameter c_t and a fixed
  slope gamma. This captures VLSTAR's defining idea (a smooth logistic
  transition on an exogenous driver, vs. a hard clustering rule) without a
  full multivariate NLS estimation.
- Cluster-regime: fit AGNES/Ward on an expanding window of monthly
  realized-correlation feature vectors, refit quarterly (matching this
  project's established CHMM refit cadence), with nearest-centroid
  assignment for months since the last refit. No future month ever informs
  the regime label of an earlier month.

CAUSALITY: all regime series only use data available up to and including
the labeled date; every detector's classification is additionally lagged
by one trading day before being applied to any strategy return (decide on
close(t), act on t+1), matching this project's established look-ahead-bug
guard (feedback_lookahead_bug_same_day_signal_decision).

Research-only. Does not touch any production runner, signal, or execution
plan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
SWITCH_CURVE = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_curve.csv"
REGIME_CSV = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_recommended_regime.csv"
SWITCH_COL = "switch_risk_ma80_dd11_total6_hold5_eg015_xg015"
GOLDEN_COL = "golden1_0531_1m"
DEFENSIVE_COL = "group_a_plus_defensive_1m"

CORE_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_regime_clustering_review.json"

MIN_HOLD_DAYS = 5
REFIT_EVERY_MONTHS = 3
MIN_MONTHS_FOR_FIRST_FIT = 12
VLSTAR_LITE_WINDOW = 21
VLSTAR_LITE_MIN_WINDOW = 252


def _load_close(db_path: Path, tickers: tuple[str, ...]) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        placeholders = ", ".join(["?"] * len(tickers))
        rows = con.execute(
            f"SELECT dt, ticker, close FROM ohlcv WHERE ticker IN ({placeholders}) ORDER BY dt, ticker",
            list(tickers),
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    wide = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return wide.dropna(how="any")


def _monthly_corr_features(returns: pd.DataFrame) -> pd.DataFrame:
    """One feature row per calendar month: upper-triangle of that month's
    realized (intra-month, daily-return-based) correlation matrix."""
    pairs = [(a, b) for i, a in enumerate(returns.columns) for b in returns.columns[i + 1:]]
    rows = []
    for period, chunk in returns.groupby(returns.index.to_period("M")):
        if len(chunk) < 5:
            continue
        corr = chunk.corr()
        # A near-zero-variance asset in a given month makes its correlation
        # undefined (NaN); treat that as "no measurable co-movement signal"
        # rather than letting it propagate into the clustering distance.
        feat = {f"{a}__{b}": float(corr.loc[a, b]) if np.isfinite(corr.loc[a, b]) else 0.0 for a, b in pairs}
        feat["month_end"] = period.to_timestamp(how="end").normalize()
        feat["realized_var_sum"] = float((chunk.std() ** 2).sum())
        rows.append(feat)
    out = pd.DataFrame(rows).set_index("month_end").sort_index()
    return out


def _causal_cluster_regime(monthly: pd.DataFrame) -> pd.Series:
    """Expanding-window AGNES/Ward (K=2), refit every REFIT_EVERY_MONTHS,
    nearest-centroid assignment between refits. Returns a monthly boolean
    Series, True = 'volatile' cluster."""
    feat_cols = [c for c in monthly.columns if c != "realized_var_sum"]
    is_volatile = pd.Series(index=monthly.index, dtype=bool)
    centroids = None
    volatile_label = None
    next_refit = MIN_MONTHS_FOR_FIRST_FIT

    for i, month_end in enumerate(monthly.index):
        if i + 1 >= MIN_MONTHS_FOR_FIRST_FIT and (centroids is None or i >= next_refit):
            train = monthly.iloc[: i + 1]
            X = train[feat_cols].values
            model = AgglomerativeClustering(n_clusters=2, linkage="ward")
            labels = model.fit_predict(X)
            centroids = np.stack([X[labels == k].mean(axis=0) for k in (0, 1)])
            var_by_cluster = [train["realized_var_sum"].values[labels == k].mean() for k in (0, 1)]
            volatile_label = int(np.argmax(var_by_cluster))
            next_refit = i + REFIT_EVERY_MONTHS

        if centroids is None:
            is_volatile.iloc[i] = False
            continue
        x = monthly.iloc[i][feat_cols].values.astype(float)
        dist = np.abs(centroids - x).sum(axis=1)  # Manhattan, matching the paper
        assigned = int(np.argmin(dist))
        is_volatile.iloc[i] = assigned == volatile_label

    return is_volatile


def _vlstar_lite_g(close_0050: pd.Series, gamma_scale: float = 3.0) -> pd.Series:
    """Daily logistic smooth-transition value G_t on trailing realized vol of
    0050, expanding-window causal median as the location parameter. gamma_scale
    controls slope steepness: gamma = gamma_scale / running_std(realized_vol)."""
    ret = np.log(close_0050 / close_0050.shift(1)).dropna()
    realized_vol = ret.rolling(VLSTAR_LITE_WINDOW).std() * np.sqrt(252)
    realized_vol = realized_vol.dropna()

    g = pd.Series(index=realized_vol.index, dtype=float)
    for i, dt in enumerate(realized_vol.index):
        if i < VLSTAR_LITE_MIN_WINDOW:
            g.loc[dt] = 0.0
            continue
        history = realized_vol.iloc[: i + 1]
        c_t = history.median()
        scale = history.std()
        gamma = gamma_scale / scale if scale > 1e-8 else 0.0
        s_t = realized_vol.iloc[i]
        g.loc[dt] = 1.0 / (1.0 + np.exp(-gamma * (s_t - c_t)))
    return g


def _vlstar_lite_regime(close_0050: pd.Series, gamma_scale: float = 3.0, threshold: float = 0.5) -> pd.Series:
    """Boolean regime call: True = 'volatile' when G_t > threshold."""
    return _vlstar_lite_g(close_0050, gamma_scale=gamma_scale) > threshold


def _apply_min_hold(raw: pd.Series, min_hold: int) -> pd.Series:
    state = False
    hold_left = 0
    out = []
    for flag in raw:
        if hold_left > 0:
            hold_left -= 1
        else:
            if flag != state:
                state = flag
                hold_left = min_hold - 1
        out.append(state)
    return pd.Series(out, index=raw.index)


def _perf_stats(r: np.ndarray) -> dict:
    if len(r) == 0 or np.all(r == 0):
        return {"ann_ret": 0.0, "ann_vol": 0.0, "sharpe": 0.0, "mdd": 0.0, "downside_vol": 0.0}
    ann_ret = float(r.mean() * 252)
    ann_vol = float(r.std() * np.sqrt(252))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum = np.exp(np.cumsum(np.log1p(r)))
    mdd = float((cum / np.maximum.accumulate(cum) - 1).min())
    downside = r[r < 0]
    downside_vol = float(downside.std() * np.sqrt(252)) if len(downside) > 1 else 0.0
    return {"ann_ret": ann_ret, "ann_vol": ann_vol, "sharpe": sharpe, "mdd": mdd, "downside_vol": downside_vol}


def build_review(
    db_path: Path = DB_PATH,
    switch_curve_path: Path = SWITCH_CURVE,
    regime_csv_path: Path = REGIME_CSV,
    core_tickers: tuple[str, ...] = CORE_TICKERS,
    min_months_for_first_fit: int = MIN_MONTHS_FOR_FIRST_FIT,
    vlstar_lite_min_window: int = VLSTAR_LITE_MIN_WINDOW,
) -> dict:
    global MIN_MONTHS_FOR_FIRST_FIT, VLSTAR_LITE_MIN_WINDOW
    MIN_MONTHS_FOR_FIRST_FIT = min_months_for_first_fit
    VLSTAR_LITE_MIN_WINDOW = vlstar_lite_min_window

    close = _load_close(db_path, core_tickers)
    if close.empty or len(close) < vlstar_lite_min_window + 30:
        return {
            "paper": "arXiv:2104.03667",
            "status": "blocked",
            "blocking_reasons": ["insufficient_price_history"],
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "train_vlstar_now": False,
        }
    returns = np.log(close / close.shift(1)).dropna(how="any")

    monthly = _monthly_corr_features(returns)

    cluster_monthly = _causal_cluster_regime(monthly)
    cluster_daily = cluster_monthly.reindex(returns.index, method="ffill").fillna(False).astype(bool)
    cluster_daily = _apply_min_hold(cluster_daily, MIN_HOLD_DAYS)
    cluster_daily_lagged = cluster_daily.shift(1).fillna(False).astype(bool)

    vlstar_raw = _vlstar_lite_regime(close["0050.TW"])
    vlstar_daily = _apply_min_hold(vlstar_raw.reindex(returns.index).fillna(False).astype(bool), MIN_HOLD_DAYS)
    vlstar_daily_lagged = vlstar_daily.shift(1).fillna(False).astype(bool)

    # --- A. Paper's own validation: naive momentum(0050) vs regime-filtered ---
    ret_0050 = returns["0050.TW"]
    mom_signal = (close["0050.TW"].pct_change(20) > 0).reindex(ret_0050.index).fillna(False).astype(bool).shift(1).fillna(False).astype(bool)
    naive_ret = np.where(mom_signal, ret_0050, 0.0)

    idx = ret_0050.index
    cluster_al = cluster_daily_lagged.reindex(idx).fillna(False).astype(bool)
    vlstar_al = vlstar_daily_lagged.reindex(idx).fillna(False).astype(bool)
    cluster_filtered_ret = np.where(mom_signal & ~cluster_al, ret_0050, 0.0)
    vlstar_filtered_ret = np.where(mom_signal & ~vlstar_al, ret_0050, 0.0)

    momentum_validation = {
        name: _perf_stats(np.asarray(r))
        for name, r in [
            ("naive_momentum_unfiltered", naive_ret),
            ("naive_momentum_cluster_filtered", cluster_filtered_ret),
            ("naive_momentum_vlstar_lite_filtered", vlstar_filtered_ret),
        ]
    }

    # --- B. Group A+-specific: agreement with + blend into existing switch curve ---
    group_a_plus_check: dict = {}
    if switch_curve_path.exists():
        curve = pd.read_csv(switch_curve_path)
        curve["dt"] = pd.to_datetime(curve["dt"])
        curve = curve.set_index("dt").sort_index()
        golden_ret = curve[GOLDEN_COL].pct_change()
        defensive_ret = curve[DEFENSIVE_COL].pct_change()
        switch_ret = curve[SWITCH_COL].pct_change()

        df = pd.concat(
            [
                golden_ret.rename("golden"),
                defensive_ret.rename("defensive"),
                switch_ret.rename("switch_ma_dd"),
                cluster_daily_lagged.rename("cluster_defensive"),
                vlstar_daily_lagged.rename("vlstar_defensive"),
            ],
            axis=1,
        ).dropna()
        df["cluster_switch_ret"] = np.where(df["cluster_defensive"], df["defensive"], df["golden"])
        df["vlstar_switch_ret"] = np.where(df["vlstar_defensive"], df["defensive"], df["golden"])

        full_window = {
            name: _perf_stats(df[col].values)
            for name, col in [
                ("golden1_alone", "golden"),
                ("switch_ma80_dd11_rule", "switch_ma_dd"),
                ("cluster_regime_switch", "cluster_switch_ret"),
                ("vlstar_lite_regime_switch", "vlstar_switch_ret"),
            ]
        }

        agreement = {}
        if regime_csv_path.exists():
            reg = pd.read_csv(regime_csv_path, usecols=["dt", "regime"])
            reg["dt"] = pd.to_datetime(reg["dt"])
            reg = reg.set_index("dt")["regime"]
            rule_defensive = (reg == "group_a_plus_defensive").reindex(df.index).fillna(False).astype(bool)
            for name, col in [("cluster_regime", "cluster_defensive"), ("vlstar_lite_regime", "vlstar_defensive")]:
                agree = float((df[col] == rule_defensive).mean())
                both = int((df[col] & rule_defensive).sum())
                det_only = int((df[col] & ~rule_defensive).sum())
                rule_only = int((~df[col] & rule_defensive).sum())
                agreement[name] = {
                    "day_by_day_agreement": round(agree, 4),
                    "both_defensive_days": both,
                    "detector_only_defensive_days": det_only,
                    "rule_only_defensive_days": rule_only,
                }

        episodes = {
            "covid_crash_2020": ("2020-01-20", "2020-03-23"),
            "bear_2022_full_year": ("2022-01-01", "2022-12-31"),
            "tariff_shock_2025_04": ("2025-04-01", "2025-04-15"),
        }
        episode_results = {}
        for name, (s, e) in episodes.items():
            sub = df.loc[s:e]
            if sub.empty:
                continue
            cg = float((1 + sub["golden"]).prod() - 1)
            cs = float((1 + sub["switch_ma_dd"]).prod() - 1)
            cc = float((1 + sub["cluster_switch_ret"]).prod() - 1)
            cv = float((1 + sub["vlstar_switch_ret"]).prod() - 1)
            episode_results[name] = {
                "golden1": round(cg, 4), "rule_switch": round(cs, 4),
                "cluster_switch": round(cc, 4), "vlstar_lite_switch": round(cv, 4),
                "cluster_defensive_days": int(sub["cluster_defensive"].sum()),
                "vlstar_defensive_days": int(sub["vlstar_defensive"].sum()),
                "n_days": int(len(sub)),
            }

        group_a_plus_check = {
            "full_window": full_window,
            "agreement_with_existing_switch_rule": agreement,
            "episodes": episode_results,
        }

    result = {
        "paper": "arXiv:2104.03667",
        "status": "available_for_shadow_monitoring",
        "method": "AGNES/Ward hierarchical clustering (causal, expanding-window, quarterly refit) "
                  "+ VLSTAR-lite (logistic smooth-transition proxy on 0050 realized volatility)",
        "core_tickers": list(core_tickers),
        "monthly_feature_rows": int(len(monthly)),
        "monthly_coverage": {
            "start": str(monthly.index.min().date()) if len(monthly) else None,
            "end": str(monthly.index.max().date()) if len(monthly) else None,
        },
        "cluster_regime_volatile_share": round(float(cluster_daily_lagged.mean()), 4),
        "vlstar_lite_regime_volatile_share": round(float(vlstar_daily_lagged.mean()), 4),
        "paper_momentum_validation": momentum_validation,
        "group_a_plus_switch_check": group_a_plus_check,
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }
    return result


def write_review(review: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    review = build_review()
    print(f"Monthly realized-correlation feature rows: {review.get('monthly_feature_rows')} "
          f"({review.get('monthly_coverage', {}).get('start')} .. {review.get('monthly_coverage', {}).get('end')})")
    print(f"\ncluster-regime volatile share (lagged): {review.get('cluster_regime_volatile_share', 0)*100:.1f}%")
    print(f"vlstar-lite volatile share (lagged):    {review.get('vlstar_lite_regime_volatile_share', 0)*100:.1f}%")
    print("\n=== A. Paper's own validation: naive momentum(0050) vs regime-filtered ===")
    for name, p in review.get("paper_momentum_validation", {}).items():
        print(f"{name:36s} ann_ret={p['ann_ret']*100:7.2f}%  ann_vol={p['ann_vol']*100:6.2f}%  "
              f"sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%  downside_vol={p['downside_vol']*100:6.2f}%")
    gap = review.get("group_a_plus_switch_check", {})
    if gap.get("full_window"):
        print("\n=== B. Group A+ full-window: golden1 vs rule-switch vs 2104.03667 detectors ===")
        for name, p in gap["full_window"].items():
            print(f"{name:26s} ann_ret={p['ann_ret']*100:7.2f}%  ann_vol={p['ann_vol']*100:6.2f}%  "
                  f"sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%")
    if gap.get("agreement_with_existing_switch_rule"):
        print("\n=== Agreement with existing switch_ma80_dd11 regime label ===")
        for name, a in gap["agreement_with_existing_switch_rule"].items():
            print(f"{name:20s} agreement={a['day_by_day_agreement']*100:.1f}%  "
                  f"both={a['both_defensive_days']}  detector_only={a['detector_only_defensive_days']}  "
                  f"rule_only={a['rule_only_defensive_days']}")
    if gap.get("episodes"):
        print("\n=== Episode-level cumulative return ===")
        for name, e in gap["episodes"].items():
            print(f"{name:24s} golden1={e['golden1']*100:+7.2f}%  rule_switch={e['rule_switch']*100:+7.2f}%  "
                  f"cluster_switch={e['cluster_switch']*100:+7.2f}%  vlstar_switch={e['vlstar_lite_switch']*100:+7.2f}%")

    write_review(review, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
