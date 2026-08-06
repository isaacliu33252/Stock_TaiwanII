"""Build a broker-neutral GroupA+ rebalance audit report from JSON inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.portfolio.holding_snapshot import (
    HoldingSnapshot,
    load_holding_snapshot_excel,
    load_holding_snapshot_json,
)
from group_a_plus.portfolio.price_loader import load_prices_from_ohlcv_freshness, load_prices_json
from group_a_plus.portfolio.rebalance_audit import (
    DEFAULT_LATEST_REBALANCE_AUDIT,
    build_rebalance_audit_report,
    write_rebalance_audit_report,
)
from group_a_plus.portfolio.rebalance_plan import RebalanceConfig, build_rebalance_plan
from group_a_plus.portfolio.rebalance_validation import RebalanceRiskConfig, validate_rebalance_plan


DEFAULT_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"


def _load_signal(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise ValueError("signal JSON must be an object")


def build_report_from_files(
    *,
    signal_path: Path,
    holdings_path: Path | None = None,
    holdings_excel_path: Path | None = None,
    latest_output: Path = DEFAULT_LATEST_REBALANCE_AUDIT,
    dated_output: Path | None = None,
    cash: float | None = None,
    excel_sheet: str | None = None,
    excel_row_label: str = "即時庫存",
    min_trade_value: float = 1_000.0,
    default_lot_size: int = 1,
    max_order_value: float = 250_000.0,
    max_total_buy_value: float = 500_000.0,
    max_turnover_ratio: float = 0.50,
    max_leveraged_target_weight: float = 0.25,
    prices_path: Path | None = None,
    price_freshness_path: Path | None = None,
) -> dict:
    signal = _load_signal(signal_path)
    snapshot = _load_snapshot(
        holdings_path=holdings_path,
        holdings_excel_path=holdings_excel_path,
        cash=cash,
        excel_sheet=excel_sheet,
        excel_row_label=excel_row_label,
    )
    prices = _load_prices(signal=signal, prices_path=prices_path, price_freshness_path=price_freshness_path)
    plan = build_rebalance_plan(
        signal,
        current_shares=snapshot.current_shares,
        cash=snapshot.cash,
        prices=prices,
        config=RebalanceConfig(
            min_trade_value=min_trade_value,
            default_lot_size=default_lot_size,
        ),
    )
    validation = validate_rebalance_plan(
        plan,
        daily_signal=signal,
        config=RebalanceRiskConfig(
            max_order_value=max_order_value,
            max_total_buy_value=max_total_buy_value,
            max_turnover_ratio=max_turnover_ratio,
            max_leveraged_target_weight=max_leveraged_target_weight,
        ),
    )
    report = build_rebalance_audit_report(
        daily_signal=signal,
        plan=plan,
        validation=validation,
        current_shares=snapshot.current_shares,
        cash=snapshot.cash,
    )
    report["holding_snapshot"] = snapshot.to_json_dict()
    paths = write_rebalance_audit_report(report, latest_path=latest_output, dated_path=dated_output)
    return {
        "report": report,
        "paths": paths,
    }


def _load_prices(
    *,
    signal: dict,
    prices_path: Path | None,
    price_freshness_path: Path | None,
) -> dict[str, float] | None:
    if prices_path is None and price_freshness_path is None:
        return None
    prices = {str(ticker): float(price) for ticker, price in dict(signal.get("latest_prices") or {}).items()}
    if price_freshness_path is not None:
        prices.update(load_prices_from_ohlcv_freshness(price_freshness_path))
    if prices_path is not None:
        prices.update(load_prices_json(prices_path))
    return prices


def _load_snapshot(
    *,
    holdings_path: Path | None,
    holdings_excel_path: Path | None,
    cash: float | None,
    excel_sheet: str | None,
    excel_row_label: str,
) -> HoldingSnapshot:
    if holdings_path is not None and holdings_excel_path is not None:
        raise ValueError("pass only one of holdings_path or holdings_excel_path")
    if holdings_path is None and holdings_excel_path is None:
        raise ValueError("pass holdings_path or holdings_excel_path")
    if holdings_path is not None:
        return load_holding_snapshot_json(holdings_path)
    assert holdings_excel_path is not None
    return load_holding_snapshot_excel(
        holdings_excel_path,
        cash=cash,
        sheet=excel_sheet,
        row_label=excel_row_label,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=str(DEFAULT_SIGNAL), help="Path to GroupA+ live_signal.json")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--holdings", help="Path to holdings JSON")
    source.add_argument("--holdings-excel", help="Path to holdings Excel workbook")
    parser.add_argument("--cash", type=float, default=None, help="Cash value for Excel holdings when workbook has no cash row")
    parser.add_argument("--excel-sheet", default=None, help="Optional Excel sheet name")
    parser.add_argument("--excel-row-label", default="即時庫存", help="Horizontal Excel holdings row label")
    parser.add_argument("--output", default=str(DEFAULT_LATEST_REBALANCE_AUDIT), help="Latest audit report output path")
    parser.add_argument("--dated-output", default=None, help="Optional dated audit report output path")
    parser.add_argument("--min-trade-value", type=float, default=1_000.0)
    parser.add_argument("--default-lot-size", type=int, default=1)
    parser.add_argument("--max-order-value", type=float, default=250_000.0)
    parser.add_argument("--max-total-buy-value", type=float, default=500_000.0)
    parser.add_argument("--max-turnover-ratio", type=float, default=0.50)
    parser.add_argument("--max-leveraged-target-weight", type=float, default=0.25)
    parser.add_argument("--prices", default=None, help="Optional latest_prices JSON/object override")
    parser.add_argument("--price-freshness", default=None, help="Optional ohlcv_freshness JSON for local cache prices")
    args = parser.parse_args()

    result = build_report_from_files(
        signal_path=Path(args.signal),
        holdings_path=Path(args.holdings) if args.holdings else None,
        holdings_excel_path=Path(args.holdings_excel) if args.holdings_excel else None,
        latest_output=Path(args.output),
        dated_output=Path(args.dated_output) if args.dated_output else None,
        cash=args.cash,
        excel_sheet=args.excel_sheet,
        excel_row_label=args.excel_row_label,
        min_trade_value=args.min_trade_value,
        default_lot_size=args.default_lot_size,
        max_order_value=args.max_order_value,
        max_total_buy_value=args.max_total_buy_value,
        max_turnover_ratio=args.max_turnover_ratio,
        max_leveraged_target_weight=args.max_leveraged_target_weight,
        prices_path=Path(args.prices) if args.prices else None,
        price_freshness_path=Path(args.price_freshness) if args.price_freshness else None,
    )
    report = result["report"]
    paths = result["paths"]
    print(f"Rebalance audit latest: {paths['latest_path']}")
    print(f"Rebalance audit dated: {paths['dated_path']}")
    print(f"Approved by validation: {report['validation']['approved']}")
    print(f"Manual approval required: {report['manual_approval']['required']}")


if __name__ == "__main__":
    main()
