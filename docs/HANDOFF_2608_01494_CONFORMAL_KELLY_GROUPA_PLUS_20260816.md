# 2608.01494 Conformal Kelly (Conformal Prediction Intervals as Fractional-Kelly Scale) — Group A+ 適用性審查

**日期**：2026-08-16
**論文**：Ryan (2026), *"Conformal Kelly: Conformal Prediction Intervals as the Scale in Fractional Kelly Position Sizing"*, ACS Athens
**結論**：**核心機制(conformal-Kelly sizing)不導入——作者自己pre-registered lockbox已經否決；但「慢適應優於快適應」的方法論原則，獨立驗證了Group A+既有`tail_conformal.py`的ACI gamma設計選擇。**

## 1. 論文核心

- 把conformal prediction區間寬度當作fractional Kelly公式的σ：`f = κ·μ/σ²`，σ從75% conformal區間的half-width讀出。
- **正面發現(開發窗口2016-2021)**：用conformal分位數當σ比傳統rolling標準差好+2.1pp/yr——因為conformal分位數是bounded influence function，對肥尾資產(USO/SLV)更穩健，標準差是quadratic influence function反而被極端值主導。
- **最反直覺、最重要的發現**：任何讓conformal區間「更快適應」市場的手法全部讓報酬變差——ACI(-1.6pp)、recency-weighted CP(-1.4pp)、volatility-scaled score(-3.3pp)、asymmetric CQR-style(-1.6pp)。機制：σ被非線性的Kelly sizing公式消耗，σ的估計雜訊會直接侵蝕複利財富，所以要在σ的「反應速度」跟「穩定度」之間取捨，且答案是要慢、甚至凍結都比rolling standard deviation好。
- **downside miscoverage當作deleverage訊號**：買到-7.4pp的MDD改善+更好的Sharpe，通過40次circular-shift placebo檢定(p=0.024)。
- **決定性負面結果**：作者用autonomous LLM agent search出~200組設定，**事先密封2022-2024當lockbox**，pre-registration寫死判準。lockbox結果：growth完全沒有轉移出樣本外——兩個設定在11個對照組裡Sharpe/Calmar**排名墊底**，連equal-weight、vol-target risk parity都打不過。作者原話：「the strategy as configured is not investable」。

## 2. 為何核心機制不導入

不需要shadow測試驗證——**作者自己的pre-registered lockbox已經是最嚴謹的否決證據**，比我們自己重新做一次驗證更可信（有sealed window、pre-registration、事先寫死的判準）。這正好呼應[[feedback_overfitting_fixed_window_tuning]]、[[feedback_check_data_coverage_before_multiyear_framing]]的既有教訓：單一開發窗口漂亮(28.5%年化、Sharpe 1.34)不代表真訊號，這篇論文是最乾淨的教科書級案例，作者已經把答案交出來了。

此外，Group A+目前也沒有一個真正的「μ/σ²連續Kelly公式」在決定部位大小（PPO是RL學出來的policy，PVA是sigmoid overlay，都不是Kelly公式），套用點本身就不明確。

## 3. 獨立驗證：Group A+的tail_conformal.py已經自己發現同樣的原則

`group_a_plus/integrations/tail_conformal.py`的`compute_tail_conformal_diagnostic`函式用ACI算00631L下檔尾部風險機率，docstring記錄了2026-07-27的gamma選擇實驗：

> 「`aci_gamma`預設(0.005)是發現更快的速率(0.05)反而讓2020年coverage變差(16.3%)後選定的——快學習率讓adaptive alpha在平靜期飄到目標之上，然後在regime剛開始轉變的關鍵時刻反應不過來。慢速率接著用held-out的2018年驗證：靜態14.5%/15.7% vs 適應式14.0%/14.0%，是真實、雖然溫和的OOS改善，不只是2020特定的過擬合。」

**這跟這篇論文的核心結論方向完全一致**：快速適應的conformal校準會在regime轉換的關鍵時刻「跟丟」，慢速穩定的校準反而更可靠。差異在於：
- Group A+的ACI是拿來算機率當**離散advisory門檻**（暫停加碼00631L、觸發trough monitoring），不是連續Kelly-style的部位大小輸入，所以論文最強烈的機制（σ被非線性sizing公式放大侵蝕估計雜訊）不完全適用。
- 但「慢適應優於快適應」這個更底層的原則，論文用嚴謹的理論(bounded influence function)+跨多種手法(ACI/recency-weighted/volatility-scaled/CQR)的系統性ablation獨立佐證了Group A+七月自己土法煉鋼調參得到的同一個結論。

**這次沒有導入新東西，是外部研究驗證既有設計選擇的正面案例**——`aci_gamma=0.005`這個選擇不是台股資料的偶然巧合，而是conformal prediction用在金融時間序列上的一般性原則。

## Do Not Do
- 不要嘗試把conformal區間寬度接進任何連續position-sizing公式（例如PVA的leverage scale）——作者自己的lockbox已經證明這條路在樣本外失敗，"not investable"。
- 不要因為這篇論文而重新質疑`tail_conformal.py`現有的`aci_gamma=0.005`設定——這篇論文反而是外部確認，不是質疑的理由。

## Next Step
無強制後續行動。這是一次乾淨的「機制不導入+既有選擇被獨立驗證」的結案。
