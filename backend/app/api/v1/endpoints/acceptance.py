"""批量验收测试接口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.acceptance import (
    AcceptanceConfigData,
    AcceptanceRunCreateData,
    AcceptanceRunData,
    AcceptanceRunHistoryData,
    AcceptanceRunRequest,
)
from app.schemas.common import ApiResponse
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


@router.get("/runs", response_model=ApiResponse[AcceptanceRunHistoryData])
def list_acceptance_runs(limit: int = 20) -> ApiResponse[AcceptanceRunHistoryData]:
    """查询验收运行历史列表。

    Args:
        limit: 返回条数上限。
    """
    items = acceptance_service.list_runs(limit=limit)
    return ApiResponse(code=0, message="ok", data=AcceptanceRunHistoryData(total=len(items), items=items))


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


@router.get("/run/{run_id}/report")
def download_acceptance_report(run_id: str) -> FileResponse:
    """下载批量验收 Markdown 报告。

    Args:
        run_id: 批次运行 ID。
    """
    run_data = acceptance_service.get_run(run_id=run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="run not found")
    if not run_data.report_path:
        raise HTTPException(status_code=404, detail="report not found")
    report_path = Path(run_data.report_path)
    if not report_path.exists() or not report_path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(
        path=str(report_path),
        filename=f"{run_id}.md",
        media_type="text/markdown; charset=utf-8",
    )
