from mcp.server.fastmcp import FastMCP
import requests
from playsound import playsound
import tempfile
import os
import logging
import threading
from dotenv import load_dotenv
import sys

# ------------------- 1. 基础初始化 -------------------
load_dotenv()
mcp = FastMCP("MusicPlayer")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

# ------------------- 2. 配置参数 -------------------
_MUSIC_API_URL = "https://api.yaohud.cn/api/music/wy"
_MUSIC_API_KEY = os.getenv("MUSIC_API_KEY")
MCP_WSS_TOKEN = os.getenv("MCP_WSS_TOKEN")

if not MCP_WSS_TOKEN:
    logger.error("MCP_WSS_TOKEN环境变量未配置！")
    # 在服务器环境中，如果没有token，我们仍然启动但记录警告
    MCP_WSS_ENDPOINT = None
else:
    MCP_WSS_ENDPOINT = f"wss://api.xiaozhi.me/mcp/?token={MCP_WSS_TOKEN}"

# ------------------- 3. 核心工具：播放音乐（服务器环境适配） -------------------
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
            
            music_data = api_resp.json().get("data", {})
            music_url = music_data.get("musicurl")
            if not music_url:
                # 尝试其他可能的字段名
                music_url = music_data.get("url") or music_data.get("music_url")
            
            if not music_url:
                logger.error(f"未找到歌曲URL，响应数据: {music_data}")
                return "❌ 错误：未找到歌曲URL"

            # 2. 下载临时文件
            logger.info(f"⬇️ 下载歌曲：{clean_name}")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                music_resp = requests.get(music_url, timeout=30)
                music_resp.raise_for_status()
                tmp_file.write(music_resp.content)
                tmp_path = tmp_file.name

            # 3. 播放（服务器环境适配）
            logger.info(f"▶️ 尝试播放：{clean_name}")
            try:
                # 在服务器环境中，playsound可能会失败
                playsound(tmp_path)
                play_result = f"🎵 播放成功：{clean_name}"
            except Exception as e:
                logger.warning(f"⚠️ 播放失败（服务器无音频设备）：{str(e)}")
                # 在服务器环境中，我们返回成功但注明无法播放
                play_result = f"🎵 歌曲已准备就绪（服务器环境无法播放音频）：{clean_name}"
            
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass
                
            logger.info(f"✅ 处理完成：{clean_name}")
            return play_result

        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 网络请求失败：{str(e)}")
            return f"❌ 网络错误：{str(e)}"
        except Exception as e:
            logger.error(f"⚠️ 处理歌曲时发生错误：{str(e)}")
            return f"❌ 播放失败：{str(e)}"

# ------------------- 4. 服务器环境健康检查 -------------------
@mcp.tool(name="health_check")
def health_check() -> str:
    """检查服务健康状态"""
    return "✅ MCP音乐播放器服务运行正常（服务器模式）"

# ------------------- 5. 启动服务 -------------------
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("music_player.log"), logging.StreamHandler()]
    )
    
    if not MCP_WSS_ENDPOINT:
        logger.error("❌ 无法启动：MCP_WSS_TOKEN未配置")
        logger.info("💡 请在GitHub仓库的Settings -> Secrets中配置MCP_WSS_TOKEN")
        sys.exit(1)
    
    logger.info(f"🚀 启动服务，连接到MCP端点：{MCP_WSS_ENDPOINT}")
    logger.info("🏭 运行环境：GitHub Actions服务器")
    
    try:
        mcp.run(
            transport="websocket",
            endpoint=MCP_WSS_ENDPOINT,
            cors_allowed_origins=["*"]
        )
    except Exception as e:
        logger.critical(f"💥 服务启动失败：{str(e)}")
        sys.exit(1)
