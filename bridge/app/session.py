"""极简会话记忆：只为多轮追问（"那第二个呢"）服务，落内存，重启即丢。"""
from __future__ import annotations

import time
from collections import OrderedDict, deque


class SessionStore:
    def __init__(self, max_sessions: int = 200, max_turns: int = 6):
        self.max_sessions = max_sessions
        self.max_turns = max_turns
        self._data: OrderedDict[str, deque] = OrderedDict()

    def history(self, session_id: str) -> list[dict]:
        return list(self._data.get(session_id, ()))

    def append(self, session_id: str, query: str, answer: str) -> None:
        dq = self._data.get(session_id)
        if dq is None:
            dq = deque(maxlen=self.max_turns)
            self._data[session_id] = dq
        dq.append({"q": query, "a": answer, "ts": int(time.time())})
        self._data.move_to_end(session_id)
        while len(self._data) > self.max_sessions:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
