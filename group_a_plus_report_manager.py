#!/usr/bin/env python3
"""Report manager for GroupA+ operational outputs."""

from __future__ import annotations

import json
from html import escape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent


class GroupAPlusReportManager:
    """Store GroupA+ reports with stable paths and metadata sidecars."""

    def __init__(self, base_dir: str | Path = "report/group_a_plus") -> None:
        base_path = Path(base_dir)
        if not base_path.is_absolute():
            base_path = PROJECT_ROOT / base_path
        self.base_dir = base_path
        self.report_types = {
            "daily": {
                "html_dir": self.base_dir / "daily" / "html",
                "json_dir": self.base_dir / "daily" / "json",
                "md_dir": self.base_dir / "daily" / "md",
                "meta_dir": self.base_dir / "daily" / "meta",
            },
        }
        self.latest_dir = self.base_dir / "latest"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for dirs in self.report_types.values():
            for directory in dirs.values():
                directory.mkdir(parents=True, exist_ok=True)
        self.latest_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_slug(value: str) -> str:
        clean = []
        for char in str(value):
            if char.isalnum() or char in {"_", "-"}:
                clean.append(char)
            else:
                clean.append("_")
        return "".join(clean).strip("_") or "unknown"

    def _filename_stem(self, report_type: str, profile: str, report_date: str, generated_at: str | None = None) -> str:
        timestamp = generated_at or datetime.now().isoformat(timespec="seconds")
        timestamp = timestamp.replace("-", "").replace(":", "").replace("T", "_")
        return f"{report_type}_{self._safe_slug(profile)}_{report_date.replace('-', '')}_{timestamp}"

    @staticmethod
    def _status_class(status: Any) -> str:
        value = str(status or "").lower()
        if value == "ok":
            return "ok"
        if value == "warn":
            return "warn"
        if value == "block":
            return "block"
        return "neutral"

    @staticmethod
    def render_daily_status_html(report: dict[str, Any]) -> str:
        """Render a self-contained HTML daily status report."""

        status = str(report.get("overall_status", "unknown"))
        status_class = GroupAPlusReportManager._status_class(status)
        profile = escape(str(report.get("profile", "")))
        generated_at = escape(str(report.get("generated_at", "")))
        check_date = escape(str(report.get("check_date", "")))
        signal = dict(report.get("signal", {}) or {})
        group_a_plus = dict(report.get("group_a_plus", {}) or {})
        source_paths = dict(report.get("source_paths", {}) or {})
        target_shares = dict(group_a_plus.get("target_shares", {}) or {})

        checks_rows = []
        for check in report.get("checks", []):
            check_status = str(check.get("status", ""))
            checks_rows.append(
                "<tr>"
                f"<td>{escape(str(check.get('name', '')))}</td>"
                f"<td><span class=\"pill {GroupAPlusReportManager._status_class(check_status)}\">{escape(check_status)}</span></td>"
                f"<td>{escape(str(check.get('detail', '')))}</td>"
                "</tr>"
            )

        share_rows = []
        for ticker, shares in target_shares.items():
            share_rows.append(
                f"<tr><td>{escape(str(ticker))}</td><td class=\"num\">{escape(str(shares))}</td></tr>"
            )

        source_rows = []
        for name, path in source_paths.items():
            source_rows.append(
                f"<tr><td>{escape(str(name))}</td><td><code>{escape(str(path))}</code></td></tr>"
            )

        overlay_weight = float(group_a_plus.get("overlay_00679b_weight", 0.0) or 0.0)
        cash_after_cost = float(group_a_plus.get("cash_after_cost", 0.0) or 0.0)

        return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GroupA+ Daily Status - {profile}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #67717f;
      --line: #d9dee7;
      --ok: #177245;
      --ok-bg: #e9f6ef;
      --warn: #9a5b00;
      --warn-bg: #fff3d6;
      --block: #a32020;
      --block-bg: #fde7e7;
      --accent: #2457a6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, "Noto Sans TC", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 24px auto 40px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      padding: 22px 0 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .subtle {{ color: var(--muted); font-size: 14px; }}
    .status-card {{
      min-width: 180px;
      padding: 14px 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      text-align: right;
    }}
    .status-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .status-value {{ margin-top: 4px; font-size: 26px; font-weight: 700; }}
    .status-value.ok {{ color: var(--ok); }}
    .status-value.warn {{ color: var(--warn); }}
    .status-value.block {{ color: var(--block); }}
    section {{
      margin-top: 18px;
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric {{
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfe;
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ margin-top: 4px; font-size: 18px; font-weight: 650; overflow-wrap: anywhere; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .pill {{
      display: inline-block;
      min-width: 52px;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-align: center;
    }}
    .pill.ok {{ color: var(--ok); background: var(--ok-bg); }}
    .pill.warn {{ color: var(--warn); background: var(--warn-bg); }}
    .pill.block {{ color: var(--block); background: var(--block-bg); }}
    .pill.neutral {{ color: var(--accent); background: #e8eef8; }}
    footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 820px) {{
      header {{ display: block; }}
      .status-card {{ margin-top: 14px; text-align: left; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 520px) {{
      main {{ width: min(100% - 20px, 1120px); margin-top: 12px; }}
      .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 22px; }}
      section {{ padding: 14px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>GroupA+ Daily Status</h1>
        <div class="subtle">Profile: <code>{profile}</code></div>
        <div class="subtle">Generated: {generated_at} · Check date: {check_date}</div>
      </div>
      <div class="status-card">
        <div class="status-label">Overall</div>
        <div class="status-value {status_class}">{escape(status)}</div>
      </div>
    </header>

    <section>
      <h2>Key Metrics</h2>
      <div class="grid">
        <div class="metric"><div class="label">Signal</div><div class="value">{escape(str(signal.get("signal_status", "")))}</div></div>
        <div class="metric"><div class="label">Reason</div><div class="value">{escape(str(signal.get("signal_reason", "")))}</div></div>
        <div class="metric"><div class="label">Overlay Regime</div><div class="value">{escape(str(group_a_plus.get("overlay_regime", "")))}</div></div>
        <div class="metric"><div class="label">Cash After Cost</div><div class="value">{cash_after_cost:,.0f}</div></div>
        <div class="metric"><div class="label">Actual Data Date</div><div class="value">{escape(str(signal.get("actual_data_date", "")))}</div></div>
        <div class="metric"><div class="label">Business Stale Days</div><div class="value">{escape(str(signal.get("business_stale_days", "")))}</div></div>
        <div class="metric"><div class="label">Calendar Stale Days</div><div class="value">{escape(str(signal.get("calendar_stale_days", "")))}</div></div>
        <div class="metric"><div class="label">00679B Weight</div><div class="value">{overlay_weight:.2%}</div></div>
      </div>
    </section>

    <section>
      <h2>Checks</h2>
      <table>
        <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>{''.join(checks_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Target Shares</h2>
      <table>
        <thead><tr><th>Ticker</th><th class="num">Target Shares</th></tr></thead>
        <tbody>{''.join(share_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Source Files</h2>
      <table>
        <thead><tr><th>Source</th><th>Path</th></tr></thead>
        <tbody>{''.join(source_rows)}</tbody>
      </table>
    </section>

    <footer>For operational review only. This report is not investment advice.</footer>
  </main>
</body>
</html>
"""

    def save_daily_status(
        self,
        report: dict[str, Any],
        *,
        markdown: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Save a daily status report as JSON, Markdown, metadata, and latest pointer."""

        dirs = self.report_types["daily"]
        profile = str(report.get("profile") or "group_a_plus")
        report_date = str(report.get("check_date") or datetime.now().strftime("%Y-%m-%d"))
        generated_at = str(report.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
        stem = self._filename_stem("daily_status", profile, report_date, generated_at)

        json_path = dirs["json_dir"] / f"{stem}.json"
        md_path = dirs["md_dir"] / f"{stem}.md"
        html_path = dirs["html_dir"] / f"{stem}.html"
        meta_path = dirs["meta_dir"] / f"{stem}.meta.json"

        json_text = json.dumps(report, ensure_ascii=False, indent=2)
        html_text = self.render_daily_status_html(report)
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(html_text, encoding="utf-8")

        meta = {
            "report_type": "daily_status",
            "profile": profile,
            "check_date": report_date,
            "generated_at": generated_at,
            "overall_status": report.get("overall_status"),
            "html_path": str(html_path.relative_to(PROJECT_ROOT)),
            "json_path": str(json_path.relative_to(PROJECT_ROOT)),
            "markdown_path": str(md_path.relative_to(PROJECT_ROOT)),
            "html_size_bytes": len(html_text.encode("utf-8")),
            "json_size_bytes": len(json_text.encode("utf-8")),
            "markdown_size_bytes": len(markdown.encode("utf-8")),
            **(metadata or {}),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        latest = {
            "report_type": "daily_status",
            "profile": profile,
            "check_date": report_date,
            "generated_at": generated_at,
            "overall_status": report.get("overall_status"),
            "html": str(html_path.relative_to(PROJECT_ROOT)),
            "json": str(json_path.relative_to(PROJECT_ROOT)),
            "markdown": str(md_path.relative_to(PROJECT_ROOT)),
            "metadata": str(meta_path.relative_to(PROJECT_ROOT)),
        }
        latest_path = self.latest_dir / "daily_status.json"
        latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "html": str(html_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "metadata": str(meta_path),
            "latest": str(latest_path),
        }

    def list_reports(self, report_type: str = "daily", limit: int = 20) -> list[dict[str, Any]]:
        dirs = self.report_types.get(report_type)
        if not dirs:
            raise ValueError(f"Unknown report type: {report_type}")
        reports: list[dict[str, Any]] = []
        for meta_path in dirs["meta_dir"].glob("*.meta.json"):
            try:
                reports.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        reports.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
        return reports[:limit]

    def cleanup_old_reports(self, retention_days: int = 30) -> dict[str, int]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        deleted = 0
        saved_bytes = 0
        for dirs in self.report_types.values():
            for directory in dirs.values():
                for path in directory.glob("*"):
                    if not path.is_file():
                        continue
                    if datetime.fromtimestamp(path.stat().st_mtime) >= cutoff:
                        continue
                    saved_bytes += path.stat().st_size
                    path.unlink()
                    deleted += 1
        return {"deleted_files": deleted, "saved_bytes": saved_bytes}
