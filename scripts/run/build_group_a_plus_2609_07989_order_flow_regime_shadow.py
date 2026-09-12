#!/usr/bin/env python3
"""Build the 2609.07989 order-flow regime advisory shadow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.order_flow_regime_shadow import (  # noqa: E402
    DEFAULT_BUCKET,
    DEFAULT_TICKERS,
    DEFAULT_WINDOW,
    DEFAULT_Z_THRESHOLD,
    append_order_flow_regime_shadow_log,
    build_order_flow_regime_shadow_from_csv,
)


DEFAULT_INPUT = PROJECT_ROOT / "results" / "intraday_signed_order_flow_latest.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07989_order_flow_regime_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07989_order_flow_regime_shadow.md"
DEFAULT_LOG = PROJECT_ROOT / "results" / "2609_07989_order_flow_regime_shadow_log.jsonl"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 2609.07989 Order-Flow Regime Shadow",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- status: `{payload.get('status')}`",
        f"- policy: `{payload.get('policy')}`",
        f"- advisory_state: `{payload.get('advisory_state', 'n/a')}`",
        f"- as_of: `{payload.get('as_of')}`",
        f"- input: `{payload.get('input_path')}`",
        f"- reason: `{payload.get('reason')}`",
        "",
        "## Decision",
        "",
    ]
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    for key in sorted(decision):
        lines.append(f"- {key}: `{decision[key]}`")
    lines.extend(
        [
            "",
            "## Stress Tickers",
            "",
        ]
    )
    stress = payload.get("stress_tickers") or []
    lines.append("- " + (", ".join(f"`{ticker}`" for ticker in stress) if stress else "none"))
    lines.extend(
        [
            "",
            "## Ticker Details",
            "",
            "| ticker | status | latest direction | z | change proxy | break |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    by_ticker = payload.get("by_ticker") if isinstance(payload.get("by_ticker"), dict) else {}
    for ticker, detail in by_ticker.items():
        latest = detail.get("latest") if isinstance(detail, dict) else {}
        latest = latest if isinstance(latest, dict) else {}
        lines.append(
            "| "
            f"`{ticker}` | `{detail.get('status')}` | `{latest.get('flow_direction')}` | "
            f"`{latest.get('z_score')}` | `{latest.get('change_probability_proxy')}` | "
            f"`{latest.get('regime_break_reference')}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This shadow requires signed intraday transaction/order-flow data.",
            "- Daily OHLCV proxies are intentionally rejected for this paper.",
            "- This report is advisory only and cannot change latest strategy target weights or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--z-threshold", type=float, default=DEFAULT_Z_THRESHOLD)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    input_path = _resolve(args.input)
    output_path = _resolve(args.output)
    markdown_path = _resolve(args.markdown)
    log_path = _resolve(args.log)
    tickers = tuple(ticker.strip() for ticker in args.tickers.split(",") if ticker.strip())

    payload = build_order_flow_regime_shadow_from_csv(
        input_path,
        tickers=tickers,
        bucket=args.bucket,
        window=args.window,
        z_threshold=args.z_threshold,
    )
    payload["input_path"] = str(input_path)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    if not args.no_log:
        append_order_flow_regime_shadow_log(log_path, payload)
    print(f"Order-flow regime shadow JSON: {output_path}")
    print(f"Order-flow regime shadow Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
