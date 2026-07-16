from ncf_2330 import _classify_tsmc_market_state
from ncf_2330 import _add_tsmc_leadership_features

import pandas as pd


def _results(
    *,
    h1_dir="UP",
    h5_dir="UP",
    h20_dir="UP",
    h1_prob=0.55,
    h5_prob=0.60,
    h20_prob=0.68,
    h1_ret=0.001,
    h5_ret=0.004,
    h20_ret=0.010,
):
    return {
        1: {"direction": h1_dir, "ens_proba": h1_prob, "ens_ret": h1_ret},
        5: {"direction": h5_dir, "ens_proba": h5_prob, "ens_ret": h5_ret},
        20: {"direction": h20_dir, "ens_proba": h20_prob, "ens_ret": h20_ret},
    }


def _risk(probability, available=True):
    return {"available": available, "probability": probability}


def _classify(
    all_results,
    *,
    combined_prob=0.62,
    calibrated_prob=0.60,
    confidence=0.55,
    weighted_return=0.008,
    tail5=0.30,
    tail8=0.10,
    upside5=0.50,
):
    return _classify_tsmc_market_state(
        all_results=all_results,
        combined_prob=combined_prob,
        calibrated_prob=calibrated_prob,
        confidence=confidence,
        weighted_return=weighted_return,
        drawdown_risk=_risk(tail5),
        severe_drawdown_risk=_risk(tail8),
        upside_reward=_risk(upside5),
    )


def test_tsmc_market_state_strong_leadership():
    state = _classify(_results())

    assert state["state"] == 1
    assert state["label_zh"] == "強勢領漲"
    assert state["policy"] == "diagnostic_only_no_weight_change"


def test_tsmc_market_state_high_range_matches_latest_smoke_profile():
    state = _classify(
        _results(
            h1_dir="DOWN",
            h5_dir="UP",
            h20_dir="UP",
            h1_prob=0.478,
            h5_prob=0.577,
            h20_prob=0.707,
            h1_ret=-0.0015,
            h5_ret=-0.0004,
            h20_ret=-0.0066,
        ),
        combined_prob=0.623,
        calibrated_prob=0.579,
        confidence=0.49,
        weighted_return=-0.001451,
        tail5=0.364673,
        tail8=0.099838,
        upside5=0.374,
    )

    assert state["state"] == 2
    assert state["label_zh"] == "高檔震盪"
    assert state["inputs"]["prob_fwd_mdd_gt8_h20"] == 0.099838


def test_tsmc_market_state_false_breakout():
    state = _classify(
        _results(h1_dir="DOWN", h5_dir="UP", h20_dir="UP", h1_ret=-0.002),
        calibrated_prob=0.59,
        weighted_return=0.001,
        tail5=0.44,
        tail8=0.18,
        upside5=0.32,
    )

    assert state["state"] == 3
    assert state["label_zh"] == "假突破"


def test_tsmc_market_state_pullback_consolidation():
    state = _classify(
        _results(h1_dir="DOWN", h5_dir="DOWN", h20_dir="UP", h5_ret=-0.004),
        calibrated_prob=0.54,
        weighted_return=-0.002,
        tail5=0.34,
        tail8=0.12,
        upside5=0.42,
    )

    assert state["state"] == 4
    assert state["label_zh"] == "拉回整理"


def test_tsmc_market_state_trend_weakening():
    state = _classify(
        _results(h1_dir="DOWN", h5_dir="DOWN", h20_dir="DOWN", h20_prob=0.44),
        combined_prob=0.45,
        calibrated_prob=0.44,
        confidence=0.52,
        weighted_return=-0.010,
        tail5=0.52,
        tail8=0.24,
        upside5=0.28,
    )

    assert state["state"] == 5
    assert state["label_zh"] == "趨勢轉弱"


def test_tsmc_leadership_score_pre_open_lags_taiwan_close_inputs():
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    tsmc = pd.Series(range(100, 140), index=idx, dtype=float)
    et50 = pd.Series(range(50, 90), index=idx, dtype=float)
    adr = pd.Series(0.01, index=idx, dtype=float)
    soxx = pd.Series(0.02, index=idx, dtype=float)
    peers = pd.Series(0.03, index=idx, dtype=float)
    fx = pd.Series(0.001, index=idx, dtype=float)
    foreign = pd.Series(range(40), index=idx, dtype=float)
    after = pd.DataFrame(index=idx)
    pre = pd.DataFrame(index=idx)

    _add_tsmc_leadership_features(
        after,
        idx,
        tsmc_close=tsmc,
        etf_0050_close=et50,
        adr_fx_ret=adr,
        soxx_ret=soxx,
        peer_semis_ret=peers,
        usdtwd_change=fx,
        inst_foreign_net=foreign,
        feature_mode="after_close",
    )
    _add_tsmc_leadership_features(
        pre,
        idx,
        tsmc_close=tsmc,
        etf_0050_close=et50,
        adr_fx_ret=adr,
        soxx_ret=soxx,
        peer_semis_ret=peers,
        usdtwd_change=fx,
        inst_foreign_net=foreign,
        feature_mode="pre_open",
    )

    assert pre["tsmc_leadership_ret_5d"].iloc[-1] == after["tsmc_leadership_ret_5d"].iloc[-2]
    assert pre["tsmc_leadership_foreign_net"].iloc[-1] == after["tsmc_leadership_foreign_net"].iloc[-2]
    assert pre["tsmc_leadership_adr_overnight"].iloc[-1] == after["tsmc_leadership_adr_overnight"].iloc[-1]
    assert "TSMC_Leadership_Score" in after.columns
