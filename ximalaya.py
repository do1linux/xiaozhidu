from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse
import tempfile
from playsound import playsound
import time

# 初始化MCP服务器
mcp = FastMCP("AudiobookService")
logger = logging.getLogger(__name__)

# 线程锁确保音频播放安全
_LOCK = threading.Lock()

# API配置
_API_BASE_URL = 'https://www.hhlqilongzhu.cn/api/ximalaya/ximalaya.php'

def download_audio(url: str, filename: str) -> str:
    """下载音频文件到临时目录"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.ximalaya.com/'
        }
        
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # 创建临时文件
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"{filename}_{int(time.time())}.mp3")
        
        # 下载文件
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"音频文件已下载到: {file_path}")
        return file_path
        
    except Exception as e:
        logger.error(f"下载音频失败: {str(e)}")
        raise

@mcp.tool()
def search_audiobooks(keyword: str) -> dict:
    """
    搜索听书内容
    
    Args:
        keyword: 搜索关键词，如"三体"、"西游记"等
        
    Returns:
        dict: 包含搜索结果的状态和信息
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        
        if not data or ('status' in data and data.get('status') == 0):
            return {
                "success": False,
                "error": "未找到相关听书内容"
            }
        
        # 格式化搜索结果
        results = []
        if isinstance(data, list):
            for item in data[:5]:  # 只返回前5个结果
                results.append({
                    "title": item.get('title', '未知标题'),
                    "playUrl": item.get('playUrl'),
                    "duration": item.get('duration'),
                    "cover": item.get('cover')
                })
        elif isinstance(data, dict):
            results.append({
                "title": data.get('title', '未知标题'),
                "playUrl": data.get('url'),
                "cover": data.get('cover')
            })
        
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "message": f"找到{len(results)}个听书内容"
        }
        
    except Exception as e:
        logger.error(f"搜索听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }

@mcp.tool()
def play_audiobook(keyword: str) -> dict:
    """
    搜索并播放听书内容
    
    Args:
        keyword: 搜索关键词，如"三体"、"西游记"等
        
    Returns:
        dict: 包含播放结果的状态和信息
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    with _LOCK:  # 线程安全锁定
        temp_file_path = None
        try:
            logger.info(f"搜索并播放听书内容: {keyword}")
            
            # 搜索听书内容
            search_result = search_audiobooks(keyword)
            if not search_result.get("success"):
                return search_result
            
            results = search_result.get("results", [])
            if not results:
                return {
                    "success": False,
                    "error": "未找到可播放的听书内容"
                }
            
            # 使用第一个结果
            first_result = results[0]
            play_url = first_result.get('playUrl')
            title = first_result.get('title', keyword)
            
            if not play_url:
                return {
                    "success": False,
                    "error": "未找到可播放的音频链接"
                }
            
            # 下载音频文件
            logger.info(f"开始下载音频: {play_url}")
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            temp_file_path = download_audio(play_url, f"audiobook_{safe_title}")
            
            # 播放音频
            logger.info("开始播放音频")
            playsound(temp_file_path)
            
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info("临时文件已清理")
            
            return {
                "success": True,
                "message": f"听书内容播放完成: {title}",
                "title": title,
                "duration": "音频播放完毕"
            }
            
        except Exception as e:
            # 确保在异常时清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            
            logger.error(f"播放听书失败: {str(e)}")
            return {
                "success": False,
                "error": f"播放失败: {str(e)}"
            }

@mcp.tool()
def download_audiobook(keyword: str) -> dict:
    """
    搜索并下载听书内容
    
    Args:
        keyword: 搜索关键词，如"三体"、"西游记"等
        
    Returns:
        dict: 包含下载结果的状态和信息
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    temp_file_path = None
    try:
        logger.info(f"搜索并下载听书内容: {keyword}")
        
        # 搜索听书内容
        search_result = search_audiobooks(keyword)
        if not search_result.get("success"):
            return search_result
        
        results = search_result.get("results", [])
        if not results:
            return {
                "success": False,
                "error": "未找到可下载的听书内容"
            }
        
        # 使用第一个结果
        first_result = results[0]
        play_url = first_result.get('playUrl')
        title = first_result.get('title', keyword)
        
        if not play_url:
            return {
                "success": False,
                "error": "未找到可下载的音频链接"
            }
        
        # 下载音频文件
        logger.info(f"开始下载音频: {play_url}")
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        temp_file_path = download_audio(play_url, safe_title)
        
        return {
            "success": True,
            "message": f"听书内容下载完成: {title}",
            "file_path": temp_file_path,
            "file_size": os.path.getsize(temp_file_path),
            "title": title
        }
        
    except Exception as e:
        # 确保在异常时清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass
        
        logger.error(f"下载听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"下载失败: {str(e)}"
        }

# 启动服务器
if __name__ == "__main__":
    mcp.run(transport="stdio")
