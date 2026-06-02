"""认证服务基础入口。"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from uuid import uuid4

from app.core.auth import build_access_token
from app.infra.mongo import get_invite_codes_collection, get_users_collection
from app.infra.repositories import InviteCodeRepository
from app.infra.repositories import UserRepository
from app.schemas.auth import LoginData
from app.schemas.identity_runtime import UserRecord


def ensure_identity_indexes() -> None:
    """确保用户与邀请码集合索引已创建。

    该函数由后续认证初始化流程显式调用，当前文件仅提供索引入口，
    不在导入阶段自动触发数据库操作。
    """
    get_users_collection().create_index("username", unique=True)
    get_users_collection().create_index("user_id", unique=True)
    get_invite_codes_collection().create_index("invite_code", unique=True)
    get_invite_codes_collection().create_index("invite_id", unique=True)
    get_invite_codes_collection().create_index("expires_at")


class AuthService:
    """认证服务。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """计算密码哈希值。

        Args:
            password: 明文密码。

        Returns:
            SHA-256 哈希结果。
        """
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """校验密码与哈希值是否匹配。

        Args:
            password: 明文密码。
            password_hash: 已保存的密码哈希值。

        Returns:
            密码是否匹配。
        """
        return hmac.compare_digest(AuthService.hash_password(password), password_hash)

    @staticmethod
    def register(invite_code: str, username: str, password: str) -> UserRecord:
        """基于邀请码注册用户。

        Args:
            invite_code: 邀请码。
            username: 用户名。
            password: 明文密码。

        Returns:
            新创建的用户记录。
        """
        invite = InviteCodeRepository.find_by_code(invite_code)
        if not invite:
            raise ValueError("邀请码不存在")
        if invite.status != "active":
            raise ValueError("邀请码不可用")
        if invite.expires_at <= datetime.now():
            raise ValueError("邀请码已过期")
        if invite.used_count >= invite.max_uses:
            raise ValueError("邀请码已用尽")
        if UserRepository.find_by_username(username):
            raise ValueError("用户名已存在")

        now = datetime.now()
        user_record = UserRecord(
            user_id=f"u_{uuid4().hex[:12]}",
            username=username,
            password_hash=AuthService.hash_password(password),
            role=invite.role,
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by=invite.created_by,
        )
        UserRepository.save(user_record)
        InviteCodeRepository.increment_usage(invite.invite_id)
        return user_record

    @staticmethod
    def login(username: str, password: str) -> LoginData:
        """使用数据库用户执行登录。

        Args:
            username: 登录用户名。
            password: 明文密码。

        Returns:
            登录结果数据。
        """
        user = UserRepository.find_by_username(username)
        if not user or not AuthService.verify_password(password, user.password_hash):
            raise ValueError("账号或密码错误")
        if user.status != "active":
            raise ValueError("当前账号已被禁用")

        token, expires_at = build_access_token(user.user_id, user.username, user.role)
        UserRepository.update_last_login(user.user_id)
        return LoginData(
            auth_enabled=True,
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            status=user.status,
            access_token=token,
            token_type="Bearer",
            expires_at=expires_at,
        )
