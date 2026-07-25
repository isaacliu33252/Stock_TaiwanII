from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_multi_window_failure_attribution import build_attribution, write_outputs


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_multi_window_failure_attribution_extracts_candidate_shortfalls(tmp_path: Path) -> None:
    gate = _write(
        tmp_path / "multi_window.json",
        {
            "decision": "research_only_no_multi_window_pass",
            "criteria": {
                "min_pass_ratio": 1.0,
                "max_final_drawdown_pct": 0.02,
                "min_sharpe_delta": 0.0,
                "require_mdd_nonworse": True,
            },
            "candidate_count": 2,
            "row_count": 3,
            "candidates": [
                {
                    "candidate": "selector",
                    "decision": "research_only_multi_window_unstable",
                    "window_count": 2,
                    "pass_count": 1,
                    "pass_ratio": 0.5,
                    "worst_delta_final_pct": -0.03,
                    "worst_delta_sharpe": -0.01,
                    "worst_delta_max_drawdown": 0.01,
                    "rows": [
                        {
                            "window": "2008",
                            "candidate": "selector",
                            "delta_final_pct": 0.04,
                            "delta_sharpe": 0.02,
                            "delta_max_drawdown": 0.01,
                            "window_pass": True,
                            "window_fail_reasons": [],
                        },
                        {
                            "window": "2020",
                            "candidate": "selector",
                            "delta_final_pct": -0.03,
                            "delta_sharpe": -0.01,
                            "delta_max_drawdown": 0.02,
                            "window_pass": False,
                            "window_fail_reasons": ["final_value_drag", "sharpe_delta"],
                        },
                    ],
                },
                {
                    "candidate": "drawdown_guard",
                    "decision": "research_only_multi_window_unstable",
                    "window_count": 1,
                    "pass_count": 0,
                    "pass_ratio": 0.0,
                    "worst_delta_final_pct": 0.01,
                    "worst_delta_sharpe": 0.02,
                    "worst_delta_max_drawdown": -0.004,
                    "rows": [
                        {
                            "window": "2008",
                            "candidate": "drawdown_guard",
                            "delta_final_pct": 0.01,
                            "delta_sharpe": 0.02,
                            "delta_max_drawdown": -0.004,
                            "window_pass": False,
                            "window_fail_reasons": ["max_drawdown_worse"],
                        },
                    ],
                },
            ],
        },
    )

    report = build_attribution(gate)

    assert report["status"] == "blocked"
    assert report["summary"]["top_failure_reasons"] == [
        {"reason": "final_value_drag", "count": 1},
        {"reason": "sharpe_delta", "count": 1},
        {"reason": "max_drawdown_worse", "count": 1},
    ]
    selector = [item for item in report["candidates"] if item["candidate"] == "selector"][0]
    assert selector["pass_ratio_shortfall"] == 0.5
    assert selector["primary_failure_reason"] == "final_value_drag"
    drag = selector["drag_windows"][0]
    assert drag["window"] == "2020"
    assert round(drag["final_value_shortfall"], 6) == 0.01
    assert round(drag["sharpe_shortfall"], 6) == 0.01
    assert drag["max_drawdown_shortfall"] == 0.0
    assert report["decision"]["creates_orders"] is False
    assert report["decision"]["target_weight_change_allowed"] is False
    assert report["decision"]["auto_rebalance_allowed"] is False
    assert report["decision"]["keep_golden1_0531_unchanged"] is True


def test_write_outputs_writes_json_markdown_and_history(tmp_path: Path) -> None:
    report = {
        "status": "blocked",
        "source_decision": "research_only_no_multi_window_pass",
        "candidate_count": 1,
        "criteria": {"min_pass_ratio": 1.0},
        "summary": {"top_failure_reasons": [{"reason": "final_value_drag", "count": 1}]},
        "candidates": [
            {
                "candidate": "selector",
                "pass_count": 0,
                "window_count": 1,
                "primary_failure_reason": "final_value_drag",
                "pass_ratio_shortfall": 1.0,
            }
        ],
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    output = tmp_path / "latest/multi_window_failure_attribution.json"
    output_md = tmp_path / "latest/multi_window_failure_attribution.md"
    history = tmp_path / "history"

    write_outputs(report, output=output, output_md=output_md, history_dir=history)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    markdown = output_md.read_text(encoding="utf-8")
    assert "GroupA+ Multi-Window Failure Attribution" in markdown
    assert "Golden1_0531 unchanged: `True`" in markdown
    assert list(history.glob("multi_window_failure_attribution_*.json"))
