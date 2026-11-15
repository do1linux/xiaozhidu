"""离线冒烟自检：用 MCP 客户端以 stdio 启动本目录的服务并实际调用工具。

不需要 MCP_ENDPOINT，不需要连外网。用法：

    python mcp_servers/selftest.py

全部通过返回 0，任一失败返回 1。这个脚本是客户端，可以正常 print；
被启动的 free_tools.py / fetch_lite.py 是服务端，不能往 stdout 打日志。
"""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


def _text(result) -> str:
    return "".join(
        c.text for c in result.content if getattr(c, "type", "") == "text"
    )


def _is_error(result) -> bool:
    return bool(
        getattr(result, "isError", None) or getattr(result, "is_error", False)
    )


async def check(script: str, calls) -> bool:
    # 自检跑全套工具，忽略外部裁剪与落盘设置
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MCP_DISABLE_TOOLS", "MCP_MEMORY_FILE")
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / script)],
        env=env,
    )
    print("--- %s ---" % script)
    ok = True
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("tools(%d): %s" % (len(names), ", ".join(names)))
            if not names:
                print("FAIL 没有注册任何工具")
                return False
            for name, arguments, expect in calls:
                if name not in names:
                    print("FAIL 缺少工具 %s" % name)
                    ok = False
                    continue
                result = await session.call_tool(name, arguments=arguments)
                text = _text(result)
                good = expect in text and not _is_error(result)
                print(
                    "%s %s -> %s"
                    % ("OK  " if good else "FAIL", name, text[:150].replace("\n", " "))
                )
                ok = ok and good
    return ok


async def main() -> int:
    try:
        a = await check(
            "free_tools.py",
            [
                ("echo", {"text": "ping"}, "ping"),
                ("get_current_time", {"timezone": "Asia/Shanghai"}, "iso"),
                ("convert_time", {"source_timezone": "Asia/Shanghai", "time": "20:30", "target_timezone": "UTC"}, "offset_hours"),
                ("calculate", {"expression": "2+3*4"}, "14"),
                (
                    "sequential_thinking",
                    {
                        "thought": "先确认时区，再换算时间",
                        "thought_number": 1,
                        "total_thoughts": 2,
                    },
                    "accepted",
                ),
                ("remember", {"key": "selftest", "value": "临时自检"}, "ok"),
                ("recall", {"query": "selftest"}, "count"),
                ("forget", {"key": "selftest"}, "deleted"),
                ("list_memories", {}, "count"),
                ("text_stats", {"text": "桥接 abc 123"}, "words_approx"),
                ("text_transform", {"text": " a  b ", "action": "compact"}, "chars"),
                ("random_int", {"min_value": 1, "max_value": 6}, "value"),
                ("random_choice", {"options": ["甲", "乙"]}, "value"),
                ("new_uuid", {}, "uuid"),
            ],
        )
        b = await check(
            "fetch_lite.py",
            [
                ("check_url", {"url": "http://127.0.0.1/"}, "已拒绝"),
                ("check_url", {"url": "file:///etc/passwd"}, "仅允许"),
            ],
        )
    except Exception as exc:
        print("FAIL 无法启动服务：%s: %s" % (type(exc).__name__, exc))
        return 1
    print("=== %s ===" % ("PASS" if a and b else "FAIL"))
    return 0 if a and b else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
