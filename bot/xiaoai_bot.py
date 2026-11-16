#!/usr/bin/env python3
"""小爱侧常驻进程：全量监听云端对话 → 交中转桥 → 只对 tts_reply 播报。

miservice 负责小米云登录、设备定位、对话记录读取与 TTS 下发；httpx 负责与
中转桥通信。本文件不依赖 xiaogpt 本体，只实现链路需要的登录、轮询、去重、
分发四件事。凭据一律从配置文件与环境变量读取，不写日志、不落对外文件。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import re
import signal
import time
from pathlib import Path

import aiohttp
import httpx
import yaml
from miservice import MiAccount, MiIOService, MiNAService

from local_tts import EdgeVoice

log = logging.getLogger("xiaoai")

CONVERSATION_API = (
    "https://userprofile.mina.mi.com/device_profile/v2/conversation"
    "?source=dialogu&hardware={hardware}&timestamp={ts}&limit=3"
)
TOKEN_PATH = os.getenv("MI_TOKEN_PATH", str(Path.home() / ".mi.token"))

DEFAULTS = {
    "bridge_url": "http://127.0.0.1:8100/api/text_chat",
    "bridge_timeout": 45.0,
    "poll_interval": 1.0,
    "mute_before_tts": True,
    "pre_tts_delay": 0.6,
    "tts_chunk": 80,
    "tts_char_delay_ms": 190,   # 每字朗读耗时（毫秒）；两段 TTS 之间按字数留间隔
    # 播报出口：mi = 小爱自带音色（默认）；edge = PC 本地 edge-tts，可指定台湾腔等音色
    "tts_backend": "mi",
    "tts_voice": "zh-TW-HsiaoChenNeural",  # edge 模式音色：台湾腔女声
    "tts_rate": "+0%",
    "tts_volume": "+0%",
    "tts_pitch": "+0Hz",
    "min_query_len": 2,
    "max_tts_chars": 300,
    "heartbeat_minutes": 30,
    "skip_queries": ["开始持续对话", "结束持续对话", "小爱同学", "小爱"],
    "blocked_patterns": [],
    "startup_ping": True,
}


# ------------------------------------------------------------------ 文本工具

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def split_for_tts(text: str, limit: int = 80) -> list[str]:
    """按标点切成 <=limit 的片段：小爱 TTS 单次有长度限制，长文会被截断。"""
    text = (text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    buf = ""
    for seg in _SENT_SPLIT.split(text):
        if not seg:
            continue
        while len(seg) > limit:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(seg[:limit])
            seg = seg[limit:]
        if buf and len(buf) + len(seg) > limit:
            parts.append(buf)
            buf = seg
        else:
            buf += seg
    if buf:
        parts.append(buf)
    return [p for p in (x.strip() for x in parts) if p]


def tts_wait_seconds(chunk: str, char_delay_ms) -> float:
    """按字数计算两段 TTS 之间的等待秒数。

    历史 bug：这里原本是 ``len(chunk) / tts_speed``，speed 默认 0.19，
    80 字会算出 421 秒（7 分钟）——把「每字秒数」当成了「每秒字数」又做了除法。
    正确语义是每字约 190ms，80 字约 15 秒，与小爱实际朗读节奏一致。
    """
    try:
        delay = float(char_delay_ms)
    except (TypeError, ValueError):
        delay = 190.0
    if delay <= 0:
        return 0.0
    return len(chunk) * delay / 1000.0


# ------------------------------------------------------------------ 主体

class XiaoaiBot:
    def __init__(self, cfg: dict):
        self.hardware = cfg.get("hardware", "LX06")
        self.account_user = cfg.get("account", "")
        self.account_pass = cfg.get("password", "")
        self.cookie_raw = (cfg.get("cookie") or "").strip()
        self.mi_did = str(cfg.get("mi_did") or "")
        self.opts = {**DEFAULTS, **(cfg.get("bot_options") or {})}

        self._session: aiohttp.ClientSession | None = None
        self.account = None
        self.mina: MiNAService | None = None
        self.miio: MiIOService | None = None
        self.device_id = ""
        self.cookies: dict[str, str] = {}
        self.last_ts = int(time.time() * 1000)
        self._seen: list[str] = []
        self._stop = asyncio.Event()
        self._http: httpx.AsyncClient | None = None
        self._edge_voice: EdgeVoice | None = None
        self.stats = {"native": 0, "tts": 0, "skip": 0, "error": 0, "polls": 0}

    # -- 生命周期 -------------------------------------------------

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        self._http = httpx.AsyncClient(timeout=self.opts["bridge_timeout"])
        return self

    async def __aexit__(self, *exc):
        if self._http:
            await self._http.aclose()
        if self._session:
            await self._session.close()

    def stop(self):
        self._stop.set()

    # -- 登录 -----------------------------------------------------

    async def login(self) -> None:
        if not self.account_user or not self.account_pass:
            if not self.cookie_raw:
                raise RuntimeError("配置里既没有账号密码，也没有 cookie，无法登录小米云")
        self.account = MiAccount(self._session, self.account_user, self.account_pass, TOKEN_PATH)
        await self.account.login("micoapi")
        self.mina = MiNAService(self.account)
        self.miio = MiIOService(self.account)
        await self._resolve_device()
        await self._refresh_cookies()
        log.info("登录成功，设备型号=%s", self.hardware)

    async def _resolve_device(self) -> None:
        if self.cookie_raw:
            for kv in self.cookie_raw.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    self.cookies[k.strip()] = v.strip()
            self.device_id = self.cookies.get("deviceId", "")
            if self.device_id:
                log.info("cookie 指定设备已生效")
                return
        devices = await self.mina.device_list()
        picked = None
        for d in devices:
            if self.mi_did and str(d.get("miotDID", "")) == self.mi_did:
                picked = d
                break
            if not self.mi_did and d.get("hardware") == self.hardware:
                picked = d
                break
        if picked is None:
            names = [f"{d.get('hardware')}/{d.get('miotDID')}/{d.get('name')}" for d in devices]
            raise RuntimeError(
                f"没找到型号 {self.hardware} 的音箱。账号下的设备：{names}；"
                f"请在配置里改成正确型号，或直接填 mi_did"
            )
        self.device_id = picked.get("deviceID", "")
        if not self.mi_did:
            self.mi_did = str(picked.get("miotDID", ""))

    async def _refresh_cookies(self) -> None:
        if self.cookie_raw and self.cookies:
            return  # 手工 cookie 模式不覆盖
        try:
            token = self.account.token["micoapi"][1]
            self.cookies = {
                "userId": str(self.account.token.get("userId", "")),
                "serviceToken": token,
                "deviceId": self.device_id,
            }
        except Exception as e:
            raise RuntimeError(f"取 serviceToken 失败：{e}") from e

    # -- 读对话 ---------------------------------------------------

    async def fetch_new(self) -> list[dict]:
        url = CONVERSATION_API.format(
            hardware=self.hardware, ts=int(time.time() * 1000)
        )
        timeout = aiohttp.ClientTimeout(total=15)
        async with self._session.get(url, cookies=self.cookies, timeout=timeout) as r:
            if r.status in (401, 403):
                log.warning("对话接口鉴权失效（%s），重新登录", r.status)
                await self.login()
                return []
            r.raise_for_status()
            data = await r.json()

        raw = data.get("data")
        if not raw:
            return []
        try:
            records = json.loads(raw).get("records") or []
        except Exception:
            return []
        # 接口一次可能带出多条，按时间正序全部处理；只取 records[0] 会漏掉
        # 连问两句时的前一句（xiaogpt 的老问题）。
        fresh = [r for r in records if int(r.get("time") or 0) > self.last_ts]
        if not fresh:
            return []
        fresh.sort(key=lambda r: int(r.get("time") or 0))
        self.last_ts = int(fresh[-1].get("time") or 0)
        return fresh

    def _dedupe(self, rec: dict) -> bool:
        key = str(rec.get("requestId") or rec.get("time") or "")
        if not key:
            return False
        if key in self._seen:
            return True
        self._seen.append(key)
        if len(self._seen) > 200:
            self._seen = self._seen[-100:]
        return False

    # -- 主循环 ---------------------------------------------------

    async def run(self) -> None:
        await self.login()
        if self.opts.get("startup_ping"):
            await self._ping()
        last_beat = time.time()
        # 注意：播报是串行的（同一时刻只让小爱说一件事），代价是长回答期间
        # 轮询暂停几秒。用 limit=3 一次多取几条来兜住这个空窗。
        while not self._stop.is_set():
            started = time.perf_counter()
            self.stats["polls"] += 1
            try:
                for rec in await self.fetch_new():
                    await self.handle(rec)
                    if self._stop.is_set():
                        break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.stats["error"] += 1
                log.warning("轮询出错：%s", type(e).__name__)
                await asyncio.sleep(2)

            if time.time() - last_beat > self.opts["heartbeat_minutes"] * 60:
                last_beat = time.time()
                log.info("心跳 %s", self.stats_line())

            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(0.0, float(self.opts["poll_interval"]) - elapsed))

    async def handle(self, rec: dict) -> None:
        if self._dedupe(rec):
            return
        query = (rec.get("query") or "").strip()
        if not query:
            return
        if query in set(self.opts["skip_queries"]) or len(query) < int(self.opts["min_query_len"]):
            self.stats["skip"] += 1
            return
        for pat in self.opts.get("blocked_patterns") or []:
            if re.search(pat, query):
                log.info("命中黑名单，跳过（%d 字）", len(query))
                self.stats["skip"] += 1
                return

        log.info("▶ 收到对话（%d 字）", len(query))

        t0 = time.perf_counter()
        try:
            r = await self._http.post(
                self.opts["bridge_url"],
                json={
                    "query": query,
                    "session_id": f"xiaoai-{self.device_id}",
                    "device_id": self.device_id,
                },
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stats["error"] += 1
            log.warning("桥不可用（%s），本轮不干预，保持小爱原样", type(e).__name__)
            return

        cost = (time.perf_counter() - t0) * 1000
        rtype = data.get("type")
        content = (data.get("content") or "").strip()
        meta = data.get("meta") or {}

        if rtype == "native_cmd":
            self.stats["native"] += 1
            log.info("↳ native_cmd（%.0fms，%s）→ 放行，不播报", cost, meta.get("reason"))
            return

        if rtype == "tts_reply" and content:
            self.stats["tts"] += 1
            log.info("↳ tts_reply（%.0fms，%s）→ 播报 %d 字", cost, meta.get("adapter"), len(content))
            await self.speak(content)
            return

        log.warning("↳ 返回不可用：type=%s", data.get("type"))

    async def _ping(self) -> None:
        base = self.opts["bridge_url"].split("/api/")[0]
        try:
            r = await self._http.get(f"{base}/healthz", timeout=5)
            log.info("桥健康检查：%s", r.json())
        except Exception as e:
            log.warning("桥暂不可达（%s），稍后自动重试", type(e).__name__)

    # -- 播报 -----------------------------------------------------

    async def speak(self, text: str) -> None:
        backend = str(self.opts.get("tts_backend", "mi")).lower()
        if backend == "edge":
            await self._speak_edge(text)
        else:
            await self._speak_mi(text)

    async def _speak_mi(self, text: str) -> None:
        """小爱自带音色：先让它闭嘴，再分段下发，段间按字数留间隔。"""
        delay = float(self.opts["pre_tts_delay"])
        if delay:
            await asyncio.sleep(delay)

        if self.opts["mute_before_tts"]:
            with contextlib.suppress(Exception):
                status = await self.mina.player_get_status(self.device_id)
                if (status or {}).get("status") == 1:
                    await self.mina.player_pause(self.device_id)

        text = text[: int(self.opts["max_tts_chars"])]
        for chunk in split_for_tts(text, int(self.opts["tts_chunk"])):
            try:
                await self.mina.text_to_speech(self.device_id, chunk)
            except Exception as e:
                log.warning("TTS 下发失败：%s", type(e).__name__)
                break
            await asyncio.sleep(tts_wait_seconds(chunk, self.opts["tts_char_delay_ms"]))

    async def _speak_edge(self, text: str) -> None:
        """本地 edge-tts：声音从 PC 声卡出，不碰小爱播放器，无需 mute。"""
        if self._edge_voice is None:
            self._edge_voice = EdgeVoice(
                voice=self.opts.get("tts_voice"),
                rate=self.opts.get("tts_rate"),
                volume=self.opts.get("tts_volume"),
                pitch=self.opts.get("tts_pitch"),
            )
        text = text[: int(self.opts["max_tts_chars"])]
        try:
            await self._edge_voice.speak(text)
        except Exception as e:
            log.warning("本地 TTS 失败（%s）：%s", type(e).__name__, e)

    def stats_line(self) -> str:
        s = self.stats
        return (f"polls={s['polls']} native={s['native']} tts={s['tts']} "
                f"skip={s['skip']} error={s['error']}")


# ------------------------------------------------------------------ 入口

def load_config(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"配置文件不存在：{path}（先把 config/xiaogpt.yaml.example 复制成 xiaogpt.yaml）")
    with p.open("rb") as f:
        return yaml.safe_load(f) or {}


async def check(cfg: dict) -> None:
    """--check：验证登录与设备，不启动监听。"""
    async with XiaoaiBot(cfg) as bot:
        await bot.login()
        print("设备型号:", bot.hardware, "｜连接正常")
        recs = await bot.fetch_new()
        print("对话接口:", "可读取" if recs else "无新记录")


def main() -> None:
    ap = argparse.ArgumentParser(description="小爱全量监听 → 中转桥 → 分发播报")
    ap.add_argument("--config", default=os.getenv("XIAOGPT_CONFIG", "/app/config/xiaogpt.yaml"))
    ap.add_argument("--check", action="store_true", help="只验证登录与设备，然后退出")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s | %(message)s",
    )
    cfg = load_config(args.config)

    if args.check:
        asyncio.run(check(cfg))
        return

    async def runner():
        async with XiaoaiBot(cfg) as bot:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                with contextlib.suppress(NotImplementedError):
                    loop.add_signal_handler(sig, bot.stop)
            try:
                await bot.run()
            finally:
                log.info("退出统计：%s", bot.stats_line())

    asyncio.run(runner())


if __name__ == "__main__":
    main()
