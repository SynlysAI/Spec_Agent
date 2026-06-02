"""认证服务基础入口。"""

from __future__ import annotations

from app.infra.mongo import get_invite_codes_collection, get_users_collection


def ensure_identity_indexes() -> None:
    """确保用户与邀请码集合索引已创建。"""
    get_users_collection().create_index("username", unique=True)
    get_users_collection().create_index("user_id", unique=True)
    get_invite_codes_collection().create_index("invite_code", unique=True)
    get_invite_codes_collection().create_index("invite_id", unique=True)
    get_invite_codes_collection().create_index("expires_at")
