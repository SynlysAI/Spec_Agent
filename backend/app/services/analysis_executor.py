"""同步分析执行器兼容入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas.tasks import TaskKind
from app.services.task_executors import _to_basic, list_output_artifacts, task_executor_registry


def execute_analysis_sync(
    task_type: TaskKind,
    input_data: dict[str, Any],
    params: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """同步执行分析任务。"""
    return task_executor_registry.execute(
        task_type=task_type,
        input_data=input_data,
        params=params,
        output_dir=output_dir,
    )


__all__ = ["_to_basic", "execute_analysis_sync", "list_output_artifacts"]
