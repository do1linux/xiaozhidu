from mcp.server.fastmcp import FastMCP
import requests
import os
import logging

# 初始化MCP
mcp = FastMCP("MusicService")
logger = logging.getLogger(__name__)

_API_URL = 'https://api.yaohud.cn/api/music/wy'

@mcp.tool()
def get_music_url(song_name: str) -> dict:
    """
    获取歌曲的播放URL，供小智AI客户端播放
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含歌曲信息和播放URL
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {
            "success": False,
            "error": "API密钥未配置",
            "solution": "请设置MUSIC_API_KEY环境变量"
        }
    
    if not song_name.strip():
        return {
            "success": False,
            "error": "歌曲名不能为空"
        }
    
    try:
        # 调用音乐API获取歌曲信息
        logger.info(f"搜索歌曲: {song_name}")
        params = {
            'key': api_key, 
            'msg': song_name.strip(), 
            'n': '1'  # 只获取第一首
        }
        
        resp = requests.post(_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        music_data = data.get('data', {})
        
        if not music_data.get('musicurl'):
            return {
                "success": False,
                "error": "未找到该歌曲",
                "search_term": song_name
            }
        
        # 返回歌曲信息和播放URL
        result = {
            "success": True,
            "song_name": song_name,
            "play_url": music_data['musicurl'],
            "song_info": {
                "title": music_data.get('title', '未知'),
                "artist": music_data.get('author', '未知'),
                "album": music_data.get('album', '未知'),
                "duration": music_data.get('duration', '未知')
            },
            "instruction": "小智AI可以使用此URL直接播放音频"
        }
        
        logger.info(f"找到歌曲: {result['song_info']['title']} - {result['song_info']['artist']}")
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
            "error": f"API请求失败: {str(e)}",
            "search_term": song_name
        }
    except Exception as e:
        logger.error(f"获取音乐URL失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": song_name
        }

@mcp.tool()
def search_music(song_name: str, limit: int = 5) -> dict:
    """
    搜索多首歌曲
    Args:
        song_name: 歌曲名称
        limit: 返回结果数量，默认5首
    Returns:
        dict: 包含多首歌曲信息
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {"success": False, "error": "API密钥未配置"}
    
    try:
        params = {
            'key': api_key, 
            'msg': song_name.strip(), 
            'n': str(limit)
        }
        
        resp = requests.post(_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        songs = data.get('data', [])
        
        if not songs:
            return {
                "success": True,
                "message": "未找到相关歌曲",
                "songs": [],
                "search_term": song_name
            }
        
        # 格式化歌曲列表
        formatted_songs = []
        for song in songs[:limit]:
            formatted_songs.append({
                "title": song.get('title', '未知'),
                "artist": song.get('author', '未知'),
                "album": song.get('album', '未知'),
                "play_url": song.get('musicurl', ''),
                "duration": song.get('duration', '未知')
            })
        
        return {
            "success": True,
            "search_term": song_name,
            "songs": formatted_songs,
            "count": len(formatted_songs)
        }
        
    except Exception as e:
        logger.error(f"搜索音乐失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}",
            "search_term": song_name
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
