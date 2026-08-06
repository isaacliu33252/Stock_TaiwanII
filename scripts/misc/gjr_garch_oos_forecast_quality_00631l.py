#!/usr/bin/env python3
"""OOS test: does 00631L.TW's confirmed GJR-GARCH asymmetry (gamma=0.178,
p<0.0001, see scripts/misc/gjr_garch_asymmetry_test.py) translate into
better out-of-sample volatility forecasts than the symmetric GARCH proxy
garch_regime_shadow.py currently uses?

In-sample significance (does the full-history MLE prefer gamma != 0) and
out-of-sample forecast value (does that extra parameter actually reduce
forecast error on data it hasn't seen) are different questions -- an
asymmetric term can be a statistically real feature of the historical
sample while still overfitting one-step-ahead forecasts if re-estimated too
infrequently or too noisily. This uses the same QLIKE loss + Diebold-Mariano
test methodology already established in this repo for volatility-forecast
comparisons (group_a_plus/integrations/risk_sensitive_loss.py, used for
GNHAR per arXiv:2606.03828 Section 5.4 -- see
scripts/evaluate/evaluate_group_a_plus_network_volatility_forecast_quality.py).

Rolling design: re-estimate both models' (omega, alpha, [gamma,] beta, mu)
every 21 trading days (matching this repo's other rolling-reestimation
scripts) on a trailing 504-day (~2y) window; the variance *state* itself is
carried forward continuously across refits (not reset), so this mimics a
live system that periodically recalibrates parameters while continuously
tracking conditional variance.

Does not modify garch_regime_shadow.py or any production file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.risk_sensitive_loss import diebold_mariano_test, qlike_loss  # noqa: E402
from scripts.misc.gjr_garch_asymmetry_test import _fit, _load_returns  # noqa: E402

TICKER = "00631L.TW"
START, END = "2014-10-23", "2026-07-31"
TRAIN_WINDOW = 504
MIN_TRAIN = 252
REFIT_EVERY = 21


def _rolling_forecasts(returns: pd.Series) -> pd.DataFrame:
    resid = returns.to_numpy(dtype=float)
    n = len(resid)

    sym_forecast_var = np.full(n, np.nan)
    gjr_forecast_var = np.full(n, np.nan)

    sym_params: dict[str, float] | None = None
    gjr_params: dict[str, float] | None = None
    sym_var_state: float | None = None
    gjr_var_state: float | None = None
    n_refits = 0

    for t in range(MIN_TRAIN, n):
        if (t - MIN_TRAIN) % REFIT_EVERY == 0:
            train = resid[max(0, t - TRAIN_WINDOW) : t]
            sym_params = _fit(train, asymmetric=False)["params"]
            gjr_params = _fit(train, asymmetric=True)["params"]
            n_refits += 1
            if sym_var_state is None:
                sym_var_state = float(np.var(train))
                gjr_var_state = float(np.var(train))

        prev = resid[t - 1]
        sym_eps = prev - sym_params["mu"]
        gjr_eps = prev - gjr_params["mu"]
        neg_flag = 1.0 if gjr_eps < 0.0 else 0.0

        sym_next = sym_params["omega"] + sym_params["alpha"] * sym_eps**2 + sym_params["beta"] * sym_var_state
        gjr_next = (
            gjr_params["omega"]
            + gjr_params["alpha"] * gjr_eps**2
            + gjr_params["gamma"] * neg_flag * gjr_eps**2
            + gjr_params["beta"] * gjr_var_state
        )
        sym_forecast_var[t] = sym_next
        gjr_forecast_var[t] = gjr_next
        sym_var_state = sym_next
        gjr_var_state = gjr_next

    print(f"  n_refits={n_refits}")
    return pd.DataFrame(
        {
            "return": returns,
            "realized_var": returns.to_numpy(dtype=float) ** 2,
            "sym_forecast_var": sym_forecast_var,
            "gjr_forecast_var": gjr_forecast_var,
        },
        index=returns.index,
    )


def main() -> None:
    returns = _load_returns(TICKER, START, END)
    print(f"Rolling OOS forecast: {TICKER} ({returns.index.min().date()} ~ {returns.index.max().date()}, n={len(returns)})")
    frame = _rolling_forecasts(returns)
    frame = frame.dropna(subset=["sym_forecast_var", "gjr_forecast_var"])

    sym_loss = qlike_loss(frame["realized_var"], frame["sym_forecast_var"])
    gjr_loss = qlike_loss(frame["realized_var"], frame["gjr_forecast_var"])

    overall_dm = diebold_mariano_test(gjr_loss, sym_loss, h=1)

    high_vol_threshold = frame["realized_var"].quantile(0.90)
    high_vol_mask = frame["realized_var"] >= high_vol_threshold
    high_vol_dm = diebold_mariano_test(gjr_loss[high_vol_mask], sym_loss[high_vol_mask], h=1)

    result = {
        "ticker": TICKER,
        "window": {"start": str(frame.index.min().date()), "end": str(frame.index.max().date()), "n": len(frame)},
        "train_window": TRAIN_WINDOW,
        "refit_every": REFIT_EVERY,
        "sym_qlike_mean": float(sym_loss.mean()),
        "gjr_qlike_mean": float(gjr_loss.mean()),
        "overall_diebold_mariano": overall_dm,
        "high_vol_days": {
            "threshold_realized_var_p90": float(high_vol_threshold),
            "n_days": int(high_vol_mask.sum()),
            "sym_qlike_mean": float(sym_loss[high_vol_mask].mean()),
            "gjr_qlike_mean": float(gjr_loss[high_vol_mask].mean()),
            "diebold_mariano": high_vol_dm,
        },
    }

    out_path = PROJECT_ROOT / "results" / "gjr_garch_oos_forecast_quality_00631l_20260801.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nSaved: {out_path}")
    print(f"\nOverall QLIKE:   sym={result['sym_qlike_mean']:.4f}  gjr={result['gjr_qlike_mean']:.4f}")
    print(f"  DM test (gjr vs sym): {overall_dm}")
    hv = result["high_vol_days"]
    print(f"\nHigh-vol days (n={hv['n_days']}, top 10% realized var):")
    print(f"  QLIKE: sym={hv['sym_qlike_mean']:.4f}  gjr={hv['gjr_qlike_mean']:.4f}")
    print(f"  DM test (gjr vs sym): {hv['diebold_mariano']}")


if __name__ == "__main__":
    main()
