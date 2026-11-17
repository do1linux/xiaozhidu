"""agnes-ai 直连兜底：OpenAI 兼容端点，不依赖 xiaozhi 是否存活。

端点与密钥走环境变量 AGNES_BASE / AGNES_KEY / AGNES_MODEL，
默认指向 https://apihub.agnes-ai.com/v1，模型 agnes-3.0-flash。

能力边界：这条路拿不到 xiaozhi 的 MCP 工具（米家控制/点歌），
system prompt 会明确要求模型"不要假装能操作设备"。
要完整的 MCP 能力，请让 xiaozhi_ws 适配器工作在链路最前面。

模型选择（实测 2026-11）：
  - agnes-3.0-flash：非推理，约 2s，稳定返回 JSON —— 默认。
  - agnes-2.5-flash / 2.5-pro 等：推理模型，token 全进 reasoning_content，
    content 为空；本适配器检测到该情况会明确报错，提示换非推理模型。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from .base import AdapterError, BaseAdapter

log = logging.getLogger("adapter.agnes")

DEFAULT_PROMPT = """你在一个家庭语音助手里工作。用户通过小爱音箱说话，你的回答会被直接朗读出来。
请只输出一个 JSON 对象，不要输出任何其它字符、不要用 markdown 代码块：
{"type":"native_cmd","content":"用户原始指令"}
或
{"type":"tts_reply","content":"你的口语化回答"}
规则：
1. 只有当用户是在下"小爱音箱本身就能执行"的设备控制/播放/定时类指令时，才用 native_cmd。
2. 其余一切（问答、查询、写文案、做方案、算数、翻译、闲聊）都用 tts_reply。
3. tts_reply 的 content 必须是能直接朗读的纯文本：不要 URL、不要列表符号、不要括号注释，
   控制在 120 字以内，先给结论再补一句关键信息。
4. 你无法直接操作硬件（开灯、放歌）。如果用户提出这类需求但你判断不该由原生执行，
   就用 tts_reply 说明情况，不要编造"已为你打开"。"""


class AgnesAdapter(BaseAdapter):
    name = "agnes"

    def __init__(self, base: str, key: str, model: str, timeout: float = 30.0,
                 prompt_file: str | None = None, json_mode: bool = True,
                 history_turns: int = 0):
        self.base = base.rstrip("/")
        self.key = key
        self.model = model
        self.timeout = timeout
        self.json_mode = json_mode
        self.history_turns = history_turns
        self.system_prompt = DEFAULT_PROMPT
        if prompt_file and Path(prompt_file).is_file():
            txt = Path(prompt_file).read_text(encoding="utf-8").strip()
            if txt:
                self.system_prompt = txt

    async def chat(self, query, session_id, history=None, force_answer: bool = False) -> str:
        if not self.key:
            raise AdapterError("AGNES_KEY 未配置")

        messages = [{"role": "system", "content": self.system_prompt}]
        if self.history_turns and history:
            for turn in history[-self.history_turns:]:
                if turn.get("q"):
                    messages.append({"role": "user", "content": turn["q"]})
                if turn.get("a"):
                    messages.append({"role": "assistant", "content": turn["a"]})
        user_content = query
        if force_answer:
            user_content = (
                f"{query}\n\n（注意：这句话是用户在向你提问，不是设备指令。"
                f'请直接给出回答，type 必须是 tts_reply。）'
            )
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 500,
            "stream": False,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.key}"},
                    json=payload,
                )
                if r.status_code >= 400 and self.json_mode:
                    # 有些中转/模型不支持 json_object，退回普通模式重试一次
                    payload.pop("response_format", None)
                    r = await client.post(
                        f"{self.base}/chat/completions",
                        headers={"Authorization": f"Bearer {self.key}"},
                        json=payload,
                    )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            raise AdapterError(f"agnes 调用失败: {e}") from e

        try:
            message = data["choices"][0]["message"]
        except Exception as e:
            raise AdapterError(f"agnes 返回结构异常: {data!r}") from e

        content = message.get("content") or ""
        # 推理模型（如 agnes-2.5-*）把 token 全写进 reasoning_content，content 为空。
        # 这种情况链路上会一路降级到兜底话术，很难排查，这里直接给出可操作的报错。
        if not content.strip() and message.get("reasoning_content"):
            raise AdapterError(
                f"模型 {self.model} 只返回了 reasoning_content，未返回 content："
                "这是推理模型，不适合本链路。请把 AGNES_MODEL 改为 agnes-3.0-flash（非推理）。"
            )
        log.debug("agnes 耗时 %.2fs", time.perf_counter() - started)
        if not content.strip():
            raise AdapterError("agnes 返回空内容")
        return content
