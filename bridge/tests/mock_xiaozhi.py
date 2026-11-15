"""一个会说 xiaozhi v1 协议的假服务器，用来在不装 xiaozhi 的情况下验证链路。

行为：收到 hello 回 hello；收到带 text 的 listen 帧后，先发 stt，再把答案
按两段 sentence_start 发出来（故意拆段，验证适配器能拼回去），最后发 stop。
"""
from __future__ import annotations

import asyncio
import json

try:
    from websockets.asyncio.server import serve
except ImportError:  # websockets < 13
    from websockets.server import serve  # type: ignore


def answer_for(text: str) -> str:
    if "楼盘" in text:
        return json.dumps(
            {"type": "tts_reply", "content": "滨湖这边省府和金融板块都有新盘。"},
            ensure_ascii=False,
        )
    if "开灯" in text or "播放" in text:
        return json.dumps({"type": "native_cmd", "content": text}, ensure_ascii=False)
    return json.dumps({"type": "tts_reply", "content": "我不知道该说什么。"},
                      ensure_ascii=False)


async def handler(ws):
    session_id = "mock-session-1"
    async for raw in ws:
        if isinstance(raw, (bytes, bytearray)):
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        t = msg.get("type")
        if t == "hello":
            await ws.send(json.dumps({
                "type": "hello", "session_id": session_id, "transport": "websocket",
                "audio_params": msg.get("audio_params", {}),
            }))
        elif t == "listen" and msg.get("text"):
            text = msg["text"]
            await ws.send(json.dumps({"type": "stt", "text": text}, ensure_ascii=False))
            await ws.send(json.dumps({"type": "tts", "state": "start"}, ensure_ascii=False))
            ans = answer_for(text)
            mid = max(1, len(ans) // 2)
            for piece in (ans[:mid], ans[mid:]):
                await ws.send(json.dumps(
                    {"type": "tts", "state": "sentence_start", "text": piece},
                    ensure_ascii=False))
                await asyncio.sleep(0.01)
            await ws.send(json.dumps({"type": "tts", "state": "stop"}, ensure_ascii=False))
        elif t == "listen" and msg.get("state") == "stop":
            await ws.send(json.dumps({"type": "goodbye"}, ensure_ascii=False))
            break


async def serve_mock(port: int = 0):
    server = await serve(handler, "127.0.0.1", port)
    # 兼容不同版本的 sockets 属性名
    sock = getattr(server, "sockets", None)
    if sock:
        port = sock[0].getsockname()[1]
    else:  # pragma: no cover
        port = server.server.sockets[0].getsockname()[1]
    return server, port


if __name__ == "__main__":
    async def _main():
        srv, p = await serve_mock(8765)
        print(f"mock xiaozhi listening on ws://127.0.0.1:{p}/xiaozhi/v1/")
        await asyncio.Future()
    asyncio.run(_main())
