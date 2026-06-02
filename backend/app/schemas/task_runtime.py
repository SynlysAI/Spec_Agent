"""任务运行态领域模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.tasks import TaskKind, TaskStatus


class TaskErrorInfo(BaseModel):
    """任务执行错误对象。"""

    detail: str = Field(description="错误详情")


class TaskRecord(BaseModel):
    """任务运行态实体。"""

    task_id: str
    task_type: TaskKind
    status: TaskStatus
    progress: int
    message: str
    input: dict[str, Any]
    params: dict[str, Any]
    result_ref: str | None = None
    error: TaskErrorInfo | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ResultRecord(BaseModel):
    """任务结果实体。"""

    result_id: str
    task_id: str
    task_type: TaskKind
    structured_data: dict[str, Any]
    text_report: str
    metadata: dict[str, Any]
    created_at: datetime


class FileRecord(BaseModel):
    """文件元数据实体。"""

    file_id: str
    file_name: str
    file_size: int
    file_ext: str
    storage_path: str
    sha256: str
    created_by: str | None = None
    created_at: datetime | None = None
