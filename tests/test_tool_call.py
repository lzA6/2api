#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试工具调用功能
"""

import json
import requests

# 配置
BASE_URL = "http://localhost:8080"
API_KEY = "your-api-key"  # 替换为实际的 API key

def test_tool_call():
    """测试工具调用功能"""
    
    # 定义一个简单的工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "城市名称，例如：北京、上海"
                        },
                        "unit": {
                            "type": "string",
                            "description": "温度单位",
                            "enum": ["celsius", "fahrenheit"]
                        }
                    },
                    "required": ["location"]
                }
            }
        }
    ]
    
    # 构建请求
    request_data = {
        "model": "GLM-4.5",
        "messages": [
            {
                "role": "user",
                "content": "北京的天气怎么样？"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    print("=" * 60)
    print("测试工具调用 (非流式)")
    print("=" * 60)
    
    # 发送请求
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json=request_data,
        headers=headers
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("\n响应内容:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # 检查是否有工具调用
        if result.get("choices"):
            choice = result["choices"][0]
            if choice.get("message", {}).get("tool_calls"):
                print("\n✅ 检测到工具调用!")
                for tc in choice["message"]["tool_calls"]:
                    print(f"  - 函数: {tc.get('function', {}).get('name')}")
                    print(f"    参数: {tc.get('function', {}).get('arguments')}")
            else:
                print("\n⚠️ 未检测到工具调用")
                if choice.get("message", {}).get("content"):
                    print(f"内容: {choice['message']['content'][:200]}")
    else:
        print(f"\n错误响应: {response.text}")
    
    # 测试流式响应
    print("\n" + "=" * 60)
    print("测试工具调用 (流式)")
    print("=" * 60)
    
    request_data["stream"] = True
    
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json=request_data,
        headers=headers,
        stream=True
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        print("\n流式响应:")
        tool_calls_detected = False
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    if data == "[DONE]":
                        print("流结束")
                        break
                    
                    try:
                        chunk = json.loads(data)
                        if chunk.get("choices"):
                            delta = chunk["choices"][0].get("delta", {})
                            if delta.get("tool_calls"):
                                tool_calls_detected = True
                                print(f"检测到工具调用: {json.dumps(delta['tool_calls'], ensure_ascii=False)}")
                            elif delta.get("content"):
                                print(f"内容: {delta['content']}", end="")
                    except json.JSONDecodeError:
                        pass
        
        if tool_calls_detected:
            print("\n\n✅ 流式响应中检测到工具调用!")
        else:
            print("\n\n⚠️ 流式响应中未检测到工具调用")
    else:
        print(f"\n错误响应: {response.text}")


if __name__ == "__main__":
    test_tool_call()