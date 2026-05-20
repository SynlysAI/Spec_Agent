"""LCMS 数据转化工具接口。"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.lcms_convert import LcmsConvertResultData
from app.services.lcms_convert_service import lcms_convert_service


router = APIRouter(prefix="/tools/lcms-convert", tags=["lcms-convert"])
logger = get_logger("spec_agent.api.lcms_convert")


@router.post("/run", response_model=ApiResponse[LcmsConvertResultData])
def run_lcms_convert(file: UploadFile = File(...)) -> ApiResponse[LcmsConvertResultData]:
    """执行 LCMS 数据目录转化。"""
    file_name = str(file.filename or "").strip()
    if not file_name:
        logger.warning("LCMS 数据转化上传文件名为空")
        raise HTTPException(status_code=400, detail="上传文件名不能为空。")
    if not file_name.lower().endswith(".zip"):
        logger.warning("LCMS 数据转化上传文件类型错误: %s", file_name)
        raise HTTPException(status_code=400, detail="请上传浏览器自动打包后的 zip 文件。")

    zip_bytes = file.file.read()
    if not zip_bytes:
        logger.warning("LCMS 数据转化上传文件为空: %s", file_name)
        raise HTTPException(status_code=400, detail="上传文件内容为空。")

    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(zip_bytes) > max_size:
        logger.warning("LCMS 数据转化上传文件过大: %s size=%s", file_name, len(zip_bytes))
        raise HTTPException(status_code=400, detail=f"上传文件大小超过限制：{settings.max_upload_size_mb}MB")

    try:
        data = lcms_convert_service.run_from_zip(zip_bytes=zip_bytes, upload_name=file_name)
    except ValueError as exc:
        logger.warning("LCMS 数据转化参数或数据异常: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("LCMS 数据转化运行失败: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LCMS 数据转化出现未处理异常")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ApiResponse(code=0, message="ok", data=data)


@router.get("/download/{job_id}")
def download_lcms_convert_csv(job_id: str) -> FileResponse:
    """下载 LCMS 数据转化结果 CSV。"""
    try:
        csv_path = lcms_convert_service.resolve_download_file(job_id=job_id)
    except FileNotFoundError as exc:
        logger.warning("LCMS 数据转化下载文件不存在: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=csv_path.name,
    )
