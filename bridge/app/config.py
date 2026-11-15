"""运行期配置：环境变量优先，其次 .env，最后按代码包根目录自动推导。

三种运行方式共用同一份代码：
  - Docker：compose 用 env_file 注入，并显式指定 BRIDGE_ROOT=/app
  - 裸 Python（Linux / Windows）：进程自己读代码根下的 .env，路径按本文件位置推导
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# 代码包根目录。Docker 内由 compose 指定 /app（prompts/logs 挂在那里）；
# 裸机自动从 bridge/app/config.py 往上两级得到仓库根，不依赖 /app 这类容器路径。
_ROOT_ENV = os.getenv("BRIDGE_ROOT", "").strip()
REPO_ROOT = Path(_ROOT_ENV) if _ROOT_ENV else Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """极简 .env 加载：已有环境变量一律优先，不覆盖。

    只服务裸 Python / Windows 模式；Docker 模式由 compose 注入，容器内也没有 .env。
    兼容 `KEY=value  # 行内注释`，不会破坏含花括号与引号的 JSON 模板值。
    """
    raw_path = os.getenv("BRIDGE_DOTENV", "").strip()
    path = Path(raw_path) if raw_path else REPO_ROOT / ".env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        m = re.search(r"\s+#", val)
        if m:
            val = val[: m.start()].rstrip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ[key] = val


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "y")


@dataclass
class Settings:
    # ---- 服务本体 ----
    host: str = field(default_factory=lambda: _env("BRIDGE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("BRIDGE_PORT", 8100))

    # ---- 适配器链：按顺序尝试，前一个失败/超时自动降级到下一个 ----
    # 可选值: xiaozhi_ws | xiaozhi_http | newapi
    adapters: list[str] = field(
        default_factory=lambda: [
            a.strip()
            for a in _env("ADAPTER_CHAIN", "xiaozhi_ws,newapi").split(",")
            if a.strip()
        ]
    )

    # ---- xiaozhi-esp32-server（虚拟设备 WebSocket 方式，无需改 xiaozhi 源码）----
    xiaozhi_ws_url: str = field(
        default_factory=lambda: _env("XIAOZHI_WS_URL", "ws://127.0.0.1:8000/xiaozhi/v1/")
    )
    xiaozhi_device_id: str = field(
        default_factory=lambda: _env("XIAOZHI_DEVICE_ID", "voice-bridge-01")
    )
    xiaozhi_client_id: str = field(
        default_factory=lambda: _env("XIAOZHI_CLIENT_ID", "voice-bridge")
    )
    xiaozhi_token: str = field(default_factory=lambda: _env("XIAOZHI_TOKEN", ""))
    xiaozhi_ws_timeout: float = field(
        default_factory=lambda: _env_float("XIAOZHI_WS_TIMEOUT", 40.0)
    )
    # 文本注入帧：不同版本的 xiaozhi 对“纯文本输入”的支持方式略有差异，
    # 用模板暴露出来，改配置即可适配，不用改代码。
    xiaozhi_text_frame: str = field(
        default_factory=lambda: _env(
            "XIAOZHI_TEXT_FRAME",
            '{"session_id":"{session_id}","type":"listen","state":"detect","text":"{text}"}',
        )
    )

    # ---- xiaozhi 自带 HTTP 文本接口（若你的版本已自行加了 /internal/text_chat）----
    xiaozhi_http_url: str = field(
        default_factory=lambda: _env(
            "XIAOZHI_HTTP_URL", "http://127.0.0.1:8000/internal/text_chat"
        )
    )

    # ---- NewAPI 直连兜底（OpenAI 兼容）----
    newapi_base: str = field(default_factory=lambda: _env("NEWAPI_BASE", "http://127.0.0.1:3000/v1"))
    newapi_key: str = field(default_factory=lambda: _env("NEWAPI_KEY", ""))
    newapi_model: str = field(default_factory=lambda: _env("NEWAPI_MODEL", "gpt-4o-mini"))
    newapi_timeout: float = field(
        default_factory=lambda: _env_float("NEWAPI_TIMEOUT", 30.0)
    )
    newapi_use_json_mode: bool = field(
        default_factory=lambda: _env_bool("NEWAPI_JSON_MODE", True)
    )
    system_prompt_file: str = field(
        default_factory=lambda: _env(
            "SYSTEM_PROMPT_FILE",
            str(REPO_ROOT / "prompts" / "xiaozhi_system_prompt.txt"),
        )
    )

    # ---- 意图判定 ----
    # 规则快筛：命中即直接判 native_cmd，不烧 token、不加延迟。
    # 判定错误的代价不对称——把“提问”误判成 native 会导致完全没回答，
    # 所以这里只放“几乎不可能有第二种解释”的设备控制/播放类句式。
    native_fastpath: bool = field(
        default_factory=lambda: _env_bool("NATIVE_FASTPATH", True)
    )
    native_keywords_file: str = field(
        default_factory=lambda: _env(
            "NATIVE_KEYWORDS_FILE",
            str(REPO_ROOT / "prompts" / "native_keywords.txt"),
        )
    )
    # 反问兜底：命中疑问句式（哪些/怎么/为什么/多少…）时，即使 LLM 返回 native_cmd
    # 也强制改判 tts_reply，避免“该答不答”。
    question_guard: bool = field(
        default_factory=lambda: _env_bool("QUESTION_GUARD", True)
    )

    # ---- 输出清洗 ----
    max_tts_chars: int = field(default_factory=lambda: _env_int("MAX_TTS_CHARS", 300))
    min_query_len: int = field(default_factory=lambda: _env_int("MIN_QUERY_LEN", 2))
    # 多轮上下文：0 = 关闭（每句独立判断，延迟最低）
    history_turns: int = field(default_factory=lambda: _env_int("HISTORY_TURNS", 0))

    # 护栏触发但二次判定仍拿不到答案时的兜底话术（宁可说一句"待会回你"，也别沉默）
    fallback_reply: str = field(default_factory=lambda: _env(
        "FALLBACK_REPLY", "这个问题我一时没查到准确的，等我确认一下再告诉你。"))

    # ---- 可观测性 ----
    # 默认只落判定元数据，不落用户 ASR 原文与模型回答正文。
    # 需要逐句排障时显式打开 LOG_TEXT=true，日志属本机临时数据，用完即清。
    log_text: bool = field(default_factory=lambda: _env_bool("LOG_TEXT", False))
    log_dir: str = field(
        default_factory=lambda: _env("LOG_DIR", str(REPO_ROOT / "logs"))
    )
    debug: bool = field(default_factory=lambda: _env_bool("BRIDGE_DEBUG", False))
    recent_buffer: int = field(default_factory=lambda: _env_int("RECENT_BUFFER", 50))

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        if d.get("newapi_key"):
            d["newapi_key"] = "***"
        return d


settings = Settings()
