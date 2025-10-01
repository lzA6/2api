"""
Admin API endpoints for token management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from typing import Dict, Any

from app.core.config import settings
from app.core.token_manager import token_manager

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer()


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify admin authentication token"""
    if settings.SKIP_AUTH_TOKEN:
        return credentials.credentials
    
    if credentials.credentials != settings.AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@router.get("/token-stats")
async def get_token_stats(token: str = Depends(verify_admin_token)) -> Dict[str, Any]:
    """Get token pool statistics"""
    return token_manager.get_token_stats()


@router.post("/reload-tokens")
async def reload_tokens(token: str = Depends(verify_admin_token)) -> Dict[str, str]:
    """Force reload tokens from file"""
    try:
        token_manager.reload_tokens()
        return {"message": "Token池已重新加载"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载失败: {str(e)}"
        )


@router.post("/reset-tokens")
async def reset_tokens(token: str = Depends(verify_admin_token)) -> Dict[str, str]:
    """Reset all tokens (clear failure counts)"""
    try:
        token_manager.reset_all_tokens()
        return {"message": "所有token状态已重置"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重置失败: {str(e)}"
        )