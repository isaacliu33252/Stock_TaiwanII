from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.evaluate.build_group_a_plus_asian_etf_tail_analytics_readiness_review import build_review, write_review


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_review_blocks_when_paper_universe_and_live_validation_missing(tmp_path: Path) -> None:
    db = tmp_path / "stock_data.db"
    with duckdb.connect(str(db)) as conn:
        conn.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
        conn.execute("INSERT INTO ohlcv VALUES ('0050.TW', '2026-07-17', 100.0)")
    cvar = tmp_path / "cvar.json"
    market = tmp_path / "market.json"
    rebalance = tmp_path / "rebalance.json"
    letf = tmp_path / "letf.json"
    _write(
        cvar,
        {
            "status": "research_only",
            "promotion_decision": "research_only",
            "ranking_by_starr95": [
                {
                    "strategy": "golden1_frozen_proxy_50_20_30",
                    "starr_95": 14.0,
                    "rachev_95_95": 1.2,
                }
            ],
            "00631l_only_tail_diagnostics": {"rachev_95_95": 0.9},
        },
    )
    _write(market, {"status": "blocked", "decision": {"auto_rebalance_allowed": False}})
    _write(
        rebalance,
        {
            "dates": {"requested_as_of_date": "2026-07-20"},
            "decision": {
                "auto_rebalance_allowed": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
            },
        },
    )
    _write(letf, {"status": "blocked", "decision": {"allow_00631l_add": False, "allow_00632r_open": False}})

    review = build_review(db_path=db, cvar_path=cvar, market_impact_path=market, rebalance_path=rebalance, letf_path=letf)

    assert review["report_type"] == "group_a_plus_asian_etf_tail_analytics_readiness_review"
    assert review["status"] == "blocked"
    assert review["decision"]["tail_analytics_ready"] is False
    assert review["decision"]["auto_rebalance_allowed"] is False
    assert review["decision"]["allow_00631l_add"] is False
    assert review["data_readiness"]["paper_etf_coverage"]["available_paper_etf_count"] == 0
    assert review["component_readiness"]["cvar_tail_risk"]["golden1_rachev_95_95"] == 1.2
    assert review["component_readiness"]["cvar_tail_risk"]["00631l_rachev_95_95"] == 0.9
    assert review["tail_reward_risk_monitor"]["tier"] == "defensive_preference"
    assert review["tail_reward_risk_monitor"]["golden1_beats_00631l_by_rachev"] is True
    assert review["tail_reward_risk_monitor"]["00631l_rachev_below_one"] is True
    assert review["validation_readiness"]["starr_rachev_ratio_monitor_implemented"] is True
    assert "asian_29_etf_universe_not_available" in review["blocking_reasons"]
    assert "long_short_etf_strategy_not_allowed" in review["blocking_reasons"]
    assert "rachev_prefers_golden1_over_00631l" in review["warning_reasons"]
    assert "00631l_rachev_below_one_tail_reward_unfavorable" in review["warning_reasons"]


def test_write_review_writes_output_and_history(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    history = tmp_path / "history"
    review = {
        "report_type": "group_a_plus_asian_etf_tail_analytics_readiness_review",
        "as_of": "2026-07-20",
        "decision": {"allow_00631l_add": False},
    }

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    assert (history / "asian_etf_tail_analytics_readiness_20260720.json").exists()
