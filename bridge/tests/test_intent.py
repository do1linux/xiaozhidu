import pytest

from app.intent import NATIVE, TTS, IntentJudge, parse_contract, sanitize_for_tts


@pytest.mark.parametrize("raw,expected,content", [
    ('{"type":"tts_reply","content":"你好"}', TTS, "你好"),
    ('{"type": "native_cmd", "content": "开灯"}', NATIVE, "开灯"),
    ('```json\n{"type":"tts_reply","content":"带代码块"}\n```', TTS, "带代码块"),
    ('好的，{"type":"tts_reply","content":"前面有废话"}', TTS, "前面有废话"),
    ('{"content":"键顺序反了","type":"tts_reply"}', TTS, "键顺序反了"),
    ('{type:tts_reply,content:没有引号}', TTS, "没有引号"),
    ('{"type":"native_cmd","content":"播放晴天"}', NATIVE, "播放晴天"),
])
def test_parse_contract_variants(raw, expected, content):
    p = parse_contract(raw)
    assert p.type == expected
    assert p.content == content


def test_parse_contract_fallback_is_tts():
    p = parse_contract("滨湖有三个板块在售。")
    assert p.type == TTS
    assert "滨湖" in p.content


def test_parse_contract_empty_is_native():
    assert parse_contract("").type == NATIVE


def test_fastpath_hits_device_control():
    j = IntentJudge(fastpath=True, question_guard=True)
    for q in ["开灯", "帮我关掉客厅灯", "把卧室灯打开", "下一首", "静音", "空调调到26度"]:
        assert j.looks_native(q), q


def test_fastpath_never_hits_questions():
    j = IntentJudge(fastpath=True, question_guard=True)
    for q in ["开灯怎么设置定时", "播放晴天这首歌是谁唱的", "滨湖有哪些新楼盘",
              "帮我写一句文案", "灯是什么牌子的"]:
        assert not j.looks_native(q), q


def test_question_guard_overrides_model_native():
    j = IntentJudge(fastpath=False, question_guard=True)
    rtype, content, reason = j.decide(
        "客厅灯有哪些品牌", '{"type":"native_cmd","content":"客厅灯有哪些品牌"}')
    assert rtype == TTS
    assert reason.startswith("guard")


def test_native_passthrough_when_confident():
    j = IntentJudge(fastpath=False, question_guard=True)
    rtype, content, _ = j.decide("播放晴天", '{"type":"native_cmd","content":"播放晴天"}')
    assert (rtype, content) == (NATIVE, "播放晴天")


def test_tts_content_sanitized():
    j = IntentJudge(fastpath=False)
    rtype, content, _ = j.decide(
        "滨湖楼盘", '{"type":"tts_reply","content":"**省府**板块 [详情](https://a.com) 不错"}')
    assert rtype == TTS
    out = sanitize_for_tts(content, 300)
    assert "*" not in out and "http" not in out and "详情" in out


def test_sanitize_truncates_on_sentence_boundary():
    text = "第一句话在这里。" * 40
    out = sanitize_for_tts(text, 100)
    assert len(out) <= 100
    assert out.endswith("。")


def test_sanitize_strips_brackets_and_urls():
    out = sanitize_for_tts("看这里 https://x.com/a 然后（备注）结束")
    assert "https" not in out


def test_fullwidth_colon_in_content_preserved():
    """全角冒号/弯引号只在键值结构上放宽，正文必须原样保留。"""
    p = parse_contract('{"type"："tts_reply","content"："结论：可以，明天上午更好。"}')
    assert p.type == TTS
    assert p.content == "结论：可以，明天上午更好。"


def test_content_with_inner_quotes():
    p = parse_contract('{"type":"tts_reply","content":"他说“好”然后走了"}')
    assert p.type == TTS
    assert p.content == "他说“好”然后走了"
