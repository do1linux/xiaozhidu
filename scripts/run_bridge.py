#!/usr/bin/env python3
"""裸 Python / Windows 启动入口：自动定位代码根、加载 .env、按配置端口起 uvicorn。

Docker 模式不用这个（compose 直接 CMD uvicorn）；Windows 服务与手动调试用它。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

from app.config import settings  # noqa: E402  （导入时加载 .env）
from app.main import app  # noqa: E402
import uvicorn  # noqa: E402


def main() -> None:
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="info" if settings.debug else "warning",
    )


if __name__ == "__main__":
    main()
