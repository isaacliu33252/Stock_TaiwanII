#!/usr/bin/env python3
"""Generate a static comparison report for latest GroupA+ and Golden1_0531."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
DEFAULT_DECISION_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "decision.json"
DEFAULT_GOLDEN_SIGNAL = PROJECT_ROOT / "results" / "signal_group_a_golden1_0531_predict_20260615_from_all_20260613_total1000000.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "compare" / "html"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy_compare.json"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash"]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _latest_signal_path(baseline: dict[str, Any], decision_pointer: str | Path, explicit_latest_signal: str | None) -> Path:
    if explicit_latest_signal:
        return _resolve(explicit_latest_signal)
    pointer_path = _resolve(decision_pointer)
    if pointer_path.exists():
        pointer = _load(pointer_path)
        signal_json = pointer.get("signal_json")
        if signal_json:
            return _resolve(signal_json)
    return _resolve(baseline["latest_group_a_plus_final_signal"])


def _weight_from_shares(payload: dict[str, Any], ticker: str, total_assets: float) -> float:
    if ticker == "cash":
        execution = dict(payload.get("execution_summary", {}) or {})
        if "cash_after_cost" in execution:
            return float(execution.get("cash_after_cost") or 0.0) / max(total_assets, 1.0)
        return float(payload.get("target_cash_weight", 0.0) or 0.0)
    shares = float((payload.get("target_shares") or {}).get(ticker, 0.0) or 0.0)
    price = float((payload.get("latest_prices") or {}).get(ticker, 0.0) or 0.0)
    return shares * price / max(total_assets, 1.0)


def _strategy_from_group_a_signal(name: str, payload: dict[str, Any], source: str, role: str) -> dict[str, Any]:
    total_assets = float(payload.get("current_total_portfolio_value") or payload.get("total_assets") or 0.0)
    target_weights = dict(payload.get("target_weights") or payload.get("planned_target_weights") or {})
    target_cash = float(payload.get("target_cash_weight", 0.0) or 0.0)
    if "cash" not in target_weights:
        target_weights["cash"] = target_cash
    return {
        "name": name,
        "role": role,
        "source": source,
        "requested_as_of_date": payload.get("requested_as_of_date"),
        "actual_data_date": payload.get("actual_data_date"),
        "signal_status": payload.get("signal_status"),
        "signal_reason": payload.get("signal_reason"),
        "action_label": payload.get("action_label"),
        "candidate_target_label": payload.get("candidate_target_label"),
        "effective_target_label": payload.get("effective_target_label"),
        "total_assets": total_assets,
        "target_weights": {ticker: float(target_weights.get(ticker, 0.0) or 0.0) for ticker in TICKERS},
        "target_shares": dict(payload.get("target_shares") or {}),
        "latest_prices": dict(payload.get("latest_prices") or {}),
        "execution_summary": dict(payload.get("execution_summary") or {}),
    }


def _strategy_from_group_a_plus_signal(name: str, payload: dict[str, Any], source: str, role: str) -> dict[str, Any]:
    total_assets = float(payload.get("total_assets") or payload.get("current_total_portfolio_value") or 0.0)
    weights = {
        ticker: _weight_from_shares(payload, ticker, total_assets)
        for ticker in TICKERS
    }
    return {
        "name": name,
        "role": role,
        "source": source,
        "requested_as_of_date": payload.get("requested_as_of_date"),
        "actual_data_date": payload.get("actual_data_date"),
        "signal_status": payload.get("signal_status"),
        "signal_reason": payload.get("signal_reason"),
        "action_label": payload.get("action_label"),
        "candidate_target_label": payload.get("candidate_target_label"),
        "effective_target_label": payload.get("effective_target_label"),
        "total_assets": total_assets,
        "target_weights": weights,
        "target_shares": dict(payload.get("target_shares") or {}),
        "latest_prices": dict(payload.get("latest_prices") or {}),
        "overlay_regime": (payload.get("overlay_policy") or {}).get("regime"),
        "overlay_00679b_weight": payload.get("overlay_00679b_weight"),
        "execution_summary": dict(payload.get("execution_summary") or {}),
    }


def _fmt_pct(value: Any) -> str:
    return f"{float(value or 0.0):.2%}"


def _fmt_num(value: Any, digits: int = 0) -> str:
    return f"{float(value or 0.0):,.{digits}f}"


def _table_rows(left: dict[str, Any], right: dict[str, Any]) -> str:
    rows = []
    left_weights = dict(left.get("target_weights") or {})
    right_weights = dict(right.get("target_weights") or {})
    left_shares = dict(left.get("target_shares") or {})
    right_shares = dict(right.get("target_shares") or {})
    for ticker in TICKERS:
        rows.append(
            "<tr>"
            f"<td>{escape(ticker)}</td>"
            f"<td class=\"num\">{_fmt_pct(left_weights.get(ticker, 0.0))}</td>"
            f"<td class=\"num\">{escape(str(left_shares.get(ticker, '-')))}</td>"
            f"<td class=\"num\">{_fmt_pct(right_weights.get(ticker, 0.0))}</td>"
            f"<td class=\"num\">{escape(str(right_shares.get(ticker, '-')))}</td>"
            f"<td class=\"num\">{_fmt_pct(float(left_weights.get(ticker, 0.0)) - float(right_weights.get(ticker, 0.0)))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _metric_card(strategy: dict[str, Any]) -> str:
    execution = dict(strategy.get("execution_summary") or {})
    return f"""
      <section class="card">
        <div class="role">{escape(str(strategy.get("role", "")))}</div>
        <h2>{escape(str(strategy.get("name", "")))}</h2>
        <dl>
          <dt>Status</dt><dd>{escape(str(strategy.get("signal_status", "")))}</dd>
          <dt>Reason</dt><dd>{escape(str(strategy.get("signal_reason", "")))}</dd>
          <dt>Actual Data</dt><dd>{escape(str(strategy.get("actual_data_date", "")))}</dd>
          <dt>Total Assets</dt><dd>{_fmt_num(strategy.get("total_assets", 0.0))}</dd>
          <dt>Cash After Cost</dt><dd>{_fmt_num(execution.get("cash_after_cost", 0.0))}</dd>
          <dt>Turnover Ratio</dt><dd>{_fmt_pct(execution.get("turnover_ratio", 0.0))}</dd>
        </dl>
        <div class="label">Effective target</div>
        <p>{escape(str(strategy.get("effective_target_label") or strategy.get("candidate_target_label") or ""))}</p>
        <div class="source"><code>{escape(str(strategy.get("source", "")))}</code></div>
      </section>
    """


def _render_html(report: dict[str, Any]) -> str:
    latest = report["latest_group_a_plus"]
    golden = report["golden1_0531"]
    generated = escape(str(report["generated_at"]))
    rows = _table_rows(latest, golden)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GroupA+ vs Golden1_0531</title>
  <style>
    :root {{
      --bg:#f6f7f9; --panel:#fff; --text:#20242a; --muted:#68717e; --line:#d9dee7;
      --accent:#2457a6; --warn:#9a5b00; --warn-bg:#fff3d6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"Noto Sans TC",sans-serif; background:var(--bg); color:var(--text); line-height:1.45; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:24px auto 42px; }}
    header {{ padding:20px 0 18px; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:19px; letter-spacing:0; }}
    .subtle {{ color:var(--muted); font-size:14px; }}
    .notice {{ margin-top:14px; padding:12px 14px; border:1px solid #ead28f; background:var(--warn-bg); color:var(--warn); border-radius:8px; }}
    .cards {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:18px; }}
    .card, section.table {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; }}
    .role {{ color:var(--accent); font-size:12px; font-weight:700; text-transform:uppercase; margin-bottom:4px; }}
    dl {{ display:grid; grid-template-columns:150px 1fr; gap:8px 12px; margin:12px 0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; font-weight:600; overflow-wrap:anywhere; }}
    .label {{ color:var(--muted); font-size:13px; margin-top:10px; }}
    p {{ margin:4px 0 0; }}
    .source {{ margin-top:12px; color:var(--muted); overflow-wrap:anywhere; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:650; }}
    .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    footer {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    @media (max-width: 820px) {{ .cards {{ grid-template-columns:1fr; }} dl {{ grid-template-columns:1fr; }} main {{ width:calc(100% - 20px); }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>GroupA+ vs Golden1_0531</h1>
      <div class="subtle">Generated: {generated}</div>
      <div class="notice">本頁 Golden1_0531 benchmark 使用 1,000,000 資金基準；Latest GroupA+ 目前沿用 active final signal 的資產基準。主要比較 target weight，股數只作操作參考。</div>
    </header>
    <div class="cards">
      {_metric_card(latest)}
      {_metric_card(golden)}
    </div>
    <section class="table" style="margin-top:14px">
      <h2>Target Comparison</h2>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th class="num">Latest Weight</th>
            <th class="num">Latest Shares</th>
            <th class="num">Golden Weight</th>
            <th class="num">Golden Shares</th>
            <th class="num">Weight Delta</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <footer>Operational comparison only. This report is not investment advice.</footer>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--decision-pointer", default=str(DEFAULT_DECISION_POINTER))
    parser.add_argument("--latest-signal", default=None)
    parser.add_argument("--golden-signal", default=str(DEFAULT_GOLDEN_SIGNAL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LATEST))
    args = parser.parse_args()

    baseline_path = _resolve(args.baseline)
    baseline = _load(baseline_path)
    latest_signal_path = _latest_signal_path(baseline, args.decision_pointer, args.latest_signal)
    golden_signal_path = _resolve(args.golden_signal)
    latest_payload = _load(latest_signal_path)
    golden_payload = _load(golden_signal_path)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": str(baseline_path.relative_to(PROJECT_ROOT)),
        "latest_group_a_plus": _strategy_from_group_a_plus_signal(
            "Latest GroupA+",
            latest_payload,
            str(latest_signal_path.relative_to(PROJECT_ROOT)),
            f"active baseline: {baseline['profile']}",
        ),
        "golden1_0531": _strategy_from_group_a_signal(
            "Golden1_0531",
            golden_payload,
            str(golden_signal_path.relative_to(PROJECT_ROOT)),
            "benchmark: Golden1_0531 total 1,000,000",
        ),
        "comparison_note": "Target weights are comparable. Target shares may use different capital bases.",
    }

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace("-", "").replace(":", "").replace("T", "_")
    html_path = output_dir / f"group_a_plus_vs_golden1_0531_{stamp}.html"
    json_path = output_dir.with_name("json") / f"group_a_plus_vs_golden1_0531_{stamp}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(_render_html(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_pointer = _resolve(args.latest_pointer)
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest = {
        "report_type": "strategy_compare",
        "generated_at": report["generated_at"],
        "latest_profile": baseline["profile"],
        "benchmark": "Golden1_0531",
        "html": str(html_path.relative_to(PROJECT_ROOT)),
        "json": str(json_path.relative_to(PROJECT_ROOT)),
    }
    latest_pointer.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"HTML: {html_path}")
    print(f"JSON: {json_path}")
    print(f"Latest: {latest_pointer}")


if __name__ == "__main__":
    main()
