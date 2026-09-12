#!/usr/bin/env python3
"""Build a research-only AEGIS-lite advisory for GroupA+.

This intentionally does not implement the paper's minimax-correlation basket
selection: GroupA+'s tradable universe is too small and too collinear for that
mechanism.  The useful transferable pieces are kept as diagnostics only:

* VAM (return / realised volatility) support for adding 00631L exposure.
* A 3-month Sortino SLSQP reference allocation constrained near active weights.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/aegis_lite_advisory.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/aegis_lite_advisory.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/aegis_lite_advisory/history"
TARGET_ASSETS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "cash")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap_signal(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        if not payload:
            raise ValueError("signal JSON list is empty")
        payload = payload[-1]
    if not isinstance(payload, dict):
        raise ValueError("signal JSON must be an object or non-empty list")
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _normalise_weights(weights: dict[str, Any]) -> dict[str, float]:
    out = {asset: 0.0 for asset in TARGET_ASSETS}
    for raw, value in weights.items():
        key = str(raw)
        if key in out:
            out[key] += float(value or 0.0)
    total = sum(max(v, 0.0) for v in out.values())
    if total <= 1e-12:
        raise ValueError("target weights sum to zero")
    return {asset: max(value, 0.0) / total for asset, value in out.items()}


def _load_base_weights(path: Path) -> tuple[dict[str, float], dict[str, Any]]:
    signal = _unwrap_signal(_load_json(path))
    raw = signal.get("target_weights")
    if not isinstance(raw, dict):
        raise ValueError(f"signal has no target_weights object: {path}")
    return _normalise_weights(raw), signal


def _load_prices(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise ValueError(f"no OHLCV rows found for {start} ~ {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    prices = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    missing = [ticker for ticker in tickers if ticker not in prices.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    return prices[tickers].ffill().dropna(how="any")


def _as_of_index(prices: pd.DataFrame, as_of: str | None) -> pd.Timestamp:
    if prices.empty:
        raise ValueError("prices are empty")
    if as_of is None or str(as_of).lower() in {"latest", "auto"}:
        return pd.Timestamp(prices.index[-1]).normalize()
    target = pd.Timestamp(as_of).normalize()
    candidates = prices.index[prices.index <= target]
    if len(candidates) == 0:
        raise ValueError(f"no price rows on or before {as_of}")
    return pd.Timestamp(candidates[-1]).normalize()


def calculate_vam(prices: pd.DataFrame, *, as_of: str | None, lookback_days: int) -> dict[str, dict[str, float]]:
    """Return VAM diagnostics using only rows up to as_of.

    Codex 2026-08-13: VAM is imported from AEGIS only as an advisory
    diagnostic, not as an active allocation rule.
    """
    as_of_dt = _as_of_index(prices, as_of)
    hist = prices.loc[:as_of_dt].tail(int(lookback_days) + 1)
    if len(hist) < max(21, int(lookback_days) // 2):
        raise ValueError(f"insufficient price history for VAM: rows={len(hist)}")
    returns = hist.pct_change().dropna()
    cumulative = hist.iloc[-1] / hist.iloc[0] - 1.0
    ann_vol = returns.std(ddof=1) * math.sqrt(252)
    out: dict[str, dict[str, float]] = {}
    for ticker in prices.columns:
        vol = float(ann_vol[ticker])
        ret = float(cumulative[ticker])
        out[ticker] = {
            "cumulative_return": ret,
            "annualized_volatility": vol,
            "vam": float(ret / vol) if vol > 1e-12 else 0.0,
        }
    return out


def build_vam_gate(
    vam: dict[str, dict[str, float]],
    *,
    max_00631l_to_0050_vol_ratio: float,
) -> dict[str, Any]:
    vam_0050 = float(vam.get("0050.TW", {}).get("vam", 0.0))
    vam_631 = float(vam.get("00631L.TW", {}).get("vam", 0.0))
    vol_0050 = float(vam.get("0050.TW", {}).get("annualized_volatility", 0.0))
    vol_631 = float(vam.get("00631L.TW", {}).get("annualized_volatility", 0.0))
    vol_ratio = vol_631 / vol_0050 if vol_0050 > 1e-12 else float("inf")
    reasons: list[str] = []
    if vam_631 < vam_0050:
        reasons.append("00631L_vam_below_0050")
    if vam_631 <= 0.0:
        reasons.append("00631L_vam_non_positive")
    if vol_ratio > float(max_00631l_to_0050_vol_ratio):
        reasons.append("00631L_realized_vol_ratio_too_high")
    return {
        "status": "supports_00631l_add" if not reasons else "does_not_support_00631l_add",
        "allow_00631l_add": not reasons,
        "reasons": reasons,
        "vam_0050": vam_0050,
        "vam_00631l": vam_631,
        "vol_ratio_00631l_to_0050": float(vol_ratio),
        "max_00631l_to_0050_vol_ratio": float(max_00631l_to_0050_vol_ratio),
    }


def _sortino_score(asset_returns: pd.DataFrame, weights: np.ndarray) -> float:
    portfolio = asset_returns.to_numpy(dtype=float) @ weights
    mean_return = float(np.mean(portfolio) * 252)
    downside = np.minimum(portfolio, 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))) * math.sqrt(252))
    if downside_deviation <= 1e-12:
        return 0.0 if mean_return <= 0.0 else 100.0
    return mean_return / downside_deviation


def sortino_reference_weights(
    prices: pd.DataFrame,
    base_weights: dict[str, float],
    *,
    as_of: str | None,
    lookback_days: int,
    max_abs_deviation: float,
    max_single_asset_weight: float,
    turnover_penalty: float,
) -> dict[str, Any]:
    """Compute a constrained 3-month Sortino reference allocation.

    This is intentionally constrained near active weights so it cannot become
    a hidden replacement strategy in research reports.
    """
    as_of_dt = _as_of_index(prices, as_of)
    hist = prices.loc[:as_of_dt].tail(int(lookback_days) + 1)
    if len(hist) < max(21, int(lookback_days) // 2):
        raise ValueError(f"insufficient price history for Sortino optimizer: rows={len(hist)}")
    returns = hist.pct_change().dropna()
    returns = returns.reindex(columns=[asset for asset in TARGET_ASSETS if asset != "cash"])
    returns["cash"] = 0.0
    assets = list(TARGET_ASSETS)
    x0 = np.array([float(base_weights.get(asset, 0.0)) for asset in assets], dtype=float)
    x0 = x0 / max(float(x0.sum()), 1e-12)
    lower = np.maximum(0.0, x0 - float(max_abs_deviation))
    upper = np.minimum(float(max_single_asset_weight), x0 + float(max_abs_deviation))
    if lower.sum() > 1.0 or upper.sum() < 1.0:
        lower = np.zeros_like(x0)
        upper = np.full_like(x0, float(max_single_asset_weight))
        upper[assets.index("cash")] = 1.0

    def objective(w: np.ndarray) -> float:
        penalty = float(turnover_penalty) * float(np.abs(w - x0).sum())
        return -_sortino_score(returns[assets], w) + penalty

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=list(zip(lower, upper)),
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}],
        options={"maxiter": 300, "ftol": 1e-10, "disp": False},
    )
    opt = np.asarray(result.x if result.success else x0, dtype=float)
    opt = np.clip(opt, 0.0, 1.0)
    opt = opt / max(float(opt.sum()), 1e-12)
    base_sortino = _sortino_score(returns[assets], x0)
    opt_sortino = _sortino_score(returns[assets], opt)
    return {
        "status": "available" if result.success else "fallback_to_active_weights",
        "success": bool(result.success),
        "message": str(result.message),
        "lookback_rows": int(len(returns)),
        "lookback_start": str(returns.index[0].date()),
        "lookback_end": str(returns.index[-1].date()),
        "base_sortino": float(base_sortino),
        "reference_sortino": float(opt_sortino),
        "sortino_delta": float(opt_sortino - base_sortino),
        "base_weights": {asset: float(x0[idx]) for idx, asset in enumerate(assets)},
        "reference_weights": {asset: float(opt[idx]) for idx, asset in enumerate(assets)},
        "weight_delta": {asset: float(opt[idx] - x0[idx]) for idx, asset in enumerate(assets)},
        "turnover_from_active": float(np.abs(opt - x0).sum()),
        "constraints": {
            "max_abs_deviation": float(max_abs_deviation),
            "max_single_asset_weight": float(max_single_asset_weight),
            "turnover_penalty": float(turnover_penalty),
        },
    }


def build_advisory(
    *,
    prices: pd.DataFrame,
    base_weights: dict[str, float],
    signal: dict[str, Any],
    signal_path: Path,
    as_of: str | None,
    vam_lookback_days: int,
    sortino_lookback_days: int,
    max_00631l_to_0050_vol_ratio: float,
    max_abs_deviation: float,
    max_single_asset_weight: float,
    turnover_penalty: float,
) -> dict[str, Any]:
    actual_as_of = _as_of_index(prices, as_of)
    vam = calculate_vam(prices, as_of=str(actual_as_of.date()), lookback_days=vam_lookback_days)
    vam_gate = build_vam_gate(vam, max_00631l_to_0050_vol_ratio=max_00631l_to_0050_vol_ratio)
    sortino = sortino_reference_weights(
        prices,
        base_weights,
        as_of=str(actual_as_of.date()),
        lookback_days=sortino_lookback_days,
        max_abs_deviation=max_abs_deviation,
        max_single_asset_weight=max_single_asset_weight,
        turnover_penalty=turnover_penalty,
    )
    advisory_reasons: list[str] = []
    if not vam_gate["allow_00631l_add"] and sortino["weight_delta"].get("00631L.TW", 0.0) > 0.01:
        advisory_reasons.append("sortino_reference_adds_00631l_but_vam_gate_disagrees")
    if not vam_gate["allow_00631l_add"]:
        advisory_reasons.append("vam_gate_does_not_support_new_00631l_adds")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_aegis_lite_advisory",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_active_weight_change",
        "source_paper": "2604.09060v2 AEGIS; VAM and Sortino ideas only; minimax correlation intentionally excluded",
        "codex_note": "Codex 2026-08-13: advisory only, does not modify golden1_0531 or latest strategy.",
        "inputs": {
            "signal_path": str(signal_path),
            "signal_strategy_id": signal.get("strategy_id"),
            "requested_as_of": as_of or "latest",
            "actual_as_of": str(actual_as_of.date()),
        },
        "active_weights": base_weights,
        "vam": {
            "lookback_days": int(vam_lookback_days),
            "by_ticker": vam,
            "gate": vam_gate,
        },
        "sortino_reference": sortino,
        "decision": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "creates_orders": False,
            "promotion_ready": False,
            "recommended_use": "daily_advisory_and_shadow_promotion_gate_only",
            "advisory_status": "review_00631l_adds" if advisory_reasons else "no_aegis_lite_objection",
            "advisory_reasons": advisory_reasons,
        },
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    gate = report["vam"]["gate"]
    sortino = report["sortino_reference"]
    lines = [
        "# GroupA+ AEGIS-lite Advisory",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Actual as-of: `{report['inputs']['actual_as_of']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['advisory_status']}`",
        "",
        "## VAM Gate",
        "",
        f"- Status: `{gate['status']}`",
        f"- VAM 0050: `{gate['vam_0050']:.6f}`",
        f"- VAM 00631L: `{gate['vam_00631l']:.6f}`",
        f"- Vol ratio 00631L/0050: `{gate['vol_ratio_00631l_to_0050']:.4f}`",
        f"- Reasons: `{', '.join(gate['reasons']) or 'none'}`",
        "",
        "## Sortino Reference",
        "",
        f"- Status: `{sortino['status']}`",
        f"- Base Sortino: `{sortino['base_sortino']:.6f}`",
        f"- Reference Sortino: `{sortino['reference_sortino']:.6f}`",
        f"- Turnover from active: `{sortino['turnover_from_active']:.6f}`",
        "",
        "## Reference Weights",
        "",
    ]
    for asset, weight in sortino["reference_weights"].items():
        lines.append(f"- `{asset}`: `{weight:.6f}`")
    lines.extend(
        [
            "",
            "Codex 2026-08-13: research-only output; no active strategy or golden1_0531 artifact is changed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: dict[str, Any], *, output_json: Path, output_md: Path, history_dir: Path | None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(report, output_md)
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        history_json = history_dir / f"aegis_lite_advisory_{stamp}.json"
        history_md = history_dir / f"aegis_lite_advisory_{stamp}.md"
        history_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_markdown(report, history_md)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--signal", default=str(DEFAULT_SIGNAL))
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-08-13")
    parser.add_argument("--vam-lookback-days", type=int, default=126)
    parser.add_argument("--sortino-lookback-days", type=int, default=63)
    parser.add_argument("--max-00631l-to-0050-vol-ratio", type=float, default=2.25)
    parser.add_argument("--max-abs-deviation", type=float, default=0.15)
    parser.add_argument("--max-single-asset-weight", type=float, default=0.85)
    parser.add_argument("--turnover-penalty", type=float, default=0.02)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signal_path = _resolve(args.signal)
    db_path = _resolve(args.db)
    base_weights, signal = _load_base_weights(signal_path)
    prices = _load_prices(db_path, [asset for asset in TARGET_ASSETS if asset != "cash"], args.start, args.end)
    report = build_advisory(
        prices=prices,
        base_weights=base_weights,
        signal=signal,
        signal_path=signal_path,
        as_of=args.as_of,
        vam_lookback_days=args.vam_lookback_days,
        sortino_lookback_days=args.sortino_lookback_days,
        max_00631l_to_0050_vol_ratio=args.max_00631l_to_0050_vol_ratio,
        max_abs_deviation=args.max_abs_deviation,
        max_single_asset_weight=args.max_single_asset_weight,
        turnover_penalty=args.turnover_penalty,
    )
    report["inputs"]["db"] = str(db_path)
    report["inputs"]["price_window"] = {"start": args.start, "end": args.end}
    write_outputs(
        report,
        output_json=_resolve(args.output_json),
        output_md=_resolve(args.output_md),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "advisory_status": report["decision"]["advisory_status"],
                "vam_gate": report["vam"]["gate"]["status"],
                "sortino_delta": report["sortino_reference"]["sortino_delta"],
                "output_json": str(_resolve(args.output_json)),
                "output_md": str(_resolve(args.output_md)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
