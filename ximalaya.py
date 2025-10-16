from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse

# 初始化MCP
mcp = FastMCP("XimalayaTingshu")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://www.hhlqilongzhu.cn/api/ximalaya/ximalaya.php'

@mcp.tool()
def search_audiobooks(keyword: str) -> dict:
    """
    搜索喜马拉雅听书内容
    Args:
        keyword: 搜索关键词，如书名、作者名等
    Returns:
        dict: 包含搜索结果的听书内容列表
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    try:
        # 调用喜马拉雅API搜索听书内容
        logger.info(f"搜索听书内容: {keyword}")
        
        # URL编码关键词
        encoded_keyword = urllib.parse.quote(keyword.strip())
        
        # 构建完整URL
        url = f"{_API_BASE_URL}?name={encoded_keyword}"
        
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        # 发送GET请求
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 检查API返回状态
        if not data or 'status' in data and data.get('status') == 0:
            return {
                "success": False,
                "error": "未找到相关听书内容",
                "search_term": keyword,
                "suggestion": "请尝试其他关键词或检查网络连接"
            }
        
        # 根据API实际返回格式处理数据
        # 由于API文档未提供完整返回格式，这里需要根据实际情况调整
        if isinstance(data, list):
            # 如果返回的是列表
            audiobooks = []
            for item in data[:10]:  # 限制返回数量
                audiobooks.append({
                    "title": item.get('title', '未知'),
                    "author": item.get('author', '未知'),
                    "album_id": item.get('albumId'),
                    "cover_url": item.get('cover', ''),
                    "description": item.get('desc', '')[:100] + '...' if item.get('desc') else '',
                    "episode_count": item.get('episodeCount', 0)
                })
            
            return {
                "success": True,
                "action": "search_results",
                "search_term": keyword,
                "audiobooks": audiobooks,
                "count": len(audiobooks),
                "instruction": "找到相关听书内容，请使用 get_album_episodes 获取具体集数列表"
            }
        elif isinstance(data, dict):
            # 如果返回的是字典，根据实际字段调整
            # 这里需要根据API实际返回格式进行调整
            return {
                "success": True,
                "action": "search_results",
                "search_term": keyword,
                "raw_data": data,  # 返回原始数据用于调试
                "instruction": "API返回数据格式需要进一步解析，请查看raw_data字段"
            }
        else:
            return {
                "success": True,
                "action": "search_results", 
                "search_term": keyword,
                "raw_data": data,
                "message": "收到API响应，但格式未知"
            }
        
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API请求超时，请稍后重试",
            "search_term": keyword
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"网络请求失败: {str(e)}",
            "search_term": keyword
        }
    except Exception as e:
        logger.error(f"搜索听书内容失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": keyword
        }

@mcp.tool()
def get_album_episodes(album_id: str) -> dict:
    """
    获取栏目的集数列表
    Args:
        album_id: 栏目ID
    Returns:
        dict: 包含栏目下所有集数的列表
    """
    if not album_id.strip():
        return {
            "success": False,
            "error": "栏目ID不能为空"
        }
    
    try:
        logger.info(f"获取栏目集数列表: {album_id}")
        
        # 构建URL
        url = f"{_API_BASE_URL}?albumId={album_id.strip()}"
        
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        # 发送GET请求
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 处理返回数据
        if not data or 'status' in data and data.get('status') == 0:
            return {
                "success": False,
                "error": "未找到该栏目的集数列表",
                "album_id": album_id
            }
        
        # 根据API实际返回格式处理
        if isinstance(data, list):
            episodes = []
            for episode in data[:50]:  # 限制返回数量
                episodes.append({
                    "track_id": episode.get('trackId'),
                    "title": episode.get('title', '未知'),
                    "duration": episode.get('duration', 0),
                    "play_count": episode.get('playCount', 0),
                    "order_num": episode.get('orderNum', 0)
                })
            
            # 按集数排序
            episodes.sort(key=lambda x: x.get('order_num', 0))
            
            return {
                "success": True,
                "action": "episode_list",
                "album_id": album_id,
                "episodes": episodes,
                "count": len(episodes),
                "instruction": "使用 play_episode 工具并指定 track_id 来播放特定集数"
            }
        else:
            return {
                "success": True,
                "action": "episode_list",
                "album_id": album_id,
                "raw_data": data,
                "instruction": "使用 play_episode 工具并指定 track_id 来播放音频"
            }
        
    except Exception as e:
        logger.error(f"获取栏目集数失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "album_id": album_id
        }

@mcp.tool()
def play_episode(track_id: str) -> dict:
    """
    播放特定音频
    Args:
        track_id: 音频ID
    Returns:
        dict: 包含音频播放URL和详细信息
    """
    if not track_id.strip():
        return {
            "success": False,
            "error": "音频ID不能为空"
        }
    
    try:
        logger.info(f"播放音频: {track_id}")
        
        # 构建URL
        url = f"{_API_BASE_URL}?trackId={track_id.strip()}"
        
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        # 发送GET请求
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 处理返回数据
        if not data or 'status' in data and data.get('status') == 0:
            return {
                "success": False,
                "error": "未找到该音频的播放信息",
                "track_id": track_id
            }
        
        # 提取音频播放URL
        # 根据API实际返回格式调整
        play_url = None
        if isinstance(data, dict):
            # 尝试常见的音频URL字段
            for key in ['url', 'playUrl', 'audioUrl', 'src', 'play_url']:
                if key in data and data[key]:
                    play_url = data[key]
                    break
        
        if not play_url:
            # 如果没有找到明确的播放URL，返回原始数据
            return {
                "success": True,
                "action": "audio_info",
                "track_id": track_id,
                "raw_data": data,
                "instruction": "已获取音频信息，但未找到明确的播放URL，请查看raw_data字段"
            }
        
        # 成功获取播放URL
        return {
            "success": True,
            "action": "play_audio",
            "track_id": track_id,
            "playable_url": play_url,
            "audio_info": {
                "title": data.get('title', '未知'),
                "duration": data.get('duration', 0),
                "format": "MP3",  # 假设格式
                "stream_type": "direct_url"
            },
            "playback_info": {
                "recommended_player": "audio_service.PlayMusicFromUrl",
                "content_type": "audiobook"
            },
            "user_message": f"已找到音频《{data.get('title', '未知')}》，正在准备播放..."
        }
        
    except Exception as e:
        logger.error(f"播放音频失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "track_id": track_id
        }

@mcp.tool()
def search_and_play_audiobook(keyword: str) -> dict:
    """
    搜索并直接播放听书内容（简化流程）
    Args:
        keyword: 搜索关键词
    Returns:
        dict: 尝试直接播放第一个匹配结果
    """
    # 先搜索
    search_result = search_audiobooks(keyword)
    
    if not search_result.get('success'):
        return search_result
    
    # 如果有搜索结果，尝试获取第一个栏目的第一集
    audiobooks = search_result.get('audiobooks', [])
    if not audiobooks:
        return {
            "success": False,
            "error": "搜索到内容但无法解析具体栏目",
            "search_term": keyword,
            "raw_data": search_result
        }
    
    first_audiobook = audiobooks[0]
    album_id = first_audiobook.get('album_id')
    
    if not album_id:
        return {
            "success": False,
            "error": "第一个结果没有有效的栏目ID",
            "search_term": keyword,
            "audiobook_info": first_audiobook
        }
    
    # 获取集数列表
    episodes_result = get_album_episodes(album_id)
    
    if not episodes_result.get('success'):
        return episodes_result
    
    episodes = episodes_result.get('episodes', [])
    if not episodes:
        return {
            "success": False,
            "error": "该栏目没有可播放的集数",
            "album_id": album_id,
            "audiobook_title": first_audiobook.get('title')
        }
    
    # 播放第一集
    first_episode = episodes[0]
    track_id = first_episode.get('track_id')
    
    if not track_id:
        return {
            "success": False,
            "error": "第一集没有有效的音频ID",
            "album_id": album_id,
            "episode_info": first_episode
        }
    
    return play_episode(track_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")
