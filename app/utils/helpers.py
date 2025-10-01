"""
Utility functions for the application
"""

import json
import re
import time
import random
from typing import Dict, List, Optional, Any, Tuple, Generator
import requests
from fake_useragent import UserAgent

from app.core.config import settings
from app.core.token_manager import token_manager

# 全局 UserAgent 实例，避免每次调用都创建新实例
_user_agent_instance = None

def get_user_agent_instance() -> UserAgent:
    """获取或创建 UserAgent 实例（单例模式）"""
    global _user_agent_instance
    if _user_agent_instance is None:
        _user_agent_instance = UserAgent()
    return _user_agent_instance


def debug_log(message: str, *args) -> None:
    """Log debug message if debug mode is enabled"""
    if settings.DEBUG_LOGGING:
        if args:
            print(f"[DEBUG] {message % args}")
        else:
            print(f"[DEBUG] {message}")


def generate_request_ids() -> Tuple[str, str]:
    """Generate unique IDs for chat and message"""
    timestamp = int(time.time())
    chat_id = f"{timestamp * 1000}-{timestamp}"
    msg_id = str(timestamp * 1000000)
    return chat_id, msg_id


def get_browser_headers(referer_chat_id: str = "") -> Dict[str, str]:
    """Get browser headers for API requests with dynamic User-Agent"""
    
    # 获取 UserAgent 实例
    ua = get_user_agent_instance()
    
    # 随机选择一个浏览器类型，偏向使用 Chrome 和 Edge
    browser_choices = ['chrome', 'chrome', 'chrome', 'edge', 'edge', 'firefox', 'safari']
    browser_type = random.choice(browser_choices)
    
    try:
        # 根据浏览器类型获取 User-Agent
        if browser_type == 'chrome':
            user_agent = ua.chrome
        elif browser_type == 'edge':
            user_agent = ua.edge
        elif browser_type == 'firefox':
            user_agent = ua.firefox
        elif browser_type == 'safari':
            user_agent = ua.safari
        else:
            user_agent = ua.random
    except:
        # 如果获取失败，使用随机 User-Agent
        user_agent = ua.random
    
    # 提取浏览器版本信息
    chrome_version = "139"  # 默认版本
    edge_version = "139"
    
    if "Chrome/" in user_agent:
        try:
            chrome_version = user_agent.split("Chrome/")[1].split(".")[0]
        except:
            pass
    
    if "Edg/" in user_agent:
        try:
            edge_version = user_agent.split("Edg/")[1].split(".")[0]
            # Edge 基于 Chromium，使用 Edge 特定的 sec-ch-ua
            sec_ch_ua = f'"Microsoft Edge";v="{edge_version}", "Chromium";v="{chrome_version}", "Not_A Brand";v="24"'
        except:
            sec_ch_ua = f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"'
    elif "Firefox/" in user_agent:
        # Firefox 不使用 sec-ch-ua
        sec_ch_ua = None
    else:
        # Chrome 或其他基于 Chromium 的浏览器
        sec_ch_ua = f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"'
    
    # 构建动态 Headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "X-FE-Version": "prod-fe-1.0.70",
        "Origin": settings.CLIENT_HEADERS["Origin"],
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    
    # 只有基于 Chromium 的浏览器才添加 sec-ch-ua
    if sec_ch_ua:
        headers["sec-ch-ua"] = sec_ch_ua
    
    # 添加 Referer
    if referer_chat_id:
        headers["Referer"] = f"{settings.CLIENT_HEADERS['Origin']}/c/{referer_chat_id}"
    
    # 调试日志
    if settings.DEBUG_LOGGING:
        debug_log(f"使用 User-Agent: {user_agent[:100]}...")
    
    return headers


def get_anonymous_token() -> str:
    """Get anonymous token for authentication"""
    headers = get_browser_headers()
    headers.update({
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": f"{settings.CLIENT_HEADERS['Origin']}/",
    })
    
    try:
        response = requests.get(
            f"{settings.CLIENT_HEADERS['Origin']}/api/v1/auths/",
            headers=headers,
            timeout=10.0
        )
        
        if response.status_code != 200:
            raise Exception(f"anon token status={response.status_code}")
        
        data = response.json()
        token = data.get("token")
        if not token:
            raise Exception("anon token empty")
        
        return token
    except Exception as e:
        debug_log(f"获取匿名token失败: {e}")
        raise


def get_auth_token() -> str:
    """Get authentication token (anonymous or from token pool)"""
    if settings.ANONYMOUS_MODE:
        try:
            token = get_anonymous_token()
            debug_log(f"匿名token获取成功: {token[:10]}...")
            return token
        except Exception as e:
            debug_log(f"匿名token获取失败，使用token池: {e}")
    
    # Use token pool for load balancing
    token = token_manager.get_next_token()
    if token:
        debug_log(f"从token池获取token: {token[:10]}...")
        return token
    else:
        debug_log("token池无可用token，使用配置文件备用token")
        return settings.BACKUP_TOKEN


def transform_thinking_content(content: str) -> str:
    """Transform thinking content according to configuration"""
    # Remove summary tags
    content = re.sub(r'(?s)<summary>.*?</summary>', '', content)
    # Clean up remaining tags
    content = content.replace("</thinking>", "").replace("<Full>", "").replace("</Full>", "")
    content = content.strip()
    
    if settings.THINKING_PROCESSING == "think":
        content = re.sub(r'<details[^>]*>', '<span>', content)
        content = content.replace("</details>", "</span>")
    elif settings.THINKING_PROCESSING == "strip":
        content = re.sub(r'<details[^>]*>', '', content)
        content = content.replace("</details>", "")
    
    # Remove line prefixes
    content = content.lstrip("> ")
    content = content.replace("\n> ", "\n")
    
    return content.strip()


def call_upstream_api(
    upstream_req: Any,
    chat_id: str,
    auth_token: str
) -> requests.Response:
    """Call upstream API with proper headers"""
    headers = get_browser_headers(chat_id)
    headers["Authorization"] = f"Bearer {auth_token}"
    
    # 准备请求数据
    request_data = upstream_req.model_dump(exclude_none=True)
    request_json = upstream_req.model_dump_json()
    
    debug_log(f"调用上游API: {settings.API_ENDPOINT}")
    debug_log(f"请求体大小: {len(request_json)} 字符")
    
    # 如果请求体太大，只显示部分内容
    if len(request_json) > 1000:
        debug_log(f"上游请求体 (截断): {request_json[:500]}...{request_json[-200:]}")
    else:
        debug_log(f"上游请求体: {request_json}")
    
    # 设置代理（如果配置了）
    proxies = {}
    if settings.HTTP_PROXY:
        proxies['http'] = settings.HTTP_PROXY
    if settings.HTTPS_PROXY:
        proxies['https'] = settings.HTTPS_PROXY
    
    try:
        response = requests.post(
            settings.API_ENDPOINT,
            json=request_data,
            headers=headers,
            timeout=(settings.CONNECTION_TIMEOUT, settings.REQUEST_TIMEOUT),
            stream=True,
            proxies=proxies if proxies else None,
            verify=True,
        )
        
        debug_log(f"上游响应状态: {response.status_code}")
        
        # 检查响应头
        if settings.DEBUG_LOGGING:
            content_type = response.headers.get('content-type', 'unknown')
            content_length = response.headers.get('content-length', 'unknown')
            debug_log(f"响应类型: {content_type}, 长度: {content_length}")
        
        return response
        
    except requests.exceptions.Timeout as e:
        debug_log(f"请求超时: {e}")
        raise Exception(f"上游API请求超时: {e}")
    except requests.exceptions.ConnectionError as e:
        debug_log(f"连接错误: {e}")
        raise Exception(f"上游API连接失败: {e}")
    except requests.exceptions.RequestException as e:
        debug_log(f"请求异常: {e}")
        raise Exception(f"上游API请求失败: {e}")
    except Exception as e:
        debug_log(f"未知错误: {e}")
        raise
