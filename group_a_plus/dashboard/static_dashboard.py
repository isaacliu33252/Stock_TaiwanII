"""Build a local read-only HTML dashboard for GroupA+ operations."""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT


LATEST_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "private" / "group_a_plus_dashboard.html"
DEFAULT_HOLDINGS = PROJECT_ROOT / "data" / "private" / "holdings_fubon_latest.json"
DEFAULT_REBALANCE = PROJECT_ROOT / "data" / "private" / "rebalance_plan_latest.json"


@dataclass(frozen=True)
class LoadedJson:
    path: Path
    data: dict[str, Any] | None
    error: str | None = None

    @property
    def exists(self) -> bool:
        return self.path.exists()


def _load_json(path: Path) -> LoadedJson:
    if not path.exists():
        return LoadedJson(path=path, data=None, error="missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return LoadedJson(path=path, data=None, error=f"{exc.__class__.__name__}: {exc}")
    if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if not isinstance(payload, dict):
        return LoadedJson(path=path, data=None, error="json root is not an object")
    return LoadedJson(path=path, data=payload)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_percent(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_number(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def _status_class(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"ok", "fresh", "active", "available", "pass", "passed"}:
        return "ok"
    if text in {"warn", "warning", "medium", "stale"}:
        return "warn"
    if text in {"error", "failed", "fail", "blocked", "high"}:
        return "bad"
    return "muted"


def _pill(label: str, value: Any) -> str:
    cls = _status_class(value)
    return f'<span class="pill {cls}"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></span>'


def _weight_rows(target_weights: dict[str, Any], prices: dict[str, Any]) -> str:
    rows = []
    for ticker, weight in sorted(target_weights.items(), key=lambda item: (-float(item[1] or 0), item[0])):
        width = max(0.0, min(100.0, float(weight or 0) * 100))
        rows.append(
            "<tr>"
            f"<td>{_esc(ticker)}</td>"
            f"<td><div class=\"bar\"><span style=\"width:{width:.3f}%\"></span></div></td>"
            f"<td class=\"num\">{_fmt_percent(weight)}</td>"
            f"<td class=\"num\">{_fmt_money(prices.get(ticker))}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="4" class="empty">No target weights</td></tr>'


def _holding_rows(holdings: dict[str, Any] | None) -> str:
    if not holdings:
        return '<tr><td colspan="2" class="empty">No holdings snapshot loaded</td></tr>'
    rows = []
    for ticker, shares in sorted(holdings.items()):
        rows.append(f"<tr><td>{_esc(ticker)}</td><td class=\"num\">{_fmt_number(shares)}</td></tr>")
    return "\n".join(rows)


def _order_rows(report: dict[str, Any] | None) -> str:
    orders = (((report or {}).get("rebalance_plan") or {}).get("orders") or [])
    if not orders:
        return '<tr><td colspan="6" class="empty">No rebalance orders available</td></tr>'
    rows = []
    for order in orders:
        rows.append(
            "<tr>"
            f"<td>{_esc(order.get('ticker'))}</td>"
            f"<td><span class=\"side {_esc(str(order.get('side', '')).lower())}\">{_esc(order.get('side'))}</span></td>"
            f"<td class=\"num\">{_fmt_number(order.get('shares'))}</td>"
            f"<td class=\"num\">{_fmt_money(order.get('price'))}</td>"
            f"<td class=\"num\">{_fmt_money(order.get('trade_value'))}</td>"
            f"<td class=\"num\">{_fmt_percent(order.get('target_weight'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _checks(report: dict[str, Any] | None) -> str:
    checks = (((report or {}).get("validation") or {}).get("checks") or [])
    if not checks:
        return '<div class="empty">No rebalance validation report available</div>'
    items = []
    for check in checks:
        status = "ok" if check.get("passed") is True else "bad"
        items.append(
            f'<div class="check {status}">'
            f"<strong>{_esc(check.get('name'))}</strong>"
            f"<span>{_esc(check.get('message'))}</span>"
            "</div>"
        )
    return "\n".join(items)


def build_dashboard_html(
    *,
    live_signal: dict[str, Any],
    ops_health: dict[str, Any] | None = None,
    crash_risk: dict[str, Any] | None = None,
    rebalance_report: dict[str, Any] | None = None,
    holdings_snapshot: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> str:
    generated = generated_at or datetime.now().isoformat(timespec="seconds")
    target_weights = dict(live_signal.get("target_weights") or {})
    prices = dict(live_signal.get("latest_prices") or {})
    market_state = live_signal.get("market_state") or {}
    latest_features = live_signal.get("latest_features") or {}
    holdings = dict((holdings_snapshot or {}).get("current_shares") or {})
    cash = (holdings_snapshot or {}).get("cash")
    validation = (rebalance_report or {}).get("validation") or {}
    manual_approval = (rebalance_report or {}).get("manual_approval") or {}
    guard_reasons = live_signal.get("execution_guard_reasons") or []
    warning_reasons = live_signal.get("execution_warning_reasons") or []

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Group A+ Dashboard</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --ok: #18794e;
      --ok-bg: #e9f7ef;
      --warn: #9a6700;
      --warn-bg: #fff4d6;
      --bad: #b42318;
      --bad-bg: #ffe7e5;
      --accent: #2364aa;
      --accent-soft: #e8f1fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, "Noto Sans TC", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #fff;
      padding: 18px 24px;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 22px 24px 36px; }}
    h1 {{ font-size: 24px; margin: 0 0 4px; letter-spacing: 0; }}
    h2 {{ font-size: 15px; margin: 0 0 12px; letter-spacing: 0; }}
    .sub {{ color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .metric {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .pill {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: #fff;
      color: var(--muted);
      white-space: nowrap;
    }}
    .pill strong {{ color: var(--text); }}
    .pill.ok {{ background: var(--ok-bg); border-color: #b7e4cb; }}
    .pill.warn {{ background: var(--warn-bg); border-color: #f1d38a; }}
    .pill.bad {{ background: var(--bad-bg); border-color: #f4b4ae; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: middle; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 12px; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bar {{ height: 10px; background: #edf0f5; border-radius: 999px; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; background: var(--accent); }}
    .side {{ border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; }}
    .side.buy {{ color: var(--ok); background: var(--ok-bg); }}
    .side.sell {{ color: var(--bad); background: var(--bad-bg); }}
    .check {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin-bottom: 8px; }}
    .check strong {{ display: block; margin-bottom: 3px; }}
    .check span {{ color: var(--muted); }}
    .check.ok {{ border-color: #b7e4cb; background: var(--ok-bg); }}
    .check.bad {{ border-color: #f4b4ae; background: var(--bad-bg); }}
    .empty {{ color: var(--muted); padding: 12px 0; }}
    .list {{ margin: 0; padding-left: 18px; color: var(--muted); }}
    .list li {{ margin: 4px 0; }}
    @media (max-width: 920px) {{
      header {{ position: static; }}
      main {{ padding: 16px; }}
      .span-3, .span-4, .span-5, .span-7, .span-8 {{ grid-column: span 12; }}
      table {{ font-size: 13px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Group A+ Dashboard</h1>
    <div class="sub">Generated {_esc(generated)} | Read-only local view</div>
  </header>
  <main class="grid">
    <section class="panel span-12">
      <h2>Latest Strategy</h2>
      <div class="metric">{_esc(live_signal.get("strategy_id"))}</div>
      <div class="pills">
        {_pill("status", live_signal.get("strategy_status"))}
        {_pill("execution", "allowed" if live_signal.get("execution_allowed") else "blocked")}
        {_pill("data date", live_signal.get("actual_data_date"))}
        {_pill("regime", live_signal.get("execution_regime"))}
        {_pill("action", live_signal.get("action"))}
      </div>
    </section>
    <section class="panel span-3">
      <h2>Market State</h2>
      <div class="metric">{_esc(market_state.get("label_zh") or market_state.get("state"))}</div>
      <div class="sub">{_esc(market_state.get("allocation_bias"))}</div>
    </section>
    <section class="panel span-3">
      <h2>Ops Health</h2>
      <div class="metric">{_esc((ops_health or {}).get("status", "missing"))}</div>
      <div class="pills">{_pill("errors", len((ops_health or {}).get("errors") or []))}{_pill("warnings", len((ops_health or {}).get("warnings") or []))}</div>
    </section>
    <section class="panel span-3">
      <h2>Crash Risk</h2>
      <div class="metric">{_esc((crash_risk or {}).get("watch_level", "missing"))}</div>
      <div class="sub">{_esc("active" if (crash_risk or {}).get("alert_active") else "not active")}</div>
    </section>
    <section class="panel span-3">
      <h2>Holding Snapshot</h2>
      <div class="metric">{len(holdings)} tickers</div>
      <div class="sub">cash {_fmt_money(cash)}</div>
    </section>
    <section class="panel span-7">
      <h2>Target Weights</h2>
      <table>
        <thead><tr><th>Ticker</th><th>Weight</th><th class="num">Target</th><th class="num">Price</th></tr></thead>
        <tbody>{_weight_rows(target_weights, prices)}</tbody>
      </table>
    </section>
    <section class="panel span-5">
      <h2>Current Holdings</h2>
      <table>
        <thead><tr><th>Ticker</th><th class="num">Shares</th></tr></thead>
        <tbody>{_holding_rows(holdings)}</tbody>
      </table>
    </section>
    <section class="panel span-8">
      <h2>Rebalance Orders</h2>
      <table>
        <thead><tr><th>Ticker</th><th>Side</th><th class="num">Shares</th><th class="num">Price</th><th class="num">Value</th><th class="num">Target</th></tr></thead>
        <tbody>{_order_rows(rebalance_report)}</tbody>
      </table>
    </section>
    <section class="panel span-4">
      <h2>Risk Checks</h2>
      <div class="pills">
        {_pill("validation", "approved" if validation.get("approved") else "not approved" if validation else "missing")}
        {_pill("manual", "required" if manual_approval.get("required") else "not required" if manual_approval else "missing")}
      </div>
      <div style="margin-top:12px">{_checks(rebalance_report)}</div>
    </section>
    <section class="panel span-4">
      <h2>Execution Guard</h2>
      <ul class="list">
        {"".join(f"<li>{_esc(reason)}</li>" for reason in guard_reasons) or "<li>No blocking guard reasons</li>"}
      </ul>
    </section>
    <section class="panel span-4">
      <h2>Warnings</h2>
      <ul class="list">
        {"".join(f"<li>{_esc(reason)}</li>" for reason in warning_reasons) or "<li>No signal warnings</li>"}
      </ul>
    </section>
    <section class="panel span-4">
      <h2>Key Features</h2>
      <table>
        <tbody>
          <tr><td>ma_gap</td><td class="num">{_fmt_percent(latest_features.get("ma_gap"), 2)}</td></tr>
          <tr><td>drawdown</td><td class="num">{_fmt_percent(latest_features.get("drawdown"), 2)}</td></tr>
          <tr><td>risk_score</td><td class="num">{_esc(latest_features.get("total_risk_score", "-"))}</td></tr>
          <tr><td>tail_risk</td><td class="num">{_esc(latest_features.get("tail_risk_score", "-"))}</td></tr>
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def build_dashboard_from_files(
    *,
    signal_path: Path = LATEST_DIR / "live_signal.json",
    ops_health_path: Path = LATEST_DIR / "ops_health.json",
    crash_risk_path: Path = LATEST_DIR / "crash_risk_alert.json",
    rebalance_path: Path = DEFAULT_REBALANCE,
    holdings_path: Path = DEFAULT_HOLDINGS,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    signal = _load_json(signal_path)
    if signal.data is None:
        raise ValueError(f"live signal unavailable: {signal.path} ({signal.error})")
    ops_health = _load_json(ops_health_path)
    crash_risk = _load_json(crash_risk_path)
    rebalance = _load_json(rebalance_path)
    holdings = _load_json(holdings_path)
    html_text = build_dashboard_html(
        live_signal=signal.data,
        ops_health=ops_health.data,
        crash_risk=crash_risk.data,
        rebalance_report=rebalance.data,
        holdings_snapshot=holdings.data,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return {
        "output_path": str(output_path),
        "signal_path": str(signal_path),
        "ops_health_loaded": ops_health.data is not None,
        "crash_risk_loaded": crash_risk.data is not None,
        "rebalance_loaded": rebalance.data is not None,
        "holdings_loaded": holdings.data is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=str(LATEST_DIR / "live_signal.json"))
    parser.add_argument("--ops-health", default=str(LATEST_DIR / "ops_health.json"))
    parser.add_argument("--crash-risk", default=str(LATEST_DIR / "crash_risk_alert.json"))
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--holdings", default=str(DEFAULT_HOLDINGS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", action="store_true", help="Print machine-readable build result")
    args = parser.parse_args()

    result = build_dashboard_from_files(
        signal_path=Path(args.signal),
        ops_health_path=Path(args.ops_health),
        crash_risk_path=Path(args.crash_risk),
        rebalance_path=Path(args.rebalance),
        holdings_path=Path(args.holdings),
        output_path=Path(args.output),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"Dashboard: {result['output_path']}")
    print(f"Holdings loaded: {result['holdings_loaded']}")
    print(f"Rebalance loaded: {result['rebalance_loaded']}")


if __name__ == "__main__":
    main()
