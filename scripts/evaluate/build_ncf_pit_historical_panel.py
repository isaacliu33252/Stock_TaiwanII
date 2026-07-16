#!/usr/bin/env python3
"""Build a point-in-time historical NCF signal panel.

The source NCF panels intentionally include realized forward labels for
calibration research.  This builder creates a signal-only surface for backtests
and live-style diagnostics by removing columns that are not known as of the
panel date.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_00631l_pit_historical_panel_20260713.csv"
DEFAULT_MANIFEST = PROJECT_ROOT / "results" / "ncf_00631l_pit_historical_panel_20260713.json"
DEFAULT_SOURCES = (
    "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv=oos_2017_2019",
    # Fable audit (2026-07-16, combination opportunities #9): the 2020-2024
    # gap left DFL's covid_2020 tuning window running on the panel_2025_2026
    # source (a family with a known全樣本 weight-drift history, fixed
    # 2026-07-07) instead of a genuine no-lookahead 2020 backfill. This is a
    # first pilot year, not the full 2020-2024 range Fable proposed --
    # 2021-2024 backfills would follow the same
    # scripts/misc/ncf_00631l.py --train-start ... --val-start ... --val-end
    # ... --full-panel command with the same train-start.
    "results/ncf_00631l_panel_backfill_2020_20260716.csv=oos_2020",
    "results/ncf_00631l_panel_latest_20260710.csv=panel_2025_2026",
)
LEAKAGE_PREFIXES = (
    "actual_",
    "forward_",
    "target_",
    "label_",
)
LEAKAGE_COLUMNS = {
    "y",
    "y_return",
    "y_direction",
}
REQUIRED_SIGNAL_COLUMNS = (
    "date",
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "ensemble_prob_up",
    "confidence",
    "prob_fwd_mdd_gt5_h20",
    "prob_fwd_gain_gt5_h20",
    "tail_reward_risk_score_h20",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_source_spec(spec: str) -> tuple[Path, str]:
    if "=" in spec:
        raw_path, name = spec.split("=", 1)
        name = name.strip()
    else:
        raw_path = spec
        name = Path(spec).stem
    path = _resolve(raw_path.strip())
    if not name:
        raise ValueError(f"Missing source name in spec: {spec}")
    return path, name


def _read_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        first_col = str(frame.columns[0]) if len(frame.columns) else ""
        if first_col.startswith("Unnamed"):
            frame = frame.rename(columns={frame.columns[0]: "date"})
    if "date" not in frame.columns:
        raise ValueError(f"{path} is missing date column")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values("date")
    return frame


def _is_leakage_column(column: str) -> bool:
    lowered = column.lower()
    return lowered in LEAKAGE_COLUMNS or any(lowered.startswith(prefix) for prefix in LEAKAGE_PREFIXES)


def _build_source_frame(path: Path, source_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = _read_panel(path)
    dropped = [column for column in raw.columns if _is_leakage_column(str(column))]
    retained = [column for column in raw.columns if column not in dropped]
    frame = raw[retained].copy()
    missing_required = [column for column in REQUIRED_SIGNAL_COLUMNS if column not in frame.columns]
    if missing_required:
        raise ValueError(f"{path} missing required PIT signal columns: {missing_required}")

    frame["asof_date"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame["signal_date"] = frame["asof_date"]
    frame["available_after_close"] = True
    frame["next_trading_date_in_source"] = frame["date"].shift(-1).dt.strftime("%Y-%m-%d")
    frame["source_panel"] = source_name
    frame["source_panel_path"] = str(path)
    frame["source_panel_sha256"] = _sha256_file(path)
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")

    metadata = {
        "source_name": source_name,
        "source_path": str(path),
        "source_sha256": frame["source_panel_sha256"].iloc[0] if len(frame) else _sha256_file(path),
        "source_rows": int(len(raw)),
        "pit_rows": int(len(frame)),
        "date_start": str(frame["date"].min()) if len(frame) else None,
        "date_end": str(frame["date"].max()) if len(frame) else None,
        "dropped_leakage_columns": dropped,
        "retained_columns_before_metadata": retained,
    }
    return frame, metadata


def build_pit_panel(source_specs: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    sources: list[dict[str, Any]] = []
    for spec in source_specs:
        path, source_name = _parse_source_spec(spec)
        if not path.exists():
            raise FileNotFoundError(path)
        frame, metadata = _build_source_frame(path, source_name)
        frames.append(frame)
        sources.append(metadata)
    if not frames:
        raise ValueError("At least one source panel is required")

    panel = pd.concat(frames, ignore_index=True, sort=False)
    panel = panel.sort_values(["date", "source_panel"]).reset_index(drop=True)
    duplicate_dates = panel[panel.duplicated("date", keep=False)]["date"].drop_duplicates().tolist()
    if duplicate_dates:
        raise ValueError(f"Overlapping source panels are not allowed; duplicate dates: {duplicate_dates[:10]}")

    leakage_retained = [column for column in panel.columns if _is_leakage_column(str(column))]
    if leakage_retained:
        raise AssertionError(f"PIT panel retained leakage columns: {leakage_retained}")

    ordered = [
        "date",
        "asof_date",
        "signal_date",
        "available_after_close",
        "next_trading_date_in_source",
        "source_panel",
        "source_panel_path",
        "source_panel_sha256",
    ]
    ordered += [column for column in panel.columns if column not in ordered]
    panel = panel[ordered]
    manifest = {
        "report_type": "ncf_pit_historical_panel",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "point_in_time_definition": (
            "Each row contains only NCF model outputs and metadata available as of that "
            "row's signal_date after market close. Realized forward labels and forward "
            "returns/drawdowns are removed."
        ),
        "execution_timing_note": (
            "Signals are available after the source close; same-day close execution is "
            "research-only unless an explicit delay model is applied. "
            "next_trading_date_in_source gives the next source-row trading date for t+1 studies."
        ),
        "row_count": int(len(panel)),
        "date_start": str(panel["date"].min()) if len(panel) else None,
        "date_end": str(panel["date"].max()) if len(panel) else None,
        "source_count": len(sources),
        "sources": sources,
        "columns": [str(column) for column in panel.columns],
        "leakage_policy": {
            "dropped_prefixes": list(LEAKAGE_PREFIXES),
            "dropped_exact_columns": sorted(LEAKAGE_COLUMNS),
            "retained_prediction_columns_with_forward_names": [
                "prob_fwd_mdd_gt5_h20",
                "prob_fwd_gain_gt5_h20",
                "tail_reward_risk_score_h20",
            ],
        },
    }
    return panel, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", default=list(DEFAULT_SOURCES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel, manifest = build_pit_panel(args.sources)
    output = _resolve(args.output)
    manifest_path = _resolve(args.manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False, encoding="utf-8-sig")
    manifest["output"] = str(output)
    manifest["output_sha256"] = _sha256_file(output)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output.resolve())
    print(manifest_path.resolve())
    print(f"rows={len(panel)} date_start={manifest['date_start']} date_end={manifest['date_end']}")


if __name__ == "__main__":
    main()
