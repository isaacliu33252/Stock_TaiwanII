#!/usr/bin/env python3
"""Build a 00631L rebound-gate shadow inspired by arXiv 2512.22895 SAMP-HDRL."""

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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.build_group_a_plus_2605_17307_ir2_candidate_scorecard import TICKERS, _float  # noqa: E402
from scripts.evaluate.build_group_a_plus_2606_09104_risk_aversion_forward_shadow import _load_close  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2512_22895_rebound_gate_00631l_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2512_22895_rebound_gate_00631l_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _future_return(series: pd.Series, pos: int, horizon: int) -> float | None:
    if pos + horizon >= len(series):
        return None
    start = float(series.iloc[pos])
    end = float(series.iloc[pos + horizon])
    if start <= 0:
        return None
    return float(end / start - 1.0)


def _future_mdd(series: pd.Series, pos: int, horizon: int) -> float | None:
    if pos + horizon >= len(series):
        return None
    path = series.iloc[pos : pos + horizon + 1].astype(float)
    peak = path.cummax()
    dd = path / peak - 1.0
    return float(dd.min())


def _event_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "event_count": 0,
            "mean_00631l_fwd20": None,
            "mean_0050_fwd20": None,
            "mean_excess_00631l_vs_0050": None,
            "win_rate_vs_0050": None,
            "mean_00631l_mdd20": None,
            "bad_mdd_gt5_rate": None,
        }
    frame = pd.DataFrame(rows)
    return {
        "event_count": int(len(frame)),
        "mean_00631l_fwd20": _float(frame["fwd_00631l_20d"].mean()),
        "mean_0050_fwd20": _float(frame["fwd_0050_20d"].mean()),
        "mean_excess_00631l_vs_0050": _float(frame["excess_00631l_vs_0050_20d"].mean()),
        "win_rate_vs_0050": _float((frame["excess_00631l_vs_0050_20d"] > 0.0).mean()),
        "mean_00631l_mdd20": _float(frame["mdd_00631l_20d"].mean()),
        "bad_mdd_gt5_rate": _float((frame["mdd_00631l_20d"] <= -0.05).mean()),
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    horizon: int = 20,
    decline_days: int = 3,
    rebound_days: int = 2,
    decline_threshold: float = -0.003,
    rebound_threshold: float = 0.0,
    min_events: int = 20,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, TICKERS, start, str(end_resolved)).ffill(limit=3)
    if close.empty or not {"0050.TW", "00631L.TW"}.issubset(close.columns):
        blockers.append("price_panel_missing")
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    events: list[dict[str, Any]] = []
    non_events: list[dict[str, Any]] = []
    latest_flags: dict[str, Any] = {}
    if not blockers:
        for pos in range(max(decline_days + rebound_days, 20), len(close) - horizon):
            date = close.index[pos]
            prior = returns["00631L.TW"].iloc[pos - decline_days - rebound_days + 1 : pos - rebound_days + 1]
            recent = returns["00631L.TW"].iloc[pos - rebound_days + 1 : pos + 1]
            ret_0050_5d = float(close["0050.TW"].iloc[pos] / close["0050.TW"].iloc[pos - 5] - 1.0)
            ret_00631l_5d = float(close["00631L.TW"].iloc[pos] / close["00631L.TW"].iloc[pos - 5] - 1.0)
            spread_5d = ret_00631l_5d - ret_0050_5d
            true_rebound = bool(
                len(prior.dropna()) == decline_days
                and len(recent.dropna()) == rebound_days
                and float(prior.mean()) < decline_threshold
                and bool((recent > rebound_threshold).all())
                and ret_0050_5d > -0.03
                and spread_5d > -0.03
            )
            fwd_631 = _future_return(close["00631L.TW"], pos, horizon)
            fwd_50 = _future_return(close["0050.TW"], pos, horizon)
            mdd_631 = _future_mdd(close["00631L.TW"], pos, horizon)
            if fwd_631 is None or fwd_50 is None or mdd_631 is None:
                continue
            row = {
                "date": str(pd.Timestamp(date).date()),
                "prior_decline_mean": _float(prior.mean()),
                "recent_rebound_min": _float(recent.min()),
                "ret_0050_5d": _float(ret_0050_5d),
                "ret_00631l_5d": _float(ret_00631l_5d),
                "spread_00631l_0050_5d": _float(spread_5d),
                "fwd_00631l_20d": _float(fwd_631),
                "fwd_0050_20d": _float(fwd_50),
                "excess_00631l_vs_0050_20d": _float(fwd_631 - fwd_50),
                "mdd_00631l_20d": _float(mdd_631),
                "true_rebound_gate": true_rebound,
            }
            (events if true_rebound else non_events).append(row)

        pos = len(close) - 1
        prior = returns["00631L.TW"].iloc[pos - decline_days - rebound_days + 1 : pos - rebound_days + 1]
        recent = returns["00631L.TW"].iloc[pos - rebound_days + 1 : pos + 1]
        ret_0050_5d = float(close["0050.TW"].iloc[pos] / close["0050.TW"].iloc[pos - 5] - 1.0)
        ret_00631l_5d = float(close["00631L.TW"].iloc[pos] / close["00631L.TW"].iloc[pos - 5] - 1.0)
        latest_true_rebound = bool(
            len(prior.dropna()) == decline_days
            and len(recent.dropna()) == rebound_days
            and float(prior.mean()) < decline_threshold
            and bool((recent > rebound_threshold).all())
            and ret_0050_5d > -0.03
            and (ret_00631l_5d - ret_0050_5d) > -0.03
        )
        latest_flags = {
            "date": str(pd.Timestamp(close.index[-1]).date()),
            "prior_decline_mean": _float(prior.mean()),
            "recent_rebound_min": _float(recent.min()),
            "ret_0050_5d": _float(ret_0050_5d),
            "ret_00631l_5d": _float(ret_00631l_5d),
            "spread_00631l_0050_5d": _float(ret_00631l_5d - ret_0050_5d),
            "true_rebound_gate": latest_true_rebound,
        }

    event_summary = _event_summary(events)
    non_event_summary = _event_summary(non_events)
    if event_summary["event_count"] < min_events and not blockers:
        blockers.append("insufficient_rebound_events")
    has_oos_value = bool(
        not blockers
        and (event_summary.get("mean_excess_00631l_vs_0050") or 0.0)
        > (non_event_summary.get("mean_excess_00631l_vs_0050") or 0.0)
        and (event_summary.get("win_rate_vs_0050") or 0.0) >= 0.55
        and (event_summary.get("bad_mdd_gt5_rate") or 1.0) <= 0.60
    )
    if not has_oos_value and not blockers:
        warnings.append("rebound_gate_not_promotable")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2512_22895_rebound_gate_00631l_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.22895.pdf",
            "imported_concept": "momentum_adjusted_utility_rebound_detection_shadow",
            "not_imported": ["hierarchical_DRL_training", "DDPG_allocator", "live_target_weight_generation"],
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "horizon": horizon,
            "decline_days": decline_days,
            "rebound_days": rebound_days,
            "decline_threshold": decline_threshold,
            "rebound_threshold": rebound_threshold,
            "fixed_no_sweep": True,
        },
        "latest_rebound_flags": latest_flags,
        "rebound_event_summary": event_summary,
        "non_rebound_summary": non_event_summary,
        "sample_rebound_events_tail": events[-10:],
        "decision": {
            "rebound_gate_has_forward_value": has_oos_value,
            "latest_true_rebound_gate": bool(latest_flags.get("true_rebound_gate")),
            "supports_new_00631l_add_today": bool(has_oos_value and latest_flags.get("true_rebound_gate")),
            "target_weight_change_allowed": False,
            "production_effect": "none",
            "summary": "Rebound gate is a fixed shadow diagnostic for 00631L adds; it cannot authorize live exposure.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2512_22895_rebound_gate_00631l_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(db_path=_resolve(args.db_path), start=args.start, end=args.end)
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
