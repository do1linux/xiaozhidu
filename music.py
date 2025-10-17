from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse

# 初始化MCP
mcp = FastMCP("MusicService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://api.yaohud.cn/api/music/wy'

@mcp.tool()
def play_song(song_name: str) -> dict:
    """
    播放歌曲 - 返回适合小智AI硬件播放的指令格式
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含播放指令和歌曲信息
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {
            "success": False,
            "error": "API密钥未配置"
        }
    
    if not song_name.strip():
        return {
            "success": False,
            "error": "歌曲名不能为空"
        }
    
    try:
        # 调用音乐API获取歌曲信息
        logger.info(f"搜索歌曲: {song_name}")
        
        # URL编码歌曲名称
        encoded_song_name = urllib.parse.quote(song_name.strip())
        
        # 构建完整URL
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n=1"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        music_data = data.get('data', {})
        music_url = music_data.get('musicurl')
        
        if not music_url:
            return {
                "success": False,
                "error": "未找到可播放的歌曲"
            }
        
        # 返回适合小智AI硬件播放的指令格式
        result = {
            "success": True,
            "action": "music_play",
            "command": {
                "type": "audio_stream",
                "url": music_url,
                "format": "mp3",
                "metadata": {
                    "title": music_data.get('name', '未知'),
                    "artist": music_data.get('songname', '未知'),
                    "album": music_data.get('album', '未知')
                }
            },
            "instruction": "使用硬件音频播放器播放此流媒体URL",
            "user_message": f"正在播放: {music_data.get('name', '未知')} - {music_data.get('songname', '未知')}"
        }
        
        logger.info(f"成功获取歌曲: {result['command']['metadata']['title']}")
        return result
        
    except Exception as e:
        logger.error(f"播放歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}"
        }

@mcp.tool()
def search_songs(keyword: str, limit: int = 5) -> dict:
    """
    搜索歌曲
    Args:
        keyword: 搜索关键词
        limit: 返回数量
    Returns:
        dict: 歌曲列表
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {"success": False, "error": "API密钥未配置"}
    
    try:
        encoded_keyword = urllib.parse.quote(keyword.strip())
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_keyword}&n={limit}"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        songs_data = data.get('data', {})
        songs_list = songs_data.get('songs', [])
        
        if not songs_list:
            return {
                "success": True,
                "action": "search_results",
                "message": "未找到相关歌曲",
                "songs": []
            }
        
        # 格式化歌曲列表
        songs = []
        for song in songs_list[:limit]:
            songs.append({
                "number": song.get('n'),
                "title": song.get('name', '未知'),
                "artist": song.get('singer', '未知'),
                "album": song.get('album', '未知'),
                "playable": True
            })
        
        return {
            "success": True,
            "action": "search_results",
            "songs": songs,
            "count": len(songs),
            "instruction": "使用 play_song 工具播放特定歌曲"
        }
        
    except Exception as e:
        logger.error(f"搜索歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }

@mcp.tool()
def get_music_status() -> dict:
    """
    获取音乐服务状态
    Returns:
        dict: 服务状态信息
    """
    return {
        "success": True,
        "service": "MusicService",
        "version": "1.0",
        "supported_actions": ["play_song", "search_songs"],
        "playback_method": "hardware_audio_stream",
        "status": "running"
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
