#!/usr/bin/env python3
"""Review option-state coverage for GroupA+ overlay gates.

Research/operations diagnostic only. It checks whether TXO PCR and SOXX option
snapshot fields are sufficiently populated for deep-hedging-style overlay
reviews and trough/crash risk gates.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/option_state_coverage_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/option_state_coverage/history"
DEFAULT_TXO_OPTIONS_LAG_DAYS_MAX = 1
DEFAULT_SOXX_OPTIONS_SNAPSHOT_ROWS_MIN = 20
DEFAULT_SOXX_OPTIONS_VALID_ATM_IV_ROWS_MIN = 10
SOXX_ATM_IV_MIN = 0.05
SOXX_ATM_IV_MAX = 2.0


def _load_db_summary(db_path: Path) -> dict[str, Any]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        txo = con.execute(
            "SELECT COUNT(*) n, MIN(dt) min_dt, MAX(dt) max_dt FROM taifex_options_daily"
        ).fetchone()
        soxx = con.execute(
            """
            SELECT COUNT(*) n, MIN(dt) min_dt, MAX(dt) max_dt
            FROM external_options_iv
            WHERE provider='yfinance' AND underlying='SOXX'
            """
        ).fetchone()
        soxx_rows = con.execute(
            """
            SELECT dt, atm_iv, put_call_iv_skew, put_call_volume_ratio,
                   put_call_oi_ratio, contract_count
            FROM external_options_iv
            WHERE provider='yfinance' AND underlying='SOXX'
            ORDER BY dt
            """
        ).fetchdf()
    finally:
        con.close()
    return {
        "txo_options_daily": {
            "rows": int(txo[0] or 0),
            "min_dt": str(txo[1]) if txo[1] is not None else None,
            "max_dt": str(txo[2]) if txo[2] is not None else None,
        },
        "soxx_external_options_iv": {
            "rows": int(soxx[0] or 0),
            "min_dt": str(soxx[1]) if soxx[1] is not None else None,
            "max_dt": str(soxx[2]) if soxx[2] is not None else None,
            "latest_rows": [
                {
                    "dt": str(pd.Timestamp(row["dt"]).date()),
                    "atm_iv": _float_or_none(row.get("atm_iv")),
                    "put_call_iv_skew": _float_or_none(row.get("put_call_iv_skew")),
                    "put_call_volume_ratio": _float_or_none(row.get("put_call_volume_ratio")),
                    "put_call_oi_ratio": _float_or_none(row.get("put_call_oi_ratio")),
                    "contract_count": _float_or_none(row.get("contract_count")),
                }
                for _, row in soxx_rows.tail(10).iterrows()
            ],
        },
    }


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if pd.notna(out) else None


def build_review(
    db_path: Path,
    as_of: str,
    *,
    txo_options_lag_days_max: int = DEFAULT_TXO_OPTIONS_LAG_DAYS_MAX,
    soxx_options_snapshot_rows_min: int = DEFAULT_SOXX_OPTIONS_SNAPSHOT_ROWS_MIN,
    soxx_options_valid_atm_iv_rows_min: int = DEFAULT_SOXX_OPTIONS_VALID_ATM_IV_ROWS_MIN,
) -> dict[str, Any]:
    db = _load_db_summary(db_path)
    as_of_ts = pd.Timestamp(as_of).normalize()
    txo_max = pd.Timestamp(db["txo_options_daily"]["max_dt"]) if db["txo_options_daily"]["max_dt"] else None
    soxx_max = (
        pd.Timestamp(db["soxx_external_options_iv"]["max_dt"])
        if db["soxx_external_options_iv"]["max_dt"]
        else None
    )
    soxx_rows = int(db["soxx_external_options_iv"]["rows"])
    soxx_latest = db["soxx_external_options_iv"]["latest_rows"][-1] if db["soxx_external_options_iv"]["latest_rows"] else {}
    soxx_valid_rows = [
        row
        for row in db["soxx_external_options_iv"]["latest_rows"]
        if row.get("atm_iv") is not None and SOXX_ATM_IV_MIN <= float(row["atm_iv"]) <= SOXX_ATM_IV_MAX
    ]

    txo_lag_days = int((as_of_ts - txo_max).days) if txo_max is not None else None
    soxx_lag_days = int((as_of_ts - soxx_max).days) if soxx_max is not None else None
    blockers: list[str] = []
    warnings: list[str] = []
    if txo_max is None:
        blockers.append("txo_options_daily_missing")
    elif txo_lag_days is not None and txo_lag_days > txo_options_lag_days_max:
        blockers.append("txo_options_daily_stale_gt_1_day")
    if soxx_rows < soxx_options_snapshot_rows_min:
        blockers.append(f"soxx_options_iv_history_lt_{soxx_options_snapshot_rows_min}_snapshots")
    if len(soxx_valid_rows) < soxx_options_valid_atm_iv_rows_min:
        blockers.append(f"soxx_options_iv_valid_history_lt_{soxx_options_valid_atm_iv_rows_min}_snapshots")
    latest_atm_iv = soxx_latest.get("atm_iv")
    if latest_atm_iv is None or not (SOXX_ATM_IV_MIN <= float(latest_atm_iv) <= SOXX_ATM_IV_MAX):
        blockers.append("soxx_latest_atm_iv_outside_5pct_200pct")
    if soxx_lag_days is not None and soxx_lag_days > 3:
        warnings.append("soxx_options_iv_stale_gt_3_days")
    if soxx_latest.get("put_call_oi_ratio") is None:
        warnings.append("soxx_latest_put_call_oi_ratio_missing")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_option_state_coverage_review",
        "status": "blocked" if blockers else "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "diagnostic_only_no_weight_change",
        "as_of": str(as_of_ts.date()),
        "coverage": db,
        "requirements": {
            "txo_options_lag_days_max": int(txo_options_lag_days_max),
            "soxx_options_snapshot_rows_min": int(soxx_options_snapshot_rows_min),
            "soxx_options_valid_atm_iv_rows_min": int(soxx_options_valid_atm_iv_rows_min),
            "soxx_latest_atm_iv_range": [SOXX_ATM_IV_MIN, SOXX_ATM_IV_MAX],
        },
        "computed": {
            "txo_lag_days_vs_as_of": txo_lag_days,
            "soxx_lag_days_vs_as_of": soxx_lag_days,
            "soxx_valid_atm_iv_rows_in_latest_10": len(soxx_valid_rows),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "option_state_gate_passed": not blockers,
            "allow_deep_hedging_overlay_research_promotion": False,
            "target_weight_change_allowed": False,
            "summary": (
                "TXO options are mostly covered, but SOXX option IV history/quality is insufficient "
                "for z-score based overlay gates."
            ),
        },
    }


def _resolve_project_path(path: str | Path) -> Path:
    out = Path(path)
    return out if out.is_absolute() else PROJECT_ROOT / out


def _history_path(history_dir: Path, as_of: str) -> Path:
    stamp = pd.Timestamp(as_of).strftime("%Y%m%d")
    return history_dir / f"{stamp}.json"


def write_review(review: dict[str, Any], *, output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review["as_of"])).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default="2026-07-17")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--txo-options-lag-days-max", type=int, default=DEFAULT_TXO_OPTIONS_LAG_DAYS_MAX)
    parser.add_argument("--soxx-options-snapshot-rows-min", type=int, default=DEFAULT_SOXX_OPTIONS_SNAPSHOT_ROWS_MIN)
    parser.add_argument("--soxx-options-valid-atm-iv-rows-min", type=int, default=DEFAULT_SOXX_OPTIONS_VALID_ATM_IV_ROWS_MIN)
    args = parser.parse_args()

    output = _resolve_project_path(args.output)
    history_dir = None if args.no_history else _resolve_project_path(args.history_dir)
    review = build_review(
        Path(args.db),
        args.as_of,
        txo_options_lag_days_max=args.txo_options_lag_days_max,
        soxx_options_snapshot_rows_min=args.soxx_options_snapshot_rows_min,
        soxx_options_valid_atm_iv_rows_min=args.soxx_options_valid_atm_iv_rows_min,
    )
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"Option-state coverage review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review['as_of'])}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "option_state_gate_passed": review["decision"]["option_state_gate_passed"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
