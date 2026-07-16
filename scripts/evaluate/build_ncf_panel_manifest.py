#!/usr/bin/env python3
"""Build reproducibility fingerprints for NCF prediction panels."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KEY_COLUMNS = (
    "prob_up_h1",
    "prob_up_h5",
    "prob_up_h20",
    "ensemble_prob_up",
    "h20_prob_up",
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        first_col = str(frame.columns[0]) if len(frame.columns) else ""
        if first_col.startswith("Unnamed"):
            frame = frame.rename(columns={frame.columns[0]: "date"})
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame


def _column_stats(frame: pd.DataFrame, columns: tuple[str, ...]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for column in columns:
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        stats[column] = {
            "non_null": int(numeric.notna().sum()),
            "missing": int(numeric.isna().sum()),
            "mean": float(numeric.mean()) if numeric.notna().any() else None,
            "std": float(numeric.std()) if numeric.notna().sum() > 1 else None,
            "min": float(numeric.min()) if numeric.notna().any() else None,
            "max": float(numeric.max()) if numeric.notna().any() else None,
        }
    return stats


def build_panel_manifest(panel_path: str | Path, *, key_columns: tuple[str, ...] = DEFAULT_KEY_COLUMNS) -> dict[str, Any]:
    path = _resolve(panel_path)
    frame = _read_panel(path)
    columns = [str(column) for column in frame.columns]
    schema_payload = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    csv_payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")

    date_values = frame["date"].dropna() if "date" in frame.columns else pd.Series(dtype=object)
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_size_bytes": int(path.stat().st_size),
        "row_count": int(len(frame)),
        "column_count": int(len(columns)),
        "date_start": str(date_values.min()) if not date_values.empty else None,
        "date_end": str(date_values.max()) if not date_values.empty else None,
        "columns": columns,
        "schema_hash": _sha256_bytes(schema_payload),
        "content_hash": _sha256_bytes(csv_payload),
        "missing_by_column": {str(column): int(frame[column].isna().sum()) for column in frame.columns},
        "key_column_stats": _column_stats(frame, key_columns),
    }


def build_manifest(panel_paths: list[str | Path], *, key_columns: tuple[str, ...] = DEFAULT_KEY_COLUMNS) -> dict[str, Any]:
    panels = [build_panel_manifest(path, key_columns=key_columns) for path in panel_paths]
    combined_payload = json.dumps(
        [(panel["path"], panel["schema_hash"], panel["content_hash"]) for panel in panels],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "report_type": "ncf_panel_manifest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "panel_count": len(panels),
        "combined_hash": _sha256_bytes(combined_payload),
        "panels": panels,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", nargs="+", required=True)
    parser.add_argument("--output", default="results/ncf_panel_manifest_latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_manifest(args.panels)
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NCF panel manifest: {output}")
    print(f"Panels: {report['panel_count']}")
    print(f"Combined hash: {report['combined_hash']}")


if __name__ == "__main__":
    main()
