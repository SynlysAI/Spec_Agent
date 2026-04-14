"""问答对话接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.dialogue import (
    DialogueAnalysisTypeData,
    DialogueAnalysisTypeItem,
    DialogueChatData,
    DialogueChatRequest,
    DialogueReportListData,
)
from app.services.dialogue_service import dialogue_service

router = APIRouter(prefix="/dialogue", tags=["dialogue"])


@router.get("/analysis-types", response_model=ApiResponse[DialogueAnalysisTypeData])
def list_analysis_types() -> ApiResponse[DialogueAnalysisTypeData]:
    """查询问答支持的分析类型列表。"""
    items = [DialogueAnalysisTypeItem(**item) for item in dialogue_service.list_analysis_types()]
    return ApiResponse(code=0, message="ok", data=DialogueAnalysisTypeData(items=items))


@router.get("/reports", response_model=ApiResponse[DialogueReportListData])
def list_reports(analysis_type: str, limit: int = 20) -> ApiResponse[DialogueReportListData]:
    """按分析类型查询历史报告列表。

    Args:
        analysis_type: 分析类型编码。
        limit: 返回上限。
    """
    items = dialogue_service.list_reports(analysis_type=analysis_type, limit=limit)
    return ApiResponse(code=0, message="ok", data=DialogueReportListData(analysis_type=analysis_type, items=items))


@router.post("/chat", response_model=ApiResponse[DialogueChatData])
def chat(payload: DialogueChatRequest) -> ApiResponse[DialogueChatData]:
    """执行问答请求。

    Args:
        payload: 问答请求参数。
    """
    history = [item.model_dump() for item in payload.history]
    answer, used_excerpt = dialogue_service.generate_answer(
        question=payload.question,
        analysis_type=payload.analysis_type,
        report_id=payload.report_id,
        history=history,
        system_prompt=payload.system_prompt,
    )
    data = DialogueChatData(
        answer=answer,
        report_id=payload.report_id,
        used_excerpt=used_excerpt,
    )
    return ApiResponse(code=0, message="ok", data=data)
