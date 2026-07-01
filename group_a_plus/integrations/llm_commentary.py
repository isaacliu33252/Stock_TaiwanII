"""Commentary layer for Group A+ daily signal.

Supports two modes:
  - template  (default, no API key needed): rule-based structured commentary
  - llm       (requires ANTHROPIC_API_KEY): Claude-generated natural language

Usage
-----
    from group_a_plus.integrations.llm_commentary import generate_commentary

    # template mode (no API key)
    report = generate_commentary(
        ncf_signal_path="results/ncf_00631l_latest_YYYYMMDD.json",
    )

    # llm mode
    report = generate_commentary(
        ncf_signal_path="results/ncf_00631l_latest_YYYYMMDD.json",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-haiku-4-5-20251001",
    )

Output schema (CommentaryReport)
---------------------------------
{
  "date": "YYYY-MM-DD",
  "mode": "template | llm",
  "headline": "一句話摘要",
  "market_pulse": "2-3 句台灣市場環境描述",
  "signal_interpretation": {
    "h1_note": "H=1 機率解讀",
    "h5_note": "H=5 機率解讀",
    "h20_note": "H=20 機率解讀（觸發依據）",
    "deleverage_status": "ACTIVE | INACTIVE"
  },
  "risk_alerts": ["最多 3 個具體風險"],
  "positive_catalysts": ["最多 3 個潛在利多"],
  "action_today": "今日操作建議 1-2 句",
  "watch_levels": {
    "ncf_h20_reentry": "h20 ≥ X.XX 可考慮解除去槓桿",
    "ncf_conf_floor": "信心值跌破 X.XX 則信號可靠度下降"
  }
}

Notes
-----
- Commentary only — never overrides quantitative decisions.
- Output saved to report/group_a_plus/latest/commentary_YYYYMMDD.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date as _date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_DELEVERAGE_H20_THRESHOLD = 0.35
_DELEVERAGE_CONF_THRESHOLD = 0.55
_DEFAULT_NEWS_LOOKBACK_DAYS = 7


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_ncf_context(ncf_data: dict[str, Any]) -> dict[str, Any]:
    """Pull the key numbers from ncf_00631l_latest_*.json into a flat dict."""
    horizons = ncf_data.get("horizons", {})
    ensemble = ncf_data.get("horizon_ensemble", {})

    h1 = horizons.get("1", {}).get("classification", {})
    h5 = horizons.get("5", {}).get("classification", {})
    h20 = horizons.get("20", {}).get("classification", {})

    h20_prob = h20.get("probability_up", 0.5)
    conf = ensemble.get("confidence", 0.0)
    deleverage_active = (h20_prob < _DELEVERAGE_H20_THRESHOLD) and (conf > _DELEVERAGE_CONF_THRESHOLD)

    # Top 3 feature importances (H=20 best model, if present)
    fi = ncf_data.get("feature_importance_top10", [])
    top_features = [f.get("feature", "?") for f in fi[:3]] if fi else []

    return {
        "ticker": ncf_data.get("ticker", "00631L.TW"),
        "last_close_date": ncf_data.get("last_close_date", "?"),
        "last_close": ncf_data.get("last_close", 0),
        "regime": ncf_data.get("current_regime", "BULL"),
        "h1_prob_up": round(h1.get("probability_up", 0.5), 4),
        "h1_direction": h1.get("direction", "?"),
        "h5_prob_up": round(h5.get("probability_up", 0.5), 4),
        "h5_direction": h5.get("direction", "?"),
        "h20_prob_up": round(h20_prob, 4),
        "h20_direction": h20.get("direction", "?"),
        "calibrated_prob_up": round(ensemble.get("calibrated_probability_up", 0.5), 4),
        "confidence": round(conf, 4),
        "ensemble_direction": ensemble.get("direction", "?"),
        "votes_up": ensemble.get("votes_up", 0),
        "deleverage_active": deleverage_active,
        "h20_threshold": _DELEVERAGE_H20_THRESHOLD,
        "conf_threshold": _DELEVERAGE_CONF_THRESHOLD,
        "top_features": top_features,
    }


def _build_prompt(ctx: dict[str, Any], signal_date: str) -> str:
    """Build the user message for the commentary generation call."""
    deleverage_str = "**已觸發（ACTIVE）**" if ctx["deleverage_active"] else "未觸發（INACTIVE）"

    feature_str = (
        "、".join(ctx["top_features"]) if ctx["top_features"] else "（本次無特徵重要性資料）"
    )

    return f"""
你是台股量化策略 Group A+ 的每日信號解說員。請根據以下 NCF 模型量化數據，
用繁體中文生成今日市場評述，輸出純 JSON（不加任何 markdown）。

=== NCF 信號快照（{signal_date}）===
標的：{ctx['ticker']}（二倍做多台股 ETF）
收盤價（{ctx['last_close_date']}）：{ctx['last_close']} TWD
市場 Regime：{ctx['regime']}

預測機率（prob_up = 未來上漲機率）：
  H=1  (隔日)：{ctx['h1_prob_up']:.4f}  → {ctx['h1_direction']}
  H=5  (5日)：{ctx['h5_prob_up']:.4f}  → {ctx['h5_direction']}
  H=20 (20日)：{ctx['h20_prob_up']:.4f}  → {ctx['h20_direction']}  ← 主要觸發指標（閾值 {ctx['h20_threshold']}）

加權 calibrated prob_up：{ctx['calibrated_prob_up']:.4f}
信心值（confidence）：{ctx['confidence']:.4f}（門檻 {ctx['conf_threshold']}）
去槓桿觸發：{deleverage_str}
頂部特徵：{feature_str}

=== 去槓桿規則說明 ===
觸發條件：H=20 prob_up < {ctx['h20_threshold']} AND confidence > {ctx['conf_threshold']}
觸發後配置：0050 ~75%、00631L ~5%、現金 ~20%（降低槓桿曝險）
解除條件：H=20 prob_up 回升至 ≥ 0.40

=== 輸出格式（嚴格遵守，純 JSON）===
{{
  "date": "{signal_date}",
  "headline": "一句話摘要（20字內）",
  "market_pulse": "2-3 句台灣股市當前環境描述（根據信號解讀）",
  "signal_interpretation": {{
    "h1_note": "H=1 機率 {ctx['h1_prob_up']} 的意義（1句）",
    "h5_note": "H=5 機率 {ctx['h5_prob_up']} 的意義（1句）",
    "h20_note": "H=20 機率 {ctx['h20_prob_up']} 的意義及與閾值 {ctx['h20_threshold']} 的關係（1-2句）",
    "deleverage_status": "{('ACTIVE' if ctx['deleverage_active'] else 'INACTIVE')}"
  }},
  "risk_alerts": ["具體風險1（基於信號）", "具體風險2", "具體風險3（最多3項）"],
  "positive_catalysts": ["潛在利多1", "潛在利多2（最多3項，可少於3）"],
  "action_today": "今日操作建議 1-2 句（說明應維持/調整倉位）",
  "watch_levels": {{
    "ncf_h20_reentry": "h20 ≥ X.XX 時可考慮解除去槓桿",
    "ncf_conf_floor": "信心值低於 X.XX 時信號可靠度下降，需謹慎"
  }}
}}
"""


def _strip_code_fences(raw: str) -> str:
    """Remove accidental markdown code fences from LLM JSON output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")].strip()
    return raw


def _call_claude(prompt: str, api_key: str, model: str) -> dict[str, Any]:
    """Call the Anthropic API and parse the JSON response."""
    try:
        import anthropic  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "anthropic SDK not installed. Run: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=(
            "你是台股量化策略分析師助手。你的輸出必須是純 JSON，"
            "不加任何說明文字、markdown 符號或程式碼區塊標記。"
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    return json.loads(_strip_code_fences(response.content[0].text))


_MINIMAX_DEFAULT_MODEL = "MiniMax-Text-01"
_MINIMAX_BASE_URL = "https://api.minimax.io/v1/chat/completions"


def _call_minimax(prompt: str, api_key: str, model: str) -> dict[str, Any]:
    """Call the MiniMax API (OpenAI-compatible) and parse the JSON response."""
    import requests  # already a project dependency

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是台股量化策略分析師助手。你的輸出必須是純 JSON，"
                    "不加任何說明文字、markdown 符號或程式碼區塊標記。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    resp = requests.post(_MINIMAX_BASE_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    return json.loads(_strip_code_fences(raw))


# ---------------------------------------------------------------------------
# Template engine (no API key needed)
# ---------------------------------------------------------------------------

def _prob_label(prob: float) -> str:
    """Map probability to a short Chinese label."""
    if prob < 0.30:
        return "強烈看跌"
    if prob < 0.40:
        return "偏空"
    if prob < 0.48:
        return "略偏空"
    if prob < 0.52:
        return "中性"
    if prob < 0.62:
        return "略偏多"
    if prob < 0.70:
        return "偏多"
    return "強烈看多"


def _generate_template_commentary(
    ctx: dict[str, Any], signal_date: str
) -> dict[str, Any]:
    """Build a structured commentary dict from NCF context using rule-based templates."""
    h1 = ctx["h1_prob_up"]
    h5 = ctx["h5_prob_up"]
    h20 = ctx["h20_prob_up"]
    conf = ctx["confidence"]
    deleverage = ctx["deleverage_active"]
    thr = ctx["h20_threshold"]
    conf_thr = ctx["conf_threshold"]
    ticker = ctx["ticker"]
    last_close = ctx["last_close"]
    last_close_date = ctx["last_close_date"]
    regime = ctx["regime"]

    # ---- headline ----
    all_down = h1 < 0.5 and h5 < 0.5 and h20 < 0.5
    if deleverage and all_down:
        headline = "NCF 三期全面看空，去槓桿已觸發"
    elif deleverage:
        headline = "NCF 中長期看空，去槓桿已觸發"
    elif h20 >= 0.55 and h5 >= 0.50:
        headline = "NCF 中長期偏多，維持標準配置"
    elif h20 >= thr:
        headline = f"NCF H=20 機率 {h20:.3f}，維持觀察（未觸發去槓桿）"
    else:
        headline = f"NCF H=20 機率 {h20:.3f}，低於閾值但信心不足以觸發"

    # ---- market pulse ----
    if h20 < 0.28:
        pulse_base = f"台灣股市中長期動能明顯偏空，NCF H=20 機率僅 {h20:.3f}，" \
                     f"顯示未來 20 日下行壓力較大。"
    elif h20 < thr:
        pulse_base = f"台灣股市中期展望偏空，NCF H=20 機率 {h20:.3f} 低於 {thr} 觸發閾值，" \
                     f"中期上行動能受壓。"
    elif h20 < 0.45:
        pulse_base = f"台灣股市短期不確定性偏高，NCF H=20 機率 {h20:.3f} 接近中性偏空，" \
                     f"尚未觸發去槓桿但需持續觀察。"
    elif h20 < 0.55:
        pulse_base = f"台灣股市維持中性格局，NCF H=20 機率 {h20:.3f}，" \
                     f"多空拉鋸，建議維持現有配置。"
    else:
        pulse_base = f"台灣股市中期偏多，NCF H=20 機率 {h20:.3f}，" \
                     f"上行動能充足，維持標準槓桿配置。"

    # add h5 colour
    h5_label = _prob_label(h5)
    if h5 < 0.45:
        pulse_extra = f"H=5 機率 {h5:.3f}（{h5_label}），本週走勢偏空。"
    elif h5 > 0.55:
        pulse_extra = f"H=5 機率 {h5:.3f}（{h5_label}），本週走勢偏多。"
    else:
        pulse_extra = f"H=5 機率 {h5:.3f}（{h5_label}），短期走勢不明確。"

    market_pulse = f"{pulse_base}{pulse_extra}"

    # ---- signal interpretation ----
    h1_note = f"隔日機率 {h1:.4f}（{_prob_label(h1)}），{'明日可能承壓' if h1 < 0.45 else '明日方向不明' if h1 < 0.55 else '明日偏多'}。"
    h5_note = f"5 日機率 {h5:.4f}（{_prob_label(h5)}），{'本週整體偏空' if h5 < 0.45 else '本週持平' if h5 < 0.55 else '本週偏多'}。"
    if h20 < thr:
        h20_note = (
            f"20 日機率 {h20:.4f} 低於觸發閾值 {thr}，且信心值 {conf:.4f} > {conf_thr}，"
            f"去槓桿條件{'已滿足，觸發 ACTIVE' if deleverage else '部分滿足'}。"
        )
    else:
        h20_note = (
            f"20 日機率 {h20:.4f} 高於觸發閾值 {thr}，去槓桿條件未達成，"
            f"維持{'標準' if h20 >= 0.50 else '觀察'}配置。"
        )

    # ---- risk alerts ----
    risks: list[str] = []
    if h20 < 0.30:
        risks.append(f"H=20 機率 {h20:.3f} 遠低於 {thr}，中期下行風險顯著")
    elif h20 < thr:
        risks.append(f"H=20 機率 {h20:.3f} 低於觸發閾值 {thr}，中期偏空壓力持續")
    if h5 < 0.40:
        risks.append(f"H=5 機率 {h5:.3f}，本週走勢明顯偏空")
    elif h5 < 0.45:
        risks.append(f"H=5 機率 {h5:.3f}，短期下行動能仍在")
    if h1 < 0.42:
        risks.append(f"H=1 機率 {h1:.3f}，隔日可能面臨短線壓力")
    if conf < 0.60:
        risks.append(f"信心值 {conf:.3f} 偏低，信號可靠性下降，請保守看待")
    if not risks:
        risks.append("三期信號均接近中性，方向不明確，建議維持現有配置靜待確認")
    risks = risks[:3]

    # ---- positive catalysts ----
    cats: list[str] = []
    if h20 < thr and h20 >= thr - 0.08:
        cats.append(f"H=20 機率接近 {thr} 附近，若回升至 0.40 以上可考慮解除去槓桿")
    if h1 >= 0.48:
        cats.append(f"H=1 機率 {h1:.3f} 接近中性，短線可能有技術性反彈")
    if conf >= 0.65:
        cats.append(f"信心值 {conf:.3f} 偏高，模型對當前方向判斷一致性強")
    if regime == "BULL":
        cats.append("整體 Regime 仍維持 BULL，大趨勢尚未反轉")
    if not cats:
        cats.append("市場條件尚未出現明確做多信號，建議耐心等待")
    cats = cats[:3]

    # ---- action today ----
    if deleverage:
        action = (
            f"去槓桿已觸發（h20={h20:.3f} < {thr}，conf={conf:.3f} > {conf_thr}），"
            f"維持低槓桿配置（0050 ~75%、00631L ~5%、現金 ~20%）。"
            f"待 H=20 機率回升至 ≥ 0.40 且信心值維持 > {conf_thr} 後再考慮恢復標準配置。"
        )
    elif h20 < thr + 0.05:
        action = (
            f"H=20 機率 {h20:.3f} 接近觸發閾值 {thr}，去槓桿尚未觸發，"
            f"維持現有配置但密切監控。若下一個交易日 h20 跌破 {thr} 且信心 > {conf_thr}，則觸發去槓桿。"
        )
    elif h20 >= 0.55:
        action = (
            f"H=20 機率 {h20:.3f}（{_prob_label(h20)}），中期偏多，"
            f"維持標準配置（0050 60%、00631L 20%、現金 20%）。"
        )
    else:
        action = (
            f"H=20 機率 {h20:.3f}（{_prob_label(h20)}），信號中性，"
            f"維持現有配置，無需調整。"
        )

    # ---- watch levels ----
    watch_levels = {
        "ncf_h20_reentry": f"h20 ≥ 0.40（目前 {h20:.3f}）→ 可考慮解除去槓桿，恢復 00631L 標準配置",
        "ncf_conf_floor": f"信心值跌破 0.50（目前 {conf:.3f}）→ 信號可靠性下降，去槓桿決策參考性降低",
    }

    return {
        "date": signal_date,
        "mode": "template",
        "headline": headline,
        "market_pulse": market_pulse,
        "signal_interpretation": {
            "h1_note": h1_note,
            "h5_note": h5_note,
            "h20_note": h20_note,
            "deleverage_status": "ACTIVE" if deleverage else "INACTIVE",
        },
        "risk_alerts": risks,
        "positive_catalysts": cats,
        "action_today": action,
        "watch_levels": watch_levels,
        "_ncf_snapshot": {
            "ticker": ticker,
            "last_close_date": last_close_date,
            "last_close": last_close,
            "regime": regime,
            "h1_prob_up": h1,
            "h5_prob_up": h5,
            "h20_prob_up": h20,
            "calibrated_prob_up": ctx["calibrated_prob_up"],
            "confidence": conf,
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_commentary(
    ncf_signal_path: str | Path,
    *,
    provider: str = "auto",
    api_key: str | None = None,
    model: str | None = None,
    signal_date: str | None = None,
    save: bool = True,
    output_dir: str | Path = "report/group_a_plus/latest",
    include_watchlist_news: bool = True,
) -> dict[str, Any]:
    """Generate a structured commentary for today's Group A+ signal.

    Parameters
    ----------
    ncf_signal_path:
        Path to ncf_00631l_latest_*.json.
    provider:
        LLM provider — "auto" (default), "minimax", "anthropic", or "template".
        "auto" picks the first available key: MINIMAX_API_KEY → ANTHROPIC_API_KEY → template.
    api_key:
        API key for the selected provider.  Overrides env vars.
    model:
        Model ID override.  Defaults: minimax→MiniMax-Text-01, anthropic→claude-haiku-4-5-20251001.
    signal_date:
        Date label (YYYY-MM-DD).  Defaults to today.
    save:
        Write output JSON to report/group_a_plus/latest/commentary_YYYYMMDD.json.
    output_dir:
        Output directory for the saved JSON file.

    Returns
    -------
    CommentaryReport dict.
    """
    path = Path(ncf_signal_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    with path.open() as f:
        ncf_data = json.load(f)

    today = signal_date or str(_date.today())
    ctx = _extract_ncf_context(ncf_data)

    # --- resolve provider and key ---
    resolved_provider = provider.lower()
    resolved_key = api_key or ""

    if resolved_provider == "auto":
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if minimax_key:
            resolved_provider, resolved_key = "minimax", minimax_key
        elif anthropic_key:
            resolved_provider, resolved_key = "anthropic", anthropic_key
        else:
            resolved_provider = "template"
    elif resolved_provider == "minimax" and not resolved_key:
        resolved_key = os.environ.get("MINIMAX_API_KEY", "")
    elif resolved_provider == "anthropic" and not resolved_key:
        resolved_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # --- dispatch ---
    prompt = _build_prompt(ctx, today)

    if resolved_provider == "minimax":
        effective_model = model or _MINIMAX_DEFAULT_MODEL
        logger.info("Calling MiniMax %s for %s commentary …", effective_model, today)
        try:
            report = _call_minimax(prompt, resolved_key, effective_model)
            report["mode"] = "minimax"
            report["_model"] = effective_model
        except Exception as exc:  # noqa: BLE001
            logger.warning("MiniMax call failed, falling back to template: %s", exc)
            report = _generate_template_commentary(ctx, today)

    elif resolved_provider == "anthropic":
        effective_model = model or _DEFAULT_MODEL
        logger.info("Calling Anthropic %s for %s commentary …", effective_model, today)
        try:
            report = _call_claude(prompt, resolved_key, effective_model)
            report["mode"] = "anthropic"
            report["_model"] = effective_model
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic call failed, falling back to template: %s", exc)
            report = _generate_template_commentary(ctx, today)

    else:
        logger.info("Using template mode for %s commentary", today)
        report = _generate_template_commentary(ctx, today)

    report["_ncf_source"] = str(path.name)

    if include_watchlist_news:
        try:
            from group_a_plus.integrations.watchlist_news import build_watchlist_news_summary

            report["watchlist_news"] = build_watchlist_news_summary(
                signal_date=today,
                lookback_days=_DEFAULT_NEWS_LOOKBACK_DAYS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Watchlist news summary failed: %s", exc)
            report["watchlist_news"] = {
                "status": "unavailable",
                "reason": str(exc),
            }

    try:
        from group_a_plus.integrations.signal_alignment import build_signal_alignment_from_file

        live_signal_path = Path(output_dir) / "live_signal.json"
        if not live_signal_path.is_absolute():
            live_signal_path = Path.cwd() / live_signal_path
        if live_signal_path.exists():
            report["signal_alignment"] = build_signal_alignment_from_file(live_signal_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Signal alignment summary failed: %s", exc)
        report["signal_alignment"] = {
            "status": "unavailable",
            "reason": str(exc),
        }

    if save:
        out_dir = Path(output_dir)
        if not out_dir.is_absolute():
            out_dir = Path.cwd() / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"commentary_{today.replace('-', '')}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("Commentary saved → %s", out_path)
        report["_saved_to"] = str(out_path)

    return report
