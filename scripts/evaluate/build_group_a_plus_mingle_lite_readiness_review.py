#!/usr/bin/env python3
"""Build a MINGLE-lite readiness review for GroupA+.

Research-only adaptation of arXiv:2608.06618. It uses PCA factor exposures to
construct an exposure-similarity graph, then checks whether current GroupA+
target weights are concentrated in central assets. It does not change live
weights or execution guards.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.mingle_lite_diversification import build_mingle_lite_frame, summarize_target_diversification
from group_a_plus.integrations.triadic_stress_index import DEFAULT_TICKER_SOURCES


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/mingle_lite_readiness_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/mingle_lite_readiness_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/mingle_lite_readiness_review/history"
DEFAULT_TICKERS = (
    "0050.TW,00631L.TW,00632R.TW,00679B.TWO,^TWII,2330.TW,2317.TW,2454.TW,SOXX,QQQ,NVDA,TSM,^VIX,TWD=X,^TNX,GC=F"
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def _read_close(con: duckdb.DuckDBPyConnection, *, table: str, ticker: str, start: str, end: str, label: str) -> pd.Series:
    rows = con.execute(
        f"SELECT dt, close FROM {table} WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
        [ticker, start, end],
    ).fetchdf()
    if rows.empty:
        return pd.Series(dtype=float, name=label)
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")["close"].astype(float).rename(label)


def load_price_panel(*, db_path: Path, tickers: list[str], start: str, end: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        series = {}
        status = {}
        for label in tickers:
            source = DEFAULT_TICKER_SOURCES.get(label)
            if source is None:
                source = ("ohlcv", label)
            close = _read_close(con, table=source[0], ticker=source[1], start=start, end=end, label=label)
            series[label] = close
            valid = close.dropna()
            status[label] = {
                "source_table": source[0],
                "source_ticker": source[1],
                "rows": int(len(valid)),
                "first_date": str(valid.index.min().date()) if not valid.empty else None,
                "latest_date": str(valid.index.max().date()) if not valid.empty else None,
                "status": "available" if not valid.empty else "missing",
            }
    finally:
        con.close()
    panel = pd.concat(series.values(), axis=1).sort_index()
    return panel, status


def _target_weights(live_signal: dict[str, Any]) -> dict[str, float]:
    live = _payload_data(live_signal)
    weights = live.get("target_weights") or {}
    return {str(k): float(v) for k, v in weights.items()}


def build_review(
    *,
    db_path: Path,
    live_signal_path: Path,
    tickers: list[str],
    as_of: str,
    lookback_days: int,
    factor_count: int,
    decay: float,
) -> dict[str, Any]:
    live_signal = _load_json(live_signal_path)
    live = _payload_data(live_signal)
    target_weights = _target_weights(live_signal)
    end = as_of or str(live.get("actual_data_date") or live.get("requested_as_of_date") or date.today().isoformat())
    start = (pd.Timestamp(end) - pd.Timedelta(days=int(lookback_days))).date().isoformat()
    prices, source_status = load_price_panel(db_path=db_path, tickers=tickers, start=start, end=end)
    available = [ticker for ticker, item in source_status.items() if int(item["rows"]) >= 60]
    frame = build_mingle_lite_frame(prices[available], factor_count=factor_count, decay=decay)
    target_summary = summarize_target_diversification(frame, target_weights)
    condition_improvement_ratio = (
        frame.sample_condition_number / frame.factor_condition_number
        if frame.factor_condition_number and frame.factor_condition_number > 0
        else None
    )
    blocking_reasons = ["research_only_no_live_weight_change", "full_mingle_admm_not_implemented"]
    if len(available) < 8:
        blocking_reasons.append("insufficient_cross_asset_universe_for_exposure_graph")
    if target_summary["risky_weight_sum"] <= 0.0:
        blocking_reasons.append("missing_live_risky_target_weights")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_mingle_lite_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.06618",
        "paper_title": "Beyond Co-Movement: Locality by Exposures Enables a Joint Factor-Graph Framework for Portfolio Diversification",
        "research_only": True,
        "production_effect": "none",
        "method": "mingle_lite_pca_exposure_similarity_graph_not_full_admm",
        "dates": {"start": start, "end": end, "lookback_days": int(lookback_days)},
        "configuration": {"factor_count": int(factor_count), "decay": float(decay), "tickers": tickers},
        "source_status": source_status,
        "available_tickers": available,
        "representation": {
            "observations": frame.observations,
            "factor_count": frame.factor_count,
            "sample_condition_number": frame.sample_condition_number,
            "factor_condition_number": frame.factor_condition_number,
            "condition_improvement_ratio": condition_improvement_ratio,
            "peripheral_score": {str(k): float(v) for k, v in frame.peripheral_score.sort_values(ascending=False).items()},
        },
        "target_diversification": target_summary,
        "import_assessment": {
            "useful_concepts": [
                "exposure_similarity_graph_instead_of_correlation_graph",
                "factor_covariance_conditioning_diagnostic",
                "peripheral_asset_review_for_diversification",
            ],
            "not_imported": [
                "full_nonconvex_admm_joint_factor_graph_training",
                "automatic_contagion_cut_allocation",
                "automatic_weight_change",
            ],
            "fit_for_group_a_plus": "diagnostic_only",
        },
        "blocking_reasons": blocking_reasons,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {"live_signal": str(live_signal_path), "db": str(db_path)},
    }


def _markdown(payload: dict[str, Any]) -> str:
    rep = payload.get("representation") or {}
    div = payload.get("target_diversification") or {}
    return """# GroupA+ MINGLE-lite Readiness Review

- status: `research_only`
- paper: `2608.06618`
- method: `{method}`
- production_effect: `none`
- promotion_allowed: `{promotion}`

## Representation

- available_tickers: `{available}`
- observations: `{observations}`
- sample_condition_number: `{sample_cond:.2f}`
- factor_condition_number: `{factor_cond:.2f}`
- condition_improvement_ratio: `{ratio:.2f}`

## Current Target Diversification

- risky_weight_sum: `{risky:.4f}`
- exposure_similarity_concentration: `{concentration:.6f}`
- weighted_graph_degree: `{degree:.6f}`
- peripheral_alignment: `{peripheral:.6f}`

```json
{target_weights}
```

## Assessment

MINGLE's exposure-locality idea is useful for diagnostics, but this report
implements only a PCA exposure-graph approximation, not the paper's full ADMM
joint optimiser. Keep it shadow-only until multi-window performance evidence
exists on the GroupA+ asset universe.

## Blocking Reasons

```json
{blockers}
```
""".format(
        method=payload.get("method"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        available=len(payload.get("available_tickers") or []),
        observations=int(rep.get("observations") or 0),
        sample_cond=float(rep.get("sample_condition_number") or 0.0),
        factor_cond=float(rep.get("factor_condition_number") or 0.0),
        ratio=float(rep.get("condition_improvement_ratio") or 0.0),
        risky=float(div.get("risky_weight_sum") or 0.0),
        concentration=float(div.get("exposure_similarity_concentration") or 0.0),
        degree=float(div.get("weighted_graph_degree") or 0.0),
        peripheral=float(div.get("peripheral_alignment") or 0.0),
        target_weights=json.dumps(div.get("normalized_risky_weights") or {}, ensure_ascii=False, indent=2),
        blockers=json.dumps(payload.get("blocking_reasons") or [], ensure_ascii=False, indent=2),
    )


def write_report(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"mingle_lite_readiness_review_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--tickers", default=DEFAULT_TICKERS)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--factor-count", type=int, default=3)
    parser.add_argument("--decay", type=float, default=0.997)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_review(
        db_path=_resolve(args.db),
        live_signal_path=_resolve(args.live_signal),
        tickers=[item.strip() for item in args.tickers.split(",") if item.strip()],
        as_of=str(args.as_of).strip(),
        lookback_days=int(args.lookback_days),
        factor_count=int(args.factor_count),
        decay=float(args.decay),
    )
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"MINGLE-lite readiness review: {_resolve(args.output)}")
    print(json.dumps(payload["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
