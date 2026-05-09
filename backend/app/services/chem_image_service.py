"""化学结构图片渲染服务。"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from app.core.logging import get_logger

logger = get_logger("spec_agent.services.chem_image")


class ChemImageService:
    """化学结构图片渲染服务。"""

    @staticmethod
    def _import_rdkit_modules() -> tuple[Any, Any]:
        """按需导入 RDKit 依赖。

        Returns:
            RDKit 的 Chem 与 Draw 模块对象。
        """
        try:
            from rdkit import Chem
            from rdkit.Chem import Draw
        except ImportError as exc:
            logger.error("未安装 RDKit，无法生成化学结构图片: %s", exc)
            raise RuntimeError("未安装 RDKit，无法生成化学结构图片") from exc
        return Chem, Draw

    @staticmethod
    def _to_png_bytes(image_obj: Any) -> bytes:
        """将 PIL 图片对象编码为 PNG 字节。

        Args:
            image_obj: Draw.MolToImage 返回的图片对象。

        Returns:
            PNG 二进制数据。
        """
        buffer = BytesIO()
        image_obj.save(buffer, format="PNG")
        return buffer.getvalue()

    def render_smiles_png(self, smiles: str, size: int = 320) -> bytes:
        """将 SMILES 转换为分子结构 PNG 图片。

        Args:
            smiles: 分子 SMILES 字符串。
            size: 图片宽高（像素）。

        Returns:
            PNG 图片字节数据。
        """
        clean_smiles = str(smiles or "").strip()
        if not clean_smiles:
            logger.warning("smiles 为空")
            raise ValueError("smiles 不能为空")

        chem_module, draw_module = self._import_rdkit_modules()
        mol = chem_module.MolFromSmiles(clean_smiles)
        if mol is None:
            logger.warning("无效的 SMILES，无法解析分子结构: %s", clean_smiles)
            raise ValueError("无效的 SMILES，无法解析分子结构")

        image_obj = draw_module.MolToImage(mol, size=(size, size))
        return self._to_png_bytes(image_obj)

    def render_smarts_png(self, smarts: str, size: int = 280) -> bytes:
        """将 SMARTS 转换为官能团结构 PNG 图片。

        Args:
            smarts: 官能团 SMARTS 字符串。
            size: 图片宽高（像素）。

        Returns:
            PNG 图片字节数据。
        """
        clean_smarts = str(smarts or "").strip()
        if not clean_smarts:
            logger.warning("smarts 为空")
            raise ValueError("smarts 不能为空")

        chem_module, draw_module = self._import_rdkit_modules()
        mol = chem_module.MolFromSmarts(clean_smarts)
        if mol is None:
            logger.warning("无效的 SMARTS，无法解析官能团结构: %s", clean_smarts)
            raise ValueError("无效的 SMARTS，无法解析官能团结构")

        image_obj = draw_module.MolToImage(mol, size=(size, size), kekulize=False)
        return self._to_png_bytes(image_obj)


chem_image_service = ChemImageService()
