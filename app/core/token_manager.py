"""
Token pool management with load balancing and round-robin mechanism
"""

import os
import time
import threading
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field


def debug_log(message: str, *args) -> None:
    """Log debug message if debug mode is enabled"""
    # Import here to avoid circular import
    try:
        from app.core.config import settings
        if settings.DEBUG_LOGGING:
            if args:
                print(f"[DEBUG] {message % args}")
            else:
                print(f"[DEBUG] {message}")
    except:
        # Fallback if settings not available
        print(f"[DEBUG] {message}")


@dataclass
class TokenInfo:
    """Token information with failure tracking"""
    token: str
    failure_count: int = 0
    is_active: bool = True
    last_failure_time: Optional[float] = None
    last_used_time: Optional[float] = None


class TokenManager:
    """Token pool manager with load balancing and failure handling"""
    
    def __init__(self, token_file_path: str = None):
        try:
            from app.core.config import settings
            self.token_file_path = token_file_path or getattr(settings, 'TOKEN_FILE_PATH', './tokens.txt')
            self.max_failures = getattr(settings, 'TOKEN_MAX_FAILURES', 3)
            self.reload_interval = getattr(settings, 'TOKEN_RELOAD_INTERVAL', 60)
        except ImportError:
            # Fallback values if settings not available
            self.token_file_path = token_file_path or './tokens.txt'
            self.max_failures = 3
            self.reload_interval = 60
        
        self.tokens: List[TokenInfo] = []
        self.current_index = 0
        self.last_reload_time = 0
        self._lock = threading.Lock()
        
        # Load tokens on initialization
        self._load_tokens()
    
    def _load_tokens(self) -> None:
        """Load tokens from file"""
        try:
            new_tokens = []
            
            # 首先尝试从tokens.txt文件加载token
            if os.path.exists(self.token_file_path):
                with open(self.token_file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for line in lines:
                    token = line.strip()
                    if token and not token.startswith('#'):  # Skip empty lines and comments
                        # Check if this token already exists to preserve failure count
                        existing_token = next((t for t in self.tokens if t.token == token), None)
                        if existing_token:
                            new_tokens.append(existing_token)
                        else:
                            new_tokens.append(TokenInfo(token=token))
                
                if new_tokens:
                    debug_log(f"从tokens.txt文件加载了 {len(new_tokens)} 个token")
                else:
                    debug_log("Token文件为空或无有效token")
            
            # 然后尝试从BACKUP_TOKEN环境变量加载token
            try:
                from app.core.config import settings
                if hasattr(settings, 'BACKUP_TOKEN') and settings.BACKUP_TOKEN:
                    # 支持多个BACKUP_TOKEN值，以逗号分隔
                    backup_tokens = [token.strip() for token in settings.BACKUP_TOKEN.split(',') if token.strip()]
                    
                    # 添加不重复的backup token
                    for backup_token in backup_tokens:
                        # 检查是否已经存在相同的token
                        existing_token = next((t for t in new_tokens if t.token == backup_token), None)
                        if not existing_token:
                            # 检查是否在原有tokens中存在，以保留失败计数
                            old_token = next((t for t in self.tokens if t.token == backup_token), None)
                            if old_token:
                                new_tokens.append(old_token)
                            else:
                                new_tokens.append(TokenInfo(token=backup_token))
                    
                    debug_log(f"从BACKUP_TOKEN加载了 {len(backup_tokens)} 个token")
            except ImportError:
                pass
            
            # 如果没有任何token，尝试仅使用BACKUP_TOKEN
            if not new_tokens:
                try:
                    from app.core.config import settings
                    if hasattr(settings, 'BACKUP_TOKEN') and settings.BACKUP_TOKEN:
                        # 支持多个BACKUP_TOKEN值，以逗号分隔
                        backup_tokens = [token.strip() for token in settings.BACKUP_TOKEN.split(',') if token.strip()]
                        new_tokens = [TokenInfo(token=token) for token in backup_tokens]
                        debug_log(f"仅使用BACKUP_TOKEN，共{len(backup_tokens)}个token")
                except ImportError:
                    pass
            
            if new_tokens:
                with self._lock:
                    self.tokens = new_tokens
                    # Reset index if it's out of bounds
                    if self.current_index >= len(self.tokens):
                        self.current_index = 0
                    self.last_reload_time = time.time()
                
                debug_log(f"总共加载了 {len(self.tokens)} 个token")
                active_count = sum(1 for t in self.tokens if t.is_active)
                debug_log(f"活跃token数量: {active_count}")
            else:
                debug_log("没有找到任何可用的token")
                
        except Exception as e:
            debug_log(f"加载token失败: {e}")
    
    def _should_reload(self) -> bool:
        """Check if tokens should be reloaded"""
        return time.time() - self.last_reload_time > self.reload_interval
    
    def get_next_token(self) -> Optional[str]:
        """Get next available token using round-robin with load balancing"""
        # Reload tokens if needed
        if self._should_reload():
            self._load_tokens()
        
        with self._lock:
            if not self.tokens:
                debug_log("没有可用的token")
                return None
            
            # Find active tokens
            active_tokens = [i for i, t in enumerate(self.tokens) if t.is_active]
            
            if not active_tokens:
                debug_log("没有活跃的token，尝试重置失败计数")
                # Reset all tokens if none are active (maybe temporary network issues)
                for token in self.tokens:
                    token.is_active = True
                    token.failure_count = 0
                active_tokens = list(range(len(self.tokens)))
            
            # Round-robin selection from active tokens
            attempts = 0
            max_attempts = len(active_tokens)
            
            while attempts < max_attempts:
                # Find next active token starting from current_index
                token_index = None
                for i in range(len(self.tokens)):
                    idx = (self.current_index + i) % len(self.tokens)
                    if idx in active_tokens:
                        token_index = idx
                        break
                
                if token_index is not None:
                    self.current_index = (token_index + 1) % len(self.tokens)
                    token_info = self.tokens[token_index]
                    token_info.last_used_time = time.time()
                    debug_log(f"选择token[{token_index}]: {token_info.token[:20]}...")
                    return token_info.token
                
                attempts += 1
            
            debug_log("无法找到可用的token")
            return None
    
    def mark_token_failed(self, token: str) -> None:
        """Mark a token as failed and deactivate if necessary"""
        with self._lock:
            for token_info in self.tokens:
                if token_info.token == token:
                    token_info.failure_count += 1
                    token_info.last_failure_time = time.time()
                    
                    if token_info.failure_count >= self.max_failures:
                        token_info.is_active = False
                        debug_log(f"Token失效 (失败{token_info.failure_count}次): {token[:20]}...")
                    else:
                        debug_log(f"Token失败 ({token_info.failure_count}/{self.max_failures}): {token[:20]}...")
                    break
    
    def mark_token_success(self, token: str) -> None:
        """Mark a token as successful (reset failure count)"""
        with self._lock:
            for token_info in self.tokens:
                if token_info.token == token:
                    if token_info.failure_count > 0:
                        debug_log(f"Token恢复正常: {token[:20]}...")
                    token_info.failure_count = 0
                    token_info.is_active = True
                    break
    
    def get_token_stats(self) -> Dict[str, Any]:
        """Get token pool statistics"""
        with self._lock:
            if not self.tokens:
                return {
                    "total": 0,
                    "active": 0,
                    "failed": 0,
                    "tokens": []
                }
            
            active_count = sum(1 for t in self.tokens if t.is_active)
            failed_count = len(self.tokens) - active_count
            
            token_details = []
            for i, token_info in enumerate(self.tokens):
                token_details.append({
                    "index": i,
                    "token_preview": token_info.token[:20] + "...",
                    "is_active": token_info.is_active,
                    "failure_count": token_info.failure_count,
                    "last_failure_time": token_info.last_failure_time,
                    "last_used_time": token_info.last_used_time
                })
            
            return {
                "total": len(self.tokens),
                "active": active_count,
                "failed": failed_count,
                "current_index": self.current_index,
                "last_reload_time": self.last_reload_time,
                "tokens": token_details
            }
    
    def reset_all_tokens(self) -> None:
        """Reset all tokens (clear failure counts and reactivate)"""
        with self._lock:
            for token_info in self.tokens:
                token_info.is_active = True
                token_info.failure_count = 0
                token_info.last_failure_time = None
            debug_log("已重置所有token状态")
    
    def reload_tokens(self) -> None:
        """Force reload tokens from file"""
        debug_log("强制重新加载token文件")
        self._load_tokens()


# Global token manager instance
token_manager = TokenManager()