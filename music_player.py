from mcp.server.fastmcp import FastMCP
import requests
import tempfile
import os
import logging
import threading
from dotenv import load_dotenv
import json
import time
import asyncio

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
    MCP_WSS_ENDPOINT = None
else:
    MCP_WSS_ENDPOINT = f"wss://api.xiaozhi.me/mcp/?token={MCP_WSS_TOKEN}"

# 存储歌曲信息的全局变量
_current_song_info = {
    "name": None,
    "url": None,
    "downloaded_path": None,
    "status": "idle"
}

# ------------------- 3. 核心工具：搜索和准备音乐 -------------------
@mcp.tool(name="search_music")
def search_music(song_name: str) -> str:
    """搜索音乐并返回歌曲信息（不播放）"""
    clean_name = song_name.strip()
    if not clean_name:
        return "❌ 错误：歌曲名不能为空"

    try:
        logger.info(f"🔍 搜索歌曲：{clean_name}")
        api_params = {"key": _MUSIC_API_KEY, "msg": clean_name, "n": 1}
        api_resp = requests.post(_MUSIC_API_URL, params=api_params, timeout=10)
        api_resp.raise_for_status()
        
        music_data = api_resp.json().get("data", {})
        music_url = music_data.get("musicurl")
        if not music_url:
            music_url = music_data.get("url") or music_data.get("music_url")
        
        if not music_url:
            logger.error(f"未找到歌曲URL，响应数据: {music_data}")
            return "❌ 错误：未找到歌曲URL"

        # 更新全局歌曲信息
        global _current_song_info
        _current_song_info = {
            "name": clean_name,
            "url": music_url,
            "downloaded_path": None,
            "status": "searched"
        }

        # 尝试获取更多信息
        artist = music_data.get("artist", "未知歌手")
        album = music_data.get("album", "未知专辑")
        
        logger.info(f"✅ 搜索成功：{clean_name} - {artist}")
        return json.dumps({
            "status": "success",
            "song_name": clean_name,
            "artist": artist,
            "album": album,
            "music_url": music_url,
            "message": f"🎵 找到歌曲：{clean_name} - {artist}"
        }, ensure_ascii=False)

    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 网络请求失败：{str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"❌ 网络错误：{str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"⚠️ 搜索歌曲时发生错误：{str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"❌ 搜索失败：{str(e)}"
        }, ensure_ascii=False)

@mcp.tool(name="download_music")
def download_music() -> str:
    """下载当前搜索到的歌曲"""
    global _current_song_info
    
    if _current_song_info["status"] != "searched":
        return "❌ 错误：请先使用 search_music 搜索歌曲"
    
    try:
        song_name = _current_song_info["name"]
        music_url = _current_song_info["url"]
        
        logger.info(f"⬇️ 下载歌曲：{song_name}")
        
        # 下载到临时文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            music_resp = requests.get(music_url, timeout=30)
            music_resp.raise_for_status()
            tmp_file.write(music_resp.content)
            tmp_path = tmp_file.name

        # 更新状态
        _current_song_info["downloaded_path"] = tmp_path
        _current_song_info["status"] = "downloaded"
        
        # 获取文件大小
        file_size = os.path.getsize(tmp_path) / 1024 / 1024  # MB
        
        logger.info(f"✅ 下载完成：{song_name} ({file_size:.2f}MB)")
        return json.dumps({
            "status": "success",
            "song_name": song_name,
            "file_path": tmp_path,
            "file_size_mb": round(file_size, 2),
            "message": f"✅ 歌曲下载完成：{song_name} ({file_size:.2f}MB)"
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"⚠️ 下载歌曲时发生错误：{str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"❌ 下载失败：{str(e)}"
        }, ensure_ascii=False)

@mcp.tool(name="get_song_info")
def get_song_info() -> str:
    """获取当前歌曲信息"""
    global _current_song_info
    return json.dumps(_current_song_info, ensure_ascii=False)

@mcp.tool(name="play_music")
def play_music(song_name: str) -> str:
    """兼容旧接口：搜索、下载并准备播放"""
    # 1. 搜索歌曲
    search_result = search_music(song_name)
    search_data = json.loads(search_result)
    
    if search_data["status"] != "success":
        return search_result
    
    # 2. 下载歌曲
    download_result = download_music()
    download_data = json.loads(download_result)
    
    if download_data["status"] != "success":
        return download_result
    
    # 3. 在服务器环境中，我们无法真正播放，但返回成功信息
    song_name = _current_song_info["name"]
    file_size = download_data["file_size_mb"]
    
    logger.info(f"🎵 歌曲准备就绪：{song_name}")
    return json.dumps({
        "status": "success", 
        "message": f"🎵 歌曲 '{song_name}' 已准备就绪 ({file_size}MB) - 服务器环境无法播放音频，但已成功下载",
        "song_name": song_name,
        "file_size_mb": file_size,
        "note": "在服务器环境中，音频文件已下载但无法播放。您可以在本地环境中使用此服务进行播放。"
    }, ensure_ascii=False)

# ------------------- 4. 服务器环境健康检查 -------------------
@mcp.tool(name="health_check")
def health_check() -> str:
    """检查服务健康状态"""
    return json.dumps({
        "status": "healthy",
        "service": "MCP音乐播放器",
        "environment": "GitHub Actions服务器",
        "timestamp": time.time(),
        "current_song": _current_song_info["name"] or "无"
    }, ensure_ascii=False)

@mcp.tool(name="service_status")
def service_status() -> str:
    """获取服务状态"""
    return json.dumps({
        "service": "MCP Music Player",
        "status": "running",
        "environment": "server",
        "audio_support": False,
        "features": ["search", "download", "metadata"],
        "current_song": _current_song_info
    }, ensure_ascii=False)

# ------------------- 5. 清理资源 -------------------
@mcp.tool(name="cleanup")
def cleanup() -> str:
    """清理临时文件"""
    global _current_song_info
    
    if _current_song_info["downloaded_path"] and os.path.exists(_current_song_info["downloaded_path"]):
        try:
            os.unlink(_current_song_info["downloaded_path"])
            logger.info(f"🧹 清理临时文件：{_current_song_info['downloaded_path']}")
        except Exception as e:
            logger.warning(f"⚠️ 清理临时文件失败：{str(e)}")
    
    _current_song_info = {
        "name": None,
        "url": None,
        "downloaded_path": None,
        "status": "idle"
    }
    
    return "✅ 资源清理完成"

# ------------------- 6. 启动服务 -------------------
async def main():
    """主异步函数"""
    if not MCP_WSS_ENDPOINT:
        logger.error("❌ 无法启动：MCP_WSS_TOKEN未配置")
        logger.info("💡 请在GitHub仓库的Settings -> Secrets中配置MCP_WSS_TOKEN")
        return

    logger.info(f"🚀 启动服务，连接到MCP端点：{MCP_WSS_ENDPOINT}")
    logger.info("🏭 运行环境：GitHub Actions服务器（无音频支持）")
    logger.info("📋 可用功能：搜索音乐、下载音乐、获取元数据")
    
    try:
        # 正确的 FastMCP WebSocket 连接方式
        async with mcp.run_over_websocket(url=MCP_WSS_ENDPOINT) as session:
            logger.info("✅ 成功连接到MCP服务器")
            # 保持连接
            await session.wait_until_done()
    except Exception as e:
        logger.critical(f"💥 服务启动失败：{str(e)}")
        raise

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("music_player.log"), logging.StreamHandler()]
    )
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 服务被用户中断")
    except Exception as e:
        logger.critical(f"💥 服务异常退出：{str(e)}")
        exit(1)
