"""Run LLM/template daily commentary for today's Group A+ NCF signal.

Usage
-----
    # template mode（不需要 API key）
    python3 scripts/run/run_llm_commentary.py

    # MiniMax（設定環境變數）
    export MINIMAX_API_KEY=eyJ...
    python3 scripts/run/run_llm_commentary.py --provider minimax

    # MiniMax（直接帶 key）
    python3 scripts/run/run_llm_commentary.py --provider minimax --api-key eyJ...

    # Anthropic（需要 API key）
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/run/run_llm_commentary.py --provider anthropic

    # 自動選最優 provider（minimax → anthropic → template）
    python3 scripts/run/run_llm_commentary.py --provider auto

    # 其他選項
    python3 scripts/run/run_llm_commentary.py --date 2026-06-29 --model MiniMax-Text-01
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

# allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from group_a_plus.integrations.llm_commentary import generate_commentary


def _find_latest_ncf(results_dir: str = "results") -> str | None:
    pattern = str(Path(results_dir) / "ncf_00631l_latest_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    # exclude experiment files (e.g. v5_bond)
    for f in reversed(files):
        if "v5" not in f and "bond" not in f and "fs" not in f:
            return f
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Group A+ LLM daily commentary")
    parser.add_argument("--ncf", default=None, help="Path to ncf_00631l_latest_*.json")
    parser.add_argument("--date", default=None, help="Signal date label (YYYY-MM-DD)")
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "minimax", "anthropic", "template"],
                        help="LLM provider (default: auto → minimax → anthropic → template)")
    parser.add_argument("--model", default=None,
                        help="Model ID override (minimax: MiniMax-Text-01, anthropic: claude-haiku-4-5-20251001)")
    parser.add_argument("--no-save", action="store_true", help="Do not save output file")
    parser.add_argument("--api-key", default=None, help="API key for selected provider (overrides env)")
    args = parser.parse_args()

    api_key = args.api_key or ""

    ncf_path = args.ncf or _find_latest_ncf()
    if not ncf_path:
        print("[ERROR] 找不到 NCF 信號檔案。請先執行：")
        print("  python scripts/misc/ncf_00631l.py --mode infer")
        sys.exit(1)

    print(f"[INFO] 使用 NCF 信號：{ncf_path}")
    print(f"[INFO] Provider：{args.provider}")
    print()

    report = generate_commentary(
        ncf_signal_path=ncf_path,
        provider=args.provider,
        api_key=api_key or None,
        model=args.model,
        signal_date=args.date,
        save=not args.no_save,
    )

    if "error" in report:
        print(f"[ERROR] {report['error']}")
        sys.exit(1)

    # pretty print
    print("=" * 60)
    print(f"  Group A+ 每日 LLM 評述  ({report.get('date', '?')})")
    print("=" * 60)
    print(f"\n📌 {report.get('headline', '')}")
    print(f"\n【市場脈動】\n{report.get('market_pulse', '')}")

    si = report.get("signal_interpretation", {})
    print(f"\n【信號解讀】")
    print(f"  H=1 : {si.get('h1_note', '')}")
    print(f"  H=5 : {si.get('h5_note', '')}")
    print(f"  H=20: {si.get('h20_note', '')}")
    print(f"  去槓桿: {si.get('deleverage_status', '')}")

    alerts = report.get("risk_alerts", [])
    if alerts:
        print("\n【風險警報】")
        for a in alerts:
            print(f"  ⚠ {a}")

    cats = report.get("positive_catalysts", [])
    if cats:
        print("\n【潛在利多】")
        for c in cats:
            print(f"  ✦ {c}")

    print(f"\n【今日行動】\n{report.get('action_today', '')}")

    wl = report.get("watch_levels", {})
    if wl:
        print("\n【觀察指標】")
        for k, v in wl.items():
            print(f"  {k}: {v}")

    if "_saved_to" in report:
        print(f"\n[已儲存] {report['_saved_to']}")
    print()


if __name__ == "__main__":
    main()
