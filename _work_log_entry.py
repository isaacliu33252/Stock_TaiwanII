#!/usr/bin/env python3
"""寫入 2026-06-23 工作日誌至 Notion"""
import subprocess, json, os

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")

content = """【Group A+ / Golden1 每日預測 — 2026-06-23】

■ 資料更新
- refresh_group_data.py → 所有標的更新至 2026-06-22

■ 策略預測（6/23）

Golden1_0531（V9 MA50 hybrid）
- 收盤（6/22）: 41.32, MA200: 20.65, MA50: 32.06
- close > MA50 → V9 規則 target_weight = 100%
- PPO pred_ratio = 0.725（看空），被 V9 規則覆寫
- 結論: 維持 100% 持有 00631L

Group A+（a213_cash30_recovery_ramp）
- regime: risk_on, 00679B_weight: 0%
- signal_status: rebalance（pva_overlay_j; trend_gate_released_0050_step）
- cash_after_cost: 254,710

■ 持股比率（6/23）
- 0050.TW: 8,374 股（69.9%）
- 00631L.TW: 3,514 股（10.9%）
- 00679B.TWO: 24 股（0.0%）
- 現金: 254,710（19.1%）
- 總市值（含現金）: 1,331,326

■ 策略績效（A213 回測至 2026-06-22）
- Final: 2,489,229（+148.92%），年化 +86.16%，Sharpe 2.547，MDD -22.84%

■ 策略共識
- 兩策略均維持最大倉位，市場在 MA200 與 MA50 之上，趨勢動能完好
- Golden1 純 00631L 全押；A213 分散持有（0050 70% + 00631L 11% + 現金 19%）"""
content = content[:2000]

payload = {
    "parent": {"data_source_id": "631c5287-c46c-47cd-aea0-be8be0d88f67"},
    "properties": {
        "Name": {"title": [{"text": {"content": "2026-06-23 Group A+ / Golden1 預測與持股比率"}}]},
        "日期": {"date": {"start": "2026-06-23"}},
        "狀態": {"select": {"name": "已完成"}},
        "工作內容": {"rich_text": [{"text": {"content": content}}]},
        "心情": {"select": {"name": "平靜"}}
    }
}

proc = subprocess.run(
    ["curl", "-s", "-X", "POST",
     "https://api.notion.com/v1/pages",
     "-H", f"Authorization: Bearer {NOTION_API_KEY}",
     "-H", "Notion-Version: 2025-09-03",
     "-H", "Content-Type: application/json",
     "-d", json.dumps(payload)],
    capture_output=True, text=True
)
result = json.loads(proc.stdout)
if result.get("object") == "error":
    print(f"ERROR: {result.get('message')}")
else:
    print(f"OK — Page ID: {result.get('id')}")
    print(f"URL: https://www.notion.so/{result.get('id')}")
