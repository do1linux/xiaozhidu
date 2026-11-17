import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import AdapterError, BaseAdapter, Unsupported
from app.main import app


class FakeAdapter(BaseAdapter):
    def __init__(self, reply: str = "", fail: bool = False,
                 retry_reply: str | None = None, name: str = "fake"):
        self.reply = reply
        self.fail = fail
        self.retry_reply = retry_reply
        self.name = name
        self.calls: list[str] = []
        self.retry_calls = 0
        self.histories: list[list] = []

    async def chat(self, query, session_id, history=None, force_answer=False):
        if force_answer:
            self.retry_calls += 1
            if self.retry_reply is None:
                raise Unsupported("不支持强制作答")   # 与 xiaozhi_ws 行为一致
            return self.retry_reply
        self.calls.append(query)
        self.histories.append(history or [])
        if self.fail:
            raise AdapterError("boom")
        return self.reply


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def set_adapters(client, *adapters):
    app.state.st.adapters = list(adapters)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_fastpath_native_skips_llm(client):
    fake = FakeAdapter('{"type":"tts_reply","content":"不该被调用"}')
    set_adapters(client, fake)
    r = client.post("/api/text_chat", json={"query": "帮我关掉客厅灯"})
    body = r.json()
    assert body["type"] == "native_cmd"
    assert body["content"] == "帮我关掉客厅灯"
    assert body["meta"]["reason"] == "fastpath"
    assert fake.calls == []


def test_tts_reply_path(client):
    fake = FakeAdapter(json.dumps(
        {"type": "tts_reply", "content": "**滨湖**有省府、金融板块 [详情](https://x.com)"},
        ensure_ascii=False))
    set_adapters(client, fake)
    r = client.post("/api/text_chat", json={"query": "滨湖这边有哪些新楼盘"})
    body = r.json()
    assert body["type"] == "tts_reply"
    assert "省府" in body["content"]
    assert "*" not in body["content"] and "http" not in body["content"]
    assert body["meta"]["adapter"] == "fake"
    assert fake.calls == ["滨湖这边有哪些新楼盘"]


def test_native_passthrough_from_llm(client):
    set_adapters(client, FakeAdapter('{"type":"native_cmd","content":"播放晴天"}'))
    body = client.post("/api/text_chat", json={"query": "播放晴天"}).json()
    assert body["type"] == "native_cmd"
    assert body["content"] == "播放晴天"


def test_question_guard_falls_back_to_reply(client):
    """模型想直接执行、但明显是提问：护栏顶掉，且不能沉默。"""
    set_adapters(client, FakeAdapter('{"type":"native_cmd","content":"客厅灯有哪些品牌"}'))
    body = client.post("/api/text_chat", json={"query": "客厅灯有哪些品牌"}).json()
    assert body["type"] == "tts_reply"
    assert body["content"]
    assert body["meta"]["reason"].startswith("guard")


def test_guard_retry_asks_second_adapter(client):
    first = FakeAdapter('{"type":"native_cmd","content":"播放晴天是谁唱的"}', name="ws")
    second = FakeAdapter('{"type":"tts_reply","content":"不相关"}',
                         retry_reply='{"type":"tts_reply","content":"周杰伦，2003 年。"}',
                         name="newapi")
    set_adapters(client, first, second)
    body = client.post("/api/text_chat", json={"query": "播放晴天这首歌是谁唱的"}).json()
    assert body["type"] == "tts_reply"
    assert "周杰伦" in body["content"]
    assert body["meta"]["reason"] == "guard_retry:newapi"
    assert first.retry_calls == 1 and second.retry_calls == 1


def test_guard_retry_still_native_means_do_nothing(client):
    first = FakeAdapter('{"type":"native_cmd","content":"播放晴天是谁唱的"}', name="ws")
    second = FakeAdapter(retry_reply='{"type":"native_cmd","content":"播放晴天是谁唱的"}',
                         name="newapi")
    set_adapters(client, first, second)
    body = client.post("/api/text_chat", json={"query": "播放晴天这首歌是谁唱的"}).json()
    assert body["type"] == "native_cmd"
    assert body["content"] == ""


def test_noise_is_swallowed(client):
    fake = FakeAdapter('{"type":"tts_reply","content":"x"}')
    set_adapters(client, fake)
    body = client.post("/api/text_chat", json={"query": "小爱同学"}).json()
    assert body["type"] == "native_cmd"
    assert body["content"] == ""
    assert fake.calls == []


def test_fallback_chain(client):
    bad = FakeAdapter(fail=True)
    good = FakeAdapter('{"type":"tts_reply","content":"备用链路兜住了"}')
    set_adapters(client, bad, good)
    body = client.post("/api/text_chat", json={"query": "你好呀今天怎么样"}).json()
    assert body["type"] == "tts_reply"
    assert body["meta"]["adapter"] == "fake"
    assert "备用" in body["content"]


def test_all_adapters_down(client):
    set_adapters(client, FakeAdapter(fail=True))
    r = client.post("/api/text_chat", json={"query": "今天天气怎么样"})
    assert r.status_code == 502
    assert "errors" in r.json()["detail"]


def test_recent_endpoint_records_calls(client):
    set_adapters(client, FakeAdapter('{"type":"tts_reply","content":"好"}'))
    client.post("/api/text_chat", json={"query": "讲个笑话吧"})
    items = client.get("/api/recent").json()["items"]
    assert items and items[-1]["reason"] == "llm:json"
    assert "q" not in items[-1]          # 默认不落用户语音原文
    assert items[-1]["q_len"] == len("讲个笑话吧")


def test_history_passed_when_enabled(client):
    st = app.state.st
    old = st.settings.history_turns
    st.settings.history_turns = 2
    try:
        fake = FakeAdapter('{"type":"tts_reply","content":"第一轮回答"}')
        set_adapters(client, fake)
        client.post("/api/text_chat", json={"query": "滨湖有哪些板块", "session_id": "s1"})
        client.post("/api/text_chat", json={"query": "那第二个呢", "session_id": "s1"})
        assert fake.histories[0] == []
        assert fake.histories[1][-1]["q"] == "滨湖有哪些板块"
    finally:
        st.settings.history_turns = old


def test_history_off_by_default(client):
    fake = FakeAdapter('{"type":"tts_reply","content":"回答"}')
    set_adapters(client, fake)
    client.post("/api/text_chat", json={"query": "随便问问天气怎样", "session_id": "s2"})
    assert fake.histories[0] == []


def test_log_default_never_writes_text(client, tmp_path):
    st = app.state.st
    st._log_path = str(tmp_path / "bridge.jsonl")
    assert st.settings.log_text is False
    set_adapters(client, FakeAdapter('{"type":"tts_reply","content":"滨湖有三个板块"}'))
    client.post("/api/text_chat", json={"query": "滨湖有哪些新楼盘", "session_id": "privacy"})
    written = (tmp_path / "bridge.jsonl").read_text(encoding="utf-8")
    assert "滨湖有哪些新楼盘" not in written
    assert "滨湖有三个板块" not in written
    assert "tts_reply" in written


def test_log_disabled_never_writes_file(client, tmp_path):
    """LOG_ENABLED=false：连元数据都不落盘，只在内存 recent 里留着。"""
    st = app.state.st
    st._log_path = str(tmp_path / "bridge.jsonl")
    old = st.settings.log_enabled
    st.settings.log_enabled = False
    try:
        set_adapters(client, FakeAdapter('{"type":"tts_reply","content":"回答"}'))
        client.post("/api/text_chat", json={"query": "随便问问天气怎样", "session_id": "nolog"})
        assert not (tmp_path / "bridge.jsonl").exists()
        # 内存缓冲不受影响，多轮/排障仍可用
        assert st.recent
    finally:
        st.settings.log_enabled = old


def test_log_text_opt_in(client, tmp_path):
    st = app.state.st
    st._log_path = str(tmp_path / "bridge.jsonl")
    st.settings.log_text = True
    try:
        set_adapters(client, FakeAdapter('{"type":"tts_reply","content":"滨湖有三个板块"}'))
        client.post("/api/text_chat", json={"query": "滨湖有哪些新楼盘", "session_id": "privacy2"})
        written = (tmp_path / "bridge.jsonl").read_text(encoding="utf-8")
        assert "滨湖有哪些新楼盘" in written
    finally:
        st.settings.log_text = False
