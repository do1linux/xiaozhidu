from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse

# 初始化MCP
mcp = FastMCP("AudiobookService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://www.hhlqilongzhu.cn/api/ximalaya/ximalaya.php'

@mcp.tool()
def play_audiobook(keyword: str) -> dict:
    """
    播放听书内容
    Args:
        keyword: 搜索关键词
    Returns:
        dict: 包含播放指令
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    try:
        logger.info(f"搜索听书内容: {keyword}")
        
        encoded_keyword = urllib.parse.quote(keyword.strip())
        url = f"{_API_BASE_URL}?name={encoded_keyword}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        if not data or 'status' in data and data.get('status') == 0:
            return {
                "success": False,
                "error": "未找到相关听书内容"
            }
        
        # 提取播放URL
        play_url = None
        if isinstance(data, dict) and data.get('url'):
            play_url = data.get('url')
        elif isinstance(data, list) and len(data) > 0 and data[0].get('playUrl'):
            play_url = data[0].get('playUrl')
        
        if not play_url:
            return {
                "success": False,
                "error": "未找到可播放的音频链接"
            }
        
        # 返回适合硬件播放的指令
        return {
            "success": True,
            "action": "audiobook_play",
            "command": {
                "type": "audio_stream",
                "url": play_url,
                "format": "mp3",
                "content_type": "audiobook"
            },
            "instruction": "使用硬件音频播放器播放此听书内容",
            "user_message": f"正在播放听书内容: {keyword}"
        }
        
    except Exception as e:
        logger.error(f"播放听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}"
        }

@mcp.tool()
def search_audiobooks(keyword: str) -> dict:
    """
    搜索听书内容
    Args:
        keyword: 搜索关键词
    Returns:
        dict: 听书内容列表
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    try:
        logger.info(f"搜索听书内容: {keyword}")
        
        encoded_keyword = urllib.parse.quote(keyword.strip())
        url = f"{_API_BASE_URL}?name={encoded_keyword}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        if not data or 'status' in data and data.get('status') == 0:
            return {
                "success": False,
                "error": "未找到相关听书内容"
            }
        
        return {
            "success": True,
            "action": "search_results",
            "raw_data": data,
            "instruction": "找到听书内容，使用 play_audiobook 工具播放"
        }
        
    except Exception as e:
        logger.error(f"搜索听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
