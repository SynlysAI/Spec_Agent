"""设备重复性评测公共工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.schemas.tasks import TaskArtifactItem


DEVICE_LABELS = {
    "nmr": "NMR 核磁",
    "gpc": "GPC 凝胶色谱",
    "raman": "Raman 拉曼",
    "lcms": "LCMS 质谱",
}


def safe_float(value: Any) -> float | None:
    """安全转换浮点值。

    Args:
        value: 原始值。

    Returns:
        可用浮点值，无法转换时返回 ``None``。
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def calc_cv(values: list[float]) -> float | None:
    """计算变异系数 CV(%)。

    Args:
        values: 数值列表。

    Returns:
        CV 百分比；数据不足或均值为零时返回 ``None``。
    """
    if len(values) < 2:
        return None
    values_array = np.asarray(values, dtype=float)
    mean_value = float(np.mean(values_array))
    if mean_value == 0:
        return None
    return float(np.std(values_array, ddof=1) / mean_value * 100.0)


def average(values: list[float]) -> float | None:
    """计算均值。

    Args:
        values: 数值列表。

    Returns:
        均值；空列表时返回 ``None``。
    """
    if not values:
        return None
    return float(sum(values) / len(values))


def format_number(value: Any, digits: int = 4, suffix: str = "") -> str:
    """格式化数值。

    Args:
        value: 原始值。
        digits: 小数位数。
        suffix: 后缀单位。

    Returns:
        可展示字符串；无效值时返回 ``N/A``。
    """
    parsed = safe_float(value)
    if parsed is None:
        return "N/A"
    return f"{parsed:.{digits}f}{suffix}"


def build_artifact(file_path: Path) -> TaskArtifactItem:
    """构建产物对象。

    Args:
        file_path: 产物文件绝对路径。

    Returns:
        前端可消费的产物对象。
    """
    relative_path = file_path.relative_to(settings.outputs_root).as_posix()
    suffix = file_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
        file_type = "image"
    elif suffix in {".txt", ".md", ".json", ".csv", ".yaml", ".yml"}:
        file_type = "text"
    elif suffix == ".pdf":
        file_type = "pdf"
    else:
        file_type = "other"
    return TaskArtifactItem(
        name=file_path.name,
        relative_path=relative_path,
        file_type=file_type,
        url=f"/static/outputs/{relative_path}",
    )
