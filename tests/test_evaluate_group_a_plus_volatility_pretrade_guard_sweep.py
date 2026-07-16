#!/usr/bin/env python3
"""Tests for volatility pre-trade guard threshold sweep helpers."""

from __future__ import annotations

from scripts.evaluate.evaluate_group_a_plus_volatility_pretrade_guard_sweep import _parse_bool_list


def test_parse_bool_list_accepts_true_false_aliases() -> None:
    assert _parse_bool_list("true,false,1,0,yes,no") == [True, False, True, False, True, False]
