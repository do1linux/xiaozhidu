"""bot 侧纯逻辑测试：不需要小米账号，也不需要真音箱。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xiaoai_bot import XiaoaiBot, split_for_tts  # noqa: E402


def make_bot(**opts) -> XiaoaiBot:
    cfg = {
        "hardware": "LX06",
        "account": "u",
        "password": "p",
        "bot_options": {"pre_tts_delay": 0, "mute_before_tts": False, **opts},
    }
    return XiaoaiBot(cfg)


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, payload=None, status=200, exc=None):
        self.payload = payload or {}
        self.status = status
        self.exc = exc
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append(json)
        if self.exc:
            raise self.exc
        return FakeResp(self.payload, self.status)

    async def get(self, *a, **kw):
        return FakeResp({"ok": True})


def make_recorder(sink: list):
    async def _speak(text: str) -> None:
        sink.append(text)
    return _speak


def drain(bot: XiaoaiBot, rec: dict) -> None:
    asyncio.run(bot.handle(rec))


def test_split_keeps_chunks_under_limit():
    text = "第一句比较短。第二句稍微长一点点，还带个逗号；第三句也不长！" * 3
    chunks = split_for_tts(text, 12)
    assert chunks
    assert all(len(c) <= 12 for c in chunks), chunks
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_split_empty():
    assert split_for_tts("") == []


def test_native_cmd_does_not_speak():
    bot = make_bot()
    bot._http = FakeHTTP({"type": "native_cmd", "content": "播放晴天", "meta": {"reason": "fastpath"}})
    spoke = []
    bot.speak = make_recorder(spoke)
    drain(bot, {"query": "播放晴天", "requestId": "r1", "time": 1})
    assert spoke == []
    assert bot.stats["native"] == 1


def test_tts_reply_speaks_content():
    bot = make_bot()
    bot._http = FakeHTTP({"type": "tts_reply", "content": "滨湖有三个板块", "meta": {}})
    spoke = []
    bot.speak = make_recorder(spoke)
    drain(bot, {"query": "滨湖有哪些新楼盘", "requestId": "r2", "time": 2})
    assert spoke == ["滨湖有三个板块"]
    assert bot.stats["tts"] == 1


def test_duplicate_record_ignored():
    bot = make_bot()
    bot._http = FakeHTTP({"type": "tts_reply", "content": "x", "meta": {}})
    spoke = []
    bot.speak = make_recorder(spoke)
    rec = {"query": "讲个笑话", "requestId": "same", "time": 3}
    drain(bot, rec)
    drain(bot, rec)
    assert len(spoke) == 1


def test_skip_queries_and_short_text():
    bot = make_bot()
    bot._http = FakeHTTP({"type": "tts_reply", "content": "x", "meta": {}})
    drain(bot, {"query": "小爱同学", "requestId": "a"})
    drain(bot, {"query": "嗯", "requestId": "b"})
    assert bot._http.calls == []
    assert bot.stats["skip"] == 2


def test_blocked_pattern():
    bot = make_bot(blocked_patterns=[r"^测试"])
    bot._http = FakeHTTP({"type": "tts_reply", "content": "x", "meta": {}})
    drain(bot, {"query": "测试一下链路", "requestId": "c"})
    assert bot._http.calls == []


def test_bridge_failure_does_not_crash():
    bot = make_bot()
    bot._http = FakeHTTP(exc=RuntimeError("connection refused"))
    drain(bot, {"query": "今天天气怎么样", "requestId": "d"})
    assert bot.stats["error"] == 1


def test_payload_shape_sent_to_bridge():
    bot = make_bot()
    bot.device_id = "dev123"
    bot._http = FakeHTTP({"type": "native_cmd", "content": "", "meta": {}})
    drain(bot, {"query": "开灯", "requestId": "e"})
    sent = bot._http.calls[0]
    assert sent["query"] == "开灯"
    assert sent["session_id"] == "xiaoai-dev123"
    assert sent["device_id"] == "dev123"
