#!/usr/bin/env python3
"""Shadow backtest GroupA+ with ncf_2330/00631L advisory tier caps.

This script is research-only. It replays the active GroupA+ regime series and
applies tier-dependent caps to 00631L, then compares the resulting costed curve
against the same costed baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402


START = "2025-01-02"
END = "2026-07-02"
INITIAL_VALUE = 1_000_000.0
DEFAULT_TIER_CSV = PROJECT_ROOT / "results" / "ncf_2330_00631l_tier_eval_20260705.csv"
OUT_JSON = PROJECT_ROOT / "results" / "ncf_tier_shadow_backtest_20260705.json"
OUT_CSV = PROJECT_ROOT / "results" / "ncf_tier_shadow_backtest_20260705_curves.csv"


@dataclass(frozen=True)
class TierCapPolicy:
    name: str
    tier0_cap: float
    tier1_cap: float
    tier2_cap: float
    tier3_cap: float | None
    release_to: str = "0050.TW"
    persistence_days: int = 1


POLICIES = (
    TierCapPolicy("strict_0_0_5_keep", 0.0, 0.0, 0.05, None),
    TierCapPolicy("strict_0_0_10_keep", 0.0, 0.0, 0.10, None),
    TierCapPolicy("soft_0_5_10_keep", 0.0, 0.05, 0.10, None),
    TierCapPolicy("cap_0_0_half_keep", 0.0, 0.0, 0.10, None),
    TierCapPolicy("p3_strict_0_0_10_keep", 0.0, 0.0, 0.10, None, persistence_days=3),
    TierCapPolicy("p5_strict_0_0_10_keep", 0.0, 0.0, 0.10, None, persistence_days=5),
    TierCapPolicy("p3_soft_0_5_10_keep", 0.0, 0.05, 0.10, None, persistence_days=3),
    TierCapPolicy("p5_soft_0_5_10_keep", 0.0, 0.05, 0.10, None, persistence_days=5),
    TierCapPolicy("tier0_only_p3", 0.0, None, None, None, persistence_days=3),
    TierCapPolicy("tier0_only_p5", 0.0, None, None, None, persistence_days=5),
    TierCapPolicy("tier0_half_p3", 0.10, None, None, None, persistence_days=3),
    TierCapPolicy("tier0_half_p5", 0.10, None, None, None, persistence_days=5),
)


def _load_tiers(path: Path, index: pd.DatetimeIndex) -> pd.Series:
    tiers = pd.read_csv(path, index_col=0, parse_dates=True, encoding="utf-8-sig")
    tiers.index = pd.to_datetime(tiers.index).normalize()
    if "tier" not in tiers.columns:
        raise RuntimeError(f"Missing tier column in {path}")
    return tiers["tier"].reindex(index).ffill().fillna(2).astype(int)


def _cap_weight(weights: dict[str, float], cap: float | None, release_to: str) -> dict[str, float]:
    if cap is None:
        return _normalize(dict(weights))
    adjusted = dict(weights)
    original = float(adjusted.get("00631L.TW", 0.0))
    capped = min(original, max(float(cap), 0.0))
    released = max(original - capped, 0.0)
    adjusted["00631L.TW"] = capped
    adjusted[release_to] = float(adjusted.get(release_to, 0.0)) + released
    return _normalize(adjusted)


def _weights_for_policy(
    base_weights: dict[str, dict[str, float]],
    policy: TierCapPolicy,
) -> dict[str, dict[str, float]]:
    caps = {
        0: policy.tier0_cap,
        1: policy.tier1_cap,
        2: policy.tier2_cap,
        3: policy.tier3_cap,
    }
    out: dict[str, dict[str, float]] = {}
    for regime, weights in base_weights.items():
        for tier, cap in caps.items():
            out[f"{regime}__tier{tier}"] = _cap_weight(weights, cap, policy.release_to)
    return out


def _regimes_for_policy(base_regimes: pd.Series, tiers: pd.Series) -> pd.Series:
    return pd.Series(
        [f"{str(regime)}__tier{int(tier)}" for regime, tier in zip(base_regimes, tiers)],
        index=base_regimes.index,
        dtype=object,
    )


def _persistent_tiers(tiers: pd.Series, persistence_days: int) -> pd.Series:
    if persistence_days <= 1:
        return tiers.astype(int)
    current = int(tiers.iloc[0])
    pending = current
    count = 0
    out: list[int] = []
    for value in tiers.astype(int):
        if int(value) == current:
            pending = current
            count = 0
        elif int(value) == pending:
            count += 1
            if count >= persistence_days:
                current = int(value)
                pending = current
                count = 0
        else:
            pending = int(value)
            count = 1
            if count >= persistence_days:
                current = pending
                count = 0
        out.append(current)
    return pd.Series(out, index=tiers.index, dtype=int)


def _exposure_stats(regimes: pd.Series, weights_by_regime: dict[str, dict[str, float]]) -> dict[str, Any]:
    weights = pd.Series(
        [float(weights_by_regime[str(regime)].get("00631L.TW", 0.0)) for regime in regimes],
        index=regimes.index,
    )
    return {
        "avg_00631l_weight": float(weights.mean()),
        "max_00631l_weight": float(weights.max()),
        "zero_00631l_days": int((weights <= 1e-12).sum()),
        "days": int(len(weights)),
    }


def _run_curve(
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
) -> tuple[pd.Series, dict[str, Any]]:
    curve, execution = _simulate_costed_curve(
        prices,
        regimes,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    return curve, {
        "metrics": _metrics(curve, initial_value),
        "execution": execution,
        "exposure": _exposure_stats(regimes, weights_by_regime),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier-csv", default=str(DEFAULT_TIER_CSV))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-json", default=str(OUT_JSON))
    parser.add_argument("--output-csv", default=str(OUT_CSV))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    report, frame = run_latest(START, END, INITIAL_VALUE, db_path, DEFAULT_LATEST_STRATEGY)
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    prices = prices.reindex(frame.index).ffill()

    base_regimes = frame["execution_regime"].astype(str)
    base_weights = {
        str(key): dict(value)
        for key, value in (report.get("base_weights") or report.get("weights") or {}).items()
    }
    tiers = _load_tiers(Path(args.tier_csv), frame.index)

    curves = pd.DataFrame(index=frame.index)
    baseline_curve, baseline = _run_curve(prices, base_regimes, base_weights, INITIAL_VALUE)
    curves["baseline"] = baseline_curve

    variants: dict[str, Any] = {}
    baseline_metrics = baseline["metrics"]
    for policy in POLICIES:
        weights_by_regime = _weights_for_policy(base_weights, policy)
        effective_tiers = _persistent_tiers(tiers, policy.persistence_days)
        regimes = _regimes_for_policy(base_regimes, effective_tiers)
        curve, result = _run_curve(prices, regimes, weights_by_regime, INITIAL_VALUE)
        curves[policy.name] = curve
        metrics = result["metrics"]
        variants[policy.name] = {
            "policy": asdict(policy),
            **result,
            "tier_counts": {str(k): int(v) for k, v in effective_tiers.value_counts().sort_index().items()},
            "delta_vs_baseline": {
                "final_value": float(metrics["final_value"] - baseline_metrics["final_value"]),
                "total_return": float(metrics["total_return"] - baseline_metrics["total_return"]),
                "max_drawdown": float(metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
                "sharpe_ratio": float(metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
                "sortino_ratio": float(metrics["sortino_ratio"] - baseline_metrics["sortino_ratio"]),
                "transaction_cost": float(
                    result["execution"]["transaction_cost"] - baseline["execution"]["transaction_cost"]
                ),
                "rebalance_count": int(
                    result["execution"]["rebalance_count"] - baseline["execution"]["rebalance_count"]
                ),
            },
        }

    best = max(
        variants.items(),
        key=lambda item: (
            item[1]["delta_vs_baseline"]["final_value"],
            item[1]["delta_vs_baseline"]["max_drawdown"],
            item[1]["delta_vs_baseline"]["sharpe_ratio"],
        ),
    )
    out = {
        "experiment": "ncf_tier_shadow_backtest",
        "period": {"start": START, "end": END},
        "inputs": {
            "tier_csv": str(Path(args.tier_csv).relative_to(PROJECT_ROOT)),
            "db": str(db_path),
        },
        "baseline": baseline,
        "variants": variants,
        "best_by_final_value": best[0],
        "dividend_coverage": dividend_coverage,
        "notes": [
            "Shadow-only replay: production target_weights are not changed.",
            "Tier caps only reduce 00631L and release the difference to 0050.TW.",
        ],
    }
    Path(args.output_json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    curves.to_csv(args.output_csv, encoding="utf-8-sig")

    print(f"Saved JSON: {args.output_json}")
    print(f"Saved curves: {args.output_csv}")
    print(
        "Baseline: "
        f"final={baseline_metrics['final_value']:,.0f}, "
        f"mdd={baseline_metrics['max_drawdown']:.2%}, "
        f"sharpe={baseline_metrics['sharpe_ratio']:.3f}, "
        f"cost={baseline['execution']['transaction_cost']:,.0f}, "
        f"rebalances={baseline['execution']['rebalance_count']}"
    )
    for name, item in variants.items():
        d = item["delta_vs_baseline"]
        m = item["metrics"]
        print(
            f"{name}: final={m['final_value']:,.0f} ({d['final_value']:+,.0f}), "
            f"mdd={m['max_drawdown']:.2%} ({d['max_drawdown']:+.2%}), "
            f"sharpe={m['sharpe_ratio']:.3f} ({d['sharpe_ratio']:+.3f}), "
            f"cost_delta={d['transaction_cost']:+,.0f}, "
            f"rebalance_delta={d['rebalance_count']:+d}"
        )


if __name__ == "__main__":
    main()
