"""实验室数据采集接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.common import ApiResponse
from app.schemas.lab_collect import (
    LabCollectConfigData,
    LabCollectRunCreateData,
    LabCollectRunListData,
    LabCollectRunRecord,
    LabCollectRunRequest,
    SpectrumSampleDetailData,
    SpectrumSampleListData,
    SpectrumSampleSummaryData,
)
from app.services.lab_collect_service import lab_collect_service

router = APIRouter(prefix="/lab-collect", tags=["lab-collect"])


@router.get("/config", response_model=ApiResponse[LabCollectConfigData])
def get_lab_collect_config() -> ApiResponse[LabCollectConfigData]:
    """查询实验室采集配置摘要。"""
    data = lab_collect_service.get_config_summary()
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/run", response_model=ApiResponse[LabCollectRunCreateData])
def create_lab_collect_run(payload: LabCollectRunRequest) -> ApiResponse[LabCollectRunCreateData]:
    """创建实验数据采集批次。"""
    try:
        data = lab_collect_service.create_run(
            collect_date=payload.collect_date,
            date_from=payload.date_from,
            date_to=payload.date_to,
            spectrum_types=payload.spectrum_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/runs", response_model=ApiResponse[LabCollectRunListData])
def list_lab_collect_runs(limit: int = 20) -> ApiResponse[LabCollectRunListData]:
    """查询采集批次列表。"""
    items = lab_collect_service.list_runs(limit=limit)
    return ApiResponse(code=0, message="ok", data=LabCollectRunListData(total=len(items), items=items))


@router.get("/run/{run_id}", response_model=ApiResponse[LabCollectRunRecord])
def get_lab_collect_run(run_id: str) -> ApiResponse[LabCollectRunRecord]:
    """查询采集批次详情。"""
    data = lab_collect_service.get_run(run_id=run_id)
    if not data:
        raise HTTPException(status_code=404, detail="采集批次不存在")
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/samples", response_model=ApiResponse[SpectrumSampleListData])
def list_spectrum_samples(
    page: int = 1,
    page_size: int = 20,
    spectrum_type: str | None = None,
    source_date: str | None = None,
    sample_name: str | None = None,
) -> ApiResponse[SpectrumSampleListData]:
    """分页查询实验样本主档。"""
    data = lab_collect_service.list_samples(
        page=page,
        page_size=page_size,
        spectrum_type=spectrum_type,
        source_date=source_date,
        sample_name=sample_name,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/samples/summary", response_model=ApiResponse[SpectrumSampleSummaryData])
def get_spectrum_sample_summary() -> ApiResponse[SpectrumSampleSummaryData]:
    """查询实验样本汇总。"""
    data = lab_collect_service.get_sample_summary()
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/samples/{sample_id}", response_model=ApiResponse[SpectrumSampleDetailData])
def get_spectrum_sample_detail(sample_id: str) -> ApiResponse[SpectrumSampleDetailData]:
    """查询实验样本详情。"""
    data = lab_collect_service.get_sample_detail(sample_id=sample_id)
    if not data:
        raise HTTPException(status_code=404, detail="样本不存在")
    return ApiResponse(code=0, message="ok", data=data)
