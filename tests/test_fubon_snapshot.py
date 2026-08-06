from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from group_a_plus.portfolio.fubon_snapshot import (
    FubonCredentials,
    fetch_fubon_holding_snapshot,
    load_fubon_credentials_from_env,
    parse_fubon_cash,
    parse_fubon_inventories,
    write_holding_snapshot,
)


FUBON_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "group_a_plus" / "portfolio" / "fubon_snapshot.py"
FORBIDDEN_FUBON_ORDER_METHODS = {
    "place_order",
    "batch_place_order",
    "cancel_order",
    "batch_cancel_order",
    "modify_price",
    "batch_modify_price",
    "modify_quantity",
    "batch_modify_quantity",
    "make_modify_price_obj",
    "make_modify_quantity_obj",
}


@dataclass
class _Resp:
    data: object
    is_success: bool = True


@dataclass
class _Account:
    account: str


@dataclass
class _Inventory:
    stock_no: str
    today_qty: int


@dataclass
class _Cash:
    available_balance: float


class _StockShouldNotBeUsed:
    def __getattr__(self, name):
        raise AssertionError(f"stock API must not be used in read-only snapshot: {name}")


class _Accounting:
    def __init__(self):
        self.inventory_called = False
        self.bank_called = False

    def inventories(self, account):
        self.inventory_called = True
        assert account.account == "1234567"
        return _Resp([_Inventory("0050", 4000), _Inventory("00631L", 12000), _Inventory("00679B", 1000)])

    def bank_remain(self, account):
        self.bank_called = True
        assert account.account == "1234567"
        return _Resp(_Cash(available_balance=300000))


class _Sdk:
    def __init__(self):
        self.accounting = _Accounting()
        self.stock = _StockShouldNotBeUsed()
        self.login_called = False
        self.logout_called = False

    def login(self, user_id, password, cert_path, cert_password):
        self.login_called = True
        assert (user_id, password, cert_path, cert_password) == ("id", "pw", "cert.pfx", "certpw")
        return _Resp([_Account("1234567")])

    def logout(self):
        self.logout_called = True


class _RetrySdk(_Sdk):
    def __init__(self):
        super().__init__()
        self.login_attempts = 0
        self.seen_passwords: list[tuple[str, str]] = []

    def login(self, user_id, password, cert_path, cert_password):
        self.login_attempts += 1
        self.seen_passwords.append((password, cert_password))
        if self.login_attempts == 1:
            return _Resp(None, is_success=False)
        return _Resp([_Account("1234567")])


def test_load_fubon_credentials_from_env() -> None:
    creds = load_fubon_credentials_from_env(
        {
            "FUBON_ID": "id",
            "FUBON_PASSWORD": "old-env-pw",
            "FUBON_CERT_PATH": "cert.pfx",
            "FUBON_CERT_PASSWORD": "old-env-certpw",
        },
        password_provider=lambda _prompt, values=iter(["pw", "certpw"]): next(values),
    )
    assert creds == FubonCredentials("id", "pw", "cert.pfx", "certpw")


def test_load_fubon_credentials_accepts_legacy_personal_id_env() -> None:
    creds = load_fubon_credentials_from_env(
        {
            "FUBON_PERSONAL_ID": "legacy-id",
            "FUBON_CERT_PATH": "cert.pfx",
        },
        password_provider=lambda _prompt, values=iter(["pw", "certpw"]): next(values),
    )
    assert creds == FubonCredentials("legacy-id", "pw", "cert.pfx", "certpw")


def test_load_fubon_credentials_reports_missing_env() -> None:
    with pytest.raises(ValueError, match="FUBON_ID or FUBON_PERSONAL_ID"):
        load_fubon_credentials_from_env({})


def test_parse_fubon_inventories_accepts_objects_and_normalizes_suffixes() -> None:
    holdings = parse_fubon_inventories([_Inventory("0050", 4000), _Inventory("00679B", 1000)])
    assert holdings == {"0050.TW": 4000.0, "00679B.TWO": 1000.0}


def test_parse_fubon_inventories_accepts_dicts() -> None:
    holdings = parse_fubon_inventories([{"symbol": "00631L", "quantity": "12000"}])
    assert holdings == {"00631L.TW": 12000.0}


def test_parse_fubon_cash_accepts_object_and_dict() -> None:
    assert parse_fubon_cash(_Cash(available_balance=300000)) == 300000.0
    assert parse_fubon_cash({"available_cash": "12345"}) == 12345.0


def test_fetch_fubon_holding_snapshot_is_read_only() -> None:
    sdk = _Sdk()
    snapshot = fetch_fubon_holding_snapshot(
        sdk=sdk,
        credentials=FubonCredentials("id", "pw", "cert.pfx", "certpw"),
        as_of="2026-07-29",
    )

    assert sdk.login_called is True
    assert sdk.logout_called is False
    assert sdk.accounting.inventory_called is True
    assert sdk.accounting.bank_called is True
    assert snapshot.current_shares == {"0050.TW": 4000.0, "00631L.TW": 12000.0, "00679B.TWO": 1000.0}
    assert snapshot.cash == 300000.0
    assert snapshot.account_id == "1234567"
    assert snapshot.as_of == "2026-07-29"


def test_write_holding_snapshot(tmp_path) -> None:
    snapshot = fetch_fubon_holding_snapshot(
        sdk=_Sdk(),
        credentials=FubonCredentials("id", "pw", "cert.pfx", "certpw"),
        as_of="2026-07-29",
    )
    output = write_holding_snapshot(snapshot, tmp_path / "holdings.json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "fubon_neo_read_only"
    assert payload["current_shares"]["0050.TW"] == 4000.0
    assert payload["cash"] == 300000.0


def test_fetch_fubon_holding_snapshot_logs_out_owned_sdk(monkeypatch) -> None:
    sdk = _Sdk()
    monkeypatch.setattr("group_a_plus.portfolio.fubon_snapshot._new_fubon_sdk", lambda: sdk)

    snapshot = fetch_fubon_holding_snapshot(
        credentials=FubonCredentials("id", "pw", "cert.pfx", "certpw"),
        as_of="2026-07-29",
    )

    assert snapshot.current_shares["0050.TW"] == 4000.0
    assert sdk.logout_called is True


def test_fetch_fubon_holding_snapshot_retries_manual_passwords(monkeypatch) -> None:
    sdk = _RetrySdk()
    monkeypatch.setattr("group_a_plus.portfolio.fubon_snapshot._new_fubon_sdk", lambda: sdk)
    prompts = iter(["wrong-login", "wrong-cert", "pw", "certpw"])

    snapshot = fetch_fubon_holding_snapshot(
        env={"FUBON_ID": "id", "FUBON_CERT_PATH": "cert.pfx"},
        password_provider=lambda _prompt: next(prompts),
        as_of="2026-07-29",
    )

    assert sdk.login_attempts == 2
    assert sdk.seen_passwords == [("wrong-login", "wrong-cert"), ("pw", "certpw")]
    assert snapshot.current_shares["0050.TW"] == 4000.0


def test_fubon_snapshot_module_has_no_order_placement_calls() -> None:
    tree = ast.parse(FUBON_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_FUBON_ORDER_METHODS:
            forbidden_calls.append(func.attr)

    assert forbidden_calls == []
