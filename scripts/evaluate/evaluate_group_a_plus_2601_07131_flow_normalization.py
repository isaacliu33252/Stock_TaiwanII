#!/usr/bin/env python3
"""Matched-filter normalization diagnostic for NCF institutional-flow features (arXiv 2601.07131).

Research-only. The paper's core empirical claim is that market-cap/turnover
normalization ("Matched Filter") of investor net-buy flow carries virtually
all the exploitable signal, and that adding complexity on top of raw,
unnormalized flow destroys it. Its own trading strategy (cross-sectional
long-short across 2,439 Korean stocks) does not transfer to GroupA+ (a
4-ticker universe), so this script does not replicate that strategy. Instead
it tests the transferable, code-verified hypothesis: NCF's production
`0050.TW` foreign/institutional net-buy features
(`scripts/misc/ncf_0050.py::load_external_df`, `inst_foreign_net` /
`inst_total_net` = net_buy / (close * 1e6)) may not adequately correct for
the large scale shift in raw net-buy magnitude confirmed in the DB (yearly
mean |foreign_net_buy| roughly 4x higher in 2025-2026 than 2020-2024).

Compares four normalization variants of the same raw `institutional_data`
columns as single-feature predictors of forward 0050.TW return direction,
via expanding-window information coefficient (Spearman IC) and AUC, split
pre/post 2024 to directly test whether normalization stabilizes predictive
quality across the scale-shift boundary. Never touches the production NCF
model, its training pipeline, or any live feature file.
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
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH

TICKER = "0050.TW"
FORWARD_HORIZONS = (5, 10, 20)
REGIME_SPLIT_DATE = "2024-01-01"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2601_07131_flow_normalization_diagnostic.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2601_07131_flow_normalization_diagnostic.md"


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def load_panel(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        price = con.execute(
            "SELECT dt, close, volume FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
        inst = con.execute(
            "SELECT dt, foreign_net_buy, institutional_total_net_buy FROM institutional_data "
            "WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    price["dt"] = pd.to_datetime(price["dt"])
    inst["dt"] = pd.to_datetime(inst["dt"])
    panel = price.set_index("dt").join(inst.set_index("dt"), how="left")
    panel[["foreign_net_buy", "institutional_total_net_buy"]] = panel[
        ["foreign_net_buy", "institutional_total_net_buy"]
    ].fillna(0.0)
    return panel.sort_index()


def build_variants(panel: pd.DataFrame) -> dict[str, pd.Series]:
    close = panel["close"].astype(float)
    volume = panel["volume"].astype(float).replace(0.0, np.nan)
    foreign = panel["foreign_net_buy"].astype(float)
    inst_total = panel["institutional_total_net_buy"].astype(float)

    variants: dict[str, pd.Series] = {}
    # (a) raw, unnormalized -- the paper's "naive" baseline.
    variants["raw_foreign_net_buy"] = foreign
    # (b) production NCF scaling (scripts/misc/ncf_0050.py: net_buy / (close * 1e6)).
    variants["price_scaled_foreign_net_buy"] = foreign / (close * 1e6)
    # (c) paper-inspired "Matched Filter": flow as a fraction of the day's own
    # trading volume, i.e. what share of trading activity was net foreign buying.
    variants["volume_normalized_foreign_net_buy"] = foreign / volume
    # (d) expanding z-score, no-lookahead (same convention used elsewhere in
    # this codebase for technical-indicator normalization).
    exp_mean = foreign.expanding(min_periods=252).mean()
    exp_std = foreign.expanding(min_periods=252).std()
    variants["expanding_zscore_foreign_net_buy"] = (foreign - exp_mean) / exp_std.replace(0.0, np.nan)

    # Same four variants for institutional_total_net_buy (chip_score's other leg).
    variants["raw_inst_total_net_buy"] = inst_total
    variants["price_scaled_inst_total_net_buy"] = inst_total / (close * 1e6)
    variants["volume_normalized_inst_total_net_buy"] = inst_total / volume
    exp_mean_i = inst_total.expanding(min_periods=252).mean()
    exp_std_i = inst_total.expanding(min_periods=252).std()
    variants["expanding_zscore_inst_total_net_buy"] = (inst_total - exp_mean_i) / exp_std_i.replace(0.0, np.nan)
    return variants


def _ic_and_auc(feature: pd.Series, forward_return: pd.Series) -> dict[str, Any]:
    joined = pd.concat([feature.rename("x"), forward_return.rename("y")], axis=1).dropna()
    if len(joined) < 30:
        return {"n": int(len(joined)), "ic": None, "ic_pvalue": None, "auc": None}
    ic, pvalue = spearmanr(joined["x"], joined["y"])
    ranks = joined["x"].rank(pct=True)
    up = (joined["y"] > 0).astype(int)
    n_up = int(up.sum())
    n_down = int((1 - up).sum())
    auc = None
    if n_up > 0 and n_down > 0:
        auc = float((ranks[up == 1].values[:, None] > ranks[up == 0].values[None, :]).mean())
    return {
        "n": int(len(joined)),
        "ic": _finite(ic),
        "ic_pvalue": _finite(pvalue),
        "auc": auc,
    }


def build_report(*, db_path: Path, start: str, end: str) -> dict[str, Any]:
    panel = load_panel(db_path, TICKER, start, end)
    variants = build_variants(panel)
    close = panel["close"].astype(float)

    results: dict[str, Any] = {}
    for name, series in variants.items():
        by_horizon: dict[str, Any] = {}
        for h in FORWARD_HORIZONS:
            forward_return = close.pct_change(h).shift(-h)
            full = _ic_and_auc(series, forward_return)
            pre = _ic_and_auc(series.loc[:REGIME_SPLIT_DATE], forward_return.loc[:REGIME_SPLIT_DATE])
            post = _ic_and_auc(series.loc[REGIME_SPLIT_DATE:], forward_return.loc[REGIME_SPLIT_DATE:])
            by_horizon[f"h{h}"] = {"full_sample": full, f"pre_{REGIME_SPLIT_DATE}": pre, f"post_{REGIME_SPLIT_DATE}": post}
        results[name] = by_horizon

    summary_rows = []
    for name, by_horizon in results.items():
        h5 = by_horizon["h5"]
        summary_rows.append(
            {
                "variant": name,
                "ic_full": h5["full_sample"]["ic"],
                "ic_pre_2024": h5[f"pre_{REGIME_SPLIT_DATE}"]["ic"],
                "ic_post_2024": h5[f"post_{REGIME_SPLIT_DATE}"]["ic"],
                "auc_full": h5["full_sample"]["auc"],
                "auc_pre_2024": h5[f"pre_{REGIME_SPLIT_DATE}"]["auc"],
                "auc_post_2024": h5[f"post_{REGIME_SPLIT_DATE}"]["auc"],
            }
        )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2601_07131_flow_normalization_diagnostic",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2601.07131.pdf",
            "title": "The Limits of Complexity: Why Feature Engineering Beats Deep Learning in Investor Flow Prediction",
            "adapted_concepts": [
                "Matched-filter (activity-normalized) flow vs raw/price-scaled flow as a single-feature predictor",
                "regime-split evaluation (pre/post scale-shift) instead of a single full-sample number",
            ],
            "not_replicated": "cross-sectional long-short across the S&P/KOSPI universe (GroupA+ has no comparable cross-section)",
        },
        "policy": "research_only_feature_diagnostic_no_model_retrain_no_weight_change",
        "status": "diagnostic_available",
        "as_of": str(panel.index.max().date()),
        "parameters": {"start": start, "end": end, "ticker": TICKER, "forward_horizons": list(FORWARD_HORIZONS), "regime_split_date": REGIME_SPLIT_DATE},
        "detail": results,
        "summary_h5": summary_rows,
        "decision": {
            "review_complete": True,
            "creates_orders": False,
            "changes_ncf_production_model": False,
            "changes_target_weights": False,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2601.07131 Institutional-Flow Normalization Diagnostic (h=5)",
        "",
        f"- Status: `{report['status']}`",
        f"- As of: `{report['as_of']}`",
        "",
        "| variant | IC (full) | IC (pre-2024) | IC (post-2024) | AUC (full) | AUC (pre-2024) | AUC (post-2024) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["summary_h5"]:
        lines.append(
            "| {v} | {icf} | {icp} | {icq} | {af} | {ap} | {aq} |".format(
                v=row["variant"],
                icf=_fmt(row["ic_full"]),
                icp=_fmt(row["ic_pre_2024"]),
                icq=_fmt(row["ic_post_2024"]),
                af=_fmt(row["auc_full"]),
                ap=_fmt(row["auc_pre_2024"]),
                aq=_fmt(row["auc_post_2024"]),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Single-feature diagnostic only (Spearman IC / rank AUC vs forward 0050.TW return).",
            "- Does not retrain or modify the production NCF model.",
            "- Does not change target weights, orders, or the switch policy.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(db_path=Path(args.db), start=args.start, end=args.end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_output))
    print(f"2601.07131 flow normalization diagnostic: {output}")
    for row in report["summary_h5"]:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
