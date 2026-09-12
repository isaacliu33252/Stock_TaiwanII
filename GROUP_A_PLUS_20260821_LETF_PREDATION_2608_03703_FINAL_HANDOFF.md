# GroupA+ 2608.03703v1 LETF Predation Final Handoff - 2026-08-21

## Status

Final decision: `do_not_promote_keep_shadow`.

The paper was already reviewed on 2026-08-05/06 under the same arXiv ID
`2608.03703` and title `Preying on Leveraged ETFs`. This 2026-08-21 turn used
the user-provided file `C:\Users\isaac\Downloads\2608.03703v1.pdf`, confirmed
it is the same 131-page August 4, 2026 draft, and reran the existing reduced-form
GroupA+ test on the currently available data.

No latest strategy, golden1_0531, target weights, daily signals, execution
plans, or order files were changed.

## Paper Summary

Paper: `arXiv:2608.03703v1`, `Preying on Leveraged ETFs`, Yinhong Zhao,
Princeton, draft dated 2026-08-04.

Core claim:

- Leveraged ETFs must rebalance in the direction of the day's move.
- Their mandated order is sized using the same closing price at which it is
  executed.
- This creates an upward-sloping, self-referential demand schedule at the close.
- When rebalancing capital is large relative to the venue that clears the close,
  arbitrageurs can buy/sell ahead of the fund, enlarge the fund's own order, and
  unload into it.
- The observable signature is that public news is over-weighted at the close and
  reverses the next trading day.

The paper's key scalar is `loop gain`, roughly:

`LETF rebalancing capital x closing-auction price impact`.

The Korea case is extreme because Samsung/SK Hynix single-stock LETFs became
large relative to the closing mechanism. The paper reports SK Hynix's
predetermined LETF order relative to actual closing auction value around 1.02
at the median, making the mechanical order comparable to the whole auction.

## GroupA+ Relevance

The potentially relevant GroupA+ exposure is:

- `00631L.TW`: Taiwan 50 2x long ETF;
- `00632R.TW`: Taiwan 50 inverse ETF;
- `2330.TW`: TSMC, the dominant Taiwan 50 constituent;
- `0050.TW`: Taiwan 50 ETF / direct underlying proxy.

The paper is relevant as a market-structure warning, not as an alpha model.
It says that if 00631L/00632R become large enough relative to TSMC/0050 closing
liquidity, GroupA+ should worry about closing-price overshoot and next-day
reversal. The question is empirical: is the loop gain large enough in Taiwan
data?

## Prior Work Found

Existing handoff:

- `GROUP_A_PLUS_20260805_LETF_PREDATION_PAPER_REVIEW_HANDOFF.md`

Existing research script:

- `scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`

Existing research report:

- `research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md`

The prior 2026-08-05/06 conclusion was already:

- no Korea-style overshoot/reversal signal in `2330.TW`;
- no signal in `0050.TW`;
- 00631L/00632R volume is far too small relative to TSMC liquidity to justify a
  live market-structure guard;
- keep research/shadow only.

## 2026-08-21 Rerun

Command:

```bash
.venv/bin/python scripts/evaluate/letf_close_auction_overshoot_reversal_test.py
```

The script is research-only. It reads the project DB plus cached control series
and overwrites:

- `research/shadow/LETF_CLOSE_AUCTION_OVERSHOOT_REVERSAL_TEST_20260805.md`

No production DB or strategy file is written.

## Rerun Results

2026 yearly average dose proxy:

- `00631L+00632R` combined daily traded value: 80.8 億 TWD;
- TSMC own daily traded value: 722.0 億 TWD;
- ratio: 0.112.

This ratio is an intentionally loose ceiling because it compares the full day's
LETF turnover to TSMC's full-day liquidity. The paper's Korean statistic is much
stricter: predetermined LETF order versus the closing auction alone. Even this
loose Taiwan proxy is still far below the Korean SK Hynix median of 1.02.

Key next-day reversal tests:

- `2330.TW` with SOXX instrument: beta -0.0111, t -0.657, p 0.511.
- `2330.TW` with QQQ instrument: beta -0.0361, t -1.410, p 0.158.
- `2330.TW` with NASDAQ instrument: beta -0.0345, t -1.251, p 0.211.
- `0050.TW` with SOXX instrument: beta +0.0038, t +0.275, p 0.784.
- `0050.TW` with QQQ instrument: beta -0.0101, t -0.519, p 0.604.
- `0050.TW` with NASDAQ instrument: beta -0.0086, t -0.399, p 0.690.

Dose split for `2330.TW`, next-day reversal, SOXX instrument:

- low dose: beta -0.0114, t -0.417, p 0.677;
- high dose: beta -0.0144, t -0.662, p 0.508.

Period split:

- pre-2020 smaller 00631L: beta -0.0347, t -1.345, p 0.179;
- 2020 onward larger 00631L: beta -0.0042, t -0.202, p 0.840.

The period split moves opposite the loop-gain concern: the coefficient gets
closer to zero after 00631L is larger.

## Expanded Instrument Check

User asked whether instruments other than `SOXX` were available. The existing
official script already tests:

- `SOXX`;
- `QQQ`;
- `^IXIC`.

The local `external_market_ohlcv` table also contains several relevant
cross-market instruments through 2026-08-18/20. A quick read-only ad hoc check
was run against:

- `TSM`: TSMC ADR;
- `NVDA`;
- `AMD`;
- `ASML`;
- `AVGO`;
- `EWT`: Taiwan ETF;
- `^GSPC`;
- `^VIX`;
- `^KS11`;
- plus the original `SOXX`, `QQQ`, `^IXIC`.

Ad hoc command shape:

```bash
.venv/bin/python - <<'PY'
# read-only DuckDB query of external_market_ohlcv and ohlcv;
# align most recent overseas return before Taiwan date;
# HAC/Newey-West next-day regression for 2330.TW and 0050.TW.
PY
```

No file was intentionally written by this ad hoc check.

### Expanded Results

For `2330.TW`, the most negative next-day coefficients were:

| Instrument | n | beta | t | p |
|---|---:|---:|---:|---:|
| `QQQ` | 3074 | -0.0364 | -1.3994 | 0.1617 |
| `TSM` | 3074 | -0.0223 | -1.3869 | 0.1655 |
| `^IXIC` | 3074 | -0.0348 | -1.2509 | 0.2110 |
| `^GSPC` | 3075 | -0.0452 | -1.2226 | 0.2215 |
| `EWT` | 2887 | -0.0206 | -0.7697 | 0.4415 |
| `SOXX` | 3074 | -0.0117 | -0.6686 | 0.5037 |

Other tested `2330.TW` instruments were also null:

- `AMD`: beta +0.0052, p 0.5051;
- `^KS11`: beta -0.0220, p 0.5373;
- `NVDA`: beta -0.0058, p 0.5829;
- `^VIX`: beta +0.0021, p 0.6302;
- `AVGO`: beta -0.0101, p 0.6463;
- `ASML`: beta -0.0023, p 0.8941.

For `0050.TW`, no tested instrument produced a significant negative next-day
reversal. The smallest p-value was positive-signed:

- `AMD`: beta +0.0101, t +1.7303, p 0.0836.

All negative `0050.TW` coefficients were weak:

- `^GSPC`: beta -0.0150, p 0.6169;
- `QQQ`: beta -0.0096, p 0.6249;
- `^KS11`: beta -0.0120, p 0.6910;
- `^IXIC`: beta -0.0083, p 0.7018;
- `EWT`: beta -0.0027, p 0.8959;
- `TSM`: beta -0.0005, p 0.9664.

### Expanded-Instrument Conclusion

The broad instrument panel does not change the result. `QQQ`, `TSM ADR`,
`^IXIC`, and `^GSPC` have mildly negative `2330.TW` point estimates, but none
is statistically meaningful and all are tiny compared with the paper's Korean
treated-post estimate around -1.85. `0050.TW` remains cleaner still.

Recommended monitoring instruments if this is revisited:

- primary: `TSM`, `QQQ`, `^IXIC`, `SOXX`;
- secondary: `NVDA`, `AMD`, `ASML`, `AVGO`, `EWT`, `^GSPC`, `^VIX`, `^KS11`.

## Decision

Keep as `research/shadow only`.

Reasons:

- no statistically meaningful next-day reversal in `2330.TW`;
- no reversal in `0050.TW`;
- expanded instruments beyond `SOXX` still do not produce a robust reversal
  result;
- high-dose days do not show materially stronger reversal;
- post-2020 larger-00631L period does not strengthen the effect;
- Taiwan dose proxy is still far below the Korea episode's auction saturation;
- the project lacks AUM/NAV and auction-level data needed for exact loop-gain
  replication.

## Import Boundary

Useful to import:

- manual awareness that concentrated LETF complexes can distort closing prices
  if they become too large;
- continued monitoring of 00631L/00632R size relative to TSMC/0050 liquidity;
- execution hygiene: do not place large personal 00631L/00632R orders entirely
  into the final closing-auction minutes when avoidable.

Do not import:

- no automatic 00631L reduction;
- no automatic 00632R hedge open/close;
- no latest strategy gate;
- no golden1_0531 change;
- no daily signal or execution-plan change.

## When To Reopen

Only reopen this paper if at least one of the following changes:

- 00631L/00632R AUM or turnover rises by roughly an order of magnitude relative
  to TSMC/0050 liquidity;
- TWSE closing-auction-level data becomes available;
- reliable 00631L/00632R AUM/NAV/rebalancing-capital data becomes available;
- a new Taiwan single-stock leveraged ETF exists on TSMC or another dominant
  Taiwan index constituent.

Until then, further tests are likely redundant.
