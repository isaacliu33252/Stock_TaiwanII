#!/usr/bin/env python3
"""Out-of-sample check: does strategy_trust_gate's TRUST/SHADOW_ONLY/ABSTAIN
label actually track NCF prediction reliability?

Research-only. Joins results/strategy_trust_shadow_log.jsonl (built daily by
the [strategy-trust-gate] pipeline step, see
group_a_plus/integrations/strategy_trust_gate.py) against
results/ncf_signal_archive.jsonl's realized-outcome join (same machinery as
evaluate_ncf_blend_live_auc_archive.py) and reports each trust_level
bucket's hit rate per horizon, using the production blend_live_auc=0.35
candidate.

This is the gate before strategy_trust_gate.py's output is allowed to
influence anything beyond a shadow log: if TRUST-day hit rate is not
meaningfully better than SHADOW_ONLY/ABSTAIN-day hit rate once enough
samples exist, the label is not doing its job and must not be wired into
target_weights/execution_regime. Do not change any weight logic based on a
result with n below --min-samples in any bucket.

As of 2026-08-02 (the day strategy_trust_gate.py was added) the shadow log
has ~0 rows, so the first several runs of this script will almost certainly
report insufficient_data for every horizon/trust_level combination. This is
expected -- the pipeline step needs to run for many trading days before this
evaluation means anything, same as the blend_live_auc archive needed ~30
samples per horizon before evaluate_ncf_blend_live_auc_archive.py produced a
non-trivial result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.ncf_signal_archive import HORIZONS_DAYS, _realized_direction, load_archive

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_ARCHIVE_PATH = PROJECT_ROOT / "results" / "ncf_signal_archive.jsonl"
DEFAULT_TRUST_LOG_PATH = PROJECT_ROOT / "results" / "strategy_trust_shadow_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "strategy_trust_gate_evaluation_latest.json"

PRODUCTION_BLEND = "0.35"  # matches ncf.py's blend_live_auc default
TRUST_LEVELS = ("TRUST", "SHADOW_ONLY", "ABSTAIN")


def _load_close(db_path: Path, ticker: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float)


def _load_trust_by_date(trust_log_path: Path) -> dict[str, str]:
    trust_by_date: dict[str, str] = {}
    if not trust_log_path.exists():
        return trust_by_date
    for line in trust_log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        date = row.get("date")
        trust_level = row.get("trust_level")
        if date and trust_level in TRUST_LEVELS:
            trust_by_date[str(date)] = str(trust_level)
    return trust_by_date


def evaluate(
    archive: pd.DataFrame,
    close_by_ticker: dict[str, pd.Series],
    trust_by_date: dict[str, str],
    *,
    horizons: tuple[int, ...] = HORIZONS_DAYS,
    min_samples: int = 20,
) -> dict[str, Any]:
    if archive.empty:
        return {"status": "empty_archive"}
    if not trust_by_date:
        return {"status": "empty_trust_log"}

    results: dict[str, Any] = {}
    for horizon in horizons:
        records = []
        for _, row in archive.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            trust_level = trust_by_date.get(date_str)
            if trust_level is None:
                continue
            ticker = row["ticker"]
            close = close_by_ticker.get(ticker)
            if close is None:
                continue
            col = f"blend_{PRODUCTION_BLEND}_probability_up"
            prob = row.get(col)
            if prob is None or pd.isna(prob):
                continue
            realized = _realized_direction(close, row["date"], horizon)
            if realized is None:
                continue
            records.append(
                {
                    "trust_level": trust_level,
                    "predicted_up": 1 if float(prob) > 0.5 else 0,
                    "realized_up": realized,
                }
            )

        n_total = len(records)
        if n_total == 0:
            results[str(horizon)] = {"status": "no_matching_dates", "n": 0}
            continue

        frame = pd.DataFrame(records)
        bucket_results = {}
        for trust_level in TRUST_LEVELS:
            subset = frame[frame["trust_level"] == trust_level]
            n = len(subset)
            if n < min_samples:
                bucket_results[trust_level] = {
                    "status": "insufficient_data",
                    "n": n,
                    "min_samples_required": min_samples,
                }
                continue
            hit_rate = float((subset["predicted_up"] == subset["realized_up"]).mean())
            bucket_results[trust_level] = {"status": "ok", "n": n, "hit_rate": hit_rate}
        results[str(horizon)] = {"status": "ok", "n_total": n_total, "by_trust_level": bucket_results}
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE_PATH))
    parser.add_argument("--trust-log", default=str(DEFAULT_TRUST_LOG_PATH))
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    archive = load_archive(Path(args.archive))
    trust_by_date = _load_trust_by_date(Path(args.trust_log))

    if archive.empty:
        print(f"Archive empty or missing: {args.archive}")
        return
    if not trust_by_date:
        print(f"Trust shadow log empty or missing: {args.trust_log}")
        print("This is expected until the [strategy-trust-gate] pipeline step has run for a while.")
        return

    tickers = sorted(archive["ticker"].unique())
    close_by_ticker = {ticker: _load_close(DB_PATH, ticker) for ticker in tickers}

    result = evaluate(archive, close_by_ticker, trust_by_date, min_samples=args.min_samples)

    print(f"Archive: {len(archive)} rows across {len(tickers)} ticker(s): {tickers}")
    print(f"Trust shadow log: {len(trust_by_date)} dates")
    for horizon, res in result.items():
        if res.get("status") in ("no_matching_dates", "empty_archive", "empty_trust_log"):
            print(f"h={horizon}: {res['status']}")
            continue
        print(f"h={horizon}: n_total={res['n_total']}")
        for trust_level, stats in res["by_trust_level"].items():
            if stats["status"] == "insufficient_data":
                print(f"  {trust_level}: insufficient_data (n={stats['n']}, need >={stats['min_samples_required']})")
            else:
                print(f"  {trust_level}: n={stats['n']} hit_rate={stats['hit_rate']:.3f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {"archive_rows": len(archive), "tickers": tickers, "trust_log_dates": len(trust_by_date), "results": result},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
