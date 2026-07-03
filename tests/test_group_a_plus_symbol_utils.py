#!/usr/bin/env python3
"""Tests for GroupA+ symbol normalization helpers."""

from __future__ import annotations

from group_a_plus.utils.symbols import (
    build_symbol_metadata,
    format_symbol_for_tradingview,
    split_symbol_suffix,
    symbol_exchange,
)


def test_tw_symbols_convert_to_tradingview_prefixes() -> None:
    assert format_symbol_for_tradingview("0050.TW") == "TWSE:0050"
    assert format_symbol_for_tradingview("00631l.tw") == "TWSE:00631L"
    assert format_symbol_for_tradingview("00679B.TWO") == "TPEX:00679B"


def test_longer_two_suffix_is_matched_before_tw() -> None:
    root, suffix = split_symbol_suffix("00679B.TWO")

    assert root == "00679B"
    assert suffix == ".TWO"
    assert symbol_exchange("00679B.TWO") == "TPEX"


def test_symbol_metadata_skips_cash() -> None:
    metadata = build_symbol_metadata(["0050.TW", "cash"])

    assert list(metadata) == ["0050.TW"]
    assert metadata["0050.TW"]["tradingview_symbol"] == "TWSE:0050"
