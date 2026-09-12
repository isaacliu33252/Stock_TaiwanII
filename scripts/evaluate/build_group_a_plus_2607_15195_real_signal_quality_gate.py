#!/usr/bin/env python3
"""Build a real-signal quality gate for the 2607.15195 GroupA+ review.

The paper relies on an engineered oracle signal. This gate checks whether the
actual GroupA+ NCF 00631L panel has enough out-of-sample signal quality to
justify any SciPhyRL-like cost-aware optimizer research. It is shadow-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260716.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_15195_real_signal_quality_gate/history"
DEFAULT_SIGNAL_COLS = ("prob_up_h20", "ensemble_prob_up", "prob_up_h5", "prob_up_h1")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_00631l_returns(db_path: Path, start: str, end: str, horizon: int) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = '00631L.TW' AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["date"] = pd.to_datetime(rows["dt"])
    close = rows.set_index("date")["close"].astype(float)
    forward_return = close.shift(-horizon) / close - 1.0
    frame = pd.DataFrame({"date": close.index, "future_return_h20": forward_return.values})
    # Compute forward MDD with a clear loop; panel size is small.
    mdds: list[float | None] = []
    values = close.to_numpy(dtype=float)
    for idx in range(len(values)):
        future = values[idx + 1 : idx + 1 + horizon]
        if len(future) < horizon or values[idx] <= 0:
            mdds.append(None)
            continue
        rel = future / values[idx]
        rel = np.concatenate([[1.0], rel])
        mdds.append(float((rel / np.maximum.accumulate(rel) - 1.0).min()))
    frame["future_mdd_h20_from_db"] = mdds
    return frame


def _prepare_panel(panel_path: Path, db_path: Path, horizon: int) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    if not panel_path.exists():
        return pd.DataFrame(), ["panel_missing"]
    panel = pd.read_csv(panel_path)
    if "date" not in panel.columns:
        return pd.DataFrame(), ["panel_date_column_missing"]
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values("date")
    if "is_live" in panel.columns:
        eval_panel = panel[~panel["is_live"].astype(bool)].copy()
    else:
        eval_panel = panel.copy()
        warnings.append("is_live_column_missing_using_all_rows")
    start = str(panel["date"].min().date())
    end = str((panel["date"].max() + pd.Timedelta(days=horizon * 2)).date())
    db_returns = _load_00631l_returns(db_path, start, end, horizon)
    if db_returns.empty:
        warnings.append("db_forward_returns_unavailable_using_panel_realized_columns_only")
    else:
        eval_panel = eval_panel.merge(db_returns, on="date", how="left")
    if "future_return_h20" not in eval_panel.columns:
        if "forward_gain_h20" in eval_panel.columns and "forward_mdd_h20" in eval_panel.columns:
            gain = pd.to_numeric(eval_panel["forward_gain_h20"], errors="coerce")
            mdd = pd.to_numeric(eval_panel["forward_mdd_h20"], errors="coerce")
            eval_panel["future_return_h20"] = gain.where(gain.notna(), mdd)
        else:
            eval_panel["future_return_h20"] = np.nan
    if "future_mdd_h20_from_db" in eval_panel.columns:
        eval_panel["future_mdd_h20"] = eval_panel["future_mdd_h20_from_db"]
    elif "forward_mdd_h20" in eval_panel.columns:
        eval_panel["future_mdd_h20"] = pd.to_numeric(eval_panel["forward_mdd_h20"], errors="coerce")
    else:
        eval_panel["future_mdd_h20"] = np.nan
    return eval_panel, warnings


def _signal_metrics(df: pd.DataFrame, signal_col: str, min_rows: int) -> dict[str, Any]:
    if signal_col not in df.columns:
        return {"signal": signal_col, "status": "missing"}
    sample = df[["date", signal_col, "future_return_h20", "future_mdd_h20"]].copy()
    sample[signal_col] = pd.to_numeric(sample[signal_col], errors="coerce")
    sample = sample.dropna(subset=[signal_col, "future_return_h20"])
    if len(sample) < min_rows:
        return {"signal": signal_col, "status": "insufficient_rows", "observations": int(len(sample))}
    pred_up = sample[signal_col] >= 0.5
    realized_up = sample["future_return_h20"] > 0
    mdd_event = sample["future_mdd_h20"] <= -0.05
    return {
        "signal": signal_col,
        "status": "available",
        "observations": int(len(sample)),
        "rank_ic_future_return_h20": _float(sample[signal_col].corr(sample["future_return_h20"], method="spearman")),
        "pearson_future_return_h20": _float(sample[signal_col].corr(sample["future_return_h20"])),
        "direction_accuracy": _float((pred_up == realized_up).mean()),
        "mean_future_return_high_prob_top_30pct": _float(sample.nlargest(max(int(len(sample) * 0.3), 1), signal_col)["future_return_h20"].mean()),
        "mean_future_return_low_prob_bottom_30pct": _float(sample.nsmallest(max(int(len(sample) * 0.3), 1), signal_col)["future_return_h20"].mean()),
        "mdd_event_rate_high_prob_top_30pct": _float(mdd_event.loc[sample.nlargest(max(int(len(sample) * 0.3), 1), signal_col).index].mean()),
        "mdd_event_rate_low_prob_bottom_30pct": _float(mdd_event.loc[sample.nsmallest(max(int(len(sample) * 0.3), 1), signal_col).index].mean()),
    }


def _economic_trigger(df: pd.DataFrame, *, h20_max: float, conf_min: float, min_events: int) -> dict[str, Any]:
    needed = {"prob_up_h20", "confidence", "future_return_h20", "future_mdd_h20"}
    if not needed.issubset(df.columns):
        return {"status": "missing_columns", "required_columns": sorted(needed)}
    sample = df.copy()
    sample["prob_up_h20"] = pd.to_numeric(sample["prob_up_h20"], errors="coerce")
    sample["confidence"] = pd.to_numeric(sample["confidence"], errors="coerce")
    sample["future_return_h20"] = pd.to_numeric(sample["future_return_h20"], errors="coerce")
    sample["future_mdd_h20"] = pd.to_numeric(sample["future_mdd_h20"], errors="coerce")
    sample = sample.dropna(subset=["prob_up_h20", "confidence", "future_return_h20"])
    trigger = sample[(sample["prob_up_h20"] < h20_max) & (sample["confidence"] >= conf_min)]
    if trigger.empty:
        return {"status": "no_trigger_events", "event_count": 0, "min_events": min_events}
    avoided = -trigger["future_return_h20"]
    return {
        "status": "available" if len(trigger) >= min_events else "insufficient_events",
        "event_count": int(len(trigger)),
        "min_events": min_events,
        "h20_max": h20_max,
        "conf_min": conf_min,
        "mean_future_return_if_held_00631l": _float(trigger["future_return_h20"].mean()),
        "net_filter_value_vs_cash": _float(avoided.mean()),
        "hit_rate_avoided_loss": _float((trigger["future_return_h20"] < 0).mean()),
        "future_mdd_le_5pct_rate": _float((trigger["future_mdd_h20"] <= -0.05).mean()),
    }


def build_gate(
    *,
    panel_path: Path = DEFAULT_PANEL,
    db_path: Path = DB_PATH,
    horizon: int = 20,
    min_rows: int = 120,
    min_rank_ic: float = 0.05,
    min_direction_accuracy: float = 0.52,
    h20_max: float = 0.33,
    conf_min: float = 0.55,
    min_trigger_events: int = 10,
    min_net_filter_value: float = 0.005,
) -> dict[str, Any]:
    blockers: list[str] = []
    panel, warnings = _prepare_panel(_resolve(panel_path), _resolve(db_path), horizon)
    if panel.empty:
        blockers.append("signal_panel_unavailable")
    metrics = [] if panel.empty else [_signal_metrics(panel, col, min_rows) for col in DEFAULT_SIGNAL_COLS]
    primary = next((row for row in metrics if row.get("signal") == "prob_up_h20"), {})
    economic = {} if panel.empty else _economic_trigger(panel, h20_max=h20_max, conf_min=conf_min, min_events=min_trigger_events)

    if primary.get("status") != "available":
        blockers.append("primary_h20_signal_quality_unavailable")
    else:
        if not isinstance(primary.get("rank_ic_future_return_h20"), (int, float)) or float(primary["rank_ic_future_return_h20"]) < min_rank_ic:
            blockers.append("primary_h20_rank_ic_below_minimum")
        if not isinstance(primary.get("direction_accuracy"), (int, float)) or float(primary["direction_accuracy"]) < min_direction_accuracy:
            blockers.append("primary_h20_direction_accuracy_below_minimum")
    if economic.get("status") != "available":
        blockers.append("a2118_bad_signal_trigger_economic_sample_insufficient")
    else:
        if not isinstance(economic.get("net_filter_value_vs_cash"), (int, float)) or float(economic["net_filter_value_vs_cash"]) < min_net_filter_value:
            blockers.append("a2118_bad_signal_trigger_net_filter_value_below_minimum")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_15195_real_signal_quality_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "pass" if not blockers else "blocked",
        "as_of": str(panel["date"].max().date()) if not panel.empty else None,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "paper_title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "risk_checked": "paper_uses_engineered_oracle_signal_so_groupa_plus_requires_real_oos_signal_quality",
        },
        "parameters": {
            "panel_path": str(panel_path),
            "horizon": horizon,
            "min_rows": min_rows,
            "min_rank_ic": min_rank_ic,
            "min_direction_accuracy": min_direction_accuracy,
            "h20_max": h20_max,
            "conf_min": conf_min,
            "min_trigger_events": min_trigger_events,
            "min_net_filter_value": min_net_filter_value,
        },
        "coverage": {
            "evaluation_rows": int(len(panel)),
            "date_start": str(panel["date"].min().date()) if not panel.empty else None,
            "date_end": str(panel["date"].max().date()) if not panel.empty else None,
        },
        "signal_quality": metrics,
        "a2118_bad_signal_trigger_economic_review": economic,
        "decision": {
            "real_signal_quality_sufficient_for_sciphyrl_optimizer_research": not blockers,
            "allow_oracle_signal_assumption": False,
            "train_sciphyrl_or_pinn_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Only real OOS signal quality may justify SciPhyRL-like optimizer research; oracle-signal paper results are not promotion evidence.",
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
    (history_dir / f"2607_15195_real_signal_quality_gate_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--min-rows", type=int, default=120)
    parser.add_argument("--min-rank-ic", type=float, default=0.05)
    parser.add_argument("--min-direction-accuracy", type=float, default=0.52)
    parser.add_argument("--h20-max", type=float, default=0.33)
    parser.add_argument("--conf-min", type=float, default=0.55)
    parser.add_argument("--min-trigger-events", type=int, default=10)
    parser.add_argument("--min-net-filter-value", type=float, default=0.005)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gate = build_gate(
        panel_path=_resolve(args.panel),
        db_path=_resolve(args.db_path),
        horizon=args.horizon,
        min_rows=args.min_rows,
        min_rank_ic=args.min_rank_ic,
        min_direction_accuracy=args.min_direction_accuracy,
        h20_max=args.h20_max,
        conf_min=args.conf_min,
        min_trigger_events=args.min_trigger_events,
        min_net_filter_value=args.min_net_filter_value,
    )
    write_gate(gate, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(gate["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
