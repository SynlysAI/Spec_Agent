"""健康检查接口。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from kombu import Connection

from app.core.config import settings
from app.infra.mongo import get_mongo_client
from app.models.common import ApiResponse

router = APIRouter(tags=["health"])


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

    payload = {"api": "up", "mongodb": mongodb_status, "rabbitmq": rabbitmq_status, "worker": "up", "time": datetime.now().isoformat()}
    return ApiResponse(code=0, message="ok", data=payload)
