"""任务接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.common import ApiResponse
from app.models.tasks import (
    CreateGpcTaskRequest,
    CreateNmrTaskRequest,
    CreateTaskData,
    TaskResultData,
    TaskStatusData,
)
from app.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/gpc", response_model=ApiResponse[CreateTaskData])
def create_gpc_task(payload: CreateGpcTaskRequest) -> ApiResponse[CreateTaskData]:
    """创建 GPC 分析任务。

    函数名称: create_gpc_task
    参数说明:
    - payload: GPC 任务请求模型。
    """
    try:
        entity = task_service.create_task(
            task_type="gpc_analysis",
            input_data=payload.input.model_dump(),
            params=payload.params.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/nmr", response_model=ApiResponse[CreateTaskData])
def create_nmr_task(payload: CreateNmrTaskRequest) -> ApiResponse[CreateTaskData]:
    """创建 NMR 分析任务（单阶段）。

    函数名称: create_nmr_task
    参数说明:
    - payload: NMR 任务请求模型。
    """
    try:
        entity = task_service.create_task(
            task_type="nmr_analysis",
            input_data=payload.input.model_dump(),
            params=payload.params.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/{task_id}", response_model=ApiResponse[TaskStatusData])
def get_task_status(task_id: str) -> ApiResponse[TaskStatusData]:
    """查询任务状态。

    函数名称: get_task_status
    参数说明:
    - task_id: 任务ID。
    """
    data = task_service.get_task_status(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/{task_id}/result", response_model=ApiResponse[TaskResultData])
def get_task_result(task_id: str) -> ApiResponse[TaskResultData]:
    """查询任务结果。

    函数名称: get_task_result
    参数说明:
    - task_id: 任务ID。
    """
    payload = task_service.get_task_result(task_id)
    if not payload:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(code=0, message="ok", data=payload)
