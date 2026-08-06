"""Read-only Fubon Neo account snapshot adapter for GroupA+ workflows.

This module only logs in, reads inventories/cash, and writes a broker-neutral
holdings JSON. It intentionally does not import or call any order-placement
API such as `sdk.stock.place_order`.
"""

from __future__ import annotations

import argparse
from contextlib import suppress
import gc
import getpass
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.portfolio.fubon_local_config import load_fubon_local_config, local_path_from_windows_path
from group_a_plus.portfolio.holding_snapshot import HoldingSnapshot


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "private" / "holdings_fubon_latest.json"
DEFAULT_SOURCE = "fubon_neo_read_only"
TPEX_CODES = {"00679B", "00751B"}


@dataclass(frozen=True)
class FubonCredentials:
    user_id: str
    password: str
    cert_path: str
    cert_password: str


PasswordProvider = Callable[[str], str]


def _manual_passwords(password_provider: PasswordProvider | None = None) -> tuple[str, str]:
    if password_provider is None and not sys.stdin.isatty():
        raise ValueError("Fubon password prompt requires an interactive terminal")
    provider = password_provider or getpass.getpass
    if password_provider is None:
        print("Password input is hidden. Type the password and press Enter.", file=sys.stderr)
    password = provider("Fubon account login password: ")
    cert_password = provider("Fubon certificate password (.p12/.pfx): ")
    if not password:
        raise ValueError("Fubon login password is required")
    if not cert_password:
        raise ValueError("Fubon certificate password is required")
    return password, cert_password


def load_fubon_credentials_from_env(
    env: Mapping[str, str] | None = None,
    *,
    password_provider: PasswordProvider | None = None,
) -> FubonCredentials:
    source = env or os.environ
    required = {
        "FUBON_ID": source.get("FUBON_ID") or source.get("FUBON_PERSONAL_ID"),
        "FUBON_CERT_PATH": source.get("FUBON_CERT_PATH"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        if "FUBON_ID" in missing:
            missing.remove("FUBON_ID")
            missing.append("FUBON_ID or FUBON_PERSONAL_ID")
        raise ValueError(f"missing required Fubon environment variables: {missing}")
    password, cert_password = _manual_passwords(password_provider)
    return FubonCredentials(
        user_id=str(required["FUBON_ID"]),
        password=password,
        cert_path=str(local_path_from_windows_path(str(required["FUBON_CERT_PATH"]))),
        cert_password=cert_password,
    )


def load_fubon_credentials(
    env: Mapping[str, str] | None = None,
    *,
    local_config_dir: str | Path | None = None,
    password_provider: PasswordProvider | None = None,
) -> FubonCredentials:
    source = env or os.environ
    env_values = {
        "FUBON_ID": source.get("FUBON_ID") or source.get("FUBON_PERSONAL_ID"),
        "FUBON_CERT_PATH": source.get("FUBON_CERT_PATH"),
    }
    if all(env_values.values()):
        return load_fubon_credentials_from_env(source, password_provider=password_provider)
    local_values = load_fubon_local_config(local_dir=local_config_dir, env=source)
    return load_fubon_credentials_from_env(local_values, password_provider=password_provider)


def _new_fubon_sdk() -> Any:
    from fubon_neo.sdk import FubonSDK

    return FubonSDK()


def _response_data(response: Any, *, operation: str) -> Any:
    if hasattr(response, "is_success") and response.is_success is False:
        raise RuntimeError(f"Fubon {operation} failed: {response}")
    if isinstance(response, dict):
        if response.get("is_success") is False:
            raise RuntimeError(f"Fubon {operation} failed: {response}")
        return response.get("data", response)
    return getattr(response, "data", response)


def _get_value(obj: Any, candidates: tuple[str, ...]) -> Any:
    if isinstance(obj, dict):
        for key in candidates:
            if key in obj:
                return obj[key]
        return None
    for key in candidates:
        if hasattr(obj, key):
            return getattr(obj, key)
    return None


def _normalize_ticker(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text:
        return None
    if "." in text:
        return text
    root = "".join(ch for ch in text if ch.isalnum())
    if not root:
        return None
    suffix = ".TWO" if root in TPEX_CODES else ".TW"
    return f"{root}{suffix}"


def _clean_float(raw: Any, *, field_name: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric: {raw!r}") from exc


def _parse_inventory_item(item: Any) -> tuple[str, float] | None:
    raw_symbol = _get_value(
        item,
        (
            "symbol",
            "stock_no",
            "stock_id",
            "stock",
            "ticker",
            "code",
        ),
    )
    ticker = _normalize_ticker(raw_symbol)
    if ticker is None:
        return None
    raw_qty = _get_value(
        item,
        (
            "quantity",
            "qty",
            "stock_qty",
            "today_qty",
            "now_qty",
            "available_qty",
            "tradable_qty",
            "shares",
        ),
    )
    if raw_qty is None:
        return None
    shares = _clean_float(raw_qty, field_name=f"inventory[{ticker}].quantity")
    if shares < 0:
        raise ValueError(f"inventory[{ticker}].quantity must be non-negative: {shares}")
    return ticker, shares


def parse_fubon_inventories(data: Any) -> dict[str, float]:
    items = data if isinstance(data, list) else list(data or [])
    holdings: dict[str, float] = {}
    for item in items:
        parsed = _parse_inventory_item(item)
        if parsed is None:
            continue
        ticker, shares = parsed
        holdings[ticker] = holdings.get(ticker, 0.0) + shares
    if not holdings:
        raise ValueError("no parseable Fubon inventories found")
    return holdings


def parse_fubon_cash(data: Any) -> float:
    raw_cash = _get_value(
        data,
        (
            "available_balance",
            "available_cash",
            "cash",
            "cash_balance",
            "bank_balance",
            "balance",
            "remain",
            "amount",
        ),
    )
    if raw_cash is None and isinstance(data, list) and data:
        raw_cash = _get_value(data[0], ("available_balance", "available_cash", "cash", "balance", "amount"))
    if raw_cash is None:
        raise ValueError(f"could not parse Fubon bank remain cash from: {data!r}")
    cash = _clean_float(raw_cash, field_name="bank_remain.cash")
    if cash < 0:
        raise ValueError(f"bank_remain.cash must be non-negative: {cash}")
    return cash


def fetch_fubon_holding_snapshot(
    *,
    sdk: Any | None = None,
    credentials: FubonCredentials | None = None,
    env: Mapping[str, str] | None = None,
    account_index: int = 0,
    as_of: str | None = None,
    local_config_dir: str | Path | None = None,
    password_provider: PasswordProvider | None = None,
    login_attempts: int = 3,
) -> HoldingSnapshot:
    owns_sdk = sdk is None
    resolved_sdk: Any | None = sdk
    attempts = 1 if credentials is not None else max(1, int(login_attempts))
    try:
        accounts: Any = None
        for attempt in range(1, attempts + 1):
            creds = credentials or load_fubon_credentials(
                env=env,
                local_config_dir=local_config_dir,
                password_provider=password_provider,
            )
            if resolved_sdk is None:
                resolved_sdk = _new_fubon_sdk()
            try:
                accounts_response = resolved_sdk.login(creds.user_id, creds.password, creds.cert_path, creds.cert_password)
                accounts = _response_data(accounts_response, operation="login")
                break
            except RuntimeError:
                if attempt >= attempts:
                    raise
                print(
                    f"Fubon login failed. Please try again ({attempt + 1}/{attempts}).",
                    file=sys.stderr,
                )
        if not isinstance(accounts, list) or not accounts:
            raise RuntimeError("Fubon login returned no accounts")
        account = accounts[account_index]

        inventories_response = resolved_sdk.accounting.inventories(account)
        bank_response = resolved_sdk.accounting.bank_remain(account)
        holdings = parse_fubon_inventories(_response_data(inventories_response, operation="inventories"))
        cash = parse_fubon_cash(_response_data(bank_response, operation="bank_remain"))
        account_id = str(_get_value(account, ("account", "account_id", "account_no", "branch_no")) or account_index)
        return HoldingSnapshot(
            current_shares=holdings,
            cash=cash,
            source=DEFAULT_SOURCE,
            account_id=account_id,
            as_of=as_of or datetime.now().date().isoformat(),
        )
    finally:
        if owns_sdk and resolved_sdk is not None and hasattr(resolved_sdk, "logout"):
            with suppress(Exception):
                resolved_sdk.logout()
            gc.collect()


def write_holding_snapshot(snapshot: HoldingSnapshot, path: Path = DEFAULT_OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_json_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output holdings JSON path")
    parser.add_argument("--account-index", type=int, default=0)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--local-config-dir", default=None, help="Local Fubon AES config dir, default C:\\fubon")
    args = parser.parse_args()

    try:
        snapshot = fetch_fubon_holding_snapshot(
            account_index=args.account_index,
            as_of=args.as_of,
            local_config_dir=args.local_config_dir,
        )
    except ValueError as exc:
        print(f"Fubon snapshot input error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Fubon snapshot error: {exc}", file=sys.stderr)
        return 2
    output = write_holding_snapshot(snapshot, Path(args.output))
    print(f"Fubon holdings snapshot: {output}")
    print(f"Account: {snapshot.account_id}")
    print(f"As of: {snapshot.as_of}")
    print(f"Holdings: {len(snapshot.current_shares)}")
    del snapshot
    gc.collect()
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
