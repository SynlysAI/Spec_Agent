"""统一谱图预览接口。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.spectra import SpectrumPreviewData
from app.services.spectrum_preview_service import spectrum_preview_service

router = APIRouter(prefix="/spectra", tags=["spectra"])
logger = get_logger("spec_agent.api.spectra")


@router.post("/preview", response_model=ApiResponse[SpectrumPreviewData])
def preview_spectrum(
    file: UploadFile | None = File(default=None),
    spectype: str = Form(default="auto"),
    file_id: str | None = Form(default=None),
    input_path: str | None = Form(default=None),
    max_points: int = Form(default=4096),
) -> ApiResponse[SpectrumPreviewData]:
    """统一谱图预览接口。

    Args:
        file: 上传文件对象，可选。
        spectype: 谱图类型（auto/ir/raman/gpc/nmr/lcms）。
        file_id: 上传文件 ID，可选。
        input_path: 本地路径，可选。
        max_points: 预览最大点数。

    Returns:
        谱图预览数据。
    """
    if max_points < 256 or max_points > 20000:
        logger.warning("max_points 取值范围异常: %s", max_points)
        raise HTTPException(status_code=400, detail="max_points 取值范围应在 256~20000")

    source_count = int(file is not None) + int(bool(file_id)) + int(bool(input_path))
    if source_count != 1:
        logger.warning("file/file_id/input_path 提供数量异常: %s", source_count)
        raise HTTPException(status_code=400, detail="file/file_id/input_path 必须且只能提供一个")

    try:
        if file is not None:
            payload = spectrum_preview_service.preview_from_bytes(
                file_bytes=file.file.read(),
                filename=file.filename or "uploaded_file",
                spectype=spectype,
                max_points=max_points,
            )
        else:
            payload = spectrum_preview_service.preview_from_source(
                file_id=file_id,
                input_path=input_path,
                spectype=spectype,
                max_points=max_points,
            )
    except ValueError as exc:
        logger.warning("谱图预览参数校验失败: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("谱图预览异常: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ApiResponse(code=0, message="ok", data=SpectrumPreviewData(**payload))
