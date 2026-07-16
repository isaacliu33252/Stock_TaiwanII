"""Read-only operational health report for GroupA+ daily automation.

Inspired by Ajenti's dashboard/plugin health patterns, but intentionally kept
as a JSON report only. This module must not start/stop services, mutate files,
or influence active allocation.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from group_a_plus.governance.latest import resolve_ncf_00631l_panel_path
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.utils.tsmc_0050_weight import (
    TSMC_0050_WEIGHT_ASSUMPTION,
    TSMC_0050_WEIGHT_ASSUMPTION_AS_OF,
    TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS,
    tsmc_0050_weight_assumption_is_stale,
)
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "report/group_a_plus/latest/ops_health.json"

REQUIRED_ARTIFACTS = {
    "strategy_manifest": "report/group_a_plus/latest/strategy.json",
    "live_signal": "report/group_a_plus/latest/live_signal.json",
    "execution_plan": "report/group_a_plus/latest/execution_plan.json",
    "strategy_env_health": "report/group_a_plus/latest/strategy_env_health.json",
}
# Fallback only -- 2026-07-07 Fable audit found this hardcoded to a
# week-stale filename while production had already moved on (strategy.json's
# active_strategy.runner_params.ncf_panel_631l_path). _resolve_ncf_panel_path
# below reads the live value; this constant only applies when strategy.json
# is missing or doesn't have that field yet.
FALLBACK_NCF_00631L_PANEL = "results/ncf_00631l_panel_latest_20260630.csv"

SCHEDULER_FILES = {
    "run_daily_bat": "run_daily.bat",
    "run_fetch_bat": "run_fetch.bat",
    "task_scheduler_xml": "task_scheduler_setup.xml",
}

MODULE_OUTPUT_PATTERNS = {
    "ncf_00631l": "results/ncf_00631l_latest_*.json",
    "ncf_00632r": "results/ncf_00632r_latest_*.json",
    "factor_lens": "results/group_a_plus_factor_lens_*.json",
    "daily_pipeline": "results/ncf_daily_pipeline_*.json",
    "alphagen_lite_feature_pool": "results/alphagen_lite_feature_pool_latest_*.json",
    "alphagen_lite_shadow": "results/alphagen_lite_shadow_latest_*.json",
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_check(root: Path, label: str, rel_path: str, *, required: bool) -> dict[str, Any]:
    path = root / rel_path
    exists = path.exists()
    return {
        "label": label,
        "path": str(path),
        "relative_path": rel_path,
        "required": required,
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists and path.is_file() else None,
        "modified_at": _iso(path.stat().st_mtime) if exists else None,
        "status": "ok" if exists else ("missing" if required else "not_found"),
    }


def _latest_match(root: Path, pattern: str) -> Path | None:
    matches = [Path(p) for p in glob.glob(str(root / pattern))]
    matches = [p for p in matches if p.is_file()]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _unwrap_standard_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _status_from_warnings(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "error"
    if warnings:
        return "warning"
    return "ok"


def collect_system_resources(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    disk = shutil.disk_usage(root)
    disk_free_ratio = disk.free / disk.total if disk.total else 0.0
    # 2026-07-07 Fable audit: disk was "informational_only" (no gate) while
    # results/ grows unbounded every pipeline run (2,947 files / 1.6GB found,
    # live disk at 1.3% free) -- a full disk mid-write can corrupt the
    # duckdb file the unattended 23:00 pipeline writes to. Same warn/error
    # bands as memory below.
    if disk_free_ratio < 0.02:
        errors.append("disk_free_below_2pct")
    elif disk_free_ratio < 0.05:
        warnings.append("disk_free_below_5pct")

    payload: dict[str, Any] = {
        "disk": {
            "root": str(root),
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "free_ratio": round(float(disk_free_ratio), 4),
            "status_policy": "warn_below_5pct_error_below_2pct",
        }
    }

    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        memory_available_ratio = memory.available / memory.total if memory.total else 0.0
        if memory_available_ratio < 0.05:
            errors.append("memory_available_below_5pct")
        elif memory_available_ratio < 0.15:
            warnings.append("memory_available_below_15pct")
        payload["cpu"] = {
            "percent": psutil.cpu_percent(interval=0),
            "count": psutil.cpu_count(),
        }
        payload["memory"] = {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.total - memory.available,
            "available_ratio": round(float(memory_available_ratio), 4),
        }
    except Exception as exc:  # noqa: BLE001
        warnings.append("psutil_unavailable")
        payload["cpu"] = {"status": "unavailable", "reason": repr(exc)}
        payload["memory"] = {"status": "unavailable", "reason": repr(exc)}

    payload["warnings"] = warnings
    payload["errors"] = errors
    payload["status"] = _status_from_warnings(errors, warnings)
    return payload


def _resolve_ncf_panel_path(root: Path) -> str:
    return resolve_ncf_00631l_panel_path(root, fallback=FALLBACK_NCF_00631L_PANEL)


def _execution_plan_freshness(root: Path, *, max_lag_days: int = 3) -> dict[str, Any]:
    """execution_plan.py reads a manually-maintained portfolio workbook
    (actual cash balance / share holdings) -- it cannot be safely
    auto-regenerated by the unattended daily pipeline with fabricated
    defaults (e.g. --cash-balance 0.0), so it is intentionally NOT wired
    into run_ncf_daily_pipeline.py. 2026-07-07 Fable audit: this meant
    execution_plan.json could go stale indefinitely (found 8+ days stale)
    with artifact_health still reporting "ok" because it only checked
    existence, not freshness relative to live_signal.json. This is a
    detection-only check -- the user must regenerate it manually.
    """
    plan_path = root / "report/group_a_plus/latest/execution_plan.json"
    live_signal_path = root / "report/group_a_plus/latest/live_signal.json"
    if not plan_path.exists() or not live_signal_path.exists():
        return {"status": "unknown", "lag_days": None}
    lag_seconds = live_signal_path.stat().st_mtime - plan_path.stat().st_mtime
    lag_days = lag_seconds / 86400.0
    stale = lag_days > max_lag_days
    return {
        "status": "stale" if stale else "fresh",
        "lag_days": round(lag_days, 2),
        "max_lag_days": max_lag_days,
        "execution_plan_modified_at": _iso(plan_path.stat().st_mtime),
        "live_signal_modified_at": _iso(live_signal_path.stat().st_mtime),
    }


def _golden_signal_freshness(root: Path, *, max_lag_days: int = 3) -> dict[str, Any]:
    """Group A's golden1 signal (results/signal_group_a_*.json, resolved via
    a2111._resolve_golden_signal_path -- the same file a2118 loads for its
    golden1-regime base weights) is generated by generate_dual_group_signal.py,
    which is not called by run_ncf_daily_pipeline.py, run_daily.bat, or
    run_fetch.bat. It must be regenerated manually.

    2026-07-12/13 audit: found a real production incident from exactly this
    gap -- live_signal.json's target_weights silently used a golden1
    snapshot that was already 3 days stale when it was picked up, and no
    health check anywhere flagged it (artifact_health only checks file
    existence, not this file's freshness). This is detection-only --
    staleness here does not block anything and the user must regenerate it
    manually (generate_dual_group_signal.py).
    """
    try:
        from group_a_plus.runners.a2111 import _resolve_golden_signal_path

        golden_path = Path(_resolve_golden_signal_path())
    except Exception as exc:  # noqa: BLE001
        return {"status": "unknown", "reason": str(exc)}
    if not golden_path.exists():
        return {"status": "unknown", "reason": f"golden1 signal file not found: {golden_path}"}
    lag_days = (_utc_now().timestamp() - golden_path.stat().st_mtime) / 86400.0
    stale = lag_days > max_lag_days
    return {
        "status": "stale" if stale else "fresh",
        "lag_days": round(lag_days, 2),
        "max_lag_days": max_lag_days,
        "golden_signal_path": str(golden_path),
        "golden_signal_modified_at": _iso(golden_path.stat().st_mtime),
    }


def _group_a_plus_decision_signal_freshness(root: Path, *, max_lag_days: int = 14) -> dict[str, Any]:
    """Group A+'s own policy_signal (report/group_a_plus/latest/decision.json
    -> results/group_a_plus_policy_signal_*.json) feeds a2118's
    `current_defensive` weights, which are only used by the
    group_a_plus_recovery regime -- not golden1 (the current regime) and not
    group_a_plus_defensive (which uses the fixed bond30_cash30 basket
    instead). Same "exists, not scheduled, no freshness check" gap as
    golden1 above, found in the same audit -- narrower blast radius (only
    matters if/when a crash-recovery transition happens), hence the longer
    default tolerance. Detection-only.
    """
    decision_path = root / "report/group_a_plus/latest/decision.json"
    if not decision_path.exists():
        return {"status": "unknown", "lag_days": None}
    decision = _read_json(decision_path) or {}
    signal_json = decision.get("signal_json")
    target_path = (root / signal_json) if signal_json else decision_path
    if not target_path.exists():
        target_path = decision_path
    lag_days = (_utc_now().timestamp() - target_path.stat().st_mtime) / 86400.0
    stale = lag_days > max_lag_days
    return {
        "status": "stale" if stale else "fresh",
        "lag_days": round(lag_days, 2),
        "max_lag_days": max_lag_days,
        "policy_signal_path": str(target_path),
        "policy_signal_modified_at": _iso(target_path.stat().st_mtime),
    }


def _volatility_gate_is_active(live_signal: dict[str, Any] | None) -> bool:
    if not isinstance(live_signal, dict):
        return False
    for alert in live_signal.get("signal_alerts", []) or []:
        if not isinstance(alert, dict):
            continue
        metadata = alert.get("metadata") or {}
        if (
            alert.get("type") == "volatility_gate_high_vol"
            and isinstance(metadata, dict)
            and metadata.get("allow_00631l_add") is False
        ):
            return True
    volatility_gate = ((live_signal.get("garch_regime_shadow") or {}).get("volatility_gate") or {})
    return volatility_gate.get("high_vol_gate") is True


def _volatility_gate_execution_guard_health(root: Path) -> dict[str, Any]:
    live_path = root / "report/group_a_plus/latest/live_signal.json"
    plan_path = root / "report/group_a_plus/latest/execution_plan.json"
    live_signal = _unwrap_standard_payload(_read_json(live_path))
    execution_plan = _unwrap_standard_payload(_read_json(plan_path))

    active = _volatility_gate_is_active(live_signal)
    warnings: list[str] = []
    aligned = False
    guard = {}

    if not active:
        return {
            "status": "ok",
            "volatility_gate_active": False,
            "execution_plan_aligned": None,
            "warnings": warnings,
        }

    if execution_plan is None:
        warnings.append("volatility_gate_active_execution_plan_missing")
    else:
        aligned = (
            str(execution_plan.get("actual_data_date") or "") == str(live_signal.get("actual_data_date") or "")
            and str(execution_plan.get("strategy_id") or "") == str(live_signal.get("strategy_id") or "")
        )
        if not aligned:
            warnings.append("volatility_gate_active_execution_plan_unaligned")
        guard = execution_plan.get("pre_trade_guard") if isinstance(execution_plan.get("pre_trade_guard"), dict) else {}
        if aligned and not guard:
            warnings.append("volatility_gate_active_pre_trade_guard_missing")
        elif aligned and guard.get("allow_00631l_add") is not False:
            warnings.append("volatility_gate_active_pre_trade_guard_not_enforced")

    return {
        "status": "warning" if warnings else "ok",
        "volatility_gate_active": True,
        "execution_plan_aligned": aligned if execution_plan is not None else False,
        "live_signal_actual_data_date": live_signal.get("actual_data_date") if live_signal else None,
        "execution_plan_actual_data_date": execution_plan.get("actual_data_date") if execution_plan else None,
        "strategy_id": live_signal.get("strategy_id") if live_signal else None,
        "execution_plan_strategy_id": execution_plan.get("strategy_id") if execution_plan else None,
        "pre_trade_guard_status": guard.get("status") if guard else None,
        "allow_00631l_add": guard.get("allow_00631l_add") if guard else None,
        "warnings": warnings,
    }


def _dfl_advisory_health(root: Path) -> dict[str, Any]:
    live_path = root / "report/group_a_plus/latest/live_signal.json"
    advisory_path = root / "report/group_a_plus/latest/a2118_dfl_advisory.json"
    live_signal = _unwrap_standard_payload(_read_json(live_path))
    advisory = _unwrap_standard_payload(_read_json(advisory_path))
    warnings: list[str] = []

    if advisory is None:
        return {
            "status": "warning",
            "exists": False,
            "path": str(advisory_path),
            "warnings": ["dfl_advisory_missing"],
        }

    live_actual = str(live_signal.get("actual_data_date") or "") if live_signal else None
    advisory_as_of = str(advisory.get("as_of") or "")
    aligned = bool(live_actual and advisory_as_of == live_actual)
    if advisory.get("status") != "available":
        warnings.append("dfl_advisory_unavailable")
    if live_actual and not aligned:
        warnings.append("dfl_advisory_unaligned")

    return {
        "status": "warning" if warnings else "ok",
        "exists": True,
        "path": str(advisory_path),
        "modified_at": _iso(advisory_path.stat().st_mtime) if advisory_path.exists() else None,
        "live_signal_actual_data_date": live_actual,
        "advisory_as_of": advisory_as_of or None,
        "aligned": aligned,
        "advisory_status": advisory.get("status"),
        "action": advisory.get("action"),
        "advisory_active": advisory.get("advisory_active"),
        "policy": advisory.get("policy"),
        "warnings": warnings,
    }


def _latest_dfl_active_date_audit_path(root: Path) -> Path | None:
    latest = root / "results/a2118_dfl_active_date_audit_latest.json"
    if latest.exists():
        return latest
    return _latest_match(root, "results/a2118_dfl_active_date_audit_*.json")


def _dfl_active_date_audit_health(root: Path) -> dict[str, Any]:
    audit_path = _latest_dfl_active_date_audit_path(root)
    warnings: list[str] = []

    if audit_path is None:
        return {
            "status": "warning",
            "exists": False,
            "path": str(root / "results/a2118_dfl_active_date_audit_latest.json"),
            "warnings": ["dfl_active_date_audit_missing"],
        }

    audit = _read_json(audit_path)
    if audit is None:
        return {
            "status": "warning",
            "exists": True,
            "path": str(audit_path),
            "modified_at": _iso(audit_path.stat().st_mtime),
            "warnings": ["dfl_active_date_audit_unreadable"],
        }

    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    assumptions = audit.get("assumptions") if isinstance(audit.get("assumptions"), dict) else {}
    policy = str(assumptions.get("policy") or "")
    if audit.get("status") != "research_only":
        warnings.append("dfl_active_date_audit_not_research_only")
    if summary.get("all_checks_pass") is not True:
        warnings.append("dfl_active_date_audit_hard_checks_not_passing")
    if policy != "shadow_only_no_auto_weight_change":
        warnings.append("dfl_active_date_audit_policy_not_shadow_only")

    return {
        "status": "warning" if warnings else "ok",
        "exists": True,
        "path": str(audit_path),
        "modified_at": _iso(audit_path.stat().st_mtime),
        "audit_status": audit.get("status"),
        "conclusion": audit.get("conclusion"),
        "policy": policy or None,
        "active_days": summary.get("active_days"),
        "all_checks_pass": summary.get("all_checks_pass"),
        "warning_days": summary.get("warning_days"),
        "existing_guard_overlap_days": summary.get("existing_guard_overlap_days"),
        "total_estimated_cost_bps": summary.get("total_estimated_cost_bps"),
        "warnings": warnings,
    }


def collect_artifact_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    artifacts = dict(REQUIRED_ARTIFACTS)
    artifacts["ncf_00631l_panel"] = _resolve_ncf_panel_path(root)
    required = [
        _path_check(root, label, rel_path, required=True)
        for label, rel_path in artifacts.items()
    ]
    scheduler = [
        _path_check(root, label, rel_path, required=False)
        for label, rel_path in SCHEDULER_FILES.items()
    ]
    daily_log = _path_check(root, "daily_log", "logs/daily.log", required=False)
    execution_plan_freshness = _execution_plan_freshness(root)
    golden_signal_freshness = _golden_signal_freshness(root)
    group_a_plus_decision_signal_freshness = _group_a_plus_decision_signal_freshness(root)
    volatility_gate_execution_guard = _volatility_gate_execution_guard_health(root)
    dfl_advisory = _dfl_advisory_health(root)
    dfl_active_date_audit = _dfl_active_date_audit_health(root)
    errors = [item["label"] for item in required if item["status"] != "ok"]
    warnings = [item["label"] for item in scheduler if item["status"] != "ok"]
    if daily_log["status"] != "ok":
        warnings.append("daily_log")
    if execution_plan_freshness["status"] == "stale":
        warnings.append("execution_plan_stale")
    if golden_signal_freshness["status"] == "stale":
        warnings.append("golden_signal_stale")
    if group_a_plus_decision_signal_freshness["status"] == "stale":
        warnings.append("group_a_plus_decision_signal_stale")
    warnings.extend(volatility_gate_execution_guard.get("warnings", []))
    warnings.extend(dfl_advisory.get("warnings", []))
    warnings.extend(dfl_active_date_audit.get("warnings", []))
    return {
        "status": _status_from_warnings(errors, warnings),
        "missing_required": errors,
        "missing_optional": warnings,
        "execution_plan_freshness": execution_plan_freshness,
        "golden_signal_freshness": golden_signal_freshness,
        "group_a_plus_decision_signal_freshness": group_a_plus_decision_signal_freshness,
        "volatility_gate_execution_guard": volatility_gate_execution_guard,
        "dfl_advisory": dfl_advisory,
        "dfl_active_date_audit": dfl_active_date_audit,
        "required": required,
        "scheduler_files": scheduler,
        "daily_log": daily_log,
    }


MAX_PIPELINE_MANIFEST_STALE_DAYS = 1


def collect_pipeline_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    manifest = _latest_match(root, "results/ncf_daily_pipeline_*.json")
    if manifest is None:
        return {
            "status": "warning",
            "latest_manifest": None,
            "warnings": ["pipeline_manifest_missing"],
            "outputs": {},
            "signals": {},
        }

    payload = _read_json(manifest)
    if payload is None:
        return {
            "status": "error",
            "latest_manifest": str(manifest),
            "latest_manifest_modified_at": _iso(manifest.stat().st_mtime),
            "errors": ["pipeline_manifest_unreadable"],
            "outputs": {},
            "signals": {},
        }

    errors: list[str] = []
    # Fable audit (2026-07-08, #2): a critical pipeline step (e.g. an NCF
    # model) can now write this manifest with status="failed" instead of
    # raising uncaught -- surface that here rather than treating a failed
    # run's own manifest as healthy.
    if payload.get("status") == "failed":
        errors.append("pipeline_run_failed")

    date_stamp = payload.get("date_stamp")
    stale_days: int | None = None
    if isinstance(date_stamp, str) and len(date_stamp) == 8 and date_stamp.isdigit():
        try:
            manifest_date = datetime.strptime(date_stamp, "%Y%m%d").date()
            stale_days = (_utc_now().date() - manifest_date).days
        except ValueError:
            stale_days = None
    # This previously only checked whether *a* manifest existed via glob,
    # never whether it was today's -- a pipeline that silently stopped
    # producing new manifests (e.g. every step erroring before reaching the
    # manifest write) kept reporting "ok" off of an old but structurally
    # valid manifest indefinitely.
    if stale_days is not None and stale_days > MAX_PIPELINE_MANIFEST_STALE_DAYS:
        errors.append("pipeline_manifest_stale")

    outputs = payload.get("outputs") or {}
    output_checks = {
        name: _path_check(root, name, str(Path(path)), required=False)
        for name, path in outputs.items()
    }
    missing_outputs = [name for name, item in output_checks.items() if item["status"] != "ok"]
    warnings = list(missing_outputs)
    return {
        "status": _status_from_warnings(errors, warnings),
        "latest_manifest": str(manifest),
        "latest_manifest_modified_at": _iso(manifest.stat().st_mtime),
        "date_stamp": date_stamp,
        "stale_days": stale_days,
        "errors": errors,
        "missing_outputs": missing_outputs,
        "outputs": output_checks,
        "signals": payload.get("signals") or {},
    }


def collect_external_data_freshness(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Surface `scripts/misc/check_ohlcv_freshness.py`'s latest report.

    2026-07-07 Fable audit: this daily pipeline step (`ohlcv_freshness`)
    produced a JSON report every day but nothing consumed it -- the
    external_market_ohlcv staleness it now also detects (2330.TW, macro
    tickers feeding ncf_2330.py's leadership/global features) was invisible
    to ops_health/alert_state despite the report existing on disk.
    """
    latest = _latest_match(root, "results/ohlcv_freshness_*.json")
    if latest is None:
        return {
            "status": "warning",
            "latest_report": None,
            "warnings": ["ohlcv_freshness_report_missing"],
        }
    payload = _read_json(latest)
    if payload is None:
        return {
            "status": "error",
            "latest_report": str(latest),
            "latest_report_modified_at": _iso(latest.stat().st_mtime),
            "errors": ["ohlcv_freshness_report_unreadable"],
        }
    overall = payload.get("overall_status", "unknown")
    status = "error" if overall == "error" else ("warning" if overall == "warning" else "ok")
    return {
        "status": status,
        "latest_report": str(latest),
        "latest_report_modified_at": _iso(latest.stat().st_mtime),
        "target_date": payload.get("target_date"),
        "overall_status": overall,
        "error_tickers": payload.get("error_tickers", []),
        "warning_tickers": payload.get("warning_tickers", []),
        "external_error_tickers": payload.get("external_error_tickers", []),
    }


def collect_module_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    modules: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for name, pattern in MODULE_OUTPUT_PATTERNS.items():
        path = _latest_match(root, pattern)
        if path is None:
            modules[name] = {
                "status": "missing",
                "pattern": pattern,
                "latest_path": None,
            }
            warnings.append(name)
            continue
        modules[name] = {
            "status": "ok",
            "pattern": pattern,
            "latest_path": str(path),
            "modified_at": _iso(path.stat().st_mtime),
            "size_bytes": int(path.stat().st_size),
        }

    live_signal = _read_json(root / "report/group_a_plus/latest/live_signal.json")
    tbrain_status = None
    finbert_status = None
    factor_lens_status = None
    if live_signal:
        data = live_signal.get("data") if live_signal.get("success") is True else live_signal
        tbrain_status = (data.get("tbrain_shadow") or {}).get("status")
        finbert_status = (data.get("finbert_sentiment") or {}).get("status")
        factor_lens_status = (data.get("factor_lens_gate") or {}).get("status")
    modules["tbrain_shadow"] = {"status": tbrain_status or "unknown", "source": "live_signal"}
    modules["finbert_sentiment"] = {"status": finbert_status or "unknown", "source": "live_signal"}
    modules["factor_lens_gate"] = {"status": factor_lens_status or "unknown", "source": "live_signal"}

    for name in ("tbrain_shadow", "finbert_sentiment", "factor_lens_gate"):
        if modules[name]["status"] not in {"ok", "available"}:
            warnings.append(name)

    return {
        "status": _status_from_warnings([], warnings),
        "warnings": warnings,
        "modules": modules,
    }


def collect_tsmc_weight_assumption_health() -> dict[str, Any]:
    """Fable audit (2026-07-08, #9): TSMC_0050_WEIGHT_ASSUMPTION feeds
    daily_signal.py's ex-TSMC proxy, which amplifies bias in this constant
    by roughly 1/(1-w) -- it directly affects the tsmc_weak_manual_review /
    narrow_lead classification. It has no recorded calibration date, so this
    always reports "stale" (needs verification against real 0050 holdings
    data) unless/until TSMC_0050_WEIGHT_ASSUMPTION_AS_OF is set.
    """
    stale = tsmc_0050_weight_assumption_is_stale()
    warnings = ["tsmc_0050_weight_assumption_uncalibrated"] if stale else []
    return {
        "status": "warning" if stale else "ok",
        "weight_assumption": TSMC_0050_WEIGHT_ASSUMPTION,
        "as_of": TSMC_0050_WEIGHT_ASSUMPTION_AS_OF,
        "max_age_days": TSMC_0050_WEIGHT_ASSUMPTION_MAX_AGE_DAYS,
        "warnings": warnings,
    }


def build_ops_health(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    system = collect_system_resources(root)
    artifacts = collect_artifact_health(root)
    pipeline = collect_pipeline_health(root)
    modules = collect_module_health(root)
    external_data_freshness = collect_external_data_freshness(root)
    tsmc_weight_assumption = collect_tsmc_weight_assumption_health()
    sections = {
        "system_resources": system,
        "artifact_health": artifacts,
        "pipeline_health": pipeline,
        "module_health": modules,
        "external_data_freshness": external_data_freshness,
        "tsmc_weight_assumption_health": tsmc_weight_assumption,
    }
    errors = [name for name, section in sections.items() if section.get("status") == "error"]
    warnings = [name for name, section in sections.items() if section.get("status") == "warning"]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_ops_health",
        "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": _status_from_warnings(errors, warnings),
        "errors": errors,
        "warnings": warnings,
        "active_allocation_impact": "none",
        "source_inspiration": "Ajenti read-only dashboard/plugin health patterns",
        **sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    std = OutputStandardizer("group_a_plus.operations.ops_health")
    try:
        report = build_ops_health(Path(args.root))
        payload = std.success(report)
    except Exception as exc:  # noqa: BLE001
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Ops health: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
