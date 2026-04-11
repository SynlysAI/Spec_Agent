"""任务接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.common import ApiResponse
from app.models.tasks import (
    TaskArtifactsData,
    CreateGpcTaskRequest,
    CreateIrRamanTaskRequest,
    CreateNmrTaskRequest,
    CreateTaskData,
    TaskKind,
    TaskListData,
    TaskStatus,
    TaskResultData,
    TaskStatusData,
)
from app.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=ApiResponse[TaskListData])
def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: TaskStatus | None = None,
    task_type: TaskKind | None = None,
) -> ApiResponse[TaskListData]:
    """分页查询任务列表。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页数量，最大 100。
        status: 可选任务状态过滤条件。
        task_type: 可选任务类型过滤条件。

    Returns:
        任务分页列表响应。
    """
    data = task_service.list_tasks(page=page, page_size=page_size, status=status, task_type=task_type)
    return ApiResponse(code=0, message="ok", data=data)


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


@router.post("/ir", response_model=ApiResponse[CreateTaskData])
def create_ir_task(payload: CreateIrRamanTaskRequest) -> ApiResponse[CreateTaskData]:
    """创建 IR 分析任务。

    函数名称: create_ir_task
    参数说明:
    - payload: IR 任务请求模型。
    """
    try:
        params = payload.params.model_dump()
        params["spectype"] = "ir"
        entity = task_service.create_task(
            task_type="ir_analysis",
            input_data=payload.input.model_dump(),
            params=params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/raman", response_model=ApiResponse[CreateTaskData])
def create_raman_task(payload: CreateIrRamanTaskRequest) -> ApiResponse[CreateTaskData]:
    """创建 Raman 分析任务。

    函数名称: create_raman_task
    参数说明:
    - payload: Raman 任务请求模型。
    """
    try:
        params = payload.params.model_dump()
        params["spectype"] = "raman"
        entity = task_service.create_task(
            task_type="raman_analysis",
            input_data=payload.input.model_dump(),
            params=params,
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


@router.get("/{task_id}/artifacts", response_model=ApiResponse[TaskArtifactsData])
def get_task_artifacts(task_id: str) -> ApiResponse[TaskArtifactsData]:
    """查询任务输出产物列表。

    Args:
        task_id: 任务 ID。

    Returns:
        任务产物列表响应。
    """
    data = task_service.list_task_artifacts(task_id)
    return ApiResponse(code=0, message="ok", data=data)
