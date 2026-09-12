from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_17808_tail_bank_review as module


def _write_source(path: Path, *, final_deltas: list[float], mdd_deltas: list[float]) -> None:
    windows = []
    for idx, (final_delta, mdd_delta) in enumerate(zip(final_deltas, mdd_deltas), start=1):
        windows.append(
            {
                "label": f"window_{idx}",
                "kind": "stress_window" if idx == 2 else "out_of_sample",
                "window": {"start": "2026-01-01", "end": "2026-01-31", "rows": 20},
                "baseline": {"metrics": {"final_value": 1_000_000.0}},
                "riccati_mv_cap_to_cash": {"metrics": {"final_value": 1_000_000.0 + final_delta}},
                "delta_vs_baseline": {
                    "final_value": final_delta,
                    "sharpe_ratio": 0.01 if final_delta > 0 else -0.01,
                    "max_drawdown": mdd_delta,
                    "worst_20d_return": 0.0,
                },
                "confirmation_days": 3,
                "cap_event_days": idx,
            }
        )
    payload = {
        "generated_at": "2026-09-03T00:00:00",
        "policy": "research_only_no_weight_change",
        "decision": {"promotion_allowed": False, "decision": "do_not_promote_keep_shadow"},
        "confirmation": {"mode": "tail_drawdown_vol", "cap_beta": 0.5},
        "spec": {"lookback_days": 252},
        "windows": windows,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_candidate_extracts_tail_bank_counts(tmp_path: Path) -> None:
    source = tmp_path / "candidate.json"
    _write_source(source, final_deltas=[10.0, -20.0], mdd_deltas=[0.001, -0.002])

    summary = module.summarize_candidate("candidate", source)

    assert summary["window_count"] == 2
    assert summary["total_cap_event_days"] == 3
    assert summary["positive_final_value_windows"] == 1
    assert summary["positive_max_drawdown_windows"] == 1
    assert summary["worst_delta_final_value"] == -20.0
    assert summary["broad_tail_coverage_pass"] is False


def test_build_report_selects_best_stability_candidate(tmp_path: Path) -> None:
    weak = tmp_path / "weak.json"
    stable = tmp_path / "stable.json"
    _write_source(weak, final_deltas=[-100.0, -50.0], mdd_deltas=[-0.003, -0.002])
    _write_source(stable, final_deltas=[-10.0, -5.0], mdd_deltas=[0.0, 0.0])

    report = module.build_report([("weak", weak), ("stable", stable)])

    assert report["decision"]["decision"] == "do_not_promote_keep_shadow"
    assert report["decision"]["best_stability_candidate"] == "stable"
    assert report["decision"]["no_further_auto_tuning_recommended"] is True
    assert report["changes_latest_strategy"] is False


def test_write_markdown_renders_research_only_decision(tmp_path: Path) -> None:
    source = tmp_path / "candidate.json"
    output = tmp_path / "review.md"
    _write_source(source, final_deltas=[1.0, -2.0], mdd_deltas=[0.0, 0.0])
    report = module.build_report([("candidate", source)])

    module.write_markdown(report, output)

    text = output.read_text(encoding="utf-8")
    assert "2608.17808 Tail Bank Review" in text
    assert "do_not_promote_keep_shadow" in text
    assert "No target-weight change" in text
    assert "candidate" in text
