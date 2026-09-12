#!/usr/bin/env python3
"""Build the GroupA+ review for arXiv:2604.11335 tail-dependence trends."""

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

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.build_group_a_plus_2607_16450_tail_dependence_monitor import (
    DEFAULT_TICKERS,
    _load_close,
    _rolling_snapshots,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date

DEFAULT_PDF = Path("/mnt/c/Users/isaac/Downloads/2604.11335.pdf")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_trend_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_11335_tail_dependence_trend_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_11335_tail_dependence_trend_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _series_slope(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    if not np.isfinite(y).all():
        return None
    return _float(np.polyfit(x, y, 1)[0])


def _trend_summary(snapshots: list[dict[str, Any]], assets: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    by_asset: dict[str, list[tuple[str, float]]] = {asset: [] for asset in assets}
    for snapshot in snapshots:
        date = str(snapshot.get("date"))
        for row in snapshot.get("pairs", []):
            asset = str(row.get("asset"))
            value = row.get("lower_tail_dependence_proxy")
            if asset in by_asset and isinstance(value, (int, float)):
                by_asset[asset].append((date, float(value)))

    summary: dict[str, dict[str, Any]] = {}
    for asset, observations in by_asset.items():
        values = [value for _date, value in observations]
        if not values:
            summary[asset] = {"status": "insufficient_data", "observations": 0}
            continue
        first_date, first_value = observations[0]
        latest_date, latest_value = observations[-1]
        prior_values = values[:-126] if len(values) > 126 else values[: max(1, len(values) // 2)]
        recent_values = values[-126:] if len(values) > 126 else values[max(0, len(values) // 2) :]
        prior_mean = float(np.mean(prior_values)) if prior_values else float(np.mean(values))
        recent_mean = float(np.mean(recent_values)) if recent_values else float(np.mean(values))
        summary[asset] = {
            "status": "available",
            "observations": len(values),
            "first_date": first_date,
            "latest_date": latest_date,
            "first_lower_tail_dependence_proxy": _float(first_value),
            "latest_lower_tail_dependence_proxy": _float(latest_value),
            "long_run_mean": _float(np.mean(values)),
            "recent_126_snapshot_mean": _float(recent_mean),
            "prior_mean": _float(prior_mean),
            "recent_minus_prior": _float(recent_mean - prior_mean),
            "min": _float(np.min(values)),
            "max": _float(np.max(values)),
            "linear_trend_per_snapshot": _series_slope(values),
        }
    return summary


def build_review(
    *,
    pdf_path: Path = DEFAULT_PDF,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    alpha: float = 0.10,
    window: int = 252,
    high_tail_dependence_threshold: float = 0.65,
    trend_alert_threshold: float = 0.10,
) -> dict[str, Any]:
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    blockers: list[str] = []
    warnings: list[str] = []
    if not pdf_path.exists():
        blockers.append("source_pdf_missing")
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, end_resolved)
    if close.empty or base not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    available = tuple(col for col in tickers if col in returns.columns and returns[col].notna().sum() >= window)
    assets = tuple(ticker for ticker in available if ticker != base)
    snapshots = _rolling_snapshots(
        returns[list(available)] if available else returns,
        base=base,
        assets=assets,
        alpha=alpha,
        window=window,
    )
    latest = snapshots[-1] if snapshots else {"date": None, "pairs": []}
    trend = _trend_summary(snapshots, assets)
    high_latest = [
        row for row in latest.get("pairs", [])
        if isinstance(row.get("lower_tail_dependence_proxy"), (int, float))
        and float(row["lower_tail_dependence_proxy"]) >= high_tail_dependence_threshold
    ]
    rising = [
        asset for asset, row in trend.items()
        if isinstance(row.get("recent_minus_prior"), (int, float))
        and float(row["recent_minus_prior"]) >= trend_alert_threshold
    ]
    if high_latest:
        warnings.append("high_latest_lower_tail_dependence_present")
    if "00631L.TW" in {row.get("asset") for row in high_latest}:
        warnings.append("00631l_lower_tail_dependence_high_vs_0050")
    if rising:
        warnings.append("tail_dependence_recent_mean_rising")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_11335_tail_dependence_trend_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "policy": "research_shadow_only_no_live_weight_change",
        "source_paper": {
            "path": str(pdf_path),
            "exists": pdf_path.exists(),
            "title": "Trends in tail dependence of heteroscedastic extremes",
            "arxiv": "2604.11335v1",
            "authors": ["John H. J. Einmahl", "Chen Zhou"],
            "paper_date": "2026-04-14",
            "main_idea": "nonparametric integrated tail-copula estimation and tests for time-varying tail dependence under heteroscedastic marginals",
        },
        "groupa_plus_mapping": {
            "importable_advantage": "tail_dependence_trend_stability_diagnostic",
            "implemented_as": "empirical rolling lower-tail co-exceedance trend proxy",
            "paper_equivalent": False,
            "reason_not_exact": "Full tail-copula asymptotic test requires larger samples and careful k/h calibration; GroupA+ has a small ETF universe and needs a conservative diagnostic first.",
        },
        "parameters": {
            "start": start,
            "end": end_resolved,
            "tickers": list(tickers),
            "available_tickers": list(available),
            "base": base,
            "alpha": alpha,
            "window": window,
            "high_tail_dependence_threshold": high_tail_dependence_threshold,
            "trend_alert_threshold": trend_alert_threshold,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "snapshot_count": int(len(snapshots)),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "latest": latest,
        "trend_summary": trend,
        "alerts": {
            "high_latest_assets": [row.get("asset") for row in high_latest],
            "recent_tail_dependence_rising_assets": rising,
        },
        "decision": {
            "review_complete": True,
            "has_importable_advantage": True,
            "best_import": "shadow_tail_dependence_trend_diagnostic_only",
            "promote_tail_copula_test_to_live_gate": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
            "allow_00632r_open_from_tail_dependence": False,
            "keep_golden1_0531_unchanged": True,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# 2604.11335 Tail Dependence Trend Review",
        "",
        f"Generated: `{review['generated_at']}`",
        f"Status: `{review['status']}`",
        "",
        "## Decision",
        "",
        "- Best import: `shadow_tail_dependence_trend_diagnostic_only`.",
        "- Do not promote a full tail-copula test to live gating.",
        "- Do not change latest strategy target weights.",
        "- Do not add `00631L.TW` or open `00632R.TW` from this paper.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Latest Lower-Tail Snapshot",
        "",
        "| Asset | Lower-tail proxy | Co-exceedance days | Correlation |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in review.get("latest", {}).get("pairs", []):
        lines.append(
            "| {asset} | {tail} | {co} | {corr} |".format(
                asset=row.get("asset"),
                tail=row.get("lower_tail_dependence_proxy"),
                co=row.get("co_exceedance_days"),
                corr=row.get("linear_correlation"),
            )
        )
    lines.extend(
        [
            "",
            "## Trend Summary",
            "",
            "| Asset | Latest | Long-run mean | Recent-prior | Slope |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for asset, row in review.get("trend_summary", {}).items():
        lines.append(
            "| {asset} | {latest} | {mean} | {diff} | {slope} |".format(
                asset=asset,
                latest=row.get("latest_lower_tail_dependence_proxy"),
                mean=row.get("long_run_mean"),
                diff=row.get("recent_minus_prior"),
                slope=row.get("linear_trend_per_snapshot"),
            )
        )
    lines.extend(
        [
            "",
            "## Alerts",
            "",
            f"- High latest assets: `{review.get('alerts', {}).get('high_latest_assets')}`",
            f"- Rising recent tail-dependence assets: `{review.get('alerts', {}).get('recent_tail_dependence_rising_assets')}`",
            f"- Warning reasons: `{review.get('warning_reasons')}`",
            "",
        ]
    )
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2604_11335_tail_dependence_trend_review_{as_of.replace('-', '')}.json"


def write_review(review: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(review) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        as_of = str(review.get("parameters", {}).get("end") or datetime.now().strftime("%Y-%m-%d"))
        _history_path(history_dir, as_of).write_text(
            json.dumps(review, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--window", type=int, default=252)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        pdf_path=_resolve(args.pdf),
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        alpha=args.alpha,
        window=args.window,
    )
    write_review(
        review,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"2604.11335 tail-dependence trend review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "best_import": review["decision"]["best_import"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "alerts": review["alerts"],
                "warnings": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
