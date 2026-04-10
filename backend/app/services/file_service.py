"""文件服务模块。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.infra.mongo import get_files_collection
from app.models.files import UploadFileData


class FileService:
    """文件服务类。"""

    @staticmethod
    def save_upload_file(upload_file: UploadFile) -> UploadFileData:
        """
        保存上传文件并返回元数据。

        参数说明:
        - upload_file: FastAPI 上传文件对象。
        """
        now = datetime.now()
        sub_dir = Path(str(now.year), f"{now.month:02d}", f"{now.day:02d}")
        target_dir = settings.upload_root / sub_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        file_id = f"f_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        file_name = upload_file.filename or "unknown"
        file_ext = Path(file_name).suffix.lower()
        target_name = f"{file_id}_{Path(file_name).name}"
        target_path = target_dir / target_name

        content = upload_file.file.read()
        target_path.write_bytes(content)
        file_size = len(content)
        file_hash = hashlib.sha256(content).hexdigest()

        payload = UploadFileData(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            file_ext=file_ext,
            storage_path=str(Path("uploads") / sub_dir / target_name).replace("\\", "/"),
            sha256=file_hash,
        )
        get_files_collection().update_one(
            {"file_id": payload.file_id},
            {
                "$set": {
                    **payload.model_dump(),
                    "created_at": datetime.now(),
                }
            },
            upsert=True,
        )
        return payload
