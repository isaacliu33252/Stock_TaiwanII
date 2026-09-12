#!/usr/bin/env python3
"""Follow-up 5 to arXiv:2104.03667 (see
build_group_a_plus_2104_03667_regime_clustering_review.py and
docs/HANDOFF_2104_03667_REGIME_CLUSTERING_VLSTAR_GROUPA_PLUS_20260827.md).

User question: does simply expanding the cluster-regime feature set from
Group A+'s 4 core tickers to 5 (adding 00713.TW, an existing fifth-asset
candidate from the 2411.19649 review) improve the correlation-clustering
regime detector, since the original review's stated diagnosis was "the
4-asset universe is too low-dimensional for AGNES/Ward clustering to have
real signal"?

This reuses `build_review()` from the original review script unmodified
(already covered by that script's own 3 tests) with a 5-ticker
`core_tickers` argument, and compares the result against the already-saved
4-ticker baseline report. No new detector logic -- purely a parameter
variation.

Research-only. Does not touch any production runner, signal, or execution
plan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2104_03667_regime_clustering_review import (  # noqa: E402
    CORE_TICKERS as BASELINE_TICKERS,
    DB_PATH,
    build_review,
)

EXPANDED_TICKERS = BASELINE_TICKERS + ("00713.TW",)
BASELINE_REPORT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_regime_clustering_review.json"
OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2104_03667_00713_asset_pool_expansion_check.json"


def build_comparison(db_path: Path = DB_PATH, baseline_report_path: Path = BASELINE_REPORT) -> dict:
    expanded = build_review(db_path=db_path, core_tickers=EXPANDED_TICKERS)

    baseline = None
    if baseline_report_path.exists():
        baseline = json.loads(baseline_report_path.read_text(encoding="utf-8"))
    else:
        baseline = build_review(db_path=db_path, core_tickers=BASELINE_TICKERS)

    def _get(d: dict, *path):
        cur = d
        for p in path:
            if cur is None:
                return None
            cur = cur.get(p)
        return cur

    comparison = {
        "baseline_tickers": list(BASELINE_TICKERS),
        "expanded_tickers": list(EXPANDED_TICKERS),
        "baseline_cluster_volatile_share": _get(baseline, "cluster_regime_volatile_share"),
        "expanded_cluster_volatile_share": _get(expanded, "cluster_regime_volatile_share"),
        "test_a_cluster_filtered": {
            "baseline": _get(baseline, "paper_momentum_validation", "naive_momentum_cluster_filtered"),
            "expanded": _get(expanded, "paper_momentum_validation", "naive_momentum_cluster_filtered"),
        },
        "test_b_cluster_regime_switch": {
            "baseline": _get(baseline, "group_a_plus_switch_check", "full_window", "cluster_regime_switch"),
            "expanded": _get(expanded, "group_a_plus_switch_check", "full_window", "cluster_regime_switch"),
        },
        "agreement_with_existing_rule": {
            "baseline": _get(baseline, "group_a_plus_switch_check", "agreement_with_existing_switch_rule", "cluster_regime"),
            "expanded": _get(expanded, "group_a_plus_switch_check", "agreement_with_existing_switch_rule", "cluster_regime"),
        },
    }

    ta_b = comparison["test_a_cluster_filtered"]["baseline"]
    ta_e = comparison["test_a_cluster_filtered"]["expanded"]
    tb_b = comparison["test_b_cluster_regime_switch"]["baseline"]
    tb_e = comparison["test_b_cluster_regime_switch"]["expanded"]
    comparison["expansion_helps_test_a"] = bool(
        ta_b and ta_e and ta_e["sharpe"] > ta_b["sharpe"] and ta_e["mdd"] > ta_b["mdd"]
    )
    comparison["expansion_helps_test_b"] = bool(
        tb_b and tb_e and tb_e["sharpe"] > tb_b["sharpe"] and tb_e["mdd"] > tb_b["mdd"]
    )

    return {
        "paper": "arXiv:2104.03667",
        "follow_up_of": "2104_03667_regime_detection_vlstar_hierarchical_clustering",
        "status": "closed",
        "question": "does adding 00713.TW to the cluster-regime feature set improve the detector",
        "comparison": comparison,
        "target_weight_change_allowed": False,
        "replace_a2118": False,
        "train_vlstar_now": False,
    }


def write_comparison(result: dict, output_path: Path = OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    result = build_comparison()
    c = result["comparison"]
    print(f"Baseline tickers: {c['baseline_tickers']}")
    print(f"Expanded tickers: {c['expanded_tickers']}")
    print(f"\nCluster volatile share: baseline={c['baseline_cluster_volatile_share']*100:.1f}%  "
          f"expanded={c['expanded_cluster_volatile_share']*100:.1f}%")

    ta = c["test_a_cluster_filtered"]
    print(f"\nTest A (cluster-filtered momentum): "
          f"baseline sharpe={ta['baseline']['sharpe']:.3f}/mdd={ta['baseline']['mdd']*100:.2f}%  "
          f"expanded sharpe={ta['expanded']['sharpe']:.3f}/mdd={ta['expanded']['mdd']*100:.2f}%")

    tb = c["test_b_cluster_regime_switch"]
    print(f"Test B (cluster_regime_switch): "
          f"baseline sharpe={tb['baseline']['sharpe']:.3f}/mdd={tb['baseline']['mdd']*100:.2f}%  "
          f"expanded sharpe={tb['expanded']['sharpe']:.3f}/mdd={tb['expanded']['mdd']*100:.2f}%")

    agr = c["agreement_with_existing_rule"]
    print(f"Agreement with existing rule: baseline={agr['baseline']['day_by_day_agreement']*100:.1f}%  "
          f"expanded={agr['expanded']['day_by_day_agreement']*100:.1f}%")

    print(f"\nExpansion helps test A (both sharpe & mdd better): {c['expansion_helps_test_a']}")
    print(f"Expansion helps test B (both sharpe & mdd better): {c['expansion_helps_test_b']}")

    write_comparison(result, OUTPUT)
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
