#!/usr/bin/env python3
"""Factor-attribution diagnostic for the golden1_0531 production signal.

Research/advisory-readiness artifact only. Never touches production weights,
pointers, or the daily pipeline. Read-only against results/*.csv and the
DuckDB ohlcv table.

Motivated by arXiv:2607.18001 ("AlphaZeroBeta: Deep Reinforcement Learning
for Market-Neutral Portfolios"), which regresses its RL portfolio's daily
returns on Fama-French + momentum + reversal + quality factors to show that
its reported Sharpe is not just disguised market beta. GroupA+ does not
trade a 500-name cross-section, so SMB/HML/RMW/QUAL (which require a broad
long-short stock universe) cannot be constructed; instead this script asks
the narrower, still-decision-relevant question for a single-index/LETF
switching strategy: how much of golden1_0531's realized return is explained
by (a) plain 0050 market beta, (b) 00631L's excess-of-2x leveraged-tracking
component (decay/rebalancing drag beyond simple 2x beta), (c) time-series
momentum, and (d) one-day reversal -- versus unexplained residual alpha.

Sample caveat: the strategy curve only covers ~1.5 years (2025-01-02
onward), i.e. one broadly bullish regime. This is a descriptive attribution,
not an out-of-sample predictive test; treat the alpha estimate as
directional, not conclusive.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402

DEFAULT_CURVE = PROJECT_ROOT / "results/group_a_plus_switch_policy_compare_golden1_20250102_20260703.json_curve.csv"
DEFAULT_CURVE_COLUMN = "golden1_0531_1m"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/golden1_factor_attribution.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/golden1_factor_attribution.md"
DEFAULT_OUTPUT_FAMILY = PROJECT_ROOT / "results/golden1_factor_attribution_family.json"
DEFAULT_OUTPUT_FAMILY_MD = PROJECT_ROOT / "report/group_a_plus/latest/golden1_factor_attribution_family.md"

MKT_TICKER = "0050.TW"
LETF_TICKER = "00631L.TW"
LETF_TARGET_MULTIPLE = 2.0
TSMOM_LOOKBACK = 20
HAC_LAGS = 5


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_strategy_returns(curve_path: Path, column: str) -> pd.Series:
    frame = pd.read_csv(curve_path, encoding="utf-8-sig")
    if "dt" not in frame.columns or column not in frame.columns:
        raise ValueError(f"{curve_path} must contain 'dt' and '{column}' columns")
    frame["dt"] = pd.to_datetime(frame["dt"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["dt"]).set_index("dt").sort_index()
    value = pd.to_numeric(frame[column], errors="coerce")
    returns = value.pct_change().dropna()
    returns.name = "strategy_return"
    return returns


def load_close_series(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        raise RuntimeError(f"No ohlcv rows for {ticker} in [{start.date()}, {end.date()}]")
    df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
    series = df.set_index("dt")["close"].astype(float).sort_index()
    series.name = ticker
    return series


def build_factors(mkt_close: pd.Series, letf_close: pd.Series) -> pd.DataFrame:
    mkt_ret = mkt_close.pct_change()
    letf_ret = letf_close.pct_change()

    letf_xs = letf_ret - LETF_TARGET_MULTIPLE * mkt_ret
    letf_xs.name = "LETF_XS"

    trailing_sign = np.sign(mkt_close.pct_change(TSMOM_LOOKBACK).shift(1))
    tsmom = trailing_sign * mkt_ret
    tsmom.name = "TSMOM"

    rev1 = -1.0 * mkt_ret.shift(1)
    rev1.name = "REV1"

    mkt_ret.name = "MKT"

    return pd.concat([mkt_ret, letf_xs, tsmom, rev1], axis=1)


def _hac_ols(y: pd.Series, X: pd.DataFrame) -> dict[str, Any]:
    design = sm.add_constant(X)
    model = sm.OLS(y, design).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    coeffs = {}
    for name in design.columns:
        coeffs[name] = {
            "coef": float(model.params[name]),
            "t": float(model.tvalues[name]),
            "p": float(model.pvalues[name]),
        }
    return {
        "n": int(model.nobs),
        "r_squared": float(model.rsquared),
        "coefficients": coeffs,
        "annualized_alpha": float(model.params["const"] * 252),
    }


def _regress_strategy(strategy_ret: pd.Series, factors: pd.DataFrame) -> dict[str, Any] | None:
    panel = pd.concat([strategy_ret, factors], axis=1).dropna()
    if len(panel) < 60:
        return None

    y = panel["strategy_return"]
    beta_only = _hac_ols(y, panel[["MKT", "LETF_XS"]])
    full_model = _hac_ols(y, panel[["MKT", "LETF_XS", "TSMOM", "REV1"]])

    simple_corr = {
        "strategy_vs_mkt": float(panel["strategy_return"].corr(panel["MKT"])),
        "strategy_vs_letf_xs": float(panel["strategy_return"].corr(panel["LETF_XS"])),
    }
    factor_corr = panel[["MKT", "LETF_XS", "TSMOM", "REV1"]].corr().round(3).to_dict()

    strategy_annualized_return = float((1.0 + y).prod() ** (252.0 / len(y)) - 1.0)
    strategy_annualized_vol = float(y.std(ddof=1) * np.sqrt(252))

    return {
        "sample": {
            "n_days": int(len(panel)),
            "start": str(panel.index.min().date()),
            "end": str(panel.index.max().date()),
        },
        "strategy_stats": {
            "annualized_return": strategy_annualized_return,
            "annualized_volatility": strategy_annualized_vol,
        },
        "simple_correlations": simple_corr,
        "factor_correlation_matrix": factor_corr,
        "beta_only_model": beta_only,
        "full_model": full_model,
        "beta_explained_r_squared_share": (
            float(beta_only["r_squared"] / full_model["r_squared"]) if full_model["r_squared"] > 0 else None
        ),
        "incremental_r_squared_from_momentum_reversal": float(full_model["r_squared"] - beta_only["r_squared"]),
    }


def build_report(curve_path: Path, curve_column: str) -> dict[str, Any]:
    strategy_ret = load_strategy_returns(curve_path, curve_column)
    start, end = strategy_ret.index.min(), strategy_ret.index.max()

    mkt_close = load_close_series(MKT_TICKER, start - pd.Timedelta(days=45), end)
    letf_close = load_close_series(LETF_TICKER, start - pd.Timedelta(days=45), end)
    factors = build_factors(mkt_close, letf_close)

    result = _regress_strategy(strategy_ret, factors)
    if result is None:
        raise RuntimeError(f"Too few aligned rows for {curve_column} to run a meaningful regression")

    return {
        "report_type": "golden1_factor_attribution",
        "source_paper": "arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)",
        "curve_path": str(curve_path.relative_to(PROJECT_ROOT)),
        "curve_column": curve_column,
        **result,
        "sample": {
            **result["sample"],
            "caveat": _sample_caveat(result["sample"]["start"], result["sample"]["end"]),
        },
    }


def _sample_caveat(start: str, end: str) -> str:
    years = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    if years < 3:
        return f"Single ~{years:.1f}-year window ({start} to {end}); likely one regime, descriptive attribution not an OOS predictive test."
    return (
        f"{years:.1f}-year window ({start} to {end}), spanning multiple regimes; still a descriptive "
        "in-sample attribution (weights/rules are fixed, not walk-forward retrained), not an OOS predictive test."
    )


def build_family_report(curve_path: Path, columns: list[str] | None = None) -> dict[str, Any]:
    raw = pd.read_csv(curve_path, encoding="utf-8-sig")
    if "dt" not in raw.columns:
        raise ValueError(f"{curve_path} must contain a 'dt' column")
    if columns is None:
        columns = [c for c in raw.columns if c != "dt"]

    all_returns = {col: load_strategy_returns(curve_path, col) for col in columns}
    start = min(s.index.min() for s in all_returns.values())
    end = max(s.index.max() for s in all_returns.values())

    mkt_close = load_close_series(MKT_TICKER, start - pd.Timedelta(days=45), end)
    letf_close = load_close_series(LETF_TICKER, start - pd.Timedelta(days=45), end)
    factors = build_factors(mkt_close, letf_close)

    per_column: dict[str, Any] = {}
    skipped: list[str] = []
    for col, strategy_ret in all_returns.items():
        result = _regress_strategy(strategy_ret, factors)
        if result is None:
            skipped.append(col)
            continue
        per_column[col] = result

    caveat = (
        _sample_caveat(str(start.date()), str(end.date()))
        if per_column
        else "No column had enough aligned rows for a regression."
    )
    return {
        "report_type": "golden1_factor_attribution_family",
        "source_paper": "arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)",
        "curve_path": str(curve_path.relative_to(PROJECT_ROOT)),
        "caveat": caveat,
        "skipped_columns": skipped,
        "columns": per_column,
    }


def _fmt_coef(entry: dict[str, Any]) -> str:
    stars = "***" if entry["p"] < 0.01 else "**" if entry["p"] < 0.05 else "*" if entry["p"] < 0.10 else ""
    return f"{entry['coef']:.4f}{stars} (t={entry['t']:.2f}, p={entry['p']:.3f})"


def _markdown(report: dict[str, Any]) -> str:
    sample = report["sample"]
    strat = report["strategy_stats"]
    beta_only = report["beta_only_model"]
    full = report["full_model"]
    corr = report["simple_correlations"]

    full_alpha = full["coefficients"]["const"]
    if full_alpha["p"] < 0.10:
        alpha_line = (
            f"- The full-model alpha is {'positive' if full_alpha['coef'] > 0 else 'negative'} and "
            f"statistically significant (p={full_alpha['p']:.3f}), so residual return beyond MKT/LETF_XS/"
            "TSMOM/REV1 exposure is distinguishable from zero at conventional levels."
        )
    else:
        alpha_line = (
            f"- The full-model alpha (annualized {full['annualized_alpha']:.2%}) is statistically "
            f"indistinguishable from zero (p={full_alpha['p']:.3f}): once MKT and LETF_XS exposure are "
            "controlled for, there is no reliable evidence of residual timing alpha in this sample -- "
            "the strategy's headline return is explained almost entirely by beta exposure, not by "
            "genuine market-neutral skill."
        )

    lines = [
        "# Golden1_0531 Factor Attribution (research diagnostic)",
        "",
        f"- Source paper: `{report['source_paper']}`",
        f"- Curve: `{report['curve_path']}` column `{report['curve_column']}`",
        f"- Sample: {sample['n_days']} trading days, {sample['start']} to {sample['end']}",
        f"- Caveat: {sample['caveat']}",
        "",
        "## Strategy Stats (full sample)",
        f"- Annualized return: `{strat['annualized_return']:.2%}`",
        f"- Annualized volatility: `{strat['annualized_volatility']:.2%}`",
        f"- Simple correlation vs 0050 (MKT): `{corr['strategy_vs_mkt']:.3f}`",
        f"- Simple correlation vs 00631L excess-of-2x (LETF_XS): `{corr['strategy_vs_letf_xs']:.3f}`",
        "",
        "## Beta-Only Model: strategy_return ~ const + MKT + LETF_XS",
        f"- n = {beta_only['n']}, R² = `{beta_only['r_squared']:.3f}`",
        f"- alpha (annualized): `{beta_only['annualized_alpha']:.2%}`",
        f"- MKT: {_fmt_coef(beta_only['coefficients']['MKT'])}",
        f"- LETF_XS: {_fmt_coef(beta_only['coefficients']['LETF_XS'])}",
        "",
        "## Full Model: + TSMOM + REV1",
        f"- n = {full['n']}, R² = `{full['r_squared']:.3f}`",
        f"- alpha (annualized): `{full['annualized_alpha']:.2%}`",
        f"- MKT: {_fmt_coef(full['coefficients']['MKT'])}",
        f"- LETF_XS: {_fmt_coef(full['coefficients']['LETF_XS'])}",
        f"- TSMOM: {_fmt_coef(full['coefficients']['TSMOM'])}",
        f"- REV1: {_fmt_coef(full['coefficients']['REV1'])}",
        "",
        "## Interpretation",
        (
            f"- Beta-only model explains `{report['beta_explained_r_squared_share']:.1%}` of the variance "
            "captured by the full model; the remainder (momentum + reversal + noise) adds "
            f"`{report['incremental_r_squared_from_momentum_reversal']:.3f}` incremental R²."
        ),
        alpha_line,
        (
            "*** p<0.01, ** p<0.05, * p<0.10. HAC (Newey-West) standard errors, "
            f"maxlags={HAC_LAGS}, matching the precedent in "
            "`scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`."
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


def _family_markdown(report: dict[str, Any]) -> str:
    rows = []
    for col, r in report["columns"].items():
        full = r["full_model"]
        beta_only = r["beta_only_model"]
        alpha_p = full["coefficients"]["const"]["p"]
        rows.append(
            {
                "column": col,
                "n": r["sample"]["n_days"],
                "beta_r2": beta_only["r_squared"],
                "full_r2": full["r_squared"],
                "alpha_ann": full["annualized_alpha"],
                "alpha_p": alpha_p,
                "mkt_beta": full["coefficients"]["MKT"]["coef"],
                "corr_mkt": r["simple_correlations"]["strategy_vs_mkt"],
            }
        )
    rows.sort(key=lambda r: r["alpha_p"])

    lines = [
        "# Golden1_0531 Family Factor Attribution (research diagnostic)",
        "",
        f"- Source paper: `{report['source_paper']}`",
        f"- Curve: `{report['curve_path']}`",
        f"- Caveat: {report['caveat']}",
    ]
    if report["skipped_columns"]:
        lines.append(f"- Skipped (too few aligned rows): {', '.join(report['skipped_columns'])}")
    lines += [
        "",
        "Sorted by full-model alpha p-value (most significant residual alpha first).",
        "",
        "| strategy | n | corr(MKT) | beta-only R² | full R² | MKT beta | alpha (ann.) | alpha p |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        sig = "**" if r["alpha_p"] < 0.05 else "*" if r["alpha_p"] < 0.10 else ""
        lines.append(
            f"| {r['column']} | {r['n']} | {r['corr_mkt']:.3f} | {r['beta_r2']:.3f} | {r['full_r2']:.3f} | "
            f"{r['mkt_beta']:.3f} | {r['alpha_ann']:.2%}{sig} | {r['alpha_p']:.3f} |"
        )
    lines += [
        "",
        "** p<0.05, * p<0.10 on the full-model alpha (const term).",
        (
            "If no row's alpha is significant, none of the switch-policy variants in this family show "
            "residual return beyond MKT/LETF_XS/TSMOM/REV1 exposure in this sample -- the whole family's "
            "reported Sharpe is beta-explained here, not signal-specific to golden1_0531."
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output: Path, output_md: Path, markdown_fn=_markdown) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown_fn(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curve", default=str(DEFAULT_CURVE))
    parser.add_argument("--curve-column", default=DEFAULT_CURVE_COLUMN)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--family", action="store_true", help="Regress every column in the curve CSV instead of a single strategy")
    parser.add_argument("--family-output", default=str(DEFAULT_OUTPUT_FAMILY))
    parser.add_argument("--family-output-md", default=str(DEFAULT_OUTPUT_FAMILY_MD))
    parser.add_argument("--columns", default=None, help="Comma-separated subset of curve columns to regress in --family mode (default: all)")
    args = parser.parse_args()

    if args.family:
        columns = [c.strip() for c in args.columns.split(",")] if args.columns else None
        report = build_family_report(_resolve(args.curve), columns=columns)
        write_outputs(
            report,
            output=_resolve(args.family_output),
            output_md=_resolve(args.family_output_md),
            markdown_fn=_family_markdown,
        )
        print(f"Family factor attribution written to {_resolve(args.family_output)}")
        print(
            json.dumps(
                {
                    "columns_regressed": list(report["columns"].keys()),
                    "skipped_columns": report["skipped_columns"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    report = build_report(_resolve(args.curve), args.curve_column)
    write_outputs(report, output=_resolve(args.output), output_md=_resolve(args.output_md))

    print(f"Factor attribution written to {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "n": report["sample"]["n_days"],
                "beta_only_r2": report["beta_only_model"]["r_squared"],
                "full_r2": report["full_model"]["r_squared"],
                "full_annualized_alpha": report["full_model"]["annualized_alpha"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
