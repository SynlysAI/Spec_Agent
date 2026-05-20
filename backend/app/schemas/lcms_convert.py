"""LCMS 数据转化接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LcmsConvertLabelPeak(BaseModel):
    """LCMS 代表峰标注模型。"""

    mz: float = Field(description="峰位 m/z。")
    intensity: float = Field(description="峰强度。")


class LcmsConvertResultData(BaseModel):
    """LCMS 数据转化结果模型。"""

    job_id: str = Field(description="本次转换任务 ID。")
    source_name: str = Field(description="源目录名称。")
    apex_rt: float = Field(description="TIC 顶点对应保留时间。")
    apex_tic: float = Field(description="TIC 顶点总离子流强度。")
    rt_x_values: list[float] = Field(default_factory=list, description="保留时间横轴数据。")
    rt_y_values: list[float] = Field(default_factory=list, description="保留时间纵轴强度数据。")
    ms_full_x_values: list[float] = Field(default_factory=list, description="原始 MS 谱图 m/z 数据。")
    ms_full_y_values: list[float] = Field(default_factory=list, description="原始 MS 谱图强度数据。")
    ms_filtered_x_values: list[float] = Field(default_factory=list, description="高峰视图 m/z 数据。")
    ms_filtered_y_values: list[float] = Field(default_factory=list, description="高峰视图强度数据。")
    label_peaks: list[LcmsConvertLabelPeak] = Field(default_factory=list, description="代表峰标注列表。")
    point_count_full: int = Field(default=0, description="原始谱点数。")
    point_count_filtered: int = Field(default=0, description="高峰视图谱点数。")
    download_url: str = Field(description="转换结果下载地址。")
