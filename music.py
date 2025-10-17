from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse
import base64

# 初始化MCP
mcp = FastMCP("MusicService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://api.yaohud.cn/api/music/migu'

@mcp.tool()
def play_song(song_name: str) -> dict:
    """
    播放歌曲 - 使用咪咕音乐API
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含音频URL和歌曲信息
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
        # 调用咪咕音乐API获取歌曲信息
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
        
        # 检查API返回状态
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        music_data = data.get('data', {})
        
        # 检查是否有音乐URL
        if not music_data.get('music_url'):
            return {
                "success": False,
                "error": "未找到可播放的歌曲",
                "search_term": song_name
            }
        
        # 返回歌曲信息和播放URL
        result = {
            "success": True,
            "action": "play_music",
            "song_name": song_name,
            "play_url": music_data['music_url'],
            "song_info": {
                "title": music_data.get('title', '未知'),
                "artist": music_data.get('singer', '未知'),
                "cover": music_data.get('cover', ''),
                "lrc_url": music_data.get('lrc_url', ''),
                "detail_link": music_data.get('detail_link', '')
            },
            "audio_info": {
                "format": "mp3",
                "source": "migu",
                "quality": "high"
            },
            "instruction": "小智AI可以使用此URL直接播放音频",
            "user_message": f"正在播放: {music_data.get('title', '未知')} - {music_data.get('singer', '未知')}"
        }
        
        logger.info(f"成功获取歌曲: {result['song_info']['title']} - {result['song_info']['artist']}")
        return result
        
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API请求超时",
            "search_term": song_name
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"网络请求失败: {str(e)}",
            "search_term": song_name
        }
    except Exception as e:
        logger.error(f"播放歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": song_name
        }

@mcp.tool()
def search_songs(keyword: str, limit: int = 5) -> dict:
    """
    搜索多首歌曲
    Args:
        keyword: 搜索关键词
        limit: 返回结果数量，默认5首
    Returns:
        dict: 包含多首歌曲信息
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {"success": False, "error": "API密钥未配置"}
    
    try:
        # URL编码关键词
        encoded_keyword = urllib.parse.quote(keyword.strip())
        
        # 构建完整URL
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_keyword}&n={limit}"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 检查API返回状态
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}",
                "search_term": keyword
            }
        
        # 处理API响应数据
        music_data = data.get('data', {})
        
        # 由于咪咕API单曲搜索返回的是单个歌曲对象，不是列表
        # 这里我们假设搜索多首时API会返回列表，如果没有则返回单首
        if isinstance(music_data, dict) and music_data.get('title'):
            # 单首歌曲结果
            songs = [{
                "title": music_data.get('title', '未知'),
                "artist": music_data.get('singer', '未知'),
                "cover": music_data.get('cover', ''),
                "play_url": music_data.get('music_url', ''),
                "has_audio": bool(music_data.get('music_url'))
            }]
        else:
            # 多首歌曲结果（假设为列表）
            songs = []
            # 这里需要根据实际API返回格式调整
        
        if not songs:
            return {
                "success": True,
                "action": "search_results",
                "message": "未找到相关歌曲",
                "search_term": keyword,
                "songs": []
            }
        
        return {
            "success": True,
            "action": "search_results",
            "search_term": keyword,
            "songs": songs,
            "count": len(songs),
            "instruction": f"找到 {len(songs)} 首相关歌曲，使用 play_song 工具播放"
        }
        
    except Exception as e:
        logger.error(f"搜索歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}",
            "search_term": keyword
        }

@mcp.tool()
def play_music(song_name: str) -> dict:
    """
    播放音乐 (play_song的别名，保持兼容性)
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含音频URL和歌曲信息
    """
    return play_song(song_name)

@mcp.tool()
def get_song_info(song_name: str) -> dict:
    """
    获取歌曲详细信息（不播放）
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含歌曲详细信息
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {"success": False, "error": "API密钥未配置"}
    
    try:
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
        
        # 检查API返回状态
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}",
                "search_term": song_name
            }
        
        music_data = data.get('data', {})
        
        return {
            "success": True,
            "action": "song_info",
            "search_term": song_name,
            "song_details": {
                "title": music_data.get('title', '未知'),
                "artist": music_data.get('singer', '未知'),
                "cover": music_data.get('cover', ''),
                "lrc_url": music_data.get('lrc_url', ''),
                "music_url": music_data.get('music_url', ''),
                "detail_link": music_data.get('detail_link', ''),
                "content_id": music_data.get('contentId', ''),
                "copyright_id": music_data.get('copyrightId', '')
            },
            "available": bool(music_data.get('music_url'))
        }
        
    except Exception as e:
        logger.error(f"获取歌曲信息失败: {str(e)}")
        return {
            "success": False,
            "error": f"获取信息失败: {str(e)}",
            "search_term": song_name
        }

@mcp.tool()
def get_service_status() -> dict:
    """
    获取音乐服务状态
    Returns:
        dict: 服务状态信息
    """
    return {
        "success": True,
        "service": "MusicService",
        "version": "2.0",
        "api_source": "咪咕音乐",
        "supported_actions": ["play_song", "search_songs", "play_music", "get_song_info"],
        "status": "running"
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
