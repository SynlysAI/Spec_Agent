"""异步任务执行模块。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import settings
from app.infra.mongo import get_results_collection, get_tasks_collection
from app.services.analysis_executor import _to_basic, execute_analysis_sync
from app.worker.celery_app import celery_app


def _update_task(task_id: str, **kwargs: Any) -> None:
    """更新任务记录。

    Args:
        task_id: 任务 ID。
        **kwargs: 需要更新的任务字段。
    """
    updates = dict(kwargs)
    updates["updated_at"] = datetime.now()
    get_tasks_collection().update_one({"task_id": task_id}, {"$set": updates})


@celery_app.task(name="app.worker.tasks.execute_analysis_task")
def execute_analysis_task(task_id: str) -> None:
    """执行谱图分析任务。

    Args:
        task_id: 任务 ID。
    """
    tasks = get_tasks_collection()
    results = get_results_collection()
    task = tasks.find_one({"task_id": task_id})
    if not task:
        return

    try:
        _update_task(task_id, status="RUNNING", progress=20, message="running")
        task_type = task.get("task_type", "unknown")
        input_data = task.get("input", {})
        params = task.get("params", {})
        _update_task(task_id, progress=45, message="preparing")
        result_payload = execute_analysis_sync(
            task_type=task_type,
            input_data=input_data,
            params=params,
            output_dir=settings.outputs_root / "tasks" / task_id,
        )

        _update_task(task_id, progress=90, message="saving result")
        result_id = f"r_{task_id}"
        results.update_one(
            {"result_id": result_id},
            {
                "$set": {
                    "result_id": result_id,
                    "task_id": task_id,
                    "task_type": task_type,
                    "structured_data": result_payload.get("structured_data", {}),
                    "text_report": result_payload.get("text_report", ""),
                    "metadata": result_payload.get("metadata", {}),
                    "created_at": datetime.now(),
                }
            },
            upsert=True,
        )
        _update_task(task_id, status="SUCCESS", progress=100, message="finished", result_ref=result_id, error=None)
    except Exception as exc:
        _update_task(task_id, status="FAILED", progress=100, message="failed", error={"detail": str(exc)})
