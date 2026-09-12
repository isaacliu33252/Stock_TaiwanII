#!/usr/bin/env python3
"""Build a split-mode GroupA++ prediction report for frozen vs latest-data sources."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path)


def _weights(data: dict[str, Any]) -> dict[str, float]:
    raw = data.get("target_weights") or data.get("live_weights") or {}
    return {ticker: float(raw.get(ticker, 0.0) or 0.0) for ticker in TICKERS} | {
        "cash": float(raw.get("cash", 0.0) or 0.0)
    }


def _shares(weights: dict[str, float], prices: dict[str, float], total: float) -> dict[str, int]:
    out: dict[str, int] = {}
    for ticker in TICKERS:
        price = float(prices.get(ticker, 0.0) or 0.0)
        out[ticker] = int((total * weights.get(ticker, 0.0)) // price) if price > 0 else 0
    return out


def _signal_date(data: dict[str, Any]) -> str | None:
    coverage = data.get("golden_signal_coverage") or {}
    signal_path = coverage.get("golden_signal_path")
    if signal_path:
        try:
            signal = _unwrap(_load_json(signal_path))
            return signal.get("actual_data_date") or signal.get("requested_as_of_date")
        except Exception:
            return None
    return data.get("actual_data_date")


def _ncf_panel_last(data: dict[str, Any]) -> str | None:
    coverage = data.get("ncf_panel_coverage") or {}
    if coverage.get("panel_631l_last_date"):
        return coverage.get("panel_631l_last_date")
    overlay = data.get("ncf_live_overlay") or {}
    return overlay.get("date_00631l")


def _ncf_00713_date(data: dict[str, Any]) -> str | None:
    sleeve = (data.get("group_a_plusplus_extension") or {}).get("ncf_sleeve_decision") or {}
    return sleeve.get("actual_date") or sleeve.get("signal_date")


def _row(
    *,
    name: str,
    mode: str,
    path: str,
    prices: dict[str, float],
    total: float,
    note: str,
) -> dict[str, Any]:
    resolved = _resolve(path)
    data = _unwrap(_load_json(resolved))
    weights = _weights(data)
    shares = _shares(weights, prices, total)
    values = {ticker: shares[ticker] * float(prices.get(ticker, 0.0) or 0.0) for ticker in TICKERS}
    window = data.get("window") or {}
    return {
        "source": name,
        "mode": mode,
        "path": _rel(resolved),
        "requested_as_of_date": data.get("requested_as_of_date"),
        "market_data_date": data.get("actual_data_date") or window.get("end"),
        "base_signal_data_date": _signal_date(data),
        "ncf_00631l_panel_last_date": _ncf_panel_last(data),
        "ncf_00713_actual_date": _ncf_00713_date(data),
        "target_weights": weights,
        "reference_target_shares_before_cost": shares,
        "reference_target_market_values": values,
        "estimated_cash_after_rounding_before_cost": float(total - sum(values.values())),
        "note": note,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    latest_data = _unwrap(_load_json(args.latest))
    prices = {ticker: float(value) for ticker, value in dict(latest_data.get("latest_prices") or {}).items()}
    prices = {ticker: float(prices.get(ticker, 0.0) or 0.0) for ticker in TICKERS}
    total = float(args.total)
    rows = [
        _row(
            name="golden1_0531_frozen_pinned",
            mode="frozen/pinned signal + latest market replay",
            path=args.golden1_frozen,
            prices=prices,
            total=total,
            note="Keeps the pinned Golden1 signal; useful for version comparison, not a latest-data rerun.",
        ),
        _row(
            name="golden1_0531_latestdata_rerun",
            mode="latest-data rerun",
            path=args.golden1_latestdata,
            prices=prices,
            total=total,
            note="Regenerated from latest available data; expected to match latest base line when the same Golden1/last PPO mainline is used.",
        ),
        _row(
            name="golden2_0830_frozen_pinned",
            mode="frozen/pinned signal + latest market replay",
            path=args.golden2_frozen,
            prices=prices,
            total=total,
            note="Keeps the frozen 2026-08-28 Golden2 signal; preserves the historical 00632R leg.",
        ),
        _row(
            name="golden2_0830_latestdata_rerun",
            mode="latest-data rerun",
            path=args.golden2_latestdata,
            prices=prices,
            total=total,
            note="Regenerated from latest data. Current frozen Golden2 model/result artifact is byte-identical to Golden1/last PPO, so it converges.",
        ),
        _row(
            name="latest_groupA++",
            mode="active latest strategy",
            path=args.latest,
            prices=prices,
            total=total,
            note="Order source.",
        ),
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_source_mode_split_predict",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_as_of": args.as_of,
        "actual_data_date": latest_data.get("actual_data_date"),
        "portfolio_value": total,
        "latest_prices": prices,
        "sources": rows,
        "decision": {
            "order_execution_source": "latest_groupA++",
            "why_three_latestdata_rows_match": (
                "Golden1 latest-data rerun, Golden2 latest-data rerun, and latest all use the same "
                "Golden1/last PPO mainline under current artifacts, then the same GroupA++ 00713 sleeve."
            ),
            "why_frozen_rows_differ": "Frozen/pinned rows keep older signal dates and therefore preserve historical weights.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# GroupA++ Source Mode Split Predict {report['requested_as_of']}",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- actual_data_date: `{report['actual_data_date']}`",
        f"- portfolio_value: `{report['portfolio_value']:,.0f}`",
        "",
        "| source | mode | signal data | market data | ncf631L | ncf00713 | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["sources"]:
        w = row["target_weights"]
        s = row["reference_target_shares_before_cost"]
        lines.append(
            "| {source} | {mode} | {signal} | {market} | {ncf631} | {ncf713} | {w0050:.4%} | {w631:.4%} | {w632:.4%} | {w679:.4%} | {w713:.4%} | {cash:.4%} | {sh0050} | {sh631} | {sh632} | {sh713} |".format(
                source=row["source"],
                mode=row["mode"],
                signal=row.get("base_signal_data_date"),
                market=row.get("market_data_date"),
                ncf631=row.get("ncf_00631l_panel_last_date"),
                ncf713=row.get("ncf_00713_actual_date"),
                w0050=w.get("0050.TW", 0.0),
                w631=w.get("00631L.TW", 0.0),
                w632=w.get("00632R.TW", 0.0),
                w679=w.get("00679B.TWO", 0.0),
                w713=w.get("00713.TW", 0.0),
                cash=w.get("cash", 0.0),
                sh0050=s.get("0050.TW", 0),
                sh631=s.get("00631L.TW", 0),
                sh632=s.get("00632R.TW", 0),
                sh713=s.get("00713.TW", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Explanation",
            "",
            f"- Why latest-data rows match: {report['decision']['why_three_latestdata_rows_match']}",
            f"- Why frozen rows differ: {report['decision']['why_frozen_rows_differ']}",
            "- Use `latest_groupA++` for orders.",
            "",
            "## Source Notes",
            "",
        ]
    )
    for row in report["sources"]:
        lines.append(f"- `{row['source']}`: {row['note']} Path: `{row['path']}`")
    lines.append("")
    return "\n".join(lines)


def write_xlsx(report: dict[str, Any], path: Path) -> None:
    rows = []
    for source in report["sources"]:
        row = {
            "source": source["source"],
            "mode": source["mode"],
            "path": source["path"],
            "base_signal_data_date": source["base_signal_data_date"],
            "market_data_date": source["market_data_date"],
            "ncf_00631l_panel_last_date": source["ncf_00631l_panel_last_date"],
            "ncf_00713_actual_date": source["ncf_00713_actual_date"],
            "cash_after_rounding": source["estimated_cash_after_rounding_before_cost"],
            "note": source["note"],
        }
        for ticker in (*TICKERS, "cash"):
            row[f"weight_{ticker}"] = source["target_weights"].get(ticker, 0.0)
        for ticker in TICKERS:
            row[f"shares_{ticker}"] = source["reference_target_shares_before_cost"].get(ticker, 0)
            row[f"market_value_{ticker}"] = source["reference_target_market_values"].get(ticker, 0.0)
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="source_mode_split", index=False)
        pd.DataFrame([report["decision"]]).to_excel(writer, sheet_name="decision", index=False)
        pd.DataFrame([report["latest_prices"]]).to_excel(writer, sheet_name="prices", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-09-07")
    parser.add_argument("--total", type=float, default=1_000_000.0)
    parser.add_argument("--golden1-frozen", default="results/group_a_plusplus_golden1_0531_override_runner_20260907.json")
    parser.add_argument("--golden1-latestdata", default="results/group_a_plusplus_golden1_0531_override_runner_latestdata_20260907.json")
    parser.add_argument("--golden2-frozen", default="results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260907.json")
    parser.add_argument("--golden2-latestdata", default="results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_latestdata_20260907.json")
    parser.add_argument("--latest", default="results/group_a_plusplus_live_signal_v2_predict_20260907_from_20260904_total1000000_latest_strategy.json")
    parser.add_argument("--output", default="report/group_a_plus/latest/group_a_plusplus_source_mode_split_predict_20260907.json")
    parser.add_argument("--markdown", default="report/group_a_plus/latest/group_a_plusplus_source_mode_split_predict_20260907.md")
    parser.add_argument("--xlsx", default="report/group_a_plus/latest/group_a_plusplus_source_mode_split_predict_20260907.xlsx")
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    write_xlsx(report, _resolve(args.xlsx))
    print(f"Split prediction JSON: {output}")
    print(f"Split prediction Markdown: {markdown}")
    print(f"Split prediction Workbook: {_resolve(args.xlsx)}")


if __name__ == "__main__":
    main()
