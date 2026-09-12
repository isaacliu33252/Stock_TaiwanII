#!/usr/bin/env python3
"""Fable 00631L round-2 direction #2 (2026-08-22): add leverage-decay/tracking-drag
features to the NCF 00631L classifier itself.

Fable's observation: every existing feature in ncf_00631l.py's FEATURES is generic
technical-indicator math on 00631L's own price; EXT_FEATURES only relates 00631L to
0050 via same-day return/Bollinger-band features (eti0050_ret, eti0050_bb_*) -- there
is no feature capturing the realized (00631L return) vs (2x realized 0050 return)
tracking gap directly, even though 00631L's entire character as a 2x daily-reset
leveraged ETF is defined by that gap. This is a different target from Fable round-1
direction #5, which added volatility features to PPO's FEATURE_COLUMNS, not to this
classifier.

Reuses (does not reimplement) group_a_plus/integrations/leveraged_etf_timing_anomaly.py
(arXiv:2604.27287 diagnostic module, already validated/tested) via
rolling_timing_anomaly() to compute realized effective-leverage / covariance / drag
statistics over a trailing window, added as new EXT_FEATURES columns:
  - letf_effective_leverage_20d   (average_effective_leverage)
  - letf_effective_leverage_std_20d (effective_leverage_std)
  - letf_covariance_ratio_20d     (covariance_ratio_underlying_return, annualized)
  - letf_volatility_drag_20d      (volatility_drag_estimate)
Window=20 chosen to match NCF's own h20 prediction horizon (decided before running
any comparison, not tuned to it).

ncf_00631l.py is never edited on disk -- monkey-patches EXT_FEATURES (in place,
same pattern already used at ncf_00631l.py:2430 for global features) and
load_external_df (wrapped, calling the original then adding the new columns) in
this process only, then calls ncf_00631l.main() twice (baseline unpatched, then
candidate patched) with different --output paths. Both use --no-tabnet (matches
daily production panel generation) for speed and to avoid re-litigating the
already-known TabNet-inclusion mismatch (round-2 direction #1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_MISC = PROJECT_ROOT / "scripts" / "misc"
if str(SCRIPTS_MISC) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_MISC))

import ncf_00631l as ncf_mod  # noqa: E402
from group_a_plus.integrations.leveraged_etf_timing_anomaly import (  # noqa: E402
    TimingAnomalyThresholds,
    rolling_timing_anomaly,
)

NEW_FEATURES = [
    "letf_effective_leverage_20d",
    "letf_effective_leverage_std_20d",
    "letf_covariance_ratio_20d",
    "letf_volatility_drag_20d",
]
LEVERAGE_DRAG_WINDOW = 20


def _load_close_series(db_path: Path, ticker: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float)


_ORIGINAL_LOAD_EXTERNAL_DF = ncf_mod.load_external_df


def _load_external_df_with_leverage_drag(main_df: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    ext = _ORIGINAL_LOAD_EXTERNAL_DF(main_df, db_path)
    try:
        letf_close = _load_close_series(Path(db_path), "00631L.TW")
        etf0050_close = _load_close_series(Path(db_path), "0050.TW")
        rolling = rolling_timing_anomaly(
            letf_close,
            etf0050_close,
            target_leverage=2.0,
            window=LEVERAGE_DRAG_WINDOW,
            thresholds=TimingAnomalyThresholds(),
        )
        rolling = rolling.reindex(main_df.index, method="ffill")
        ext["letf_effective_leverage_20d"] = rolling["average_effective_leverage"].values
        ext["letf_effective_leverage_std_20d"] = rolling["effective_leverage_std"].values
        ext["letf_covariance_ratio_20d"] = rolling["covariance_ratio_underlying_return"].values
        ext["letf_volatility_drag_20d"] = rolling["volatility_drag_estimate"].values
    except Exception as exc:  # noqa: BLE001
        print(f"  [leverage-drag-feature] WARNING: failed to compute, columns will be NaN: {exc}")
        for col in NEW_FEATURES:
            ext[col] = np.nan
    return ext


def run_variant(*, label: str, patched: bool, extra_args: list[str]) -> None:
    if patched:
        ncf_mod.EXT_FEATURES[:] = ncf_mod.EXT_FEATURES + [f for f in NEW_FEATURES if f not in ncf_mod.EXT_FEATURES]
        ncf_mod.load_external_df = _load_external_df_with_leverage_drag
    else:
        ncf_mod.EXT_FEATURES[:] = [f for f in ncf_mod.EXT_FEATURES if f not in NEW_FEATURES]
        ncf_mod.load_external_df = _ORIGINAL_LOAD_EXTERNAL_DF

    argv = ["ncf_00631l.py", "--no-tabnet"] + extra_args
    print(f"\n=== running variant: {label} (patched={patched}) ===")
    old_argv = sys.argv
    sys.argv = argv
    try:
        ncf_mod.main()
    finally:
        sys.argv = old_argv


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--val-start", default="2025-01-02")
    parser.add_argument("--val-end", default="latest")
    parser.add_argument("--walk-forward", action="store_true")
    args = parser.parse_args()

    common = ["--val-start", args.val_start, "--val-end", args.val_end]
    if args.walk_forward:
        common.append("--walk-forward")

    run_variant(
        label="baseline",
        patched=False,
        extra_args=common + ["--output", "results/ncf_00631l_leverage_drag_baseline_20260822.json"],
    )
    run_variant(
        label="leverage_drag_features",
        patched=True,
        extra_args=common + ["--output", "results/ncf_00631l_leverage_drag_candidate_20260822.json"],
    )
    print("\nDone. Compare results/ncf_00631l_leverage_drag_baseline_20260822.json vs "
          "results/ncf_00631l_leverage_drag_candidate_20260822.json")


if __name__ == "__main__":
    main()
