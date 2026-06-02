"""任务对象级权限测试。"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tasks import router as tasks_router
from app.core.auth import get_current_user
from app.schemas.task_runtime import TaskRecord
from app.schemas.tasks import TaskListData
from app.services.task_service import TaskService


def build_task_record(created_by: str | None, *, task_id: str = "t_gpc_001") -> TaskRecord:
    """构造任务记录测试桩。"""
    now = datetime.now()
    return TaskRecord(
        task_id=task_id,
        task_type="gpc_analysis",
        status="SUCCESS",
        progress=100,
        message="finished",
        input={"input_type": "file_id", "file_id": "f_001"},
        params={},
        result_ref=f"r_{task_id}",
        error=None,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


class TestTaskOwnershipService(unittest.TestCase):
    """验证任务服务的对象级权限。"""

    @patch("app.services.task_service.TaskRepository.list_paginated")
    def test_list_tasks_filters_created_by_for_normal_user(self, list_paginated: MagicMock) -> None:
        """普通用户查询任务列表时应按 created_by 过滤。"""
        list_paginated.return_value = (0, [])

        TaskService.list_tasks(
            page=1,
            page_size=20,
            current_user={"user_id": "u_user_001", "role": "user", "username": "alice", "status": "active"},
        )

        query = list_paginated.call_args.kwargs["query"]
        self.assertEqual(query["created_by"], "u_user_001")

    @patch("app.services.task_service.TaskRepository.list_paginated")
    def test_list_tasks_does_not_filter_created_by_for_admin(self, list_paginated: MagicMock) -> None:
        """管理员查询任务列表时不应附加 created_by 过滤。"""
        list_paginated.return_value = (0, [])

        TaskService.list_tasks(
            page=1,
            page_size=20,
            current_user={"user_id": "u_admin_001", "role": "admin", "username": "admin", "status": "active"},
        )

        query = list_paginated.call_args.kwargs["query"]
        self.assertNotIn("created_by", query)

    @patch("app.services.task_service.TaskRepository.find_by_task_id")
    def test_get_task_status_returns_none_for_other_user(self, find_by_task_id: MagicMock) -> None:
        """普通用户查看他人任务状态时应视为不存在。"""
        find_by_task_id.return_value = build_task_record("u_other_001")

        result = TaskService.get_task_status(
            "t_gpc_001",
            current_user={"user_id": "u_user_001", "role": "user", "username": "alice", "status": "active"},
        )

        self.assertIsNone(result)

    @patch("app.services.task_service.TaskRepository.find_by_task_id")
    def test_get_task_status_allows_admin_to_access_any_task(self, find_by_task_id: MagicMock) -> None:
        """管理员可查看任意任务状态。"""
        find_by_task_id.return_value = build_task_record("u_other_001")

        result = TaskService.get_task_status(
            "t_gpc_001",
            current_user={"user_id": "u_admin_001", "role": "admin", "username": "admin", "status": "active"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.task_id, "t_gpc_001")

    @patch("app.services.task_service.TaskRepository.find_by_task_id")
    def test_list_task_artifacts_returns_none_for_other_user(self, find_by_task_id: MagicMock) -> None:
        """普通用户查看他人任务产物时应视为不存在。"""
        find_by_task_id.return_value = build_task_record("u_other_001")

        result = TaskService.list_task_artifacts(
            "t_gpc_001",
            current_user={"user_id": "u_user_001", "role": "user", "username": "alice", "status": "active"},
        )

        self.assertIsNone(result)


class TestTaskOwnershipEndpoints(unittest.TestCase):
    """验证任务 HTTP 入口按用户上下文传递访问控制。"""

    @staticmethod
    def create_client(user_context: dict[str, str]) -> TestClient:
        """创建任务路由测试客户端。"""
        app = FastAPI()
        app.include_router(tasks_router)
        app.dependency_overrides[get_current_user] = lambda: user_context
        return TestClient(app)

    @patch("app.api.v1.endpoints.tasks.task_service.list_tasks")
    def test_list_tasks_endpoint_passes_current_user_to_service(self, list_tasks: MagicMock) -> None:
        """任务列表接口应将当前用户上下文传给服务层。"""
        list_tasks.return_value = TaskListData(total=0, page=1, page_size=20, items=[])
        client = self.create_client(
            {"user_id": "u_user_001", "role": "user", "username": "alice", "status": "active"}
        )

        response = client.get("/tasks")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_tasks.call_args.kwargs["current_user"]["user_id"], "u_user_001")

    @patch("app.api.v1.endpoints.tasks.task_service.get_task_status")
    def test_get_task_status_returns_404_when_service_denies_access(self, get_task_status: MagicMock) -> None:
        """任务详情接口在无权限时应返回 404。"""
        get_task_status.return_value = None
        client = self.create_client(
            {"user_id": "u_user_001", "role": "user", "username": "alice", "status": "active"}
        )

        response = client.get("/tasks/t_other_001")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
