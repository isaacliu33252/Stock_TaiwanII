#!/usr/bin/env python3
"""Export the frozen GroupA+ GIFT state/reward panel for offline experiments.

The panel is an immutable input artifact for future walk-forward design. This
script does not train models, output actions, target weights, or live decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_llm_state_reward_interface_frozen_manifest import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_FROZEN_MANIFEST,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke import (  # noqa: E402
    DEFAULT_TICKERS,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    DEFAULT_DB,
    _feature_frame,
    _load_json,
    _load_ohlcv_from_db,
    _resolve,
)


DEFAULT_PANEL_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_panel.parquet"
DEFAULT_REVIEW_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_panel_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_frozen_panel/history"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _params_for_feature_frame(params: dict[str, Any] | None) -> dict[str, float]:
    params = params or {}
    return {
        "downside_drawdown_weight": float(params.get("drawdown_weight", 0.50)),
        "downside_volatility_weight": float(params.get("volatility_weight", 0.30)),
        "downside_tail_decay_weight": float(params.get("tail_decay_weight", 0.20)),
        "volatility_penalty_scale": float(params.get("volatility_scale", 3.0)),
        "tail_decay_scale": float(params.get("tail_decay_scale", 4.0)),
    }


def build_panel(
    *,
    frozen_manifest_path: Path = DEFAULT_FROZEN_MANIFEST,
    db_path: Path = DEFAULT_DB,
    tickers: list[str] | None = None,
    start: str = "2016-01-01",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = _load_json(frozen_manifest_path)
    freeze = manifest.get("freeze") if isinstance(manifest.get("freeze"), dict) else {}
    decision = manifest.get("decision") if isinstance(manifest.get("decision"), dict) else {}
    selected_tickers = tickers or list(DEFAULT_TICKERS)

    blockers: list[str] = []
    if not manifest:
        blockers.append("missing_frozen_manifest")
    elif manifest.get("status") != "frozen_for_manual_offline_review":
        blockers.append(f"frozen_manifest_not_available:{manifest.get('status')}")
    if decision.get("offline_feature_reward_export_allowed") is not True:
        blockers.append("offline_feature_reward_export_not_allowed")
    if not freeze.get("proposal_id"):
        blockers.append("missing_frozen_proposal_id")
    if not freeze.get("frozen_manifest_sha256"):
        blockers.append("missing_frozen_manifest_sha256")
    if not db_path.exists():
        blockers.append("missing_duckdb")

    frames: list[pd.DataFrame] = []
    missing_tickers: list[str] = []
    can_build_panel = db_path.exists() and bool(freeze.get("proposal_id")) and bool(freeze.get("frozen_manifest_sha256"))
    if can_build_panel:
        feature_kwargs = _params_for_feature_frame(freeze.get("reward_params"))
        for ticker in selected_tickers:
            ohlcv = _load_ohlcv_from_db(db_path, ticker=ticker, start=start)
            if ohlcv.empty:
                missing_tickers.append(ticker)
                continue
            frame = _feature_frame(ohlcv, proposal_id=str(freeze.get("proposal_id")), **feature_kwargs)
            frame.insert(0, "ticker", ticker)
            frame["return"] = pd.to_numeric(frame["close"], errors="coerce").pct_change()
            frame["freeze_id"] = freeze.get("freeze_id")
            frame["frozen_manifest_sha256"] = freeze.get("frozen_manifest_sha256")
            frame["proposal_id"] = freeze.get("proposal_id")
            frames.append(frame)
    if missing_tickers:
        blockers.append(f"missing_ohlcv_data:{','.join(missing_tickers)}")

    panel = pd.concat(frames, ignore_index=True).sort_values(["date", "ticker"]) if frames else pd.DataFrame()
    state_columns = [column for column in freeze.get("state_columns", []) if column in panel.columns]
    reward_columns = [column for column in freeze.get("reward_columns", []) if column in panel.columns]
    required = ["date", "ticker", "close", "return", *state_columns, *reward_columns]
    missing_columns = [column for column in required if column not in panel.columns]
    if missing_columns and not panel.empty:
        blockers.append(f"missing_panel_columns:{','.join(missing_columns)}")

    finite_reward_ratio = None
    if "reward_proxy" in panel.columns and len(panel):
        reward = pd.to_numeric(panel["reward_proxy"], errors="coerce")
        finite_reward_ratio = float(np.isfinite(reward.to_numpy(dtype=float, na_value=np.nan)).sum() / len(panel))

    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": manifest.get("as_of"),
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "frozen_feature_reward_panel_only_no_model_training_no_live_action",
        "inputs": {
            "frozen_manifest": str(frozen_manifest_path),
            "frozen_manifest_sha256": freeze.get("frozen_manifest_sha256"),
            "db": str(db_path),
            "tickers": selected_tickers,
            "start": start,
            "proposal_id": freeze.get("proposal_id"),
            "reward_params": freeze.get("reward_params"),
        },
        "summary": {
            "row_count": int(len(panel)),
            "ticker_count": len(selected_tickers),
            "available_ticker_count": int(panel["ticker"].nunique()) if "ticker" in panel.columns else 0,
            "missing_tickers": missing_tickers,
            "date_start": panel["date"].min().date().isoformat() if "date" in panel.columns and len(panel) else None,
            "date_end": panel["date"].max().date().isoformat() if "date" in panel.columns and len(panel) else None,
            "state_columns": state_columns,
            "reward_columns": reward_columns,
            "finite_reward_ratio": _finite_float(finite_reward_ratio),
            "reward_proxy_min": _finite_float(panel["reward_proxy"].min()) if "reward_proxy" in panel.columns and len(panel) else None,
            "reward_proxy_max": _finite_float(panel["reward_proxy"].max()) if "reward_proxy" in panel.columns and len(panel) else None,
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "offline_walk_forward_input_ready": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    return panel, review


def write_outputs(
    panel: pd.DataFrame,
    review: dict[str, Any],
    *,
    panel_output: Path,
    review_output: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> dict[str, Any]:
    panel_output.parent.mkdir(parents=True, exist_ok=True)
    review_output.parent.mkdir(parents=True, exist_ok=True)
    if not panel.empty:
        panel.to_parquet(panel_output, index=False)
    review = dict(review)
    review["outputs"] = {
        "panel": str(panel_output),
        "panel_sha256": _sha256_file(panel_output),
        "review": str(review_output),
    }
    review_output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(review.get("as_of") or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        history_path = history_dir / f"llm_state_reward_interface_frozen_panel_review_{stamp}.json"
        history_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-manifest", default=str(DEFAULT_FROZEN_MANIFEST))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--panel-output", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--review-output", default=str(DEFAULT_REVIEW_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    panel, review = build_panel(
        frozen_manifest_path=_resolve(args.frozen_manifest),
        db_path=_resolve(args.db),
        tickers=args.ticker or None,
        start=args.start,
    )
    review = write_outputs(
        panel,
        review,
        panel_output=_resolve(args.panel_output),
        review_output=_resolve(args.review_output),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"LLM state-reward frozen panel review: {_resolve(args.review_output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "row_count": review["summary"]["row_count"],
                "available_ticker_count": review["summary"]["available_ticker_count"],
                "panel_sha256": review["outputs"]["panel_sha256"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
