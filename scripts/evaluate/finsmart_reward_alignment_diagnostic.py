#!/usr/bin/env python3
"""Diagnose whether existing keyword-proxy sentiment features are aligned with
realized returns, and on what horizon.

Research/advisory-readiness artifact only. Motivated by arXiv:2607.28127
("FinSMART", Iacovides et al. 2026-07-30), whose central methodological
finding is that a sentiment signal's correlation with realized returns is far
stronger on the *publication-day* return than on the next-day return (Pearson
correlation drops from ~0.4 to ~0.03 within one trading day in their data),
and that gating on an economically-meaningful move threshold sharpens the
signal further. Full RL fine-tuning of a sentiment LLM against realized
returns (as the paper does) is not attempted here -- this repo has no
LLM training infrastructure (no PEFT/LoRA/TRL/GRPO, no GPU) and the local
news corpus is title-only, far thinner than the paper's full-article corpus.
This script only asks the cheaper, prior question: does the sentiment feature
that already exists here show the same same-day >> next-day alignment
pattern, on any horizon, before any further investment is considered.

Does not modify any production feature, DB, or report. Read-only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from build_finbert_sentiment_features import score_text_finbert_proxy  # noqa: E402

SENTIMENT_DIR = PROJECT_ROOT / "FinRL" / "data" / "sentiment"
FINMIND_MERGED = PROJECT_ROOT / "news" / "finmind_stock_news_merged_full.jsonl"
OUTPUT_MD = PROJECT_ROOT / "research" / "shadow" / "FINSMART_REWARD_ALIGNMENT_DIAGNOSTIC_20260805.md"
ALPHA_THRESHOLD = 0.005  # matches the paper's tau = 0.5%


def _load_market_return(ticker: str) -> pd.Series:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(
        "SELECT dt, close FROM ohlcv WHERE ticker = ? ORDER BY dt", [ticker]
    ).fetchdf()
    con.close()
    df["dt"] = pd.to_datetime(df["dt"])
    return df.set_index("dt")["close"].pct_change().rename("ret")


def _corr_same_next(sentiment: pd.Series, ret: pd.Series, label: str) -> dict:
    df = pd.concat([sentiment.rename("s"), ret.rename("r")], axis=1).dropna()
    df["r_next"] = ret.reindex(df.index).shift(-1)
    df = df.dropna()

    same_corr = df["s"].corr(df["r"])
    next_corr = df["s"].corr(df["r_next"])

    gated = df[df["r"].abs() > ALPHA_THRESHOLD]
    gated_same_corr = gated["s"].corr(gated["r"]) if len(gated) >= 20 else np.nan
    gated_next = pd.concat([sentiment.rename("s"), ret.reindex(sentiment.index).shift(-1).rename("r_next")], axis=1).dropna()
    gated_next_mask = ret.reindex(gated_next.index).abs() > ALPHA_THRESHOLD
    gated_next_corr = gated_next.loc[gated_next_mask.reindex(gated_next.index).fillna(False), "s"].corr(
        gated_next.loc[gated_next_mask.reindex(gated_next.index).fillna(False), "r_next"]
    ) if gated_next_mask.sum() >= 20 else np.nan

    return {
        "series": label,
        "n": int(len(df)),
        "corr_same_day": round(float(same_corr), 4) if pd.notna(same_corr) else None,
        "corr_next_day": round(float(next_corr), 4) if pd.notna(next_corr) else None,
        "n_gated_same": int(len(gated)),
        "corr_same_day_gated_0.5pct": round(float(gated_same_corr), 4) if pd.notna(gated_same_corr) else None,
        "corr_next_day_gated_0.5pct": round(float(gated_next_corr), 4) if pd.notna(gated_next_corr) else None,
    }


def _load_finmind_sentiment(ticker_id: str) -> pd.Series:
    rows = []
    with open(FINMIND_MERGED, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("finmind_stock_id") != ticker_id:
                continue
            score = score_text_finbert_proxy(rec.get("title", ""))["finbert_sentiment_score"]
            rows.append({"date": rec["date"], "score": score})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date")["score"].mean()
    return daily.rename("sentiment")


def main() -> None:
    tw50_ret = _load_market_return("0050.TW")

    results = []

    # (1) production feature: LTN-based rule_based_finbert_proxy, market-wide
    prod = pd.read_csv(SENTIMENT_DIR / "finbert_market_sentiment_daily.csv", parse_dates=["date"])
    prod_series = prod.set_index("date")["finbert_sentiment_score"]
    results.append(_corr_same_next(prod_series, tw50_ret, "production finbert_sentiment (LTN, market-wide, rule_based_finbert_proxy) vs 0050 return"))

    # (2) same rule-based scorer applied to FinMind 0050-tagged, ticker-specific headlines
    finmind_0050 = _load_finmind_sentiment("0050")
    results.append(_corr_same_next(finmind_0050, tw50_ret, "FinMind 0050-tagged headlines (same keyword scorer) vs 0050 return"))

    # (3) llm_market_sentiment_daily.csv (separate keyword pipeline, market-wide)
    llm_path = SENTIMENT_DIR / "llm_market_sentiment_daily.csv"
    if llm_path.exists():
        llm_df = pd.read_csv(llm_path, parse_dates=["date"])
        score_col = "llm_sentiment_score" if "llm_sentiment_score" in llm_df.columns else llm_df.columns[1]
        llm_series = llm_df.set_index("date")[score_col]
        results.append(_corr_same_next(llm_series, tw50_ret, "production llm_sentiment_score (LTN, market-wide) vs 0050 return"))

    lines = []
    lines.append("# FinSMART Reward-Alignment Diagnostic — Existing Sentiment Features vs 0050 Returns")
    lines.append("")
    lines.append("**Status: research/shadow only. Not wired to any production signal or gate.**")
    lines.append("")
    lines.append("Motivated by arXiv:2607.28127 (\"FinSMART\", Iacovides et al. 2026-07-30). Their key")
    lines.append("methodological finding: sentiment-return alignment is far stronger on the")
    lines.append("publication-day return than the next-day return (Pearson corr ~0.4 -> ~0.03 in")
    lines.append("their data), and gating on an economically-meaningful move threshold sharpens it")
    lines.append("further. This is a cheap diagnostic only -- checks whether the existing")
    lines.append("keyword-proxy sentiment features (production is rule-based, not real FinBERT")
    lines.append("inference -- see finbert_scoring_mode column) show the same pattern on any")
    lines.append(f"horizon, gated at |return| > {ALPHA_THRESHOLD:.1%} (paper's tau). No LLM fine-tuning")
    lines.append("or RL training was attempted -- this repo has no PEFT/LoRA/TRL/GRPO infra and no")
    lines.append("GPU, and local news is title-only (far thinner than the paper's full-article corpus).")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(pd.DataFrame(results).to_string(index=False))
    lines.append("")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
