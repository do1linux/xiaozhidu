from mcp.server.fastmcp import FastMCP
import requests
import os
import logging
import threading
import urllib.parse
import base64

# 初始化MCP
mcp = FastMCP("HardwareMusicService")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()

_API_BASE_URL = 'https://api.yaohud.cn/api/music/wy'

@mcp.tool()
def play_music_direct(song_name: str) -> dict:
    """
    直接硬件播放音乐 - 绕过固件限制
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含音频数据和硬件控制指令
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
        # 获取音乐信息
        logger.info(f"搜索歌曲: {song_name}")
        
        encoded_song_name = urllib.parse.quote(song_name.strip())
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n=1"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        music_data = data.get('data', {})
        music_url = music_data.get('musicurl')
        
        if not music_url:
            return {
                "success": False,
                "error": "未找到可播放的歌曲"
            }
        
        # 下载音频数据
        logger.info(f"下载音频数据: {music_url}")
        audio_response = requests.get(music_url, timeout=30)
        audio_response.raise_for_status()
        
        # 将音频数据编码为base64，便于传输
        audio_base64 = base64.b64encode(audio_response.content).decode('utf-8')
        
        # 返回硬件控制指令
        result = {
            "success": True,
            "action": "hardware_audio_play",
            "hardware_control": {
                "type": "direct_audio",
                "audio_data": audio_base64,
                "data_format": "base64_mp3",
                "sample_rate": 44100,
                "channels": 2,
                "bit_depth": 16
            },
            "song_info": {
                "title": music_data.get('name', '未知'),
                "artist": music_data.get('songname', '未知'),
                "album": music_data.get('album', '未知')
            },
            "instruction": "ESP32-S3请直接解码并播放此音频数据",
            "user_message": f"正在通过硬件直接播放: {music_data.get('name', '未知')}"
        }
        
        logger.info(f"成功获取音频数据: {result['song_info']['title']}")
        return result
        
    except Exception as e:
        logger.error(f"硬件播放失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}"
        }

@mcp.tool()
def play_music_url(song_name: str) -> dict:
    """
    返回音频URL供ESP32-S3直接下载播放
    Args:
        song_name: 歌曲名称
    Returns:
        dict: 包含音频URL和硬件指令
    """
    api_key = os.environ.get('MUSIC_API_KEY')
    if not api_key:
        return {
            "success": False,
            "error": "API密钥未配置"
        }
    
    try:
        # 获取音乐URL
        logger.info(f"搜索歌曲URL: {song_name}")
        
        encoded_song_name = urllib.parse.quote(song_name.strip())
        url = f"{_API_BASE_URL}?key={api_key}&msg={encoded_song_name}&n=1"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 200:
            return {
                "success": False,
                "error": f"API返回错误: {data.get('msg', '未知错误')}"
            }
        
        music_data = data.get('data', {})
        music_url = music_data.get('musicurl')
        
        if not music_url:
            return {
                "success": False,
                "error": "未找到可播放的歌曲"
            }
        
        # 返回URL供ESP32-S3直接下载播放
        result = {
            "success": True,
            "action": "hardware_download_play",
            "audio_url": music_url,
            "hardware_instruction": {
                "method": "direct_download",
                "target": "esp32_s3",
                "protocol": "http"
            },
            "song_info": {
                "title": music_data.get('name', '未知'),
                "artist": music_data.get('songname', '未知'),
                "album": music_data.get('album', '未知')
            },
            "user_message": f"ESP32-S3正在直接下载播放: {music_data.get('name', '未知')}"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"获取音乐URL失败: {str(e)}")
        return {
            "success": False,
            "error": f"处理请求时出错: {str(e)}"
        }

@mcp.tool()
def control_audio_hardware(command: str, value: int = None) -> dict:
    """
    直接控制ESP32-S3音频硬件
    Args:
        command: 控制命令 (play, pause, stop, volume, mute)
        value: 数值 (音量0-100等)
    Returns:
        dict: 控制结果
    """
    commands = {
        "play": "开始播放",
        "pause": "暂停播放", 
        "stop": "停止播放",
        "volume": f"设置音量为{value}",
        "mute": "静音"
    }
    
    if command not in commands:
        return {
            "success": False,
            "error": f"不支持的命令: {command}",
            "supported_commands": list(commands.keys())
        }
    
    return {
        "success": True,
        "action": "hardware_control",
        "command": command,
        "value": value,
        "instruction": f"ESP32-S3执行音频控制: {commands[command]}",
        "user_message": f"已发送硬件控制指令: {commands[command]}"
    }

@mcp.tool()
def get_hardware_status() -> dict:
    """
    获取ESP32-S3硬件状态
    Returns:
        dict: 硬件状态信息
    """
    return {
        "success": True,
        "hardware": "ESP32-S3",
        "audio_capabilities": {
            "i2s": True,
            "pwm_audio": True,
            "mp3_decoding": True,
            "wav_playback": True,
            "sample_rate_max": 48000,
            "channels": 2
        },
        "status": "ready",
        "instruction": "硬件就绪，可接收音频播放指令"
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
