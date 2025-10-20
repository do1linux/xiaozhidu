from mcp.server.fastmcp import FastMCP
import requests
from playsound import playsound
import tempfile
import os
import logging
import threading

# -------------------------- 配置与初始化 --------------------------
# 初始化MCP和日志
mcp = FastMCP("MusicPlayer")
logger = logging.getLogger(__name__)
_LOCK = threading.Lock()  # 线程锁保证并发安全

# 从环境变量读取API配置（更安全，避免硬编码）
_API_URL = ' https://api.yaohud.cn/api/music/wy'  # 音乐API地址（需确保API可用）
_API_KEY = os.environ.get('MUSIC_API_KEY')       # 从环境变量获取API Key

# 检查API Key是否有效
if not _API_KEY:
    raise ValueError("未设置环境变量 MUSIC_API_KEY，请先配置！")


# -------------------------- MCP工具函数 --------------------------
@mcp.tool()
def play_music(song_name: str) -> str:
    """
    通过MCP接口播放音乐（线程安全）
    Args:
        song_name: 要播放的歌曲名（支持中文/英文）
    Returns:
        str: 播放结果（成功/失败信息）
    """
    # 1. 校验输入合法性
    song_name = song_name.strip()
    if not song_name:
        return "错误：歌曲名不能为空"

    # 2. 加锁保证线程安全（避免并发请求导致的问题）
    with _LOCK:
        try:
            # 步骤1：调用音乐API获取播放链接
            logger.info(f"正在搜索歌曲：{song_name}")
            api_params = {
                'key': _API_KEY,
                'msg': song_name,
                'n': '1'  # 只取第1个搜索结果
            }
            api_resp = requests.post(_API_URL, params=api_params, timeout=10)
            api_resp.raise_for_status()  # 抛出HTTP错误（如404、500）
            
            # 解析API返回的音乐URL
            music_data = api_resp.json()
            if not music_data.get('data') or not music_data['data'].get('musicurl'):
                return "错误：API未返回有效的音乐链接"
            music_url = music_data['data']['musicurl']

            # 步骤2：下载音乐到临时文件（避免长期占用磁盘）
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_file.write(requests.get(music_url, timeout=10).content)
                tmp_path = tmp_file.name

            # 步骤3：播放音乐（调用系统默认播放器）
            logger.info(f"正在播放：{song_name}（临时文件：{tmp_path}）")
            playsound(tmp_path)
            
            # 步骤4：播放完成后清理临时文件
            os.unlink(tmp_path)
            logger.info(f"播放完成，临时文件已清理：{tmp_path}")
            
            return f"成功播放：{song_name}"

        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求失败：{str(e)}", exc_info=True)
            return f"播放失败：网络问题或API不可用 - {str(e)}"
        except KeyError as e:
            logger.error(f"解析API响应失败：缺少关键字段 {str(e)}", exc_info=True)
            return f"播放失败：API返回格式异常 - {str(e)}"
        except Exception as e:
            logger.error(f"播放过程中发生未知错误：{str(e)}", exc_info=True)
            return f"播放失败：未知错误 - {str(e)}"


# -------------------------- 主程序入口 --------------------------
if __name__ == "__main__":
    # 启动MCP服务（通过标准输入输出与外部交互，支持命令行调用或MCP客户端）
    logger.info("音乐播放器MCP服务启动...")
    mcp.run(transport="stdio")
