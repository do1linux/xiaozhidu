from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse
import time
import json

# 初始化MCP
mcp = FastMCP("MusicService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

_API_BASE_URL = 'https://api.yaohud.cn/api/music/wy'

def create_hardware_play_command(audio_url, metadata):
    """创建针对小智AI硬件的播放指令"""
    return {
        "action": "hardware_music_play",
        "command_type": "direct_audio_stream",
        "stream_url": audio_url,
        "audio_format": "mp3",
        "stream_protocol": "http",
        "metadata": {
            "title": metadata.get('title', '未知'),
            "artist": metadata.get('artist', '未知'),
            "album": metadata.get('album', '未知'),
            "duration": metadata.get('duration', 0)
        },
        "hardware_config": {
            "output": "speaker",
            "volume": 80,
            "buffer_size": 8192,
            "codec": "mp3"
        },
        "playback_instruction": "立即开始硬件音频播放",
        "timestamp": int(time.time())
    }

def test_audio_stream(url: str) -> dict:
    """测试音频流是否可访问"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Range': 'bytes=0-8191'
        }
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        
        if response.status_code in [200, 206]:
            content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length', '未知')
            
            return {
                "accessible": True,
                "content_type": content_type,
                "content_length": content_length,
                "status_code": response.status_code
            }
        else:
            return {
                "accessible": False,
                "status_code": response.status_code,
                "reason": response.reason
            }
    except Exception as e:
        return {
            "accessible": False,
            "error": str(e)
        }

@mcp.tool()
def play_song(song_name: str) -> dict:
    """
    播放歌曲 - 针对小智AI硬件优化
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含播放指令和歌曲信息
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {
            "success": False,
            "error": "API密钥未配置，请设置MUSIC_API_KEY环境变量",
            "suggestion": "在环境变量中设置MUSIC_API_KEY=your_api_key"
        }
    
    if not song_name or not song_name.strip():
        return {
            "success": False,
            "error": "歌曲名不能为空",
            "suggestion": "请输入要播放的歌曲名称"
        }
    
    try:
        logger.info(f"搜索歌曲: {song_name}")
        
        # URL编码歌曲名称
        encoded_song_name = urllib.parse.quote(song_name.strip())
        
        # 构建API请求URL
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n=1"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        # 发送请求
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        logger.info(f"API响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 检查API响应
        if data.get('code') != 200:
            error_msg = data.get('msg', '未知错误')
            return {
                "success": False,
                "error": f"音乐API返回错误: {error_msg}",
                "api_response": data
            }
        
        music_data = data.get('data', {})
        music_url = music_data.get('musicurl')
        
        if not music_url:
            return {
                "success": False,
                "error": "未找到可播放的歌曲URL",
                "api_response": data,
                "suggestion": "请尝试搜索其他歌曲名称"
            }
        
        # 测试音频流可访问性
        stream_test = test_audio_stream(music_url)
        logger.info(f"音频流测试结果: {stream_test}")
        
        if not stream_test['accessible']:
            return {
                "success": False,
                "error": "音频流无法访问",
                "stream_test": stream_test,
                "suggestion": "音频链接可能已过期或需要特殊访问权限"
            }
        
        # 创建硬件播放指令
        metadata = {
            'title': music_data.get('name', '未知'),
            'artist': music_data.get('songname', '未知'),
            'album': music_data.get('album', '未知')
        }
        
        hardware_command = create_hardware_play_command(music_url, metadata)
        
        # 构建完整响应
        response = {
            "success": True,
            "action": "music_play",
            "command": hardware_command,
            "instruction": "立即使用硬件音频输出设备播放此音频流",
            "user_message": f"正在播放: {metadata['title']} - {metadata['artist']}",
            "debug_info": {
                "stream_accessible": True,
                "content_type": stream_test.get('content_type'),
                "tested_at": time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        logger.info(f"成功准备播放: {metadata['title']} - {metadata['artist']}")
        return response
        
    except requests.exceptions.Timeout:
        logger.error("API请求超时")
        return {
            "success": False,
            "error": "音乐API请求超时",
            "suggestion": "请检查网络连接或稍后重试"
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求错误: {str(e)}")
        return {
            "success": False,
            "error": f"网络请求失败: {str(e)}",
            "suggestion": "请检查网络连接"
        }
    except Exception as e:
        logger.error(f"播放歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}",
            "suggestion": "请稍后重试或联系技术支持"
        }

@mcp.tool()
def search_songs(keyword: str, limit: int = 5) -> dict:
    """
    搜索歌曲
    Args:
        keyword: 搜索关键词
        limit: 返回数量
    Returns:
        dict: 歌曲列表
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {
            "success": False, 
            "error": "API密钥未配置"
        }
    
    if not keyword or not keyword.strip():
        return {
            "success": False,
            "error": "搜索关键词不能为空"
        }
    
    try:
        encoded_keyword = urllib.parse.quote(keyword.strip())
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_keyword}&n={limit}"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
            'Accept': 'application/json'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        songs_data = data.get('data', {})
        songs_list = songs_data.get('songs', [])
        
        if not songs_list:
            return {
                "success": True,
                "action": "search_results",
                "message": "未找到相关歌曲",
                "songs": [],
                "suggestion": "请尝试其他搜索关键词"
            }
        
        # 格式化歌曲列表
        songs = []
        for song in songs_list[:limit]:
            song_info = {
                "id": song.get('n'),
                "title": song.get('name', '未知'),
                "artist": song.get('singer', '未知'),
                "album": song.get('album', '未知'),
                "playable": True,
                "action_required": "使用 play_song 工具播放此歌曲"
            }
            songs.append(song_info)
        
        return {
            "success": True,
            "action": "search_results",
            "songs": songs,
            "count": len(songs),
            "instruction": "选择歌曲后使用 play_song 工具进行播放"
        }
        
    except Exception as e:
        logger.error(f"搜索歌曲失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }

@mcp.tool()
def test_audio_output() -> dict:
    """
    测试音频硬件输出
    Returns:
        dict: 测试播放指令
    """
    test_url = "https://www.soundjay.com/button/beep-07.wav"
    
    # 测试音频流
    stream_test = test_audio_stream(test_url)
    
    hardware_command = {
        "action": "audio_test",
        "command_type": "test_audio_stream",
        "stream_url": test_url,
        "audio_format": "wav",
        "hardware_config": {
            "output": "speaker",
            "volume": 50,
            "test_mode": True
        },
        "playback_instruction": "播放测试音频，确认硬件音频输出正常"
    }
    
    return {
        "success": True,
        "action": "audio_test",
        "command": hardware_command,
        "instruction": "播放测试音频以验证硬件音频输出",
        "user_message": "正在播放测试音频，请确认是否有声音输出",
        "debug_info": {
            "stream_test": stream_test,
            "purpose": "硬件音频输出验证"
        }
    }

@mcp.tool()
def get_music_status() -> dict:
    """
    获取音乐服务状态
    Returns:
        dict: 服务状态信息
    """
    api_key_configured = bool(os.environ.get('MUSIC_API_KEY'))
    
    return {
        "success": True,
        "service": "MusicService",
        "version": "2.0",
        "status": "running",
        "configuration": {
            "api_configured": api_key_configured,
            "base_url": _API_BASE_URL,
            "supported_actions": ["play_song", "search_songs", "test_audio_output"]
        },
        "hardware_support": {
            "audio_output": True,
            "stream_playback": True,
            "formats": ["mp3", "wav"],
            "instruction_type": "hardware_direct"
        },
        "troubleshooting": [
            "1. 确认MUSIC_API_KEY环境变量已设置",
            "2. 使用 test_audio_output 测试硬件",
            "3. 检查网络连接",
            "4. 验证音频流URL可访问性"
        ]
    }

@mcp.tool()
def diagnose_playback_issue() -> dict:
    """
    诊断播放问题
    Returns:
        dict: 诊断结果和建议
    """
    # 检查API密钥
    api_key = os.environ.get('MUSIC_API_KEY')
    
    # 测试网络连接
    network_ok = False
    try:
        response = requests.get("https://api.yaohud.cn", timeout=5)
        network_ok = response.status_code == 200
    except:
        network_ok = False
    
    return {
        "success": True,
        "diagnosis": {
            "api_key_configured": bool(api_key),
            "network_connectivity": network_ok,
            "service_status": "active",
            "common_issues": [
                "硬件音频输出未启用",
                "音量设置为0",
                "音频驱动问题",
                "网络流媒体阻塞"
            ]
        },
        "recommendations": [
            "运行 test_audio_output 检查硬件",
            "确认设备音量设置",
            "检查网络连接",
            "尝试播放其他歌曲"
        ],
        "immediate_actions": [
            "使用 test_audio_output 工具",
            "检查环境变量配置",
            "验证API密钥有效性"
        ]
    }

if __name__ == "__main__":
    # 启动MCP服务
    mcp.run(transport="stdio")
