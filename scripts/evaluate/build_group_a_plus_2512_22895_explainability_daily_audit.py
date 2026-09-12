#!/usr/bin/env python3
"""Build a daily sleeve explainability audit inspired by arXiv 2512.22895 SAMP-HDRL."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "results/group_a_combined_live_latest.json"
DEFAULT_NCF_0050 = PROJECT_ROOT / "results/ncf_0050_latest_20260826_debug.json"
DEFAULT_NCF_00631L = PROJECT_ROOT / "results/ncf_00631l_latest_20260826_debug.json"
DEFAULT_DYNAMIC_BUCKET = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_dynamic_bucket_shadow.json"
DEFAULT_REBOUND_GATE = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_rebound_gate_00631l_shadow.json"
DEFAULT_CASH_TEMP = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_cash_temperature_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_explainability_daily_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_explainability_daily_audit/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> float:
    return round(_f(value) * 100.0, 4)


def _ncf_summary(payload: dict[str, Any]) -> dict[str, Any]:
    ens = payload.get("horizon_ensemble") if isinstance(payload.get("horizon_ensemble"), dict) else {}
    dd = payload.get("forward_drawdown_risk") if isinstance(payload.get("forward_drawdown_risk"), dict) else {}
    up = payload.get("forward_upside_reward") if isinstance(payload.get("forward_upside_reward"), dict) else {}
    return {
        "last_close_date": payload.get("last_close_date"),
        "last_close": payload.get("last_close"),
        "direction": ens.get("direction"),
        "probability_up": ens.get("combined_probability_up"),
        "calibrated_probability_up": ens.get("calibrated_probability_up"),
        "confidence": ens.get("confidence"),
        "weighted_return": ens.get("weighted_return"),
        "predicted_close": ens.get("predicted_close"),
        "forward_drawdown_gt5_prob": dd.get("probability"),
        "forward_upside_gt5_prob": up.get("probability"),
    }


def _net_exposure(weights: dict[str, Any]) -> dict[str, float]:
    w50 = _f(weights.get("0050.TW"))
    w631 = _f(weights.get("00631L.TW"))
    w632 = _f(weights.get("00632R.TW"))
    long_exposure = w50 + 2.0 * w631
    hedge_exposure = w632
    return {
        "long_exposure_approx": round(long_exposure, 6),
        "hedge_exposure_approx": round(hedge_exposure, 6),
        "net_directional_exposure_approx": round(long_exposure - hedge_exposure, 6),
    }


def build_audit(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    ncf_0050_path: Path = DEFAULT_NCF_0050,
    ncf_00631l_path: Path = DEFAULT_NCF_00631L,
    dynamic_bucket_path: Path = DEFAULT_DYNAMIC_BUCKET,
    rebound_gate_path: Path = DEFAULT_REBOUND_GATE,
    cash_temperature_path: Path = DEFAULT_CASH_TEMP,
) -> dict[str, Any]:
    live = _load_json(live_signal_path)
    ncf_0050 = _load_json(ncf_0050_path)
    ncf_00631l = _load_json(ncf_00631l_path)
    bucket = _load_json(dynamic_bucket_path)
    rebound = _load_json(rebound_gate_path)
    cash_temp = _load_json(cash_temperature_path)

    weights = dict(live.get("target_weights") or {})
    weights["cash"] = _f(live.get("target_cash_weight"))
    exposure = _net_exposure(weights)
    live_cash = _f(weights.get("cash"))
    cash_decision = cash_temp.get("decision") if isinstance(cash_temp.get("decision"), dict) else {}
    bucket_decision = bucket.get("decision") if isinstance(bucket.get("decision"), dict) else {}
    rebound_decision = rebound.get("decision") if isinstance(rebound.get("decision"), dict) else {}
    n50 = _ncf_summary(ncf_0050)
    n631 = _ncf_summary(ncf_00631l)

    ncf_0050_strength = "neutral_to_mild_bullish"
    if _f(n50.get("confidence")) >= 0.65 and _f(n50.get("probability_up")) >= 0.65:
        ncf_0050_strength = "bullish"
    elif _f(n50.get("probability_up")) < 0.50:
        ncf_0050_strength = "weak"
    ncf_00631l_strength = "neutral"
    if _f(n631.get("confidence")) >= 0.65 and _f(n631.get("probability_up")) >= 0.65:
        ncf_00631l_strength = "bullish_but_trend_following"
    elif _f(n631.get("probability_up")) < 0.50:
        ncf_00631l_strength = "weak"

    supports_631_add = bool(bucket_decision.get("supports_new_00631l_add")) and bool(
        rebound_decision.get("supports_new_00631l_add_today")
    )
    supports_632_hedge = bool(bucket_decision.get("supports_00632r_hedge"))
    supports_more_cash = bool(cash_decision.get("supports_increasing_cash"))
    ambiguous_mix = bool(bucket_decision.get("ambiguous_leverage_inverse_mix")) or (
        _f(weights.get("00631L.TW")) > 0 and _f(weights.get("00632R.TW")) > 0
    )

    sleeve_audit = [
        {
            "sleeve": "0050_core",
            "target_weight_pct": _pct(weights.get("0050.TW")),
            "role": "bullish_core",
            "evidence": [
                f"live target keeps 0050 at {_pct(weights.get('0050.TW'))}%",
                f"NCF 0050 direction={n50.get('direction')} prob={n50.get('probability_up')} confidence={n50.get('confidence')}",
                f"dynamic bucket quality assets={bucket_decision.get('quality_assets_latest')}",
            ],
            "audit_view": ncf_0050_strength,
        },
        {
            "sleeve": "00631L_leverage",
            "target_weight_pct": _pct(weights.get("00631L.TW")),
            "role": "leveraged_bullish_sleeve",
            "evidence": [
                f"NCF 00631L direction={n631.get('direction')} prob={n631.get('probability_up')} confidence={n631.get('confidence')}",
                f"dynamic bucket supports add={bucket_decision.get('supports_new_00631l_add')}",
                f"rebound gate supports today={rebound_decision.get('supports_new_00631l_add_today')}",
            ],
            "audit_view": "do_not_add_aggressively" if not supports_631_add else "reviewable_add",
        },
        {
            "sleeve": "00632R_hedge",
            "target_weight_pct": _pct(weights.get("00632R.TW")),
            "role": "downside_hedge",
            "evidence": [
                f"dynamic bucket supports hedge={bucket_decision.get('supports_00632r_hedge')}",
                f"net exposure approx={exposure.get('net_directional_exposure_approx')}",
                "hedge has expected drag if Taiwan market rises",
            ],
            "audit_view": "hedge_has_reason_but_size_needs_manual_review" if supports_632_hedge else "hedge_not_supported",
        },
        {
            "sleeve": "cash_defense",
            "target_weight_pct": _pct(weights.get("cash")),
            "role": "risk_free_baseline",
            "evidence": [
                f"live cash={round(live_cash * 100.0, 4)}%",
                f"cash-temperature diagnostic={cash_decision.get('reference_diagnostic_cash_weight')}",
                f"cash bias={cash_decision.get('live_cash_bias')}",
            ],
            "audit_view": "cash_likely_low_for_conservative_execution" if supports_more_cash else "cash_near_diagnostic",
        },
    ]

    overall_view = "bullish_core_with_defensive_overlay"
    if ambiguous_mix and supports_more_cash:
        overall_view = "ambiguous_leverage_inverse_mix_prefer_conservative_cash"
    elif exposure["net_directional_exposure_approx"] < 0:
        overall_view = "net_bearish"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_explainability_daily_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": live.get("actual_data_date") or live.get("requested_as_of_date"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "imported_concept": "hierarchical_agent_explainability_audit",
            "not_imported": ["SHAP_live_gate", "hierarchical_DRL_training", "target_weight_generation"],
        },
        "live_signal": {
            "requested_as_of_date": live.get("requested_as_of_date"),
            "actual_data_date": live.get("actual_data_date"),
            "signal_status": live.get("signal_status"),
            "signal_reason": live.get("signal_reason"),
            "action_label": live.get("action_label"),
            "target_weights": weights,
            "exposure": exposure,
        },
        "ncf": {
            "0050": n50,
            "00631L": n631,
        },
        "shadow_inputs": {
            "dynamic_bucket_decision": bucket_decision,
            "rebound_gate_decision": rebound_decision,
            "cash_temperature_decision": cash_decision,
        },
        "sleeve_audit": sleeve_audit,
        "decision": {
            "overall_view": overall_view,
            "is_clean_bullish_signal": False,
            "is_clean_bearish_signal": False,
            "supports_00631l_aggressive_add": bool(supports_631_add),
            "supports_00632r_as_hedge": bool(supports_632_hedge),
            "supports_more_cash_for_conservative_execution": bool(supports_more_cash),
            "ambiguous_leverage_inverse_mix": bool(ambiguous_mix),
            "target_weight_change_allowed": False,
            "production_effect": "none",
            "summary": "Daily audit explains the sleeves, but it is review-only and cannot change A21.18 weights.",
        },
    }


def write_audit(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_explainability_daily_audit_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--ncf-0050", default=str(DEFAULT_NCF_0050))
    parser.add_argument("--ncf-00631l", default=str(DEFAULT_NCF_00631L))
    parser.add_argument("--dynamic-bucket", default=str(DEFAULT_DYNAMIC_BUCKET))
    parser.add_argument("--rebound-gate", default=str(DEFAULT_REBOUND_GATE))
    parser.add_argument("--cash-temperature", default=str(DEFAULT_CASH_TEMP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_audit(
        live_signal_path=_resolve(args.live_signal),
        ncf_0050_path=_resolve(args.ncf_0050),
        ncf_00631l_path=_resolve(args.ncf_00631l),
        dynamic_bucket_path=_resolve(args.dynamic_bucket),
        rebound_gate_path=_resolve(args.rebound_gate),
        cash_temperature_path=_resolve(args.cash_temperature),
    )
    write_audit(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
