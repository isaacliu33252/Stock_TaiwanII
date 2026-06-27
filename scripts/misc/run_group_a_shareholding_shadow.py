#!/usr/bin/env python3
"""Generate an advisory-only Group A TDCC shareholding research signal."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_shareholding_shadow_config.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"
LATEST_JSON = DEFAULT_OUTPUT_DIR / "group_a_shareholding_shadow_latest.json"
HISTORY_JSONL = DEFAULT_OUTPUT_DIR / "group_a_shareholding_shadow_history.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--as-of-date", default=str(date.today()), help="YYYY-MM-DD")
    return parser.parse_args()


def _load_weekly_features(db_path: Path, stock_id: str, cutoff_date: str) -> pd.DataFrame:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        tiers = conn.execute(
            """
            SELECT dt, holding_level, people, percent
            FROM shareholding_distribution
            WHERE stock_id = ? AND dt <= ?
            ORDER BY dt, holding_level
            """,
            [stock_id, cutoff_date],
        ).fetchdf()
    finally:
        conn.close()
    if tiers.empty:
        return pd.DataFrame()

    tiers["minority_percent"] = tiers["percent"].where(tiers["holding_level"].between(1, 5), 0.0)
    tiers["major_percent"] = tiers["percent"].where(tiers["holding_level"].between(12, 15), 0.0)
    total_people = (
        tiers.loc[tiers["holding_level"] == 17, ["dt", "people"]]
        .drop_duplicates(subset=["dt"], keep="last")
        .rename(columns={"people": "total_people"})
    )
    return (
        tiers.groupby("dt", as_index=False)[["minority_percent", "major_percent"]]
        .sum()
        .merge(total_people, on="dt", how="left")
        .sort_values("dt")
        .reset_index(drop=True)
    )


def _ticker_snapshot(features: pd.DataFrame, lookback_weeks: int) -> dict[str, object]:
    if features.empty:
        return {"available": False}
    latest = features.iloc[-1]
    prior = features.iloc[max(len(features) - 1 - lookback_weeks, 0)]
    prior_people = int(prior["total_people"])
    people_change_ratio = (
        (int(latest["total_people"]) - prior_people) / prior_people if prior_people else 0.0
    )
    return {
        "available": True,
        "data_date": str(pd.Timestamp(latest["dt"]).date()),
        "comparison_date": str(pd.Timestamp(prior["dt"]).date()),
        "comparison_weeks": int(min(lookback_weeks, len(features) - 1)),
        "minority_percent": float(latest["minority_percent"]),
        "major_percent": float(latest["major_percent"]),
        "total_people": int(latest["total_people"]),
        "minority_percent_change": float(latest["minority_percent"] - prior["minority_percent"]),
        "major_percent_change": float(latest["major_percent"] - prior["major_percent"]),
        "total_people_change": int(latest["total_people"] - prior_people),
        "total_people_change_ratio": float(people_change_ratio),
    }


def assess_shadow_signal(config: dict[str, object], snapshots: dict[str, dict[str, object]]) -> dict[str, object]:
    leverage_ticker = str(config["leverage_ticker"])
    leverage = snapshots.get(leverage_ticker, {})
    if not leverage.get("available"):
        return {"state": "insufficient_data", "reasons": [f"{leverage_ticker}: no TDCC history"]}

    minority_change = float(leverage["minority_percent_change"])
    people_change_ratio = float(leverage["total_people_change_ratio"])
    caution = config["caution"]
    risk_off = config["risk_off"]
    reasons: list[str] = []

    risk_off_hit = (
        minority_change >= float(risk_off["leverage_minority_percent_change"])
        and people_change_ratio >= float(risk_off["leverage_total_people_change_ratio"])
    )
    caution_hit = (
        minority_change >= float(caution["leverage_minority_percent_change"])
        or people_change_ratio >= float(caution["leverage_total_people_change_ratio"])
    )
    if risk_off_hit:
        state = "risk_off"
        reasons.append(
            f"{leverage_ticker} leverage ETF crowding exceeded both risk-off thresholds"
        )
    elif caution_hit:
        state = "caution"
        reasons.append(
            f"{leverage_ticker} leverage ETF crowding exceeded at least one caution threshold"
        )
    else:
        state = "normal"
        reasons.append(f"{leverage_ticker} leverage ETF crowding remained below caution thresholds")
    return {"state": state, "reasons": reasons}


def build_shadow_report(
    config: dict[str, object],
    snapshots: dict[str, dict[str, object]],
    *,
    requested_as_of_date: str,
    cutoff_date: str,
) -> dict[str, object]:
    assessment = assess_shadow_signal(config, snapshots)
    return {
        "branch_name": config["branch_name"],
        "branch_status": config["status"],
        "production_release_unchanged": config["production_release_unchanged"],
        "advisory_only": True,
        "changes_production_target_shares": False,
        "requested_as_of_date": requested_as_of_date,
        "availability_cutoff_date": cutoff_date,
        "availability_lag_days": int(config["availability_lag_days"]),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "state": assessment["state"],
        "reasons": assessment["reasons"],
        "snapshots": snapshots,
        "config": config,
    }


def main() -> None:
    args = _parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    lag_days = int(config["availability_lag_days"])
    cutoff = date.fromisoformat(args.as_of_date) - timedelta(days=lag_days)
    snapshots = {
        str(ticker): _ticker_snapshot(
            _load_weekly_features(Path(args.db), str(ticker), str(cutoff)),
            int(config["lookback_weeks"]),
        )
        for ticker in config["tickers"]
    }
    report = build_shadow_report(
        config,
        snapshots,
        requested_as_of_date=args.as_of_date,
        cutoff_date=str(cutoff),
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"group_a_shareholding_shadow_{stamp}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(output_path, output_dir / LATEST_JSON.name)
    with (output_dir / HISTORY_JSONL.name).open("a", encoding="utf-8") as history:
        history.write(json.dumps(report, ensure_ascii=False) + "\n")
    print(f"State: {report['state']}")
    print(f"JSON: {output_path}")
    print(f"Latest: {output_dir / LATEST_JSON.name}")
    print(f"History: {output_dir / HISTORY_JSONL.name}")


if __name__ == "__main__":
    main()
