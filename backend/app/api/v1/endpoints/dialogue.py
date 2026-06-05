"""问答对话接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.dialogue import (
    DialogueAnalysisTypeData,
    DialogueAnalysisTypeItem,
    DialogueChatData,
    DialogueChatRequest,
    DialogueModelItem,
    DialogueModelListData,
    DialogueReportListData,
)
from app.services.dialogue_model_service import DialogueModelUnavailableError
from app.services.dialogue_service import dialogue_service

router = APIRouter(prefix="/dialogue", tags=["dialogue"])


@router.get("/analysis-types", response_model=ApiResponse[DialogueAnalysisTypeData])
def list_analysis_types(
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[DialogueAnalysisTypeData]:
    """查询问答支持的分析类型列表。

    Args:
        current_user: 当前登录用户上下文。
    """
    items = [DialogueAnalysisTypeItem(**item) for item in dialogue_service.list_analysis_types(current_user=current_user)]
    return ApiResponse(code=0, message="ok", data=DialogueAnalysisTypeData(items=items))


@router.get("/models", response_model=ApiResponse[DialogueModelListData])
def list_models() -> ApiResponse[DialogueModelListData]:
    """查询问答可选模型列表。"""
    items = [DialogueModelItem(**item) for item in dialogue_service.list_models()]
    data = DialogueModelListData(
        default_model_key=dialogue_service.get_default_model_key(),
        items=items,
    )
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/reports", response_model=ApiResponse[DialogueReportListData])
def list_reports(
    analysis_type: str,
    limit: int = 20,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[DialogueReportListData]:
    """按分析类型查询历史报告列表。

    Args:
        analysis_type: 分析类型编码。
        limit: 返回上限。
        current_user: 当前登录用户上下文。
    """
    items = dialogue_service.list_reports(
        analysis_type=analysis_type,
        limit=limit,
        current_user=current_user,
    )
    return ApiResponse(code=0, message="ok", data=DialogueReportListData(analysis_type=analysis_type, items=items))


@router.post("/chat", response_model=ApiResponse[DialogueChatData])
def chat(
    payload: DialogueChatRequest,
    current_user: dict[str, str] | None = Depends(get_current_user),
) -> ApiResponse[DialogueChatData]:
    """执行问答请求。

    Args:
        payload: 问答请求参数。
        current_user: 当前登录用户上下文。
    """
    history = [item.model_dump() for item in payload.history]
    try:
        answer, used_excerpt = dialogue_service.generate_answer(
            model_key=payload.model_key,
            question=payload.question,
            analysis_type=payload.analysis_type,
            report_id=payload.report_id,
            history=history,
            system_prompt=payload.system_prompt,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DialogueModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail="该模型暂不可用") from exc

    data = DialogueChatData(
        answer=answer,
        report_id=payload.report_id,
        used_excerpt=used_excerpt,
    )
    return ApiResponse(code=0, message="ok", data=data)
