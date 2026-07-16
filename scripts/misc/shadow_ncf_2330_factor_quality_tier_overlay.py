#!/usr/bin/env python3
"""Shadow-test the ncf_2330 checklist factor-quality overlay on 00631L tiers.

This does not change production weights. It starts from the existing
`evaluate_ncf_2330_00631l_tier.py` advisory tier labels, then tests whether a
research-only checklist overlay should adjust 00631L suitability:

  base tier 3 -> adjusted tier 2
  base tier 2 -> adjusted tier 1
  base tier 1 -> adjusted tier 1
  base tier 0 -> adjusted tier 0

It also tests a counter-hypothesis: when the overlay flags high valuation /
technical extension but the base tier is already constructive, the signal may
be a late-bull momentum confirmation rather than a de-risking signal.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.misc.evaluate_ncf_2330_00631l_tier import (  # noqa: E402
    OUT_CSV as BASE_OUT_CSV,
    OUT_JSON as BASE_OUT_JSON,
    PANEL_2330,
    PANEL_631L,
    TierSpec,
    assign_tiers,
    build_feature_frame,
    summarize_tiers,
)
from scripts.report.build_ncf_2330_checklist import RESULTS_DIR, build_checklist  # noqa: E402


OUT_JSON = PROJECT_ROOT / "results" / f"ncf_2330_factor_quality_tier_overlay_shadow_{datetime.now().strftime('%Y%m%d')}.json"
OUT_CSV = PROJECT_ROOT / "results" / f"ncf_2330_factor_quality_tier_overlay_shadow_{datetime.now().strftime('%Y%m%d')}.csv"


@dataclass(frozen=True)
class OverlaySpec:
    name: str
    min_risk_score: float = 4.0
    max_net_score: float = -3.0
    require_bearish_signal: bool = True
    min_base_tier_to_cut: int = 2
    floor_tier: int = 1
    mode: str = "downgrade"


def load_factor_quality_overlay_frame(
    dates: pd.DatetimeIndex,
    *,
    db_path: Path,
    results_dir: Path,
    project_root: Path,
    mode: str = "daily",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt in pd.DatetimeIndex(dates).sort_values():
        report = build_checklist(
            db_path=db_path,
            results_dir=results_dir,
            project_root=project_root,
            mode=mode,
            as_of=str(pd.Timestamp(dt).date()),
        )
        overlay = report.get("factor_quality_overlay") or {}
        row: dict[str, Any] = {
            "date": pd.Timestamp(dt).normalize(),
            "factor_quality_signal": overlay.get("signal"),
            "factor_quality_label": overlay.get("label"),
            "factor_quality_risk_score": overlay.get("risk_score"),
            "factor_quality_opportunity_score": overlay.get("opportunity_score"),
            "factor_quality_net_score": overlay.get("net_score"),
        }
        for name, component in (overlay.get("components") or {}).items():
            if not isinstance(component, dict):
                continue
            row[f"fq_{name}_risk_points"] = component.get("risk_points")
            row[f"fq_{name}_opportunity_points"] = component.get("opportunity_points")
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).set_index("date").sort_index()
    numeric_cols = [
        col for col in out.columns
        if col.startswith("factor_quality_") and col.endswith("_score")
        or col.startswith("fq_")
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def apply_factor_quality_overlay_to_tiers(frame: pd.DataFrame, spec: OverlaySpec) -> pd.DataFrame:
    out = frame.copy()
    risk_score = pd.to_numeric(out.get("factor_quality_risk_score"), errors="coerce")
    net_score = pd.to_numeric(out.get("factor_quality_net_score"), errors="coerce")
    trigger = (risk_score >= float(spec.min_risk_score)) & (net_score <= float(spec.max_net_score))
    if spec.require_bearish_signal:
        trigger &= out.get("factor_quality_signal", pd.Series(index=out.index, dtype=object)).astype(str).eq("bearish")

    base_tier = pd.to_numeric(out["tier"], errors="coerce").fillna(2).astype(int)
    adjusted = base_tier.copy()
    if spec.mode == "momentum_confirm":
        cut_mask = trigger.fillna(False) & (base_tier == 2)
        adjusted.loc[cut_mask] = 3
    elif spec.mode == "no_add":
        cut_mask = trigger.fillna(False) & (base_tier >= 3)
        adjusted.loc[cut_mask] = 2
    else:
        cut_mask = trigger.fillna(False) & (base_tier >= int(spec.min_base_tier_to_cut))
        adjusted.loc[cut_mask] = (base_tier.loc[cut_mask] - 1).clip(lower=int(spec.floor_tier))
    out["base_tier"] = base_tier
    out["tier"] = adjusted
    out["factor_quality_overlay_trigger"] = trigger.fillna(False)
    out["factor_quality_tier_cut"] = base_tier - adjusted
    out["factor_quality_overlay_spec"] = spec.name
    return out


def _affected_summary(frame: pd.DataFrame) -> dict[str, Any]:
    changed = frame[frame["factor_quality_tier_cut"] != 0].dropna(
        subset=["fwd_00631L_vs_0050_excess_20d", "fwd_00631L.TW_mdd_20d"]
    )
    if changed.empty:
        return {"changed_days": 0}
    by_base: dict[str, Any] = {}
    for tier, group in changed.groupby("base_tier"):
        by_base[str(int(tier))] = {
            "days": int(len(group)),
            "mean_excess_20d": float(group["fwd_00631L_vs_0050_excess_20d"].mean()),
            "win_vs_0050_20d": float((group["fwd_00631L_vs_0050_excess_20d"] > 0.0).mean()),
            "bad_mdd_gt5_20d": float((group["fwd_00631L.TW_mdd_20d"] <= -0.05).mean()),
            "avg_fwd_mdd_20d": float(group["fwd_00631L.TW_mdd_20d"].mean()),
        }
    return {
        "changed_days": int(len(changed)),
        "mean_tier_delta": float((changed["tier"] - changed["base_tier"]).mean()),
        "by_base_tier": by_base,
        "mean_excess_20d": float(changed["fwd_00631L_vs_0050_excess_20d"].mean()),
        "win_vs_0050_20d": float((changed["fwd_00631L_vs_0050_excess_20d"] > 0.0).mean()),
        "bad_mdd_gt5_20d": float((changed["fwd_00631L.TW_mdd_20d"] <= -0.05).mean()),
        "avg_fwd_mdd_20d": float(changed["fwd_00631L.TW_mdd_20d"].mean()),
    }


def _overlay_score(
    base_summary: dict[str, Any],
    adjusted_summary: dict[str, Any],
    affected: dict[str, Any],
    spec: OverlaySpec,
) -> float:
    changed_days = int(affected.get("changed_days", 0) or 0)
    if changed_days < 5:
        return -999.0
    base_sep = base_summary.get("separation") or {}
    adj_sep = adjusted_summary.get("separation") or {}
    base_excess = float(base_sep.get("tier3_minus_tier0_excess_20d") or 0.0)
    adj_excess = float(adj_sep.get("tier3_minus_tier0_excess_20d") or 0.0)
    affected_excess = float(affected.get("mean_excess_20d") or 0.0)
    affected_bad_mdd = float(affected.get("bad_mdd_gt5_20d") or 0.0)
    if spec.mode == "momentum_confirm":
        # Prefer upgrades on days where 00631L later outperformed 0050 without
        # adding bad MDD, while preserving tier separation.
        return (
            2.0 * affected_excess
            - 0.20 * affected_bad_mdd
            + 1.0 * (adj_excess - base_excess)
            + min(changed_days, 60) / 600.0
        )
    # Prefer overlays that cut days where 00631L later underperformed 0050 or
    # had bad MDD, while not damaging tier separation.
    return (
        -2.0 * affected_excess
        + 0.20 * affected_bad_mdd
        + 1.0 * (adj_excess - base_excess)
        + min(changed_days, 60) / 600.0
    )


def make_overlay_specs() -> list[OverlaySpec]:
    specs: list[OverlaySpec] = []
    for min_risk in (4.0, 5.0, 6.0):
        for max_net in (-2.0, -3.0, -4.0, -5.0):
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_bearish",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=True,
                )
            )
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_bearish_noadd",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=True,
                    min_base_tier_to_cut=3,
                    floor_tier=2,
                    mode="no_add",
                )
            )
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_bearish_momentum",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=True,
                    min_base_tier_to_cut=2,
                    floor_tier=2,
                    mode="momentum_confirm",
                )
            )
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_scoreonly",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=False,
                )
            )
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_scoreonly_noadd",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=False,
                    min_base_tier_to_cut=3,
                    floor_tier=2,
                    mode="no_add",
                )
            )
            specs.append(
                OverlaySpec(
                    name=f"risk{int(min_risk)}_net{int(abs(max_net))}_scoreonly_momentum",
                    min_risk_score=min_risk,
                    max_net_score=max_net,
                    require_bearish_signal=False,
                    min_base_tier_to_cut=2,
                    floor_tier=2,
                    mode="momentum_confirm",
                )
            )
    return specs


def run_shadow(
    *,
    db_path: Path,
    panel_00631l: Path,
    panel_2330: Path,
    results_dir: Path,
    project_root: Path,
    sample_step: int = 1,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base_features = build_feature_frame(db_path, panel_00631l, panel_2330)
    if start is not None:
        base_features = base_features.loc[pd.Timestamp(start):]
    if end is not None:
        base_features = base_features.loc[: pd.Timestamp(end)]
    base_tiered = assign_tiers(base_features, TierSpec())
    sample_step = max(int(sample_step), 1)
    overlay_dates = pd.DatetimeIndex(base_tiered.index[::sample_step])
    overlay = load_factor_quality_overlay_frame(
        overlay_dates,
        db_path=db_path,
        results_dir=results_dir,
        project_root=project_root,
    )
    overlay = overlay.reindex(base_tiered.index).ffill()
    joined = base_tiered.join(overlay, how="left")
    base_summary = summarize_tiers(base_tiered)

    ranked: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for spec in make_overlay_specs():
        adjusted = apply_factor_quality_overlay_to_tiers(joined, spec)
        adjusted_summary = summarize_tiers(adjusted)
        affected = _affected_summary(adjusted)
        score = _overlay_score(base_summary, adjusted_summary, affected, spec)
        ranked.append({
            "score": score,
            "spec": asdict(spec),
            "summary": adjusted_summary,
            "affected": affected,
        })
        frames[spec.name] = adjusted

    ranked.sort(key=lambda item: item["score"], reverse=True)
    best_name = ranked[0]["spec"]["name"] if ranked else ""
    best_frame = frames[best_name] if best_name else joined
    report = {
        "experiment": "ncf_2330_factor_quality_tier_overlay_shadow",
        "policy": "research_only_no_weight_change",
        "base_tier_eval": {
            "json": str(BASE_OUT_JSON.relative_to(PROJECT_ROOT)),
            "csv": str(BASE_OUT_CSV.relative_to(PROJECT_ROOT)),
        },
        "inputs": {
            "panel_00631l": str(panel_00631l.relative_to(PROJECT_ROOT)) if panel_00631l.is_relative_to(PROJECT_ROOT) else str(panel_00631l),
            "panel_2330": str(panel_2330.relative_to(PROJECT_ROOT)) if panel_2330.is_relative_to(PROJECT_ROOT) else str(panel_2330),
            "db": str(db_path),
            "sample_step": int(sample_step),
            "overlay_sample_rows": int(len(overlay_dates)),
            "start": str(pd.Timestamp(base_tiered.index.min()).date()) if len(base_tiered) else None,
            "end": str(pd.Timestamp(base_tiered.index.max()).date()) if len(base_tiered) else None,
        },
        "base_summary": base_summary,
        "best": ranked[0] if ranked else None,
        "top10": ranked[:10],
        "ranked": ranked,
        "tier_overlay_rule": {
            "downgrade": {
                "0": "unchanged",
                "1": "unchanged",
                "2": "downgrade_to_1_when_triggered",
                "3": "downgrade_to_2_when_triggered",
            },
            "no_add": {
                "0": "unchanged",
                "1": "unchanged",
                "2": "unchanged",
                "3": "cap_to_2_when_triggered",
            },
            "momentum_confirm": {
                "0": "unchanged",
                "1": "unchanged",
                "2": "upgrade_to_3_when_triggered",
                "3": "unchanged",
            },
        },
        "notes": [
            "Shadow test only; does not alter GroupA+ target weights.",
            "Score rewards cutting days where 00631L later underperformed 0050 or had bad 20d MDD, without weakening tier separation.",
            "Checklist overlay is rebuilt point-in-time for each historical date.",
        ],
    }
    return best_frame, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--panel-00631l", type=Path, default=PANEL_631L)
    parser.add_argument("--panel-2330", type=Path, default=PANEL_2330)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--start", default=None, help="Optional YYYY-MM-DD subwindow start after building the base frame.")
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD subwindow end after building the base frame.")
    parser.add_argument("--sample-step", type=int, default=5, help="Rebuild checklist every N trading rows, then forward-fill. Use 1 for full daily shadow.")
    parser.add_argument("--output-json", type=Path, default=OUT_JSON)
    parser.add_argument("--output-csv", type=Path, default=OUT_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame, report = run_shadow(
        db_path=args.db,
        panel_00631l=args.panel_00631l,
        panel_2330=args.panel_2330,
        results_dir=args.results_dir,
        project_root=args.project_root,
        sample_step=args.sample_step,
        start=args.start,
        end=args.end,
    )
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_csv, encoding="utf-8-sig")
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    best = report.get("best") or {}
    print(f"Saved JSON: {args.output_json}")
    print(f"Saved CSV: {args.output_csv}")
    print(f"Best score: {float(best.get('score', 0.0)):.6f}")
    print(f"Best spec: {(best.get('spec') or {}).get('name')}")
    affected = best.get("affected") or {}
    print(f"Changed days: {affected.get('changed_days')}")
    print(
        "Affected mean excess20="
        f"{float(affected.get('mean_excess_20d') or 0.0):.4%}, "
        f"bad_mdd20={float(affected.get('bad_mdd_gt5_20d') or 0.0):.1%}"
    )


if __name__ == "__main__":
    main()
