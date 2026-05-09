"""LCMS 外部推理服务。"""

from __future__ import annotations

from pathlib import Path

import requests

from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger("spec_agent.services.lcms")


class LcmsService:
    """LCMS 外部推理服务封装。"""

    def __init__(self, infer_url: str | None = None) -> None:
        """初始化 LCMS 推理客户端。

        Args:
            infer_url: 推理接口地址；未传入时读取系统配置。
        """
        self.infer_url = infer_url or settings.lcms_infer_url
        self.connect_timeout = 10
        self.read_timeout = 120
        self.session = requests.Session()

    def infer_mass(self, file_path: str) -> dict:
        """上传 LCMS 谱图并获取分子量预测结果。

        Args:
            file_path: 本地谱图文件路径。

        Returns:
            推理服务返回的 JSON 结果。
        """
        target_path = Path(file_path)
        if not target_path.exists() or not target_path.is_file():
            logger.warning("LCMS 输入文件不存在: %s", target_path)
            raise ValueError(f"LCMS 输入文件不存在: {target_path}")

        mime_type = "text/plain"
        if target_path.suffix.lower() == ".csv":
            mime_type = "text/csv"

        with target_path.open("rb") as file_handle:
            files = {
                "file": (
                    target_path.name,
                    file_handle,
                    mime_type,
                )
            }
            response = self.session.post(
                self.infer_url,
                files=files,
                timeout=(self.connect_timeout, self.read_timeout),
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            logger.error("LCMS 服务返回格式异常, 实际类型: %s", type(payload).__name__)
            raise RuntimeError("LCMS 服务返回格式异常")
        return payload


lcms_service = LcmsService()
