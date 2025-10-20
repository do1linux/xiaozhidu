from mcp.server.fastmcp import FastMCP
import requests
import tempfile
import os
import logging
import threading
import base64

# 初始化MCP和日志
mcp = FastMCP("MusicPlayer")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

# 从环境变量获取API密钥
_API_URL = 'https://api.yaohud.cn/api/music/wy'
_API_KEY = os.environ.get('MUSIC_API_KEY')

if not _API_KEY:
    logger.warning("MUSIC_API_KEY环境变量未设置，请设置有效的API密钥")

@mcp.tool()
def play_music(song_name: str) -> str:
    """
    通过MCP接口获取音乐信息，供小智AI客户端播放
    Args:
        song_name: 歌曲名
    Returns:
        str: 音乐URL或错误信息
    """
    if not _API_KEY:
        return "错误：请设置MUSIC_API_KEY环境变量"
    
    if not song_name.strip():
        return "错误：歌曲名不能为空"

    with _LOCK:
        try:
            # 1. 调用API获取音乐信息
            logger.info(f"搜索歌曲: {song_name}")
            params = {'key': _API_KEY, 'msg': song_name.strip(), 'n': '1'}
            resp = requests.post(_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get('code') != 200:
                return f"API错误: {data.get('msg', '未知错误')}"
                
            music_data = data['data']
            music_url = music_data['musicurl']
            
            # 返回完整的音乐信息，小智AI客户端可以使用这些信息播放
            result = {
                "song_name": song_name,
                "music_url": music_url,
                "playable_url": music_url,  # 客户端可以直接播放的URL
                "message": f"找到歌曲: {song_name}，请在小智AI客户端中播放"
            }
            
            return f"音乐播放信息: {result}"

        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求失败: {str(e)}")
            return f"网络请求失败: {str(e)}"
        except Exception as e:
            logger.error(f"获取音乐失败: {str(e)}")
            return f"获取音乐失败: {str(e)}"

@mcp.tool()
def search_music(song_name: str, count: int = 5) -> str:
    """
    搜索多首歌曲
    Args:
        song_name: 歌曲名
        count: 返回结果数量
    Returns:
        str: 搜索结果
    """
    if not _API_KEY:
        return "错误：请设置MUSIC_API_KEY环境变量"
    
    try:
        params = {'key': _API_KEY, 'msg': song_name.strip(), 'n': str(count)}
        resp = requests.post(_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        if data.get('code') != 200:
            return f"API错误: {data.get('msg', '未知错误')}"
            
        songs = data['data']
        result = []
        for i, song in enumerate(songs, 1):
            result.append(f"{i}. {song.get('songname', '未知歌曲')} - {song.get('singername', '未知歌手')}")
        
        return f"找到 {len(result)} 首歌曲:\n" + "\n".join(result)
        
    except Exception as e:
        return f"搜索失败: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
