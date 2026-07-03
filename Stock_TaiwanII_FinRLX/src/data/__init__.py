# src/data/__init__.py
"""Data loading and processing — 台股資料處理。"""
from .data_loader import TaiwanDataLoader, load_taiwan_stocks

__all__ = ["TaiwanDataLoader", "load_taiwan_stocks"]