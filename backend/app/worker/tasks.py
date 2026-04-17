"""异步任务执行模块。"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.infra.repositories import ResultRepository, TaskRepository
from app.schemas.task_runtime import ResultRecord, TaskErrorInfo
from app.services.analysis_executor import execute_analysis_sync
from app.worker.celery_app import celery_app


def _update_task(task_id: str, **kwargs: Any) -> None:
    """更新任务记录。

    Args:
        task_id: 任务 ID。
        **kwargs: 需要更新的任务字段。
    """
    updates = dict(kwargs)
    TaskRepository.update(task_id, **updates)


@celery_app.task(name="app.worker.tasks.execute_analysis_task")
def execute_analysis_task(task_id: str) -> None:
    """执行谱图分析任务。

    Args:
        task_id: 任务 ID。
    """
    task = TaskRepository.find_by_task_id(task_id)
    if not task:
        return

    try:
        _update_task(task_id, status="RUNNING", progress=20, message="running")
        task_type = task.task_type
        input_data = task.input
        params = task.params
        _update_task(task_id, progress=45, message="preparing")
        result_payload = execute_analysis_sync(
            task_type=task_type,
            input_data=input_data,
            params=params,
            output_dir=settings.outputs_root / "tasks" / task_id,
        )

        _update_task(task_id, progress=90, message="saving result")
        result_id = f"r_{task_id}"
        ResultRepository.save(
            ResultRecord(
                result_id=result_id,
                task_id=task_id,
                task_type=task_type,
                structured_data=result_payload.get("structured_data", {}),
                text_report=result_payload.get("text_report", ""),
                metadata=result_payload.get("metadata", {}),
                created_at=task.updated_at,
            )
        )
        _update_task(task_id, status="SUCCESS", progress=100, message="finished", result_ref=result_id, error=None)
    except Exception as exc:
        _update_task(task_id, status="FAILED", progress=100, message="failed", error=TaskErrorInfo(detail=str(exc)))


@celery_app.task(name="app.worker.tasks.execute_acceptance_run_task")
def execute_acceptance_run_task(run_id: str) -> None:
    """执行批量验收批次。

    Args:
        run_id: 批量验收运行 ID。
    """
    from app.services.acceptance_service import acceptance_service

    acceptance_service.run_batch(run_id=run_id)
