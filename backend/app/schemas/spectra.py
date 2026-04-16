"""谱图预览接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpectrumPreviewData(BaseModel):
    """谱图预览响应模型。

    Args:
        spectype: 识别后的谱图类型。
        source_name: 输入文件名或来源标识。
        x_values: 横轴数据序列。
        y_values: 纵轴数据序列。
        x_min: 横轴最小值。
        x_max: 横轴最大值。
        point_count: 原始数据点数量。
        display_count: 返回给前端的展示点数量。
    """

    spectype: str = Field(description="识别后的谱图类型")
    source_name: str = Field(description="输入文件名或来源标识")
    x_values: list[float] = Field(description="横轴数据序列")
    y_values: list[float] = Field(description="纵轴数据序列")
    x_min: float = Field(description="横轴最小值")
    x_max: float = Field(description="横轴最大值")
    point_count: int = Field(description="原始数据点数量")
    display_count: int = Field(description="返回展示点数量")
