"""异步任务执行模块。"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.infra.repositories import ResultRepository, TaskRepository
from app.schemas.task_runtime import ResultRecord, TaskErrorInfo
from app.services.analysis_executor import execute_analysis_sync
from app.worker.celery_app import celery_app

logger = get_logger("spec_agent.worker.tasks")


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
        logger.warning("任务 %s 不存在，跳过执行", task_id)
        return

    try:
        _update_task(task_id, status="RUNNING", progress=20, message="running")
        logger.info("任务 %s 开始执行，类型: %s", task_id, task.task_type)
        task_type = task.task_type
        input_data = task.input
        params = task.params
        _update_task(task_id, progress=45, message="preparing")
        logger.info("任务 %s 开始调用分析引擎，输出目录: %s", task_id, settings.outputs_root / "tasks" / task_id)
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
        logger.info("任务 %s 结果已保存，result_id: %s", task_id, result_id)
        _update_task(task_id, status="SUCCESS", progress=100, message="finished", result_ref=result_id, error=None)
        logger.info("任务 %s 执行完成", task_id)
    except Exception as exc:
        logger.error("任务 %s 执行失败: %s", task_id, exc)
        _update_task(task_id, status="FAILED", progress=100, message="failed", error=TaskErrorInfo(detail=str(exc)))


@celery_app.task(name="app.worker.tasks.execute_acceptance_run_task")
def execute_acceptance_run_task(run_id: str) -> None:
    """执行谱解批量验收批次。

    Args:
        run_id: 批量验收运行 ID。
    """
    from app.services.acceptance_service import acceptance_service

    logger.info("开始执行谱解批量验收批次，run_id: %s", run_id)
    acceptance_service.run_batch(run_id=run_id)
    logger.info("谱解批量验收批次执行完成，run_id: %s", run_id)


@celery_app.task(name="app.worker.tasks.execute_consistency_run_task")
def execute_consistency_run_task(run_id: str) -> None:
    """执行设备重复性评测批次。

    Args:
        run_id: 一致性评测运行 ID。
    """
    from app.services.consistency_service import consistency_service

    logger.info("开始执行设备重复性评测批次，run_id: %s", run_id)
    consistency_service.run_batch(run_id=run_id)
    logger.info("设备重复性评测批次执行完成，run_id: %s", run_id)


@celery_app.task(name="app.worker.tasks.execute_lab_collect_run_task")
def execute_lab_collect_run_task(run_id: str) -> None:
    """执行实验室数据采集批次。

    Args:
        run_id: 采集批次 ID。
    """
    from app.services.lab_collect_service import lab_collect_service

    logger.info("开始执行实验室数据采集批次，run_id: %s", run_id)
    lab_collect_service.run_collect(run_id=run_id)
    logger.info("实验室数据采集批次执行完成，run_id: %s", run_id)
