from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.integrations.daily_semantic_context import (
    append_daily_semantic_context_log,
    build_daily_semantic_context,
)


def test_daily_semantic_context_compresses_shadow_inputs() -> None:
    report = build_daily_semantic_context(
        live_signal={
            "success": True,
            "data": {
                "requested_as_of_date": "2026-08-10",
                "actual_data_date": "2026-08-06",
                "business_stale_days": 2,
                "execution_allowed": False,
                "execution_regime": "golden1",
                "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
                "market_state": {"state": "choppy_range_low_risk", "label_zh": "低風險盤整"},
            },
        },
        signal_alignment={
            "alignment": "bullish_alignment",
            "dominant_direction": "bullish",
            "sources": [
                {"name": "weak", "available": True, "direction": "neutral", "strength": 0.1, "reason": "x"},
                {"name": "strong", "available": True, "direction": "bullish", "strength": 0.9, "reason": "y"},
            ],
        },
        risk_mechanism={"mechanism": "FAST_CRASH", "reasons": ["tail"]},
        watchlist_news={"source": "local", "article_count": 0, "fallback_used": True, "watchlist": []},
        hierarchical_credit_review={"primary_attribution": "data_freshness_error"},
        event_execution_quality={"status": "blocked_review_only", "quality_score": 0.48, "blockers": ["source_fresh_enough"]},
        relative_exposure_thesis={"thesis_class": "short_term_inverse_hedge_review_only", "thesis_quality_score": 0.55},
        moira_policy_critic={"status": "blocked_review_only", "proposal_count": 1, "blocking_reasons": ["x"], "proposals": [{"proposal_id": "p"}]},
        as_of="2026-08-07",
    )

    assert report["as_of"] == "2026-08-07"
    assert report["signal_context"]["top_sources"][0]["name"] == "strong"
    assert report["moira_shadow_context"]["credit_primary_attribution"] == "data_freshness_error"
    assert report["moira_shadow_context"]["policy_critic_proposal_ids"] == ["p"]
    assert "execution_guard_false" in report["compressed_takeaways"]["hard_blockers"]
    assert "source_stale_ge_2_business_days" in report["compressed_takeaways"]["hard_blockers"]
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["allow_00632r_open"] is False


def test_daily_semantic_context_log_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "summary.jsonl"
    report = build_daily_semantic_context(as_of="2026-08-07")

    append_daily_semantic_context_log(log, report, date="2026-08-07")
    append_daily_semantic_context_log(log, report, date="2026-08-07")

    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-07"
