#!/usr/bin/env python3
"""Build a readiness review for the RG-ResMoE-lite volatility gate shadow.

This consumes scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py
output and writes a compact JSON/Markdown promotion-readiness summary. It is
research-only and never changes GroupA+ target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INPUT = PROJECT_ROOT / "results" / "group_a_plus_rg_resmoe_volatility_gate_pilot_multi_highvol_q080_b135_20260820.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rg_resmoe_volatility_gate_readiness_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rg_resmoe_volatility_gate_readiness_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "rg_resmoe_volatility_gate_readiness_review" / "history"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _pct(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _pathway_summary(metric: dict[str, Any]) -> dict[str, Any]:
    dm = metric.get("dm_qlike_vs_base") or {}
    return {
        "n": metric.get("n"),
        "qlike_improvement_pct": _pct(metric.get("qlike_improvement_pct")),
        "win_rate_vs_base": _pct(metric.get("win_rate_vs_base")),
        "dm_status": dm.get("status"),
        "dm_p_value": _pct(dm.get("p_value")),
        "dm_a_more_accurate": dm.get("a_more_accurate"),
        "dm_significant_at_5pct": dm.get("significant_at_5pct"),
    }


def _ticker_summary(ticker: str, payload: dict[str, Any]) -> dict[str, Any]:
    horizons: dict[str, Any] = {}
    for horizon, result in (payload.get("results") or {}).items():
        pooled = (result.get("pooled") or {}).get("gate_pathway_soft") or {}
        hv_only = (result.get("pooled") or {}).get("high_vol_only_gate_pathway_soft") or {}
        high_vol = ((result.get("slices") or {}).get("top_realized_vol_decile") or {}).get("gate_pathway_soft") or {}
        recent = ((result.get("slices") or {}).get("recent_2025_2026") or {}).get("gate_pathway_soft") or {}
        var_pooled = (((result.get("var_calibration") or {}).get("pooled") or {}).get("gate_pathway_soft") or {})
        residual_var_pooled = (((result.get("residual_var_calibration") or {}).get("pooled") or {}).get("gate_pathway_soft") or {})
        horizons[str(horizon)] = {
            "pooled_soft_gate": _pathway_summary(pooled),
            "pooled_high_vol_only_soft_gate": _pathway_summary(hv_only),
            "top_realized_vol_decile_improvement_pct": _pct(high_vol.get("qlike_improvement_pct")),
            "recent_2025_2026_improvement_pct": _pct(recent.get("qlike_improvement_pct")),
            "gaussian_var_calibration": {
                "var_5pct": var_pooled.get("var_5pct") or {},
                "var_1pct": var_pooled.get("var_1pct") or {},
            },
            "residual_var_calibration": {
                "var_5pct": residual_var_pooled.get("var_5pct") or {},
                "var_1pct": residual_var_pooled.get("var_1pct") or {},
            },
        }
    decision = payload.get("promotion_decision") or {}
    high_vol_only_decision = payload.get("high_vol_only_promotion_decision") or {}
    return {
        "ticker": ticker,
        "decision": decision.get("decision"),
        "high_vol_only_decision": high_vol_only_decision.get("decision"),
        "blockers": decision.get("blockers") or [],
        "high_vol_only_blockers": high_vol_only_decision.get("blockers") or [],
        "horizons": horizons,
    }


def _calibration_passed(calibration: dict[str, Any]) -> bool:
    return calibration.get("status") == "ok" and calibration.get("kupiec_reject_5pct") is False


def _horizon_tail_ready(horizon_review: dict[str, Any]) -> bool:
    residual_var = horizon_review.get("residual_var_calibration") or {}
    return _calibration_passed(residual_var.get("var_5pct") or {}) and _calibration_passed(
        residual_var.get("var_1pct") or {}
    )


def _layered_decision(ticker_reviews: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    tail_blockers: list[str] = []
    h5_blockers: list[str] = []
    h5_details: dict[str, Any] = {}

    for ticker, review in ticker_reviews.items():
        horizons = review.get("horizons") or {}
        for horizon, horizon_review in horizons.items():
            if not _horizon_tail_ready(horizon_review):
                tail_blockers.append(f"{ticker}:h{horizon}_tail_calibration_not_ready")

        h5 = horizons.get("5") or {}
        h5_hv = h5.get("pooled_high_vol_only_soft_gate") or {}
        h5_improvement = h5_hv.get("qlike_improvement_pct")
        h5_dm_p = h5_hv.get("dm_p_value")
        h5_more_accurate = h5_hv.get("dm_a_more_accurate")
        h5_tail_ready = _horizon_tail_ready(h5)
        ticker_h5_ready = (
            h5_tail_ready
            and h5_improvement is not None
            and float(h5_improvement) > 0.0
            and h5_more_accurate is True
        )
        h5_details[ticker] = {
            "ready": bool(ticker_h5_ready),
            "qlike_improvement_pct": h5_improvement,
            "dm_p_value": h5_dm_p,
            "dm_a_more_accurate": h5_more_accurate,
            "tail_ready": h5_tail_ready,
            "note": "h5_high_vol_only_shadow_advisory_reference_no_weight_change",
        }
        if not ticker_h5_ready:
            h5_blockers.append(f"{ticker}:h5_high_vol_shadow_not_ready")

    # Full promotion requires the existing strict blockers to be empty.
    full_ready = not blockers
    # Tail layer is useful independently of forecast promotion: it only checks
    # calibrated residual VaR coverage.
    tail_ready = not tail_blockers
    # Partial H5 layer is intentionally weaker than full promotion: positive
    # high-vol-only H5 improvement + calibrated H5 tail, but not necessarily
    # DM significant for both tickers.
    h5_partial_ready = (
        not h5_blockers
        and all((detail.get("qlike_improvement_pct") or 0.0) > 0.0 for detail in h5_details.values())
    )

    return {
        "full_promotion_ready": bool(full_ready),
        "tail_calibration_ready": bool(tail_ready),
        "h5_high_vol_shadow_ready": "partial" if h5_partial_ready and not full_ready else bool(h5_partial_ready),
        "trade_policy": "shadow_only_no_weight_change",
        "blockers": {
            "full_promotion": blockers,
            "tail_calibration": tail_blockers,
            "h5_high_vol_shadow": h5_blockers,
        },
        "h5_high_vol_shadow_details": h5_details,
        "interpretation": (
            "Full promotion remains blocked; calibrated tail references and H5 high-vol-only "
            "advisory can be observed in shadow without changing target weights."
            if h5_partial_ready and tail_ready and not full_ready
            else "Keep all RG-ResMoE outputs in research shadow."
        ),
    }


def build_review(payload: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    by_ticker_raw = payload.get("by_ticker")
    if not isinstance(by_ticker_raw, dict):
        raise ValueError("pilot payload must contain by_ticker; rerun evaluator with current script")
    ticker_reviews = {
        ticker: _ticker_summary(ticker, ticker_payload)
        for ticker, ticker_payload in by_ticker_raw.items()
    }
    blockers: list[str] = []
    for ticker, review in ticker_reviews.items():
        for blocker in review["blockers"]:
            blockers.append(f"{ticker}:{blocker}")
    decision = "do_not_promote_keep_shadow" if blockers else "eligible_for_manual_review_not_auto_promote"
    layered = _layered_decision(ticker_reviews, blockers)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_rg_resmoe_volatility_gate_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source_path),
        "research_source": "arXiv:2608.12251 RG-ResMoE integration-pathway pilot",
        "policy": "research_only_no_weight_change",
        "decision": decision,
        "layered_decision": layered,
        "blockers": blockers,
        "ticker_reviews": ticker_reviews,
        "promotion_requirements": [
            "soft gate must show positive pooled QLIKE improvement for every tracked horizon",
            "DM test must support lower QLIKE than frozen HAR-RV base at 5% significance",
            "0050 and 00631L must both pass before any combined gate can enter manual promotion review",
            "VaR breach rates must remain calibrated against 5% and 1% nominal levels in pooled and high-vol slices",
            "separate signed promotion review is required before target-weight or execution-guard wiring",
        ],
    }


def _fmt_pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2f}%"


def render_markdown(review: dict[str, Any]) -> str:
    layered = review.get("layered_decision") or {}
    lines = [
        "# RG-ResMoE Volatility Gate Readiness Review",
        "",
        f"- Generated: `{review['generated_at']}`",
        f"- Decision: `{review['decision']}`",
        f"- Policy: `{review['policy']}`",
        f"- Source: `{review['source']}`",
        "",
        "## Layered Decision",
        "",
        f"- Full promotion ready: `{layered.get('full_promotion_ready')}`",
        f"- Tail calibration ready: `{layered.get('tail_calibration_ready')}`",
        f"- H5 high-vol shadow ready: `{layered.get('h5_high_vol_shadow_ready')}`",
        f"- Trade policy: `{layered.get('trade_policy')}`",
        f"- Interpretation: {layered.get('interpretation')}",
        "",
        "## Blockers",
        "",
    ]
    blockers = review.get("blockers") or []
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- none")
    h5_details = layered.get("h5_high_vol_shadow_details") or {}
    if h5_details:
        lines.extend(["", "## H5 Shadow Details", ""])
        lines.extend([
            "| Ticker | Ready | QLIKE Improvement | DM p-value | Tail Ready |",
            "|---|---:|---:|---:|---:|",
        ])
        for ticker, detail in h5_details.items():
            dm_p = detail.get("dm_p_value")
            dm_text = "n/a" if dm_p is None else f"{float(dm_p):.4f}"
            lines.append(
                "| "
                f"{ticker} | "
                f"{detail.get('ready')} | "
                f"{_fmt_pct(detail.get('qlike_improvement_pct'))} | "
                f"{dm_text} | "
                f"{detail.get('tail_ready')} |"
            )
    lines.extend(["", "## Ticker Summary", ""])
    for ticker, ticker_review in (review.get("ticker_reviews") or {}).items():
        lines.extend([
            f"### {ticker}",
            "",
            f"- Decision: `{ticker_review['decision']}`",
        ])
        if ticker_review.get("blockers"):
            lines.append(f"- Blockers: `{', '.join(ticker_review['blockers'])}`")
        lines.append(f"- High-vol-only decision: `{ticker_review.get('high_vol_only_decision')}`")
        if ticker_review.get("high_vol_only_blockers"):
            lines.append(f"- High-vol-only blockers: `{', '.join(ticker_review['high_vol_only_blockers'])}`")
        lines.extend([
            "",
            "| Horizon | Full Soft QLIKE | Full DM p | HV-only QLIKE | HV-only DM p | Top Vol Decile | Recent 2025-2026 | Cal VaR5 Breach | Cal VaR5 Kupiec p | Cal VaR1 Breach | Cal VaR1 Kupiec p |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for horizon, horizon_review in (ticker_review.get("horizons") or {}).items():
            pooled = horizon_review["pooled_soft_gate"]
            hv_only = horizon_review.get("pooled_high_vol_only_soft_gate") or {}
            p_value = pooled.get("dm_p_value")
            p_text = "n/a" if p_value is None else f"{float(p_value):.4f}"
            hv_p_value = hv_only.get("dm_p_value")
            hv_p_text = "n/a" if hv_p_value is None else f"{float(hv_p_value):.4f}"
            gaussian_var = horizon_review.get("gaussian_var_calibration") or {}
            residual_var = horizon_review.get("residual_var_calibration") or {}
            var5 = gaussian_var.get("var_5pct") or {}
            var1 = gaussian_var.get("var_1pct") or {}
            cal_var5 = residual_var.get("var_5pct") or {}
            cal_var1 = residual_var.get("var_1pct") or {}
            var5_breach = var5.get("breach_rate")
            var1_breach = var1.get("breach_rate")
            cal_var5_breach = cal_var5.get("breach_rate")
            cal_var1_breach = cal_var1.get("breach_rate")
            var5_breach_text = "n/a" if var5_breach is None else f"{float(var5_breach):.3f}"
            var1_breach_text = "n/a" if var1_breach is None else f"{float(var1_breach):.3f}"
            cal_var5_breach_text = "n/a" if cal_var5_breach is None else f"{float(cal_var5_breach):.3f}"
            cal_var1_breach_text = "n/a" if cal_var1_breach is None else f"{float(cal_var1_breach):.3f}"
            cal_var5_p = cal_var5.get("kupiec_p_value")
            cal_var1_p = cal_var1.get("kupiec_p_value")
            cal_var5_p_text = "n/a" if cal_var5_p is None else f"{float(cal_var5_p):.4f}"
            cal_var1_p_text = "n/a" if cal_var1_p is None else f"{float(cal_var1_p):.4f}"
            lines.append(
                "| "
                f"H{horizon} | "
                f"{_fmt_pct(pooled.get('qlike_improvement_pct'))} | "
                f"{p_text} | "
                f"{_fmt_pct(hv_only.get('qlike_improvement_pct'))} | "
                f"{hv_p_text} | "
                f"{_fmt_pct(horizon_review.get('top_realized_vol_decile_improvement_pct'))} | "
                f"{_fmt_pct(horizon_review.get('recent_2025_2026_improvement_pct'))} | "
                f"{cal_var5_breach_text} | "
                f"{cal_var5_p_text} | "
                f"{cal_var1_breach_text} | "
                f"{cal_var1_p_text} |"
            )
        lines.append("")
    lines.extend(["## Promotion Requirements", ""])
    lines.extend(f"- {item}" for item in review.get("promotion_requirements") or [])
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return history_dir / f"rg_resmoe_volatility_gate_readiness_review_{stamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    review = build_review(_load_json(input_path), source_path=input_path)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(review), encoding="utf-8")
    if not args.no_history:
        history_path = _history_path(Path(args.history_dir))
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Readiness review JSON: {output_json}")
    print(f"Readiness review MD: {output_md}")
    print(f"Decision: {review['decision']}")
    if review.get("blockers"):
        print(f"Blockers: {len(review['blockers'])}")


if __name__ == "__main__":
    main()
