from mcp.server.fastmcp import FastMCP
import requests
import os
import logging

# 初始化MCP和日志
mcp = FastMCP("MusicService")
logger = logging.getLogger(__name__)

_API_URL = 'https://api.yaohud.cn/api/music/wy'
_API_KEY = os.environ.get('MUSIC_API_KEY')

def get_music_url(song_name: str) -> dict:
    """获取音乐URL的基础函数"""
    if not song_name.strip():
        return {"success": False, "error": "歌曲名不能为空"}

    try:
        logger.info(f"搜索歌曲: {song_name}")
        params = {'key': _API_KEY, 'msg': song_name.strip(), 'n': '1'}
        resp = requests.post(_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        music_url = data['data']['musicurl']
        
        return {
            "success": True,
            "audio_url": music_url,
            "song_name": song_name
        }
        
    except Exception as e:
        logger.error(f"搜索失败: {str(e)}")
        return {"success": False, "error": f"搜索失败: {str(e)}"}

@mcp.tool()
def play_music(song_name: str) -> dict:
    """
    提供音乐播放解决方案
    
    Args:
        song_name: 歌曲名，如"周杰伦 青花瓷"
        
    Returns:
        dict: 包含多种播放选项
    """
    music_data = get_music_url(song_name)
    if not music_data["success"]:
        return music_data
    
    audio_url = music_data["audio_url"]
    
    return {
        "success": True,
        "song_name": song_name,
        "audio_url": audio_url,
        "playback_methods": [
            "1. 直接访问音频链接",
            "2. 复制URL到其他播放器", 
            "3. 在支持的环境中使用HTML播放器"
        ],
        "quick_access": f"🎵 播放链接: {audio_url}",
        "message": f"已为您找到《{song_name}》，请选择合适的播放方式"
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
