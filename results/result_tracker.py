# ============================================================================
# 結果追蹤器 (Result Tracker)
# ============================================================================
"""
負責儲存與追蹤訓練與回測結果。

功能特色：
- 模型檢查點儲存
- 訓練曲線繪製
- 績效指標記錄
- 交易歷史輸出
- 實驗比較
- 結果摘要產生

使用方式：
    from FinRL.results.result_tracker import ResultTracker
    
    tracker = ResultTracker()
    tracker.save_result(result, config)
    tracker.load_results()
    tracker.compare_runs()
    tracker.generate_summary()

作者: FinRL量化交易專家
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RESULTS_DIR, MODELS_DIR


class ResultTracker:
    """
    結果追蹤器
    
    用於追蹤、儲存和比較不同實驗的結果。
    
    屬性：
        results_dir: 結果儲存目錄
        models_dir: 模型儲存目錄
        experiments_file: 實驗記錄檔案路徑
        metrics_file: 績效指標 CSV 檔案路徑
    
    使用範例：
        >>> tracker = ResultTracker()
        >>> tracker.save_result(backtest_result, config)
        >>> tracker.compare_runs(metric='sharpe_ratio')
        >>> tracker.generate_summary()
    """
    
    def __init__(
        self,
        results_dir: Optional[str] = None,
        models_dir: Optional[str] = None
    ):
        """
        初始化結果追蹤器
        
        參數：
            results_dir: 結果儲存目錄（預設使用 config.py 中的設定）
            models_dir: 模型儲存目錄
        """
        self.results_dir = results_dir if results_dir else RESULTS_DIR
        self.models_dir = models_dir if models_dir else MODELS_DIR
        
        # 確保目錄存在
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)
        
        # 實驗記錄檔案
        self.experiments_file = os.path.join(self.results_dir, "experiments.json")
        self.metrics_file = os.path.join(self.results_dir, "metrics.csv")
        
        print(f"[ResultTracker] 結果追蹤器初始化完成")
        print(f"  - 結果目錄: {self.results_dir}")
        print(f"  - 模型目錄: {self.models_dir}")
    
    def save_result(
        self,
        result: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        儲存單一實驗結果
        
        儲存內容：
        - 回測結果（績效指標、交易歷史、權益曲線）
        - 實驗配置
        - 時間戳記
        - 自訂標籤
        
        參數：
            result: 回測結果字典（包含 metrics, trade_history, portfolio_values 等）
            config: 實驗配置（Agent 類型、超參數等）
            name: 實驗名稱（若為 None，自動生成）
            tags: 標籤列表（用於分類，例如 ['ppo', 'training', '2024']）
        
        返回：
            結果檔案路徑
        """
        # 生成實驗名稱
        if name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"experiment_{timestamp}"
        
        # 建立實驗目錄
        exp_dir = os.path.join(self.results_dir, name)
        os.makedirs(exp_dir, exist_ok=True)
        
        # 準備儲存資料
        record = {
            'name': name,
            'timestamp': datetime.now().isoformat(),
            'config': config or {},
            'tags': tags or [],
        }
        
        # 處理結果
        if 'metrics' in result:
            record['metrics'] = result['metrics']
        
        if 'trade_history' in result:
            trades_file = os.path.join(exp_dir, 'trades.csv')
            if result['trade_history']:
                df = pd.DataFrame(result['trade_history'])
                df.to_csv(trades_file, index=False)
                record['trades_file'] = trades_file
        
        if 'portfolio_values' in result:
            equity_file = os.path.join(exp_dir, 'equity.csv')
            equity = np.array(result['portfolio_values'])
            np.save(equity_file, equity)
            record['equity_file'] = equity_file
        
        if 'returns' in result:
            returns_file = os.path.join(exp_dir, 'returns.csv')
            returns = np.array(result['returns'])
            np.save(returns_file, returns)
            record['returns_file'] = returns_file
        
        # 儲存實驗記錄
        exp_record_file = os.path.join(exp_dir, 'experiment.json')
        with open(exp_record_file, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        
        # 更新實驗索引
        self._update_experiments_index(record)
        
        # 更新 metrics CSV
        if 'metrics' in result:
            self._update_metrics_csv(record)
        
        print(f"[ResultTracker] 實驗結果已儲存: {name}")
        return exp_dir
    
    def _update_experiments_index(self, record: Dict[str, Any]):
        """更新實驗索引檔案"""
        experiments = []
        
        if os.path.exists(self.experiments_file):
            try:
                with open(self.experiments_file, 'r', encoding='utf-8') as f:
                    experiments = json.load(f)
            except json.JSONDecodeError:
                experiments = []
        
        # 添加新記錄
        index_entry = {
            'name': record['name'],
            'timestamp': record['timestamp'],
            'tags': record.get('tags', []),
            'metrics': record.get('metrics', {}),
        }
        experiments.append(index_entry)
        
        # 儲存
        with open(self.experiments_file, 'w', encoding='utf-8') as f:
            json.dump(experiments, f, indent=2, ensure_ascii=False)
    
    def _update_metrics_csv(self, record: Dict[str, Any]):
        """更新 metrics CSV 檔案"""
        if 'metrics' not in record:
            return
        
        metrics = record['metrics']
        
        # 建立記錄
        row = {
            'name': record['name'],
            'timestamp': record['timestamp'],
            'total_return': metrics.get('total_return', 0),
            'annual_return': metrics.get('annual_return', 0),
            'sharpe_ratio': metrics.get('sharpe_ratio', 0),
            'sortino_ratio': metrics.get('sortino_ratio', 0),
            'calmar_ratio': metrics.get('calmar_ratio', 0),
            'max_drawdown': metrics.get('max_drawdown', 0),
            'win_rate': metrics.get('win_rate', 0),
            'profit_factor': metrics.get('profit_factor', 0),
            'total_trades': metrics.get('total_trades', 0),
        }
        
        df = pd.DataFrame([row])
        
        if os.path.exists(self.metrics_file):
            existing_df = pd.read_csv(self.metrics_file)
            df = pd.concat([existing_df, df], ignore_index=True)
        
        df.to_csv(self.metrics_file, index=False)
    
    def load_results(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        載入實驗結果
        
        參數：
            name: 實驗名稱（若為 None，載入所有實驗）
        
        返回：
            實驗結果列表
        """
        if name is not None:
            # 載入特定實驗
            exp_dir = os.path.join(self.results_dir, name)
            exp_file = os.path.join(exp_dir, 'experiment.json')
            
            if os.path.exists(exp_file):
                with open(exp_file, 'r', encoding='utf-8') as f:
                    return [json.load(f)]
            else:
                print(f"[ResultTracker] 找不到實驗: {name}")
                return []
        
        # 載入所有實驗
        experiments = self.load_experiments()
        return experiments
    
    def load_experiments(self) -> List[Dict[str, Any]]:
        """
        載入所有實驗記錄
        
        返回：
            實驗記錄列表
        """
        if not os.path.exists(self.experiments_file):
            return []
        
        try:
            with open(self.experiments_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    
    def load_metrics_csv(self) -> pd.DataFrame:
        """
        載入 metrics CSV 檔案
        
        返回：
            DataFrame 包含所有指標記錄
        """
        if not os.path.exists(self.metrics_file):
            return pd.DataFrame()
        
        return pd.read_csv(self.metrics_file)
    
    def compare_runs(
        self,
        metric: str = 'sharpe_ratio',
        top_n: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        比較不同實驗的指定指標
        
        參數：
            metric: 要比較的指標名稱（預設 'sharpe_ratio'）
            top_n: 只顯示前 N 名（可選）
            tags: 篩選特定標籤的實驗（可選）
        
        返回：
            比較的 DataFrame，按指標排序
        """
        experiments = self.load_experiments()
        
        if not experiments:
            print("[ResultTracker] 沒有找到實驗記錄")
            return pd.DataFrame()
        
        # 篩選包含指定指標的實驗
        filtered = []
        for exp in experiments:
            if 'metrics' not in exp:
                continue
            
            if metric not in exp['metrics']:
                continue
            
            # 標籤篩選
            if tags:
                exp_tags = exp.get('tags', [])
                if not any(tag in exp_tags for tag in tags):
                    continue
            
            filtered.append({
                'name': exp.get('name', ''),
                'timestamp': exp.get('timestamp', ''),
                'tags': ','.join(exp.get('tags', [])),
                metric: exp['metrics'].get(metric, 0),
                'total_return': exp['metrics'].get('total_return', 0),
                'max_drawdown': exp['metrics'].get('max_drawdown', 0),
                'win_rate': exp['metrics'].get('win_rate', 0),
            })
        
        if not filtered:
            print(f"[ResultTracker] 沒有找到指標 '{metric}' 的記錄")
            return pd.DataFrame()
        
        # 建立 DataFrame 並排序
        df = pd.DataFrame(filtered)
        df = df.sort_values(metric, ascending=False)
        
        # 限制顯示數量
        if top_n is not None:
            df = df.head(top_n)
        
        print(f"\n[ResultTracker] {metric} 排名:")
        print("=" * 80)
        for i, row in df.iterrows():
            print(f"  {row['name']:30s} | {metric}: {row[metric]:>10.4f} | "
                  f"報酬: {row['total_return']*100:>8.2f}% | 回撤: {row['max_drawdown']*100:>8.2f}%")
        print("=" * 80)
        
        return df
    
    def get_latest_metrics(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        取得最新的績效指標
        
        參數：
            name: 實驗名稱（若為 None，則取得所有實驗的最新記錄）
        
        返回：
            績效指標字典
        """
        experiments = self.load_experiments()
        
        if not experiments:
            return {}
        
        if name:
            # 取得特定實驗的最新記錄
            filtered = [exp for exp in experiments if exp.get('name') == name]
            if filtered:
                return filtered[-1].get('metrics', {})
            return {}
        else:
            # 取得所有實驗的最新記錄
            return experiments[-1].get('metrics', {})
    
    def generate_summary(
        self,
        tags: Optional[List[str]] = None,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        產生實驗摘要報告
        
        包含：
        - 總實驗數
        - 平均/最佳/最差績效指標
        - 最近實驗列表
        
        參數：
            tags: 只包含特定標籤的實驗
            output_file: 輸出檔案路徑（可選）
        
        返回：
            摘要字典
        """
        experiments = self.load_experiments()
        
        if not experiments:
            print("[ResultTracker] 沒有找到實驗記錄")
            return {}
        
        # 標籤篩選
        if tags:
            experiments = [
                exp for exp in experiments
                if any(tag in exp.get('tags', []) for tag in tags)
            ]
        
        if not experiments:
            print("[ResultTracker] 沒有符合標籤條件的實驗")
            return {}
        
        # 收集指標
        metrics_summary = {
            'total_experiments': len(experiments),
            'sharpe_ratios': [],
            'total_returns': [],
            'max_drawdowns': [],
            'win_rates': [],
            'profit_factors': [],
        }
        
        for exp in experiments:
            metrics = exp.get('metrics', {})
            metrics_summary['sharpe_ratios'].append(metrics.get('sharpe_ratio', 0))
            metrics_summary['total_returns'].append(metrics.get('total_return', 0))
            metrics_summary['max_drawdowns'].append(metrics.get('max_drawdown', 0))
            metrics_summary['win_rates'].append(metrics.get('win_rate', 0))
            metrics_summary['profit_factors'].append(metrics.get('profit_factor', 0))
        
        # 計算統計
        summary = {
            'total_experiments': len(experiments),
            'avg_sharpe': np.mean(metrics_summary['sharpe_ratios']),
            'best_sharpe': np.max(metrics_summary['sharpe_ratios']),
            'avg_return': np.mean(metrics_summary['total_returns']),
            'best_return': np.max(metrics_summary['total_returns']),
            'avg_drawdown': np.mean(metrics_summary['max_drawdowns']),
            'worst_drawdown': np.min(metrics_summary['max_drawdowns']),
            'avg_win_rate': np.mean(metrics_summary['win_rates']),
            'avg_profit_factor': np.mean(metrics_summary['profit_factors']),
        }
        
        # 格式化輸出
        print("\n" + "=" * 70)
        print("                     實驗摘要報告")
        print("=" * 70)
        print(f"  總實驗數:         {summary['total_experiments']}")
        print(f"\n  【夏普比率】")
        print(f"    平均值:         {summary['avg_sharpe']:.3f}")
        print(f"    最佳值:         {summary['best_sharpe']:.3f}")
        print(f"\n  【報酬率】")
        print(f"    平均值:         {summary['avg_return']*100:.2f}%")
        print(f"    最佳值:         {summary['best_return']*100:.2f}%")
        print(f"\n  【最大回撤】")
        print(f"    平均值:         {summary['avg_drawdown']*100:.2f}%")
        print(f"    最大:           {summary['worst_drawdown']*100:.2f}%")
        print(f"\n  【勝率】")
        print(f"    平均值:         {summary['avg_win_rate']*100:.2f}%")
        print(f"\n  【利潤因子】")
        print(f"    平均值:         {summary['avg_profit_factor']:.3f}")
        print("=" * 70)
        
        # 儲存摘要
        if output_file is None:
            output_file = os.path.join(self.results_dir, f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n[ResultTracker] 摘要已儲存至：{output_file}")
        
        return summary
    
    def save_model(
        self,
        model,
        name: str,
        agent_type: str = "ppo"
    ) -> str:
        """
        儲存模型
        
        參數：
            model: 訓練好的模型
            name: 模型名稱
            agent_type: Agent 類型（ppo, a2c, sac, ddpg）
        
        返回：
            檔案路徑
        """
        filepath = os.path.join(self.models_dir, f"{name}_{agent_type}.zip")
        
        try:
            model.save(filepath)
            print(f"[ResultTracker] 模型已儲存至：{filepath}")
        except Exception as e:
            print(f"[ResultTracker] 模型儲存失敗: {e}")
        
        return filepath
    
    def load_model(
        self,
        name: str,
        agent_type: str = "ppo"
    ):
        """
        載入模型
        
        參數：
            name: 模型名稱
            agent_type: Agent 類型
        
        返回：
            載入的模型
        """
        from stable_baselines3 import PPO, A2C, SAC, DDPG
        
        filepath = os.path.join(self.models_dir, f"{name}_{agent_type}.zip")
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"[ResultTracker] 找不到模型檔案：{filepath}")
        
        if agent_type.lower() == "ppo":
            model = PPO.load(filepath)
        elif agent_type.lower() == "a2c":
            model = A2C.load(filepath)
        elif agent_type.lower() == "sac":
            model = SAC.load(filepath)
        elif agent_type.lower() == "ddpg":
            model = DDPG.load(filepath)
        else:
            raise ValueError(f"[ResultTracker] 不支援的 Agent 類型：{agent_type}")
        
        print(f"[ResultTracker] 模型已從 {filepath} 載入")
        return model
    
    def list_experiments(self) -> pd.DataFrame:
        """
        列出所有實驗
        
        返回：
            DataFrame 包含實驗名稱、時間、標籤等
        """
        experiments = self.load_experiments()
        
        if not experiments:
            return pd.DataFrame()
        
        df = pd.DataFrame([{
            'name': exp.get('name', ''),
            'timestamp': exp.get('timestamp', ''),
            'tags': ','.join(exp.get('tags', [])),
        } for exp in experiments])
        
        return df
    
    def delete_experiment(self, name: str) -> bool:
        """
        刪除實驗
        
        參數：
            name: 實驗名稱
        
        返回：
            是否刪除成功
        """
        exp_dir = os.path.join(self.results_dir, name)
        
        if not os.path.exists(exp_dir):
            print(f"[ResultTracker] 實驗不存在: {name}")
            return False
        
        # 刪除目錄
        import shutil
        shutil.rmtree(exp_dir)
        
        # 更新索引
        experiments = self.load_experiments()
        experiments = [e for e in experiments if e.get('name') != name]
        
        with open(self.experiments_file, 'w', encoding='utf-8') as f:
            json.dump(experiments, f, indent=2)
        
        print(f"[ResultTracker] 實驗已刪除: {name}")
        return True


# ============================================================================
# 工廠函式
# ============================================================================

def create_result_tracker(
    results_dir: Optional[str] = None,
    models_dir: Optional[str] = None
) -> ResultTracker:
    """
    便捷函式：建立結果追蹤器
    
    參數：
        results_dir: 結果目錄
        models_dir: 模型目錄
    
    返回：
        ResultTracker 實例
    """
    return ResultTracker(results_dir=results_dir, models_dir=models_dir)