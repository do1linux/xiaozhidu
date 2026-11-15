"""免费本地 MCP 工具集（stdio 传输，单进程）。

对标 modelcontextprotocol/servers 的 Time / Sequential Thinking / Memory /
Everything 参考实现，重写为 keyless、无外部账号、无付费后端的本地工具。

由仓库顶层 mcp_pipe.py 启动时 stdout 是 JSON-RPC 通道：禁止 print，
日志一律走 stderr，否则会污染协议流导致 xiaozhi 服务端解析失败。
"""

import ast
import json
import logging
import operator
import os
import random
import re
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)
LOG = logging.getLogger("free_tools")

mcp = FastMCP("FreeTools")

# 通过 MCP_DISABLE_TOOLS=text_stats,text_transform,... 关闭用不到的工具，
# 减少工具描述占用的上下文。
_DISABLED = {
    s.strip()
    for s in os.environ.get("MCP_DISABLE_TOOLS", "").split(",")
    if s.strip()
}


def tool(*args, **kwargs):
    """@mcp.tool() 的包装，支持按函数名禁用工具。"""
    def decorate(fn):
        if fn.__name__ not in _DISABLED:
            mcp.tool(*args, **kwargs)(fn)
        return fn
    return decorate


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValueError(
            "未知时区 %r；Windows 上需安装 tzdata（见顶层 requirements.txt）" % name
        ) from exc


@tool()
def echo(text: str) -> Dict[str, Any]:
    """链路自检：原样返回输入并标明服务名，用于确认小智到 MCP 的通道已打通。"""
    return {"echo": text, "server": "free_tools", "transport": "stdio"}


@tool()
def get_current_time(timezone: str = "Asia/Shanghai") -> Dict[str, Any]:
    """取指定 IANA 时区的当前时间，例如 Asia/Shanghai、UTC、America/New_York。"""
    now = datetime.now(_zone(timezone))
    return {
        "timezone": timezone,
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "utc_offset": now.strftime("%z"),
        "unix": int(now.timestamp()),
    }


@tool()
def convert_time(source_timezone: str, time: str, target_timezone: str) -> Dict[str, Any]:
    """把一个时区的时钟时间换算到另一个时区，按源时区的当天计算。
    time 格式为 HH:MM 或 HH:MM:SS，例如 20:30。"""
    src = _zone(source_timezone)
    dst = _zone(target_timezone)
    parts = time.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("time 需为 HH:MM 或 HH:MM:SS")
    try:
        nums = [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError("time 含非数字字符") from exc
    nums += [0] * (3 - len(nums))
    h, m, s = nums
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
        raise ValueError("time 超出合法时间范围")
    base = datetime.now(src).replace(hour=h, minute=m, second=s, microsecond=0)
    out = base.astimezone(dst)
    delta = (out.utcoffset() - base.utcoffset()).total_seconds() / 3600
    return {
        "source": {
            "timezone": source_timezone,
            "date": base.strftime("%Y-%m-%d"),
            "time": base.strftime("%H:%M:%S"),
        },
        "target": {
            "timezone": target_timezone,
            "date": out.strftime("%Y-%m-%d"),
            "time": out.strftime("%H:%M:%S"),
        },
        "offset_hours": delta,
    }


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        if abs(node.value) > 1e12:
            raise ValueError("数值过大")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    raise ValueError("表达式含不支持的语法（仅允许 + - * / // % 与括号）")


@tool()
def calculate(expression: str) -> Dict[str, Any]:
    """安全的四则运算，支持括号与小数；用 AST 白名单求值，不执行任意代码。"""
    expr = expression.strip()
    if not expr or len(expr) > 200:
        raise ValueError("表达式为空或超过 200 字符")
    tree = ast.parse(expr, mode="eval")
    try:
        value = _eval_node(tree)
    except ZeroDivisionError as exc:
        raise ValueError("除数为零") from exc
    if isinstance(value, float):
        if not abs(value) < 1e15:
            raise ValueError("结果过大或非有限值")
        if value.is_integer():
            value = int(value)
    return {"expression": expr, "result": value}


_THOUGHTS: List[Dict[str, Any]] = []
_THOUGHT_LOCK = threading.Lock()
_THOUGHT_LIMIT = 50


@tool()
def sequential_thinking(
    thought: str,
    thought_number: int,
    total_thoughts: int,
    next_thought_needed: bool = True,
    is_revision: bool = False,
    revises_thought: Optional[int] = None,
) -> Dict[str, Any]:
    """登记一步分步推理，返回进度确认。
    对标官方 Sequential Thinking：工具本身不做推理，只提供可回溯的脚手架；
    仅记录步号与长度，不留存推理正文。"""
    if thought_number < 1 or total_thoughts < 1 or thought_number > total_thoughts:
        raise ValueError("thought_number / total_thoughts 不合法")
    if not thought.strip():
        raise ValueError("thought 不能为空")
    with _THOUGHT_LOCK:
        _THOUGHTS.append(
            {
                "number": thought_number,
                "total": total_thoughts,
                "is_revision": is_revision,
                "revises": revises_thought,
                "length": len(thought),
            }
        )
        if len(_THOUGHTS) > _THOUGHT_LIMIT:
            del _THOUGHTS[:-_THOUGHT_LIMIT]
        count = len(_THOUGHTS)
    return {
        "accepted": True,
        "thought_number": thought_number,
        "total_thoughts": total_thoughts,
        "next_thought_needed": next_thought_needed,
        "session_steps": count,
    }


_MEMORY: Dict[str, Dict[str, str]] = {}
_MEMORY_LOCK = threading.Lock()
_MEMORY_FILE = os.environ.get("MCP_MEMORY_FILE", "").strip()
_MEMORY_PATH = Path(_MEMORY_FILE) if _MEMORY_FILE else None


def _memory_load() -> None:
    if not _MEMORY_PATH or not _MEMORY_PATH.is_file():
        return
    try:
        data = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            with _MEMORY_LOCK:
                for key, val in data.items():
                    if isinstance(val, dict):
                        _MEMORY[str(key)] = val
    except Exception as exc:
        LOG.warning("记忆文件读取失败：%s", type(exc).__name__)


def _memory_save() -> None:
    if not _MEMORY_PATH:
        return
    _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MEMORY_PATH.with_name(_MEMORY_PATH.name + ".tmp")
    tmp.write_text(json.dumps(_MEMORY, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(_MEMORY_PATH))


_memory_load()


@tool()
def remember(key: str, value: str) -> Dict[str, Any]:
    """记住一条键值信息。默认只存进程内存、服务重启即失效；
    仅当显式设置 MCP_MEMORY_FILE 时才落盘。
    不要写入账号、口令、设备 ID、对话原文或其他个人敏感信息。"""
    key = key.strip()
    if not key or len(key) > 120:
        raise ValueError("key 为空或超过 120 字符")
    if len(value) > 4000:
        raise ValueError("value 超过 4000 字符")
    now = datetime.now().isoformat(timespec="seconds")
    with _MEMORY_LOCK:
        created = _MEMORY.get(key, {}).get("created_at", now)
        _MEMORY[key] = {"value": value, "created_at": created, "updated_at": now}
        try:
            _memory_save()
            persisted = bool(_MEMORY_PATH)
        except Exception as exc:
            LOG.warning("记忆落盘失败：%s", type(exc).__name__)
            persisted = False
    return {"ok": True, "key": key, "persisted": persisted}


@tool()
def recall(query: str = "") -> Dict[str, Any]:
    """按关键字检索记忆；query 为空列出全部，最多返回 20 条。"""
    q = query.strip()
    with _MEMORY_LOCK:
        items = [
            {
                "key": k,
                "value": v.get("value", ""),
                "updated_at": v.get("updated_at", ""),
            }
            for k, v in _MEMORY.items()
            if not q or q in k or q in str(v.get("value", ""))
        ]
    return {"count": len(items), "items": items[:20], "truncated": len(items) > 20}


@tool()
def forget(key: str) -> Dict[str, Any]:
    """删除一条记忆。"""
    with _MEMORY_LOCK:
        existed = _MEMORY.pop(key.strip(), None) is not None
        if existed:
            try:
                _memory_save()
            except Exception as exc:
                LOG.warning("记忆落盘失败：%s", type(exc).__name__)
    return {"ok": True, "deleted": existed}


@tool()
def list_memories() -> Dict[str, Any]:
    """列出记忆的键与更新时间，不返回正文，避免把内容塞进模型上下文。"""
    with _MEMORY_LOCK:
        keys = [
            {"key": k, "updated_at": v.get("updated_at", "")}
            for k, v in _MEMORY.items()
        ]
    return {"count": len(keys), "keys": keys[:50]}


@tool()
def text_stats(text: str) -> Dict[str, Any]:
    """统计文本长度：字符数、非空白字符数、行数、中英混排近似词数、UTF-8 字节数。"""
    if len(text) > 100000:
        raise ValueError("文本超过 100000 字符")
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)
    return {
        "chars": len(text),
        "chars_no_space": len(re.sub(r"\s", "", text)),
        "lines": len(text.splitlines()),
        "words_approx": len(words),
        "utf8_bytes": len(text.encode("utf-8")),
    }


_ACTIONS = ("upper", "lower", "strip", "compact", "dedupe_lines", "truncate")


@tool()
def text_transform(text: str, action: str, limit: int = 200) -> Dict[str, Any]:
    """纯本地文本处理。action 取 upper / lower / strip / compact /
    dedupe_lines / truncate；仅 truncate 用到 limit（1..10000）。"""
    if len(text) > 100000:
        raise ValueError("文本超过 100000 字符")
    if action not in _ACTIONS:
        raise ValueError("action 必须是 %s 之一" % ", ".join(_ACTIONS))
    if not 1 <= limit <= 10000:
        raise ValueError("limit 需在 1..10000")
    if action == "upper":
        out = text.upper()
    elif action == "lower":
        out = text.lower()
    elif action == "strip":
        out = "\n".join(line.strip() for line in text.splitlines()).strip()
    elif action == "compact":
        out = re.sub(r"\s+", " ", text).strip()
    elif action == "dedupe_lines":
        seen, lines = set(), []
        for line in text.splitlines():
            if line not in seen:
                seen.add(line)
                lines.append(line)
        out = "\n".join(lines)
    else:
        out = text[:limit]
    return {"action": action, "chars": len(out), "text": out}


@tool()
def random_int(min_value: int = 1, max_value: int = 100) -> Dict[str, Any]:
    """在闭区间 [min_value, max_value] 内取一个随机整数。"""
    if min_value > max_value or abs(min_value) > 1e9 or abs(max_value) > 1e9:
        raise ValueError("区间不合法或数值过大")
    return {
        "min": min_value,
        "max": max_value,
        "value": random.randint(min_value, max_value),
    }


@tool()
def random_choice(options: List[str]) -> Dict[str, Any]:
    """从给定选项中随机选一项。"""
    if not options:
        raise ValueError("options 不能为空")
    if len(options) > 200:
        raise ValueError("options 超过 200 项")
    return {"count": len(options), "value": random.choice(options)}


@tool()
def new_uuid() -> Dict[str, Any]:
    """生成一个 UUID v4，用于给任务或记忆编号。"""
    return {"uuid": str(uuid.uuid4())}


if __name__ == "__main__":
    if _DISABLED:
        LOG.warning("已禁用工具：%s", ",".join(sorted(_DISABLED)))
    mcp.run(transport="stdio")
