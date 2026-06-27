#!/usr/bin/env python3
"""Local tool layer for GroupA+ review agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ToolResult:
    output: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class BaseTool:
    name = "base_tool"
    description = ""

    def __call__(self, **kwargs: Any) -> ToolResult:
        try:
            return ToolResult(output=self.run(**kwargs))
        except Exception as exc:
            return ToolResult(error=str(exc))

    def run(self, **kwargs: Any) -> Any:
        raise NotImplementedError


class ToolCollection:
    """Small local equivalent of FinGenius ToolCollection."""

    def __init__(self, *tools: BaseTool) -> None:
        self.tools = tuple(tools)
        self.tool_map = {tool.name: tool for tool in tools}

    def execute(self, name: str, **tool_input: Any) -> ToolResult:
        tool = self.tool_map.get(name)
        if tool is None:
            return ToolResult(error=f"Unknown tool: {name}")
        return tool(**tool_input)


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


class LoadJsonTool(BaseTool):
    name = "load_json"
    description = "Load a local JSON file."

    def run(self, *, path: str) -> dict[str, Any]:
        return load_json(path)


class LoadLatestDailyStatusTool(BaseTool):
    name = "load_latest_daily_status"
    description = "Load latest managed GroupA+ daily status report."

    def run(self, *, latest_pointer: str = "report/group_a_plus/latest/daily_status.json") -> dict[str, Any]:
        pointer = load_json(latest_pointer)
        return {
            "pointer": pointer,
            "report": load_json(pointer["json"]),
        }


class LoadStrategyCompareTool(BaseTool):
    name = "load_strategy_compare"
    description = "Load latest managed GroupA+ vs Golden1 comparison."

    def run(self, *, latest_pointer: str = "report/group_a_plus/latest/strategy_compare.json") -> dict[str, Any]:
        pointer = load_json(latest_pointer)
        return {
            "pointer": pointer,
            "report": load_json(pointer["json"]),
        }


class LoadBaselineTool(BaseTool):
    name = "load_baseline"
    description = "Load active GroupA+ baseline pointer."

    def run(self, *, path: str = "GROUP_A_PLUS_CURRENT_BASELINE.json") -> dict[str, Any]:
        return load_json(path)


def default_review_tools() -> ToolCollection:
    return ToolCollection(
        LoadJsonTool(),
        LoadLatestDailyStatusTool(),
        LoadStrategyCompareTool(),
        LoadBaselineTool(),
    )
