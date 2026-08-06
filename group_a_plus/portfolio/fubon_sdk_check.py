"""Smoke check Fubon Neo SDK import/instantiation without login."""

from __future__ import annotations

import argparse
import json
from typing import Any


def check_fubon_sdk(*, sdk_factory: Any | None = None) -> dict[str, Any]:
    import fubon_neo
    from fubon_neo.sdk import FubonSDK

    factory = sdk_factory or FubonSDK
    try:
        sdk = factory()
        sdk_instantiated = True
        sdk_type = f"{type(sdk).__module__}.{type(sdk).__name__}"
        instantiation_error = None
    except Exception as exc:
        sdk_instantiated = False
        sdk_type = None
        instantiation_error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    return {
        "sdk_imported": True,
        "sdk_instantiated": sdk_instantiated,
        "version": getattr(fubon_neo, "__version__", None),
        "module_path": getattr(fubon_neo, "__file__", None),
        "sdk_type": sdk_type,
        "instantiation_error": instantiation_error,
        "login_attempted": False,
        "accounting_attempted": False,
        "order_api_attempted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()
    result = check_fubon_sdk()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"Fubon SDK imported: {result['sdk_imported']}")
    print(f"Fubon SDK instantiated: {result['sdk_instantiated']}")
    print(f"Version: {result['version']}")
    print(f"Module path: {result['module_path']}")
    print("Login attempted: false")
    print("Accounting attempted: false")
    print("Order API attempted: false")


if __name__ == "__main__":
    main()
