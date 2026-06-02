"""认证服务相关测试。"""

from __future__ import annotations

import unittest
from datetime import datetime

from app.schemas.identity_runtime import InviteCodeRecord, UserRecord


class TestIdentityRuntimeModels(unittest.TestCase):
    """验证认证运行态实体模型。"""

    def test_identity_runtime_user_record_accepts_admin_role(self) -> None:
        """应支持管理员角色的用户实体。"""
        now = datetime.now()
        record = UserRecord(
            user_id="u_admin_001",
            username="admin",
            password_hash="hashed",
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by=None,
        )

        self.assertEqual(record.role, "admin")
        self.assertEqual(record.status, "active")

    def test_identity_runtime_invite_code_record_tracks_usage(self) -> None:
        """应记录邀请码使用次数与上限。"""
        now = datetime.now()
        record = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=now,
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=now,
            updated_at=now,
        )

        self.assertEqual(record.max_uses, 1)
        self.assertEqual(record.used_count, 0)


if __name__ == "__main__":
    unittest.main()
