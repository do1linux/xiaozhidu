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
def play_music(song_name: str) -> dict:
    """
    播放音乐 - 默认返回第一首可直接播放的歌曲URL
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含可直接播放的音频URL和完整歌曲信息
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
        logger.info(f"搜索并播放歌曲: {song_name}")
        
        # URL编码歌曲名称
        encoded_song_name = urllib.parse.quote(song_name.strip())
        
        # 构建完整URL - 默认获取第一首歌曲
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n=1"
        
        # 设置请求头
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        # 发送GET请求
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
        
        # 检查是否有可直接播放的musicurl
        if not music_data.get('musicurl'):
            return {
                "success": False,
                "error": "未找到可播放的歌曲链接",
                "search_term": song_name,
                "suggestion": "请尝试搜索其他歌曲或检查歌曲名称"
            }
        
        # 成功获取到播放URL，构建完整响应
        result = {
            "success": True,
            "action": "play_music",
            "song_name": song_name,
            "playable_url": music_data['musicurl'],  # 可直接播放的音频URL
            "song_details": {
                "title": music_data.get('name', '未知'),
                "artist": music_data.get('songname', '未知'),
                "album": music_data.get('album', '未知'),
                "cover_image": music_data.get('picture', ''),
                "lyrics_available": bool(music_data.get('lrc')),
                "lyrics_url": music_data.get('lrc', '')
            },
            "playback_info": {
                "format": "MP3",  # 根据URL推断
                "stream_type": "direct_url",
                "recommended_player": "audio_service.PlayMusicFromUrl"
            },
            "user_message": f"已找到歌曲《{music_data.get('name', '未知')}》- {music_data.get('songname', '未知')}，正在准备播放..."
        }
        
        logger.info(f"成功获取歌曲: {result['song_details']['title']} - {result['song_details']['artist']}")
        return result
        
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API请求超时，请稍后重试",
            "search_term": song_name
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"网络请求失败: {str(e)}",
            "search_term": song_name
        }
    except Exception as e:
        logger.error(f"播放音乐失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": song_name
        }

@mcp.tool()
def search_and_play(song_name: str, song_number: int = 1) -> dict:
    """
    搜索并播放指定序号的歌曲
    Args:
        song_name: 歌曲名称
        song_number: 歌曲序号（从1开始），默认第一首
    Returns:
        dict: 包含可直接播放的音频URL和完整歌曲信息
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
    
    if song_number < 1:
        return {
            "success": False,
            "error": "歌曲序号必须大于0"
        }
    
    try:
        # 调用音乐API获取指定序号的歌曲
        logger.info(f"搜索并播放歌曲: {song_name}，序号: {song_number}")
        
        # URL编码歌曲名称
        encoded_song_name = urllib.parse.quote(song_name.strip())
        
        # 构建完整URL - 获取指定序号的歌曲
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n={song_number}"
        
        # 设置请求头
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        # 发送GET请求
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 检查API返回状态
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}",
                "search_term": song_name,
                "song_number": song_number
            }
        
        music_data = data.get('data', {})
        
        # 检查是否有可直接播放的musicurl
        if not music_data.get('musicurl'):
            # 如果没有直接播放URL，检查是否有歌曲列表
            songs_list = music_data.get('songs', [])
            if songs_list and song_number <= len(songs_list):
                # 有歌曲列表但无直接播放URL，建议用户使用play_music播放第一首
                selected_song = songs_list[song_number-1]
                return {
                    "success": False,
                    "error": "无法直接获取该歌曲的播放链接",
                    "search_term": song_name,
                    "song_number": song_number,
                    "song_info": {
                        "title": selected_song.get('name'),
                        "artist": selected_song.get('singer'),
                        "album": selected_song.get('album')
                    },
                    "suggestion": "请尝试使用 play_music 工具播放第一首匹配的歌曲，或调整搜索词"
                }
            else:
                return {
                    "success": False,
                    "error": "未找到指定序号的歌曲",
                    "search_term": song_name,
                    "song_number": song_number
                }
        
        # 成功获取到播放URL
        result = {
            "success": True,
            "action": "play_music",
            "song_name": song_name,
            "song_number": song_number,
            "playable_url": music_data['musicurl'],  # 可直接播放的音频URL
            "song_details": {
                "title": music_data.get('name', '未知'),
                "artist": music_data.get('songname', '未知'),
                "album": music_data.get('album', '未知'),
                "cover_image": music_data.get('picture', ''),
                "lyrics_available": bool(music_data.get('lrc')),
                "lyrics_url": music_data.get('lrc', '')
            },
            "playback_info": {
                "format": "MP3",
                "stream_type": "direct_url",
                "recommended_player": "audio_service.PlayMusicFromUrl"
            },
            "user_message": f"已找到第{song_number}首歌曲《{music_data.get('name', '未知')}》- {music_data.get('songname', '未知')}，正在准备播放..."
        }
        
        logger.info(f"成功获取歌曲: {result['song_details']['title']} - {result['song_details']['artist']}")
        return result
        
    except Exception as e:
        logger.error(f"搜索并播放失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": song_name,
            "song_number": song_number
        }

@mcp.tool()
def search_music(song_name: str, limit: int = 5) -> dict:
    """
    搜索多首歌曲（不播放）
    Args:
        song_name: 歌曲名称
        limit: 返回结果数量，默认5首
    Returns:
        dict: 包含多首歌曲信息，用于选择
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {"success": False, "error": "API密钥未配置"}
    
    try:
        # URL编码歌曲名称
        encoded_song_name = urllib.parse.quote(song_name.strip())
        
        # 构建完整URL
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n={limit}"
        
        # 设置请求头
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        # 发送GET请求
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
        
        # 处理API响应数据
        songs_data = data.get('data', {})
        songs_list = songs_data.get('songs', [])
        
        if not songs_list:
            return {
                "success": True,
                "action": "search_results",
                "message": "未找到相关歌曲",
                "search_term": song_name,
                "songs": []
            }
        
        # 格式化歌曲列表
        formatted_songs = []
        for song in songs_list[:limit]:
            formatted_songs.append({
                "number": song.get('n'),
                "title": song.get('name', '未知'),
                "artist": song.get('singer', '未知'),
                "album": song.get('album', '未知')
            })
        
        return {
            "success": True,
            "action": "search_results",
            "search_term": song_name,
            "songs": formatted_songs,
            "count": len(formatted_songs),
            "instruction": f"找到 {len(formatted_songs)} 首相关歌曲，使用 'search_and_play' 工具并指定序号来播放特定歌曲，或使用 'play_music' 直接播放第一首"
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
