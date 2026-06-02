"""管理员接口与路由权限测试。"""

from __future__ import annotations

import importlib
import unittest
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.auth import build_access_token
from app.core.auth import get_current_user
from app.core.auth import require_admin
from app.schemas.identity_runtime import UserRecord


class TestAdminEndpoints(unittest.TestCase):
    """验证管理员接口与角色保护。"""

    @staticmethod
    def _create_client() -> TestClient:
        """创建包含 V1 路由的测试客户端。

        Returns:
            挂载了 `/api/v1` 前缀的测试客户端。
        """
        app = TestAdminEndpoints._create_app()
        return TestClient(app)

    @staticmethod
    def _create_app() -> FastAPI:
        """创建挂载 V1 路由的 FastAPI 应用。

        Returns:
            已挂载 V1 路由的 FastAPI 应用。
        """
        mocked_collection = MagicMock()
        with (
            patch("app.infra.repositories.get_acceptance_runs_collection", return_value=mocked_collection),
            patch("app.infra.repositories.get_consistency_runs_collection", return_value=mocked_collection),
            patch("app.infra.repositories.get_lab_collect_runs_collection", return_value=mocked_collection),
            patch("app.infra.repositories.get_spectrum_samples_collection", return_value=mocked_collection),
            patch("app.infra.repositories.get_spectrum_sample_files_collection", return_value=mocked_collection),
            patch("app.infra.repositories.get_molecular_statistics_collection", return_value=mocked_collection),
        ):
            api_router = importlib.import_module("app.api.v1.router").api_router
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        return app

    @staticmethod
    def _build_authorization(user_id: str, username: str, role: str) -> dict[str, str]:
        """构造 Bearer 认证请求头。

        Args:
            user_id: 用户 ID。
            username: 用户名。
            role: Token 中声明的角色。

        Returns:
            可直接用于请求的认证头字典。
        """
        token, _ = build_access_token(user_id, username, role)
        return {"Authorization": f"Bearer {token}"}

    @patch("app.core.auth.settings.auth_enabled", True)
    def test_get_admin_users_requires_admin_permission(self) -> None:
        """未提供管理员认证时应拒绝访问用户列表。"""
        client = self._create_client()

        response = client.get("/api/v1/admin/users")

        self.assertIn(response.status_code, {401, 403})

    @patch("app.api.v1.endpoints.admin.UserRepository.list_all")
    def test_get_admin_users_returns_user_list_when_admin_dependency_passes(
        self,
        list_all_users: MagicMock,
    ) -> None:
        """管理员依赖通过时应返回用户列表。"""
        now = datetime.now()
        list_all_users.return_value = [
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
            ),
            UserRecord(
                user_id="u_user_001",
                username="alice",
                password_hash="hashed",
                role="user",
                status="disabled",
                created_at=now,
                updated_at=now,
                last_login_at=None,
                created_by="u_admin_001",
            ),
        ]
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        client = TestClient(app)

        response = client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["total"], 2)
        self.assertEqual(payload["data"]["items"][0]["user_id"], "u_admin_001")
        self.assertEqual(payload["data"]["items"][1]["status"], "disabled")

    @patch("app.infra.repositories.UserRepository.find_by_user_id")
    @patch("app.core.auth.settings.auth_enabled", True)
    def test_normal_user_access_admin_endpoint_returns_forbidden(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """普通用户访问管理员接口时应返回 403。"""
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
        client = self._create_client()

        response = client.get(
            "/api/v1/admin/users",
            headers=self._build_authorization("u_user_001", "alice", "user"),
        )

        self.assertEqual(response.status_code, 403)

    @patch("app.api.v1.endpoints.admin.InviteCodeRepository.save")
    def test_create_invite_code_persists_admin_metadata(
        self,
        save_invite_code: MagicMock,
    ) -> None:
        """创建邀请码时应保存固定角色、创建人和有效期配置。"""
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "u_admin_001",
            "username": "admin",
            "role": "admin",
            "status": "active",
        }
        client = TestClient(app)

        response = client.post(
            "/api/v1/admin/invite-codes",
            json={"expires_hours": 72, "max_uses": 3},
        )

        self.assertEqual(response.status_code, 200)
        save_invite_code.assert_called_once()
        saved_record = save_invite_code.call_args.args[0]
        self.assertEqual(saved_record.role, "user")
        self.assertEqual(saved_record.created_by, "u_admin_001")
        self.assertEqual(saved_record.max_uses, 3)
        self.assertEqual(saved_record.used_count, 0)
        self.assertEqual(saved_record.status, "active")
        expires_delta = saved_record.expires_at - saved_record.created_at
        self.assertAlmostEqual(expires_delta.total_seconds(), 72 * 3600, delta=5)

    def test_admin_protected_routers_register_require_admin_dependency(self) -> None:
        """实验管理相关路由应在 router 层挂载管理员依赖。"""
        app = self._create_app()
        target_paths = {
            "/api/v1/lab-collect/config",
            "/api/v1/acceptance/config",
            "/api/v1/consistency/config",
        }
        matched_routes = [
            route for route in app.routes if isinstance(route, APIRoute) and route.path in target_paths
        ]

        self.assertEqual(len(matched_routes), 3)
        for route in matched_routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(require_admin, dependency_calls)

    @patch("app.api.v1.endpoints.admin.UserRepository.update_status")
    @patch("app.api.v1.endpoints.admin.UserRepository.find_by_user_id")
    def test_patch_admin_user_status_returns_success_when_updated(
        self,
        find_by_user_id: MagicMock,
        update_status: MagicMock,
    ) -> None:
        """更新用户状态成功时应返回 200。"""
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
        update_status.return_value = True
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "u_admin_001",
            "username": "admin",
            "role": "admin",
            "status": "active",
        }
        client = TestClient(app)

        response = client.patch(
            "/api/v1/admin/users/u_user_001/status",
            json={"status": "disabled"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["user_id"], "u_user_001")
        self.assertEqual(payload["data"]["status"], "disabled")

    @patch("app.api.v1.endpoints.admin.UserRepository.find_by_user_id")
    def test_patch_admin_user_status_returns_not_found_for_missing_user(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """目标用户不存在时应返回 404。"""
        find_by_user_id.return_value = None
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "u_admin_001",
            "username": "admin",
            "role": "admin",
            "status": "active",
        }
        client = TestClient(app)

        response = client.patch(
            "/api/v1/admin/users/u_missing/status",
            json={"status": "disabled"},
        )

        self.assertEqual(response.status_code, 404)

    @patch("app.api.v1.endpoints.admin.UserRepository.find_by_user_id")
    def test_patch_admin_user_status_rejects_disabling_self(
        self,
        find_by_user_id: MagicMock,
    ) -> None:
        """管理员禁用自己时应返回 400。"""
        now = datetime.now()
        find_by_user_id.return_value = UserRecord(
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
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "u_admin_001",
            "username": "admin",
            "role": "admin",
            "status": "active",
        }
        client = TestClient(app)

        response = client.patch(
            "/api/v1/admin/users/u_admin_001/status",
            json={"status": "disabled"},
        )

        self.assertEqual(response.status_code, 400)

    @patch("app.api.v1.endpoints.admin.UserRepository.update_status")
    @patch("app.api.v1.endpoints.admin.UserRepository.count_active_admins")
    @patch("app.api.v1.endpoints.admin.UserRepository.find_by_user_id")
    def test_patch_admin_user_status_rejects_disabling_other_admin(
        self,
        find_by_user_id: MagicMock,
        count_active_admins: MagicMock,
        update_status: MagicMock,
    ) -> None:
        """禁用其他管理员账号时应返回 400。"""
        now = datetime.now()
        find_by_user_id.return_value = UserRecord(
            user_id="u_admin_002",
            username="backup-admin",
            password_hash="hashed",
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by=None,
        )
        count_active_admins.return_value = 2
        update_status.return_value = True
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "u_admin_001",
            "username": "admin",
            "role": "admin",
            "status": "active",
        }
        client = TestClient(app)

        response = client.patch(
            "/api/v1/admin/users/u_admin_002/status",
            json={"status": "disabled"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "一期不允许禁用管理员账号")

    @patch("app.api.v1.endpoints.admin.InviteCodeRepository.disable")
    def test_patch_admin_invite_disable_returns_success(
        self,
        disable_invite: MagicMock,
    ) -> None:
        """禁用邀请码成功时应返回 200。"""
        disable_invite.return_value = True
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        client = TestClient(app)

        response = client.patch("/api/v1/admin/invite-codes/invite_001/disable")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["invite_id"], "invite_001")
        self.assertEqual(payload["data"]["status"], "disabled")

    @patch("app.api.v1.endpoints.admin.InviteCodeRepository.disable")
    def test_patch_admin_invite_disable_returns_not_found(
        self,
        disable_invite: MagicMock,
    ) -> None:
        """目标邀请码不存在时应返回 404。"""
        disable_invite.return_value = False
        app = self._create_app()
        app.dependency_overrides[require_admin] = lambda: None
        client = TestClient(app)

        response = client.patch("/api/v1/admin/invite-codes/invite_missing/disable")

        self.assertEqual(response.status_code, 404)
