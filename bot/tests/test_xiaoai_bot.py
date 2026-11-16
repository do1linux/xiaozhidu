"""bot 侧纯逻辑测试：不需要小米账号，也不需要真音箱。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xiaoai_bot import XiaoaiBot, split_for_tts, tts_wait_seconds  # noqa: E402
from local_tts import EdgeVoice, DEFAULT_VOICE  # noqa: E402


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


# ---- TTS 段间等待：锁死「每字秒数」语义，防止再退化成除法 -----------------

def test_tts_wait_scales_with_length_not_divides():
    # 80 字 * 190ms = 15.2 秒；旧实现 len/0.19 = 421 秒，差 27 倍
    wait = tts_wait_seconds("汉" * 80, 190)
    assert abs(wait - 15.2) < 0.001


def test_tts_wait_respects_custom_delay():
    assert abs(tts_wait_seconds("12345", 100) - 0.5) < 0.001


def test_tts_wait_zero_and_bad_delay_are_safe():
    assert tts_wait_seconds("任意文本", 0) == 0.0
    # 非法配置回退到默认 190ms，不抛异常
    assert abs(tts_wait_seconds("abc", "bad") - 0.57) < 0.001


# ---- 本地 edge-tts（台湾腔女声）----------------------------------------------

def test_default_voice_is_taiwanese_female():
    assert DEFAULT_VOICE == "zh-TW-HsiaoChenNeural"


def test_edge_voice_synth_and_player_injected(tmp_path):
    """合成与播放都注入，验证调用顺序、文本传递与临时文件清理。"""
    seen = {}

    async def fake_synth(text, path):
        seen["synth_text"] = text
        seen["synth_path"] = path
        with open(path, "wb") as f:
            f.write(b"fake-mp3")

    async def fake_player(path):
        seen["played"] = path
        with open(path, "rb") as f:
            seen["bytes"] = f.read()

    v = EdgeVoice(synth=fake_synth, player=fake_player)
    asyncio.run(v.speak("欢迎光临"))

    assert seen["synth_text"] == "欢迎光临"
    assert seen["played"] == seen["synth_path"]
    assert seen["bytes"] == b"fake-mp3"
    # 播完即删，不落用户数据
    assert not __import__("os").path.exists(seen["synth_path"])


def test_edge_voice_forwards_voice_and_rate(tmp_path):
    """音色/语速等参数要传给注入的合成器默认值之外的路径由实现保证。"""
    captured = {}

    async def fake_synth(text, path):
        with open(path, "wb") as f:
            f.write(b"x")

    async def fake_player(path):
        pass

    v = EdgeVoice(voice="zh-TW-HsiaoYuNeural", rate="+10%",
                  synth=fake_synth, player=fake_player)
    assert v.voice == "zh-TW-HsiaoYuNeural"
    assert v.rate == "+10%"
    asyncio.run(v.speak("你好"))


def test_bot_edge_backend_uses_local_voice_not_mina():
    """edge 模式绝不调用小爱播放器（声音从 PC 出，两个出口分家）。"""
    bot = make_bot(tts_backend="edge", pre_tts_delay=0)
    called = {"mina": False}

    async def fake_mina(*a, **kw):
        called["mina"] = True

    bot.mina = type("M", (), {
        "player_get_status": fake_mina,
        "player_pause": fake_mina,
        "text_to_speech": fake_mina,
    })()

    seen = {}

    async def fake_synth(text, path):
        seen["text"] = text
        with open(path, "wb") as f:
            f.write(b"x")

    async def fake_player(path):
        seen["played"] = True

    bot._edge_voice = EdgeVoice(synth=fake_synth, player=fake_player)
    asyncio.run(bot.speak("台湾腔测试"))

    assert seen.get("text") == "台湾腔测试"
    assert seen.get("played") is True
    assert called["mina"] is False


def test_bot_mi_backend_still_uses_mina():
    """默认 mi 模式保持原行为：仍走小爱 text_to_speech。"""
    bot = make_bot(pre_tts_delay=0, tts_chunk=80, tts_char_delay_ms=0)
    chunks = []

    async def fake_tts(device, chunk):
        chunks.append(chunk)

    bot.mina = type("M", (), {
        "player_get_status": staticmethod(lambda *a: None),
        "player_pause": staticmethod(lambda *a: None),
        "text_to_speech": staticmethod(fake_tts),
    })()
    bot.opts["mute_before_tts"] = False

    asyncio.run(bot.speak("小爱原声"))
    assert "".join(chunks) == "小爱原声"
