"""Load local Fubon account metadata from the AES config folder.

This supports the notebook-style local layout under ``C:\fubon`` without
printing decrypted values. Password fields are intentionally not returned:
Fubon SDK login must prompt for passwords at runtime.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

DEFAULT_LOCAL_FUBON_DIR = Path(os.environ.get("FUBON_LOCAL_DIR", "/mnt/c/fubon"))
_WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def local_path_from_windows_path(path: str | Path) -> Path:
    text = str(path).strip().strip('"')
    match = _WINDOWS_DRIVE_RE.match(text)
    if match and os.name != "nt":
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(text).expanduser()


def _aes_decrypt(secret_str: str, key: bytes) -> str:
    from Crypto.Cipher import AES

    cryptor = AES.new(key, AES.MODE_CBC, iv=b"0123456789abcdef")
    base64_decrypted = __import__("base64").decodebytes(secret_str.encode("utf-8"))
    return str(cryptor.decrypt(base64_decrypted), encoding="utf-8").replace("\0", "")


def _load_records(config_path: Path) -> dict[str, Mapping[str, Any]]:
    records: dict[str, Mapping[str, Any]] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict) and item.get("name"):
            records[str(item["name"])] = item
    return records


def _decrypt_user_id(records: Mapping[str, Mapping[str, Any]], name: str, key: bytes) -> str:
    item = records.get(name)
    if not item:
        raise ValueError(f"missing Fubon AES config record: {name}")
    return _aes_decrypt(str(item["user_id"]), key)


def _fallback_cert_path(configured: Path, local_dir: Path) -> Path:
    if configured.exists():
        return configured
    candidates: list[Path] = []
    if configured.parent.exists():
        candidates.extend(sorted(configured.parent.glob("*.p12")))
        candidates.extend(sorted(configured.parent.glob("*.pfx")))
    candidates.extend(sorted(local_dir.rglob("*.p12")))
    candidates.extend(sorted(local_dir.rglob("*.pfx")))
    existing = [path for path in candidates if path.exists()]
    if len(existing) == 1:
        return existing[0]
    return configured


def load_fubon_local_config(
    *,
    local_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return non-password Fubon fields from local AES config.

    Environment overrides:
    - ``FUBON_LOCAL_DIR`` changes the default local directory.
    - ``FUBON_CERT_PATH`` overrides the decrypted certificate path.

    Passwords stored in the AES config are intentionally ignored. Login code
    must prompt the user manually for the Fubon login password and certificate
    password.
    """
    source = env or os.environ
    base = local_path_from_windows_path(local_dir or source.get("FUBON_LOCAL_DIR") or DEFAULT_LOCAL_FUBON_DIR)
    key_path = base / "key" / "key.key"
    config_path = base / "config" / "encrype.config"
    if not key_path.exists():
        raise FileNotFoundError(f"Fubon AES key not found: {key_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Fubon AES config not found: {config_path}")

    key = key_path.read_bytes()
    records = _load_records(config_path)
    user_id = _decrypt_user_id(records, "fubon_stock", key)
    cert_path_raw = _decrypt_user_id(records, "fubon_pfx", key)
    cert_path = local_path_from_windows_path(source.get("FUBON_CERT_PATH") or cert_path_raw)
    cert_path = _fallback_cert_path(cert_path, base)
    return {
        "FUBON_ID": user_id,
        "FUBON_CERT_PATH": str(cert_path),
        "FUBON_LOCAL_DIR": str(base),
        "FUBON_PASSWORD_MANUAL_REQUIRED": "1",
        "FUBON_CERT_PASSWORD_MANUAL_REQUIRED": "1",
    }
