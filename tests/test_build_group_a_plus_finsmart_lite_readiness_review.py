from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_finsmart_lite_readiness_review import (
    build_review,
    write_review,
)


def _write_diagnostic(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "## Results",
                "",
                "series    n  corr_same_day  corr_next_day  n_gated_same  corr_same_day_gated_0.5pct  corr_next_day_gated_0.5pct",
                "production finbert_sentiment (LTN, market-wide, rule_based_finbert_proxy) vs 0050 return  1555  0.1148  0.0052  968  0.1379  -0.0500",
                "FinMind 0050-tagged headlines (same keyword scorer) vs 0050 return  354  0.2355  0.0884  253  0.2638  0.1033",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_build_review_allows_shadow_design_but_blocks_training_and_live(tmp_path: Path) -> None:
    pdf = tmp_path / "2607.28127.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    diagnostic = _write_diagnostic(tmp_path / "diagnostic.md")

    review = build_review(pdf_path=pdf, diagnostic_path=diagnostic, as_of="2026-08-06")

    assert review["report_type"] == "group_a_plus_finsmart_lite_readiness_review"
    assert review["status"] == "available_for_shadow_design"
    assert review["decision"]["finsmart_lite_shadow_design_allowed"] is True
    assert review["decision"]["market_aligned_sentiment_shadow_allowed"] is True
    assert review["decision"]["llm_training_allowed"] is False
    assert review["decision"]["grpo_training_allowed"] is False
    assert review["decision"]["outputs_target_weights"] is False
    assert review["decision"]["target_weight_change_allowed"] is False
    assert review["decision"]["keep_golden1_0531_unchanged"] is True
    assert review["diagnostic_summary"]["best_existing_alignment"]["corr_next_day"] == 0.0884
    assert "group_a_plus/integrations/signal_alignment.py" in review["recommended_shadow_design"]["integration_points"]


def test_build_review_blocks_when_pdf_missing(tmp_path: Path) -> None:
    diagnostic = _write_diagnostic(tmp_path / "diagnostic.md")

    review = build_review(pdf_path=tmp_path / "missing.pdf", diagnostic_path=diagnostic, as_of="2026-08-06")

    assert review["status"] == "blocked"
    assert "missing_source_pdf" in review["blocking_reasons"]
    assert review["decision"]["finsmart_lite_shadow_design_allowed"] is False
    assert review["decision"]["target_weight_change_allowed"] is False


def test_write_review_writes_latest_and_history(tmp_path: Path) -> None:
    review = {
        "report_type": "group_a_plus_finsmart_lite_readiness_review",
        "as_of": "2026-08-06",
    }
    output = tmp_path / "latest" / "review.json"
    history = tmp_path / "history"

    write_review(review, output, history)

    assert json.loads(output.read_text(encoding="utf-8")) == review
    history_file = history / "finsmart_lite_readiness_review_20260806.json"
    assert json.loads(history_file.read_text(encoding="utf-8")) == review
