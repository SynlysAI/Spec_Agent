"""Celery 应用初始化模块。"""

from __future__ import annotations

import os

from celery import Celery

from app.core.config import settings

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
