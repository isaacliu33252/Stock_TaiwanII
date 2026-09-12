from pathlib import Path

from scripts.evaluate.build_group_a_plus_2609_07989_order_flow_regime_review import (
    build_report,
    render_markdown,
)


def test_order_flow_regime_review_keeps_latest_strategy_unchanged() -> None:
    report = build_report(Path("/tmp/2609.07989_regimes_in_the_order_flow.pdf"))

    assert report["paper"]["arxiv_id"] == "2609.07989"
    assert report["decision"]["import_mode"] == "execution_advisory_shadow_only"
    assert report["decision"]["advisory_import_allowed"] is True
    assert report["decision"]["changes_latest_strategy"] is False
    assert report["decision"]["changes_golden2_0830"] is False
    assert report["decision"]["live_weight_change_allowed"] is False
    assert report["decision"]["order_generation_allowed"] is False


def test_order_flow_regime_review_rejects_daily_proxy_and_multivariate_live_gate() -> None:
    report = build_report(Path("/tmp/2609.07989_regimes_in_the_order_flow.pdf"))
    by_name = {item["name"]: item for item in report["adoption_candidates"]}

    assert by_name["duration_aware_intraday_order_flow_changepoint_shadow"]["status"] == "conditional_shadow"
    assert by_name["daily_ohlcv_proxy_order_flow_regime_gate"]["status"] == "do_not_adopt"
    assert by_name["multivariate_bocpdms_bvar_live_gate"]["status"] == "reject_for_now"
    assert all(item["live_change_allowed"] is False for item in report["adoption_candidates"])


def test_order_flow_regime_review_markdown_contains_required_decision() -> None:
    report = build_report(Path("/tmp/2609.07989_regimes_in_the_order_flow.pdf"))
    markdown = render_markdown(report)

    assert "# 2609.07989 Order-Flow Regime Review" in markdown
    assert "execution_advisory_shadow_only" in markdown
    assert "duration_aware_intraday_order_flow_changepoint_shadow" in markdown
    assert "Keep this paper out of live target-weight logic" in markdown
