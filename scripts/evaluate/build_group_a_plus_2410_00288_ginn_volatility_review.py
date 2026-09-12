#!/usr/bin/env python3
"""Review arXiv 2410.00288 GINN ideas for GroupA++ / NCF00631L.

Research-only. This report records transfer candidates from the paper and
checks the current repository coverage. It never changes live weights, golden
artifacts, strategy manifests, or order generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.gjr_garch_shadow import (  # noqa: E402
    compute_gjr_garch_shadow,
)

DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260907.csv"
DEFAULT_GJR = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_garch_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2410_00288_ginn_volatility_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2410_00288_ginn_volatility_review.md"
DEFAULT_PAPER = Path("/mnt/c/Users/isaac/Downloads/2410.00288.pdf")
VOL_FEATURE_HINTS = (
    "garch_forecast_variance",
    "gjr_forecast_variance",
    "garch_persistence",
    "garch_informed_volatility",
    "forecast_variance_ratio_gjr_over_symmetric",
)


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _panel_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    frame = pd.read_csv(path, encoding="utf-8-sig")
    cols = list(frame.columns)
    date_col = "date" if "date" in frame.columns else None
    has_vol_cols = [col for col in cols if "vol" in col.lower() or "garch" in col.lower()]
    explicit_ginn_inputs = [col for col in cols if col in VOL_FEATURE_HINTS]
    summary = {
        "status": "available",
        "path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
        "rows": int(len(frame)),
        "columns": cols,
        "date_min": None,
        "date_max": None,
        "has_generic_volatility_columns": has_vol_cols,
        "has_explicit_garch_informed_columns": explicit_ginn_inputs,
    }
    if date_col:
        dates = pd.to_datetime(frame[date_col], errors="coerce").dropna()
        if not dates.empty:
            summary["date_min"] = str(dates.min().date())
            summary["date_max"] = str(dates.max().date())
    return summary


def _gjr_summary(path: Path, as_of: str, recompute: bool) -> dict[str, Any]:
    payload = _load_json(path)
    if recompute or not payload:
        payload = {
            "schema_version": 1,
            "report_type": "gjr_garch_shadow",
            "as_of": as_of,
            **compute_gjr_garch_shadow(DB_PATH, as_of),
        }
    return {
        "status": payload.get("status"),
        "path": str(path.relative_to(PROJECT_ROOT) if path.exists() and path.is_relative_to(PROJECT_ROOT) else path),
        "date": payload.get("date"),
        "policy": payload.get("policy"),
        "evidence_level": payload.get("evidence_level"),
        "latest_return": payload.get("latest_return"),
        "symmetric_persistence": (payload.get("symmetric_garch") or {}).get("persistence"),
        "gjr_persistence": (payload.get("gjr_garch") or {}).get("persistence"),
        "gjr_gamma": ((payload.get("gjr_garch") or {}).get("params") or {}).get("gamma"),
        "lr_p_value": (payload.get("likelihood_ratio_test") or {}).get("p_value"),
        "vol_model_disagreement": payload.get("vol_model_disagreement"),
        "gjr_asymmetry_shock": payload.get("gjr_asymmetry_shock"),
        "forecast_variance_ratio_gjr_over_symmetric": payload.get("forecast_variance_ratio_gjr_over_symmetric"),
        "decision_boundary": payload.get("decision_boundary"),
    }


def build_report(panel_path: Path, gjr_path: Path, paper_path: Path, as_of: str, recompute_gjr: bool) -> dict[str, Any]:
    panel = _panel_summary(panel_path)
    gjr = _gjr_summary(gjr_path, as_of, recompute_gjr)
    explicit_garch_cols = panel.get("has_explicit_garch_informed_columns") or []
    can_add_features = panel.get("status") == "available" and not explicit_garch_cols

    transfer_items = [
        {
            "idea": "GARCH-informed volatility teacher for NCF00631L",
            "paper_basis": "GINN trains an LSTM volatility head with a weighted loss against realized variance and GARCH variance.",
            "group_a_plusplus_mapping": "Add PIT GARCH/GJR forecast variance, variance-ratio, persistence, and negative-shock flags to the NCF00631L feature panel.",
            "recommended_status": "candidate_shadow",
            "latest_strategy_change": False,
            "why": "Current NCF direction accuracy is only modest; volatility features can improve confidence/risk conditioning, but need purged walk-forward proof before allocation use.",
        },
        {
            "idea": "Auxiliary volatility head with GINN loss",
            "paper_basis": "The paper's best lambda is 0.01; GINN-0 is also strong, implying GARCH can act as a robust teacher/regularizer.",
            "group_a_plusplus_mapping": "Train an auxiliary NN head to forecast next-day or H5/H20 realized variance while the existing NCF direction/tail heads remain primary.",
            "recommended_status": "candidate_shadow",
            "latest_strategy_change": False,
            "why": "This is low-risk as a side objective, but promotion must show direction-calibration or tail-risk improvement, not just lower volatility MSE.",
        },
        {
            "idea": "Volatility-conditioned abstention / no-add gate for 00631L",
            "paper_basis": "Volatility has more stable second-moment structure than price direction, but spike timing remains hard.",
            "group_a_plusplus_mapping": "Use high forecast variance or GARCH/GJR disagreement only to raise add thresholds or require human review; never as an automatic bullish/bearish signal.",
            "recommended_status": "candidate_shadow",
            "latest_strategy_change": False,
            "why": "This matches the current shadow-only GJR boundary and avoids converting a risk forecast into directional alpha.",
        },
        {
            "idea": "Dedicated time-series holdout for lambda/model selection",
            "paper_basis": "The paper avoids ordinary K-fold leakage and selects lambda on a separate time-series dataset.",
            "group_a_plusplus_mapping": "Use existing purged walk-forward windows plus a separate tuning window for lambda/teacher weight and freeze before live evaluation.",
            "recommended_status": "governance_requirement",
            "latest_strategy_change": False,
            "why": "Prevents overfitting a 00631L-specific volatility head to the latest live window.",
        },
    ]

    blocked_items = [
        {
            "idea": "Directly set lambda=0.01 in production",
            "reason": "The paper tuned lambda on global equity indices, not 00631L Taiwan leveraged ETF data.",
        },
        {
            "idea": "Use volatility forecast as a direction classifier",
            "reason": "The paper predicts variance, not return direction; mapping high volatility to UP/DOWN would be an unsupported extra assumption.",
        },
        {
            "idea": "Replace current GJR shadow with active allocation rule",
            "reason": "The repository already records significant in-sample asymmetry but failed earlier OOS promotion gates; current GJR policy remains shadow_only_no_weight_change.",
        },
        {
            "idea": "Adopt the full 3-layer 256-width LSTM blindly",
            "reason": "NCF00631L sample size is much smaller than the paper's index datasets; a smaller ablation-first model is safer.",
        },
    ]

    decision = {
        "promotion_allowed_now": False,
        "latest_strategy_weight_change_allowed": False,
        "recommended_next_step": "build_garch_informed_ncf00631l_shadow_panel_and_purged_walkforward",
        "priority": "medium_high",
        "reason": (
            "The paper offers a useful volatility-feature and auxiliary-loss design, "
            "but current evidence only supports shadow integration. Existing GJR-GARCH "
            "is already diagnostic-only, and the active NCF panel lacks explicit GARCH-informed features."
        ),
    }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2410_00288_ginn_volatility_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "path": str(paper_path),
            "title": "GARCH-Informed Neural Networks for Volatility Prediction in Financial Markets",
            "arxiv_id": "2410.00288",
            "main_claims_used": [
                "GARCH forecasts can regularize an LSTM volatility model through a combined loss.",
                "A 90-day rolling window is used for one-step variance prediction.",
                "The reported best lambda is 0.01; lambda=0 GINN-0 remains competitive.",
                "GINN/GINN-0 are smoother than GARCH and can understate volatility peaks.",
                "The paper evaluates volatility R2/MSE/MAE, not trading PnL or direction accuracy.",
            ],
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "panel_coverage": panel,
        "current_gjr_garch_shadow": gjr,
        "gap_assessment": {
            "ncf00631l_has_explicit_garch_informed_features": bool(explicit_garch_cols),
            "can_add_shadow_features_without_live_weight_change": bool(can_add_features),
            "existing_gjr_shadow_already_covers_asymmetry_diagnostic": gjr.get("status") == "available",
            "missing_required_validation": [
                "Purged walk-forward comparison of baseline NCF vs GARCH-informed NCF.",
                "Ablation separating realized-vol columns, symmetric GARCH, GJR ratio, and auxiliary loss.",
                "Direction metrics: accuracy, balanced accuracy, AUC, Brier, calibration slope.",
                "Portfolio metrics: final value, max drawdown, worst 20d return, turnover, missed rebound cost.",
                "Spike-timing review because the paper warns smooth GINN outputs can miss peak magnitude.",
            ],
        },
        "transfer_candidates": transfer_items,
        "blocked_or_deferred_items": blocked_items,
        "decision": decision,
    }


def _fmt_pct(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "NA"


def _fmt_float(value: Any, digits: int = 6) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "NA"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    gjr = report["current_gjr_garch_shadow"]
    panel = report["panel_coverage"]
    decision = report["decision"]
    lines = [
        "# 2410.00288 GINN Volatility Review",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: promotion_allowed_now=`{decision['promotion_allowed_now']}`",
        f"- Latest strategy weight change: `{decision['latest_strategy_weight_change_allowed']}`",
        f"- Recommended next step: `{decision['recommended_next_step']}`",
        "",
        "## Paper Takeaways",
        "",
        "- GINN uses GARCH variance as a teacher/regularizer for an LSTM volatility model.",
        "- The paper's best reported lambda is 0.01, and GINN-0 is close, so the GARCH teacher carries most of the useful regularization.",
        "- The model is evaluated on volatility R2/MSE/MAE, not direction accuracy or trading PnL.",
        "- The authors warn that GINN is smoother than GARCH and can miss peak magnitude/timing.",
        "",
        "## Current Coverage",
        "",
        f"- NCF00631L panel: `{panel.get('path')}` rows=`{panel.get('rows')}` dates=`{panel.get('date_min')}` to `{panel.get('date_max')}`",
        f"- Explicit GARCH-informed panel columns: `{panel.get('has_explicit_garch_informed_columns')}`",
        f"- Existing GJR shadow status: `{gjr.get('status')}` date=`{gjr.get('date')}` policy=`{gjr.get('policy')}` evidence=`{gjr.get('evidence_level')}`",
        f"- GJR gamma: `{_fmt_float(gjr.get('gjr_gamma'))}` LR p-value=`{_fmt_float(gjr.get('lr_p_value'))}`",
        f"- GJR/symmetric variance ratio: `{_fmt_float(gjr.get('forecast_variance_ratio_gjr_over_symmetric'))}` disagreement=`{gjr.get('vol_model_disagreement')}` asymmetry_shock=`{gjr.get('gjr_asymmetry_shock')}`",
        "",
        "## Transfer Candidates",
        "",
        "| idea | status | latest strategy change | mapping |",
        "|---|---|---:|---|",
    ]
    for item in report["transfer_candidates"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["idea"],
                    item["recommended_status"],
                    str(item["latest_strategy_change"]),
                    item["group_a_plusplus_mapping"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## Deferred", ""])
    for item in report["blocked_or_deferred_items"]:
        lines.append(f"- {item['idea']}: {item['reason']}")
    lines.extend(
        [
            "",
            "## Required Validation",
            "",
        ]
    )
    for item in report["gap_assessment"]["missing_required_validation"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "可以導入，但只應先導入為 shadow：新增 GARCH-informed NCF00631L volatility feature / auxiliary head / abstention gate 評估。暫時不應改 groupA++ 最新策略權重、golden1_0531 或 golden2_0830。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--gjr-shadow", default=str(DEFAULT_GJR))
    parser.add_argument("--paper", default=str(DEFAULT_PAPER))
    parser.add_argument("--as-of", default="2026-09-04")
    parser.add_argument("--recompute-gjr", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        _resolve(args.panel),
        _resolve(args.gjr_shadow),
        _resolve(args.paper),
        args.as_of,
        args.recompute_gjr,
    )
    write_outputs(report, _resolve(args.output), _resolve(args.markdown))
    print(f"decision={report['decision']['recommended_next_step']}")
    print(f"promotion_allowed_now={report['decision']['promotion_allowed_now']}")
    print(f"latest_strategy_change={report['decision']['latest_strategy_weight_change_allowed']}")
    print(f"ncf_explicit_garch_cols={report['gap_assessment']['ncf00631l_has_explicit_garch_informed_features']}")
    print(f"output={_resolve(args.output)}")
    print(f"markdown={_resolve(args.markdown)}")


if __name__ == "__main__":
    main()
