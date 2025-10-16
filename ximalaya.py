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
def play_audiobook(keyword: str) -> dict:
    """
    直接播放听书内容（简化版）
    Args:
        keyword: 搜索关键词
    Returns:
        dict: 尝试直接播放第一个匹配结果
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    try:
        # 由于API文档不完整，这里提供一个简化的直接播放功能
        # 实际使用时需要根据API的具体返回格式调整
        
        logger.info(f"尝试直接播放听书内容: {keyword}")
        
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
        
        # 简化处理：假设API返回了可直接播放的URL
        play_url = None
        if isinstance(data, dict) and data.get('url'):
            play_url = data.get('url')
        elif isinstance(data, list) and len(data) > 0 and data[0].get('playUrl'):
            play_url = data[0].get('playUrl')
        
        if play_url:
            return {
                "success": True,
                "action": "play_audiobook",
                "search_term": keyword,
                "playable_url": play_url,
                "content_type": "audiobook",
                "playback_info": {
                    "recommended_player": "audio_service.PlayMusicFromUrl",
                    "format": "MP3"
                },
                "user_message": f"已找到听书内容《{keyword}》，正在准备播放..."
            }
        else:
            # 如果没有直接播放URL，返回搜索结果
            return search_audiobooks(keyword)
        
    except Exception as e:
        logger.error(f"播放听书内容失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "search_term": keyword
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
