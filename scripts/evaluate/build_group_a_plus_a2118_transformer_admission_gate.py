#!/usr/bin/env python3
"""Build the A21.18 Transformer/Autoformer admission gate.

This gate decides whether the downside-diversification forecast work has enough
economic and OOS evidence to justify a deep sequence model. It does not train a
Transformer and never changes live weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGE2 = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_diversification_forecast_shadow.json"
DEFAULT_STAGE3 = PROJECT_ROOT / "report/group_a_plus/latest/a2118_downside_dcc_forecast_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_transformer_admission_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/a2118_transformer_admission_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _best_rank_ic(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("model_comparison") if isinstance(report.get("model_comparison"), list) else []
    valid = [row for row in rows if isinstance(row.get("rank_ic_mean"), (int, float))]
    if not valid:
        return {}
    return max(valid, key=lambda row: float(row["rank_ic_mean"]))


def _best_positive_economic(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("economic_filter_review") if isinstance(report.get("economic_filter_review"), list) else []
    valid = [row for row in rows if isinstance(row.get("net_filter_value"), (int, float))]
    positive = [row for row in valid if float(row["net_filter_value"]) > 0]
    if not positive:
        return {}
    return max(positive, key=lambda row: float(row["net_filter_value"]))


def build_gate(
    *,
    stage2_path: Path = DEFAULT_STAGE2,
    stage3_path: Path = DEFAULT_STAGE3,
    min_rank_ic: float = 0.05,
    min_dcc_rank_ic_improvement: float = 0.02,
    min_positive_net_filter_value: float = 0.005,
    min_positive_filter_signal_count: int = 20,
    require_dcc_qlike_not_worse_than_simple: bool = True,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    stage2 = _load(_resolve(stage2_path))
    stage3 = _load(_resolve(stage3_path))
    if not stage2:
        blockers.append("stage2_simple_semicovariance_report_missing")
    if not stage3:
        blockers.append("stage3_downside_dcc_report_missing")

    best_simple = _best_rank_ic(stage2)
    best_dcc = _best_rank_ic(stage3)
    best_simple_economic = _best_positive_economic(stage2)
    best_dcc_economic = _best_positive_economic(stage3)

    simple_rank_ic = best_simple.get("rank_ic_mean")
    dcc_rank_ic = best_dcc.get("rank_ic_mean")
    simple_qlike = best_simple.get("qlike_like_semicov")
    dcc_qlike = best_dcc.get("qlike_like_semicov")
    rank_ic_improvement = None
    if isinstance(simple_rank_ic, (int, float)) and isinstance(dcc_rank_ic, (int, float)):
        rank_ic_improvement = float(dcc_rank_ic) - float(simple_rank_ic)
    else:
        blockers.append("rank_ic_comparison_unavailable")

    if isinstance(dcc_rank_ic, (int, float)) and float(dcc_rank_ic) < min_rank_ic:
        blockers.append("dcc_rank_ic_below_minimum")
    if rank_ic_improvement is not None and rank_ic_improvement < min_dcc_rank_ic_improvement:
        blockers.append("dcc_rank_ic_improvement_not_material")
    if (
        require_dcc_qlike_not_worse_than_simple
        and isinstance(simple_qlike, (int, float))
        and isinstance(dcc_qlike, (int, float))
        and float(dcc_qlike) > float(simple_qlike)
    ):
        blockers.append("dcc_qlike_like_loss_worse_than_best_simple")

    dcc_net = best_dcc_economic.get("net_filter_value")
    dcc_count = best_dcc_economic.get("failed_signal_count")
    if not isinstance(dcc_net, (int, float)) or float(dcc_net) < min_positive_net_filter_value:
        blockers.append("dcc_positive_net_filter_value_below_minimum")
    if not isinstance(dcc_count, int) or dcc_count < min_positive_filter_signal_count:
        blockers.append("dcc_positive_filter_signal_count_too_small")

    if rank_ic_improvement is not None and 0 <= rank_ic_improvement < min_dcc_rank_ic_improvement:
        warnings.append("dcc_rank_ic_improvement_is_positive_but_too_small")
    if isinstance(dcc_count, int) and dcc_count < min_positive_filter_signal_count:
        warnings.append("positive_economic_filter_value_based_on_too_few_failed_signals")

    admit = not blockers
    return {
        "schema_version": 1,
        "report_type": "a2118_transformer_admission_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_admission_only_no_live_weight_change",
        "status": "pass" if admit else "blocked",
        "as_of": stage3.get("as_of") or stage2.get("as_of"),
        "parameters": {
            "min_rank_ic": min_rank_ic,
            "min_dcc_rank_ic_improvement": min_dcc_rank_ic_improvement,
            "min_positive_net_filter_value": min_positive_net_filter_value,
            "min_positive_filter_signal_count": min_positive_filter_signal_count,
            "require_dcc_qlike_not_worse_than_simple": require_dcc_qlike_not_worse_than_simple,
        },
        "evidence": {
            "best_simple_rank_ic_model": best_simple,
            "best_dcc_rank_ic_model": best_dcc,
            "rank_ic_improvement_dcc_vs_simple": _float(rank_ic_improvement),
            "best_simple_positive_economic_filter": best_simple_economic,
            "best_dcc_positive_economic_filter": best_dcc_economic,
        },
        "decision": {
            "admit_transformer_research": admit,
            "admit_autoformer_research": admit,
            "train_deep_model_now": admit,
            "promote_to_live_weights": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": (
                "Transformer/Autoformer research is admitted only when DCC materially improves simple OOS forecasts "
                "and the economic filter value is supported by enough signals."
                if admit
                else "Do not train Transformer/Autoformer yet; DCC evidence is not materially stronger than simple semi-covariance baselines."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_gate(gate: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(gate.get("as_of") or datetime.now().date())
    (history_dir / f"a2118_transformer_admission_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage2-path", default=str(DEFAULT_STAGE2))
    parser.add_argument("--stage3-path", default=str(DEFAULT_STAGE3))
    parser.add_argument("--min-rank-ic", type=float, default=0.05)
    parser.add_argument("--min-dcc-rank-ic-improvement", type=float, default=0.02)
    parser.add_argument("--min-positive-net-filter-value", type=float, default=0.005)
    parser.add_argument("--min-positive-filter-signal-count", type=int, default=20)
    parser.add_argument("--allow-worse-qlike", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gate = build_gate(
        stage2_path=_resolve(args.stage2_path),
        stage3_path=_resolve(args.stage3_path),
        min_rank_ic=args.min_rank_ic,
        min_dcc_rank_ic_improvement=args.min_dcc_rank_ic_improvement,
        min_positive_net_filter_value=args.min_positive_net_filter_value,
        min_positive_filter_signal_count=args.min_positive_filter_signal_count,
        require_dcc_qlike_not_worse_than_simple=not args.allow_worse_qlike,
    )
    write_gate(gate, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(gate["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
