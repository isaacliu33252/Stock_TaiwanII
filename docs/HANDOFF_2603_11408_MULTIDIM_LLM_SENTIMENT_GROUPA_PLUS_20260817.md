# 2603.11408《Beyond Polarity: Multi-Dimensional LLM Sentiment Signals for WTI Crude Oil Futures Return Prediction》審查 — 交接記錄

**日期**：2026-08-17
**論文**：Dai, Ma, Liu, Geng, Wang，*"Beyond Polarity: Multi-Dimensional LLM Sentiment Signals for WTI Crude Oil Futures Return Prediction"*
**結論**：**論文本身不直接適用（WTI原油期貨，Group A+無原油部位），但這是今天唯一一篇直接命中Group A+既有訊號線（2026-07-01已嘗試過的LLM/新聞情緒訊號，判定shadow-only）的論文。用免費、零API成本的中文關鍵字proxy複製論文核心假說（多維度情緒優於純極性）並實測，18組測試(3維度×3視野×2 ticker)中沒有任何一組通過多重比較校正——強化(非推翻)既有shadow-only判斷，是獨立方法得出同一結論的交叉驗證。**

## 1. 論文核心

用LLM(GPT-4o、Llama 3.2-3b)從能源新聞文章萃取**五個情緒維度**——relevance(相關性)、polarity(極性)、intensity(強度)、uncertainty(不確定性)、forwardness(前瞻性)，而非傳統只看polarity的情緒分析。用relevance加權聚合成週頻特徵，加上跨文章離散度(std)跟week-on-week動量，餵進LightGBM分類器預測WTI原油期貨週報酬方向。

**核心發現**：
1. GPT-4o+FinBERT組合預測效果最好(AUC 0.6515)，優於純AlphaVantage基準(AUC 0.5694)。
2. **SHAP分析顯示intensity跟uncertainty維度比polarity本身更重要**——最重要的兩個特徵是`gpt_intensity_mean`跟`finbert_polarity_std`，證明「多維度情緒優於純極性判斷」。
3. Llama 3.2-3b加入GPT-4o反而沒有提升(可能引入雜訊)，顯示更小的LLM不見得能提供互補資訊。

## 2. 為何論文本身不適用

Group A+可交易資產(0050/00631L/00632R/00679B)無原油曝險，論文target(WTI原油週報酬)跟Group A+的決策問題無直接對應。

## 3. 為何這篇特別值得追蹤：直接命中既有訊號線

2026-07-01，Group A+已經嘗試過同構想的初步版本(見memory `project_llm_feature_generator_news`)——用FinMind新聞API配合**純關鍵字比對的polarity-only proxy**（不是真正的LLM多維度萃取）預測0050/00631L報酬，最終結論是**「沒有可靠正向預測力，維持shadow-only」**，根因判定為「2025-01~2026-06整段是單一多頭regime，任何偏空訊號在這段期間統計上都會被打臉」。但當時**只測了polarity一個維度，從未測過intensity/uncertainty**。這篇論文剛好提供了「如果換用真正的多維度情緒會不會不一樣」的具體對照假說。

## 4. 追加實測：用免費proxy複製「多維度優於純極性」假說

**設計**：重用7月已經抓好、快取在repo裡的新聞語料(`news/finmind_stock_news_merged_full.jsonl`，0050.TW 5,632篇+00631L.TW 506篇，2025-01~2026-06真實中文新聞標題，無新API呼叫)。因為只有標題無全文，且是中文文本，無法直接套用論文的GPT-4o prompt或既有的英文Loughran-McDonald字典(`group_a_plus/integrations/lm_dictionary_sentiment.py`已有`uncertainty`類別但只對英文token生效，中文標題幾乎零命中)。改用既有的中文情緒關鍵字基礎設施(`build_finbert_sentiment_features.py`的`POSITIVE_TERMS`/`NEGATIVE_TERMS`)為基礎，額外**手刻一個中文不確定性詞典**(「可能」「或將」「預期」「估計」「疑慮」「觀望」「傳聞」等，仿論文uncertainty維度精神，對應LM字典的Uncertainty類別但用中文詞彙)：

- polarity = (positive_hits - negative_hits) / max(total_hits, 1)
- intensity = positive_hits + negative_hits（情緒詞密度，用詞越重代表強度越強，仿論文「同極性下區分強弱措辭」的定義）
- uncertainty = 不確定性詞典命中數

每個維度算週頻(依事件日聚合)IC(Spearman rank correlation，跟論文獨立找到的核心診斷指標一致)，對0050.TW跟00631L.TW分別測h1/h5/h20三個視野，共18組。腳本：`<scratchpad>/multidim_sentiment_ic_test.py`。

**第一輪結果——出現一個看似顯著的訊號**：0050.TW在h5視野，intensity IC=+0.106(p=0.015)，polarity同視野IC僅+0.013(幾乎零)。這部分支持論文「intensity帶有polarity沒有的資訊」的主張。

**加入多重比較校正後被推翻**：用Benjamini-Hochberg FDR校正全部18組p值，**沒有任何一組的調整後p值低於0.27**（原本p=0.015的intensity結果校正後變成0.270）。18組測試在α=0.05下，純雜訊也預期會出現約0.9個「顯著」結果——這個唯一的正面訊號完全落在雜訊預期範圍內。

**最終結論**：**沒有任何一個維度(polarity/intensity/uncertainty)在Group A+既有新聞語料上展現出統計上可信的預測力**——跟7月的判定完全一致，是**用不同情緒詞典、額外加了intensity/uncertainty兩個新維度的獨立方法，得出同一個「無可靠訊號」結論**，讓既有shadow-only判斷更站得住腳。

## Do Not Do
- 不要把「加了新維度後結果差不多」直接等同於「論文的多維度洞察在Group A+不成立」——這次用的是關鍵字計數proxy，不是論文真正的GPT-4o全文語意萃取，且只有新聞標題沒有全文，樣本仍落在同一個已知的單一多頭regime窗口內。這次測試**只能排除「粗糙關鍵字proxy版本的多維度情緒」在目前資料條件下無效**，不能完全排除「若真的用LLM對全文做語意分析可能找到不同東西」的可能性。
- 不要只看單一p<0.05結果就下結論——18組測試中出現1個「顯著」結果完全落在多重比較的雜訊預期範圍內(0.05×18≈0.9)，必須做FDR或Bonferroni校正才能判斷是否為真訊號，這次校正後完全不顯著。
- 若未來真的想用真正的LLM(GPT-4o等)對台股新聞全文做論文式的五維度萃取，需要先解決兩個既有的基礎設施缺口：(1) 台股新聞全文取得管道(MOPS被WAF擋、FinMind只有標題+免費額度有限)，(2) 樣本期間目前只涵蓋單一多頭regime，任何情緒訊號(不論極性或多維度)在這段期間都可能被regime本身蓋過，需要累積到真正的空頭/盤整期資料才能做出可信判斷。

## Next Step
無強制後續行動。若未來新聞資料源問題解決(例如取得MOPS或其他全文新聞管道)，且累積到涵蓋非多頭regime的樣本，值得用真正的LLM多維度萃取重新測試一次，屆時應該同時計入FDR校正避免重蹈這次「單一p<0.05結果」的陷阱。

詳細記錄完。
