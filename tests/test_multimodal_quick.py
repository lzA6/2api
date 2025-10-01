"""
glm-4.5v 多模态功能测试
"""
import requests
import json

# 创建一个1x1像素的红色图片作为测试
tiny_red_image = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)

# API配置
api_url = "http://localhost:8080/v1/chat/completions"
api_key = "sk-your-api-key"

# 构建正确的多模态请求
request_data = {
    "model": "glm-4.5v",  # 使用多模态模型
    "messages": [
        {
            "role": "user",
            "content": [  # content必须是数组
                {
                    "type": "text",
                    "text": "这是什么颜色的图片？"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": tiny_red_image
                    }
                }
            ]
        }
    ],
    "stream": False
}

print("发送的请求:")
print(json.dumps(request_data, indent=2, ensure_ascii=False))
print("\n" + "="*60)

# 发送请求
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    response = requests.post(api_url, json=request_data, headers=headers)
    print(f"响应状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("\n模型回复:")
        print(result["choices"][0]["message"]["content"])
    else:
        print("\n错误响应:")
        print(response.text)
        
except Exception as e:
    print(f"\n发生错误: {e}")