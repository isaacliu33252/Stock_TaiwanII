#!/usr/bin/env python3
"""分段訓練 v2：14個feature，Group A 從 s06 续训（再100K），Group B 從 s03 续训"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')

from train_segments import (
    GROUP_A_TICKERS, GROUP_B_TICKERS,
    GROUP_A_TRAIN_START, GROUP_A_TRAIN_END,
    GROUP_B_TRAIN_START, GROUP_B_TRAIN_END,
    BACKTEST_START, BACKTEST_END, DOWNLOAD_END,
    train_group, backtest_all,
    download_all_stocks,
)

PROJECT_ROOT = Path('/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main')
MODEL_DIR = PROJECT_ROOT / "models" / "portfolio"

SEG_TIMESTEPS = 10_000
TOTAL_SEGS = 10

def main():
    print("=" * 72)
    print("分段訓練 v2（14-feature）")
    print("Group A: 從 s06 续训 → s07~s10（共50K）")
    print("Group B: 從 s03 续训 → s04~s10（共70K）")
    print("=" * 72)

    # Group A：从 s06 续训
    print("\n── Group A 续训 ──")
    resume_a = MODEL_DIR / "group_a_seg_s06.zip"
    for seg in range(7, TOTAL_SEGS + 1):
        model = train_group(
            GROUP_A_TICKERS, GROUP_A_TRAIN_START, GROUP_A_TRAIN_END,
            "group_a_seg", seg,
            resume_path=str(resume_a) if seg == 7 else None,
            seg_timesteps=SEG_TIMESTEPS,
        )
        resume_a = MODEL_DIR / f"group_a_seg_s{seg:02d}.zip"

    # Group B：从 s03 续训
    print("\n── Group B 续训 ──")
    resume_b = MODEL_DIR / "group_b_seg_s03.zip"
    for seg in range(4, TOTAL_SEGS + 1):
        model = train_group(
            GROUP_B_TICKERS, GROUP_B_TRAIN_START, GROUP_B_TRAIN_END,
            "group_b_seg", seg,
            resume_path=str(resume_b) if seg == 4 else None,
            seg_timesteps=SEG_TIMESTEPS,
        )
        resume_b = MODEL_DIR / f"group_b_seg_s{seg:02d}.zip"

    print("\n訓練完成！")

if __name__ == "__main__":
    main()