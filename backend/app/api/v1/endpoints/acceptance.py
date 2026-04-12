"""批量验收测试接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.acceptance import (
    AcceptanceConfigData,
    AcceptanceRunCreateData,
    AcceptanceRunData,
    AcceptanceRunRequest,
)
from app.models.common import ApiResponse
from app.services.acceptance_service import acceptance_service

router = APIRouter(prefix="/acceptance", tags=["acceptance"])


@router.get("/config", response_model=ApiResponse[AcceptanceConfigData])
def get_acceptance_config() -> ApiResponse[AcceptanceConfigData]:
    """查询验收配置摘要。"""
    config_path, items, total_samples = acceptance_service.get_config_summary()
    data = AcceptanceConfigData(
        config_path=str(config_path),
        items=items,
        total_samples=total_samples,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/run", response_model=ApiResponse[AcceptanceRunCreateData])
def create_acceptance_run(payload: AcceptanceRunRequest) -> ApiResponse[AcceptanceRunCreateData]:
    """创建批量验收运行任务。

    Args:
        payload: 启动参数。
    """
    run_data = acceptance_service.create_run(spectrum_types=payload.spectrum_types)
    data = AcceptanceRunCreateData(run_id=run_data.run_id, status=run_data.status)
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/run/{run_id}", response_model=ApiResponse[AcceptanceRunData])
def get_acceptance_run(run_id: str) -> ApiResponse[AcceptanceRunData]:
    """查询批量验收运行状态。

    Args:
        run_id: 批次运行 ID。
    """
    run_data = acceptance_service.get_run(run_id=run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="run not found")
    return ApiResponse(code=0, message="ok", data=run_data)

