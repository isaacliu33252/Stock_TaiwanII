#!/usr/bin/env python3
"""Fubon SDK bridge helpers for signal validation and order preview."""

from __future__ import annotations

import argparse
import csv
import getpass
import importlib.metadata
import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"

ENV_PERSONAL_ID = "FUBON_PERSONAL_ID"
ENV_CERT_PATH = "FUBON_CERT_PATH"
ENV_ACCOUNT = "FUBON_ACCOUNT"


@dataclass
class CredentialStatus:
    personal_id: str | None
    cert_path: str | None
    cert_path_exists: bool
    account: str | None

    @property
    def ready_for_login(self) -> bool:
        return bool(
            self.personal_id
            and self.cert_path
            and self.cert_path_exists
        )


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_input_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_symbol(ticker: str) -> str:
    return str(ticker).split(".", 1)[0]


def _load_credential_status() -> CredentialStatus:
    cert_path = os.getenv(ENV_CERT_PATH)
    return CredentialStatus(
        personal_id=os.getenv(ENV_PERSONAL_ID),
        cert_path=cert_path,
        cert_path_exists=bool(cert_path and Path(cert_path).expanduser().exists()),
        account=os.getenv(ENV_ACCOUNT),
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _require_signal_fields(signal: dict[str, Any]) -> None:
    required = ["group", "signal_status", "signal_reason", "current_shares", "target_shares", "latest_prices"]
    missing = [key for key in required if key not in signal]
    if missing:
        raise ValueError(f"Signal JSON missing fields: {', '.join(missing)}")


def _distributed_abs_quantity(total_abs: int, steps: int, step_index: int) -> int:
    if step_index < 0:
        return 0
    base = total_abs // steps
    remainder = total_abs % steps
    return base * step_index + min(remainder, step_index)


def _build_signal_order_plan(signal: dict[str, Any], steps: int, step_index: int) -> dict[str, Any]:
    if steps < 1:
        raise ValueError("--steps must be >= 1")
    if step_index < 1 or step_index > steps:
        raise ValueError("--step-index must be between 1 and --steps")

    _require_signal_fields(signal)

    current_shares = signal.get("current_shares", {}) or {}
    target_shares = signal.get("target_shares", {}) or {}
    latest_prices = signal.get("latest_prices", {}) or {}
    tickers = sorted(set(current_shares) | set(target_shares))

    orders: list[dict[str, Any]] = []
    total_estimated_value = 0.0

    for ticker in tickers:
        current = int(round(float(current_shares.get(ticker, 0) or 0)))
        target = int(round(float(target_shares.get(ticker, 0) or 0)))
        delta = target - current
        if delta == 0:
            continue

        sign = 1 if delta > 0 else -1
        total_abs = abs(delta)
        step_qty_abs = _distributed_abs_quantity(total_abs, steps, step_index) - _distributed_abs_quantity(
            total_abs, steps, step_index - 1
        )
        step_qty = sign * step_qty_abs
        if step_qty == 0:
            continue

        step_start_shares = current + sign * _distributed_abs_quantity(total_abs, steps, step_index - 1)
        step_end_shares = step_start_shares + step_qty
        abs_qty = abs(step_qty)
        latest_price = float(latest_prices.get(ticker, 0.0) or 0.0)
        estimated_value = abs_qty * latest_price
        total_estimated_value += estimated_value

        board_lot_qty = (abs_qty // 1000) * 1000
        odd_lot_qty = abs_qty % 1000

        orders.append(
            {
                "ticker": ticker,
                "symbol": _normalize_symbol(ticker),
                "side": "BUY" if step_qty > 0 else "SELL",
                "step_quantity": abs_qty,
                "step_quantity_signed": step_qty,
                "current_shares": current,
                "target_shares": target,
                "step_start_shares": step_start_shares,
                "step_end_shares": step_end_shares,
                "board_lot_quantity": board_lot_qty,
                "odd_lot_quantity": odd_lot_qty,
                "latest_price": latest_price,
                "estimated_value": estimated_value,
                "price_type": "Reference",
                "time_in_force": "ROD",
                "order_type": "Stock",
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_json": signal.get("_source_path"),
        "group": signal.get("group"),
        "signal_status": signal.get("signal_status"),
        "signal_reason": signal.get("signal_reason"),
        "actual_data_date": signal.get("actual_data_date"),
        "requested_as_of_date": signal.get("requested_as_of_date"),
        "steps": steps,
        "step_index": step_index,
        "current_total_portfolio_value": signal.get("current_total_portfolio_value"),
        "target_cash_weight": signal.get("target_cash_weight"),
        "orders": orders,
        "total_estimated_value": total_estimated_value,
    }


def _flatten_order_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in plan.get("orders", []):
        for market_type, quantity_key in (("Common", "board_lot_quantity"), ("IntradayOdd", "odd_lot_quantity")):
            quantity = int(item.get(quantity_key, 0) or 0)
            if quantity <= 0:
                continue
            rows.append(
                {
                    "ticker": item["ticker"],
                    "symbol": item["symbol"],
                    "side": item["side"],
                    "quantity": quantity,
                    "market_type": market_type,
                    "price_type": item["price_type"],
                    "time_in_force": item["time_in_force"],
                    "order_type": item["order_type"],
                    "latest_price": item["latest_price"],
                    "estimated_value": round(quantity * float(item["latest_price"]), 2),
                    "step_start_shares": item["step_start_shares"],
                    "step_end_shares": item["step_end_shares"],
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "ticker",
        "symbol",
        "side",
        "quantity",
        "market_type",
        "price_type",
        "time_in_force",
        "order_type",
        "latest_price",
        "estimated_value",
        "step_start_shares",
        "step_end_shares",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _object_to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _object_to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_object_to_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _object_to_jsonable(item) for key, item in vars(value).items()}

    result: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        try:
            item = getattr(value, key)
        except Exception:
            continue
        if callable(item):
            continue
        result[key] = _object_to_jsonable(item)
    return result or repr(value)


def cmd_check(args: argparse.Namespace) -> int:
    spec = importlib.util.find_spec("fubon_neo")
    version = None
    if spec is not None:
        try:
            version = importlib.metadata.version("fubon_neo")
        except importlib.metadata.PackageNotFoundError:
            version = None

    credentials = _load_credential_status()
    report: dict[str, Any] = {
        "fubon_neo_importable": spec is not None,
        "fubon_neo_version": version,
        "fubon_neo_origin": None if spec is None else spec.origin,
        "credentials": {
            "personal_id_present": bool(credentials.personal_id),
            "cert_path": credentials.cert_path,
            "cert_path_exists": credentials.cert_path_exists,
            "account": credentials.account,
            "ready_for_login": credentials.ready_for_login,
            "passwords": "manual_prompt_required_for_login_check",
        },
        "runtime_probe_skipped": True,
        "runtime_probe_note": (
            "This command does not instantiate FubonSDK(). A prior WSL/Linux probe crashed, so login should be "
            "tested explicitly with `login-check`, ideally in your broker-supported runtime."
        ),
    }

    if args.signal_json:
        signal_path = _resolve_input_path(args.signal_json)
        signal = _load_json(signal_path)
        signal["_source_path"] = str(signal_path)
        _require_signal_fields(signal)
        report["signal"] = {
            "path": str(signal_path),
            "group": signal.get("group"),
            "signal_status": signal.get("signal_status"),
            "signal_reason": signal.get("signal_reason"),
            "actual_data_date": signal.get("actual_data_date"),
            "current_shares": signal.get("current_shares"),
            "target_shares": signal.get("target_shares"),
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))
    if args.require_credentials and not credentials.ready_for_login:
        return 1
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    signal_path = _resolve_input_path(args.signal_json)
    signal = _load_json(signal_path)
    signal["_source_path"] = str(signal_path)

    plan = _build_signal_order_plan(signal=signal, steps=args.steps, step_index=args.step_index)
    rows = _flatten_order_rows(plan)

    prefix = args.output_prefix or f"fubon_order_preview_{_timestamp()}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    csv_path = RESULTS_DIR / f"{prefix}.csv"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    _write_csv(csv_path, rows)

    print(f"Signal: {signal_path}")
    print(f"Status: {plan['signal_status']} / {plan['signal_reason']}")
    print(f"Step:   {plan['step_index']} / {plan['steps']}")
    print(f"Orders: {len(plan['orders'])} tickers, {len(rows)} market rows")
    print(f"Value:  {plan['total_estimated_value']:.2f}")
    print(f"JSON:   {json_path}")
    print(f"CSV:    {csv_path}")
    return 0


def cmd_login_check(args: argparse.Namespace) -> int:
    from fubon_neo.sdk import FubonSDK

    personal_id = args.personal_id or os.getenv(ENV_PERSONAL_ID)
    cert_path_raw = args.cert_path or os.getenv(ENV_CERT_PATH)

    missing = []
    if not personal_id:
        missing.append(ENV_PERSONAL_ID)
    if not cert_path_raw:
        missing.append(ENV_CERT_PATH)
    if missing:
        raise SystemExit(f"Missing credential inputs: {', '.join(missing)}")

    cert_path = Path(cert_path_raw).expanduser()
    if not cert_path.exists():
        raise SystemExit(f"Certificate not found: {cert_path}")
    password = getpass.getpass("Fubon login password: ")
    cert_password = getpass.getpass("Fubon certificate password: ")
    if not password:
        raise SystemExit("Fubon login password is required")
    if not cert_password:
        raise SystemExit("Fubon certificate password is required")

    sdk = FubonSDK()
    try:
        response = sdk.login(str(personal_id), str(password), str(cert_path), str(cert_password))
        payload = _object_to_jsonable(response)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        try:
            sdk.logout()
        except Exception:
            pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fubon SDK enablement helpers for this project.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Check local SDK availability and credential readiness.")
    check_parser.add_argument("--signal-json", help="Optional signal JSON to validate against the bridge.")
    check_parser.add_argument(
        "--require-credentials",
        action="store_true",
        help="Exit with code 1 when login credentials are incomplete.",
    )
    check_parser.set_defaults(func=cmd_check)

    preview_parser = subparsers.add_parser("preview-orders", help="Convert a signal JSON into Fubon order previews.")
    preview_parser.add_argument("--signal-json", required=True, help="Path to signal_group_*.json")
    preview_parser.add_argument("--steps", type=int, default=1, help="Total number of build steps.")
    preview_parser.add_argument("--step-index", type=int, default=1, help="Which step to preview, 1-based.")
    preview_parser.add_argument(
        "--output-prefix",
        help="Optional output filename prefix under results/. Default uses timestamp.",
    )
    preview_parser.set_defaults(func=cmd_preview)

    login_parser = subparsers.add_parser(
        "login-check",
        help="Attempt Fubon login and print account payload. Do not use this in an unsupported runtime.",
    )
    login_parser.add_argument("--personal-id", help=f"Override {ENV_PERSONAL_ID}")
    login_parser.add_argument("--cert-path", help=f"Override {ENV_CERT_PATH}")
    login_parser.set_defaults(func=cmd_login_check)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
