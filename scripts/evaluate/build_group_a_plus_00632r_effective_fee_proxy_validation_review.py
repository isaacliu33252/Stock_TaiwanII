#!/usr/bin/env python3
"""Validate the 00632R effective-fee / effective-drag proxy.

This independently recomputes tracking error, variance-decay, and effective
drag from daily OHLCV. It validates whether the proxy is usable as
manual-review evidence only; it does not permit 00632R opens or target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_letf_tracking_error_effective_fee_readiness_review import (
    DEFAULT_DB,
    _load_close_panel,
)


DEFAULT_TAIL_GATE = PROJECT_ROOT / "report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/00632r_effective_fee_proxy_validation/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _summary(series: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {"count": 0, "mean": None, "std": None, "p05": None, "p50": None, "p95": None, "latest": None}
    return {
        "count": int(len(clean)),
        "mean": _finite(clean.mean()),
        "std": _finite(clean.std(ddof=0)),
        "p05": _finite(clean.quantile(0.05)),
        "p50": _finite(clean.quantile(0.50)),
        "p95": _finite(clean.quantile(0.95)),
        "latest": _finite(clean.iloc[-1]),
    }


def _series_frame(
    panel: pd.DataFrame,
    *,
    reference_ticker: str,
    inverse_ticker: str,
    beta: float,
    horizon: int,
) -> pd.DataFrame:
    close = panel[[reference_ticker, inverse_ticker]].dropna()
    ref_log_1d = np.log(close[reference_ticker] / close[reference_ticker].shift(1))
    ref_h = np.log(close[reference_ticker] / close[reference_ticker].shift(horizon))
    inv_h = np.log(close[inverse_ticker] / close[inverse_ticker].shift(horizon))
    realized_variance = ref_log_1d.pow(2).rolling(horizon).sum()
    variance_decay_proxy = ((beta - beta**2) / 2.0) * realized_variance
    tracking_error = inv_h - beta * ref_h
    effective_drag_proxy = tracking_error - variance_decay_proxy
    out = pd.DataFrame(
        {
            "tracking_error": tracking_error,
            "variance_decay_proxy": variance_decay_proxy,
            "effective_drag_proxy": effective_drag_proxy,
            "realized_variance": realized_variance,
        }
    ).dropna()
    out.index = pd.to_datetime(out.index)
    return out


def _tail_overlap(frame: pd.DataFrame, *, quantile: float) -> dict[str, Any]:
    if frame.empty:
        return {"tracking_tail_count": 0, "drag_tail_count": 0, "overlap_count": 0, "overlap_rate": None}
    te_cut = frame["tracking_error"].quantile(quantile)
    drag_cut = frame["effective_drag_proxy"].quantile(quantile)
    te_tail = frame["tracking_error"] <= te_cut
    drag_tail = frame["effective_drag_proxy"] <= drag_cut
    overlap = te_tail & drag_tail
    return {
        "tracking_tail_threshold": _finite(te_cut),
        "drag_tail_threshold": _finite(drag_cut),
        "tracking_tail_count": int(te_tail.sum()),
        "drag_tail_count": int(drag_tail.sum()),
        "overlap_count": int(overlap.sum()),
        "overlap_rate": _finite(overlap.sum() / max(int(te_tail.sum()), 1)),
    }


def _horizon_validation(
    frame: pd.DataFrame,
    *,
    horizon: int,
    recent_observations: int,
    tail_quantile: float,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "horizon_days": horizon,
            "status": "no_data",
            "full_sample": {},
            "recent_sample": {},
            "validation_metrics": {},
        }
    full_corr = frame["tracking_error"].corr(frame["effective_drag_proxy"])
    full_sign_agreement = (np.sign(frame["tracking_error"]) == np.sign(frame["effective_drag_proxy"])).mean()
    recent = frame.tail(recent_observations)
    recent_corr = recent["tracking_error"].corr(recent["effective_drag_proxy"]) if len(recent) > 1 else np.nan
    recent_sign_agreement = (
        (np.sign(recent["tracking_error"]) == np.sign(recent["effective_drag_proxy"])).mean() if len(recent) else np.nan
    )
    residual = frame["tracking_error"] - frame["effective_drag_proxy"]
    return {
        "horizon_days": horizon,
        "status": "available",
        "full_sample": {
            "start": frame.index.min().date().isoformat(),
            "end": frame.index.max().date().isoformat(),
            "tracking_error": _summary(frame["tracking_error"]),
            "effective_drag_proxy": _summary(frame["effective_drag_proxy"]),
            "variance_decay_proxy": _summary(frame["variance_decay_proxy"]),
            "residual_tracking_minus_drag": _summary(residual),
        },
        "recent_sample": {
            "observations": int(len(recent)),
            "tracking_error": _summary(recent["tracking_error"]),
            "effective_drag_proxy": _summary(recent["effective_drag_proxy"]),
        },
        "validation_metrics": {
            "tracking_vs_drag_correlation": _finite(full_corr),
            "tracking_vs_drag_sign_agreement": _finite(full_sign_agreement),
            "recent_tracking_vs_drag_correlation": _finite(recent_corr),
            "recent_tracking_vs_drag_sign_agreement": _finite(recent_sign_agreement),
            "tail_overlap": _tail_overlap(frame, quantile=tail_quantile),
        },
    }


def build_review(
    *,
    db_path: Path = DEFAULT_DB,
    tail_gate_path: Path = DEFAULT_TAIL_GATE,
    as_of: str | None = "2026-07-20",
    start: str = "2020-01-01",
    reference_ticker: str = "0050.TW",
    inverse_ticker: str = "00632R.TW",
    beta: float = -1.0,
    horizons: list[int] | None = None,
    recent_observations: int = 60,
    correlation_floor: float = 0.95,
    sign_agreement_floor: float = 0.85,
    tail_overlap_floor: float = 0.80,
    tail_quantile: float = 0.05,
) -> dict[str, Any]:
    horizon_values = horizons or [5, 10, 20, 30]
    tail_gate = _load(tail_gate_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not db_path.exists():
        blockers.append("missing_duckdb")
    if not tail_gate:
        blockers.append("missing_tail_tracking_error_gate_review")

    panel = (
        _load_close_panel(db_path, tickers=[reference_ticker, inverse_ticker], start=start, as_of=as_of)
        if db_path.exists()
        else pd.DataFrame()
    )
    if panel.empty:
        blockers.append("missing_ohlcv_panel")

    horizon_results = []
    for horizon in horizon_values:
        frame = (
            _series_frame(
                panel,
                reference_ticker=reference_ticker,
                inverse_ticker=inverse_ticker,
                beta=beta,
                horizon=horizon,
            )
            if not panel.empty
            else pd.DataFrame()
        )
        horizon_results.append(
            _horizon_validation(
                frame,
                horizon=horizon,
                recent_observations=recent_observations,
                tail_quantile=tail_quantile,
            )
        )

    failed_horizons: list[str] = []
    for row in horizon_results:
        metrics = row.get("validation_metrics") or {}
        corr = _finite(metrics.get("tracking_vs_drag_correlation"))
        sign = _finite(metrics.get("tracking_vs_drag_sign_agreement"))
        overlap = _finite((metrics.get("tail_overlap") or {}).get("overlap_rate"))
        horizon = str(row.get("horizon_days"))
        if corr is None or corr < correlation_floor:
            failed_horizons.append(f"{horizon}:correlation")
        if sign is None or sign < sign_agreement_floor:
            failed_horizons.append(f"{horizon}:sign_agreement")
        if overlap is None or overlap < tail_overlap_floor:
            failed_horizons.append(f"{horizon}:tail_overlap")

    proxy_validated_for_manual_review = not blockers and not failed_horizons
    if failed_horizons:
        blockers.append("effective_fee_proxy_validation_metrics_failed")
    if proxy_validated_for_manual_review and tail_gate.get("decision", {}).get("allow_00632r_open") is not True:
        warnings.append("proxy_validated_for_manual_review_but_tail_gate_still_blocks_live_action")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_00632r_effective_fee_proxy_validation_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "validated_for_manual_review_only" if proxy_validated_for_manual_review else "blocked",
        "policy": "effective_fee_proxy_validation_only_no_hedge_open_no_weight_change",
        "inputs": {
            "db": str(db_path),
            "tail_tracking_error_gate_review": str(tail_gate_path),
            "reference_ticker": reference_ticker,
            "inverse_ticker": inverse_ticker,
            "start": start,
            "horizons": horizon_values,
            "recent_observations": recent_observations,
        },
        "thresholds": {
            "correlation_floor": correlation_floor,
            "sign_agreement_floor": sign_agreement_floor,
            "tail_overlap_floor": tail_overlap_floor,
            "tail_quantile": tail_quantile,
        },
        "horizon_results": horizon_results,
        "summary": {
            "proxy_validated_for_manual_review": proxy_validated_for_manual_review,
            "failed_horizons": failed_horizons,
            "available_horizon_count": sum(1 for row in horizon_results if row.get("status") == "available"),
            "tail_gate_split_recommended": (tail_gate.get("decision") or {}).get("gate_split_recommended"),
            "tail_gate_allows_00632r_open": (tail_gate.get("decision") or {}).get("allow_00632r_open"),
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "Validation checks whether effective drag tracks realized tracking error closely enough for manual-review evidence.",
            "Passing this review does not validate a live hedge policy, market-impact readiness, or target-weight changes.",
            "00632R remains blocked for live action unless every other readiness gate changes.",
        ],
        "decision": {
            "effective_fee_proxy_validated_for_manual_review": proxy_validated_for_manual_review,
            "effective_fee_proxy_validated_for_live": False,
            "manual_hedge_discussion_allowed": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"00632r_effective_fee_proxy_validation_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--tail-gate", default=str(DEFAULT_TAIL_GATE))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--reference-ticker", default="0050.TW")
    parser.add_argument("--inverse-ticker", default="00632R.TW")
    parser.add_argument("--horizon", action="append", type=int, default=[])
    parser.add_argument("--recent-observations", type=int, default=60)
    parser.add_argument("--correlation-floor", type=float, default=0.95)
    parser.add_argument("--sign-agreement-floor", type=float, default=0.85)
    parser.add_argument("--tail-overlap-floor", type=float, default=0.80)
    parser.add_argument("--tail-quantile", type=float, default=0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        db_path=_resolve(args.db),
        tail_gate_path=_resolve(args.tail_gate),
        as_of=args.as_of,
        start=args.start,
        reference_ticker=args.reference_ticker,
        inverse_ticker=args.inverse_ticker,
        horizons=args.horizon or None,
        recent_observations=args.recent_observations,
        correlation_floor=args.correlation_floor,
        sign_agreement_floor=args.sign_agreement_floor,
        tail_overlap_floor=args.tail_overlap_floor,
        tail_quantile=args.tail_quantile,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"00632R effective-fee proxy validation review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "proxy_validated_for_manual_review": review["summary"]["proxy_validated_for_manual_review"],
                "failed_horizons": review["summary"]["failed_horizons"],
                "manual_hedge_discussion_allowed": review["decision"]["manual_hedge_discussion_allowed"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
