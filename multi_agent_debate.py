"""
multi_agent_debate.py
=====================
Research → Battle 雙環境辯論引擎（FinGenius 架構移植）
用於 Group A+ regime switch 決策：Golden ↔ Defensive

每個交易日，3 個專家 Agent 根據晶片、風控、技術數據進行結構化辯論，
最終投票決定是否切換 regime。

辯論流程：
  1. 各 Agent 根據自己的專業領域，分析 features 並發言
  2. 累積上下文傳遞（每個發言者都能看到前面的發言）
  3. 每輪結束後投票（可改票）
  4. 多數決（2/3 票）決定是否切換
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VoteOption(str, Enum):
    """辯論投票選項"""
    SWITCH = "switch"       # 建議切換 regime
    HOLD = "hold"           # 建議維持現有 regime
    ABSTAIN = "abstain"     # 棄權（資訊不足）


@dataclass
class DebateTurn:
    """單次發言"""
    agent: str
    content: str
    vote: VoteOption | None = None
    round: int = 0


@dataclass
class DebateState:
    """辯論狀態追蹤"""
    votes: dict[str, VoteOption] = field(default_factory=dict)
    round_votes: dict[int, dict[str, VoteOption]] = field(default_factory=dict)
    history: list[DebateTurn] = field(default_factory=list)
    terminated: set[str] = field(default_factory=set)
    current_round: int = 0

    def record_vote(self, agent: str, vote: VoteOption, round_num: int) -> None:
        self.votes[agent] = vote
        if round_num not in self.round_votes:
            self.round_votes[round_num] = {}
        self.round_votes[round_num][agent] = vote

    def final_result(self) -> tuple[VoteOption, dict[str, int]]:
        """計算最終投票結果"""
        counts: dict[VoteOption, int] = {v: 0 for v in VoteOption}
        for v in self.votes.values():
            if v != VoteOption.ABSTAIN:
                counts[v] += 1
        winner = max(counts, key=counts.get)
        return winner, counts  # type: ignore


# ─────────────────────────────────────────────
# 專家 Agent 提示詞
# ─────────────────────────────────────────────

CHIP_AGENT_PROMPT = """你是一位專業的晶片分析師，專精於機構動向、散戶情緒、融資融券、主力分點行為。

你的任務：根據以下晶片 sub-features，分析目前是否應該切換 regime。

晶片子指標說明：
- inst_0050_5d：投信 0050 5日淨買（負=賣出，風險）
- foreign_0050_5d：外資 0050 5日淨買（負=賣出，風險）
- margin_0050_balance_chg_5d：融資餘額 5日變化（正+價格跌=風險）
- market_margin_balance_chg_5d：整體融資餘額變化（正+價格跌=風險）
- tdcc_minority_chg_1w：TDCC 散戶持股 1週變化（正=散戶加碼）
- tdcc_major_chg_1w：TDCC 主力持股 1週變化（負=主力減碼）
- foreign_shareholding_ratio_chg_5d：外資持股比率 5日變化（負=賣出）
- short_margin_balance_chg_5d：融券餘額 5日變化（正=看空）
- short_sbl_balance_chg_5d：借券餘額 5日變化（正=借券賣出增加）
- securities_lending_volume_5d：融券成交量 5日均值（高=借券壓力大）
- day_trade_volume_5d：當日沖銷量 5日均值（高=散戶短線活躍）
- dealer_tx_volume_5d：期貨自營商交易量 5日均值
- dealer_txo_volume_5d：選擇權自營商交易量 5日均值

晶片風險評估方法：
- 機構（投信/外資）持續賣出 → 強烈建議切換防守
- 散戶（融資/融券/借券）大幅增加 + 價格下跌 → 建議切換防守
- 主力減碼 + 散戶加碼 → 強烈建議切換防守
- 所有指標穩定 → 建議維持

分析格式：
1. 列出關鍵異常指標（偏離正常範圍的）
2. 說明這些指標的綜合意涵
3. 明確表態：建議 switch（切換）或 hold（維持）
4. 說明信心程度：高 / 中 / 低

請用繁體中文回答。"""


RISK_AGENT_PROMPT = """你是一位專業的衍生性商品風控分析師，專精於期貨選擇權、未平倉量、外資期權部位。

你的任務：根據以下衍生性商品 sub-features，分析目前是否應該切換 regime。

衍生性商品子指標說明：
- tx_foreign_net_oi：TX 期貨外資未平倉淨口數（負=淨空單）
- tx_foreign_net_oi_chg_5d：TX 期貨外資 5日OI變化（負=持續加碼空單）
- txo_foreign_call_net_oi：TXO 選擇權外資買權未平倉（正=樂觀）
- txo_foreign_put_net_oi：TXO 選擇權外資賣權未平倉（正=避險需求）
- txo_put_call_net_oi：TXO 外資 賣權-買權 淨OI（正=偏空）
- txo_put_call_net_oi_chg_5d：TXO 5日 賣權-買權 淨OI變化（正=偏空加劇）

風控評估方法：
- 外資在 TX 持續加碼空單（OI 負且越來越負）→ 強烈建議切換防守
- TXO 賣權 OI > 買權 OI（put/call > 0）且持續擴大 → 建議切換防守
- 兩者同時滿足 → 強化防守信號
- 指標穩定或好轉 → 建議維持

分析格式：
1. 列出關鍵異常指標
2. 說明這些指標的綜合意涵
3. 明確表態：建議 switch 或 hold
4. 說明信心程度：高 / 中 / 低

請用繁體中文回答。"""


TECH_AGENT_PROMPT = """你是一位專業的技術分析師，專精於均線、動能、乖離率、乖離等技術指標。

你的任務：根據以下技術 sub-features，分析目前是否應該切換 regime。

技術子指標說明：
- ma_gap：0050 現價 / MA20 - 1（正=價格在均線上方，負=跌破均線）
- drawdown：從近期高點的回撤幅度（負=正在回撤）
- exit_momentum：5日動能（正=近期上漲，負=近期下跌）
- 0050_close：0050 最新收盤價

技術評估方法：
- ma_gap < -2%：價格大幅低於均線 → 建議切換防守
- ma_gap < -1% + drawdown < -5%：價格跌破均線且從高點回撤 > 5% → 建議切換防守
- ma_gap > +1% + exit_momentum > 0%：價格在均線上方且動能正向 → 建議維持或切換进攻
- ma_gap 在 -1% ~ +1% 之間：中性觀望

分析格式：
1. 列出關鍵技術訊號
2. 說明這些訊號的綜合意涵
3. 明確表態：建議 switch 或 hold
4. 說明信心程度：高 / 中 / 低

請用繁體中文回答。"""


BATTLE_INSTRUCTIONS = """你正在參與一場關於「是否應該切換 regime」的辯論。

規則：
1. 你必須基於前面專家的發言，給出你的觀點（支持或反對切換）
2. 引用具體數據來支持你的立場
3. 回應前面專家的觀點（可以支持或反駁）
4. 發言後明確說出你的投票：switch / hold / abstain
5. 你可以在每輪改票，以最後一次投票為準

重要：不要做深度分析，直接基於數據表態！"""


# ─────────────────────────────────────────────
# Agent 類別
# ─────────────────────────────────────────────

class ChipAgent:
    """晶片分析 Agent"""
    name = "chip_agent"
    prompt = CHIP_AGENT_PROMPT

    @staticmethod
    def analyze(features: dict[str, float]) -> str:
        keys = [
            "inst_0050_5d", "foreign_0050_5d",
            "margin_0050_balance_chg_5d", "market_margin_balance_chg_5d",
            "tdcc_0050_minority_chg_1w", "tdcc_0050_major_chg_1w",
            "foreign_shareholding_0050_ratio_chg_5d",
            "short_0050_margin_balance_chg_5d", "short_0050_sbl_balance_chg_5d",
            "securities_lending_0050_volume_5d",
            "day_trade_0050_volume_5d",
            "dealer_tx_volume_5d", "dealer_txo_volume_5d",
        ]
        lines = [f"## 晶片分析師分析"]
        lines.append(f"日期：{features.get('date', 'N/A')}")
        lines.append("")
        for k in keys:
            v = features.get(k, 0.0)
            lines.append(f"- {k}: {v:,.0f}")

        # 簡單邏輯評估
        risk_count = 0
        if features.get("inst_0050_5d", 0) < 0: risk_count += 1
        if features.get("foreign_0050_5d", 0) < 0: risk_count += 1
        if features.get("margin_0050_balance_chg_5d", 0) > 0 and features.get("price_5d", 0) < 0: risk_count += 1
        if features.get("tdcc_0050_major_chg_1w", 0) < 0: risk_count += 1
        if features.get("foreign_shareholding_0050_ratio_chg_5d", 0) < 0: risk_count += 1
        if features.get("short_0050_margin_balance_chg_5d", 0) > 0: risk_count += 1
        if features.get("short_0050_sbl_balance_chg_5d", 0) > 0: risk_count += 1

        lines.append("")
        if risk_count >= 4:
            lines.append(f"**結論：建議 SWITCH（{risk_count}/7 項晶片指標惡化）**")
        elif risk_count >= 2:
            lines.append(f"**結論：建議 HOLD（{risk_count}/7 項指標值得關注）**")
        else:
            lines.append(f"**結論：建議 HOLD（{risk_count}/7 項指標穩定）**")

        return "\n".join(lines)


class RiskAgent:
    """衍生性商品風控 Agent"""
    name = "risk_agent"
    prompt = RISK_AGENT_PROMPT

    @staticmethod
    def analyze(features: dict[str, float]) -> str:
        keys = [
            "tx_foreign_net_oi", "tx_foreign_net_oi_chg_5d",
            "txo_foreign_call_net_oi", "txo_foreign_put_net_oi",
            "txo_foreign_put_call_net_oi", "txo_foreign_put_call_net_oi_chg_5d",
        ]
        lines = [f"## 風控分析師分析"]
        lines.append(f"日期：{features.get('date', 'N/A')}")
        lines.append("")
        for k in keys:
            v = features.get(k, 0.0)
            lines.append(f"- {k}: {v:,.0f}")

        risk_count = 0
        if features.get("tx_foreign_net_oi", 0) < 0: risk_count += 1
        if features.get("tx_foreign_net_oi_chg_5d", 0) < 0: risk_count += 1
        if features.get("txo_foreign_put_call_net_oi", 0) > 0: risk_count += 1
        if features.get("txo_foreign_put_call_net_oi_chg_5d", 0) > 0: risk_count += 1

        lines.append("")
        if risk_count >= 3:
            lines.append(f"**結論：建議 SWITCH（{risk_count}/4 項風控指標惡化）**")
        elif risk_count >= 2:
            lines.append(f"**結論：建議 HOLD（{risk_count}/4 項指標值得關注）**")
        else:
            lines.append(f"**結論：建議 HOLD（{risk_count}/4 項指標穩定）**")

        return "\n".join(lines)


class TechnicalAgent:
    """技術分析 Agent"""
    name = "technical_agent"
    prompt = TECH_AGENT_PROMPT

    @staticmethod
    def analyze(features: dict[str, float]) -> str:
        ma_gap = features.get("ma_gap", 0.0)
        drawdown = features.get("drawdown", 0.0)
        momentum = features.get("exit_momentum", 0.0)
        close = features.get("0050_close", 0.0)

        lines = [f"## 技術分析師分析"]
        lines.append(f"日期：{features.get('date', 'N/A')}")
        lines.append("")
        lines.append(f"- 0050 收盤價：{close:.2f}")
        lines.append(f"- MA20 乖離：{ma_gap*100:.2f}%")
        lines.append(f"- 近期回撤：{drawdown*100:.2f}%")
        lines.append(f"- 5日動能：{momentum*100:.2f}%")
        lines.append("")

        # 技術訊號評估
        if ma_gap < -0.02:
            signal = "SWITCH（價格大幅低於均線）"
        elif ma_gap < -0.01 and drawdown < -0.05:
            signal = "SWITCH（跌破均線且回撤超過5%）"
        elif ma_gap > 0.01 and momentum > 0:
            signal = "HOLD（價格在均線上方且動能正向）"
        else:
            signal = "HOLD（中性技術訊號）"

        lines.append(f"**結論：建議 {signal}**")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# 辯論協調器
# ─────────────────────────────────────────────

class DebateOrchestrator:
    """
    辯論協調器：執行 Research → Battle 流程

    用法：
        features = {...}  # 某日的 regime features
        result = DebateOrchestrator.run(features, current_regime="golden", debate_rounds=2)
        # result: {"decision": "switch"|"hold", "votes": {...}, "debate_log": [...]}
    """

    def __init__(self, model: str = "mini-max", provider: str = "minimax"):
        self.model = model
        self.provider = provider
        self.state = DebateState()
        self.agents = [ChipAgent(), RiskAgent(), TechnicalAgent()]

    def run(
        self,
        features: dict[str, float],
        current_regime: str = "golden",
        debate_rounds: int = 2,
        use_llm: bool = False,
    ) -> dict[str, Any]:
        """
        執行完整辯論流程

        Args:
            features: 當日的 regime features dict
            current_regime: 目前所處 regime ("golden" 或 "defensive")
            debate_rounds: 辯論輪數（預設2輪）
            use_llm: 是否使用 LLM 生成發言（否則用規則式）

        Returns:
            {
                "decision": "switch" | "hold",
                "votes": {agent_name: vote},
                "vote_counts": {vote_option: count},
                "debate_log": [DebateTurn, ...],
                "chip_vote": str,
                "risk_vote": str,
                "tech_vote": str,
            }
        """
        self.state = DebateState()
        self.state.current_round = 0

        # Research 階段：每個 Agent 分析自己的領域
        analyses: dict[str, str] = {}
        for agent in self.agents:
            analyses[agent.name] = agent.analyze(features)

        # Battle 階段：結構化辯論
        debate_log: list[DebateTurn] = []

        for round_num in range(debate_rounds):
            self.state.current_round = round_num + 1

            for agent in self.agents:
                # 構建累積上下文
                prior = self._build_prior_context(debate_log, analyses, round_num)

                # 發言並投票
                if use_llm:
                    content = self._llm_speak(agent, prior, current_regime)
                else:
                    content = self._rule_based_speak(agent, analyses, prior, current_regime)

                vote = self._extract_vote(content)
                self.state.record_vote(agent.name, vote, round_num + 1)

                turn = DebateTurn(
                    agent=agent.name,
                    content=content,
                    vote=vote,
                    round=round_num + 1,
                )
                self.state.history.append(turn)
                debate_log.append(turn)

        # 最終決策：多數決（排除 abstain）
        decision, counts = self.state.final_result()

        return {
            "decision": decision.value if decision else "hold",
            "votes": {k: v.value for k, v in self.state.votes.items()},
            "vote_counts": {k.value: v for k, v in counts.items()},
            "debate_log": [
                {"agent": t.agent, "content": t.content, "vote": t.vote.value if t.vote else None, "round": t.round}
                for t in debate_log
            ],
            "chip_vote": self.state.votes.get("chip_agent", VoteOption.HOLD).value,
            "risk_vote": self.state.votes.get("risk_agent", VoteOption.HOLD).value,
            "tech_vote": self.state.votes.get("technical_agent", VoteOption.HOLD).value,
        }

    def _build_prior_context(
        self,
        debate_log: list[DebateTurn],
        analyses: dict[str, str],
        current_round: int,
    ) -> str:
        """構建前面發言的累積上下文"""
        parts = ["# 前面專家的分析與發言：\n"]
        for turn in debate_log:
            if turn.round <= current_round:
                parts.append(f"**【{turn.agent}】**（第{turn.round}輪）")
                parts.append(turn.content[:300])
                if turn.vote:
                    parts.append(f"→ 投票：{turn.vote.value}")
                parts.append("")
        return "\n".join(parts)

    def _rule_based_speak(
        self,
        agent,
        analyses: dict[str, str],
        prior_context: str,
        current_regime: str,
    ) -> str:
        """規則式發言（不依賴 LLM）"""
        own_analysis = analyses.get(agent.name, "")

        # 根據不同 Agent 給出不同側重點的發言
        if agent.name == "chip_agent":
            content = own_analysis
        elif agent.name == "risk_agent":
            content = own_analysis
        else:
            content = own_analysis

        # 加入對前面發言的回應
        prior_lines = prior_context.split("\n")
        other_agents = [a for a in ["chip_agent", "risk_agent", "technical_agent"] if a != agent.name]
        mentioned = []
        for line in prior_lines:
            for other in other_agents:
                if other in line and other not in mentioned:
                    mentioned.append(other)

        if mentioned:
            content += f"\n\n我注意到前面 {', '.join(mentioned)} 的分析，這與我的判斷一致/有出入。"

        return content

    def _llm_speak(
        self,
        agent,
        prior_context: str,
        current_regime: str,
    ) -> str:
        """使用 LLM 生成發言（需要 LLM API）"""
        # 預留介面，暫時用規則式
        return self._rule_based_speak(agent, {}, prior_context, current_regime)

    def _extract_vote(self, content: str) -> VoteOption:
        """從發言內容中提取投票"""
        content_lower = content.lower()
        if "switch" in content_lower and ("建議 switch" in content_lower or "**結論：建議 switch" in content_lower):
            return VoteOption.SWITCH
        elif "abstain" in content_lower:
            return VoteOption.ABSTAIN
        else:
            return VoteOption.HOLD


# ─────────────────────────────────────────────
# 便利函數
# ─────────────────────────────────────────────

def decide_with_debate(
    features: dict[str, float],
    current_regime: str = "golden",
    debate_rounds: int = 2,
) -> dict[str, Any]:
    """
    單一函數介面：傳入 features，直接得到辯論結果

    Args:
        features: regime features dict（與 backtest 的 _regime_features 輸出相同格式）
        current_regime: 目前 regime
        debate_rounds: 辯論輪數

    Returns:
        {
            "decision": "switch" | "hold",
            "chip_vote": str,
            "risk_vote": str,
            "tech_vote": str,
            "vote_counts": dict,
        }
    """
    orchestrator = DebateOrchestrator()
    return orchestrator.run(
        features=features,
        current_regime=current_regime,
        debate_rounds=debate_rounds,
        use_llm=False,
    )


if __name__ == "__main__":
    # 簡單測試
    import datetime

    mock_features = {
        "date": "2026-06-12",
        "0050_close": 232.85,
        "ma_gap": 0.0101,
        "drawdown": -0.0525,
        "exit_momentum": -0.0211,
        "inst_0050_5d": -200_483_722.0,
        "foreign_0050_5d": -113_325_019.0,
        "margin_0050_balance_chg_5d": 1749.0,
        "market_margin_balance_chg_5d": -223_031.0,
        "tdcc_0050_minority_chg_1w": 0.07,
        "tdcc_0050_major_chg_1w": -0.07,
        "foreign_shareholding_0050_ratio_chg_5d": 1.31,
        "short_0050_margin_balance_chg_5d": -321_000.0,
        "short_0050_sbl_balance_chg_5d": 44_281_000.0,
        "securities_lending_0050_volume_5d": 213_484.0,
        "day_trade_0050_volume_5d": 0.0,
        "dealer_tx_volume_5d": 974_348.0,
        "dealer_txo_volume_5d": 3_699_278.0,
        "tx_foreign_net_oi": -65_039.0,
        "tx_foreign_net_oi_chg_5d": 4107.0,
        "txo_foreign_call_net_oi": 2347.0,
        "txo_foreign_put_net_oi": 5948.0,
        "txo_foreign_put_call_net_oi": 3601.0,
        "txo_foreign_put_call_net_oi_chg_5d": -476.0,
        "price_5d": -0.0211,
    }

    result = decide_with_debate(mock_features, current_regime="defensive", debate_rounds=2)
    print("=== 辯論結果 ===")
    print(f"決策：{result['decision']}")
    print(f"晶片 Agent 投票：{result['chip_vote']}")
    print(f"風控 Agent 投票：{result['risk_vote']}")
    print(f"技術 Agent 投票：{result['tech_vote']}")
    print(f"投票統計：{result['vote_counts']}")
    print()
    print("=== 辯論過程 ===")
    for turn in result["debate_log"]:
        print(f"[Round {turn['round']}] {turn['agent']}: {turn['content'][:200]}...")
        print(f"  → 投票：{turn['vote']}")
        print()
