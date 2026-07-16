from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_group_a_plus_shadow_log_unified_join import (
    _flatten,
    build_summary,
    load_source_frame,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_flatten_nests_dicts_up_to_max_depth() -> None:
    out: dict = {}
    _flatten({"a": 1, "b": {"c": 2, "d": {"e": 3}}}, "src", out, max_depth=2)

    assert out["src__a"] == 1
    assert out["src__b__c"] == 2
    # "d" is at depth 2 already, so its dict value gets JSON-serialized rather
    # than flattened one level further.
    assert out["src__b__d"] == json.dumps({"e": 3}, ensure_ascii=False)


def test_flatten_serializes_lists() -> None:
    out: dict = {}
    _flatten([1, 2, 3], "src__items", out)

    assert out["src__items"] == json.dumps([1, 2, 3])


def test_load_source_frame_indexes_by_date_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    _write_jsonl(
        path,
        [
            {"date": "2026-07-14", "state": "bull_trend", "risk_level": "risk_on"},
            {"date": "2026-07-15", "state": "crash_risk", "risk_level": "severe"},
            {"date": "2026-07-15", "state": "bear_breakdown", "risk_level": "severe"},  # dup date, keep last
        ],
    )

    frame = load_source_frame("market_state", path)

    assert list(frame.index) == [pd.Timestamp("2026-07-14"), pd.Timestamp("2026-07-15")]
    assert frame.loc[pd.Timestamp("2026-07-15"), "market_state__state"] == "bear_breakdown"
    assert frame.loc[pd.Timestamp("2026-07-14"), "market_state__risk_level"] == "risk_on"


def test_load_source_frame_filters_by_ticker(tmp_path: Path) -> None:
    path = tmp_path / "archive.jsonl"
    _write_jsonl(
        path,
        [
            {"date": "2026-07-14", "ticker": "00631L.TW", "blend_0.35_probability_up": 0.6},
            {"date": "2026-07-14", "ticker": "00632R.TW", "blend_0.35_probability_up": 0.4},
        ],
    )

    frame = load_source_frame("ncf_signal_archive", path, ticker_filter="00631L.TW")

    assert len(frame) == 1
    assert frame.iloc[0]["ncf_signal_archive__blend_0.35_probability_up"] == 0.6


def test_load_source_frame_missing_file_returns_empty(tmp_path: Path) -> None:
    frame = load_source_frame("missing_source", tmp_path / "does_not_exist.jsonl")

    assert frame.empty


def test_build_summary_counts_rows_with_data_per_source() -> None:
    idx = pd.to_datetime(["2026-07-14", "2026-07-15", "2026-07-16"])
    joined = pd.DataFrame(
        {
            "market_state__state": ["bull_trend", None, "crash_risk"],
            "signal_alignment__alignment": [None, "aligned", None],
        },
        index=idx,
    )
    sources = {"market_state": Path("unused"), "signal_alignment": Path("unused")}

    summary = build_summary(joined, sources)

    assert summary["total_dates"] == 3
    assert summary["sources"]["market_state"]["rows_with_data"] == 2
    assert summary["sources"]["signal_alignment"]["rows_with_data"] == 1
