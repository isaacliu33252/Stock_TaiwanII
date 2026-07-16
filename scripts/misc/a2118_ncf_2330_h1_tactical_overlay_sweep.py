#!/usr/bin/env python3
"""Research sweep: does ncf_2330's H1 (1-day) direction signal improve GroupA+'s
current live strategy ("latest" -> a2118, per report/group_a_plus/latest/strategy.json)?

Context: five prior attempts to give ncf_2330 weight-level influence over a2118 were
all rejected (see GROUP_A_PLUS_NCF2330_SWITCHRULE_INTEGRATION_ATTEMPTS_HANDOFF_20260705.md),
but every one of them used ncf_2330's H20 direction and/or 20d tail-risk output. None
tested the H1 (1-day-ahead) direction signal specifically. The 2026-07-07 leadership
feature promotion (results/NCF_2330_LEADERSHIP_PROMOTION_HANDOFF_20260707.md) raised H1
val_auc from ~0.55 to ~0.76 (confirmed on strict 2025-2026 OOS) while H20/tail-risk moved
much less -- so this is a genuinely new, not-yet-tested angle, not a re-run of a
previously-rejected mechanism.

Overlay tested: trim 00631L (into cash) for a single day whenever ncf_2330's H1 model
predicts TSMC DOWN with prob_up_h1 below a threshold AND confidence above a threshold,
only while a2118 is in its normal golden1 regime (mirrors the existing
a2118_ncf_2330_tsmc_overlay_sweep.py convention). Because this is a daily/high-frequency
signal (unlike the rare late-bull hedge trigger), trigger-day counts and transaction
costs are reported prominently -- a2118's own design notes already flag that
continuous/frequent NCF-based overlays caused -18.5% drag in an earlier iteration (A21.13).

Read-only with respect to production strategy code. Writes one JSON report to results/.
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve  # noqa: E402
from backtest_group_a_plus_policy_signal import _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY  # noqa: E402
from group_a_plus.runners.latest import run_latest  # noqa: E402

START = "2025-01-02"
END = "2026-07-02"
INITIAL_VALUE = 1_000_000.0

PANEL_2330 = PROJECT_ROOT / "results" / "ncf_2330_panel_latest_20260707.csv"
OUT = PROJECT_ROOT / "results" / f"a2118_ncf_2330_h1_tactical_overlay_sweep_20260707.json"

H1_PROB_MAX_VALUES = [0.35, 0.40, 0.45]
CONFIDENCE_MIN_VALUES = [0.15, 0.20, 0.25, 0.30]
TRIM_FRACTIONS = [0.15, 0.25, 0.35, 0.50, 0.65, 0.75, 1.00]


def _load_panel(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index).normalize()
    return df[["prob_up_h1", "confidence", "direction"]].rename(
        columns={"prob_up_h1": "h1_prob_up", "confidence": "h1_confidence", "direction": "h1_direction"}
    )


def _build_signal_frame(frame: pd.DataFrame, panel_path: Path) -> pd.DataFrame:
    idx = pd.DatetimeIndex(frame.index).normalize()
    panel = _load_panel(panel_path)
    signal = panel.reindex(idx).copy()
    signal["execution_regime"] = frame["execution_regime"].astype(str).reindex(idx)
    return signal


def _trimmed_weights(golden_weights: dict[str, float], trim_fraction: float) -> dict[str, float]:
    weights = dict(golden_weights)
    shift = float(weights.get("00631L.TW", 0.0)) * float(trim_fraction)
    weights["00631L.TW"] = float(weights.get("00631L.TW", 0.0)) - shift
    weights["cash"] = float(weights.get("cash", 0.0)) + shift
    return _normalize(weights)


def _trigger_mask(signal: pd.DataFrame, *, h1_prob_max: float, confidence_min: float) -> pd.Series:
    h1_bearish = (signal["h1_prob_up"] < h1_prob_max) & (signal["h1_confidence"] > confidence_min)
    return ((signal["execution_regime"] == "golden1") & h1_bearish).fillna(False)


def _max_drawdown_from_entry(curve: pd.Series, dates: pd.DatetimeIndex, horizon: int = 1) -> float | None:
    values: list[float] = []
    for dt in dates:
        if dt not in curve.index:
            continue
        loc = curve.index.get_loc(dt)
        if isinstance(loc, slice):
            continue
        end = min(int(loc) + horizon, len(curve) - 1)
        segment = curve.iloc[int(loc): end + 1]
        if len(segment) > 1:
            values.append(float((segment / segment.iloc[0] - 1.0).min()))
    return min(values) if values else None


def _run_variant(
    *,
    signal: pd.DataFrame,
    total_return_prices: pd.DataFrame,
    base_regimes: pd.Series,
    base_weights: dict[str, dict[str, float]],
    initial_value: float,
    trim_fraction: float,
    h1_prob_max: float,
    confidence_min: float,
) -> dict[str, Any]:
    mask = _trigger_mask(signal, h1_prob_max=h1_prob_max, confidence_min=confidence_min)
    regime_name = f"h1_tactical_trim_{trim_fraction:.2f}"
    regimes = base_regimes.copy()
    regimes.loc[mask] = regime_name
    weights_by_regime = dict(base_weights)
    weights_by_regime[regime_name] = _trimmed_weights(base_weights["golden1"], trim_fraction)
    curve, sim = _simulate_costed_curve(
        total_return_prices,
        regimes,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    metrics = _metrics(curve, initial_value)
    trigger_dates = pd.DatetimeIndex(mask[mask].index)
    return {
        "params": {"h1_prob_max": h1_prob_max, "confidence_min": confidence_min, "trim_fraction": trim_fraction},
        "metrics": metrics,
        "execution": sim,
        "trigger_days": int(mask.sum()),
        "trigger_dates": [str(dt.date()) for dt in trigger_dates],
        "worst_1d_return_after_trigger": _max_drawdown_from_entry(curve, trigger_dates, horizon=1),
    }


def _score_variant(item: dict[str, Any], baseline: dict[str, Any]) -> tuple[float, float, float, int]:
    metrics = item["metrics"]
    return (
        float(metrics["max_drawdown"]) - float(baseline["max_drawdown"]),
        float(metrics["final_value"]) - float(baseline["final_value"]),
        float(metrics["sharpe_ratio"]) - float(baseline["sharpe_ratio"]),
        -int(item["trigger_days"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--panel", default=str(PANEL_2330))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--window-label", default=None)
    args = parser.parse_args()

    report, frame = run_latest(args.start, args.end, INITIAL_VALUE, DB_PATH, DEFAULT_LATEST_STRATEGY)
    signal = _build_signal_frame(frame, Path(args.panel))
    total_return_prices, _ = _load_total_return_prices(DB_PATH, frame.index)
    total_return_prices = total_return_prices.reindex(frame.index).ffill()
    base_regimes = frame["execution_regime"].astype(str)
    base_weights = {
        key: dict(value)
        for key, value in (report.get("base_weights") or report.get("weights") or {}).items()
    }
    baseline_metrics = report["metrics"]
    baseline_execution = report["execution"]

    variants = []
    for h1_prob_max, confidence_min, trim_fraction in product(
        H1_PROB_MAX_VALUES, CONFIDENCE_MIN_VALUES, TRIM_FRACTIONS
    ):
        variants.append(
            _run_variant(
                signal=signal,
                total_return_prices=total_return_prices,
                base_regimes=base_regimes,
                base_weights=base_weights,
                initial_value=INITIAL_VALUE,
                trim_fraction=trim_fraction,
                h1_prob_max=h1_prob_max,
                confidence_min=confidence_min,
            )
        )

    for item in variants:
        m = item["metrics"]
        item["delta_vs_baseline"] = {
            "final_value": float(m["final_value"]) - float(baseline_metrics["final_value"]),
            "sharpe_ratio": float(m["sharpe_ratio"]) - float(baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(m["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
            "transaction_cost": float(item["execution"]["transaction_cost"]) - float(baseline_execution["transaction_cost"]),
            "rebalance_count": int(item["execution"]["rebalance_count"]) - int(baseline_execution["rebalance_count"]),
        }

    variants_sorted = sorted(variants, key=lambda item: _score_variant(item, baseline_metrics), reverse=True)
    variants_by_final = sorted(variants, key=lambda item: item["delta_vs_baseline"]["final_value"], reverse=True)

    n_improved_final = sum(1 for v in variants if v["delta_vs_baseline"]["final_value"] > 0)
    n_improved_mdd = sum(1 for v in variants if v["delta_vs_baseline"]["max_drawdown"] > 1e-9)
    n_improved_both = sum(
        1 for v in variants
        if v["delta_vs_baseline"]["final_value"] > 0 and v["delta_vs_baseline"]["max_drawdown"] > -1e-9
    )

    report_out = {
        "window": {"start": args.start, "end": args.end, "label": args.window_label},
        "panel": str(args.panel),
        "baseline": {"metrics": baseline_metrics, "execution": baseline_execution},
        "n_variants": len(variants),
        "n_improved_final_value": n_improved_final,
        "n_improved_max_drawdown": n_improved_mdd,
        "n_improved_both": n_improved_both,
        "top_by_combined_score": variants_sorted[:10],
        "top_by_final_value": variants_by_final[:5],
        "all_variants": variants,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_out, f, indent=2, ensure_ascii=False, default=str)

    print(f"[h1-overlay-sweep] baseline: final_value={baseline_metrics['final_value']:.0f} "
          f"sharpe={baseline_metrics['sharpe_ratio']:.4f} max_dd={baseline_metrics['max_drawdown']:.4f}")
    print(f"[h1-overlay-sweep] {len(variants)} variants: "
          f"{n_improved_final} improved final_value, {n_improved_mdd} improved max_drawdown, "
          f"{n_improved_both} improved both")
    print("\n[h1-overlay-sweep] Top 5 by combined score (mdd, final_value, sharpe, -trigger_days):")
    for item in variants_sorted[:5]:
        d = item["delta_vs_baseline"]
        print(f"  {item['params']}  trigger_days={item['trigger_days']:>3}  "
              f"d_final={d['final_value']:>+10.0f}  d_sharpe={d['sharpe_ratio']:>+.4f}  "
              f"d_mdd={d['max_drawdown']:>+.4f}  d_cost={d['transaction_cost']:>+.0f}")
    print(f"\n[h1-overlay-sweep] Saved: {output_path}")


if __name__ == "__main__":
    main()
