#!/usr/bin/env python3
"""Sweep defensive cash floors for the adaptive quantile gate.

Research-only. The first full-frame validation showed the quantile gate barely
acted because latest GroupA+ already carries almost no 00631L. This sweep tests
the next logical shadow improvement: raise cash inside `group_a_plus_defensive`
only when observable risk is elevated.
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

from scripts.evaluate.backtest_group_a_plus_adaptive_quantile_risk_gate_frame import (  # noqa: E402
    DB_PATH,
    DEFAULT_FRAME,
    DEFAULT_REPORT,
    DEFAULT_TICKERS,
    _json_default,
    _load_close,
    _load_report,
    _metrics,
    _next_return,
    _normalize,
    _turnover_cost,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json"


def _parse_ints(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def _parse_floats(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def _raise_cash_floor(weights: dict[str, float], floor: float, tickers: tuple[str, ...]) -> tuple[dict[str, float], bool]:
    adjusted = dict(weights)
    gap = float(floor) - adjusted.get("cash", 0.0)
    if gap <= 1e-12:
        return adjusted, False
    risk_tickers = [ticker for ticker in tickers if adjusted.get(ticker, 0.0) > 0]
    total_risk = sum(adjusted[ticker] for ticker in risk_tickers)
    if total_risk <= 0:
        return adjusted, False
    take = min(gap, total_risk)
    for ticker in risk_tickers:
        adjusted[ticker] -= take * adjusted[ticker] / total_risk
    adjusted["cash"] += take
    return _normalize(adjusted, tickers), True


def _variant_replay(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    *,
    cash_floor: float,
    total_risk_min: int,
    tail_risk_min: int,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> dict[str, Any]:
    weights_by_regime = report.get("base_weights") or report.get("weights") or {}
    work = frame.copy()
    work["dt"] = pd.to_datetime(work["dt"]).dt.normalize()
    rows: list[dict[str, Any]] = []
    prev_raw: dict[str, float] | None = None
    prev_variant: dict[str, float] | None = None

    for _, row in work.iterrows():
        regime = str(row.get("execution_regime") or row.get("base_regime") or "")
        if regime not in weights_by_regime:
            continue
        raw = _normalize(dict(weights_by_regime[regime]), tickers)
        variant = dict(raw)
        total_risk = int(float(row.get("total_risk_score", 0.0) or 0.0))
        tail_risk = int(float(row.get("tail_risk_score", 0.0) or 0.0))
        active = regime == "group_a_plus_defensive" and (total_risk >= total_risk_min or tail_risk >= tail_risk_min)
        changed = False
        if active:
            variant, changed = _raise_cash_floor(variant, cash_floor, tickers)

        raw_ret, next_date = _next_return(close, row["dt"], raw, tickers)
        variant_ret, _ = _next_return(close, row["dt"], variant, tickers)
        if raw_ret is None or variant_ret is None:
            continue
        raw_net = raw_ret - _turnover_cost(prev_raw, raw, tickers)
        variant_net = variant_ret - _turnover_cost(prev_variant, variant, tickers)
        rows.append(
            {
                "date": str(pd.Timestamp(row["dt"]).date()),
                "next_date": next_date,
                "execution_regime": regime,
                "total_risk_score": total_risk,
                "tail_risk_score": tail_risk,
                "active": active,
                "changed": changed,
                "raw_net_return": raw_net,
                "variant_net_return": variant_net,
                "delta_net_return": variant_net - raw_net,
                "raw_cash_weight": raw.get("cash", 0.0),
                "variant_cash_weight": variant.get("cash", 0.0),
            }
        )
        prev_raw = raw
        prev_variant = variant

    raw_metrics = _metrics(rows, "raw_net_return")
    variant_metrics = _metrics(rows, "variant_net_return")
    return {
        "cash_floor": cash_floor,
        "total_risk_min": total_risk_min,
        "tail_risk_min": tail_risk_min,
        "active_days": sum(row["active"] for row in rows),
        "changed_days": sum(row["changed"] for row in rows),
        "raw_metrics": raw_metrics,
        "variant_metrics": variant_metrics,
        "delta": {
            "total_return_delta": variant_metrics["total_return"] - raw_metrics["total_return"],
            "sharpe_delta": variant_metrics["sharpe_ratio"] - raw_metrics["sharpe_ratio"],
            "max_drawdown_delta": variant_metrics["max_drawdown"] - raw_metrics["max_drawdown"],
            "worst_day_delta": variant_metrics["worst_day"] - raw_metrics["worst_day"],
        },
        "rows": rows,
    }


def _score(result: dict[str, Any]) -> float:
    delta = result["delta"]
    return float(
        delta["total_return_delta"]
        + 0.20 * delta["sharpe_delta"]
        + 0.75 * delta["max_drawdown_delta"]
        + 0.50 * delta["worst_day_delta"]
    )


def sweep(
    report: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.DataFrame,
    *,
    cash_floors: list[float],
    total_risk_mins: list[int],
    tail_risk_mins: list[int],
) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for cash_floor in cash_floors:
        for total_risk_min in total_risk_mins:
            for tail_risk_min in tail_risk_mins:
                result = _variant_replay(
                    report,
                    frame,
                    close,
                    cash_floor=cash_floor,
                    total_risk_min=total_risk_min,
                    tail_risk_min=tail_risk_min,
                )
                name = f"cash{int(cash_floor * 100):02d}_risk{total_risk_min}_tail{tail_risk_min}"
                row = {
                    "variant": name,
                    "score": _score(result),
                    "cash_floor": cash_floor,
                    "total_risk_min": total_risk_min,
                    "tail_risk_min": tail_risk_min,
                    "active_days": result["active_days"],
                    "changed_days": result["changed_days"],
                    **result["variant_metrics"],
                    **{f"delta_{key}": value for key, value in result["delta"].items()},
                }
                variants.append(row)
                details[name] = result
    ranked = sorted(variants, key=lambda row: (row["score"], row["delta_total_return_delta"]), reverse=True)
    best = ranked[0] if ranked else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_defensive_cash_floor_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ok" if ranked else "no_variants",
        "method": "Raise cash only inside group_a_plus_defensive when total_risk_score or tail_risk_score crosses candidate thresholds.",
        "top_variants": ranked[:20],
        "best_variant_detail": details[best["variant"]] if best else None,
        "decision": {
            "promotion_decision": "shadow_candidate_for_deeper_walkforward" if best and best["delta_max_drawdown_delta"] > 0 and best["delta_total_return_delta"] >= -0.002 else "do_not_promote",
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--frame", default=str(DEFAULT_FRAME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--cash-floors", default="0.40,0.45,0.50,0.55")
    parser.add_argument("--total-risk-mins", default="5,6,7,8")
    parser.add_argument("--tail-risk-mins", default="1,2,99")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = _load_report(Path(args.report))
    frame = pd.read_csv(args.frame)
    close = _load_close(Path(args.db), DEFAULT_TICKERS)
    result = sweep(
        report,
        frame,
        close,
        cash_floors=_parse_floats(args.cash_floors),
        total_risk_mins=_parse_ints(args.total_risk_mins),
        tail_risk_mins=_parse_ints(args.tail_risk_mins),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    pd.DataFrame(result["top_variants"]).to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    best = result["top_variants"][0]
    print(
        "best={variant} score={score:.6f} total_delta={total:.4%} mdd_delta={mdd:.4%} sharpe_delta={sharpe:.4f} changed={changed}".format(
            variant=best["variant"],
            score=best["score"],
            total=best["delta_total_return_delta"],
            mdd=best["delta_max_drawdown_delta"],
            sharpe=best["delta_sharpe_delta"],
            changed=best["changed_days"],
        )
    )
    print(f"JSON: {output}")
    print(f"CSV:  {output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
