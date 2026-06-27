#!/usr/bin/env python3
"""Small JSON output standard for Taiwan strategy utilities."""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from enum import Enum
from typing import Any


class OutputType(str, Enum):
    TABLE = "table"
    DICT = "dict"
    ARRAY = "array"
    TEXT = "text"
    NUMBER = "number"
    ERROR = "error"
    EMPTY = "empty"


class OutputStandardizer:
    VERSION = "1.0.0"

    def __init__(self, script_name: str = "unknown") -> None:
        self.script_name = script_name
        self.start_time = time.time()

    def success(self, data: Any, output_type: OutputType | None = None, **metadata: Any) -> dict[str, Any]:
        return {
            "success": True,
            "data": self._convert(data),
            "metadata": {
                "script": self.script_name,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "output_type": str(output_type or self._detect_type(data)),
                "version": self.VERSION,
                "execution_time_ms": int((time.time() - self.start_time) * 1000),
                **metadata,
            },
            "error": None,
        }

    def error(self, exc: BaseException | str, **metadata: Any) -> dict[str, Any]:
        message = str(exc)
        err_type = type(exc).__name__ if isinstance(exc, BaseException) else "Error"
        return {
            "success": False,
            "data": None,
            "metadata": {
                "script": self.script_name,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "output_type": OutputType.ERROR.value,
                "version": self.VERSION,
                "execution_time_ms": int((time.time() - self.start_time) * 1000),
                **metadata,
            },
            "error": {
                "message": message,
                "type": err_type,
                "traceback": traceback.format_exc() if isinstance(exc, BaseException) else "",
            },
        }

    def _detect_type(self, data: Any) -> OutputType:
        if data is None:
            return OutputType.EMPTY
        try:
            import pandas as pd

            if isinstance(data, pd.DataFrame):
                return OutputType.TABLE
            if isinstance(data, pd.Series):
                return OutputType.ARRAY
        except Exception:
            pass
        if isinstance(data, dict):
            return OutputType.DICT
        if isinstance(data, (list, tuple)):
            return OutputType.ARRAY
        if isinstance(data, str):
            return OutputType.TEXT
        if isinstance(data, (int, float)):
            return OutputType.NUMBER
        return OutputType.DICT

    def _convert(self, data: Any) -> Any:
        try:
            import pandas as pd

            if isinstance(data, pd.DataFrame):
                return {
                    "columns": list(data.columns),
                    "rows": data.where(pd.notna(data), None).to_dict(orient="records"),
                    "row_count": int(len(data)),
                }
            if isinstance(data, pd.Series):
                return data.where(pd.notna(data), None).tolist()
        except Exception:
            pass
        return _jsonable(data)


def _jsonable(value: Any) -> Any:
    try:
        import numpy as np
        import pandas as pd

        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (pd.Timestamp,)):
            return value.isoformat()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def write_standard_output(payload: dict[str, Any], path: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if path:
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


def standardize_success(data: Any, script_name: str, output_type: OutputType | None = None, **metadata: Any) -> dict[str, Any]:
    return OutputStandardizer(script_name).success(data, output_type, **metadata)


def standardize_error(exc: BaseException | str, script_name: str, **metadata: Any) -> dict[str, Any]:
    return OutputStandardizer(script_name).error(exc, **metadata)
