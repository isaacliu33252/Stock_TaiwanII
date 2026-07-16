"""Daily NCF signal archive: research infrastructure, not a production signal.

`ncf_dynamic_horizon_signal` (see `ncf.py`) blends a stable multi-year OOS AUC
prior with the current run's live validation AUC via `blend_live_auc=0.35`.
That default was a judgement call, not something backtested against realized
outcomes -- and there is currently no archive of daily NCF signal snapshots
long enough to check it (as of 2026-07-11, the only dated snapshots on disk
cover a handful of days in late June 2026).

This module builds that archive going forward: each day, record the raw
horizon probabilities/AUCs plus what `ncf_dynamic_horizon_signal` would have
produced under several `blend_live_auc` candidates (including the current
default), so that once enough forward-realized outcomes exist, a script can
join the archive against realized returns and compare candidates with the
same QLIKE/Diebold-Mariano-style rigor already used for volatility forecasts.

Writing to the archive changes nothing about live trading decisions -- it is
a pure logging step, safe to run standalone or best-effort inside the daily
pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from group_a_plus.integrations.ncf import DEFAULT_HORIZON_AUC_PRIORS, ncf_dynamic_horizon_signal

ARCHIVE_SCHEMA_VERSION = 1
BLEND_VARIANTS: tuple[float, ...] = (0.0, 0.35, 0.65, 1.0)  # 0.35 is ncf.py's current production default
HORIZONS_DAYS: tuple[int, ...] = (1, 5, 20)


def build_archive_row(
    ncf_signal: dict[str, Any],
    *,
    blend_variants: tuple[float, ...] = BLEND_VARIANTS,
    auc_priors: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any] | None:
    """One archive row for one ticker's daily NCF signal snapshot.

    Returns None if the signal has no per-horizon data (nothing to compare).
    """
    horizon_prob_up = ncf_signal.get("horizon_prob_up") or {}
    if not horizon_prob_up:
        return None
    row: dict[str, Any] = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "ticker": str(ncf_signal.get("ticker", "")),
        "date": str(ncf_signal.get("date", "")),
        "horizon_prob_up": {str(k): float(v) for k, v in horizon_prob_up.items()},
        "horizon_val_auc": {str(k): float(v) for k, v in (ncf_signal.get("horizon_val_auc") or {}).items()},
    }
    for blend in blend_variants:
        dynamic = ncf_dynamic_horizon_signal(ncf_signal, auc_priors=auc_priors, blend_live_auc=blend)
        row[f"blend_{blend:.2f}_probability_up"] = dynamic["probability_up"]
    return row


def append_archive_rows(rows: list[dict[str, Any]], archive_path: Path) -> int:
    """Append new (ticker, date) rows to a JSONL archive, skipping duplicates.

    Returns the number of rows actually appended.
    """
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys: set[tuple[str, str]] = set()
    if archive_path.exists():
        with archive_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                existing = json.loads(line)
                existing_keys.add((existing.get("ticker"), existing.get("date")))

    new_rows = []
    seen_in_batch: set[tuple[str, str]] = set()
    for row in rows:
        if row is None:
            continue
        key = (row["ticker"], row["date"])
        if key in existing_keys or key in seen_in_batch:
            continue
        seen_in_batch.add(key)
        new_rows.append(row)
    if not new_rows:
        return 0
    with archive_path.open("a", encoding="utf-8") as fh:
        for row in new_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(new_rows)


def load_archive(archive_path: Path) -> pd.DataFrame:
    if not archive_path.exists():
        return pd.DataFrame()
    rows = []
    with archive_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def _realized_direction(close: pd.Series, as_of: pd.Timestamp, horizon: int) -> int | None:
    """UP(1)/DOWN(0) realized direction `horizon` trading days after `as_of`, or None if not yet observable."""
    close = close.sort_index()
    if as_of not in close.index:
        # fall back to the last available date on/before as_of
        prior = close.index[close.index <= as_of]
        if len(prior) == 0:
            return None
        as_of = prior[-1]
    pos = close.index.get_loc(as_of)
    target_pos = pos + horizon
    if target_pos >= len(close):
        return None
    base = float(close.iloc[pos])
    future = float(close.iloc[target_pos])
    if base <= 0:
        return None
    return 1 if future > base else 0


def evaluate_archive_against_realized(
    archive: pd.DataFrame,
    close_by_ticker: dict[str, pd.Series],
    *,
    blend_variants: tuple[float, ...] = BLEND_VARIANTS,
    horizons: tuple[int, ...] = HORIZONS_DAYS,
    min_samples: int = 30,
) -> dict[str, Any]:
    """Join the archive against realized forward direction and score each blend candidate.

    Reports per-horizon hit rate for each blend variant, or `insufficient_data`
    with the current sample count when fewer than `min_samples` complete
    (already-realized) observations exist for that horizon.
    """
    if archive.empty:
        return {"status": "empty_archive"}

    results: dict[str, Any] = {}
    for horizon in horizons:
        records = []
        for _, row in archive.iterrows():
            ticker = row["ticker"]
            close = close_by_ticker.get(ticker)
            if close is None:
                continue
            horizon_key = str(horizon)
            prob = row.get("horizon_prob_up", {}).get(horizon_key)
            if prob is None:
                continue
            realized = _realized_direction(close, row["date"], horizon)
            if realized is None:
                continue
            record = {"ticker": ticker, "date": row["date"], "realized_up": realized}
            for blend in blend_variants:
                col = f"blend_{blend:.2f}_probability_up"
                if col in row and pd.notna(row[col]):
                    record[f"predicted_up_{blend:.2f}"] = 1 if float(row[col]) > 0.5 else 0
            records.append(record)

        n = len(records)
        if n < min_samples:
            results[str(horizon)] = {
                "status": "insufficient_data",
                "n": n,
                "min_samples_required": min_samples,
            }
            continue

        frame = pd.DataFrame(records)
        blend_results = {}
        for blend in blend_variants:
            col = f"predicted_up_{blend:.2f}"
            if col not in frame.columns:
                continue
            valid = frame[col].notna()
            if valid.sum() == 0:
                continue
            hit_rate = float((frame.loc[valid, col] == frame.loc[valid, "realized_up"]).mean())
            blend_results[f"{blend:.2f}"] = {"n": int(valid.sum()), "hit_rate": hit_rate}
        results[str(horizon)] = {"status": "ok", "n": n, "blend_hit_rates": blend_results}
    return results
