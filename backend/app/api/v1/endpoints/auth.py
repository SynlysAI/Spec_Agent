"""本地登录接口。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Header
from fastapi import HTTPException

from app.core.auth import build_access_token
from app.core.auth import resolve_authenticated_username
from app.core.auth import verify_local_credentials
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.auth import AuthStatusData
from app.schemas.auth import LoginData
from app.schemas.auth import LoginRequest
from app.schemas.common import ApiResponse

logger = get_logger("spec_agent.api.auth")


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=ApiResponse[AuthStatusData])
def get_auth_status(authorization: str | None = Header(default=None)) -> ApiResponse[AuthStatusData]:
    """获取当前服务登录开关与会话状态。

    Args:
        authorization: 请求头中的 Authorization 值。

    Returns:
        当前登录配置与认证状态。
    """
    username: str | None = None
    authenticated = False
    if settings.auth_enabled and authorization:
        try:
            username = resolve_authenticated_username(authorization)
            authenticated = bool(username)
        except HTTPException:
            authenticated = False
            username = None

    data = AuthStatusData(
        auth_enabled=settings.auth_enabled,
        authenticated=authenticated,
        username=username,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/login", response_model=ApiResponse[LoginData])
def login(payload: LoginRequest) -> ApiResponse[LoginData]:
    """执行本地账号密码登录。

    Args:
        payload: 登录请求参数。

    Returns:
        登录成功后的令牌与会话信息。
    """
    if not settings.auth_enabled:
        logger.warning("登录失败：当前服务未启用登录校验")
        raise HTTPException(status_code=400, detail="当前服务未启用登录校验")
    if not verify_local_credentials(payload.username, payload.password):
        logger.warning("登录失败：账号或密码错误，用户名=%s", payload.username)
        raise HTTPException(status_code=401, detail="账号或密码错误")

    token, expires_at = build_access_token(payload.username)
    data = LoginData(
        auth_enabled=True,
        username=payload.username,
        access_token=token,
        token_type="Bearer",
        expires_at=expires_at,
    )
    return ApiResponse(code=0, message="ok", data=data)
