"""xiaozhi 版本若已自带 /internal/text_chat 文本接口，走这条更省事（无音频协商）。"""
from __future__ import annotations

import logging

import httpx

from .base import AdapterError, BaseAdapter

log = logging.getLogger("adapter.xiaozhi_http")


class XiaozhiHTTPAdapter(BaseAdapter):
    name = "xiaozhi_http"

    def __init__(self, url: str, timeout: float = 40.0):
        self.url = url
        self.timeout = timeout

    async def chat(self, query, session_id, history=None, force_answer: bool = False) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self.url, json={"query": query, "session_id": session_id}
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            raise AdapterError(f"xiaozhi_http 调用失败: {e}") from e

        # 兼容两种返回：已经分了类型 / 只给一段文本
        if isinstance(data, dict):
            if data.get("type") in ("native_cmd", "tts_reply"):
                import json as _json
                return _json.dumps(data, ensure_ascii=False)
            for key in ("content", "text", "answer", "reply"):
                if isinstance(data.get(key), str):
                    return data[key]
        if isinstance(data, str):
            return data
        raise AdapterError(f"xiaozhi_http 返回结构无法识别: {data!r}")
