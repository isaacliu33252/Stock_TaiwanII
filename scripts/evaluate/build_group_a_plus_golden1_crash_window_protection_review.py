#!/usr/bin/env python3
"""Crash-window protection diagnostic for golden1_0531 / switch-policy variants.

Research/advisory-readiness artifact only. Never touches production weights,
pointers, or the daily pipeline. Read-only against results/*.csv and the
DuckDB ohlcv table.

Follow-up to `build_group_a_plus_golden1_factor_attribution_review.py`, which
found no statistically significant residual alpha for golden1_0531 or any
switch_ma* variant over a 9.6-year, multi-regime sample (2017-01 to
2026-08) -- the strategies' average excess return is beta-explained. Average
excess return is not the whole story for a switching strategy, though: the
point of switching out of a leveraged/long allocation is often drawdown
protection during crashes, which a mean-return regression does not directly
measure. This script asks the narrower question: during known Taiwan-market
crash windows, did switching actually cut losses relative to simply holding
the market (0050), or is that also indistinguishable from the beta-implied
loss?

Caveat: only 3 windows are examined (small n for a between-window
comparison); this is descriptive, not a significance test on the crash
effect itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(PROJECT_ROOT), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_group_a_plus_golden1_factor_attribution_review import (  # noqa: E402
    MKT_TICKER,
    load_close_series,
)

DEFAULT_CURVE = PROJECT_ROOT / "results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810_curve.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/golden1_crash_window_protection.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/golden1_crash_window_protection.md"

STRATEGY_COLUMNS = [
    "golden1_0531_1m",
    "group_a_plus_defensive_1m",
    "switch_ma20_dd5_hold5",
    "switch_ma20_dd7_hold5",
    "switch_ma60_dd8_hold10",
    "switch_ma60_dd10_hold10",
    "switch_ma90_dd12_hold5_eg020_xg010",
    "switch_ma120_dd12_hold15",
]

CRASH_WINDOWS = [
    ("2018Q4_correction", "2018-10-01", "2018-12-31"),
    ("2020_covid_crash", "2020-01-15", "2020-03-23"),
    ("2022_bear_market", "2022-01-01", "2022-10-31"),
]

DRAWDOWN_THRESHOLD = -0.08
MIN_GAP_TRADING_DAYS = 20


PEAK_LOOKBACK_TRADING_DAYS = 252


def detect_drawdown_episodes(
    mkt_close: pd.Series, threshold: float = DRAWDOWN_THRESHOLD, min_gap_days: int = MIN_GAP_TRADING_DAYS
) -> list[tuple[str, str, str]]:
    """Objectively find peak-to-trough episodes where 0050 fell below `threshold`
    from its trailing 1-year high (not the all-time high, which would keep a
    single stale pre-2020-style peak "open" for years in a structurally rising
    market and produce many overlapping pseudo-episodes off the same old high),
    merging episodes that resume within `min_gap_days` trading days of each
    other (multi-leg selloffs). Returns (label, peak_date, trough_date) tuples,
    avoiding hand-picked windows."""
    mkt_close = mkt_close.dropna().sort_index()
    running_max = mkt_close.rolling(PEAK_LOOKBACK_TRADING_DAYS, min_periods=1).max()
    drawdown = mkt_close / running_max - 1.0
    in_episode = (drawdown < threshold).to_numpy()

    blocks: list[tuple[int, int]] = []
    start = None
    for i, flag in enumerate(in_episode):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            blocks.append((start, i - 1))
            start = None
    if start is not None:
        blocks.append((start, len(in_episode) - 1))

    merged: list[tuple[int, int]] = []
    for s, e in blocks:
        if merged and (mkt_close.index[s] - mkt_close.index[merged[-1][1]]).days <= min_gap_days * 1.5:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    episodes: list[tuple[str, str, str]] = []
    for s, e in merged:
        lookback_start = max(0, s - PEAK_LOOKBACK_TRADING_DAYS + 1)
        peak_date = mkt_close.iloc[lookback_start : s + 1].idxmax()
        trough_date = drawdown.iloc[s : e + 1].idxmin()
        year = trough_date.year
        label = f"{year}_drawdown_{peak_date.strftime('%Y%m%d')}_{trough_date.strftime('%Y%m%d')}"
        episodes.append((label, str(peak_date.date()), str(trough_date.date())))
    return episodes


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_curve_values(curve_path: Path, columns: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(curve_path, encoding="utf-8-sig")
    if "dt" not in frame.columns:
        raise ValueError(f"{curve_path} must contain a 'dt' column")
    frame["dt"] = pd.to_datetime(frame["dt"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["dt"]).set_index("dt").sort_index()
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{curve_path} is missing columns: {missing}")
    return frame[columns].apply(pd.to_numeric, errors="coerce")


def _window_stats(values: pd.Series) -> dict[str, Any] | None:
    values = values.dropna()
    if len(values) < 3:
        return None
    window_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    running_max = values.cummax()
    drawdown = values / running_max - 1.0
    max_drawdown = float(drawdown.min())
    return {"n": int(len(values)), "return": window_return, "max_drawdown": max_drawdown}


def build_report(curve_path: Path, columns: list[str], windows: list[tuple[str, str, str]] | None = None) -> dict[str, Any]:
    curve = load_curve_values(curve_path, columns)
    windows = windows if windows is not None else CRASH_WINDOWS

    windows_out: dict[str, Any] = {}
    for label, start, end in windows:
        window_curve = curve.loc[start:end]
        if window_curve.empty:
            windows_out[label] = {"start": start, "end": end, "skipped": "no rows in curve for this window"}
            continue

        mkt_close = load_close_series(MKT_TICKER, pd.Timestamp(start), pd.Timestamp(end))
        mkt_stats = _window_stats(mkt_close)

        strategies: dict[str, Any] = {}
        for col in columns:
            stats = _window_stats(window_curve[col])
            if stats is None or mkt_stats is None:
                continue
            stats["excess_return_vs_mkt"] = stats["return"] - mkt_stats["return"]
            stats["drawdown_relief_vs_mkt"] = stats["max_drawdown"] - mkt_stats["max_drawdown"]
            strategies[col] = stats

        windows_out[label] = {
            "start": start,
            "end": end,
            "mkt_0050": mkt_stats,
            "strategies": strategies,
        }

    aggregate: dict[str, Any] = {}
    for col in columns:
        excess_vals = [
            w["strategies"][col]["excess_return_vs_mkt"]
            for w in windows_out.values()
            if isinstance(w, dict) and "strategies" in w and col in w["strategies"]
        ]
        relief_vals = [
            w["strategies"][col]["drawdown_relief_vs_mkt"]
            for w in windows_out.values()
            if isinstance(w, dict) and "strategies" in w and col in w["strategies"]
        ]
        if not excess_vals:
            continue
        n = len(excess_vals)
        aggregate[col] = {
            "n_windows": n,
            "mean_excess_return_vs_mkt": float(sum(excess_vals) / n),
            "mean_drawdown_relief_vs_mkt": float(sum(relief_vals) / n),
            "windows_with_positive_excess_return": int(sum(1 for v in excess_vals if v > 0)),
            "windows_with_positive_drawdown_relief": int(sum(1 for v in relief_vals if v > 0)),
        }

    n_windows_used = len(windows_out)
    return {
        "report_type": "golden1_crash_window_protection",
        "curve_path": str(curve_path.relative_to(PROJECT_ROOT)),
        "caveat": (
            f"{n_windows_used} crash window(s); descriptive comparison, not a formal significance test. "
            "Fixed weights/rules replayed in-sample, not walk-forward retrained."
        ),
        "windows": windows_out,
        "aggregate": aggregate,
    }


def _fmt_pct(x: float) -> str:
    return f"{x:+.2%}"


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Golden1_0531 / Switch-Policy Crash-Window Protection (research diagnostic)",
        "",
        f"- Curve: `{report['curve_path']}`",
        f"- Caveat: {report['caveat']}",
        "",
    ]

    for label, w in report["windows"].items():
        lines.append(f"## {label} ({w['start']} to {w['end']})")
        if "skipped" in w:
            lines.append(f"- Skipped: {w['skipped']}")
            lines.append("")
            continue
        mkt = w["mkt_0050"]
        lines.append(f"- 0050 (MKT) return: `{_fmt_pct(mkt['return'])}`, max drawdown: `{_fmt_pct(mkt['max_drawdown'])}`")
        lines.append("")
        lines.append("| strategy | return | max drawdown | excess vs MKT | drawdown relief vs MKT |")
        lines.append("|---|---|---|---|---|")
        for col, stats in w["strategies"].items():
            lines.append(
                f"| {col} | {_fmt_pct(stats['return'])} | {_fmt_pct(stats['max_drawdown'])} | "
                f"{_fmt_pct(stats['excess_return_vs_mkt'])} | {_fmt_pct(stats['drawdown_relief_vs_mkt'])} |"
            )
        lines.append("")

    lines.append("## Aggregate Across Windows")
    lines.append("")
    lines.append(
        "| strategy | n windows | mean excess return vs MKT | positive-excess hit rate | "
        "mean drawdown relief vs MKT | positive-relief hit rate |"
    )
    lines.append("|---|---|---|---|---|---|")
    for col, agg in sorted(report["aggregate"].items(), key=lambda kv: -kv[1]["mean_drawdown_relief_vs_mkt"]):
        n = agg["n_windows"]
        lines.append(
            f"| {col} | {n} | {_fmt_pct(agg['mean_excess_return_vs_mkt'])} | "
            f"{agg['windows_with_positive_excess_return']}/{n} | "
            f"{_fmt_pct(agg['mean_drawdown_relief_vs_mkt'])} | "
            f"{agg['windows_with_positive_drawdown_relief']}/{n} |"
        )
    lines.append("")
    lines.append(
        "Positive \"drawdown relief\" means the strategy's max drawdown in that window was shallower "
        "(less negative) than simply holding 0050; positive \"excess return\" means it lost less (or gained "
        "more) than 0050 over the window."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output: Path, output_md: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curve", default=str(DEFAULT_CURVE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--columns", default=",".join(STRATEGY_COLUMNS))
    parser.add_argument(
        "--auto-detect",
        action="store_true",
        help="Detect drawdown episodes from 0050 (threshold/min-gap below) instead of using the 3 hand-picked CRASH_WINDOWS",
    )
    parser.add_argument("--threshold", type=float, default=DRAWDOWN_THRESHOLD)
    parser.add_argument("--min-gap-days", type=int, default=MIN_GAP_TRADING_DAYS)
    args = parser.parse_args()

    columns = [c.strip() for c in args.columns.split(",")]
    curve_path = _resolve(args.curve)

    windows = None
    if args.auto_detect:
        curve_dates = load_curve_values(curve_path, columns).index
        mkt_close = load_close_series(MKT_TICKER, curve_dates.min(), curve_dates.max())
        windows = detect_drawdown_episodes(mkt_close, threshold=args.threshold, min_gap_days=args.min_gap_days)
        print(f"Auto-detected {len(windows)} drawdown episodes (threshold={args.threshold:.0%}):")
        for label, start, end in windows:
            print(f"  {label}: {start} -> {end}")

    report = build_report(curve_path, columns, windows=windows)
    write_outputs(report, output=_resolve(args.output), output_md=_resolve(args.output_md))

    print(f"Crash-window protection report written to {_resolve(args.output)}")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
