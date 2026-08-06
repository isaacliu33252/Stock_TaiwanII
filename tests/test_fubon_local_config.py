from __future__ import annotations

import base64
import json

import pytest
from Crypto.Cipher import AES

from group_a_plus.portfolio.fubon_local_config import load_fubon_local_config, local_path_from_windows_path


def _pad32(value: str) -> bytes:
    raw = value.encode("utf-8")
    while len(raw) % 32 != 0:
        raw += b"\0"
    return raw


def _encrypt(value: str, key: bytes) -> str:
    encrypted = AES.new(key, AES.MODE_CBC, iv=b"0123456789abcdef").encrypt(_pad32(value))
    return base64.encodebytes(encrypted).decode("utf-8")


def test_local_path_from_windows_path_maps_c_drive_on_wsl() -> None:
    assert str(local_path_from_windows_path("C:\\fubon")) == "/mnt/c/fubon"
    assert str(local_path_from_windows_path("C:/CAFubon/test.p12")) == "/mnt/c/CAFubon/test.p12"


def test_load_fubon_local_config_ignores_stored_passwords(tmp_path) -> None:
    key_dir = tmp_path / "key"
    config_dir = tmp_path / "config"
    cert_dir = tmp_path / "cert"
    key_dir.mkdir()
    config_dir.mkdir()
    cert_dir.mkdir()
    cert_path = cert_dir / "client.p12"
    cert_path.write_text("fixture", encoding="utf-8")
    key = b"1" * 32
    (key_dir / "key.key").write_bytes(key)
    rows = [
        {"name": "fubon_stock", "user_id": _encrypt("user", key), "password": _encrypt("pass", key)},
        {"name": "fubon_pfx", "user_id": _encrypt(str(cert_path), key), "password": _encrypt("certpass", key)},
    ]
    (config_dir / "encrype.config").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    values = load_fubon_local_config(local_dir=tmp_path, env={})

    assert values == {
        "FUBON_ID": "user",
        "FUBON_CERT_PATH": str(cert_path),
        "FUBON_LOCAL_DIR": str(tmp_path),
        "FUBON_PASSWORD_MANUAL_REQUIRED": "1",
        "FUBON_CERT_PASSWORD_MANUAL_REQUIRED": "1",
    }


def test_load_fubon_local_config_uses_single_cert_fallback(tmp_path) -> None:
    key_dir = tmp_path / "key"
    config_dir = tmp_path / "config"
    key_dir.mkdir()
    config_dir.mkdir()
    cert_path = tmp_path / "fallback.p12"
    cert_path.write_text("fixture", encoding="utf-8")
    key = b"2" * 32
    (key_dir / "key.key").write_bytes(key)
    rows = [
        {"name": "fubon_stock", "user_id": _encrypt("user", key), "password": _encrypt("pass", key)},
        {"name": "fubon_pfx", "user_id": _encrypt("C:/missing/client.pfx", key), "password": _encrypt("certpass", key)},
    ]
    (config_dir / "encrype.config").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    values = load_fubon_local_config(local_dir=tmp_path, env={})

    assert values["FUBON_CERT_PATH"] == str(cert_path)


def test_load_fubon_local_config_requires_key(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="Fubon AES key not found"):
        load_fubon_local_config(local_dir=tmp_path, env={})
