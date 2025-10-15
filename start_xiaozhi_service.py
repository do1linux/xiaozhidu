#!/usr/bin/env python3
"""
测试小智AI音乐服务客户端
"""

import requests
import json
import time

def test_service():
    """测试音乐服务"""
    base_url = "http://localhost:8080"
    
    print("🧪 测试小智AI音乐服务...")
    
    # 测试状态
    try:
        response = requests.get(f"{base_url}/status")
        print(f"✅ 状态检查: {response.status_code}")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        return
    
    # 测试搜索
    test_songs = ["周杰伦 七里香", "邓紫棋 光年之外"]
    
    for song in test_songs:
        try:
            print(f"\n🔍 测试搜索: {song}")
            response = requests.post(f"{base_url}/search", json={"song_name": song})
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 搜索成功: {result.get('status')}")
                print(f"📝 响应: {result.get('response', '无响应')}")
            else:
                print(f"❌ 搜索失败: {response.status_code}")
        except Exception as e:
            print(f"❌ 搜索异常: {e}")
    
    print("\n🎉 测试完成！")

if __name__ == "__main__":
    test_service()
