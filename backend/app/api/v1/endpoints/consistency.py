"""设备重复性评测接口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.consistency import (
    ConsistencyConfigData,
    ConsistencyRunCreateData,
    ConsistencyRunData,
    ConsistencyRunHistoryData,
    ConsistencyRunRequest,
)
from app.services.consistency_service import consistency_service

logger = get_logger("spec_agent.api.consistency")

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get("/config", response_model=ApiResponse[ConsistencyConfigData])
def get_consistency_config() -> ApiResponse[ConsistencyConfigData]:
    """查询一致性评测配置摘要。"""
    config_path, items, total_devices = consistency_service.get_config_summary()
    data = ConsistencyConfigData(
        config_path=str(config_path),
        items=items,
        total_devices=total_devices,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/run", response_model=ApiResponse[ConsistencyRunCreateData])
def create_consistency_run(payload: ConsistencyRunRequest) -> ApiResponse[ConsistencyRunCreateData]:
    """创建一致性评测运行任务。

    Args:
        payload: 启动参数。
    """
    run_data = consistency_service.create_run(device_types=payload.device_types)
    data = ConsistencyRunCreateData(run_id=run_data.run_id, status=run_data.status)
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/runs", response_model=ApiResponse[ConsistencyRunHistoryData])
def list_consistency_runs(limit: int = 20) -> ApiResponse[ConsistencyRunHistoryData]:
    """查询一致性评测历史列表。

    Args:
        limit: 返回条数上限。
    """
    items = consistency_service.list_runs(limit=limit)
    return ApiResponse(code=0, message="ok", data=ConsistencyRunHistoryData(total=len(items), items=items))


@router.get("/run/{run_id}", response_model=ApiResponse[ConsistencyRunData])
def get_consistency_run(run_id: str) -> ApiResponse[ConsistencyRunData]:
    """查询一致性评测运行状态。

    Args:
        run_id: 批次运行 ID。
    """
    run_data = consistency_service.get_run(run_id=run_id)
    if not run_data:
        logger.warning("查询一致性评测运行失败: run_id=%s 不存在", run_id)
        raise HTTPException(status_code=404, detail="run not found")
    return ApiResponse(code=0, message="ok", data=run_data)


@router.get("/run/{run_id}/report")
def download_consistency_report(run_id: str) -> FileResponse:
    """下载一致性评测 Markdown 报告。

    Args:
        run_id: 批次运行 ID。
    """
    run_data = consistency_service.get_run(run_id=run_id)
    if not run_data:
        logger.warning("下载一致性评测报告失败: run_id=%s 不存在", run_id)
        raise HTTPException(status_code=404, detail="run not found")
    if not run_data.report_path:
        logger.warning("下载一致性评测报告失败: run_id=%s 无报告路径", run_id)
        raise HTTPException(status_code=404, detail="report not found")
    report_path = Path(run_data.report_path)
    if not report_path.exists() or not report_path.is_file():
        logger.warning("下载一致性评测报告失败: 报告文件不存在, path=%s", run_data.report_path)
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(
        path=str(report_path),
        filename=f"{run_id}.md",
        media_type="text/markdown; charset=utf-8",
    )
