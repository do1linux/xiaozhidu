"""适配器基类：每个适配器只负责“把一句文本丢给大模型侧，拿回原始文本答案”。"""
from __future__ import annotations

import abc
from typing import Any


class AdapterError(RuntimeError):
    pass


class Unsupported(AdapterError):
    """适配器不支持当前请求形态（例如强制二次判定），不该当成故障告警。"""


class BaseAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def chat(self, query: str, session_id: str,
                   history: list[dict[str, Any]] | None = None,
                   force_answer: bool = False) -> str:
        """返回大模型侧给出的原始文本（期望是 {"type":..,"content":..} 的 JSON）。

        force_answer=True 表示"已确定这是提问，别再判成原生指令"，
        仅当适配器支持二次判定时才实现，不支持的直接抛 AdapterError 让链路跳过。
        """

    async def aclose(self) -> None:  # pragma: no cover - 可选
        return None
