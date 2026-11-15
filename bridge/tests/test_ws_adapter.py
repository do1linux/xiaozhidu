"""端到端验证：假 xiaozhi + 真适配器，确保协议帧处理是对的。"""
import pytest

from app.adapters.xiaozhi_ws import XiaozhiWSAdapter
from app.intent import parse_contract
from tests.mock_xiaozhi import serve_mock


@pytest.fixture()
async def mock_url():
    server, port = await serve_mock(0)
    try:
        yield f"ws://127.0.0.1:{port}/xiaozhi/v1/"
    finally:
        server.close()
        await server.wait_closed()


async def test_ws_adapter_collects_split_sentences(mock_url):
    adapter = XiaozhiWSAdapter(url=mock_url, device_id="t-1", timeout=10)
    raw = await adapter.chat("滨湖这边有哪些新楼盘", "s1")
    parsed = parse_contract(raw)
    assert parsed.type == "tts_reply"
    assert "省府" in parsed.content


async def test_ws_adapter_native(mock_url):
    adapter = XiaozhiWSAdapter(url=mock_url, device_id="t-1", timeout=10)
    raw = await adapter.chat("开灯", "s1")
    assert parse_contract(raw).type == "native_cmd"
