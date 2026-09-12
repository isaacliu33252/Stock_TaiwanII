from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate.build_group_a_plus_hierarchical_credit_review_shadow import build_report, write_report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_hierarchical_credit_report_from_signal_files(tmp_path: Path) -> None:
    forecast = _write(
        tmp_path / "forecast.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-08-07",
                "actual_data_date": "2026-08-06",
                "business_stale_days": 0,
                "execution_allowed": True,
                "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
                "latest_prices": {"0050.TW": 100.0, "00631L.TW": 30.0, "00632R.TW": 10.0},
                "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
                "signal_alignment": {"alignment": "bullish_alignment", "dominant_direction": "bullish"},
            },
        },
    )
    actual = _write(
        tmp_path / "actual.json",
        {
            "success": True,
            "data": {
                "requested_as_of_date": "2026-08-08",
                "actual_data_date": "2026-08-07",
                "business_stale_days": 0,
                "execution_allowed": True,
                "latest_prices": {"0050.TW": 98.0, "00631L.TW": 28.8, "00632R.TW": 10.2},
                "latest_features": {"total_risk_score": 2, "tail_risk_score": 0},
                "signal_alignment": {"alignment": "bullish_alignment", "dominant_direction": "bullish"},
            },
        },
    )

    report = build_report(forecast_path=forecast, actual_path=actual, as_of="2026-08-07")

    assert report["as_of"] == "2026-08-07"
    assert report["primary_attribution"] == "selection_error"
    assert report["sources"]["forecast_signal"] == str(forecast)
    assert report["decision"]["creates_orders"] is False


def test_write_hierarchical_credit_report_writes_history_and_log(tmp_path: Path) -> None:
    output = tmp_path / "latest" / "credit.json"
    history = tmp_path / "history"
    log = tmp_path / "credit.jsonl"
    report = {
        "as_of": "2026-08-07",
        "primary_attribution": "market_noise",
        "secondary_attributions": [],
        "confidence": 0.7,
        "layer_scores": {"market_noise": 0.25},
        "evidence": [],
        "realized": {},
        "decision": {"target_weight_change_allowed": False},
    }

    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert (history / "hierarchical_credit_review_shadow_20260807.json").exists()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["date"] == "2026-08-07"
    assert rows[0]["primary_attribution"] == "market_noise"
