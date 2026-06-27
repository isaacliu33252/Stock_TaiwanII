#!/usr/bin/env python3
"""Generate a dependency-light HTML report for strategy backtests."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd

from finrl_meta_strategy_governance import metrics, rolling_sharpe


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_JSON = PROJECT_ROOT / "results" / "group_ab_meta_governed_hold10_no2884_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json", default=str(DEFAULT_JSON))
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.0f}"
        return f"{value:.4f}"
    return str(value)


def _table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(_fmt(row.get(col, '')))}</td>" for col in columns) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _sparkline(values: pd.Series, *, width: int = 860, height: int = 180, color: str = "#2563eb") -> str:
    values = values.dropna().astype(float)
    if values.empty:
        return "<p>No data</p>"
    sample = values.iloc[:: max(len(values) // 400, 1)]
    ymin, ymax = float(sample.min()), float(sample.max())
    span = ymax - ymin if ymax != ymin else 1.0
    points = []
    for i, value in enumerate(sample):
        x = i * width / max(len(sample) - 1, 1)
        y = height - ((float(value) - ymin) / span) * height
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f"<svg viewBox='0 0 {width} {height}' class='chart'>"
        f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{' '.join(points)}'/>"
        f"</svg>"
    )


def main() -> None:
    args = _parse_args()
    summary_path = _resolve(args.summary_json)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    outputs = summary.get("outputs", {})
    curve_path = _resolve(outputs["curve_csv"])
    trade_path = _resolve(outputs["trade_log_csv"]) if outputs.get("trade_log_csv") else None
    output = _resolve(args.output) if args.output else summary_path.with_suffix(".html")

    curves = pd.read_csv(curve_path, encoding="utf-8-sig")
    curves["date"] = pd.to_datetime(curves["date"])
    curves = curves.set_index("date").sort_index()
    result_rows = list(summary.get("results", []))
    best = summary.get("best", {})
    best_variant = str(best.get("variant", result_rows[0]["variant"] if result_rows else ""))
    best_curve = curves[best_variant].astype(float) if best_variant in curves.columns else curves.iloc[:, -1].astype(float)
    daily = best_curve.pct_change().dropna()
    drawdown = best_curve / best_curve.cummax() - 1.0
    roll = rolling_sharpe(daily, window=126, min_periods=63)

    perf_columns = [
        "variant",
        "final_value",
        "annual_return",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "max_drawdown",
        "volatility",
        "num_events",
        "total_cost",
    ]
    enriched_rows = []
    for row in result_rows:
        variant = str(row.get("variant", ""))
        enriched = dict(row)
        if variant in curves.columns:
            enriched.update(metrics(curves[variant], events=int(row.get("num_events", 0)), total_cost=float(row.get("total_cost", 0.0))))
        enriched_rows.append(enriched)

    trade_preview = ""
    if trade_path and trade_path.exists():
        trades = pd.read_csv(trade_path, encoding="utf-8-sig")
        trade_preview = _table(
            trades.head(30).to_dict("records"),
            [col for col in ["variant", "date", "reason", "stress_state", "transfer_notional", "sell_notional", "total_cost"] if col in trades.columns],
        )
    else:
        trade_preview = "<p>No trade log found.</p>"

    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(str(summary.get('experiment', 'Strategy Report')))}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; }}
h1, h2 {{ margin-bottom: 8px; }}
.meta {{ color: #4b5563; margin-bottom: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0 28px; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f3f4f6; }}
.chart {{ width: 100%; height: 180px; border: 1px solid #e5e7eb; background: #fff; }}
.grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
code {{ background: #f3f4f6; padding: 2px 4px; }}
</style>
</head>
<body>
<h1>{html.escape(str(summary.get('experiment', 'Strategy Report')))}</h1>
<div class="meta">
Source: <code>{html.escape(str(summary_path))}</code><br>
Window: {html.escape(str(summary.get('window', {}).get('start', '')))} ~ {html.escape(str(summary.get('window', {}).get('end', '')))}<br>
Best: <strong>{html.escape(best_variant)}</strong>
</div>

<h2>Performance</h2>
{_table(enriched_rows, [col for col in perf_columns if any(col in row for row in enriched_rows)])}

<div class="grid">
<section>
<h2>Best Portfolio Value</h2>
{_sparkline(best_curve, color="#2563eb")}
</section>
<section>
<h2>Drawdown</h2>
{_sparkline(drawdown, color="#dc2626")}
</section>
<section>
<h2>Rolling Sharpe 126D</h2>
{_sparkline(roll, color="#059669")}
</section>
</div>

<h2>Trade Log Preview</h2>
{trade_preview}

<h2>Outputs</h2>
{_table([{k: v for k, v in outputs.items()}], list(outputs.keys()))}
</body>
</html>
"""
    output.write_text(html_text, encoding="utf-8")
    print(f"HTML report: {output}")


if __name__ == "__main__":
    main()
