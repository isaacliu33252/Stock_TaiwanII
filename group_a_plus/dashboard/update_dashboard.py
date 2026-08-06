"""One-command local dashboard refresh for GroupA+ operations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from group_a_plus.dashboard.static_dashboard import (
    DEFAULT_HOLDINGS,
    DEFAULT_OUTPUT,
    DEFAULT_REBALANCE,
    build_dashboard_from_files,
)
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.portfolio.rebalance_cli import DEFAULT_SIGNAL, build_report_from_files


DEFAULT_FRESHNESS_DIR = PROJECT_ROOT / "results"
DEFAULT_FUBON_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python") if (PROJECT_ROOT / ".venv" / "bin" / "python").exists() else "python3"


def _load_signal(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"signal JSON must be an object: {path}")


def _compact_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) >= 10:
        return text[:10].replace("-", "")
    return None


def infer_price_freshness_path(signal_path: Path, freshness_dir: Path = DEFAULT_FRESHNESS_DIR) -> Path:
    signal = _load_signal(signal_path)
    compact = _compact_date(signal.get("actual_data_date") or signal.get("requested_as_of_date") or signal.get("signal_asof"))
    if not compact:
        raise ValueError("could not infer signal date for ohlcv freshness report")
    return freshness_dir / f"ohlcv_freshness_{compact}.json"


def refresh_fubon_snapshot(
    *,
    holdings_path: Path = DEFAULT_HOLDINGS,
    account_index: int = 0,
    fubon_python: str = DEFAULT_FUBON_PYTHON,
    local_config_dir: Path | None = None,
    interactive: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        fubon_python,
        "-m",
        "group_a_plus.portfolio.fubon_snapshot",
        "--output",
        str(holdings_path),
        "--account-index",
        str(account_index),
    ]
    if local_config_dir is not None:
        command.extend(["--local-config-dir", str(local_config_dir)])
    if interactive:
        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            timeout=90,
            check=False,
        )
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )


def update_dashboard(
    *,
    signal_path: Path = DEFAULT_SIGNAL,
    holdings_path: Path = DEFAULT_HOLDINGS,
    price_freshness_path: Path | None = None,
    rebalance_path: Path = DEFAULT_REBALANCE,
    dashboard_path: Path = DEFAULT_OUTPUT,
    refresh_fubon: bool = False,
    account_index: int = 0,
    fubon_python: str = DEFAULT_FUBON_PYTHON,
    local_config_dir: Path | None = None,
    interactive_fubon: bool = False,
) -> dict[str, Any]:
    if refresh_fubon:
        completed = refresh_fubon_snapshot(
            holdings_path=holdings_path,
            account_index=account_index,
            fubon_python=fubon_python,
            local_config_dir=local_config_dir,
            interactive=interactive_fubon,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Fubon snapshot refresh failed with rc={completed.returncode}{suffix}")

    if not holdings_path.exists():
        raise FileNotFoundError(f"holdings snapshot not found: {holdings_path}")

    resolved_price_freshness = price_freshness_path or infer_price_freshness_path(signal_path)
    rebalance_result = build_report_from_files(
        signal_path=signal_path,
        holdings_path=holdings_path,
        latest_output=rebalance_path,
        dated_output=rebalance_path.parent / f"rebalance_plan_{_compact_date(_load_signal(signal_path).get('actual_data_date'))}.json",
        price_freshness_path=resolved_price_freshness,
    )
    dashboard_result = build_dashboard_from_files(
        signal_path=signal_path,
        rebalance_path=rebalance_path,
        holdings_path=holdings_path,
        output_path=dashboard_path,
    )
    return {
        "dashboard_path": str(dashboard_path),
        "holdings_path": str(holdings_path),
        "rebalance_path": str(rebalance_path),
        "price_freshness_path": str(resolved_price_freshness),
        "refresh_fubon": refresh_fubon,
        "rebalance_validation_approved": bool(rebalance_result["report"]["validation"]["approved"]),
        "manual_approval_required": bool(rebalance_result["report"]["manual_approval"]["required"]),
        "dashboard_loaded": dashboard_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=str(DEFAULT_SIGNAL))
    parser.add_argument("--holdings", default=str(DEFAULT_HOLDINGS))
    parser.add_argument("--price-freshness", default=None)
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--dashboard", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--refresh-fubon", action="store_true", help="Refresh read-only Fubon holdings before building")
    parser.add_argument("--account-index", type=int, default=0)
    parser.add_argument("--fubon-python", default=DEFAULT_FUBON_PYTHON)
    parser.add_argument("--local-config-dir", default=None, help="Local Fubon AES config dir, default C:\\fubon")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = update_dashboard(
            signal_path=Path(args.signal),
            holdings_path=Path(args.holdings),
            price_freshness_path=Path(args.price_freshness) if args.price_freshness else None,
            rebalance_path=Path(args.rebalance),
            dashboard_path=Path(args.dashboard),
            refresh_fubon=args.refresh_fubon,
            account_index=args.account_index,
            fubon_python=args.fubon_python,
            local_config_dir=Path(args.local_config_dir) if args.local_config_dir else None,
            interactive_fubon=bool(args.refresh_fubon and sys.stdin.isatty()),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Dashboard update error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"Dashboard: {result['dashboard_path']}")
    print(f"Rebalance: {result['rebalance_path']}")
    print(f"Validation approved: {result['rebalance_validation_approved']}")
    print(f"Manual approval required: {result['manual_approval_required']}")


if __name__ == "__main__":
    main()
