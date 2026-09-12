#!/usr/bin/env python3
"""Build a 2607.16450 regime-switching volatility promotion gate.

The source paper lists regime-switching volatility as future research. This
wrapper converts the existing forecast-quality shadow output into a promotion
readiness artifact. It never emits target weights, execution regimes, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORECAST_QUALITY = (
    PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_regime_switching_volatility_forecast_quality.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_regime_switching_volatility_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_regime_switching_volatility_gate/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _metric(payload: dict[str, Any], horizon: str, benchmark: str, key: str) -> float | None:
    row = ((payload.get("results") or {}).get(str(horizon)) or {}).get(benchmark) or {}
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def build_gate(
    *,
    forecast_quality_path: Path,
    min_qlike_improvement_pct: float = 0.0,
    min_win_rate_vs_har: float = 0.50,
    required_horizons: tuple[str, ...] = ("5", "10", "20"),
) -> dict[str, Any]:
    quality = _load(forecast_quality_path)
    blockers: list[str] = []
    warnings: list[str] = []
    horizon_reviews: list[dict[str, Any]] = []

    if not quality:
        blockers.append("missing_regime_switching_volatility_forecast_quality")

    for horizon in required_horizons:
        vs_naive = _metric(quality, horizon, "regime_vs_naive", "qlike_improvement_pct")
        vs_har = _metric(quality, horizon, "regime_vs_har_rv", "qlike_improvement_pct")
        win_vs_har = _metric(quality, horizon, "regime_vs_har_rv", "win_rate_vs_benchmark")
        status = "available" if None not in (vs_naive, vs_har, win_vs_har) else "missing"
        if status == "missing":
            blockers.append(f"missing_required_horizon_metrics:h{horizon}")
        else:
            if vs_naive is not None and vs_naive < min_qlike_improvement_pct:
                blockers.append(f"h{horizon}_underperforms_naive_on_qlike")
            if vs_har is not None and vs_har < min_qlike_improvement_pct:
                blockers.append(f"h{horizon}_underperforms_har_rv_on_qlike")
            if win_vs_har is not None and win_vs_har < min_win_rate_vs_har:
                blockers.append(f"h{horizon}_win_rate_below_har_threshold")
        horizon_reviews.append(
            {
                "horizon": int(horizon),
                "status": status,
                "regime_vs_naive_qlike_improvement_pct": vs_naive,
                "regime_vs_har_rv_qlike_improvement_pct": vs_har,
                "win_rate_vs_har_rv": win_vs_har,
            }
        )

    if horizon_reviews and all(
        isinstance(row.get("regime_vs_har_rv_qlike_improvement_pct"), (int, float))
        and float(row["regime_vs_har_rv_qlike_improvement_pct"]) < -50.0
        for row in horizon_reviews
    ):
        warnings.append("regime_switching_volatility_materially_worse_than_har_rv_all_horizons")

    as_of = (quality.get("window") or {}).get("end") or "unknown"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_regime_switching_volatility_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked_for_live_promotion" if blockers else "passed_shadow_forecast_gate",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "future_research_concept": "regime_switching_volatility_models",
            "imported_as": "forecast_quality_promotion_gate",
        },
        "forecast_quality_context": {
            "ticker": quality.get("ticker"),
            "window": quality.get("window"),
            "rolling_window": quality.get("rolling_window"),
            "n_regimes": quality.get("n_regimes"),
            "use_augmented_features": quality.get("use_augmented_features"),
        },
        "thresholds": {
            "min_qlike_improvement_pct": min_qlike_improvement_pct,
            "min_win_rate_vs_har": min_win_rate_vs_har,
            "required_horizons": list(required_horizons),
        },
        "horizon_reviews": horizon_reviews,
        "decision": {
            "promote_regime_switching_volatility_gate": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_regime_gate": False,
            "summary": "Regime-switching volatility remains future-research/shadow-only until it beats HAR-RV and naive persistence across required horizons.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "inputs": {"forecast_quality": str(forecast_quality_path)},
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_regime_switching_volatility_gate_{stamp}.json"


def write_gate(gate: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(gate.get("as_of"))).write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-quality", default=str(DEFAULT_FORECAST_QUALITY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    gate = build_gate(forecast_quality_path=_resolve(args.forecast_quality))
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_gate(gate, output, history_dir)
    print(f"2607.16450 regime-switching volatility gate: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, str(gate.get('as_of')))}")
    print(
        json.dumps(
            {
                "status": gate["status"],
                "promote": gate["decision"]["promote_regime_switching_volatility_gate"],
                "blocking_reasons": gate["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
