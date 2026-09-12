# 2603.01157v2 BAWS Paper-Style Replication

- Generated: `2026-08-14T13:39:10`
- Policy: `research_only_no_groupa_plus_live_change`
- Local reps: `10`
- Local bootstrap samples: `50`

## Simulation Winners

| Setting | MAB | Var | MSE | CR | CL |
|---|---:|---:|---:|---:|---:|
| A1 | saws_lite | full | saws_lite | fixed_250 | fixed_250 |
| A2 | fixed_250 | full | fixed_250 | fixed_250 | fixed_250 |
| A3 | fixed_250 | full | fixed_250 | saws_lite | saws_lite |
| B1 | fixed_250 | full | fixed_250 | fixed_250 | fixed_250 |
| B2 | fixed_250 | full | fixed_250 | fixed_250 | saws_lite |
| B3 | saws_lite | full | fixed_250 | fixed_250 | fixed_250 |

## Empirical S&P500 Subset

- Cache window: `{'start': '2019-10-07', 'end': '2026-08-13', 'rows': 1722}`
- Evaluation window: `{'start': '2023-09-28', 'end': '2026-08-13', 'rows': 37}`
- Best method by quantile score: `fixed_250`
- Caveat: Local cache starts in 2019, not the paper's 2005-01-04 start; this is not the full Table 4 replication.

## GroupA+ Decision

Paper-style simulations may show BAWS advantages in synthetic settings, but GroupA+ ETF and portfolio tests do not support live promotion.

No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.
