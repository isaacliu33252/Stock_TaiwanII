#!/usr/bin/env python3
"""Build GroupA+ adaptive quantile risk gate shadow report.

This is a diagnostic-only artifact inspired by arXiv:2605.24345. It does not
change live target weights, target shares, or execution regimes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.adaptive_quantile_risk_gate import (  # noqa: E402
    append_adaptive_quantile_risk_gate_shadow_log,
    classify_adaptive_quantile_risk_gate,
)


DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_OPS_HEALTH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"
DEFAULT_STRATEGY_TRUST = PROJECT_ROOT / "report/group_a_plus/latest/strategy_trust.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/adaptive_quantile_risk_gate_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/adaptive_quantile_risk_gate/history"
DEFAULT_LOG = PROJECT_ROOT / "results/adaptive_quantile_risk_gate_shadow_log.jsonl"


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap_signal(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"adaptive_quantile_risk_gate_shadow_{stamp}.json"


def build_report(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL,
    ops_health_path: Path | None = DEFAULT_OPS_HEALTH,
    strategy_trust_path: Path | None = DEFAULT_STRATEGY_TRUST,
    yesterday_review_path: Path | None = None,
    regime_analog_count: int | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    live_envelope = _load_json(live_signal_path)
    if live_envelope is None:
        raise FileNotFoundError(f"missing live signal: {live_signal_path}")
    live_signal = _unwrap_signal(live_envelope)

    ops_health = _load_json(ops_health_path)
    strategy_trust = _load_json(strategy_trust_path)
    yesterday_review = _load_json(yesterday_review_path)

    result = classify_adaptive_quantile_risk_gate(
        live_signal,
        ops_health=ops_health,
        strategy_trust=strategy_trust,
        yesterday_review=yesterday_review,
        regime_analog_count=regime_analog_count,
    )
    report_as_of = as_of or str(live_signal.get("actual_data_date") or live_signal.get("signal_date") or "")
    result.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": report_as_of,
            "sources": {
                "live_signal": str(live_signal_path),
                "ops_health": str(ops_health_path) if ops_health_path else None,
                "strategy_trust": str(strategy_trust_path) if strategy_trust_path else None,
                "yesterday_review": str(yesterday_review_path) if yesterday_review_path else None,
            },
        }
    )
    return result


def write_report(
    report: dict[str, Any],
    *,
    output_path: Path = DEFAULT_OUTPUT,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
    log_path: Path | None = DEFAULT_LOG,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report.get("as_of")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if log_path is not None and report.get("as_of"):
        append_adaptive_quantile_risk_gate_shadow_log(log_path, report, date=str(report["as_of"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--ops-health", default=str(DEFAULT_OPS_HEALTH))
    parser.add_argument("--strategy-trust", default=str(DEFAULT_STRATEGY_TRUST))
    parser.add_argument("--yesterday-review", default=None)
    parser.add_argument("--regime-analog-count", type=int, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    report = build_report(
        live_signal_path=Path(args.live_signal),
        ops_health_path=Path(args.ops_health) if args.ops_health else None,
        strategy_trust_path=Path(args.strategy_trust) if args.strategy_trust else None,
        yesterday_review_path=Path(args.yesterday_review) if args.yesterday_review else None,
        regime_analog_count=args.regime_analog_count,
        as_of=args.as_of,
    )
    write_report(
        report,
        output_path=Path(args.output),
        history_dir=None if args.no_history else Path(args.history_dir),
        log_path=None if args.no_log else Path(args.log),
    )
    print(
        "as_of={as_of} posture={posture} quantile={quantile} uncertainty={uncertainty}".format(
            as_of=report.get("as_of"),
            posture=report.get("risk_posture"),
            quantile=report.get("quantile_level"),
            uncertainty=report.get("uncertainty_score"),
        )
    )
    print(f"Output: {args.output}")
    if not args.no_history:
        print(f"History: {_history_path(Path(args.history_dir), report.get('as_of'))}")


if __name__ == "__main__":
    main()
