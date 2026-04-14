"""健康检查接口。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from kombu import Connection

from app.core.config import settings
from app.infra.mongo import get_mongo_client
from app.schemas.common import ApiResponse
from app.worker.celery_app import celery_app

router = APIRouter(tags=["health"])


def _check_worker_status() -> str:
    """探测 Celery worker 是否在线。"""
    try:
        inspector = celery_app.control.inspect(timeout=3)
        ping_result = inspector.ping()
        if ping_result:
            return "up"

        stats_result = inspector.stats()
        return "up" if stats_result else "down"
    except Exception:
        return "down"


@router.get("/health", response_model=ApiResponse[dict])
def health_check() -> ApiResponse[dict]:
    """服务健康检查接口。

    函数名称: health_check
    参数说明:
    - 无。
    """
    mongodb_status = "down"
    rabbitmq_status = "down"
    try:
        get_mongo_client().admin.command("ping")
        mongodb_status = "up"
    except Exception:
        mongodb_status = "down"

    try:
        with Connection(settings.rabbitmq_broker_url, connect_timeout=3) as conn:
            conn.connect()
        rabbitmq_status = "up"
    except Exception:
        rabbitmq_status = "down"

    payload = {
        "api": "up",
        "mongodb": mongodb_status,
        "rabbitmq": rabbitmq_status,
        "worker": _check_worker_status(),
        "time": datetime.now().isoformat(),
    }
    return ApiResponse(code=0, message="ok", data=payload)
