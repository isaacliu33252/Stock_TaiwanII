from __future__ import annotations

from group_a_plus.portfolio.fubon_sdk_check import check_fubon_sdk


class _FakeFubonSDK:
    pass


def test_check_fubon_sdk_instantiates_without_login_with_factory() -> None:
    result = check_fubon_sdk(sdk_factory=_FakeFubonSDK)

    assert result["sdk_imported"] is True
    assert result["sdk_instantiated"] is True
    assert result["version"] == "2.2.8"
    assert result["module_path"]
    assert result["sdk_type"].endswith("._FakeFubonSDK")
    assert result["instantiation_error"] is None
    assert result["login_attempted"] is False
    assert result["accounting_attempted"] is False
    assert result["order_api_attempted"] is False


def test_check_fubon_sdk_reports_instantiation_error_without_login() -> None:
    class BrokenFactory:
        def __init__(self):
            raise ValueError("network unavailable")

    result = check_fubon_sdk(sdk_factory=BrokenFactory)

    assert result["sdk_imported"] is True
    assert result["sdk_instantiated"] is False
    assert result["instantiation_error"] == {"type": "ValueError", "message": "network unavailable"}
    assert result["login_attempted"] is False
    assert result["accounting_attempted"] is False
    assert result["order_api_attempted"] is False


def test_check_fubon_sdk_real_import_path_never_logs_in() -> None:
    result = check_fubon_sdk()

    assert result["sdk_imported"] is True
    assert result["version"] == "2.2.8"
    assert result["module_path"]
    assert result["login_attempted"] is False
    assert result["accounting_attempted"] is False
    assert result["order_api_attempted"] is False
