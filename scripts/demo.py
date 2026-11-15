#!/usr/bin/env python3
"""链路自测：往中转桥灌一批典型句子，看判定是否符合预期。

用法：
    python3 scripts/demo.py                       # 默认打 127.0.0.1:8100
    python3 scripts/demo.py http://127.0.0.1:8100
不进语音链路，纯 HTTP，所以可以随时在服务器上跑，不影响小爱。
"""
from __future__ import annotations

import sys
import time
import unicodedata

import httpx

CASES = [
    ("开灯", "native_cmd"),
    ("帮我关掉客厅灯", "native_cmd"),
    ("把卧室灯打开", "native_cmd"),
    ("下一首", "native_cmd"),
    ("播放晴天", "native_cmd"),
    ("小爱同学", "native_cmd"),
    ("滨湖这边有哪些新楼盘", "tts_reply"),
    ("帮我写一句卖房文案，突出湖景", "tts_reply"),
    ("给我设计一套徽派建筑画册的框架", "tts_reply"),
    ("从合肥南站到滨湖怎么走最快", "tts_reply"),
    ("明天适合签合同吗", "tts_reply"),
]


def pad(text: str, width: int) -> str:
    """按显示宽度补空格：中文占两格，len() 会让表格错位。"""
    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - w)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100").rstrip("/")
    ok = 0
    print(pad("句子", 30) + pad("期望", 14) + pad("实际", 14) + pad("耗时", 8) + "说明")
    print("-" * 96)
    with httpx.Client(timeout=60) as c:
        for query, expect in CASES:
            t0 = time.perf_counter()
            try:
                r = c.post(f"{base}/api/text_chat",
                           json={"query": query, "session_id": "demo"})
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(pad(query, 30) + pad(expect, 14) + pad("请求失败", 14) + pad("", 8) + str(e))
                continue
            cost = (time.perf_counter() - t0) * 1000
            got = data.get("type")
            status = "✅" if got == expect else "⚠️"
            if got == expect:
                ok += 1
            note = (data.get("content") or "")[:40]
            reason = (data.get("meta") or {}).get("reason", "")
            print(pad(query, 30) + pad(expect, 14) + pad(got, 14)
                  + pad(f"{cost:.0f}ms", 8) + f"{status} {reason} {note}")

    print("-" * 96)
    print(f"命中 {ok}/{len(CASES)}。不一致的先看 meta.reason：fastpath 说明规则写宽了，"
          f"llm 说明提示词要调。")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
