"""
FastAPI application configuration module
"""

import os
from typing import Dict, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_ENDPOINT: str = os.getenv("API_ENDPOINT", "https://chat.z.ai/api/chat/completions")
    AUTH_TOKEN: str = os.getenv("AUTH_TOKEN", "sk-your-api-key")
    BACKUP_TOKEN: str = os.getenv("BACKUP_TOKEN", "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMxNmJjYjQ4LWZmMmYtNGExNS04NTNkLWYyYTI5YjY3ZmYwZiIsImVtYWlsIjoiR3Vlc3QtMTc1NTg0ODU4ODc4OEBndWVzdC5jb20ifQ.PktllDySS3trlyuFpTeIZf-7hl8Qu1qYF3BxjgIul0BrNux2nX9hVzIjthLXKMWAf9V0qM8Vm_iyDqkjPGsaiQ")
    
    # Model Configuration
    PRIMARY_MODEL: str = os.getenv("PRIMARY_MODEL", "GLM-4.5")
    THINKING_MODEL: str = os.getenv("THINKING_MODEL", "GLM-4.5-Thinking")
    SEARCH_MODEL: str = os.getenv("SEARCH_MODEL", "GLM-4.5-Search")
    AIR_MODEL: str = os.getenv("AIR_MODEL", "GLM-4.5-Air")
    GLM_46_MODEL: str = os.getenv("GLM_46_MODEL", "GLM-4.6")
    GLM_46_THINKING_MODEL: str = os.getenv("GLM_46_THINKING_MODEL", "GLM-4.6-Thinking")
    
    # Server Configuration
    LISTEN_PORT: int = int(os.getenv("LISTEN_PORT", "8080"))
    DEBUG_LOGGING: bool = os.getenv("DEBUG_LOGGING", "true").lower() == "true"
    
    # Feature Configuration
    THINKING_PROCESSING: str = os.getenv("THINKING_PROCESSING", "think")  # strip: 去除<details>标签；think: 转为<span>标签；raw: 保留原样
    ANONYMOUS_MODE: bool = os.getenv("ANONYMOUS_MODE", "true").lower() == "true"
    TOOL_SUPPORT: bool = os.getenv("TOOL_SUPPORT", "true").lower() == "true"
    SCAN_LIMIT: int = int(os.getenv("SCAN_LIMIT", "200000"))
    SKIP_AUTH_TOKEN: bool = os.getenv("SKIP_AUTH_TOKEN", "false").lower() == "true"
    
    # Signature Configuration - 强制禁用，忽略所有环境变量
    ENABLE_SIGNATURE: bool = False  # 强制禁用签名验证
    SIGNATURE_SECRET_KEY: str = "disabled"  # 已禁用
    SIGNATURE_ALGORITHM: str = "disabled"   # 已禁用
    
    # Token Pool Configuration
    TOKEN_FILE_PATH: str = os.getenv("TOKEN_FILE_PATH", "./tokens.txt")
    TOKEN_MAX_FAILURES: int = int(os.getenv("TOKEN_MAX_FAILURES", "3"))
    TOKEN_RELOAD_INTERVAL: int = int(os.getenv("TOKEN_RELOAD_INTERVAL", "60"))
    
    # Request Configuration
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "120"))
    CONNECTION_TIMEOUT: int = int(os.getenv("CONNECTION_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    
    # Proxy Configuration
    HTTP_PROXY: Optional[str] = os.getenv("HTTP_PROXY")
    HTTPS_PROXY: Optional[str] = os.getenv("HTTPS_PROXY")
    
    # Browser Headers - 匹配真实F12调试信息
    CLIENT_HEADERS: Dict[str, str] = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN",
        "Content-Type": "application/json", 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
        "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Fe-Version": "prod-fe-1.0.83",  # 匹配F12信息中的版本
        "Origin": "https://chat.z.ai",
        "Connection": "keep-alive",
    }
    
    class Config:
        env_file = ".env"


settings = Settings()