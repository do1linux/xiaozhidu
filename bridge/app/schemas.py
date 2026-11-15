"""请求/响应契约。

上行（xiaogpt 侧）: {"query": "...", "session_id": "...", "device_id": "..."}
下行            : {"type": "native_cmd" | "tts_reply", "content": "...", "meta": {...}}
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ResultType = Literal["native_cmd", "tts_reply"]


class ChatReq(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str = "default-session"
    device_id: Optional[str] = None


class ChatResp(BaseModel):
    type: ResultType
    content: str = ""
    # meta 不参与业务，只用于排障：判断是哪一层给出的结论、耗时多久
    meta: dict = Field(default_factory=dict)


class ClassifyReq(BaseModel):
    query: str
    session_id: str = "default-session"
