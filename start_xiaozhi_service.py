#!/usr/bin/env python3
"""
小智AI音乐服务快速启动脚本
用于测试和验证服务连接
"""

import os
import time
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    """测试连接配置"""
    print("🔧 测试小智AI音乐服务配置...")
    
    # 检查环境变量
    token = os.getenv("MCP_WSS_TOKEN")
    api_key = os.getenv("MUSIC_API_KEY")
    
    if not token:
        print("❌ MCP_WSS_TOKEN 未设置")
        return False
    
    print(f"✅ MCP Token: {token[:20]}...")
    
    if api_key:
        print("✅ 音乐API密钥已配置")
    else:
        print("⚠️ 音乐API密钥未配置")
    
    # 测试音乐API
    if api_key:
        try:
            test_params = {"key": api_key, "msg": "测试", "n": 1}
            response = requests.post("https://api.yaohud.cn/api/music/wy", params=test_params, timeout=10)
            if response.status_code == 200:
                print("✅ 音乐API连接正常")
            else:
                print(f"⚠️ 音乐API返回状态码: {response.status_code}")
        except Exception as e:
            print(f"❌ 音乐API测试失败: {e}")
    
    return True

def show_usage():
    """显示使用说明"""
    print("\n🎵 小智AI音乐服务使用指南")
    print("=" * 50)
    print("1. 在GitHub仓库的Settings -> Secrets中配置:")
    print("   - MCP_WSS_TOKEN: 你的小智AI MCP Token")
    print("   - MUSIC_API_KEY: 音乐API密钥（可选）")
    print()
    print("2. 手动启动服务:")
    print("   - 进入GitHub Actions页面")
    print("   - 选择 'Xiaozhi AI Music Service' 工作流")
    print("   - 点击 'Run workflow'")
    print()
    print("3. 在小智AI中使用:")
    print("   - 对AI说: '播放周杰伦的青花瓷'")
    print("   - 或: '搜索邓紫棋的歌曲'")
    print("   - 或: '推荐一些热门歌曲'")
    print()
    print("4. 服务特性:")
    print("   - 每次运行约4小时")
    print("   - 自动定时重启")
    print("   - 完整日志记录")

if __name__ == "__main__":
    print("🚀 小智AI音乐服务配置检查")
    print("=" * 50)
    
    if test_connection():
        print("\n✅ 配置检查通过！")
        show_usage()
    else:
        print("\n❌ 配置检查失败，请检查环境变量设置")
        show_usage()
