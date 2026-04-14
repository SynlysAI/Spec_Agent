"""统一谱图预览服务。"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.infra.mongo import get_files_collection
from app.modules.nmr.service import get_nmr_sample_data


class SpectrumPreviewService:
    """统一谱图预览服务。"""

    @staticmethod
    def _decode_text_bytes(file_bytes: bytes) -> str:
        """尝试按多种编码解码文本谱图数据。

        Args:
            file_bytes: 文件二进制内容。

        Returns:
            解码后的文本内容。
        """
        for encoding in ("utf-16", "utf-8", "utf-8-sig", "gbk"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("无法解析文件编码，请使用 UTF-16/UTF-8/GBK 编码文本文件")

    @staticmethod
    def _parse_two_column_text(content: str) -> tuple[np.ndarray, np.ndarray]:
        """解析两列数值文本为 x/y 数组。

        Args:
            content: 文本内容。

        Returns:
            x 与 y 的 numpy 数组。
        """
        rows: list[tuple[float, float]] = []
        for raw_line in content.splitlines():
            parts = raw_line.strip().replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        if not rows:
            raise ValueError("未解析到有效谱图数据，请确保文件至少包含两列数值")
        arr = np.asarray(rows, dtype=np.float64)
        return arr[:, 0], arr[:, 1]

    @staticmethod
    def _downsample(x_values: np.ndarray, y_values: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
        """按最大点数进行等间隔下采样。

        Args:
            x_values: 原始 x 序列。
            y_values: 原始 y 序列。
            max_points: 返回最大点数。

        Returns:
            下采样后的 x/y 序列。
        """
        if max_points <= 0 or len(x_values) <= max_points:
            return x_values, y_values
        indices = np.linspace(0, len(x_values) - 1, max_points, dtype=int)
        return x_values[indices], y_values[indices]

    def _preview_nmr_folder(self, folder_path: str) -> tuple[np.ndarray, np.ndarray]:
        """读取 NMR Bruker 目录并生成预览数据。

        Args:
            folder_path: Bruker 数据目录路径。

        Returns:
            ppm 与强度序列。
        """
        data, ppm_scale, _, _ = get_nmr_sample_data(folder_path, index=0)
        return np.asarray(ppm_scale, dtype=np.float64), np.asarray(data, dtype=np.float64)

    def _resolve_source_path(self, file_id: str | None, input_path: str | None) -> tuple[str, str]:
        """解析预览输入路径来源。

        Args:
            file_id: 文件 ID。
            input_path: 本地路径。

        Returns:
            实际路径与来源名称。
        """
        if file_id:
            file_doc = get_files_collection().find_one({"file_id": file_id}, {"_id": 0})
            if not file_doc:
                raise ValueError("file_id 不存在")
            storage_path = str(file_doc.get("storage_path", "")).replace("\\", "/")
            return str(settings.project_root / storage_path), str(file_doc.get("file_name") or file_id)
        if input_path:
            return str(input_path), Path(str(input_path)).name
        raise ValueError("file_id 与 input_path 不能同时为空")

    def preview_from_bytes(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        spectype: str = "auto",
        max_points: int = 4096,
    ) -> dict:
        """从上传文件字节生成谱图预览。

        Args:
            file_bytes: 上传文件二进制内容。
            filename: 上传文件名。
            spectype: 指定谱图类型。
            max_points: 最大展示点数。

        Returns:
            统一预览数据字典。
        """
        ext = Path(filename).suffix.lower()
        inferred = (spectype or "auto").lower()
        if inferred == "auto":
            inferred = "nmr" if ext == ".zip" else "ir"

        if inferred == "nmr" and ext == ".zip":
            with tempfile.TemporaryDirectory(prefix="nmr_preview_") as temp_dir:
                zip_path = Path(temp_dir) / filename
                zip_path.write_bytes(file_bytes)
                extract_dir = Path(temp_dir) / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)
                children = [item for item in extract_dir.iterdir() if item.is_dir()]
                nmr_path = str(children[0] if len(children) == 1 else extract_dir)
                x_values, y_values = self._preview_nmr_folder(nmr_path)
        else:
            content = self._decode_text_bytes(file_bytes)
            x_values, y_values = self._parse_two_column_text(content)

        return self._build_preview_payload(
            spectype=inferred,
            source_name=filename,
            x_values=x_values,
            y_values=y_values,
            max_points=max_points,
        )

    def preview_from_source(
        self,
        *,
        file_id: str | None = None,
        input_path: str | None = None,
        spectype: str = "auto",
        max_points: int = 4096,
    ) -> dict:
        """从 file_id 或 input_path 生成谱图预览。

        Args:
            file_id: 上传文件 ID。
            input_path: 本地路径。
            spectype: 指定谱图类型。
            max_points: 最大展示点数。

        Returns:
            统一预览数据字典。
        """
        path_str, source_name = self._resolve_source_path(file_id=file_id, input_path=input_path)
        source_path = Path(path_str)
        if not source_path.exists():
            raise ValueError(f"输入路径不存在: {source_path}")

        inferred = (spectype or "auto").lower()
        if inferred == "auto":
            if source_path.is_dir():
                inferred = "nmr"
            elif source_path.suffix.lower() == ".arw":
                inferred = "gpc"
            elif source_path.suffix.lower() == ".zip":
                inferred = "nmr"
            else:
                inferred = "ir"

        if inferred == "nmr":
            if source_path.is_file() and source_path.suffix.lower() == ".zip":
                with tempfile.TemporaryDirectory(prefix="nmr_preview_") as temp_dir:
                    extract_dir = Path(temp_dir) / "extract"
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(source_path, "r") as zip_ref:
                        zip_ref.extractall(extract_dir)
                    children = [item for item in extract_dir.iterdir() if item.is_dir()]
                    nmr_path = str(children[0] if len(children) == 1 else extract_dir)
                    x_values, y_values = self._preview_nmr_folder(nmr_path)
            else:
                folder_path = str(source_path if source_path.is_dir() else source_path.parent)
                x_values, y_values = self._preview_nmr_folder(folder_path)
        else:
            if source_path.is_dir():
                if inferred == "gpc":
                    arw_files = sorted(source_path.rglob("*.arw"))
                    if not arw_files:
                        raise ValueError("GPC 目录中未找到可预览的 .arw 文件")
                    source_path = arw_files[0]
                    source_name = source_path.name
                else:
                    text_files = sorted(source_path.rglob("*.txt")) + sorted(source_path.rglob("*.csv"))
                    if not text_files:
                        raise ValueError("目录中未找到可预览的 txt/csv 文件")
                    source_path = text_files[0]
                    source_name = source_path.name
            file_bytes = source_path.read_bytes()
            content = self._decode_text_bytes(file_bytes)
            x_values, y_values = self._parse_two_column_text(content)

        return self._build_preview_payload(
            spectype=inferred,
            source_name=source_name,
            x_values=x_values,
            y_values=y_values,
            max_points=max_points,
        )

    def _build_preview_payload(
        self,
        *,
        spectype: str,
        source_name: str,
        x_values: np.ndarray,
        y_values: np.ndarray,
        max_points: int,
    ) -> dict:
        """组装统一预览结果。

        Args:
            spectype: 谱图类型。
            source_name: 来源名称。
            x_values: 原始 x 数据。
            y_values: 原始 y 数据。
            max_points: 最大展示点数。

        Returns:
            统一预览返回字典。
        """
        if len(x_values) != len(y_values):
            raise ValueError("谱图 x/y 数据长度不一致")
        if len(x_values) == 0:
            raise ValueError("谱图数据为空")

        display_x, display_y = self._downsample(x_values, y_values, max_points=max_points)
        x_min = float(np.min(x_values))
        x_max = float(np.max(x_values))

        return {
            "spectype": spectype,
            "source_name": source_name,
            "x_values": [float(item) for item in display_x.tolist()],
            "y_values": [float(item) for item in display_y.tolist()],
            "x_min": x_min,
            "x_max": x_max,
            "point_count": int(len(x_values)),
            "display_count": int(len(display_x)),
        }


spectrum_preview_service = SpectrumPreviewService()
