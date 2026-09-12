from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_2607_16450_geopolitical_cvar_overlay import build_overlay, write_overlay


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_geopolitical_cvar_overlay_flags_high_stress_without_live_weight_change(tmp_path: Path) -> None:
    watchlist = tmp_path / "watchlist.json"
    _write(
        watchlist,
        {
            "signal_date": "2026-08-24",
            "source": "local_ltn_jsonl",
            "articles": [
                {
                    "date": "2026-08-24",
                    "source": "fixture",
                    "title": "台海軍演升級 出口管制與制裁衝擊先進製程供應鏈",
                    "snippet": "共軍軍演、晶片禁令、供應鏈中斷引發市場避險。",
                    "url": "https://example.test/a",
                },
                {
                    "date": "2026-08-24",
                    "source": "fixture",
                    "title": "Taiwan Strait blockade risk and export control pressure rise",
                    "snippet": "Geopolitical conflict and supply chain disruption dominate.",
                    "url": "https://example.test/b",
                },
            ],
        },
    )

    overlay = build_overlay(watchlist_news_path=watchlist)

    assert overlay["report_type"] == "group_a_plus_2607_16450_geopolitical_cvar_overlay"
    assert overlay["status"] == "available_for_monitoring"
    assert overlay["score"]["state"] == "high_geopolitical_stress"
    assert overlay["overlay"]["cvar_penalty_multiplier"] == 1.5
    assert overlay["overlay"]["advisory_max_00631l_weight"] == 0.0
    assert overlay["decision"]["target_weight_change_allowed"] is False
    assert overlay["decision"]["allow_00631l_add_from_geopolitical_overlay"] is False


def test_geopolitical_cvar_overlay_normal_when_no_keywords(tmp_path: Path) -> None:
    watchlist = tmp_path / "watchlist.json"
    _write(
        watchlist,
        {
            "signal_date": "2026-08-24",
            "source": "local_ltn_jsonl",
            "articles": [{"title": "台股量縮整理", "snippet": "市場等待財報。"}],
        },
    )

    overlay = build_overlay(watchlist_news_path=watchlist)

    assert overlay["score"]["state"] == "normal"
    assert overlay["overlay"]["cvar_penalty_multiplier"] == 1.0
    assert overlay["overlay"]["advisory_max_00631l_weight"] == 0.2
    assert "no_geopolitical_keywords_matched_in_watchlist_news" in overlay["warning_reasons"]


def test_write_geopolitical_cvar_overlay_writes_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    overlay = {
        "report_type": "group_a_plus_2607_16450_geopolitical_cvar_overlay",
        "as_of": "2026-08-24",
        "decision": {"target_weight_change_allowed": False},
    }

    write_overlay(overlay, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == overlay
    assert (history / "2607_16450_geopolitical_cvar_overlay_20260824.json").exists()
