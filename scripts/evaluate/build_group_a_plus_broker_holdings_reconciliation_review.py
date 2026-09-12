#!/usr/bin/env python3
"""Build a broker holdings reconciliation review for GroupA+.

The review compares a transaction-derived holdings sample with manually
confirmed holdings. It is a governance gate, not an order source.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_reconciliation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/broker_holdings_reconciliation/history"
DEFAULT_CONFIRMED = {"0050.TW": 2794, "00631L.TW": 500}
GROUP_A_PLUS_RECONCILIATION_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_confirmed(values: list[str]) -> dict[str, int]:
    confirmed = dict(DEFAULT_CONFIRMED)
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"confirmed holding must be TICKER=SHARES, got {raw!r}")
        ticker, shares = raw.split("=", 1)
        confirmed[ticker.strip()] = int(float(shares.strip()))
    return confirmed


def confirmed_from_authoritative_sample(sample_path: Path) -> dict[str, int]:
    sample = _load(sample_path)
    if sample.get("authoritative_broker_export") is not True:
        raise ValueError("confirmed-from-authoritative-sample requires authoritative_broker_export=true")
    latest = sample.get("latest_positions")
    if not isinstance(latest, dict) or not latest:
        raise ValueError("authoritative sample has no latest_positions")
    missing = [ticker for ticker in GROUP_A_PLUS_RECONCILIATION_TICKERS if ticker not in latest]
    if missing:
        raise ValueError(f"authoritative sample missing Group A+ tickers: {missing}")
    return {ticker: int(latest[ticker]) for ticker in GROUP_A_PLUS_RECONCILIATION_TICKERS}


def build_review(
    *,
    sample_path: Path,
    confirmed_holdings: dict[str, int],
    confirmed_holdings_source: str = "user_confirmed_in_chat",
) -> dict[str, Any]:
    sample = _load(sample_path)
    latest = sample.get("latest_positions") or {}
    negative_positions = sample.get("negative_positions") or {}
    rows: list[dict[str, Any]] = []
    for ticker, confirmed in sorted(confirmed_holdings.items()):
        sample_shares = latest.get(ticker)
        delta = None if sample_shares is None else int(sample_shares) - int(confirmed)
        rows.append(
            {
                "ticker": ticker,
                "confirmed_shares": int(confirmed),
                "sample_shares": sample_shares,
                "sample_minus_confirmed": delta,
                "matches_confirmed": delta == 0,
                "source": confirmed_holdings_source,
            }
        )

    matched = [row for row in rows if row["matches_confirmed"]]
    mismatched = [row for row in rows if row["matches_confirmed"] is False]
    missing = [row for row in rows if row["sample_shares"] is None]
    blockers: list[str] = []
    if not sample:
        blockers.append("broker_holdings_time_series_sample_missing")
    if sample.get("authoritative_broker_export") is not True:
        blockers.append("authoritative_broker_export_missing")
    if negative_positions:
        blockers.append("transaction_sample_has_negative_positions")
    if mismatched:
        blockers.append("confirmed_holdings_mismatch_transaction_sample")
    if missing:
        blockers.append("confirmed_holdings_missing_from_transaction_sample")

    coverage = sample.get("coverage") or {}
    reconciled = not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_holdings_reconciliation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "blocked" if blockers else "reconciled_for_manual_review",
        "policy": "reconciliation_governance_only_no_order_generation",
        "as_of": coverage.get("last_transaction_date") or "2026-07-17",
        "confirmed_holdings_source": confirmed_holdings_source,
        "comparison": rows,
        "summary": {
            "confirmed_ticker_count": len(rows),
            "matched_confirmed_count": len(matched),
            "mismatched_confirmed_count": len(mismatched),
            "missing_confirmed_count": len(missing),
            "negative_position_count": len(negative_positions),
            "authoritative_broker_export": sample.get("authoritative_broker_export") is True,
        },
        "blocking_reasons": blockers,
        "decision": {
            "broker_holdings_reconciled": reconciled,
            "can_generate_live_orders": reconciled,
            "allow_00631l_add": reconciled,
            "allow_00632r_open": False,
            "auto_rebalance_allowed": reconciled,
            "target_weight_change_allowed": reconciled,
            "keep_golden1_0531_unchanged": not reconciled,
            "summary": (
                "Broker holdings reconciled against an authoritative export; this gate "
                "does not create orders and downstream GIFT/pre-trade guards still apply."
                if reconciled
                else "Confirmed 00631L matches transaction-derived sample, but 0050 and other "
                "negative sample positions show the ledger is incomplete. Require an "
                "authoritative broker holdings/cash export before any order generation."
            ),
        },
        "inputs": {
            "sample": str(sample_path),
            "confirmed_holdings": confirmed_holdings,
        },
    }


def _history_path(history_dir: Path, review: dict[str, Any]) -> Path:
    return history_dir / f"{str(review.get('as_of') or 'latest').replace('-', '')}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review).write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    parser.add_argument("--confirmed", action="append", default=[])
    parser.add_argument(
        "--confirmed-from-authoritative-sample",
        action="store_true",
        help="Use latest_positions from an authoritative broker export sample as confirmed holdings.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    sample_path = _resolve(args.sample)
    if args.confirmed_from_authoritative_sample:
        confirmed = confirmed_from_authoritative_sample(sample_path)
        confirmed_source = "authoritative_broker_export_latest_positions"
    else:
        confirmed = _parse_confirmed(args.confirmed)
        confirmed_source = "user_confirmed_in_chat"
    review = build_review(
        sample_path=sample_path,
        confirmed_holdings=confirmed,
        confirmed_holdings_source=confirmed_source,
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output, history_dir)
    print(f"Broker holdings reconciliation review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review)}")
    print(json.dumps({"status": review["status"], **review["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
