"""认证接口模型。"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(description="登录用户名")
    password: str = Field(description="登录密码")


class LoginData(BaseModel):
    """登录结果数据。"""

    auth_enabled: bool = Field(description="是否启用登录校验")
    username: str = Field(description="当前登录用户名")
    access_token: str = Field(description="访问令牌")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_at: int = Field(description="过期时间戳（秒）")


class AuthStatusData(BaseModel):
    """认证状态数据。"""

    auth_enabled: bool = Field(description="是否启用登录校验")
    authenticated: bool = Field(description="当前请求是否已认证")
    username: str | None = Field(default=None, description="当前登录用户名")
