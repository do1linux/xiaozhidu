"""xiaozhi-esp32-server 的「虚拟设备」适配器（不需要改 xiaozhi 一行源码）。

原理：xiaozhi 的 WebSocket 协议本来就是给 ESP32 设备用的，而"设备"只要求
能发 hello、能发一条带 text 的 listen 帧。我们用 Python 伪装成一个设备，
把文本塞进去，再把 tts 的 sentence_start 文本收集回来——等于复用了
xiaozhi 内部的 LLM + MCP + 意图逻辑，但不需要任何 ESP32 硬件。

协议要点（v1）：
  → {"type":"hello","version":1,"transport":"websocket","audio_params":{...}}
  ← {"type":"hello","session_id":"...","audio_params":{...}}
  → {"session_id":"..","type":"listen","state":"detect","text":"用户这句话"}
  ← {"type":"tts","state":"sentence_start","text":"..."}   (可能多段)
  ← {"type":"tts","state":"stop"}                            (本轮结束)

注意：不同版本对“纯文本输入”的支持方式略有差异，所以注入帧做成
模板（XIAOZHI_TEXT_FRAME），改环境变量即可适配，不必改代码。
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import uuid

from .base import AdapterError, BaseAdapter, Unsupported

log = logging.getLogger("adapter.xiaozhi_ws")

HELLO = {
    "type": "hello",
    "version": 1,
    "transport": "websocket",
    "audio_params": {
        "format": "opus",
        "sample_rate": 24000,
        "channels": 1,
        "frame_duration": 60,
    },
}


class XiaozhiWSAdapter(BaseAdapter):
    name = "xiaozhi_ws"

    def __init__(self, url: str, device_id: str, client_id: str = "voice-bridge",
                 token: str = "", timeout: float = 40.0, text_frame: str | None = None):
        self.base_url = url
        self.device_id = device_id
        self.client_id = client_id
        self.token = token
        self.timeout = timeout
        self.text_frame = text_frame or (
            '{"session_id":"{session_id}","type":"listen","state":"detect","text":"{text}"}'
        )

    def _url(self) -> str:
        sep = "&" if "?" in self.base_url else "?"
        url = f"{self.base_url}{sep}device-id={self.device_id}&client-id={self.client_id}"
        if self.token:
            url += f"&token={self.token}"
        return url

    async def chat(self, query, session_id, history=None, force_answer: bool = False) -> str:
        if force_answer:
            # xiaozhi 侧无法在单轮内"重判"，交给链路上的下一个适配器
            raise Unsupported("xiaozhi_ws 不支持强制作答二次判定")
        try:
            from websockets.asyncio.client import connect
        except ImportError:  # 兼容旧版 websockets
            from websockets import connect  # type: ignore

        deadline = time.monotonic() + self.timeout
        sentences: list[str] = []
        fallback: list[str] = []
        got_any = False

        try:
            async with connect(
                self._url(),
                max_size=None,
                open_timeout=10,
                additional_headers=_headers(),
                ssl=_ssl_ctx(self._url()),
            ) as ws:
                await ws.send(json.dumps(HELLO, ensure_ascii=False))
                # 服务端可能先推几帧 iot/mcp 状态，再回 hello，所以循环找
                hello = None
                deadline_hello = time.monotonic() + min(10.0, self.timeout)
                while time.monotonic() < deadline_hello:
                    head = await _recv_json(ws, max(1.0, deadline_hello - time.monotonic()))
                    if head is None:
                        break
                    if head.get("type") == "hello":
                        hello = head
                        break
                if not hello:
                    raise AdapterError("xiaozhi 未按协议回 hello（检查 URL 路径与 device-id 鉴权）")
                sid = hello.get("session_id") or f"vb-{uuid.uuid4().hex[:8]}"

                # 模板里有大量 JSON 花括号，不能用 str.format，直接字符串替换
                frame = (
                    self.text_frame
                    .replace("{session_id}", sid)
                    .replace("{text}", json.dumps(query, ensure_ascii=False)[1:-1])
                )
                await ws.send(frame)

                while True:
                    remain = deadline - time.monotonic()
                    if remain <= 0:
                        log.warning("xiaozhi ws 超时，已收集 %d 段", len(sentences))
                        break
                    item = await _recv(ws, remain)
                    if item is None:
                        break
                    if isinstance(item, (bytes, bytearray)):
                        continue  # 音频帧直接丢弃：TTS 由小爱侧负责
                    try:
                        msg = json.loads(item)
                    except Exception:
                        continue
                    t = msg.get("type")
                    if t == "tts":
                        state = msg.get("state")
                        if state == "sentence_start":
                            txt = (msg.get("text") or "").strip()
                            if txt:
                                sentences.append(txt)
                                got_any = True
                        elif state == "stop":
                            break
                    elif t in ("stt", "llm"):
                        txt = (msg.get("text") or "").strip()
                        if txt:
                            fallback.append(txt)
                    elif t in ("goodbye", "error"):
                        if t == "error":
                            log.warning("xiaozhi 返回错误帧，type=%s", msg.get("type"))
                        break
                    # 其余类型（iot/mcp/alert/audio 控制）一律忽略

                # 礼貌收尾，让 xiaozhi 尽快释放这一轮会话
                try:
                    await ws.send(json.dumps(
                        {"session_id": sid, "type": "listen", "state": "stop"},
                        ensure_ascii=False,
                    ))
                except Exception:
                    pass
        except AdapterError:
            raise
        except Exception as e:  # 连接失败/协议不符 → 交给上层降级
            raise AdapterError(f"xiaozhi_ws 调用失败: {e}") from e

        answer = "".join(sentences).strip()
        if not answer and fallback:
            answer = fallback[-1]
        if not answer and not got_any:
            raise AdapterError("xiaozhi_ws 未返回任何文本")
        return answer


def _headers() -> dict:
    return {"User-Agent": "voice-bridge/1.0", "Protocol-Version": "1"}


def _ssl_ctx(url: str):
    return ssl.create_default_context() if url.startswith("wss://") else None


async def _recv(ws, timeout: float):
    try:
        return await asyncio.wait_for(ws.recv(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


async def _recv_json(ws, timeout: float):
    raw = await _recv(ws, timeout)
    if isinstance(raw, (bytes, bytearray)) or raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
