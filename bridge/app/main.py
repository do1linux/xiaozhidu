"""中转桥：xiaogpt → 这里 → xiaozhi / agnes-ai → 结构化结论。

对外只有一个真正重要的接口：POST /api/text_chat
响应恒为 {"type":"native_cmd"|"tts_reply","content":"...","meta":{...}}
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .adapters import AdapterError, BaseAdapter, Unsupported, build_adapters
from .config import Settings, settings
from .intent import NATIVE, TTS, IntentJudge, parse_contract, sanitize_for_tts
from .schemas import ChatReq, ChatResp, ClassifyReq
from .session import SessionStore

log = logging.getLogger("bridge")

# 这几句是噪音：唤醒词本身、音箱自己的确认语、纯语气词
_NOISE = {"小爱同学", "小爱", "在吗", "在不在", "嗯", "哦", "啊", "好的", "没事", "算了"}
# 含用户语音或模型正文的字段，未显式开启 LOG_TEXT 时一律不落盘
_TEXT_KEYS = ("q", "content", "detail")


class State:
    def __init__(self, s: Settings):
        self.settings = s
        self.adapters: list[BaseAdapter] = build_adapters(s)
        self.judge = IntentJudge.from_file(
            s.native_keywords_file, s.native_fastpath, s.question_guard
        )
        self.sessions = SessionStore()
        self.recent: deque = deque(maxlen=max(10, s.recent_buffer))
        self._log_path = os.path.join(s.log_dir, "bridge.jsonl")
        os.makedirs(s.log_dir, exist_ok=True)

    def record(self, item: dict) -> None:
        safe = dict(item)
        if self.settings.log_text:
            for k in _TEXT_KEYS:
                if k in safe:
                    safe[k] = str(safe[k])[:200]
        else:
            for k in _TEXT_KEYS:
                if k in safe:
                    safe[k + "_len"] = len(str(safe[k]))
                    del safe[k]
        self.recent.append(safe)
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写不进去不能影响主链路


@asynccontextmanager
async def lifespan(app: FastAPI):
    st = State(settings)
    app.state.st = st
    log.info("适配器链: %s | fastpath=%s | guard=%s",
             [a.name for a in st.adapters], settings.native_fastpath, settings.question_guard)
    yield


app = FastAPI(title="xiao bridge", version="2.0", lifespan=lifespan)


def _st() -> State:
    return app.state.st


async def _ask_upstream(st: State, query: str, session_id: str,
                        force_answer: bool = False) -> tuple[str, str]:
    """按链路依次尝试，返回 (原始文本, 命中的适配器名)。"""
    history = st.sessions.history(session_id) if st.settings.history_turns else []
    errors: list[str] = []
    for adapter in st.adapters:
        try:
            text = await adapter.chat(query, session_id, history, force_answer=force_answer)
            if text and text.strip():
                return text, adapter.name
            errors.append(f"{adapter.name}: 空返回")
        except Unsupported as e:
            errors.append(f"{adapter.name}: {e}")
            log.debug("%s 不支持该请求形态", adapter.name)
        except AdapterError as e:
            errors.append(f"{adapter.name}: {e}")
            log.warning("%s 调用失败：%s", adapter.name, type(e).__name__)
        except Exception as e:  # 适配器内部异常不该拖垮整个请求
            errors.append(f"{adapter.name}: {type(e).__name__} {e}")
            log.exception("%s 未预期异常", adapter.name)
    raise HTTPException(status_code=502, detail={"errors": errors})


@app.post("/api/text_chat", response_model=ChatResp)
async def text_chat(req: ChatReq):
    st = _st()
    started = time.perf_counter()
    query = st.judge.normalize_query(req.query)

    # 1) 噪音直接吞掉：返回 native_cmd + 空 content，xiaogpt 侧什么都不做
    if len(query) < st.settings.min_query_len or query in _NOISE:
        resp = ChatResp(type=NATIVE, content="", meta={"reason": "noise", "skipped": True})
        st.record({"ts": _now(), "q": req.query, "type": resp.type, "reason": "noise",
                   "ms": 0, "adapter": None})
        return resp

    # 2) 规则快筛：明确的设备控制不烧 token，延迟 <1ms
    if st.judge.looks_native(query):
        resp = ChatResp(
            type=NATIVE,
            content=query,
            meta={"reason": "fastpath", "adapter": None,
                  "ms": round((time.perf_counter() - started) * 1000, 1)},
        )
        st.record({"ts": _now(), "q": query, "type": resp.type, "reason": "fastpath",
                   "ms": resp.meta["ms"], "adapter": None})
        return resp

    # 3) 交给上游判断
    try:
        upstream, adapter_name = await _ask_upstream(st, query, req.session_id)
    except HTTPException as e:
        st.record({"ts": _now(), "q": query, "type": "error", "reason": "upstream_down",
                   "ms": round((time.perf_counter() - started) * 1000, 1), "detail": e.detail})
        raise

    rtype, content, reason = st.judge.decide(query, upstream)

    # 护栏把模型的 native 判定顶掉时，结论是"必须回答"但手里没有答案，
    # 这时换一个支持强制作答的适配器（agnes）做一次二次判定。
    if rtype == TTS and not content and reason.startswith("guard"):
        try:
            upstream2, adapter2 = await _ask_upstream(
                st, query, req.session_id, force_answer=True)
        except HTTPException:
            upstream2, adapter2 = "", ""
        if upstream2:
            p2 = parse_contract(upstream2)
            if p2.type == TTS and p2.content:
                content, reason = p2.content, f"guard_retry:{adapter2}"
            else:
                upstream, adapter_name = upstream2, adapter2
                rtype, content, reason = NATIVE, "", "guard_retry_still_native"
        if not content and rtype == TTS:
            content = st.settings.fallback_reply
            reason = "guard_fallback_reply"

    if rtype == TTS:
        content = sanitize_for_tts(content, st.settings.max_tts_chars)

    ms = round((time.perf_counter() - started) * 1000, 1)
    meta = {"reason": reason, "adapter": adapter_name, "ms": ms}
    if st.settings.log_text:
        meta["raw_head"] = upstream[:200]
    resp = ChatResp(type=rtype, content=content, meta=meta)
    if rtype == TTS and content:
        st.sessions.append(req.session_id, query, content)
    st.record({"ts": _now(), "q": query, "type": rtype, "reason": reason,
               "ms": ms, "adapter": adapter_name, "content": content[:200]})
    return resp


@app.post("/api/classify", response_model=ChatResp)
async def classify(req: ClassifyReq):
    """只做判定、不做播报，用于调 prompt / 调快筛规则。"""
    return await text_chat(ChatReq(query=req.query, session_id=req.session_id))


@app.get("/healthz")
async def healthz():
    st = _st()
    return {
        "ok": True,
        "adapters": [a.name for a in st.adapters],
        "native_fastpath": st.settings.native_fastpath,
        "question_guard": st.settings.question_guard,
        "log_text": st.settings.log_text,
        "recent": len(st.recent),
    }


@app.get("/api/recent")
async def recent(limit: int = 20):
    st = _st()
    return {"items": list(st.recent)[-max(1, min(limit, 200)):]}


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # pragma: no cover
    log.exception("未处理异常")
    return JSONResponse(status_code=500, content={"detail": {"error": type(exc).__name__}})


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")
