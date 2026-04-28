"""拉曼光谱仪采集工具接口。"""

from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.raman_capture import RamanCaptureRunData, RamanCaptureRunRequest
from app.services.raman_capture_service import raman_capture_service

router = APIRouter(prefix="/raman-capture", tags=["raman-capture"])


@router.post("/run", response_model=ApiResponse[RamanCaptureRunData])
def run_raman_capture(payload: RamanCaptureRunRequest) -> ApiResponse[RamanCaptureRunData]:
    """执行拉曼光谱仪批量采集。"""
    try:
        data = raman_capture_service.run_batch_capture(
            instrument_ip=settings.raman_capture_instrument_ip,
            callback_url=settings.raman_capture_callback_url,
            submit_port=settings.raman_capture_submit_port,
            result_port=settings.raman_capture_result_port,
            wavenumber_list=payload.wavenumber_list,
            power_list=payload.power_list,
            explore_time=payload.explore_time,
            integer=payload.integer,
            power_type=payload.power_type,
            grating_index=payload.grating_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.exceptions.Timeout as exc:
        raise HTTPException(status_code=504, detail="拉曼光谱仪请求超时") from exc
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"拉曼光谱仪请求失败: {exc}") from exc

    return ApiResponse(code=0, message="ok", data=data)
