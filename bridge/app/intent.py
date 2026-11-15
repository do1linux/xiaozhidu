"""意图判定：把上游（LLM）返回的文本收敛成 native_cmd / tts_reply 两种结论。

设计要点：
1. 解析必须"抗摧残"。xiaozhi 的 TTS 流水线会把句子切段、可能吃掉引号和花括号，
   所以 JSON 原文经常面目全非（type:tts_reply,content:你好）。这里用
   「严格 JSON → raw_decode → 宽松正则」三级降级。
2. 判定错误的代价不对称：
   - 提问误判成 native  → 用户完全得不到回答（严重）
   - native 误判成 tts   → 小爱已经执行过了，只是多说一段话（轻微）
   所以兜底一律偏向 tts_reply，并且加疑问句强制改判。
3. 规则快筛只放"没有第二种解释"的句式，宁可漏，不可错。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

NATIVE = "native_cmd"
TTS = "tts_reply"

# ---------------------------------------------------------------- 解析

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
# 兼容被 TTS 处理过的退化形态：type:tts_reply / "type" ： "native_cmd"
# 注意：只对"键值结构"放宽全角冒号/弯引号，绝不改写正文——否则"好的：马上"会被改标点。
_TYPE_RE = re.compile(r'["“”\']?type["“”\']?\s*[:：=]\s*["“”\']?(native_cmd|tts_reply)', re.I)
_CONTENT_RE = re.compile(r'["“”\']?content["“”\']?\s*[:：=]\s*["“”\']?', re.I)


@dataclass
class Parsed:
    type: str
    content: str
    how: str  # 解析路径，便于排障


def _strip_wrappers(text: str) -> str:
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    # 去掉 ZWSP / BOM 之类
    return text.replace("\u200b", "").replace("\ufeff", "").strip()


def _try_json(text: str) -> dict | None:
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except Exception:
            continue
        if isinstance(obj, dict) and "type" in obj:
            return obj
    return None


def parse_contract(raw: str) -> Parsed:
    """把上游返回的任意文本解析为 (type, content)。"""
    text = _strip_wrappers(raw or "")
    if not text:
        return Parsed(NATIVE, "", "empty")  # 空内容 → 什么都不做，最安全

    obj = _try_json(text)
    if obj is not None:
        t = str(obj.get("type", "")).strip().lower()
        c = obj.get("content", "")
        if isinstance(c, (dict, list)):
            c = json.dumps(c, ensure_ascii=False)
        c = str(c or "")
        if t in (NATIVE, TTS):
            return Parsed(t, c.strip(), "json")

    m = _TYPE_RE.search(text)
    if m:
        t = m.group(1).lower()
        rest = text[m.end():]
        mc = _CONTENT_RE.search(rest)
        if mc:
            c = rest[mc.end():]
            c = re.sub(r'["\']?\s*\}\s*$', "", c.strip())
            c = c.strip().strip('"').strip()
        else:
            c = ""
        if t == NATIVE:
            return Parsed(NATIVE, c or text, "regex")
        return Parsed(TTS, c or _strip_json_noise(text), "regex")

    return Parsed(TTS, _strip_json_noise(text), "raw")


def _strip_json_noise(text: str) -> str:
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        t = t[1:-1]
    t = re.sub(r'["“”\']?type["“”\']?\s*[:：=]\s*["“”\']?(native_cmd|tts_reply)["“”\']?',
               "", t, flags=re.I)
    t = re.sub(r'["“”\']?content["“”\']?\s*[:：=]\s*', "", t, flags=re.I)
    return t.strip().strip(",").strip().strip('"').strip()


# ---------------------------------------------------------------- 规则快筛

# 只保留"设备控制 / 播放控制"这类几乎不可能被当成提问的句式。
# 注意：不要放"播放晴天"这种后面可能接?"播放晴天这首歌的歌词" 的模糊句式——
# 实际加了「播放」前缀的，基本都是原生播放意图，可以放行；
# 但带问号、疑问词的语句一律不进快筛。
_ROOMS = r"(客厅|卧室|书房|厨房|卫生间|阳台|餐厅|走廊|玄关|全部|所有|这个|那个)"
_LIGHTS = r"(灯|台灯|吊灯|灯带|吸顶灯|氛围灯)"
_ONOFF = r"(打开|关掉|关闭|开一下|关一下|开|关)"

_NATIVE_PATTERNS = [
    # 灯的开关（"开灯" / "帮我关掉客厅灯" / "把卧室灯打开" / "客厅灯关闭"）
    rf"^(请|帮我|麻烦)?(把)?{_ROOMS}?(的)?{_LIGHTS}{_ONOFF}$",
    rf"^(请|帮我|麻烦)?{_ONOFF}{_ROOMS}?(的)?{_LIGHTS}$",
    # 音量 / 静音
    r"^(音量|声音)(调?到|调?成|调?为|加|减|大一点|小一点|大|小|最大|最小)\d{0,3}(%|百分之\d+)?$",
    r"^(静音|取消静音|别说话了|闭嘴)$",
    # 播放控制（不含"播放某首歌"，那种带歌名容易和提问混淆，交给 LLM 判）
    r"^(暂停|继续播放|继续|下一首|上一首|切歌|单曲循环|随机播放|停止播放|退出播放|关掉音乐)$",
    r"^播放(音乐|歌曲|电台|广播|新闻|白噪音|雨声|助眠音乐)$",
    # 定时 / 提醒
    r"^(取消|删除)?(所有)?(闹钟|闹铃|计时器|倒计时|提醒)$",
    r"^\d{1,2}(点|时)(半|\d{1,2}分)?(叫醒我)?$",
    # 家电
    r"^(请|帮我|麻烦)?(打开|关掉|关闭|开一下|关一下)(空调|电视|风扇|加湿器|净化器|窗帘|热水器|扫地机器人|投影仪|新风)$",
    r"^(空调|电视|风扇|热水器)(调到|设为|温度调到)\d{1,2}度?$",
]

# 疑问信号：出现这些词，即使模型说 native，也强制改判为 tts_reply
_QUESTION_HINTS = re.compile(
    r"(什么|啥|哪些|哪个|哪里|哪儿|哪首|哪一|怎么|怎样|咋|为什么|为何|凭什么|"
    r"多少|多大|多远|多久|几个|谁|是否|能不能|可不可以|有没有|是不是|如何|"
    r"介绍|推荐|对比|分析|写一|写个|生成|设计|规划|查一下|查查|搜一下|查询|"
    r"帮我写|翻译|总结|评价|怎么样|多少钱|吗？|呢？|\?|？)"
)

_CTRL_WORDS = re.compile(r"^(小爱同学|小爱|你好小爱)[，,。\s]*")


class IntentJudge:
    """把上游文本 + 本地规则合成为最终结论。"""

    def __init__(self, patterns: list[str] | None = None, fastpath: bool = True,
                 question_guard: bool = True):
        self.patterns = [re.compile(p) for p in (patterns or _NATIVE_PATTERNS)]
        self.fastpath = fastpath
        self.question_guard = question_guard

    @classmethod
    def from_file(cls, path: str | None, fastpath: bool = True,
                  question_guard: bool = True) -> "IntentJudge":
        pats: list[str] = []
        if path:
            p = Path(path)
            if p.is_file():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pats.append(line)
        return cls(pats or _NATIVE_PATTERNS, fastpath, question_guard)

    # -- 外部入口 -------------------------------------------------

    def normalize_query(self, query: str) -> str:
        q = (query or "").strip()
        q = _CTRL_WORDS.sub("", q)
        q = q.strip("。！!，, ")
        return q.strip()

    def looks_native(self, query: str) -> bool:
        if not self.fastpath:
            return False
        q = self.normalize_query(query).replace(" ", "")
        if not q or _QUESTION_HINTS.search(q):
            return False
        return any(p.match(q) for p in self.patterns)

    def is_question(self, query: str) -> bool:
        return bool(_QUESTION_HINTS.search(query or ""))

    def decide(self, query: str, upstream: str) -> tuple[str, str, str]:
        """返回 (type, content, reason)。"""
        if self.looks_native(query):
            return NATIVE, self.normalize_query(query), "fastpath"

        parsed = parse_contract(upstream)
        if parsed.type == NATIVE:
            if self.question_guard and self.is_question(query):
                # 模型把提问判成了原生指令：宁可多说，也不能不答
                return TTS, "", "guard_overrode_native"
            return NATIVE, parsed.content or self.normalize_query(query), f"llm:{parsed.how}"

        content = parsed.content
        if not content:
            return NATIVE, "", "empty_reply"
        return TTS, content, f"llm:{parsed.how}"


# ---------------------------------------------------------------- TTS 清洗

_MD_LINK = re.compile(r"\[([^\]]*)\]\((?:[^)]*)\)")
_MD_CHARS = re.compile(r"[*_`#>|~]+")
_URL = re.compile(r"https?://\S+")
_SPACES = re.compile(r"[ \t\u3000]+")


def sanitize_for_tts(text: str, max_chars: int = 300) -> str:
    """让人耳听得懂的版本：去 Markdown、去链接、去多余符号，超长按句截断。"""
    t = (text or "").strip()
    if not t:
        return ""
    t = _MD_LINK.sub(r"\1", t)
    t = _URL.sub("", t)
    t = _MD_CHARS.sub("", t)
    t = _SPACES.sub(" ", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    for sep in ("。", "！", "？", "；", "\n", "，"):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.5:
            return cut[: idx + 1]
    return cut.rstrip("，、, ") + "。"
