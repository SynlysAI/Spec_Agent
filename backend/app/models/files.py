"""文件接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadFileData(BaseModel):
    """上传文件返回数据模型。

    函数名称: UploadFileData
    参数说明:
    - file_id: 文件唯一标识。
    - file_name: 原始文件名。
    - file_size: 文件大小（字节）。
    - file_ext: 文件扩展名。
    - storage_path: 存储相对路径。
    - sha256: 文件摘要。
    """

    file_id: str = Field(description="文件唯一标识")
    file_name: str = Field(description="原始文件名")
    file_size: int = Field(description="文件大小")
    file_ext: str = Field(description="文件扩展名")
    storage_path: str = Field(description="存储相对路径")
    sha256: str = Field(description="文件摘要")

