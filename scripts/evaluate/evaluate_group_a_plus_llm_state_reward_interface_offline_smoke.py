#!/usr/bin/env python3
"""Offline smoke check for accepted LLM state/reward interface proposals.

This is intentionally small: it computes feature and reward proxies from daily
OHLCV only. It does not train PPO, output actions, produce target weights, or
connect to the live pipeline.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION = (
    PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_proposal_validation_review.json"
)
DEFAULT_DATA = PROJECT_ROOT / "data/cache/0050_TW_2016-01-01_2026-05-05_1d.parquet.bak"
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_offline_smoke_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_offline_smoke/history"


ACCEPTED_PROPOSAL_ID = "gift_research_momentum_vol_drawdown_turnover_v1"
DOWNSIDE_TAIL_DECAY_PROPOSAL_ID = "gift_research_downside_vol_letf_tail_decay_v1"

PROPOSAL_COLUMNS = {
    ACCEPTED_PROPOSAL_ID: {
        "feature_columns": ["relative_momentum", "realized_volatility"],
        "reward_columns": ["drawdown_penalty", "turnover_penalty", "reward_proxy"],
    },
    DOWNSIDE_TAIL_DECAY_PROPOSAL_ID: {
        "feature_columns": ["downside_deviation", "realized_volatility", "drawdown_depth", "ema_cross_strength"],
        "reward_columns": ["drawdown_penalty", "volatility_scaling_penalty", "letf_tail_decay_cost", "reward_proxy"],
    },
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ohlcv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix.lower() in {".parquet", ".bak"}:
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
    return df.reset_index(drop=True)


def _load_ohlcv_from_db(db_path: Path, *, ticker: str, start: str) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT
                dt AS date,
                open,
                high,
                low,
                close,
                volume,
                ticker AS symbol
            FROM ohlcv
            WHERE ticker = ? AND dt >= ?
            ORDER BY dt
            """,
            [ticker, start],
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.reset_index(drop=True)


def _accepted_proposals(validation: dict[str, Any]) -> list[str]:
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    ids = summary.get("accepted_proposal_ids")
    if isinstance(ids, list):
        return [str(item) for item in ids]
    results = validation.get("proposal_results") if isinstance(validation.get("proposal_results"), list) else []
    return [
        str(item.get("proposal_id"))
        for item in results
        if isinstance(item, dict) and item.get("accepted_for_offline_review") is True
    ]


def _proposal_columns(proposal_id: str) -> dict[str, list[str]]:
    return PROPOSAL_COLUMNS.get(proposal_id, PROPOSAL_COLUMNS[ACCEPTED_PROPOSAL_ID])


def _feature_frame(
    df: pd.DataFrame,
    *,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    momentum_window: int = 20,
    vol_window: int = 20,
    downside_drawdown_weight: float = 0.50,
    downside_volatility_weight: float = 0.30,
    downside_tail_decay_weight: float = 0.20,
    volatility_penalty_scale: float = 3.0,
    tail_decay_scale: float = 4.0,
) -> pd.DataFrame:
    out = df[["date", "close", "volume"]].copy()
    close = out["close"].astype(float)
    returns = close.pct_change()
    out["realized_volatility"] = returns.rolling(vol_window, min_periods=vol_window).std(ddof=0)
    out["drawdown"] = close / close.cummax() - 1.0
    out["drawdown_penalty"] = (-out["drawdown"]).clip(lower=0.0, upper=0.25)
    if proposal_id == DOWNSIDE_TAIL_DECAY_PROPOSAL_ID:
        downside = returns.clip(upper=0.0)
        out["downside_deviation"] = downside.rolling(vol_window, min_periods=vol_window).std(ddof=0)
        out["drawdown_depth"] = (-out["drawdown"]).clip(lower=0.0, upper=0.50)
        ema_fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
        ema_slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
        out["ema_cross_strength"] = (ema_fast / ema_slow - 1.0).clip(lower=-0.25, upper=0.25)
        out["volatility_scaling_penalty"] = (out["realized_volatility"] * volatility_penalty_scale).clip(
            lower=0.0,
            upper=0.25,
        )
        out["letf_tail_decay_cost"] = (
            out["drawdown_depth"].clip(lower=0.0, upper=0.25)
            * out["realized_volatility"].fillna(0.0)
            * tail_decay_scale
        ).clip(lower=0.0, upper=0.25)
        reward_cost = (
            downside_drawdown_weight * out["drawdown_penalty"].fillna(0.0)
            + downside_volatility_weight * out["volatility_scaling_penalty"].fillna(0.0)
            + downside_tail_decay_weight * out["letf_tail_decay_cost"].fillna(0.0)
        )
        out["reward_proxy"] = -reward_cost.clip(lower=0.0, upper=0.25)
    else:
        out["relative_momentum"] = close / close.shift(momentum_window) - 1.0
        out["turnover_penalty"] = 0.0
        out["reward_proxy"] = -(out["drawdown_penalty"] + out["turnover_penalty"]).clip(lower=0.0, upper=0.25)
    return out


def _finite_summary(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    rows = len(frame)
    summary: dict[str, Any] = {"rows": rows, "columns": {}}
    for column in columns:
        series = pd.to_numeric(frame[column], errors="coerce") if column in frame.columns else pd.Series(dtype=float)
        finite = np.isfinite(series.to_numpy(dtype=float, na_value=np.nan))
        summary["columns"][column] = {
            "non_null_count": int(series.notna().sum()),
            "finite_count": int(finite.sum()),
            "finite_ratio": float(finite.sum() / rows) if rows else 0.0,
            "min": float(np.nanmin(series.to_numpy(dtype=float))) if series.notna().any() else None,
            "max": float(np.nanmax(series.to_numpy(dtype=float))) if series.notna().any() else None,
        }
    return summary


def _window_summary(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str] | None = None,
    min_rows: int = 120,
) -> dict[str, Any]:
    if frame.empty or "date" not in frame.columns:
        return {"window_count": 0, "windows": [], "all_windows_have_min_rows": False}
    tmp = frame.copy()
    tmp["year"] = tmp["date"].dt.year
    ready_columns = feature_columns or ["relative_momentum", "realized_volatility"]
    windows = []
    for year, group in tmp.groupby("year"):
        feature_ready = group.dropna(subset=ready_columns)
        windows.append(
            {
                "year": int(year),
                "rows": int(len(group)),
                "feature_ready_rows": int(len(feature_ready)),
                "has_min_rows": bool(len(feature_ready) >= min_rows),
            }
        )
    return {
        "window_count": len(windows),
        "windows": windows,
        "all_windows_have_min_rows": all(item["has_min_rows"] for item in windows if item["year"] > windows[0]["year"])
        if windows
        else False,
    }


def build_review(
    *,
    validation_path: Path = DEFAULT_VALIDATION,
    data_path: Path = DEFAULT_DATA,
    db_path: Path = DEFAULT_DB,
    db_ticker: str = "0050.TW",
    db_start: str = "2016-01-01",
    use_db: bool = True,
    proposal_id: str = ACCEPTED_PROPOSAL_ID,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    validation = _load_json(validation_path)
    accepted_ids = _accepted_proposals(validation)
    db_df = _load_ohlcv_from_db(db_path, ticker=db_ticker, start=db_start) if use_db else pd.DataFrame()
    if not db_df.empty:
        df = db_df
        data_source = "duckdb_ohlcv"
        data_source_path = db_path
    else:
        df = _load_ohlcv(data_path)
        data_source = "parquet_or_csv_fallback"
        data_source_path = data_path

    blockers: list[str] = []
    warnings: list[str] = []
    if not validation:
        blockers.append("missing_proposal_validation_review")
    if proposal_id not in accepted_ids:
        blockers.append("accepted_sample_proposal_missing")
    if df.empty:
        blockers.append("missing_ohlcv_data")

    required_columns = {"date", "close", "volume"}
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        blockers.append(f"missing_data_columns:{','.join(missing_columns)}")

    frame = pd.DataFrame()
    if not blockers or not any(reason.startswith("missing_data_columns") for reason in blockers):
        if not df.empty and not missing_columns:
            frame = _feature_frame(df, proposal_id=proposal_id)

    columns = _proposal_columns(proposal_id)
    feature_columns = columns["feature_columns"]
    reward_columns = columns["reward_columns"]
    finite_summary = _finite_summary(frame, feature_columns + reward_columns) if not frame.empty else {}
    windows = _window_summary(frame, feature_columns=feature_columns) if not frame.empty else {}

    for column in feature_columns + reward_columns:
        column_summary = (finite_summary.get("columns") or {}).get(column) if finite_summary else None
        if not column_summary or column_summary.get("finite_count", 0) <= 0:
            blockers.append(f"no_finite_values:{column}")

    reward_proxy = frame["reward_proxy"] if "reward_proxy" in frame else pd.Series(dtype=float)
    if not reward_proxy.empty and (reward_proxy.min() < -0.25 or reward_proxy.max() > 0.0):
        blockers.append("reward_proxy_not_bounded")

    if windows and not windows.get("all_windows_have_min_rows"):
        warnings.append("some_yearly_windows_have_less_than_120_feature_ready_rows")

    data_range = {}
    if not df.empty and "date" in df.columns:
        data_range = {
            "start": df["date"].min().date().isoformat(),
            "end": df["date"].max().date().isoformat(),
            "rows": int(len(df)),
        }

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_offline_smoke_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "offline_smoke_only_no_model_training_no_live_action",
        "inputs": {
            "validation_review": str(validation_path),
            "data_source": data_source,
            "data": str(data_source_path),
            "fallback_data": str(data_path),
            "db": str(db_path),
            "db_ticker": db_ticker,
            "db_start": db_start,
            "accepted_proposal_id": proposal_id,
            "accepted_proposal_found": proposal_id in accepted_ids,
        },
        "data_range": data_range,
        "feature_proxy": {
            column: {"uses_future_data": False}
            for column in feature_columns
        },
        "reward_proxy": {
            column: {"bounded_range": [0.0, 0.25]}
            for column in reward_columns
            if column != "reward_proxy"
        }
        | {
            "reward_proxy": {"bounded_range": [-0.25, 0.0]},
        },
        "finite_summary": finite_summary,
        "window_summary": windows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
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
    return history_dir / f"llm_state_reward_interface_offline_smoke_{stamp}.json"


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
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--db-ticker", default="0050.TW")
    parser.add_argument("--db-start", default="2016-01-01")
    parser.add_argument("--no-db", action="store_true", help="Disable DuckDB OHLCV and use --data fallback.")
    parser.add_argument("--proposal-id", default=ACCEPTED_PROPOSAL_ID)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        validation_path=_resolve(args.validation),
        data_path=_resolve(args.data),
        db_path=_resolve(args.db),
        db_ticker=args.db_ticker,
        db_start=args.db_start,
        use_db=not args.no_db,
        proposal_id=args.proposal_id,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward offline smoke review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "rows": review.get("data_range", {}).get("rows"),
                "available_for_manual_offline_review": review["decision"]["available_for_manual_offline_review"],
                "promote_to_live": review["decision"]["promote_to_live"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
                "blocking_reasons": review["blocking_reasons"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
