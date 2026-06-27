#!/usr/bin/env python3
"""Run deterministic Research -> Debate -> Vote review for latest GroupA+."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from group_a_plus_review_agents import AgentReview, default_review_agents, final_vote
from group_a_plus_review_tools import PROJECT_ROOT, default_review_tools, resolve_path


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "review"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "review.json"


def _review_to_dict(review: AgentReview) -> dict[str, Any]:
    return {
        "agent": review.agent,
        "vote": review.vote,
        "severity": review.severity,
        "findings": review.findings,
        "evidence": review.evidence,
    }


def _load_context() -> dict[str, Any]:
    tools = default_review_tools()
    daily_result = tools.execute("load_latest_daily_status")
    compare_result = tools.execute("load_strategy_compare")
    baseline_result = tools.execute("load_baseline")
    errors = {
        "daily_status": daily_result.error,
        "strategy_compare": compare_result.error,
        "baseline": baseline_result.error,
    }
    active_errors = {key: value for key, value in errors.items() if value}
    if active_errors:
        raise RuntimeError(f"review context load failed: {active_errors}")
    return {
        "daily_status": daily_result.output["report"],
        "daily_status_pointer": daily_result.output["pointer"],
        "strategy_compare": compare_result.output["report"],
        "strategy_compare_pointer": compare_result.output["pointer"],
        "baseline": baseline_result.output,
    }


def _debate_summary(reviews: list[AgentReview]) -> list[dict[str, Any]]:
    summary = []
    for review in reviews:
        if review.vote == "block":
            stance = "blocking objection"
        elif review.vote == "caution":
            stance = "cautionary objection"
        elif review.vote == "shadow_only":
            stance = "research-only objection"
        else:
            stance = "supports approval"
        summary.append(
            {
                "agent": review.agent,
                "stance": stance,
                "key_point": review.findings[0] if review.findings else "",
            }
        )
    return summary


def _status_class(status: str) -> str:
    return status if status in {"approve", "caution", "block", "shadow_only"} else "neutral"


def _render_html(report: dict[str, Any]) -> str:
    decision = dict(report["vote"])
    decision_class = _status_class(str(decision["decision"]))
    reviews = report["research_reviews"]
    review_rows = []
    for review in reviews:
        findings = "<br>".join(escape(str(item)) for item in review.get("findings", []))
        vote = str(review.get("vote", ""))
        review_rows.append(
            "<tr>"
            f"<td>{escape(str(review.get('agent', '')))}</td>"
            f"<td><span class=\"pill {_status_class(vote)}\">{escape(vote)}</span></td>"
            f"<td>{findings}</td>"
            "</tr>"
        )

    debate_rows = []
    for item in report.get("debate", []):
        debate_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('agent', '')))}</td>"
            f"<td>{escape(str(item.get('stance', '')))}</td>"
            f"<td>{escape(str(item.get('key_point', '')))}</td>"
            "</tr>"
        )

    counts = decision.get("vote_counts", {})
    counts_html = " · ".join(f"{escape(str(k))}: {escape(str(v))}" for k, v in counts.items())
    profile = escape(str(report.get("profile", "")))
    generated = escape(str(report.get("generated_at", "")))
    daily_html = escape(str(report.get("inputs", {}).get("daily_html", "")))
    compare_html = escape(str(report.get("inputs", {}).get("compare_html", "")))

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GroupA+ Review Vote</title>
  <style>
    :root {{
      --bg:#f6f7f9; --panel:#fff; --text:#20242a; --muted:#68717e; --line:#d9dee7;
      --approve:#177245; --approve-bg:#e9f6ef; --caution:#9a5b00; --caution-bg:#fff3d6;
      --block:#a32020; --block-bg:#fde7e7; --shadow:#2457a6; --shadow-bg:#e8eef8;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"Noto Sans TC",sans-serif; background:var(--bg); color:var(--text); line-height:1.45; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:24px auto 42px; }}
    header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; padding:20px 0 18px; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:19px; letter-spacing:0; }}
    .subtle {{ color:var(--muted); font-size:14px; }}
    .decision {{ min-width:220px; padding:16px; background:var(--panel); border:1px solid var(--line); border-radius:8px; text-align:right; }}
    .decision .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    .decision .value {{ margin-top:4px; font-size:28px; font-weight:750; }}
    .decision .value.approve {{ color:var(--approve); }}
    .decision .value.caution {{ color:var(--caution); }}
    .decision .value.block {{ color:var(--block); }}
    .decision .value.shadow_only {{ color:var(--shadow); }}
    section {{ margin-top:18px; padding:18px; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:650; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; }}
    .pill {{ display:inline-block; min-width:78px; padding:3px 8px; border-radius:999px; font-size:12px; font-weight:700; text-align:center; }}
    .pill.approve {{ color:var(--approve); background:var(--approve-bg); }}
    .pill.caution {{ color:var(--caution); background:var(--caution-bg); }}
    .pill.block {{ color:var(--block); background:var(--block-bg); }}
    .pill.shadow_only {{ color:var(--shadow); background:var(--shadow-bg); }}
    .action {{ font-size:17px; font-weight:650; }}
    footer {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    @media (max-width: 820px) {{ header {{ display:block; }} .decision {{ margin-top:14px; text-align:left; }} main {{ width:calc(100% - 20px); }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>GroupA+ Review Vote</h1>
        <div class="subtle">Profile: <code>{profile}</code></div>
        <div class="subtle">Generated: {generated}</div>
      </div>
      <div class="decision">
        <div class="label">Final Decision</div>
        <div class="value {decision_class}">{escape(str(decision["decision"]))}</div>
      </div>
    </header>

    <section>
      <h2>Execution Gate</h2>
      <div class="action">{escape(str(decision.get("action", "")))}</div>
      <p class="subtle">Votes: {counts_html}</p>
    </section>

    <section>
      <h2>Research Agents</h2>
      <table>
        <thead><tr><th>Agent</th><th>Vote</th><th>Findings</th></tr></thead>
        <tbody>{''.join(review_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Debate Summary</h2>
      <table>
        <thead><tr><th>Agent</th><th>Stance</th><th>Key Point</th></tr></thead>
        <tbody>{''.join(debate_rows)}</tbody>
      </table>
    </section>

    <section>
      <h2>Linked Reports</h2>
      <p>Daily status: <code>{daily_html}</code></p>
      <p>Strategy compare: <code>{compare_html}</code></p>
    </section>

    <footer>Deterministic review layer only. It does not alter strategy targets. Not investment advice.</footer>
  </main>
</body>
</html>
"""


def _write_report(report: dict[str, Any], output_dir: Path, latest_pointer: Path) -> dict[str, str]:
    html_dir = output_dir / "html"
    json_dir = output_dir / "json"
    html_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(report["generated_at"]).replace("-", "").replace(":", "").replace("T", "_")
    profile = str(report.get("profile", "group_a_plus")).replace("/", "_")
    html_path = html_dir / f"review_{profile}_{stamp}.html"
    json_path = json_dir / f"review_{profile}_{stamp}.json"
    html_path.write_text(_render_html(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = {
        "report_type": "review_vote",
        "generated_at": report["generated_at"],
        "profile": report.get("profile"),
        "decision": report["vote"]["decision"],
        "html": str(html_path.relative_to(PROJECT_ROOT)),
        "json": str(json_path.relative_to(PROJECT_ROOT)),
    }
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"html": str(html_path), "json": str(json_path), "latest": str(latest_pointer)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LATEST))
    args = parser.parse_args()

    context = _load_context()
    reviews = [agent.review(context) for agent in default_review_agents()]
    vote = final_vote(reviews)
    daily_pointer = context["daily_status_pointer"]
    compare_pointer = context["strategy_compare_pointer"]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": context["baseline"].get("profile"),
        "phase": "research_debate_vote",
        "inputs": {
            "daily_status": daily_pointer.get("json"),
            "daily_html": daily_pointer.get("html"),
            "strategy_compare": compare_pointer.get("json"),
            "compare_html": compare_pointer.get("html"),
            "baseline": "GROUP_A_PLUS_CURRENT_BASELINE.json",
        },
        "research_reviews": [_review_to_dict(review) for review in reviews],
        "debate": _debate_summary(reviews),
        "vote": vote,
    }
    paths = _write_report(report, resolve_path(args.output_dir), resolve_path(args.latest_pointer))
    print(f"HTML: {paths['html']}")
    print(f"JSON: {paths['json']}")
    print(f"Latest: {paths['latest']}")
    print(f"Decision: {vote['decision']} - {vote['action']}")


if __name__ == "__main__":
    main()
