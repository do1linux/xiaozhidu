from __future__ import annotations

import logging

from ..config import Settings
from .agnes import AgnesAdapter
from .base import AdapterError, BaseAdapter, Unsupported
from .xiaozhi_http import XiaozhiHTTPAdapter
from .xiaozhi_ws import XiaozhiWSAdapter

log = logging.getLogger("adapters")

__all__ = [
    "AdapterError",
    "Unsupported",
    "BaseAdapter",
    "AgnesAdapter",
    "XiaozhiHTTPAdapter",
    "XiaozhiWSAdapter",
    "build_adapters",
]


def build_adapters(s: Settings) -> list[BaseAdapter]:
    """按 ADAPTER_CHAIN 顺序构建，名字写错直接跳过并告警（不炸服务）。"""
    out: list[BaseAdapter] = []
    for name in s.adapters:
        if name == "xiaozhi_ws":
            out.append(XiaozhiWSAdapter(
                url=s.xiaozhi_ws_url,
                device_id=s.xiaozhi_device_id,
                client_id=s.xiaozhi_client_id,
                token=s.xiaozhi_token,
                timeout=s.xiaozhi_ws_timeout,
                text_frame=s.xiaozhi_text_frame,
            ))
        elif name == "xiaozhi_http":
            out.append(XiaozhiHTTPAdapter(url=s.xiaozhi_http_url, timeout=s.xiaozhi_ws_timeout))
        elif name in ("agnes", "newapi"):
            # newapi 保留为兼容别名：老 .env 里 ADAPTER_CHAIN=newapi 不必改也能跑。
            out.append(AgnesAdapter(
                base=s.agnes_base,
                key=s.agnes_key,
                model=s.agnes_model,
                timeout=s.agnes_timeout,
                prompt_file=s.system_prompt_file,
                json_mode=s.agnes_use_json_mode,
                history_turns=s.history_turns,
            ))
        else:
            log.warning("未知适配器 %r，已忽略", name)
    return out
