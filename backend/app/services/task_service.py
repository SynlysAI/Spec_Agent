"""任务服务模块。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.logging import get_logger
from app.infra.repositories import FileRepository, ResultRepository, TaskRepository
from app.schemas.task_runtime import TaskErrorInfo, TaskRecord
from app.schemas.tasks import (
    TaskArtifactItem,
    TaskArtifactsData,
    TaskKind,
    TaskListData,
    TaskListItem,
    TaskResultData,
    TaskResultError,
    TaskStatus,
    TaskStatusData,
)
from app.worker.tasks import execute_analysis_task

logger = get_logger("spec_agent.services.task")


class TaskService:
    """任务服务（MongoDB + Celery 实现）。"""

    @staticmethod
    def create_task(
        task_type: TaskKind,
        input_data: dict[str, Any],
        params: dict[str, Any],
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """创建任务并派发到 Celery。

        Args:
            task_type: 任务类型。
            input_data: 输入参数。
            params: 任务参数。
            created_by: 任务创建人用户 ID。

        Returns:
            任务创建结果。
        """
        TaskService._validate_input_source(input_data=input_data)

        prefix_map = {
            "gpc_analysis": "t_gpc",
            "nmr_analysis": "t_nmr",
            "ir_analysis": "t_ir",
            "raman_analysis": "t_raman",
            "lcms_analysis": "t_lcms",
        }
        prefix = prefix_map.get(task_type, "t_task")
        task_id = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        now = datetime.now()

        task_record = TaskRecord(
            task_id=task_id,
            task_type=task_type,
            status="PENDING",
            progress=0,
            message="task created",
            input=input_data,
            params=params,
            result_ref=None,
            error=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        TaskRepository.create(task_record)

        try:
            execute_analysis_task.apply_async(args=[task_id], queue=settings.celery_task_queue)
            TaskRepository.update(task_id, status="QUEUED", progress=5, message="queued")
            return {"task_id": task_id, "task_type": task_type, "status": "QUEUED"}
        except Exception as exc:
            logger.error("任务 %s 派发到 Celery 失败: %s", task_id, exc)
            TaskRepository.update(
                task_id,
                status="FAILED",
                progress=100,
                message="queue dispatch failed",
                error=TaskErrorInfo(detail=str(exc)),
            )
            return {"task_id": task_id, "task_type": task_type, "status": "FAILED"}

    @staticmethod
    def get_task_status(task_id: str) -> TaskStatusData | None:
        """获取任务状态。

        函数名称: get_task_status
        参数说明:
        - task_id: 任务ID。
        """
        task_record = TaskRepository.find_by_task_id(task_id)
        if not task_record:
            return None
        return TaskStatusData(**task_record.model_dump(mode="python"))

    @staticmethod
    def list_tasks(
        page: int = 1,
        page_size: int = 20,
        status: TaskStatus | None = None,
        task_type: TaskKind | None = None,
    ) -> TaskListData:
        """分页查询任务列表。

        Args:
            page: 页码，从 1 开始。
            page_size: 每页数量。
            status: 可选任务状态过滤条件。
            task_type: 可选任务类型过滤条件。

        Returns:
            任务分页列表结果。
        """
        safe_page = max(page, 1)
        safe_size = min(max(page_size, 1), 100)
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if task_type:
            query["task_type"] = task_type

        total, task_records = TaskRepository.list_paginated(query=query, page=safe_page, page_size=safe_size)
        items = [TaskListItem(**record.model_dump(mode="python")) for record in task_records]
        return TaskListData(total=total, page=safe_page, page_size=safe_size, items=items)

    @staticmethod
    def get_task_result(task_id: str) -> TaskResultData | None:
        """获取任务结果。

        函数名称: get_task_result
        参数说明:
        - task_id: 任务ID。
        """
        task_record = TaskRepository.find_by_task_id(task_id)
        if not task_record:
            return None

        status = task_record.status
        if status == "FAILED":
            err = task_record.error.model_dump(mode="python") if task_record.error else {}
            return TaskResultData(
                task_id=task_id,
                status=status,
                error=TaskResultError(
                    error_code="50001",
                    error_message="任务执行失败",
                    error_detail=str(err.get("detail", "unknown")),
                ),
            )

        if status != "SUCCESS":
            return TaskResultData(task_id=task_id, status=status, result=None)

        result_ref = task_record.result_ref
        if not result_ref:
            return TaskResultData(task_id=task_id, status=status, result=None)

        result_record = ResultRepository.find_by_result_id(result_ref)
        if not result_record:
            return TaskResultData(task_id=task_id, status=status, result=None)

        payload = {
            "structured_data": result_record.structured_data,
            "text_report": result_record.text_report,
            "metadata": result_record.metadata,
        }
        return TaskResultData(task_id=task_id, status=status, result=payload)

    @staticmethod
    def list_task_artifacts(task_id: str) -> TaskArtifactsData:
        """查询任务输出产物列表。

        Args:
            task_id: 任务 ID。

        Returns:
            任务产物列表对象。
        """
        output_dir = settings.outputs_root / "tasks" / task_id
        if not output_dir.exists() or not output_dir.is_dir():
            return TaskArtifactsData(task_id=task_id, items=[])

        items: list[TaskArtifactItem] = []
        for file_path in sorted(output_dir.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
                file_type = "image"
            elif suffix in {".txt", ".md", ".json", ".csv"}:
                file_type = "text"
            elif suffix in {".pdf"}:
                file_type = "pdf"
            else:
                file_type = "other"

            relative_path = file_path.relative_to(settings.outputs_root).as_posix()
            items.append(
                TaskArtifactItem(
                    name=file_path.name,
                    relative_path=relative_path,
                    file_type=file_type,
                    url=f"/static/outputs/{relative_path}",
                )
            )
        return TaskArtifactsData(task_id=task_id, items=items)

    @staticmethod
    def _validate_input_source(input_data: dict[str, Any]) -> None:
        """校验输入源合法性。

        函数名称: _validate_input_source
        参数说明:
        - input_data: 输入参数对象。
        """
        input_type = input_data.get("input_type")
        if input_type == "file_id":
            file_id = input_data.get("file_id")
            file_record = FileRepository.find_by_file_id(file_id)
            if not file_record:
                logger.warning("file_id 不存在: %s", file_id)
                raise ValueError("file_id 不存在")
            return

        input_path = input_data.get("input_path")
        if input_type in {"file_path", "folder_path"}:
            if not input_path:
                logger.warning("input_path 不能为空, input_type=%s", input_type)
                raise ValueError("input_path 不能为空")
            target_path = Path(str(input_path))
            if not target_path.exists():
                logger.warning("输入路径不存在: %s", target_path)
                raise ValueError(f"输入路径不存在: {target_path}")
            if input_type == "folder_path" and not target_path.is_dir():
                logger.warning("folder_path 必须是目录: %s", target_path)
                raise ValueError(f"folder_path 必须是目录: {target_path}")
            return

        logger.warning("不支持的 input_type: %s", input_type)
        raise ValueError(f"不支持的 input_type: {input_type}")


task_service = TaskService()
