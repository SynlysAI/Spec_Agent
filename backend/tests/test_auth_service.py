"""认证服务相关测试。"""

from __future__ import annotations

import unittest
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import router as auth_router
from app.core.auth import build_access_token
from app.core.auth import get_current_user
from app.core.auth import get_current_user_optional
from app.core.auth import require_admin
from app.infra.repositories import InviteCodeRepository
from app.infra.repositories import UserRepository
from app.schemas.identity_runtime import InviteCodeRecord, UserRecord
from app.services.auth_service import AuthService
from app.services.auth_service import ensure_identity_indexes


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


class TestIdentityRepositories(unittest.TestCase):
    """验证认证仓储与索引入口。"""

    @patch("app.infra.repositories.get_users_collection")
    def test_user_repository_save_uses_upsert(self, get_users_collection: MagicMock) -> None:
        """保存用户时应执行 upsert。"""
        collection = MagicMock()
        get_users_collection.return_value = collection
        now = datetime.now()

        UserRepository.save(
            UserRecord(
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
        )

        collection.update_one.assert_called_once()
        _, kwargs = collection.update_one.call_args
        self.assertTrue(kwargs["upsert"])

    @patch("app.infra.repositories.get_users_collection")
    def test_user_repository_find_by_username_returns_user_record(self, get_users_collection: MagicMock) -> None:
        """按用户名查询应返回用户运行态实体。"""
        now = datetime.now()
        get_users_collection.return_value.find_one.return_value = {
            "user_id": "u_admin_001",
            "username": "admin",
            "password_hash": "hashed",
            "role": "admin",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
            "created_by": None,
        }

        result = UserRepository.find_by_username("admin")

        self.assertIsInstance(result, UserRecord)
        self.assertEqual(result.username, "admin")

    @patch("app.infra.repositories.get_invite_codes_collection")
    def test_invite_code_repository_save_uses_upsert(self, get_invite_codes_collection: MagicMock) -> None:
        """保存邀请码时应执行 upsert。"""
        collection = MagicMock()
        get_invite_codes_collection.return_value = collection
        now = datetime.now()

        InviteCodeRepository.save(
            InviteCodeRecord(
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
        )

        collection.update_one.assert_called_once()
        _, kwargs = collection.update_one.call_args
        self.assertTrue(kwargs["upsert"])

    @patch("app.services.auth_service.get_invite_codes_collection")
    @patch("app.services.auth_service.get_users_collection")
    def test_ensure_identity_indexes_creates_required_indexes(
        self,
        get_users_collection: MagicMock,
        get_invite_codes_collection: MagicMock,
    ) -> None:
        """索引初始化应为用户与邀请码集合创建关键索引。"""
        user_collection = MagicMock()
        invite_collection = MagicMock()
        get_users_collection.return_value = user_collection
        get_invite_codes_collection.return_value = invite_collection

        ensure_identity_indexes()

        user_collection.create_index.assert_any_call("username", unique=True)
        user_collection.create_index.assert_any_call("user_id", unique=True)
        invite_collection.create_index.assert_any_call("invite_code", unique=True)
        invite_collection.create_index.assert_any_call("invite_id", unique=True)
        invite_collection.create_index.assert_any_call("expires_at")


class TestAuthService(unittest.TestCase):
    """验证认证服务的注册与登录流程。"""

    @patch("app.services.auth_service.InviteCodeRepository.consume_available_code")
    @patch("app.services.auth_service.UserRepository.find_by_username")
    @patch("app.services.auth_service.UserRepository.save")
    def test_register_with_valid_invite(
        self,
        save_user: MagicMock,
        find_user: MagicMock,
        consume_invite: MagicMock,
    ) -> None:
        """有效邀请码应允许注册并原子消费使用次数。"""
        find_user.return_value = None
        consume_invite.return_value = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=datetime.now() + timedelta(hours=1),
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        result = AuthService.register("ABC12345", "alice", "Password123!")

        self.assertEqual(result.username, "alice")
        self.assertEqual(result.role, "user")
        save_user.assert_called_once()
        consume_invite.assert_called_once()

    @patch("app.services.auth_service.InviteCodeRepository.find_by_code")
    @patch("app.services.auth_service.InviteCodeRepository.consume_available_code")
    @patch("app.services.auth_service.UserRepository.find_by_username")
    def test_register_with_expired_invite_raises_error(
        self,
        find_user: MagicMock,
        consume_invite: MagicMock,
        find_invite: MagicMock,
    ) -> None:
        """邀请码已过期时注册应失败。"""
        now = datetime.now()
        find_user.return_value = None
        consume_invite.return_value = None
        find_invite.return_value = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=now - timedelta(seconds=1),
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=now,
            updated_at=now,
        )

        with self.assertRaisesRegex(ValueError, "邀请码已过期"):
            AuthService.register("ABC12345", "alice", "Password123!")

    @patch("app.services.auth_service.InviteCodeRepository.find_by_code")
    @patch("app.services.auth_service.InviteCodeRepository.consume_available_code")
    @patch("app.services.auth_service.UserRepository.find_by_username")
    def test_register_with_unavailable_invite_raises_error(
        self,
        find_user: MagicMock,
        consume_invite: MagicMock,
        find_invite: MagicMock,
    ) -> None:
        """邀请码不可用或已用尽时注册应失败。"""
        now = datetime.now()
        find_user.return_value = None
        consume_invite.return_value = None
        find_invite.return_value = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="disabled",
            expires_at=now + timedelta(hours=1),
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=now,
            updated_at=now,
        )

        with self.assertRaisesRegex(ValueError, "邀请码不可用"):
            AuthService.register("ABC12345", "alice", "Password123!")

    @patch("app.services.auth_service.InviteCodeRepository.find_by_code")
    @patch("app.services.auth_service.InviteCodeRepository.consume_available_code")
    @patch("app.services.auth_service.UserRepository.find_by_username")
    def test_register_with_used_up_invite_raises_error(
        self,
        find_user: MagicMock,
        consume_invite: MagicMock,
        find_invite: MagicMock,
    ) -> None:
        """邀请码已用尽时注册应失败。"""
        now = datetime.now()
        find_user.return_value = None
        consume_invite.return_value = None
        find_invite.return_value = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=now + timedelta(hours=1),
            max_uses=1,
            used_count=1,
            created_by="u_admin_001",
            created_at=now,
            updated_at=now,
        )

        with self.assertRaisesRegex(ValueError, "邀请码已用尽"):
            AuthService.register("ABC12345", "alice", "Password123!")

    @patch("app.services.auth_service.UserRepository.find_by_username")
    @patch("app.services.auth_service.UserRepository.update_last_login")
    def test_login_with_database_user(
        self,
        update_last_login: MagicMock,
        find_by_username: MagicMock,
    ) -> None:
        """数据库用户应可通过账号密码登录。"""
        find_by_username.return_value = UserRecord(
            user_id="u_user_001",
            username="alice",
            password_hash=AuthService.hash_password("Password123!"),
            role="user",
            status="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_login_at=None,
            created_by="u_admin_001",
        )

        login_data = AuthService.login("alice", "Password123!")

        self.assertEqual(login_data.username, "alice")
        self.assertTrue(login_data.access_token)
        update_last_login.assert_called_once_with("u_user_001")

    @patch("app.services.auth_service.UserRepository.find_by_username")
    def test_login_with_disabled_user_raises_error(
        self,
        find_by_username: MagicMock,
    ) -> None:
        """禁用用户登录应失败。"""
        find_by_username.return_value = UserRecord(
            user_id="u_user_001",
            username="alice",
            password_hash=AuthService.hash_password("Password123!"),
            role="user",
            status="disabled",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_login_at=None,
            created_by="u_admin_001",
        )

        with self.assertRaisesRegex(ValueError, "当前账号已被禁用"):
            AuthService.login("alice", "Password123!")


class TestAuthContext(unittest.TestCase):
    """验证认证上下文解析与权限控制。"""

    @staticmethod
    def _build_authorization(user_id: str = "u_user_001", username: str = "alice", role: str = "user") -> str:
        """构造 Bearer 认证头。"""
        token, _ = build_access_token(user_id, username, role)
        return f"Bearer {token}"

    @patch("app.infra.repositories.UserRepository.find_by_user_id")
    @patch("app.core.auth.settings.auth_enabled", True)
    def test_get_current_user_uses_database_role_and_status(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """当前用户上下文应以数据库中的真实角色与状态为准。"""
        now = datetime.now()
        find_by_user_id.return_value = UserRecord(
            user_id="u_user_001",
            username="alice-db",
            password_hash="hashed",
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by="u_admin_001",
        )

        current_user = get_current_user(self._build_authorization())

        self.assertEqual(current_user["username"], "alice-db")
        self.assertEqual(current_user["role"], "admin")
        self.assertEqual(current_user["status"], "active")

    @patch("app.infra.repositories.UserRepository.find_by_user_id")
    @patch("app.core.auth.settings.auth_enabled", True)
    def test_get_current_user_rejects_missing_database_user(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """数据库不存在对应用户时应拒绝当前认证。"""
        find_by_user_id.return_value = None

        with self.assertRaises(HTTPException) as context:
            get_current_user(self._build_authorization())

        self.assertEqual(context.exception.status_code, 401)

    @patch("app.infra.repositories.UserRepository.find_by_user_id")
    @patch("app.core.auth.settings.auth_enabled", True)
    def test_get_current_user_rejects_disabled_user(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """数据库中的禁用用户应被拒绝访问。"""
        now = datetime.now()
        find_by_user_id.return_value = UserRecord(
            user_id="u_user_001",
            username="alice",
            password_hash="hashed",
            role="user",
            status="disabled",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by="u_admin_001",
        )

        with self.assertRaises(HTTPException) as context:
            get_current_user(self._build_authorization())

        self.assertEqual(context.exception.status_code, 401)

    @patch("app.infra.repositories.UserRepository.find_by_user_id")
    @patch("app.core.auth.settings.auth_enabled", True)
    def test_require_admin_rejects_normal_user_context(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """普通用户上下文访问管理员依赖时应被拒绝。"""
        now = datetime.now()
        find_by_user_id.return_value = UserRecord(
            user_id="u_user_001",
            username="alice",
            password_hash="hashed",
            role="user",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by="u_admin_001",
        )

        with self.assertRaises(HTTPException) as context:
            require_admin(self._build_authorization())

        self.assertEqual(context.exception.status_code, 403)


class TestAuthEndpoints(unittest.TestCase):
    """验证认证接口行为。"""

    @staticmethod
    def _create_client() -> TestClient:
        """创建仅包含认证路由的测试客户端。"""
        app = FastAPI()
        app.include_router(auth_router)
        return TestClient(app)

    @patch("app.api.v1.endpoints.auth.settings.auth_enabled", True)
    def test_get_current_user_profile_without_token_returns_anonymous(self) -> None:
        """未携带令牌时 /auth/me 应返回匿名态而非 401。"""
        client = self._create_client()

        response = client.get("/auth/me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertFalse(payload["data"]["authenticated"])
        self.assertIsNone(payload["data"]["user_id"])

    @patch("app.api.v1.endpoints.auth.settings.auth_enabled", True)
    def test_get_current_user_profile_returns_database_status(
        self,
    ) -> None:
        """已登录用户的 /auth/me 应返回数据库中的真实状态。"""
        app = FastAPI()
        app.include_router(auth_router)
        app.dependency_overrides[get_current_user_optional] = lambda: {
            "user_id": "u_user_001",
            "username": "alice",
            "role": "user",
            "status": "disabled",
        }
        client = TestClient(app)

        response = client.get("/auth/me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
