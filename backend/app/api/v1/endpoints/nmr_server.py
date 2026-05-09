"""NMRServer 接口。"""

from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.nmr_server import (
    NmrServerForwardRequest,
    NmrServerResultData,
    NmrServerReverseRequest,
    NmrServerSearchRequest,
)
from app.services.nmr_server_service import (
    NmrServerBusinessError,
    NmrServerProtocolError,
    nmr_server_service,
)

router = APIRouter(prefix="/nmrserver", tags=["nmrserver"])
logger = get_logger("spec_agent.api.nmrserver")


@router.post("/forward", response_model=ApiResponse[NmrServerResultData])
def nmrserver_forward(payload: NmrServerForwardRequest) -> ApiResponse[NmrServerResultData]:
    """NMRServer 正向预测接口。"""
    try:
        items = nmr_server_service.forward_predict(smiles_input=payload.smiles_input)
    except ValueError as exc:
        logger.warning("NMRServer 正向预测参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.exceptions.Timeout as exc:
        logger.error("NMRServer 正向预测请求超时: %s", exc)
        raise HTTPException(status_code=504, detail="NMRServer 请求超时") from exc
    except requests.exceptions.RequestException as exc:
        logger.error("NMRServer 正向预测请求失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"NMRServer 请求失败: {exc}") from exc
    except (NmrServerBusinessError, NmrServerProtocolError) as exc:
        logger.error("NMRServer 正向预测业务异常: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ApiResponse(code=0, message="ok", data=NmrServerResultData(items=items))


@router.post("/reverse", response_model=ApiResponse[NmrServerResultData])
def nmrserver_reverse(payload: NmrServerReverseRequest) -> ApiResponse[NmrServerResultData]:
    """NMRServer 反向预测接口。"""
    try:
        items = nmr_server_service.reverse_predict(
            h_shifts_input=payload.h_shifts_input,
            h_split_input=payload.h_split_input,
            c_shifts_input=payload.c_shifts_input,
            formula=payload.formula,
            allowed_elements=payload.allowed_elements,
            candidates=payload.candidates,
        )
    except ValueError as exc:
        logger.warning("NMRServer 反向预测参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.exceptions.Timeout as exc:
        logger.error("NMRServer 反向预测请求超时: %s", exc)
        raise HTTPException(status_code=504, detail="NMRServer 请求超时") from exc
    except requests.exceptions.RequestException as exc:
        logger.error("NMRServer 反向预测请求失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"NMRServer 请求失败: {exc}") from exc
    except (NmrServerBusinessError, NmrServerProtocolError) as exc:
        logger.error("NMRServer 反向预测业务异常: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ApiResponse(code=0, message="ok", data=NmrServerResultData(items=items))


@router.post("/search", response_model=ApiResponse[NmrServerResultData])
def nmrserver_search(payload: NmrServerSearchRequest) -> ApiResponse[NmrServerResultData]:
    """NMRServer 数据库搜索接口。"""
    try:
        items = nmr_server_service.database_search(
            h_shifts_input=payload.h_shifts_input,
            h_split_input=payload.h_split_input,
            c_shifts_input=payload.c_shifts_input,
            num_search=payload.num_search,
            topk=payload.topk,
            allowed_elements=payload.allowed_elements,
        )
    except ValueError as exc:
        logger.warning("NMRServer 数据库搜索参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.exceptions.Timeout as exc:
        logger.error("NMRServer 数据库搜索请求超时: %s", exc)
        raise HTTPException(status_code=504, detail="NMRServer 请求超时") from exc
    except requests.exceptions.RequestException as exc:
        logger.error("NMRServer 数据库搜索请求失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"NMRServer 请求失败: {exc}") from exc
    except (NmrServerBusinessError, NmrServerProtocolError) as exc:
        logger.error("NMRServer 数据库搜索业务异常: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ApiResponse(code=0, message="ok", data=NmrServerResultData(items=items))
