# ============================================================================
# FinRL Data Utilities - 統一資料讀取與快取管理
# ============================================================================
"""
提供安全、快速的 parquet 讀取工具，支援 PyArrow 24 + Pandas 3.x

主要功能：
    1. read_parquet_safe() - PyArrow 24 相容 + graceful fallback
    2. CacheValidator - 快取有效性驗證（日期範圍、完整性）
    3. ParquetStreamReader - 串流讀取（大型檔案，省記憶體）
    4. normalize_date_column() - 統一日期欄位標準化

PyArrow 24 + Pandas 3.0.2 的 parquet 讀取問題：
    - pd.read_parquet() 在某些 timestamp 格式會失敗
    - 解法：pyarrow.dataset + timestamp_as_object=True
"""

import pyarrow as pa
import pyarrow.dataset as pads
import pyarrow.parquet as pap
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Union, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 統一 parquet 讀取（PyArrow 24 相容 + graceful fallback）
# ─────────────────────────────────────────────────────────────────────────────

def read_parquet_safe(
    file_path: Union[str, Path],
    timestamp_as_object: bool = True,
    columns: Optional[List[str]] = None,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """
    安全讀取 parquet，自動處理 PyArrow 24 + Pandas 3.x 的相容性問題。

    策略：
        1. 嘗試 pd.read_parquet()（多數情況成功）
        2. 失敗則用 pyarrow.dataset + timestamp_as_object=True
        3. 仍失敗則回傳 None（不爆錯）

    Args:
        file_path: parquet 檔案路徑
        timestamp_as_object: 是否將 timestamp 轉為 object（避免 tz 問題）
        columns: 只讀取特定欄位（可省記憶體）
        use_cache: 是否使用快取（這裡純粹為了 API 一致性）

    Returns:
        DataFrame 或 None（檔案不存在或損壞時）
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path

    if not path.exists():
        logger.warning(f"[read_parquet_safe] 檔案不存在: {path}")
        return None

    # ── 策略 1: pd.read_parquet (最快速) ────────────────────────────────────
    try:
        df = pd.read_parquet(path, columns=columns)
        if df is not None and not df.empty:
            return _normalize_date_column(df)
    except Exception as e:
        logger.debug(f"[read_parquet_safe] pd.read_parquet 失敗: {e}")

    # ── 策略 2: pyarrow.dataset (PyArrow 24 解法) ──────────────────────────
    try:
        dataset = pads.dataset(str(path))
        table = dataset.to_table(columns=columns) if columns else dataset.to_table()
        df = table.to_pandas(timestamp_as_object=timestamp_as_object)
        if df is not None and not df.empty:
            return _normalize_date_column(df)
    except Exception as e:
        logger.debug(f"[read_parquet_safe] pyarrow.dataset 失敗: {e}")

    # ── 策略 3: PyArrow 24 tz-metadata 損壞，嘗試修復讀取 ────────────────────
    except (AttributeError, TypeError) as e3:
        # PyArrow 24 特定錯誤：timestamp metadata 中 tz=None 但被錯誤解讀
        # 'NoneType' object has no attribute 'timezone' 就是這個問題
        logger.warning(f"[read_parquet_safe] PyArrow tz metadata 損壞，嘗試修復: {path.name} | {e3}")
        try:
            # 讀取整個 schema，找出 timestamp 欄位
            schema = pap.read_schema(str(path))
            timestamp_cols = [
                name for name, field in zip(schema.names, schema)
                if pa.types.is_timestamp(field.type)
            ]
            # 讀取 table 後，手動將 timestamp 轉為字串（繞過 tz 問題）
            table = pap.read_table(str(path), columns=columns)
            df = table.to_pandas(timestamp_as_object=True)
            # 如果某個 timestamp 欄位變成了 object 且含有 tz-aware datetime，
            # 嘗試手動去除 tz
            for col in timestamp_cols:
                if col in df.columns:
                    try:
                        if hasattr(df[col].dtype, 'tz') and df[col].dtype.tz is not None:
                            df[col] = df[col].dt.tz_localize(None)
                        elif str(df[col].dtype) == 'object':
                            # 可能是混合型，嘗試解析
                            df[col] = pd.to_datetime(df[col], errors='coerce').dt.normalize()
                    except Exception:
                        pass
            return _normalize_date_column(df)
        except Exception as e4:
            logger.error(f"[read_parquet_safe] 修復失敗: {path.name} | {e4}")
            return None

    return None


def write_parquet_safe(
    df: pd.DataFrame,
    file_path: Union[str, Path],
    timestamp_as_object: bool = True,
    **kwargs
) -> bool:
    """
    安全寫入 parquet，避免 PyArrow 24 的 timestamp 問題。

    Args:
        df: 要寫入的 DataFrame
        file_path: 目標路徑
        timestamp_as_object: 寫入前先將 timestamp 轉為 object
        **kwargs: 額外傳給 to_parquet()

    Returns:
        True 成功，False 失敗
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        df_out = _normalize_date_column(df)
        df_out.to_parquet(path, index=False, **kwargs)
        return True
    except Exception as e:
        logger.error(f"[write_parquet_safe] 寫入失敗: {path.name} | {e}")
        # fallback: 轉所有 timestamp 為字串再寫
        try:
            df_str = df_out.copy()
            for col in df_str.columns:
                if pd.api.types.is_datetime64_any_dtype(df_str[col]):
                    df_str[col] = df_str[col].dt.strftime('%Y-%m-%d %H:%M:%S')
            df_str.to_parquet(path, index=False, **kwargs)
            return True
        except Exception as e2:
            logger.error(f"[write_parquet_safe] fallback 也失敗: {path.name} | {e2}")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. 日期欄位標準化（所有 loader 統一使用）
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    標準化 DataFrame 的日期欄位，確保：
        1. 'datetime' 欄位 rename 為 'date'（常見於 yfinance）
        2. 去除時區資訊（tz_localize(None) 或 tz-aware handling）
        3. normalize 為 date（去除時間部分）
        4. 轉為 pd.NaT/null safe

    這個函式不修改原始 DataFrame，會建立 copy。
    """
    df = df.copy()

    # 找出日期欄位（優先用 'date'，其次 'datetime'）
    date_col = None
    if 'date' in df.columns:
        date_col = 'date'
    elif 'datetime' in df.columns and 'date' not in df.columns:
        date_col = 'datetime'

    if date_col is None:
        return df

    # 轉換日期：先處理 tz-aware datetime，再統一轉為 Naive datetime
    date_series = df[date_col]

    # 如果是 tz-aware（PyArrow 24 timestamp with Asia/Taipei），先去除時區
    if hasattr(date_series.dtype, 'tz') and date_series.dtype.tz is not None:
        try:
            date_series = date_series.dt.tz_localize(None)
        except Exception:
            # 某些 timezone 處理失敗，改用 UTC 轉換再移除 tz
            try:
                date_series = date_series.dt.tz_convert('UTC').dt.tz_localize(None)
            except Exception:
                pass

    # 轉換為 datetime（處理字串、object 等各种格式）
    try:
        date_series = pd.to_datetime(date_series, errors='coerce')
    except (AttributeError, TypeError):
        # 仍失敗時，手動處理
        date_series = pd.to_datetime(date_series.astype(str), errors='coerce')

    # pd.to_datetime() can reintroduce timezone-aware dtype when the parquet
    # values already carry tz metadata. Drop tz again so cache validation and
    # date slicing compare like with like.
    if hasattr(date_series.dtype, 'tz') and date_series.dtype.tz is not None:
        try:
            date_series = date_series.dt.tz_localize(None)
        except Exception:
            date_series = date_series.dt.tz_convert('UTC').dt.tz_localize(None)

    # normalize（去除時間，只保留日期）
    date_series = date_series.dt.normalize()

    df[date_col] = date_series

    # 如果原本是 datetime 欄位，rename 為 date
    if date_col == 'datetime':
        df['date'] = df.pop('datetime')

    return df


def normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """外部可直接呼叫的版本"""
    return _normalize_date_column(df)


def _normalize_timestamp(value: Union[str, datetime, pd.Timestamp]) -> pd.Timestamp:
    """Return a timezone-naive normalized Timestamp for date comparisons."""
    ts = pd.to_datetime(value)
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


# ─────────────────────────────────────────────────────────────────────────────
# 3. 快取驗證器（CacheValidator）
# ─────────────────────────────────────────────────────────────────────────────

class CacheValidator:
    """
    驗證 parquet 快取的有效性，避免用到過期/損壞的資料。

    檢查項目：
        1. 檔案是否存在
        2. 是否可讀取（不爆錯）
        3. 日期範圍是否覆蓋需求區間
        4. 是否包含必要欄位
        5. 資料筆數是否合理（不能為 0 或異常少）

    使用方式：
        validator = CacheValidator(required_columns=['date','close','volume'])
        is_valid, reason = validator.validate('cache/0050_TW.parquet',
                                               start='2020-01-01',
                                               end='2024-12-31')
        if is_valid:
            df = read_parquet_safe('cache/0050_TW.parquet')
    """

    def __init__(
        self,
        required_columns: Optional[List[str]] = None,
        min_rows: int = 10,
        allow_empty: bool = False,
    ):
        self.required_columns = required_columns or []
        self.min_rows = min_rows
        self.allow_empty = allow_empty

    def validate(
        self,
        file_path: Union[str, Path],
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
    ) -> tuple[bool, str]:
        """
        驗證快取是否可用。

        Returns:
            (is_valid, reason) - is_valid=True 表示可用，reason 為詳細說明
        """
        path = Path(file_path) if isinstance(file_path, str) else file_path

        # 檢查 1: 檔案存在
        if not path.exists():
            return False, f"檔案不存在: {path.name}"

        # 檢查 2: 可讀取
        df = read_parquet_safe(path)
        if df is None:
            return False, f"檔案損壞或無法讀取: {path.name}"

        # 檢查 3: 非空
        if df.empty:
            reason = "資料為空"
            return self.allow_empty, reason

        # 檢查 4: 最低筆數
        if len(df) < self.min_rows:
            return False, f"資料筆數過少 ({len(df)} < {self.min_rows}): {path.name}"

        # 檢查 5: 必要欄位
        if self.required_columns:
            missing = [c for c in self.required_columns if c not in df.columns]
            if missing:
                return False, f"缺少欄位: {missing}"

        # 檢查 6: 日期範圍覆蓋
        date_col = 'date' if 'date' in df.columns else None
        file_start = None
        file_end = None

        if date_col is not None:
            df_dates = _normalize_date_column(df[[date_col]])[date_col]
            valid_dates = df_dates.dropna()
            if not valid_dates.empty:
                file_start = valid_dates.min()
                file_end = valid_dates.max()

        if start_date or end_date:
            if date_col is None or file_start is None:
                return True, "無日期欄位但其他檢查通過"

            if start_date:
                start_dt = _normalize_timestamp(start_date)
                if file_start > start_dt:
                    return False, (
                        f"快取起始日期 {file_start.date()} 晚於需求 {start_date}，"
                        f"需要重新下載: {path.name}"
                    )

            if end_date:
                end_dt = _normalize_timestamp(end_date)
                if file_end < end_dt:
                    return False, (
                        f"快取結束日期 {file_end.date()} 早於需求 {end_date}，"
                        f"需要重新下載: {path.name}"
                    )

        if file_start is not None and file_end is not None:
            return True, f"驗證通過 ({len(df)} 筆, {file_start.date()}~{file_end.date()})"
        return True, f"驗證通過 ({len(df)} 筆)"

    def validate_and_read(
        self,
        file_path: Union[str, Path],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        一步驟：驗證 + 讀取。驗證失敗不會拋例外，直接回 None。
        """
        is_valid, reason = self.validate(file_path, start_date, end_date)
        if not is_valid:
            logger.info(f"[CacheValidator] 跳過无效快取: {reason}")
            return None
        df = read_parquet_safe(file_path)

        # 讀取後再過濾日期（確保嚴格符合需求）
        if df is not None and (start_date or end_date):
            date_col = 'date' if 'date' in df.columns else None
            if date_col:
                df = _normalize_date_column(df)
                mask = pd.Series(True, index=df.index)
                if start_date:
                    mask &= df[date_col] >= _normalize_timestamp(start_date)
                if end_date:
                    mask &= df[date_col] <= _normalize_timestamp(end_date)
                df = df[mask].reset_index(drop=True)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# 4. 串流讀取器（ParquetStreamReader）- 省記憶體
# ─────────────────────────────────────────────────────────────────────────────

class ParquetStreamReader:
    """
    記憶體友善的 parquet 串流讀取器，適用於超大型檔案。

    特點：
        - 不會把整個檔案載入記憶體
        - 可依日期範圍分塊讀取
        - 適用於超長歷史數據（10+ 年）的訓練場景

    使用方式：
        reader = ParquetStreamReader('large_file.parquet')
        for chunk in reader.iter_chunks(start='2020-01-01', end='2024-12-31', chunksize=500):
            process(chunk)  # 每块 500 rows
    """

    def __init__(self, file_path: Union[str, Path]):
        self.path = Path(file_path) if isinstance(file_path, str) else file_path
        self._dataset = None
        self._schema = None

    @property
    def dataset(self):
        if self._dataset is None:
            self._dataset = pads.dataset(str(self.path))
            self._schema = self._dataset.schema
        return self._dataset

    @property
    def schema(self):
        if self._schema is None:
            _ = self.dataset  # 觸發初始化
        return self._schema

    def iter_chunks(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[List[str]] = None,
        chunksize: int = 1000,
    ) -> iter:
        """
        依序 yield DataFrame chunks。

        Args:
            start_date: 起始日期過濾（'YYYY-MM-DD'）
            end_date: 結束日期過濾（'YYYY-MM-DD'）
            columns: 只讀特定欄位
            chunksize: 每次 yield 的行數

        Yields:
            DataFrame (最多 chunksize 行)
        """
        filter_expr = self._build_date_filter(start_date, end_date)
        chunks = []

        for batch in self.dataset.to_batches(
            filter=filter_expr,
            columns=columns,
        ):
            df = batch.to_pandas(timestamp_as_object=True)
            df = _normalize_date_column(df)
            chunks.append(df)

            while len(pd.concat(chunks, ignore_index=True)) >= chunksize:
                combined = pd.concat(chunks, ignore_index=True)
                yield combined.iloc[:chunksize]
                # 保留多餘的部分，繼續累積
                leftover = combined.iloc[chunksize:].reset_index(drop=True)
                chunks = [leftover] if len(leftover) > 0 else []

        if chunks:
            yield pd.concat(chunks, ignore_index=True).reset_index(drop=True)

    def _build_date_filter(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
    ):
        """Build pyarrow dataset filter expression for date range."""
        if start_date is None and end_date is None:
            return None

        import pyarrow.compute as pc

        filters = []
        date_col = 'date'

        if start_date:
            start_ts = pd.Timestamp(start_date).timestamp()
            filters.append(pc.field(date_col) >= start_ts)

        if end_date:
            end_ts = pd.Timestamp(end_date).timestamp()
            filters.append(pc.field(date_col) <= end_ts)

        if len(filters) == 1:
            return filters[0]
        elif len(filters) == 2:
            return pc.and_(filters[0], filters[1])
        return None

    def read_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        讀取指定日期範圍的全部資料（不回傳 chunk，直接合併）。
        適合中小型檔案（< 1M rows）。
        """
        dfs = list(self.iter_chunks(start_date, end_date, columns, chunksize=5000))
        if not dfs:
            return None
        return pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]

    def get_date_range(self) -> tuple[Optional[datetime], Optional[datetime]]:
        """取得檔案內真實的日期範圍（不掃描全部，只讀 metadata）"""
        try:
            metadata = pap.read_metadata(str(self.path))
            schema = metadata.schema
            # 尝试找 date 欄位
            date_fields = [f for f in schema.names if 'date' in f.lower()]
            if not date_fields:
                return None, None

            # 讀取第一筆和最後一筆（用 filter 抓取）
            # 這裡用批次讀取取頭尾
            all_dates = []
            for batch in self.dataset.to_batches(columns=[date_fields[0]]):
                df = batch.to_pandas(timestamp_as_object=True)
                if date_fields[0] in df.columns:
                    all_dates.extend(df[date_fields[0]].dropna().tolist())
                if len(all_dates) > 10000:  #  cukup for range
                    break

            if not all_dates:
                return None, None

            return min(all_dates), max(all_dates)
        except Exception:
            return None, None


# ─────────────────────────────────────────────────────────────────────────────
# 5. 便利函式（快速呼叫）
# ─────────────────────────────────────────────────────────────────────────────

def smart_read(
    file_path: Union[str, Path],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    required_columns: Optional[List[str]] = None,
    use_stream: bool = False,
) -> Optional[pd.DataFrame]:
    """
    智慧讀取：自動選擇最快的方式。

    策略：
        - 檔案 < 50MB 且不需要過濾日期 → pd.read_parquet
        - 檔案 > 50MB 或需要日期過濾 → ParquetStreamReader
        - 讀取失敗 → 回 None

    Args:
        file_path: 檔案路徑
        start_date: 起始日期過濾
        end_date: 結束日期過濾
        required_columns: 必須包含的欄位
        use_stream: 強制使用串流模式

    Returns:
        DataFrame 或 None
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path

    if not path.exists():
        return None

    # 評估檔案大小
    file_size_mb = path.stat().st_size / (1024 * 1024)

    # 小檔案直接讀
    if file_size_mb < 50 and not use_stream and not start_date and not end_date:
        df = read_parquet_safe(path)
        if df is not None and required_columns:
            missing = [c for c in required_columns if c not in df.columns]
            if missing:
                return None
        return df

    # 大檔案或需要過濾 → 串流
    reader = ParquetStreamReader(path)
    return reader.read_range(start_date, end_date, required_columns)


# ─────────────────────────────────────────────────────────────────────────────
# 6. 快速建立驗證器的捷徑
# ─────────────────────────────────────────────────────────────────────────────

def validator_for_stock_data(min_rows: int = 100) -> CacheValidator:
    """股票 OHLCV 資料的標準驗證器"""
    return CacheValidator(
        required_columns=['date', 'open', 'high', 'low', 'close', 'volume'],
        min_rows=min_rows,
    )
