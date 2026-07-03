"""A21.19 runner - A21.11 + FinBERT boundary risk gate.

This is a research candidate.  It keeps A21.11 weights unchanged, then tests
whether market-news sentiment can improve regime timing near the MA100 boundary.
FinBERT never trims golden1 daily allocation directly; it can only force the
execution regime to defensive after a sustained high-risk signal.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    _load_total_return_prices,
    _simulate_costed_curve,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2111 import run_a2111
from tw_output_standard import OutputStandardizer, write_standard_output


A2119_ID = "a2119_a2111_finbert_gate"
DEFAULT_FINBERT_DAILY = PROJECT_ROOT / "FinRL" / "data" / "sentiment" / "finbert_market_sentiment_daily.csv"

FINBERT_RISK_ON_THRESHOLD = 0.55
FINBERT_RISK_OFF_THRESHOLD = 0.43
FINBERT_MA_GAP_MAX = 0.03
FINBERT_MA_GAP_TRIGGER_MAX = -0.015
FINBERT_EXIT_MOMENTUM_MAX = 0.01
FINBERT_ON_CONSECUTIVE = 1
FINBERT_OFF_CONSECUTIVE = 2
FINBERT_MIN_TOTAL_RISK_SCORE: float | None = None
FINBERT_QUALITY_RISK_OVERRIDE_THRESHOLD: float | None = None


def _load_finbert_risk(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    if df.empty or "date" not in df.columns:
        return pd.Series(dtype=float)
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    data = data.dropna(subset=["date"]).sort_values("date")

    def val(row: pd.Series, name: str, default: float = 0.0) -> float:
        if name not in row or pd.isna(row[name]):
            return default
        return float(row[name])

    risks: list[float] = []
    for _, row in data.iterrows():
        sentiment = val(row, "finbert_sentiment_score")
        negative_ratio = val(row, "finbert_negative_ratio")
        confidence = val(row, "finbert_confidence")
        intensity = max(val(row, "finbert_news_intensity"), 0.0)
        negative_score = min(max(-sentiment, negative_ratio, 0.0), 1.0)
        intensity_score = min(intensity / 3.0, 1.0)
        risks.append(min(max(0.55 * negative_score + 0.25 * confidence + 0.20 * intensity_score, 0.0), 1.0))
    return pd.Series(risks, index=data["date"], dtype=float)


def _apply_finbert_gate(
    execution_regime: pd.Series,
    ma_gap: pd.Series,
    finbert_risk: pd.Series,
    exit_momentum: pd.Series | None = None,
    entry_quality: pd.Series | None = None,
    *,
    risk_on_threshold: float = FINBERT_RISK_ON_THRESHOLD,
    risk_off_threshold: float = FINBERT_RISK_OFF_THRESHOLD,
    ma_gap_max: float = FINBERT_MA_GAP_MAX,
    ma_gap_trigger_max: float | None = None,
    exit_momentum_max: float | None = None,
    quality_risk_override_threshold: float | None = FINBERT_QUALITY_RISK_OVERRIDE_THRESHOLD,
    on_consecutive: int = FINBERT_ON_CONSECUTIVE,
    off_consecutive: int = FINBERT_OFF_CONSECUTIVE,
) -> tuple[pd.Series, dict]:
    modified = execution_regime.copy()
    aligned_risk = finbert_risk.reindex(execution_regime.index).ffill().fillna(0.0)
    aligned_quality = (
        entry_quality.reindex(execution_regime.index).ffill().fillna(False).astype(bool)
        if entry_quality is not None
        else pd.Series(True, index=execution_regime.index)
    )
    active = False
    on_count = 0
    off_count = 0
    events: list[dict] = []

    for dt in execution_regime.index:
        base_regime = str(execution_regime.loc[dt])
        risk = float(aligned_risk.loc[dt])
        gap = float(ma_gap.get(dt, 999.0))
        momentum = float(exit_momentum.get(dt, 999.0)) if exit_momentum is not None else 0.0
        quality = bool(aligned_quality.loc[dt])

        momentum_ok = exit_momentum_max is None or momentum <= exit_momentum_max
        trigger_gap_ok = ma_gap_trigger_max is None or gap <= ma_gap_trigger_max
        quality_ok = quality or (
            quality_risk_override_threshold is not None and risk >= quality_risk_override_threshold
        )
        if risk >= risk_on_threshold and gap < ma_gap_max and trigger_gap_ok and momentum_ok and quality_ok:
            on_count += 1
            off_count = 0
        else:
            on_count = 0
            if risk <= risk_off_threshold or gap >= ma_gap_max or not momentum_ok:
                off_count += 1
            else:
                off_count = 0

        if not active and base_regime == "golden1" and on_count >= on_consecutive:
            active = True
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "finbert_gate_ON",
                    "finbert_risk": round(risk, 4),
                    "ma_gap": round(gap, 4),
                    "exit_momentum": round(momentum, 4),
                    "entry_quality": quality,
                    "consecutive_days": on_count,
                }
            )
        if active and off_count >= off_consecutive:
            active = False
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "finbert_gate_OFF",
                    "finbert_risk": round(risk, 4),
                    "ma_gap": round(gap, 4),
                    "exit_momentum": round(momentum, 4),
                    "consecutive_clear": off_count,
                }
            )

        if active and base_regime == "golden1":
            modified.loc[dt] = "group_a_plus_defensive"

    return modified, {
        "finbert_gate_activations": sum(1 for event in events if event["event"] == "finbert_gate_ON"),
        "finbert_gate_days": int((modified != execution_regime).sum()),
        "finbert_gate_events": events,
        "finbert_risk_mean": float(aligned_risk.mean()) if len(aligned_risk) else 0.0,
        "finbert_risk_max": float(aligned_risk.max()) if len(aligned_risk) else 0.0,
    }


def run_a2119(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    finbert_daily_path: str | Path = DEFAULT_FINBERT_DAILY,
    finbert_risk_on_threshold: float = FINBERT_RISK_ON_THRESHOLD,
    finbert_risk_off_threshold: float = FINBERT_RISK_OFF_THRESHOLD,
    finbert_ma_gap_max: float = FINBERT_MA_GAP_MAX,
    finbert_ma_gap_trigger_max: float | None = FINBERT_MA_GAP_TRIGGER_MAX,
    finbert_exit_momentum_max: float | None = FINBERT_EXIT_MOMENTUM_MAX,
    finbert_min_total_risk_score: float | None = FINBERT_MIN_TOTAL_RISK_SCORE,
    finbert_quality_risk_override_threshold: float | None = FINBERT_QUALITY_RISK_OVERRIDE_THRESHOLD,
    finbert_on_consecutive: int = FINBERT_ON_CONSECUTIVE,
    finbert_off_consecutive: int = FINBERT_OFF_CONSECUTIVE,
) -> tuple[dict, pd.DataFrame]:
    base_report, base_frame = run_a2111(
        start,
        end,
        initial_value,
        db,
        warmup_days,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    finbert_path = Path(finbert_daily_path)
    if not finbert_path.is_absolute():
        finbert_path = PROJECT_ROOT / finbert_path
    finbert_risk = _load_finbert_risk(finbert_path)
    entry_quality = None
    if finbert_min_total_risk_score is not None and "total_risk_score" in base_frame:
        entry_quality = base_frame["total_risk_score"] >= finbert_min_total_risk_score
    execution_regime, gate = _apply_finbert_gate(
        base_frame["execution_regime"],
        base_frame["ma_gap"],
        finbert_risk,
        base_frame["exit_momentum"],
        entry_quality,
        risk_on_threshold=finbert_risk_on_threshold,
        risk_off_threshold=finbert_risk_off_threshold,
        ma_gap_max=finbert_ma_gap_max,
        ma_gap_trigger_max=finbert_ma_gap_trigger_max,
        exit_momentum_max=finbert_exit_momentum_max,
        quality_risk_override_threshold=finbert_quality_risk_override_threshold,
        on_consecutive=finbert_on_consecutive,
        off_consecutive=finbert_off_consecutive,
    )
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve_db(db), base_frame.index)
    curve, execution = _simulate_costed_curve(
        total_return_prices,
        execution_regime,
        base_report["weights"],
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    out_frame = base_frame.copy()
    out_frame["a2111_execution_regime"] = base_frame["execution_regime"]
    out_frame["execution_regime"] = execution_regime
    out_frame["finbert_risk"] = finbert_risk.reindex(out_frame.index).ffill().fillna(0.0)
    out_frame["portfolio_value"] = curve
    report = {
        "experiment": "group_a_plus_a2119_a2111_finbert_gate",
        "strategy": A2119_ID,
        "status": "research_candidate",
        "window": base_report["window"],
        "metrics": _metrics(curve, initial_value),
        "baseline_a2111_metrics": base_report["metrics"],
        "execution": execution,
        "finbert_gate": gate,
        "rules": {
            "base": "a2111_tight_entry_bond30c30",
            "finbert_risk_on_threshold": finbert_risk_on_threshold,
            "finbert_risk_off_threshold": finbert_risk_off_threshold,
            "finbert_ma_gap_max": finbert_ma_gap_max,
            "finbert_ma_gap_trigger_max": finbert_ma_gap_trigger_max,
            "finbert_exit_momentum_max": finbert_exit_momentum_max,
            "finbert_min_total_risk_score": finbert_min_total_risk_score,
            "finbert_quality_risk_override_threshold": finbert_quality_risk_override_threshold,
            "finbert_on_consecutive": finbert_on_consecutive,
            "finbert_off_consecutive": finbert_off_consecutive,
            "finbert_action": "force defensive only; no daily golden1 allocation trim",
        },
        "cost_assumptions": base_report["cost_assumptions"],
        "dividend_coverage": dividend_coverage,
        "weights": base_report["weights"],
        "inputs": {
            **base_report["inputs"],
            "finbert_daily": str(finbert_path.relative_to(PROJECT_ROOT)) if finbert_path.is_relative_to(PROJECT_ROOT) else str(finbert_path),
        },
    }
    return report, out_frame


def _resolve_db(db: Path) -> Path:
    return db if db.is_absolute() else PROJECT_ROOT / db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--finbert-daily", default=str(DEFAULT_FINBERT_DAILY))
    parser.add_argument("--finbert-risk-on-threshold", type=float, default=FINBERT_RISK_ON_THRESHOLD)
    parser.add_argument("--finbert-risk-off-threshold", type=float, default=FINBERT_RISK_OFF_THRESHOLD)
    parser.add_argument("--finbert-ma-gap-max", type=float, default=FINBERT_MA_GAP_MAX)
    parser.add_argument("--finbert-ma-gap-trigger-max", type=float, default=FINBERT_MA_GAP_TRIGGER_MAX)
    parser.add_argument("--finbert-exit-momentum-max", type=float, default=FINBERT_EXIT_MOMENTUM_MAX)
    parser.add_argument("--finbert-min-total-risk-score", type=float, default=FINBERT_MIN_TOTAL_RISK_SCORE)
    parser.add_argument(
        "--finbert-quality-risk-override-threshold",
        type=float,
        default=FINBERT_QUALITY_RISK_OVERRIDE_THRESHOLD,
    )
    parser.add_argument("--finbert-on-consecutive", type=int, default=FINBERT_ON_CONSECUTIVE)
    parser.add_argument("--finbert-off-consecutive", type=int, default=FINBERT_OFF_CONSECUTIVE)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2119.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2119_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2119")
    try:
        report, frame = run_a2119(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            args.finbert_daily,
            args.finbert_risk_on_threshold,
            args.finbert_risk_off_threshold,
            args.finbert_ma_gap_max,
            args.finbert_ma_gap_trigger_max,
            args.finbert_exit_momentum_max,
            args.finbert_min_total_risk_score,
            args.finbert_quality_risk_override_threshold,
            args.finbert_on_consecutive,
            args.finbert_off_consecutive,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Runner JSON: {Path(args.output).resolve()}")
    print(f"Runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
