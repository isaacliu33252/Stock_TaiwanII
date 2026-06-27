#!/usr/bin/env python3
"""Compatibility entry point for GroupA++ 00751B versus cash evaluation."""

import importlib


_module = importlib.import_module("group_a_plus.portfolio.cash_00751b")

DEFAULT_WORKBOOK = _module.DEFAULT_WORKBOOK
HEADER_TO_TICKER = _module.HEADER_TO_TICKER
evaluate = _module.evaluate
load_prices = _module.load_prices
read_group_a_plus_plus_holdings = _module.read_group_a_plus_plus_holdings
write_workbook = _module.write_workbook
main = _module.main


if __name__ == "__main__":
    main()
