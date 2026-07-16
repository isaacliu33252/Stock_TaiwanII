#!/usr/bin/env python3
"""Append today's signal_alignment shadow variant (with 3 new sources) to a log.

Research-only, pure logging step -- see
group_a_plus/integrations/signal_alignment_shadow_variant.py for why this
exists. Reads inputs that are already produced daily (live_signal.json embeds
trough_nowcast; compounding_regime and crash_risk_alert are separate daily
artifacts) and never changes the production
report/group_a_plus/latest/signal_alignment.json, target weights, or
execution guards.

Safe to run standalone, or add as a best-effort step in
scripts/run/run_ncf_daily_pipeline.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.signal_alignment import (
    DEFAULT_LIVE_SIGNAL_PATH,
    _unwrap_standard_json,
    append_signal_alignment_shadow_log,
)
from group_a_plus.integrations.signal_alignment_shadow_variant import build_signal_alignment_shadow_variant

DEFAULT_CRASH_RISK_ALERT_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "crash_risk_alert.json"
DEFAULT_LOG_PATH = PROJECT_ROOT / "results" / "signal_alignment_shadow_variant_log.jsonl"
DEFAULT_LATEST_PATH = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "signal_alignment_shadow_variant.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest_compounding_regime_path() -> Path | None:
    matches = sorted(
        (PROJECT_ROOT / "results").glob("00631l_leveraged_compounding_regime_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def main() -> None:
    live_signal = _unwrap_standard_json(_load_json(DEFAULT_LIVE_SIGNAL_PATH))
    compounding_path = _latest_compounding_regime_path()
    compounding_payload = _load_json(compounding_path) if compounding_path else {}
    compounding_latest = compounding_payload.get("latest") if isinstance(compounding_payload.get("latest"), dict) else {}
    crash_risk_alert = _unwrap_standard_json(_load_json(DEFAULT_CRASH_RISK_ALERT_PATH))

    result = build_signal_alignment_shadow_variant(
        live_signal,
        compounding_regime_latest=compounding_latest,
        crash_risk_alert=crash_risk_alert,
    )

    DEFAULT_LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_LATEST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_signal_alignment_shadow_log(DEFAULT_LOG_PATH, result)

    print(
        f"variant alignment={result.get('alignment')} dominant={result.get('dominant_direction')} "
        f"leverage_tier={ (result.get('leverage_suitability') or {}).get('tier') }"
    )
    print(f"Latest: {DEFAULT_LATEST_PATH}")
    print(f"Log: {DEFAULT_LOG_PATH}")


if __name__ == "__main__":
    main()
