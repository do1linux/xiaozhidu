"""本地 TTS：edge-tts 生成音频 + 本机声卡播放。

与 mi 模式的区别：音色由 edge-tts 决定（如台湾腔女声 zh-TW-HsiaoChenNeural），
播报出口是 PC 声卡而不是小爱音箱。小爱仍负责唤醒、听写与原生指令（开灯/放歌），
大模型的回答从电脑喇叭出来——两条声音链路是分开的，见 README「台湾腔」。

设计要点：
- 合成与播放都可注入（synth / player），测试时不联网、不发声。
- 播放走 asyncio.to_thread，避免阻塞 bot 的小米云轮询循环。
- 临时 mp3 播完即删，不落用户数据。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile

log = logging.getLogger("xiaoai.tts")

DEFAULT_VOICE = "zh-TW-HsiaoChenNeural"  # 台湾腔女声


class EdgeVoice:
    """把文本合成为 mp3 并在本机播放。

    :param voice: 音色名，默认台湾腔女声；可用 edge_tts.Communicate 支持的任意音色。
    :param synth: 异步合成函数 (text, path) -> None；None 则用 edge_tts。
    :param player: 异步播放函数 (path) -> None；None 则用 playsound（丢到线程）。
    """

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        synth=None,
        player=None,
    ):
        self.voice = voice or DEFAULT_VOICE
        self.rate = rate or "+0%"
        self.volume = volume or "+0%"
        self.pitch = pitch or "+0Hz"
        self._synth = synth
        self._player = player

    async def _default_synth(self, text: str, path: str) -> None:
        import edge_tts  # 延迟导入：未启用 edge 模式时不要求已安装

        comm = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
        )
        await comm.save(path)

    @staticmethod
    async def _default_player(path: str) -> None:
        from playsound import playsound  # 延迟导入，同上

        # playsound 是同步阻塞的，丢到线程里跑，别卡住轮询循环
        await asyncio.to_thread(playsound, path)

    async def speak(self, text: str) -> None:
        """合成并播放一段文本；临时文件用完即删。"""
        text = (text or "").strip()
        if not text:
            return
        fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="vb_tts_")
        os.close(fd)
        try:
            synth = self._synth or self._default_synth
            await synth(text, tmp)
            player = self._player or self._default_player
            await player(tmp)
        finally:
            with contextlib.suppress(OSError):
                os.remove(tmp)
