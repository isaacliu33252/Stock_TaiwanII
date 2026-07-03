from __future__ import annotations

import json
import importlib.util
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "group_a_plus_decision_policy.py"
    spec = importlib.util.spec_from_file_location("_test_group_a_plus_decision_policy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_ncf_advisory_context_returns_shadow_recommendation(tmp_path: Path) -> None:
    module = _load_module()
    panel = tmp_path / "ncf_advisory.csv"
    panel.write_text(
        "\n".join(
            [
                "date,market_direction,market_probability_up,agreement_score,conflict_flag,cross_ticker_confidence,dynamic_00631l_direction,dynamic_00631l_prob_up,dynamic_00632r_direction,dynamic_00632r_prob_up",
                "2026-06-24,UP,0.61,0.70,false,0.03,UP,0.62,DOWN,0.38",
                "2026-06-25,DOWN,0.31,0.80,false,0.07,DOWN,0.34,UP,0.76",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    context = module._load_ncf_advisory_context(panel)

    assert context["status"] == "available"
    assert context["date"] == "2026-06-25"
    assert context["shadow_recommendation"]["policy"] == "bearish_reduce_40"
    assert context["decision_policy_effect"] == "report_only_no_weight_change"


def test_apply_policy_embeds_ncf_context_without_changing_targets() -> None:
    module = _load_module()
    baseline = {
        "profile": "test_profile",
        "latest_group_a_plus_final_signal": "results/source_signal.json",
    }
    review = {"generated_at": "2026-06-27T10:00:00", "vote": {"decision": "approve", "vote_counts": {"approve": 1}}}
    compare = {"generated_at": "2026-06-27T10:01:00"}
    source_signal = {
        "total_assets": 1_000_000.0,
        "latest_prices": {"0050.TW": 100.0, "00631L.TW": 40.0, "00632R.TW": 10.0, "00679B.TWO": 25.0},
        "current_shares": {"0050.TW": 1000, "00631L.TW": 1000, "00632R.TW": 0, "00679B.TWO": 1000},
        "target_shares": {"0050.TW": 2000, "00631L.TW": 2000, "00632R.TW": 0, "00679B.TWO": 4000},
        "execution_summary": {"cash_after_cost": 700_000.0},
    }
    ncf_context = {
        "status": "available",
        "date": "2026-06-25",
        "shadow_recommendation": {
            "policy": "bearish_reduce_40",
            "risk_reduction": 0.40,
            "implementation_status": "not_applied_to_live_weights",
        },
    }

    report, signal = module._apply_policy(
        baseline,
        review,
        compare,
        source_signal,
        min_cash_after_cost_weight=0.01,
        target_total_assets=None,
        ncf_advisory_context=ncf_context,
    )

    assert report["ncf_advisory_context"] == ncf_context
    assert signal["ncf_advisory_context"] == ncf_context
    assert report["target_shares_after_policy"] == source_signal["target_shares"]
    assert signal["target_shares"] == source_signal["target_shares"]


def _ncf_payload(ticker: str, prob_h1: float, prob_h5: float, prob_h20: float) -> dict:
    return {
        "ticker": ticker,
        "last_close_date": "2026-06-25",
        "last_close": 10.0,
        "horizon_ensemble": {
            "direction": "UP" if prob_h20 > 0.5 else "DOWN",
            "calibrated_probability_up": prob_h20,
            "combined_probability_up": prob_h20,
            "confidence": 0.6,
            "weighted_return": 0.01,
            "votes_up": 2,
            "direction_weights": {"1": 0.1, "5": 0.2, "20": 0.7},
        },
        "horizons": {
            "1": {"classification": {"probability_up": prob_h1, "val_auc": 0.55}},
            "5": {"classification": {"probability_up": prob_h5, "val_auc": 0.62}},
            "20": {"classification": {"probability_up": prob_h20, "val_auc": 0.70}},
        },
        "forward_drawdown_risk": {"available": False},
        "forward_upside_reward": {"available": False},
    }


def test_live_ncf_context_prefers_json_signals(tmp_path: Path) -> None:
    module = _load_module()
    p631 = tmp_path / "ncf_00631l_latest.json"
    p632 = tmp_path / "ncf_00632r_latest.json"
    p631.write_text(json.dumps(_ncf_payload("00631L.TW", 0.35, 0.45, 0.33)), encoding="utf-8")
    p632.write_text(json.dumps(_ncf_payload("00632R.TW", 0.55, 0.63, 0.77)), encoding="utf-8")

    context = module._load_ncf_live_advisory_context(p631, p632)

    assert context["status"] == "available"
    assert context["source"] == "live_ncf_json"
    assert context["date"] == "2026-06-25"
    assert context["market_direction"] == "DOWN"
    assert context["shadow_recommendation"]["policy"] == "bearish_reduce_40"
    assert context["decision_policy_effect"] == "report_only_no_weight_change"
