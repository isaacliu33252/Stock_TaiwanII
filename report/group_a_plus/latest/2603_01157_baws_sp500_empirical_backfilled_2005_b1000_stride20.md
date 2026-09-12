# 2603.01157v2 BAWS Paper-Style Replication

- Generated: `2026-08-14T13:48:08`
- Policy: `research_only_no_groupa_plus_live_change`
- Local reps: `1`
- Local bootstrap samples: `20`

## Simulation Winners

| Setting | MAB | Var | MSE | CR | CL |
|---|---:|---:|---:|---:|---:|

## Empirical S&P500 Subset

- Cache window: `{'start': '2005-01-05', 'end': '2026-08-13', 'rows': 5435}`
- Evaluation window: `{'start': '2008-12-26', 'end': '2026-07-27', 'rows': 222}`
- Best method by quantile score: `baws`
- Caveat: Local cache covers the paper's requested S&P 500 start date. This is still a local reproduction, not the paper's full Table 4, because the run uses local bootstrap/stride settings.

## GroupA+ Decision

Paper-style simulations may show BAWS advantages in synthetic settings, but GroupA+ ETF and portfolio tests do not support live promotion.

No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
