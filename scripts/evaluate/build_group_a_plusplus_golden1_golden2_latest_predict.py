#!/usr/bin/env python3
"""Build a GroupA++ Golden1/Golden2/latest prediction comparison."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.runners.a2118 import run_a2118


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


def _latest_prices(db_path: Path, data_date: str) -> dict[str, float]:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            select ticker, close
            from ohlcv
            where dt = ? and ticker in (?, ?, ?, ?, ?)
            order by ticker
            """,
            [data_date, *TICKERS],
        ).fetchall()
    finally:
        con.close()
    return {str(ticker): float(close) for ticker, close in rows}


def _shares(weights: dict[str, float], prices: dict[str, float], total: float) -> dict[str, int]:
    out: dict[str, int] = {}
    for ticker in TICKERS:
        price = float(prices.get(ticker, 0.0) or 0.0)
        out[ticker] = int((total * float(weights.get(ticker, 0.0) or 0.0)) // price) if price > 0 else 0
    return out


def _market_values(shares: dict[str, int], prices: dict[str, float]) -> dict[str, float]:
    return {ticker: float(shares.get(ticker, 0)) * float(prices.get(ticker, 0.0) or 0.0) for ticker in TICKERS}


def _source_row(
    *,
    source: str,
    path: Path,
    payload: dict[str, Any],
    prices: dict[str, float],
    total: float,
) -> dict[str, Any]:
    data = _unwrap(payload)
    weights = dict(data.get("target_weights") or data.get("live_weights") or {})
    weights = {ticker: float(weights.get(ticker, 0.0) or 0.0) for ticker in TICKERS} | {
        "cash": float(weights.get("cash", 0.0) or 0.0)
    }
    shares = _shares(weights, prices, total)
    values = _market_values(shares, prices)
    sleeve = (data.get("group_a_plusplus_extension") or {}).get("ncf_sleeve_decision") or {}
    return {
        "source": source,
        "path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
        "strategy_family": data.get("strategy_family"),
        "actual_data_date": data.get("actual_data_date") or (data.get("window") or {}).get("end"),
        "execution_allowed": data.get("execution_allowed"),
        "regime": data.get("execution_regime") or data.get("today_regime"),
        "ncf_00713_status": sleeve.get("status"),
        "ncf_00713_reason": sleeve.get("reason"),
        "ncf_00713_effective_weight": sleeve.get("effective_weight"),
        "target_weights": weights,
        "reference_target_shares_before_cost": shares,
        "reference_target_market_values": values,
        "estimated_cash_after_rounding_before_cost": float(total - sum(values.values())),
    }


def _write_runner_output(path: Path, frame_path: Path, report: dict[str, Any], frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(frame_path, encoding="utf-8-sig")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_override(
    *,
    source: str,
    output: Path,
    frame_output: Path,
    start: str,
    end: str,
    total: float,
    db_path: Path,
    runner_params: dict[str, Any],
    golden_signal_path: str,
    ncf_panel_631l_path: str,
) -> dict[str, Any]:
    params = dict(runner_params)
    params["golden_signal_path_override"] = golden_signal_path
    params["ncf_panel_631l_path"] = ncf_panel_631l_path
    report, frame = run_a2118(start, end, total, db_path, **params)
    report = dict(report)
    report["source"] = source
    report["requested_as_of_date"] = None
    _write_runner_output(output, frame_output, report, frame)
    return report


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    manifest = resolve_latest(_resolve(args.manifest))
    runner_params = dict((manifest["active_strategy"] or {}).get("runner_params") or {})
    total = float(args.total)

    latest_payload = _load_json(args.latest_signal)
    latest_data = _unwrap(latest_payload)
    actual_data_date = str(latest_data.get("actual_data_date") or args.data_date)
    prices = dict(latest_data.get("latest_prices") or {}) or _latest_prices(db_path, actual_data_date)
    prices = {ticker: float(prices.get(ticker, 0.0) or 0.0) for ticker in TICKERS}

    golden1_report = _run_override(
        source="golden1_0531_groupA++",
        output=_resolve(args.golden1_output),
        frame_output=_resolve(args.golden1_frame_output),
        start=args.start,
        end=actual_data_date,
        total=total,
        db_path=db_path,
        runner_params=runner_params,
        golden_signal_path=args.golden1_signal,
        ncf_panel_631l_path=args.golden1_ncf_panel_631l,
    )
    golden2_report = _run_override(
        source="golden2_0830_groupA++_whatif",
        output=_resolve(args.golden2_output),
        frame_output=_resolve(args.golden2_frame_output),
        start=args.start,
        end=actual_data_date,
        total=total,
        db_path=db_path,
        runner_params=runner_params,
        golden_signal_path=args.golden2_signal,
        ncf_panel_631l_path=args.golden2_ncf_panel_631l,
    )

    sources = [
        _source_row(source="golden1_0531_groupA++", path=_resolve(args.golden1_output), payload=golden1_report, prices=prices, total=total),
        _source_row(source="golden2_0830_groupA++_whatif", path=_resolve(args.golden2_output), payload=golden2_report, prices=prices, total=total),
        _source_row(source="latest_groupA++", path=_resolve(args.latest_signal), payload=latest_payload, prices=prices, total=total),
    ]
    return {
        "schema_version": 1,
        "report_type": f"group_a_plusplus_golden1_golden2_latest_predict_{args.as_of.replace('-', '')}",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_as_of": args.as_of,
        "actual_data_date": actual_data_date,
        "portfolio_value": total,
        "latest_prices": prices,
        "active_manifest": args.manifest,
        "runner_params_used": runner_params,
        "sources": sources,
        "decision": {
            "can_run_all_three_as_groupAplusplus": True,
            "order_execution_source": "latest_groupA++_subject_to_execution_guard",
            "golden1_0531_role": "lockdown research comparator",
            "golden2_0830_role": "lockdown frozen-release what-if comparator; do not modify frozen release files",
            "latest_groupAplusplus_role": "active strategy source; order execution still requires execution_allowed=true",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# GroupA++ Golden1 / Golden2 / Latest Predict {report['requested_as_of']}",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- actual_data_date: `{report['actual_data_date']}`",
        f"- portfolio_value: `{report['portfolio_value']:,.0f}`",
        f"- latest_strategy_00713_sleeve: `{report['runner_params_used'].get('group_a_plusplus_00713_cash_sleeve_weight'):.2%}`",
        "",
        "| source | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00632R sh | 00713 sh | ncf_00713 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["sources"]:
        w = row["target_weights"]
        s = row["reference_target_shares_before_cost"]
        lines.append(
            "| {source} | {w0050:.4%} | {w631:.4%} | {w632:.4%} | {w679:.4%} | {w713:.4%} | {cash:.4%} | {sh0050} | {sh631} | {sh632} | {sh713} | {ncf} |".format(
                source=row["source"],
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
                ncf=row.get("ncf_00713_reason"),
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- `latest_groupA++` is the active strategy source, but order execution still requires `execution_allowed=true`.",
            "- `golden1_0531_groupA++` and `golden2_0830_groupA++_whatif` are lockdown comparators.",
            "- `golden1_0531` and `golden2_0830` frozen release files were not modified.",
            "",
        ]
    )
    return "\n".join(lines)


def write_xlsx(report: dict[str, Any], path: Path) -> None:
    rows = []
    for source in report["sources"]:
        row = {
            "source": source["source"],
            "path": source["path"],
            "actual_data_date": source["actual_data_date"],
            "ncf_00713_status": source.get("ncf_00713_status"),
            "ncf_00713_reason": source.get("ncf_00713_reason"),
            "cash_after_rounding": source["estimated_cash_after_rounding_before_cost"],
        }
        for ticker in (*TICKERS, "cash"):
            row[f"weight_{ticker}"] = source["target_weights"].get(ticker, 0.0)
        for ticker in TICKERS:
            row[f"shares_{ticker}"] = source["reference_target_shares_before_cost"].get(ticker, 0)
            row[f"market_value_{ticker}"] = source["reference_target_market_values"].get(ticker, 0.0)
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="prediction", index=False)
        pd.DataFrame([report["decision"]]).to_excel(writer, sheet_name="decision", index=False)
        pd.DataFrame([report["latest_prices"]]).to_excel(writer, sheet_name="prices", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-09-07")
    parser.add_argument("--data-date", default="2026-09-04")
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--total", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--latest-signal", default="results/group_a_plusplus_live_signal_v2_predict_20260907_from_20260904_total1000000_latest_strategy.json")
    parser.add_argument("--golden1-signal", default="results/signal_group_a_golden1_0531_predict_20260707_from_20260706_total1000000.json")
    parser.add_argument("--golden2-signal", default="results/golden2_0830/signal_group_a_golden2_0830_20260831.json")
    parser.add_argument("--golden1-ncf-panel-631l", default="results/ncf_00631l_panel_latest_20260907.csv")
    parser.add_argument("--golden2-ncf-panel-631l", default="results/golden2_0830/ncf_00631l_panel_golden2_0830.csv")
    parser.add_argument("--golden1-output", default="results/group_a_plusplus_golden1_0531_override_runner_20260907.json")
    parser.add_argument("--golden1-frame-output", default="results/group_a_plusplus_golden1_0531_override_frame_20260907.csv")
    parser.add_argument("--golden2-output", default="results/golden2_0830/group_a_plusplus_golden2_0830_override_runner_20260907.json")
    parser.add_argument("--golden2-frame-output", default="results/golden2_0830/group_a_plusplus_golden2_0830_override_frame_20260907.csv")
    parser.add_argument("--output", default="report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260907.json")
    parser.add_argument("--markdown", default="report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260907.md")
    parser.add_argument("--xlsx", default="report/group_a_plus/latest/group_a_plusplus_golden1_golden2_latest_predict_20260907.xlsx")
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    write_xlsx(report, _resolve(args.xlsx))
    print(f"Prediction JSON: {output}")
    print(f"Prediction Markdown: {markdown}")
    print(f"Prediction Workbook: {_resolve(args.xlsx)}")


if __name__ == "__main__":
    main()
