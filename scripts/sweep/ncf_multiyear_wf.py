#!/usr/bin/env python3
"""Multi-year purged walk-forward evaluation for NCF 00631L and 00632R.

Runs one OOS fold per year (2022–2026):
  train = all data before val_year
  val   = val_year only (Jan–Dec)

Reports per-year, per-horizon AUC so we can confirm that v6 interaction
features are stable across market regimes, not just fitting to 2025-2026.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/sweep/ncf_multiyear_wf.py
    PYTHONPATH=. .venv/bin/python scripts/sweep/ncf_multiyear_wf.py --ticker 00631L --years 2023 2024 2025
    PYTHONPATH=. .venv/bin/python scripts/sweep/ncf_multiyear_wf.py --no-external-features
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = ROOT / "results"

TICKER_SCRIPTS = {
    "00631L": ROOT / "scripts" / "misc" / "ncf_00631l.py",
    "00632R": ROOT / "ncf_00632r.py",
}

FOLDS = [
    {"val_year": 2022, "train_start": "2015-01-01", "val_start": "2022-01-01", "val_end": "2022-12-31"},
    {"val_year": 2023, "train_start": "2015-01-01", "val_start": "2023-01-01", "val_end": "2023-12-31"},
    {"val_year": 2024, "train_start": "2015-01-01", "val_start": "2024-01-01", "val_end": "2024-12-31"},
    {"val_year": 2025, "train_start": "2015-01-01", "val_start": "2025-01-01", "val_end": "2025-12-31"},
    {"val_year": 2026, "train_start": "2015-01-01", "val_start": "2026-01-01", "val_end": "latest"},
]

HORIZONS = [1, 5, 20]


def _run_fold(
    script: Path,
    fold: dict,
    no_external: bool,
    python: str,
) -> dict | None:
    """Run one NCF training fold and return parsed JSON output, or None on failure."""
    tmp_output = RESULTS_DIR / f"_ncf_wf_tmp_{fold['val_year']}_{script.stem}.json"
    cmd = [
        python, str(script),
        "--train-start", fold["train_start"],
        "--val-start", fold["val_start"],
        "--val-end", fold["val_end"],
        "--output", str(tmp_output),
    ]
    if no_external:
        cmd.append("--no-external-features")

    print(f"  Running fold {fold['val_year']}: {' '.join(cmd[-6:])}", flush=True)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1200,
        )
        if result.returncode != 0:
            print(f"  ✗ fold {fold['val_year']} failed (exit {result.returncode})")
            print(result.stderr[-800:] if result.stderr else "")
            return None

        if not tmp_output.exists():
            print(f"  ✗ fold {fold['val_year']} produced no output file")
            return None

        data = json.loads(tmp_output.read_text(encoding="utf-8"))
        tmp_output.unlink(missing_ok=True)
        return data

    except subprocess.TimeoutExpired:
        print(f"  ✗ fold {fold['val_year']} timed out (>20 min)")
        return None
    except Exception as exc:
        print(f"  ✗ fold {fold['val_year']} error: {exc}")
        return None


def _extract_auc(data: dict) -> dict[int, float]:
    """Extract ensemble AUC per horizon from NCF JSON output.

    Supports both old (regime_classification) and current (classification.val_auc) structure.
    """
    aucs: dict[int, float] = {}
    horizons_data = data.get("horizons", {})
    for h in HORIZONS:
        h_key = str(h)
        if h_key not in horizons_data:
            continue
        hd = horizons_data[h_key]

        # Current structure: horizons[h].classification.val_auc
        clf = hd.get("classification") or {}
        ens_all = None
        ens_bull = None
        ens_bear = None

        if isinstance(clf, dict):
            ens_all = clf.get("val_auc") or clf.get("ensemble", {}).get("auc")
            # Bull/bear split inside classification (if present)
            bull = clf.get("bull") or {}
            bear = clf.get("bear") or {}
            ens_bull = bull.get("ensemble", {}).get("auc") or bull.get("val_auc")
            ens_bear = bear.get("ensemble", {}).get("auc") or bear.get("val_auc")

        # Older structure: horizons[h].regime_classification.bull/bear
        regime_clf = hd.get("regime_classification") or {}
        if regime_clf:
            bull = regime_clf.get("bull") or {}
            bear = regime_clf.get("bear") or {}
            ens_bull = ens_bull or bull.get("ensemble", {}).get("auc")
            ens_bear = ens_bear or bear.get("ensemble", {}).get("auc")

        aucs[h] = {
            "bull": ens_bull,
            "bear": ens_bear,
            "all": ens_all,
        }
    return aucs


def _print_summary(ticker: str, fold_results: list[dict]) -> None:
    """Print per-year AUC table."""
    print(f"\n{'='*72}")
    print(f"  {ticker} — Multi-year OOS AUC Summary")
    print(f"{'='*72}")
    header = f"  {'Year':>6} | {'H1 All':>8} {'H1 Bull':>8} {'H1 Bear':>8} |"
    header += f" {'H5 All':>8} {'H5 Bull':>8} {'H5 Bear':>8} |"
    header += f" {'H20 All':>9} {'H20 Bull':>9} {'H20 Bear':>9}"
    print(header)
    print(f"  {'-'*70}")

    for row in fold_results:
        year = row["val_year"]
        aucs = row["aucs"]

        def _fmt(v):
            return f"{v:.4f}" if v is not None else "  n/a  "

        h1 = aucs.get(1, {})
        h5 = aucs.get(5, {})
        h20 = aucs.get(20, {})
        line = f"  {year:>6} |"
        line += f" {_fmt(h1.get('all')):>8} {_fmt(h1.get('bull')):>8} {_fmt(h1.get('bear')):>8} |"
        line += f" {_fmt(h5.get('all')):>8} {_fmt(h5.get('bull')):>8} {_fmt(h5.get('bear')):>8} |"
        line += f" {_fmt(h20.get('all')):>9} {_fmt(h20.get('bull')):>9} {_fmt(h20.get('bear')):>9}"
        print(line)

    print(f"\n  Note: AUC > 0.55 = useful, AUC < 0.52 = near-random for that year/regime.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", choices=["00631L", "00632R", "both"], default="both")
    parser.add_argument("--years", type=int, nargs="+",
                        default=[f["val_year"] for f in FOLDS],
                        help="Which val years to run (default: all 2022-2026)")
    parser.add_argument("--no-external-features", action="store_true")
    parser.add_argument("--output", default=None,
                        help="Save summary JSON to this path")
    parser.add_argument("--python", default=str(ROOT / ".venv" / "bin" / "python"),
                        help="Python interpreter to use")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)

    tickers = ["00631L", "00632R"] if args.ticker == "both" else [args.ticker]
    active_folds = [f for f in FOLDS if f["val_year"] in args.years]

    all_summary: dict[str, list] = {}

    for ticker in tickers:
        script = TICKER_SCRIPTS[ticker]
        print(f"\n{'#'*72}")
        print(f"  Ticker: {ticker}  ({len(active_folds)} folds)")
        print(f"{'#'*72}")

        fold_results = []
        for fold in active_folds:
            print(f"\n--- Fold {fold['val_year']} ---", flush=True)
            data = _run_fold(script, fold, args.no_external_features, args.python)
            if data is None:
                fold_results.append({"val_year": fold["val_year"], "aucs": {}, "error": True})
                continue
            aucs = _extract_auc(data)
            fold_results.append({"val_year": fold["val_year"], "aucs": aucs, "error": False})

        _print_summary(ticker, fold_results)
        all_summary[ticker] = fold_results

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps({
                "generated_at": datetime.now().isoformat(),
                "folds": [f["val_year"] for f in active_folds],
                "tickers": tickers,
                "results": all_summary,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSummary saved to {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
