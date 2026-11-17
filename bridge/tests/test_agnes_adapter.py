"""agnes-ai 适配器单测：不联网，monkeypatch httpx。

重点锁定两件事：
  1. 正常返回 JSON 时原样透传；
  2. 推理模型只吐 reasoning_content 时明确报错（这是最容易踩的坑）。
"""
import pytest

from app.adapters import AgnesAdapter, build_adapters
from app.adapters.base import AdapterError
from app.config import Settings


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def _msg(content=None, reasoning=None):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"choices": [{"message": message}]}


def _adapter(monkeypatch, responses):
    """把 AgnesAdapter 内部的 httpx.AsyncClient 换成一个按序返回 responses 的假客户端。"""
    calls = []

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            calls.append((url, kw))
            r = responses[len(calls) - 1] if len(calls) <= len(responses) else responses[-1]
            if isinstance(r, Exception):
                raise r
            return r

    monkeypatch.setattr("app.adapters.agnes.httpx.AsyncClient", _Client)
    adapter = AgnesAdapter(base="https://apihub.agnes-ai.com/v1", key="sk-test",
                           model="agnes-3.0-flash")
    return adapter, calls


async def test_returns_json_content(monkeypatch):
    adapter, calls = _adapter(monkeypatch, [_Resp(_msg('{"type":"tts_reply","content":"你好"}'))])
    out = await adapter.chat("你好", "s1")
    assert out == '{"type":"tts_reply","content":"你好"}'
    assert calls[0][0] == "https://apihub.agnes-ai.com/v1/chat/completions"
    assert calls[0][1]["json"]["response_format"] == {"type": "json_object"}


async def test_reasoning_model_raises_actionable_error(monkeypatch):
    adapter, _ = _adapter(monkeypatch, [_Resp(_msg(content="", reasoning="让我想想……"))])
    with pytest.raises(AdapterError) as e:
        await adapter.chat("你好", "s1")
    assert "reasoning_content" in str(e.value)
    assert "agnes-3.0-flash" in str(e.value)


async def test_json_mode_falls_back_on_400(monkeypatch):
    adapter, calls = _adapter(monkeypatch, [
        _Resp(_msg("ignored"), status=400),
        _Resp(_msg('{"type":"tts_reply","content":"ok"}')),
    ])
    out = await adapter.chat("你好", "s1")
    assert "ok" in out
    assert len(calls) == 2
    assert "response_format" not in calls[1][1]["json"]


async def test_empty_key_raises(monkeypatch):
    adapter = AgnesAdapter(base="https://apihub.agnes-ai.com/v1", key="",
                           model="agnes-3.0-flash")
    with pytest.raises(AdapterError) as e:
        await adapter.chat("你好", "s1")
    assert "AGNES_KEY" in str(e.value)


def test_newapi_alias_builds_agnes_adapter(monkeypatch):
    monkeypatch.setenv("ADAPTER_CHAIN", "newapi")
    monkeypatch.setenv("AGNES_KEY", "sk-x")
    built = build_adapters(Settings())
    assert len(built) == 1
    assert isinstance(built[0], AgnesAdapter)
    assert built[0].name == "agnes"


def test_defaults_point_to_agnes(monkeypatch):
    for k in ("AGNES_BASE", "AGNES_KEY", "AGNES_MODEL",
              "NEWAPI_BASE", "NEWAPI_KEY", "NEWAPI_MODEL", "ADAPTER_CHAIN"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.agnes_base == "https://apihub.agnes-ai.com/v1"
    assert s.agnes_model == "agnes-3.0-flash"
    assert s.adapters == ["xiaozhi_ws", "agnes"]
