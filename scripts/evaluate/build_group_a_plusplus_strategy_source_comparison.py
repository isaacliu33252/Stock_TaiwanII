#!/usr/bin/env python3
"""Compare GroupA++ latest against Golden1_0531 and Golden2_0830 sources."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.md"
DEFAULT_XLSX = PROJECT_ROOT / "report/group_a_plus/latest/group_a_plusplus_strategy_source_comparison.xlsx"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _weights_from_signal(payload: dict[str, Any]) -> dict[str, float]:
    data = _unwrap(payload)
    raw = dict(data.get("target_weights") or data.get("planned_target_weights") or {})
    weights = {ticker: float(raw.get(ticker, 0.0) or 0.0) for ticker in TICKERS}
    weights["cash"] = float(raw.get("cash", data.get("target_cash_weight", 0.0)) or 0.0)
    return weights


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
    name: str,
    path: Path,
    payload: dict[str, Any],
    prices: dict[str, float],
    total: float,
    source_type: str,
    promotion_status: str | None = None,
) -> dict[str, Any]:
    data = _unwrap(payload)
    weights = _weights_from_signal(payload)
    shares = _shares(weights, prices, total)
    values = _market_values(shares, prices)
    return {
        "name": name,
        "source_type": source_type,
        "path": str(path),
        "requested_as_of_date": data.get("requested_as_of_date"),
        "actual_data_date": data.get("actual_data_date"),
        "strategy_id": data.get("strategy_id"),
        "strategy_family": data.get("strategy_family"),
        "execution_allowed": data.get("execution_allowed"),
        "promotion_status": promotion_status,
        "target_weights": weights,
        "reference_target_shares_before_cost": shares,
        "reference_target_market_values": values,
        "estimated_cash_after_rounding_before_cost": float(total - sum(values.values())),
    }


def _golden2_gate_summary(gate_payload: dict[str, Any]) -> dict[str, Any]:
    gate = _unwrap(gate_payload)
    candidates = gate.get("candidates") if isinstance(gate.get("candidates"), list) else []
    first = candidates[0] if candidates else {}
    return {
        "decision": gate.get("decision"),
        "candidate": first.get("candidate"),
        "window_count": first.get("window_count"),
        "pass_count": first.get("pass_count"),
        "pass_ratio": first.get("pass_ratio"),
        "worst_delta_final_pct": first.get("worst_delta_final_pct"),
        "worst_delta_sharpe": first.get("worst_delta_sharpe"),
        "worst_delta_max_drawdown": first.get("worst_delta_max_drawdown"),
        "candidate_decision": first.get("decision"),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    total = float(args.total)
    latest_path = _resolve(args.latest_signal)
    golden1_path = _resolve(args.golden1_signal)
    golden1_release_path = _resolve(args.golden1_release)
    golden2_path = _resolve(args.golden2_signal)
    golden2_gate_path = _resolve(args.golden2_gate)

    latest_payload = _load_json(latest_path)
    latest_data = _unwrap(latest_payload)
    prices = {ticker: float(value) for ticker, value in dict(latest_data.get("latest_prices") or {}).items()}
    for payload in (_load_json(golden1_path), _load_json(golden2_path)):
        data = _unwrap(payload)
        for ticker, value in dict(data.get("latest_prices") or {}).items():
            prices.setdefault(str(ticker), float(value))

    golden1_release = _load_json(golden1_release_path)
    golden1_release_snapshot = dict((golden1_release.get("latest_operational_snapshot") or {}))
    golden2_gate = _load_json(golden2_gate_path)
    gate_summary = _golden2_gate_summary(golden2_gate)

    sources = [
        _source_row(
            name="golden1_0531_current_resolved",
            source_type="current_golden1_source",
            path=golden1_path,
            payload=_load_json(golden1_path),
            prices=prices,
            total=total,
            promotion_status="production_source",
        ),
        _source_row(
            name="golden1_0531_frozen_release_snapshot",
            source_type="frozen_release_snapshot",
            path=golden1_release_path,
            payload=golden1_release_snapshot,
            prices=prices,
            total=total,
            promotion_status=str(golden1_release.get("status")),
        ),
        _source_row(
            name="golden2_0830_prediction",
            source_type="frozen_candidate_prediction",
            path=golden2_path,
            payload=_load_json(golden2_path),
            prices=prices,
            total=total,
            promotion_status=str(gate_summary.get("decision")),
        ),
        _source_row(
            name="groupA++_latest_strategy",
            source_type="active_latest_strategy",
            path=latest_path,
            payload=latest_payload,
            prices=prices,
            total=total,
            promotion_status="active",
        ),
    ]
    latest_weights = sources[-1]["target_weights"]
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_strategy_source_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "portfolio_value": total,
        "as_of": latest_data.get("requested_as_of_date"),
        "actual_data_date": latest_data.get("actual_data_date"),
        "latest_prices": prices,
        "sources": sources,
        "golden2_gate_summary": gate_summary,
        "decision": {
            "can_run_group_a_plusplus_golden1_golden2_latest": True,
            "use_for_orders": "groupA++_latest_strategy",
            "golden1_0531_role": "production signal source feeding latest strategy",
            "golden2_0830_role": "research-only comparator; not promoted to live because multi-window gate did not pass",
            "group_a_plusplus_live_weights": latest_weights,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GroupA++ Strategy Source Comparison",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report.get('as_of')}`",
        f"- actual_data_date: `{report.get('actual_data_date')}`",
        f"- portfolio_value: `{report['portfolio_value']:.2f}`",
        "",
        "## Decision",
        "",
        f"- Can run: `{report['decision']['can_run_group_a_plusplus_golden1_golden2_latest']}`",
        f"- Use for orders: `{report['decision']['use_for_orders']}`",
        f"- Golden2 gate: `{report['golden2_gate_summary'].get('decision')}`",
        f"- Golden2 pass ratio: `{report['golden2_gate_summary'].get('pass_count')}/{report['golden2_gate_summary'].get('window_count')}`",
        "",
        "## Weights And Shares",
        "",
        "| source | 0050 | 00631L | 00632R | 00679B | 00713 | cash | 0050 sh | 00631L sh | 00713 sh | cash after rounding | status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["sources"]:
        w = row["target_weights"]
        s = row["reference_target_shares_before_cost"]
        lines.append(
            "| {name} | {w0050:.4%} | {w631:.4%} | {w632:.4%} | {w679:.4%} | {w713:.4%} | {cash:.4%} | {sh0050} | {sh631} | {sh713} | {cash_after:.2f} | {status} |".format(
                name=row["name"],
                w0050=w.get("0050.TW", 0.0),
                w631=w.get("00631L.TW", 0.0),
                w632=w.get("00632R.TW", 0.0),
                w679=w.get("00679B.TWO", 0.0),
                w713=w.get("00713.TW", 0.0),
                cash=w.get("cash", 0.0),
                sh0050=s.get("0050.TW", 0),
                sh631=s.get("00631L.TW", 0),
                sh713=s.get("00713.TW", 0),
                cash_after=row["estimated_cash_after_rounding_before_cost"],
                status=row.get("promotion_status"),
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `groupA++_latest_strategy` is the execution source.",
            "- `golden2_0830` remains research-only because its multi-window gate did not pass.",
            "- `00713.TW` is funded from cash at 5%; `0050.TW` and `00631L.TW` are not reduced.",
            "",
        ]
    )
    return "\n".join(lines)


def write_xlsx(report: dict[str, Any], path: Path) -> None:
    rows = []
    for source in report["sources"]:
        row = {
            "source": source["name"],
            "source_type": source["source_type"],
            "promotion_status": source.get("promotion_status"),
            "requested_as_of_date": source.get("requested_as_of_date"),
            "actual_data_date": source.get("actual_data_date"),
            "cash_after_rounding": source["estimated_cash_after_rounding_before_cost"],
        }
        for ticker in (*TICKERS, "cash"):
            row[f"weight_{ticker}"] = source["target_weights"].get(ticker, 0.0)
        for ticker in TICKERS:
            row[f"shares_{ticker}"] = source["reference_target_shares_before_cost"].get(ticker, 0)
        rows.append(row)
    gate = pd.DataFrame([report["golden2_gate_summary"]])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="source_comparison", index=False)
        gate.to_excel(writer, sheet_name="golden2_gate", index=False)
        pd.DataFrame([report["decision"]]).to_excel(writer, sheet_name="decision", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=float, default=1_000_000.0)
    parser.add_argument("--latest-signal", default="report/group_a_plus/latest/live_signal.json")
    parser.add_argument("--golden1-signal", default="results/group_a_combined_live_latest.json")
    parser.add_argument("--golden1-release", default="results/group_a_release_Golden1_0531.json")
    parser.add_argument(
        "--golden2-signal",
        default="results/golden2_0830/group_a_plus_live_signal_v2_golden2_0830_predict_20260907_from_20260904_total_1m.json",
    )
    parser.add_argument("--golden2-gate", default="report/group_a_plus/latest/golden2_multi_window_gate.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    xlsx = _resolve(args.xlsx)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    write_xlsx(report, xlsx)
    print(f"GroupA++ source comparison: {output}")
    print(f"Markdown: {markdown}")
    print(f"Workbook: {xlsx}")


if __name__ == "__main__":
    main()
