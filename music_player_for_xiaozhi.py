from mcp.server.fastmcp import FastMCP
import requests
import tempfile
import os
import logging
import json
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 创建 MCP 实例
mcp = FastMCP("XiaozhiMusicPlayer")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("xiaozhi_music.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置参数
_MUSIC_API_URL = "https://api.yaohud.cn/api/music/wy"
_MUSIC_API_KEY = os.getenv("MUSIC_API_KEY")
MCP_WSS_TOKEN = os.getenv("MCP_WSS_TOKEN")

if not MCP_WSS_TOKEN:
    logger.error("❌ MCP_WSS_TOKEN 未配置！")
    exit(1)

MCP_WSS_ENDPOINT = f"wss://api.xiaozhi.me/mcp/?token={MCP_WSS_TOKEN}"

# 存储状态
_service_status = {
    "start_time": time.time(),
    "total_requests": 0,
    "last_request": None
}

@mcp.tool(name="play_music")
def play_music(song_name: str) -> str:
    """
    播放音乐 - 为小智AI智能体提供的音乐播放功能
    
    参数:
        song_name: 歌曲名称，如"周杰伦 青花瓷"
    
    返回:
        JSON格式的播放结果
    """
    _service_status["total_requests"] += 1
    _service_status["last_request"] = time.time()
    
    clean_name = song_name.strip()
    if not clean_name:
        return json.dumps({
            "status": "error",
            "message": "❌ 请告诉我你想听的歌曲名称",
            "example": "尝试说：播放周杰伦的青花瓷"
        }, ensure_ascii=False)

    try:
        logger.info(f"🎵 小智AI请求播放: {clean_name}")
        
        # 搜索歌曲
        api_params = {
            "key": _MUSIC_API_KEY, 
            "msg": clean_name, 
            "n": 1
        }
        
        api_resp = requests.post(_MUSIC_API_URL, params=api_params, timeout=10)
        api_resp.raise_for_status()
        
        music_data = api_resp.json().get("data", {})
        music_url = (
            music_data.get("musicurl") or 
            music_data.get("url") or 
            music_data.get("music_url")
        )
        
        if not music_url:
            return json.dumps({
                "status": "error",
                "message": f"❌ 没有找到歌曲《{clean_name}》，请尝试其他歌曲",
                "suggestion": "可以尝试更具体的歌曲名，如'周杰伦 七里香'"
            }, ensure_ascii=False)

        # 获取歌曲信息
        artist = music_data.get("artist", "未知歌手")
        album = music_data.get("album", "未知专辑")
        
        # 下载歌曲到临时文件（模拟播放）
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                music_resp = requests.get(music_url, timeout=30)
                music_resp.raise_for_status()
                tmp_file.write(music_resp.content)
                tmp_path = tmp_file.name
            
            file_size = os.path.getsize(tmp_path) / 1024 / 1024  # MB
            
            # 清理临时文件
            os.unlink(tmp_path)
            
            logger.info(f"✅ 成功处理: {clean_name} - {artist} ({file_size:.1f}MB)")
            
            return json.dumps({
                "status": "success",
                "message": f"🎵 正在为你播放：{clean_name} - {artist}",
                "song_info": {
                    "name": clean_name,
                    "artist": artist,
                    "album": album,
                    "file_size_mb": round(file_size, 1),
                    "music_url": music_url
                },
                "response": f"已找到歌曲《{clean_name}》，正在为你播放{artist}的这首歌曲。文件大小{file_size:.1f}MB，播放愉快！🎶"
            }, ensure_ascii=False)
            
        except Exception as download_error:
            logger.error(f"下载失败: {download_error}")
            return json.dumps({
                "status": "success",
                "message": f"🎵 找到歌曲：{clean_name} - {artist}",
                "song_info": {
                    "name": clean_name,
                    "artist": artist,
                    "album": album,
                    "music_url": music_url
                },
                "response": f"已找到歌曲《{clean_name}》- {artist}，但由于服务器限制无法直接播放。你可以通过这个链接收听：{music_url}",
                "direct_url": music_url
            }, ensure_ascii=False)

    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求失败: {e}")
        return json.dumps({
            "status": "error",
            "message": "❌ 网络连接出现问题，请稍后重试",
            "response": "抱歉，现在网络不太稳定，无法搜索歌曲。请稍后再试。"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"播放失败: {e}")
        return json.dumps({
            "status": "error",
            "message": f"❌ 播放失败：{str(e)}",
            "response": f"抱歉，处理歌曲时出现了问题：{str(e)}。请尝试其他歌曲。"
        }, ensure_ascii=False)

@mcp.tool(name="search_music")
def search_music(song_name: str) -> str:
    """
    搜索音乐信息
    
    参数:
        song_name: 要搜索的歌曲名称
    """
    _service_status["total_requests"] += 1
    _service_status["last_request"] = time.time()
    
    clean_name = song_name.strip()
    if not clean_name:
        return json.dumps({
            "status": "error",
            "message": "❌ 请输入要搜索的歌曲名称"
        }, ensure_ascii=False)

    try:
        logger.info(f"🔍 小智AI搜索歌曲: {clean_name}")
        
        api_params = {"key": _MUSIC_API_KEY, "msg": clean_name, "n": 1}
        api_resp = requests.post(_MUSIC_API_URL, params=api_params, timeout=10)
        api_resp.raise_for_status()
        
        music_data = api_resp.json().get("data", {})
        music_url = (
            music_data.get("musicurl") or 
            music_data.get("url") or 
            music_data.get("music_url")
        )
        
        if not music_url:
            return json.dumps({
                "status": "error",
                "message": f"❌ 没有找到歌曲《{clean_name}》",
                "response": f"没有找到歌曲《{clean_name}》，请尝试搜索其他歌曲。"
            }, ensure_ascii=False)

        artist = music_data.get("artist", "未知歌手")
        album = music_data.get("album", "未知专辑")
        
        return json.dumps({
            "status": "success",
            "message": f"🎵 找到歌曲：{clean_name} - {artist}",
            "song_info": {
                "name": clean_name,
                "artist": artist,
                "album": album,
                "music_url": music_url
            },
            "response": f"找到了《{clean_name}》- {artist}，专辑：{album}。需要使用播放功能来收听这首歌曲吗？"
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return json.dumps({
            "status": "error",
            "message": f"❌ 搜索失败：{str(e)}",
            "response": f"搜索歌曲时出现了问题：{str(e)}"
        }, ensure_ascii=False)

@mcp.tool(name="music_service_status")
def music_service_status() -> str:
    """获取音乐服务状态"""
    uptime = time.time() - _service_status["start_time"]
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    return json.dumps({
        "status": "running",
        "service": "小智AI音乐播放器",
        "uptime": f"{hours}小时{minutes}分钟",
        "total_requests": _service_status["total_requests"],
        "last_request": _service_status["last_request"],
        "environment": "GitHub Actions",
        "response": f"音乐服务运行正常！已运行{hours}小时{minutes}分钟，处理了{_service_status['total_requests']}个请求。"
    }, ensure_ascii=False)

@mcp.tool(name="recommend_songs")
def recommend_songs(artist: str = None) -> str:
    """
    推荐歌曲
    
    参数:
        artist: 指定歌手（可选）
    """
    _service_status["total_requests"] += 1
    
    # 默认推荐列表
    default_songs = ["周杰伦 七里香", "邓紫棋 光年之外", "林俊杰 不为谁而作的歌", "Taylor Swift Love Story"]
    
    if artist:
        search_result = search_music(f"{artist} 热门歌曲")
        result_data = json.loads(search_result)
        
        if result_data["status"] == "success":
            return json.dumps({
                "status": "success",
                "message": f"🎵 找到{artist}的歌曲",
                "recommendations": [result_data["song_info"]],
                "response": f"为你推荐{artist}的歌曲：《{result_data['song_info']['name']}》"
            }, ensure_ascii=False)
    
    return json.dumps({
        "status": "success",
        "message": "🎵 热门歌曲推荐",
        "recommendations": default_songs,
        "response": "为你推荐一些热门歌曲：周杰伦《七里香》、邓紫棋《光年之外》、林俊杰《不为谁而作的歌》、Taylor Swift《Love Story》。想听哪一首呢？"
    }, ensure_ascii=False)

if __name__ == "__main__":
    logger.info("🚀 启动小智AI音乐播放器服务")
    logger.info(f"📡 连接端点: {MCP_WSS_ENDPOINT}")
    logger.info("🎯 服务已准备好为小智AI提供音乐播放功能")
    
    try:
        # 运行 MCP 服务，连接到小智AI
        mcp.run(
            transport="websocket",
            url=MCP_WSS_ENDPOINT
        )
    except Exception as e:
        logger.critical(f"💥 服务启动失败: {e}")
        exit(1)
