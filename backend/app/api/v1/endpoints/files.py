"""文件上传接口。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.files import UploadFileData
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=ApiResponse[UploadFileData])
def upload_file(file: UploadFile = File(...), biz_type: str | None = Form(default=None)) -> ApiResponse[UploadFileData]:
    """上传文件接口。

    函数名称: upload_file
    参数说明:
    - file: 上传文件对象。
    - biz_type: 业务类型（gpc/nmr/ir/raman/lcms），可选。
    """
    _validate_upload(file=file, biz_type=biz_type)
    saved = FileService.save_upload_file(upload_file=file)
    return ApiResponse(code=0, message="ok", data=saved)


def _validate_upload(file: UploadFile, biz_type: str | None) -> None:
    """校验上传文件合法性。

    函数名称: _validate_upload
    参数说明:
    - file: 上传文件对象。
    - biz_type: 业务类型（gpc/nmr/ir/raman/lcms）。
    """
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = filename.lower().rsplit(".", maxsplit=1)
    suffix = f".{ext[-1]}" if len(ext) == 2 else ""
    allowed_map = {
        None: {".arw", ".txt", ".csv", ".json", ".pdf"},
        "gpc": {".arw", ".pdf", ".json"},
        "nmr": {".txt", ".csv", ".zip"},
        "ir": {".txt", ".csv"},
        "raman": {".txt", ".csv"},
        "lcms": {".txt", ".csv"},
    }
    if biz_type not in allowed_map:
        raise HTTPException(status_code=400, detail="biz_type 仅支持 gpc/nmr/ir/raman/lcms")

    allowed = allowed_map[biz_type]
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")

    content = file.file.read()
    file.file.seek(0)
    if not content:
        raise HTTPException(status_code=400, detail="空文件不允许上传")

    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制: {settings.max_upload_size_mb}MB")
