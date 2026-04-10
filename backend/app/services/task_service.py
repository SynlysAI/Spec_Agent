"""任务服务模块。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.infra.mongo import get_files_collection, get_results_collection, get_tasks_collection
from app.models.tasks import TaskKind, TaskResultData, TaskResultError, TaskStatusData
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

        prefix = "t_gpc" if task_type == "gpc_analysis" else "t_nmr"
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
            execute_analysis_task.delay(task_id)
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


task_service = TaskService()
