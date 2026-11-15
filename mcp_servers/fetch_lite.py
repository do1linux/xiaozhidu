"""受控网页抓取 MCP 服务（stdio 传输，单进程）。

对标 modelcontextprotocol/servers 的 Fetch 参考实现，差异：
- 默认拒绝内网 / 回环 / 链路本地 / 保留地址，仅允许 80 / 443 端口；
- 不自动跟随重定向，避免从公网跳进内网；
- 限制响应体（1MB）与返回长度（默认 6000 字符）；
- 不自动检查 robots.txt，使用前需自行遵守目标站点条款。

由仓库顶层 mcp_pipe.py 启动时 stdout 是 JSON-RPC 通道：禁止 print，
日志一律走 stderr，否则会污染协议流导致 xiaozhi 服务端解析失败。
"""

import html.parser
import ipaddress
import logging
import os
import re
import socket
import sys
import urllib.parse
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)
LOG = logging.getLogger("fetch_lite")

mcp = FastMCP("FetchLite")

_MAX_BYTES = 1_000_000
_MAX_CHARS = 20_000
_ALLOWED_PORTS = (80, 443)
_REDIRECT_CODES = (301, 302, 303, 307, 308)


def _assert_public(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("仅允许 http / https")
    if parts.username or parts.password:
        raise ValueError("URL 不允许携带用户名或口令")
    host = parts.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError("端口不合法") from exc
    if port not in _ALLOWED_PORTS:
        raise ValueError("仅允许 80 / 443 端口")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError("域名无法解析") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise ValueError("目标地址不是允许的公网地址，已拒绝")


class _TextExtractor(html.parser.HTMLParser):
    _SKIP = ("script", "style", "noscript", "svg", "template")
    _BREAK = ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "section")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


@mcp.tool()
def check_url(url: str) -> Dict[str, Any]:
    """只做安全校验、不发 HTTP 请求，返回该地址是否会被 fetch_url 放行。
    可用于离线自检内网拦截是否生效。"""
    try:
        _assert_public(url)
        return {"allowed": True, "url": url}
    except ValueError as exc:
        return {"allowed": False, "url": url, "reason": str(exc)}


@mcp.tool()
def fetch_url(url: str, max_chars: int = 6000, timeout: int = 8) -> Dict[str, Any]:
    """抓取一个公网网页或 JSON 地址并返回纯文本；HTML 会去掉标签与脚本。
    max_chars 取 200..20000，timeout 取 1..15 秒。
    内网地址、非 80/443 端口、重定向一律拒绝。"""
    if not 200 <= max_chars <= _MAX_CHARS:
        raise ValueError("max_chars 需在 200..20000")
    if not 1 <= timeout <= 15:
        raise ValueError("timeout 需在 1..15 秒")
    _assert_public(url)
    headers = {
        "User-Agent": os.environ.get("MCP_FETCH_UA", "FreeMCP-FetchLite/1.0"),
        "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
    }
    resp = requests.get(
        url,
        headers=headers,
        timeout=(3, timeout),
        allow_redirects=False,
        stream=True,
    )
    try:
        if resp.status_code in _REDIRECT_CODES:
            return {
                "url": url,
                "status": resp.status_code,
                "blocked": "redirect",
                "note": "不自动跟随重定向；确认目标安全后请显式传入新地址",
                "text": "",
            }
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        length = resp.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > _MAX_BYTES:
            raise ValueError("响应体超过 1MB 上限")
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=4096):
            buf.extend(chunk)
            if len(buf) >= _MAX_BYTES:
                break
        raw = bytes(buf)
        enc = resp.encoding
        if not enc or enc.lower() in ("iso-8859-1", "latin-1", "latin1"):
            enc = getattr(resp, "apparent_encoding", None) or "utf-8"
        try:
            text = raw.decode(enc, errors="replace")
        except (LookupError, TypeError):
            text = raw.decode("utf-8", errors="replace")
        if ctype in ("text/html", "application/xhtml+xml"):
            parser = _TextExtractor()
            try:
                parser.feed(text)
                text = parser.text()
            except Exception as exc:
                LOG.warning("HTML 解析降级：%s", type(exc).__name__)
                text = re.sub(r"<[^>]+>", " ", text)
        return {
            "url": url,
            "status": resp.status_code,
            "content_type": ctype,
            "bytes": len(raw),
            "chars": min(len(text), max_chars),
            "truncated": len(text) > max_chars,
            "text": text[:max_chars],
        }
    finally:
        resp.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
