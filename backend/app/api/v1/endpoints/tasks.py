"""任务接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.tasks import (
    TaskArtifactsData,
    CreateGpcTaskRequest,
    CreateIrRamanTaskRequest,
    CreateLcmsTaskRequest,
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
logger = get_logger("spec_agent.api.tasks")


def _ensure_uploaded_file_input(input_data: dict[str, object]) -> None:
    """要求用户任务提交只能使用上传文件引用。

    Args:
        input_data: 任务输入参数。

    Raises:
        HTTPException: 当输入类型不是 `file_id` 时抛出。
    """
    if input_data.get("input_type") != "file_id":
        raise HTTPException(status_code=400, detail="当前版本仅支持上传文件方式提交任务")


@router.get("", response_model=ApiResponse[TaskListData])
def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: TaskStatus | None = None,
    task_type: TaskKind | None = None,
    current_user: dict[str, str] | None = Depends(get_current_user),
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
    data = task_service.list_tasks(
        page=page,
        page_size=page_size,
        status=status,
        task_type=task_type,
        current_user=current_user,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/gpc", response_model=ApiResponse[CreateTaskData])
def create_gpc_task(
    payload: CreateGpcTaskRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[CreateTaskData]:
    """创建 GPC 分析任务。

    Args:
        payload: GPC 任务请求模型。
        current_user: 当前登录用户上下文。

    Returns:
        任务创建响应。
    """
    _ensure_uploaded_file_input(payload.input.model_dump())
    try:
        entity = task_service.create_task(
            task_type="gpc_analysis",
            input_data=payload.input.model_dump(),
            params=payload.params.model_dump(),
            created_by=current_user["user_id"] if current_user else None,
        )
    except ValueError as exc:
        logger.warning("创建 GPC 任务参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/nmr", response_model=ApiResponse[CreateTaskData])
def create_nmr_task(
    payload: CreateNmrTaskRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[CreateTaskData]:
    """创建 NMR 分析任务（单阶段）。

    Args:
        payload: NMR 任务请求模型。
        current_user: 当前登录用户上下文。

    Returns:
        任务创建响应。
    """
    _ensure_uploaded_file_input(payload.input.model_dump())
    try:
        entity = task_service.create_task(
            task_type="nmr_analysis",
            input_data=payload.input.model_dump(),
            params=payload.params.model_dump(),
            created_by=current_user["user_id"] if current_user else None,
        )
    except ValueError as exc:
        logger.warning("创建 NMR 任务参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/ir", response_model=ApiResponse[CreateTaskData])
def create_ir_task(
    payload: CreateIrRamanTaskRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[CreateTaskData]:
    """创建 IR 分析任务。

    Args:
        payload: IR 任务请求模型。
        current_user: 当前登录用户上下文。

    Returns:
        任务创建响应。
    """
    _ensure_uploaded_file_input(payload.input.model_dump())
    try:
        params = payload.params.model_dump()
        params["spectype"] = "ir"
        entity = task_service.create_task(
            task_type="ir_analysis",
            input_data=payload.input.model_dump(),
            params=params,
            created_by=current_user["user_id"] if current_user else None,
        )
    except ValueError as exc:
        logger.warning("创建 IR 任务参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/raman", response_model=ApiResponse[CreateTaskData])
def create_raman_task(
    payload: CreateIrRamanTaskRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[CreateTaskData]:
    """创建 Raman 分析任务。

    Args:
        payload: Raman 任务请求模型。
        current_user: 当前登录用户上下文。

    Returns:
        任务创建响应。
    """
    _ensure_uploaded_file_input(payload.input.model_dump())
    try:
        params = payload.params.model_dump()
        params["spectype"] = "raman"
        entity = task_service.create_task(
            task_type="raman_analysis",
            input_data=payload.input.model_dump(),
            params=params,
            created_by=current_user["user_id"] if current_user else None,
        )
    except ValueError as exc:
        logger.warning("创建 Raman 任务参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/lcms", response_model=ApiResponse[CreateTaskData])
def create_lcms_task(
    payload: CreateLcmsTaskRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[CreateTaskData]:
    """创建 LCMS 分析任务。

    Args:
        payload: LCMS 任务请求模型。
        current_user: 当前登录用户上下文。

    Returns:
        任务创建响应。
    """
    _ensure_uploaded_file_input(payload.input.model_dump())
    try:
        entity = task_service.create_task(
            task_type="lcms_analysis",
            input_data=payload.input.model_dump(),
            params=payload.params.model_dump(),
            created_by=current_user["user_id"] if current_user else None,
        )
    except ValueError as exc:
        logger.warning("创建 LCMS 任务参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = CreateTaskData(task_id=entity["task_id"], task_type=entity["task_type"], status=entity["status"])
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/{task_id}", response_model=ApiResponse[TaskStatusData])
def get_task_status(task_id: str, current_user: dict[str, str] | None = Depends(get_current_user)) -> ApiResponse[TaskStatusData]:
    """查询任务状态。

    函数名称: get_task_status
    参数说明:
    - task_id: 任务ID。
    """
    data = task_service.get_task_status(task_id, current_user=current_user)
    if not data:
        logger.warning("查询任务状态失败, task_id 不存在: %s", task_id)
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/{task_id}/result", response_model=ApiResponse[TaskResultData])
def get_task_result(task_id: str, current_user: dict[str, str] | None = Depends(get_current_user)) -> ApiResponse[TaskResultData]:
    """查询任务结果。

    函数名称: get_task_result
    参数说明:
    - task_id: 任务ID。
    """
    payload = task_service.get_task_result(task_id, current_user=current_user)
    if not payload:
        logger.warning("查询任务结果失败, task_id 不存在: %s", task_id)
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(code=0, message="ok", data=payload)


@router.get("/{task_id}/artifacts", response_model=ApiResponse[TaskArtifactsData])
def get_task_artifacts(
    task_id: str,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[TaskArtifactsData]:
    """查询任务输出产物列表。

    Args:
        task_id: 任务 ID。

    Returns:
        任务产物列表响应。
    """
    data = task_service.list_task_artifacts(task_id, current_user=current_user)
    if not data:
        logger.warning("查询任务产物失败, task_id 不存在或无权限: %s", task_id)
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(code=0, message="ok", data=data)
