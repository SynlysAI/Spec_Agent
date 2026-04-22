"""Celery 应用初始化模块。"""

from __future__ import annotations

import os
from logging import INFO

from celery import Celery
from celery.signals import after_setup_logger
from celery.signals import task_failure
from celery.signals import task_prerun
from celery.signals import task_success

from app.core.config import settings
from app.core.logging import configure_worker_logging
from app.core.logging import get_logger

celery_app = Celery(
    "spec_agent_worker",
    broker=settings.rabbitmq_broker_url,
    backend="rpc://",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_default_queue=settings.celery_task_queue,
)

# Windows 下使用 prefork 容易出现子进程任务跟踪异常，默认切换为 solo 池。
if os.name == "nt":
    celery_app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
    )

celery_app.autodiscover_tasks(["app.worker"])

WORKER_LOGGER = configure_worker_logging(level=INFO)


@after_setup_logger.connect
def on_after_setup_logger(*args, **kwargs) -> None:
    """在 Celery 启动日志阶段确保项目日志已初始化。"""
    configure_worker_logging(level=INFO)


@task_prerun.connect
def on_task_prerun(task_id: str | None = None, task=None, args=None, kwargs=None, **extras) -> None:
    """记录任务开始日志。"""
    logger = get_logger("spec_agent.worker")
    task_name = task.name if task else "unknown"
    logger.info(
        f"task started: {task_name}",
        extra={"request_id": task_id or "-"},
    )


@task_success.connect
def on_task_success(result=None, sender=None, **kwargs) -> None:
    """记录任务成功日志。"""
    logger = get_logger("spec_agent.worker")
    task_name = sender.name if sender else "unknown"
    request_id = getattr(getattr(sender, "request", None), "id", "-")
    logger.info(
        f"task succeeded: {task_name}",
        extra={"request_id": request_id},
    )


@task_failure.connect
def on_task_failure(task_id=None, exception=None, sender=None, **kwargs) -> None:
    """记录任务失败日志。"""
    logger = get_logger("spec_agent.worker")
    task_name = sender.name if sender else "unknown"
    logger.error(
        f"task failed: {task_name} error={exception}",
        extra={"request_id": task_id or "-"},
    )
