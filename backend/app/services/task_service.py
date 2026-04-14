"""任务服务模块。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.infra.mongo import get_files_collection, get_results_collection, get_tasks_collection
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


class TaskService:
    """任务服务（MongoDB + Celery 实现）。"""

    @staticmethod
    def create_task(task_type: TaskKind, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        """创建任务并派发到 Celery。

        函数名称: create_task
        参数说明:
        - task_type: 任务类型。
        - input_data: 输入参数。
        - params: 任务参数。
        """
        TaskService._validate_input_source(input_data=input_data)

        prefix_map = {
            "gpc_analysis": "t_gpc",
            "nmr_analysis": "t_nmr",
            "ir_analysis": "t_ir",
            "raman_analysis": "t_raman",
        }
        prefix = prefix_map.get(task_type, "t_task")
        task_id = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        now = datetime.now()

        task_doc = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "PENDING",
            "progress": 0,
            "message": "task created",
            "input": input_data,
            "params": params,
            "result_ref": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        get_tasks_collection().insert_one(task_doc)

        try:
            execute_analysis_task.apply_async(args=[task_id], queue=settings.celery_task_queue)
            get_tasks_collection().update_one(
                {"task_id": task_id},
                {"$set": {"status": "QUEUED", "progress": 5, "message": "queued", "updated_at": datetime.now()}},
            )
            return {"task_id": task_id, "task_type": task_type, "status": "QUEUED"}
        except Exception as exc:
            get_tasks_collection().update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": "FAILED",
                        "progress": 100,
                        "message": "queue dispatch failed",
                        "error": {"detail": str(exc)},
                        "updated_at": datetime.now(),
                    }
                },
            )
            return {"task_id": task_id, "task_type": task_type, "status": "FAILED"}

    @staticmethod
    def get_task_status(task_id: str) -> TaskStatusData | None:
        """获取任务状态。

        函数名称: get_task_status
        参数说明:
        - task_id: 任务ID。
        """
        task = get_tasks_collection().find_one({"task_id": task_id}, {"_id": 0})
        if not task:
            return None
        return TaskStatusData(**task)

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

        collection = get_tasks_collection()
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, {"_id": 0})
            .sort([("created_at", -1)])
            .skip((safe_page - 1) * safe_size)
            .limit(safe_size)
        )
        items = [TaskListItem(**doc) for doc in cursor]
        return TaskListData(total=total, page=safe_page, page_size=safe_size, items=items)

    @staticmethod
    def get_task_result(task_id: str) -> TaskResultData | None:
        """获取任务结果。

        函数名称: get_task_result
        参数说明:
        - task_id: 任务ID。
        """
        task = get_tasks_collection().find_one({"task_id": task_id}, {"_id": 0})
        if not task:
            return None

        status = task["status"]
        if status == "FAILED":
            err = task.get("error") or {}
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

        result_ref = task.get("result_ref")
        if not result_ref:
            return TaskResultData(task_id=task_id, status=status, result=None)

        result_doc = get_results_collection().find_one({"result_id": result_ref}, {"_id": 0})
        if not result_doc:
            return TaskResultData(task_id=task_id, status=status, result=None)

        payload = {
            "structured_data": result_doc.get("structured_data", {}),
            "text_report": result_doc.get("text_report", ""),
            "metadata": result_doc.get("metadata", {}),
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
            file_doc = get_files_collection().find_one({"file_id": file_id}, {"_id": 0})
            if not file_doc:
                raise ValueError("file_id 不存在")
            return

        input_path = input_data.get("input_path")
        if input_type in {"file_path", "folder_path"}:
            if not input_path:
                raise ValueError("input_path 不能为空")
            target_path = Path(str(input_path))
            if not target_path.exists():
                raise ValueError(f"输入路径不存在: {target_path}")
            if input_type == "folder_path" and not target_path.is_dir():
                raise ValueError(f"folder_path 必须是目录: {target_path}")
            return

        raise ValueError(f"不支持的 input_type: {input_type}")


task_service = TaskService()
