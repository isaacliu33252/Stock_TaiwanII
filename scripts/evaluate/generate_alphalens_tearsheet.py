#!/usr/bin/env python3
"""Generate an Alphalens-reloaded tear sheet for GroupA+ NCF advisory factors.

Produces a multi-page PDF saved under results/tearsheets/.
Uses alphalens.plotting functions directly (single-asset time-series format),
combined with our factor_lens.py data prep.

Usage:
    .venv/bin/python scripts/evaluate/generate_alphalens_tearsheet.py
    .venv/bin/python scripts/evaluate/generate_alphalens_tearsheet.py \
        --factor ncf_00631l_prob_up --output results/tearsheets/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.backends.backend_pdf as pdf_backend
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import alphalens.performance as perf
import alphalens.plotting as plotting

from FinRL.data.stock_db import DB_PATH
from group_a_plus.integrations.factor_lens import (
    ic_decay,
    make_single_asset_factor_data,
    rolling_time_series_ic,
    cumulative_quantile_returns,
)
from scripts.evaluate.evaluate_group_a_plus_factor_lens import (
    build_factor_series,
    load_advisory,
    load_close_prices,
    resolve_latest_advisory_panel,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "tearsheets"
HORIZONS = (1, 5, 20)
DECAY_LAGS = 20
ROLLING_WINDOW = 63


def _factor_data_to_alphalens(factor_data: pd.DataFrame) -> pd.DataFrame:
    """Reformat our factor_data into the shape alphalens.performance expects.

    alphalens expects a MultiIndex DataFrame (date, asset) with columns:
    fwd_ret_<N>d, factor, factor_quantile.
    Our make_single_asset_factor_data already produces this exact layout.
    """
    al = factor_data.copy()
    # alphalens perf functions use period-labeled columns like '1D','5D','20D'
    # but we can use our fwd_ret_Nd directly for the plotting calls that accept
    # a generic factor_data — they just need 'factor' and 'factor_quantile'.
    return al


def generate_tearsheet(
    factor_name: str,
    factor: pd.Series,
    price: pd.Series,
    output_dir: Path,
) -> Path:
    factor_data = make_single_asset_factor_data(
        factor, price, asset="0050.TW", horizons=HORIZONS
    )
    fd = _factor_data_to_alphalens(factor_data)

    rolling_ic = rolling_time_series_ic(fd, window=ROLLING_WINDOW)
    decay = ic_decay(factor, price, max_lag=DECAY_LAGS)
    cum_q = {
        col: cumulative_quantile_returns(fd, horizon=col)
        for col in [f"fwd_ret_{h}d" for h in HORIZONS]
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    out_path = output_dir / f"{factor_name}_{date_tag}.pdf"

    with pdf_backend.PdfPages(str(out_path)) as pdf:

        # ── Page 1: Rolling IC ──────────────────────────────────────────────
        fig, axes = plt.subplots(len(HORIZONS), 1, figsize=(14, 4 * len(HORIZONS)))
        fig.suptitle(f"{factor_name}\nRolling IC (window={ROLLING_WINDOW}d)", fontsize=13)
        for ax, col in zip(axes, rolling_ic.columns):
            series = rolling_ic[col].dropna()
            pct_pos = (series > 0).mean() * 100
            icir = series.mean() / series.std() if series.std() > 0 else float("nan")
            ax.fill_between(series.index, series.values, 0,
                            where=(series.values >= 0), alpha=0.25, color="steelblue")
            ax.fill_between(series.index, series.values, 0,
                            where=(series.values < 0), alpha=0.25, color="tomato")
            ax.plot(series.index, series.values, lw=1.2, color="steelblue")
            ax.axhline(0, color="black", lw=1.0, ls="-")
            ax.axhline(series.mean(), color="red", lw=2.0, ls="--",
                       label=f"mean = {series.mean():.3f}")
            ax.set_title(
                f"{col}   ICIR={icir:.2f}   % above 0 = {pct_pos:.1f}%",
                fontsize=10,
            )
            ax.legend(fontsize=9, loc="upper left")
            ax.set_ylabel("Spearman IC")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # ── Page 2: IC Decay ───────────────────────────────────────────────
        lags = list(range(1, DECAY_LAGS + 1))
        ic_vals = [decay.get(f"{l}d") for l in lags]
        fig, ax = plt.subplots(figsize=(14, 5))
        fig.suptitle(f"{factor_name}\nIC Decay (Spearman)", fontsize=13)
        ax.bar(lags, ic_vals, color=["steelblue" if (v or 0) >= 0 else "tomato" for v in ic_vals])
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xlabel("Lag (trading days)")
        ax.set_ylabel("Spearman IC")
        ax.set_xticks(lags)
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # ── Page 3: Mean return by quantile ────────────────────────────────
        fwd_cols = [f"fwd_ret_{h}d" for h in HORIZONS]
        mean_q = fd.dropna(subset=["factor_quantile"]).groupby("factor_quantile")[fwd_cols].mean()
        fig, axes = plt.subplots(1, len(fwd_cols), figsize=(14, 5))
        fig.suptitle(f"{factor_name}\nMean Forward Return by Quantile", fontsize=13)
        for ax, col in zip(axes, fwd_cols):
            vals = mean_q[col] * 100  # to %
            colors = ["steelblue" if v >= 0 else "tomato" for v in vals]
            ax.bar(vals.index.astype(int), vals.values, color=colors)
            ax.axhline(0, color="black", lw=0.8)
            ax.set_title(col)
            ax.set_xlabel("Quantile")
            ax.set_ylabel("Mean return (%)")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # ── Page 4: Cumulative returns by quantile ──────────────────────────
        fig, axes = plt.subplots(len(HORIZONS), 1, figsize=(14, 4 * len(HORIZONS)))
        fig.suptitle(f"{factor_name}\nCumulative Returns by Quantile", fontsize=13)
        for ax, h in zip(axes, HORIZONS):
            col = f"fwd_ret_{h}d"
            cumret = cum_q[col]
            if cumret.empty:
                ax.set_title(f"{col} — no data")
                continue
            for q in cumret.columns:
                ax.plot(cumret.index, cumret[q] * 100, label=f"Q{int(q)}", lw=1.2)
            ax.axhline(0, color="black", lw=0.8, ls="--")
            ax.set_title(col)
            ax.legend(fontsize=8, ncol=5)
            ax.set_ylabel("Cumulative return (%)")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory-panel", default=None)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--asset", default="0050.TW")
    parser.add_argument("--factor", default=None, help="Single factor name (default: all)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    advisory_path = (
        Path(args.advisory_panel) if args.advisory_panel else resolve_latest_advisory_panel()
    )
    if not advisory_path.is_absolute():
        advisory_path = PROJECT_ROOT / advisory_path
    advisory = load_advisory(advisory_path)

    end_date = advisory.index.max() + timedelta(days=max(HORIZONS) * 3)
    prices = load_close_prices(
        Path(args.db),
        [args.asset],
        advisory.index.min().strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    price = prices[args.asset].dropna()

    factors = build_factor_series(advisory)
    if args.factor:
        if args.factor not in factors:
            print(f"Unknown factor '{args.factor}'. Available: {list(factors)}")
            sys.exit(1)
        factors = {args.factor: factors[args.factor]}

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    for name, factor in factors.items():
        print(f"Generating tear sheet: {name} ...")
        try:
            out = generate_tearsheet(name, factor, price, output_dir)
            print(f"  Saved: {out}")
        except Exception as exc:
            print(f"  FAILED: {exc}")


if __name__ == "__main__":
    main()
