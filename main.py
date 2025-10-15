from mcp.server.fastmcp import FastMCP
import requests
from playsound import playsound
import tempfile
import os
import logging
import threading
from dotenv import load_dotenv

# ------------------- 1. 基础初始化 -------------------
load_dotenv()  # 加载本地.env文件（可选，优先于环境变量）
mcp = FastMCP("MusicPlayer")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

# ------------------- 2. 配置参数（关键：从环境变量读TOKEN） -------------------
_MUSIC_API_URL = " https://api.yaohud.cn/api/music/wy "
_MUSIC_API_KEY = os.getenv("MUSIC_API_KEY")  # 音乐API Key（可选，若需）
# 从GitHub Secrets读取MCP服务Token，拼接WSS端点
MCP_WSS_TOKEN = os.getenv("MCP_WSS_TOKEN")  # 必须：GitHub Actions中设置的Secret
if not MCP_WSS_TOKEN:
    raise ValueError("MCP_WSS_TOKEN环境变量未配置！")
MCP_WSS_ENDPOINT = f"wss://api.xiaozhi.me/mcp/?token={MCP_WSS_TOKEN}"  # 动态生成接入点

# ------------------- 3. 核心工具：播放音乐（优化播放异常处理） -------------------
@mcp.tool(name="play_music")
def play_music(song_name: str) -> str:
    clean_name = song_name.strip()
    if not clean_name:
        return "❌ 错误：歌曲名不能为空"

    with _LOCK:
        try:
            # 1. 搜索歌曲
            logger.info(f"🔍 搜索歌曲：{clean_name}")
            api_params = {"key": _MUSIC_API_KEY, "msg": clean_name, "n": 1}
            api_resp = requests.post(_MUSIC_API_URL, params=api_params, timeout=10)
            api_resp.raise_for_status()
            music_url = api_resp.json().get("data", {}).get("musicurl")
            if not music_url:
                return "❌ 错误：未找到歌曲URL"

            # 2. 下载临时文件
            logger.info(f"⬇️ 下载歌曲：{clean_name}")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_file.write(requests.get(music_url, timeout=10).content)
                tmp_path = tmp_file.name

            # 3. 播放（捕获无音频设备的异常）
            logger.info(f"▶️ 尝试播放：{clean_name}")
            try:
                playsound(tmp_path)
            except Exception as e:
                logger.warning(f"⚠️ 播放失败（无音频设备？）：{str(e)}")
                return f"🎵 歌曲已下载，但播放失败（无音频设备）：{clean_name}"
            os.unlink(tmp_path)
            logger.info(f"✅ 播放完成：{clean_name}")

            return f"🎵 播放成功：{clean_name}"

        except requests.exceptions.HTTPError as e:
            logger.error(f"🌐 API调用失败：{str(e)}")
            return f"❌ 网络错误：音乐API返回状态码{e.response.status_code}"
        except KeyError:
            logger.error("🔑 API数据格式错误（可能Key失效）")
            return "❌ 错误：音乐API返回数据异常"
        except Exception as e:
            logger.error(f"⚠️ 未知错误：{str(e)}")
            return f"❌ 播放失败：{str(e)}"

# ------------------- 4. 启动服务（保持后台运行） -------------------
if __name__ == "__main__":
    # 配置日志（写入文件+控制台）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("music_player.log"), logging.StreamHandler()]
    )
    logger.info(f"🚀 启动服务，连接到MCP端点：{MCP_WSS_ENDPOINT}")
    try:
        mcp.run(
            transport="websocket",
            endpoint=MCP_WSS_ENDPOINT,
            cors_allowed_origins=["*"]
        )
    except Exception as e:
        logger.critical(f"💥 服务启动失败：{str(e)}")
        os._exit(1)
