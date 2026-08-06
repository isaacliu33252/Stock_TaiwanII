# FinSMART Reward-Alignment Diagnostic — Existing Sentiment Features vs 0050 Returns

**Status: research/shadow only. Not wired to any production signal or gate.**

Motivated by arXiv:2607.28127 ("FinSMART", Iacovides et al. 2026-07-30). Their key
methodological finding: sentiment-return alignment is far stronger on the
publication-day return than the next-day return (Pearson corr ~0.4 -> ~0.03 in
their data), and gating on an economically-meaningful move threshold sharpens it
further. This is a cheap diagnostic only -- checks whether the existing
keyword-proxy sentiment features (production is rule-based, not real FinBERT
inference -- see finbert_scoring_mode column) show the same pattern on any
horizon, gated at |return| > 0.5% (paper's tau). No LLM fine-tuning
or RL training was attempted -- this repo has no PEFT/LoRA/TRL/GRPO infra and no
GPU, and local news is title-only (far thinner than the paper's full-article corpus).

## Results

                                                                                  series    n  corr_same_day  corr_next_day  n_gated_same  corr_same_day_gated_0.5pct  corr_next_day_gated_0.5pct
production finbert_sentiment (LTN, market-wide, rule_based_finbert_proxy) vs 0050 return 1555         0.1148         0.0052           968                      0.1379                     -0.0500
                      FinMind 0050-tagged headlines (same keyword scorer) vs 0050 return  354         0.2355         0.0884           253                      0.2638                      0.1033
                        production llm_sentiment_score (LTN, market-wide) vs 0050 return 1555        -0.0203        -0.0252           968                     -0.0255                     -0.0269
