#!/usr/bin/env python3
"""Validate the adaptive-quantile defensive cash-floor candidate by windows."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_SWEEP = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_sweep_latest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_adaptive_quantile_defensive_cash_floor_validation_latest.json"

CRISIS_WINDOWS = {
    "2024_q3_ai_selloff": ("2024-07-01", "2024-09-30"),
    "2025_tariff_shock": ("2025-02-24", "2025-05-09"),
    "2026_summer_drawdown": ("2026-06-01", "2026-08-05"),
}


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _metrics(rows: pd.DataFrame, column: str) -> dict[str, Any]:
    returns = rows[column].astype(float)
    if returns.empty:
        return {"n": 0}
    equity = (1.0 + returns).cumprod()
    peak = equity.cummax()
    std = returns.std(ddof=0)
    return {
        "n": int(len(returns)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "mean_daily_return": float(returns.mean()),
        "sharpe_ratio": float(returns.mean() / std * math.sqrt(252)) if std > 0 else 0.0,
        "max_drawdown": float((equity / peak - 1.0).min()),
        "worst_day": float(returns.min()),
        "positive_day_rate": float((returns > 0).mean()),
    }


def _window_result(rows: pd.DataFrame, *, name: str, start: str, end: str) -> dict[str, Any]:
    mask = (rows["date"] >= start) & (rows["date"] <= end)
    subset = rows.loc[mask].copy()
    raw = _metrics(subset, "raw_net_return")
    variant = _metrics(subset, "variant_net_return")
    if raw["n"] == 0:
        return {"window": name, "start": start, "end": end, "status": "no_rows", "n": 0}
    delta = {
        "total_return_delta": variant["total_return"] - raw["total_return"],
        "sharpe_delta": variant["sharpe_ratio"] - raw["sharpe_ratio"],
        "max_drawdown_delta": variant["max_drawdown"] - raw["max_drawdown"],
        "worst_day_delta": variant["worst_day"] - raw["worst_day"],
    }
    checks = {
        "nonworse_total_return": delta["total_return_delta"] >= -0.002,
        "nonworse_max_drawdown": delta["max_drawdown_delta"] >= -1e-12,
        "nonworse_worst_day": delta["worst_day_delta"] >= -1e-12,
        "changed_days_present": int(subset["changed"].sum()) > 0,
    }
    return {
        "window": name,
        "start": start,
        "end": end,
        "status": "ok",
        "n": int(len(subset)),
        "changed_days": int(subset["changed"].sum()),
        "active_days": int(subset["active"].sum()),
        "raw_metrics": raw,
        "variant_metrics": variant,
        "delta": delta,
        "checks": checks,
        "window_pass": all(checks.values()),
    }


def validate_sweep(
    sweep: dict[str, Any],
    *,
    variant_name: str | None = None,
) -> dict[str, Any]:
    detail = sweep.get("best_variant_detail") or {}
    if variant_name:
        best = next((row for row in sweep.get("top_variants", []) if row.get("variant") == variant_name), None)
        if best is None:
            return {"status": "missing_variant", "variant": variant_name}
        if best != (sweep.get("top_variants") or [{}])[0]:
            return {
                "status": "variant_detail_unavailable",
                "variant": variant_name,
                "reason": "sweep file stores detailed rows only for best_variant_detail",
            }
    variant = variant_name or ((sweep.get("top_variants") or [{}])[0].get("variant"))
    rows = pd.DataFrame(detail.get("rows") or [])
    if rows.empty:
        return {"status": "missing_rows", "variant": variant}
    rows["date"] = rows["date"].astype(str)

    start = str(rows["date"].min())
    end = str(rows["date"].max())
    windows: list[dict[str, Any]] = []
    windows.append(_window_result(rows, name="full", start=start, end=end))
    for year in sorted({date[:4] for date in rows["date"]}):
        windows.append(_window_result(rows, name=f"year_{year}", start=f"{year}-01-01", end=f"{year}-12-31"))
    for name, (win_start, win_end) in CRISIS_WINDOWS.items():
        windows.append(_window_result(rows, name=name, start=win_start, end=win_end))

    evaluable = [row for row in windows if row.get("status") == "ok" and row.get("changed_days", 0) > 0]
    pass_count = sum(bool(row.get("window_pass")) for row in evaluable)
    fail_windows = [row["window"] for row in evaluable if not row.get("window_pass")]
    promotion = (
        "shadow_candidate_for_fold_ablation"
        if evaluable and pass_count == len(evaluable) and windows[0].get("window_pass")
        else "do_not_promote"
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_adaptive_quantile_defensive_cash_floor_validation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "variant": variant,
        "source_report_type": sweep.get("report_type"),
        "summary": {
            "window_count": len(windows),
            "evaluable_changed_window_count": len(evaluable),
            "pass_count": pass_count,
            "fail_windows": fail_windows,
        },
        "windows": windows,
        "decision": {
            "promotion_decision": promotion,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "reason": (
                "passes all changed windows; still needs fold ablation/signed review"
                if promotion != "do_not_promote"
                else "one or more changed windows failed or evidence is insufficient"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--variant", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    sweep = json.loads(Path(args.sweep).read_text(encoding="utf-8-sig"))
    report = validate_sweep(sweep, variant_name=args.variant)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")

    print(
        "variant={variant} decision={decision} pass={passed}/{total} fails={fails}".format(
            variant=report.get("variant"),
            decision=(report.get("decision") or {}).get("promotion_decision"),
            passed=(report.get("summary") or {}).get("pass_count"),
            total=(report.get("summary") or {}).get("evaluable_changed_window_count"),
            fails=(report.get("summary") or {}).get("fail_windows"),
        )
    )
    print(f"JSON: {output}")


if __name__ == "__main__":
    main()
