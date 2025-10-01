# -*- coding: utf-8 -*-

import json
import requests

# API 配置
API_BASE = "http://localhost:8080"
API_KEY = "sk-your-api-key"

def test_weather_query():
    """测试天气查询"""
    print("=" * 50)
    print("上海天气查询测试")
    print("=" * 50)
    
    # 工具定义
    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"},
                    "date": {"type": "string", "description": "查询日期（可选）"}
                },
                "required": ["city"]
            }
        }
    }
    
    # 发送请求
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    data = {
        "model": "GLM-4.5",
        "messages": [
            {"role": "user", "content": "查询上海2025年9月3日的天气"}
        ],
        "tools": [tool]
    }
    
    print("\n发送请求...")
    response = requests.post(f"{API_BASE}/v1/chat/completions", 
                           headers=headers, 
                           json=data)
    
    if response.status_code == 200:
        result = response.json()
        message = result["choices"][0]["message"]
        
        print("\n模型响应:")
        if message.get("tool_calls"):
            print("检测到工具调用:")
            for tc in message["tool_calls"]:
                print(f"  - 工具: {tc['function']['name']}")
                print(f"  - 参数: {tc['function']['arguments']}")
        else:
            print("未检测到工具调用")
            print(f"内容: {message.get('content', '无内容')[:100]}...")
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")

if __name__ == "__main__":
    test_weather_query()