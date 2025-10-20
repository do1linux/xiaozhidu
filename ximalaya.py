from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse
import tempfile
from playsound import playsound
import time

# 初始化MCP
mcp = FastMCP("AudiobookService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://www.hhlqilongzhu.cn/api/ximalaya/ximalaya.php'

def download_audio(url: str, filename: str) -> str:
    """
    下载音频文件到临时目录
    Args:
        url: 音频URL
        filename: 保存的文件名
    Returns:
        str: 下载的文件路径
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
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
def play_audiobook(keyword: str) -> dict:
    """
    搜索并播放听书内容
    Args:
        keyword: 搜索关键词
    Returns:
        dict: 播放结果信息
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    with _LOCK:  # 线程安全锁定
        temp_file_path = None
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
            
            # 下载音频文件
            logger.info(f"开始下载音频: {play_url}")
            temp_file_path = download_audio(play_url, f"audiobook_{encoded_keyword}")
            
            # 播放音频
            logger.info("开始播放音频")
            playsound(temp_file_path)
            
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info("临时文件已清理")
            
            return {
                "success": True,
                "message": f"听书内容播放完成: {keyword}",
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
def search_and_download_audiobook(keyword: str, download_only: bool = False) -> dict:
    """
    搜索听书内容并下载音频文件
    Args:
        keyword: 搜索关键词
        download_only: 仅下载不播放，默认为False
    Returns:
        dict: 下载结果信息
    """
    if not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    temp_file_path = None
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
        title = "未知标题"
        
        if isinstance(data, dict):
            play_url = data.get('url')
            title = data.get('title', keyword)
        elif isinstance(data, list) and len(data) > 0:
            play_url = data[0].get('playUrl')
            title = data[0].get('title', keyword)
        
        if not play_url:
            return {
                "success": False,
                "error": "未找到可下载的音频链接"
            }
        
        # 下载音频文件
        logger.info(f"开始下载音频: {play_url}")
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        temp_file_path = download_audio(play_url, safe_title)
        
        result = {
            "success": True,
            "message": f"听书内容下载完成: {title}",
            "file_path": temp_file_path,
            "file_size": os.path.getsize(temp_file_path) if temp_file_path and os.path.exists(temp_file_path) else 0,
            "title": title
        }
        
        # 如果不需要播放，直接返回下载结果
        if download_only:
            return result
        
        # 播放下载的音频
        logger.info("开始播放音频")
        playsound(temp_file_path)
        
        # 清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            result["file_path"] = "已清理"
            result["message"] = f"听书内容播放完成: {title}"
        
        return result
        
    except Exception as e:
        # 确保在异常时清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass
        
        logger.error(f"处理听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理失败: {str(e)}"
        }

@mcp.tool()
def search_audiobooks(keyword: str) -> dict:
    """
    搜索听书内容（仅搜索，不下载播放）
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
            "action": "search_results",
            "results": results,
            "count": len(results),
            "instruction": f"找到{len(results)}个听书内容，使用 play_audiobook 工具播放"
        }
        
    except Exception as e:
        logger.error(f"搜索听书失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }

if __name__ == "__main__":
    mcp.run(transport="stdio")
