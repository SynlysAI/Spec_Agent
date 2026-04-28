"""拉曼光谱仪采集工具接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RamanCaptureRunRequest(BaseModel):
    """拉曼光谱仪批量采集请求模型。

    Args:
        wavenumber_list: 需要扫描的中心波数列表。
        power_list: 需要扫描的激光功率列表。
        explore_time: 积分时间。
        integer: 积分次数。
        power_type: 功率类型。
        grating_index: 光栅索引。
    """

    wavenumber_list: list[float] = Field(default_factory=list, description="中心波数列表")
    power_list: list[float] = Field(default_factory=list, description="激光功率列表")
    explore_time: float = Field(default=5.0, gt=0, description="积分时间")
    integer: int = Field(default=1, ge=1, description="积分次数")
    power_type: int = Field(default=2, ge=0, description="功率类型")
    grating_index: int = Field(default=1, ge=0, description="光栅索引")


class RamanCaptureResultItem(BaseModel):
    """单个拉曼采集条件的结果模型。

    Args:
        sequence: 任务序号。
        task_id: 采集任务 ID。
        wavenumber: 中心波数。
        power: 激光功率。
        explore_time: 积分时间。
        integer: 积分次数。
        power_type: 功率类型。
        grating_index: 光栅索引。
        status: 任务状态。
        success: 是否采集成功。
        point_count: 数据点数量。
        y_min: 强度最小值。
        y_max: 强度最大值。
        duration_seconds: 采集耗时。
        error_msg: 错误信息。
        response_file: 结果文件名。
        x_values: 谱图横轴数据。
        y_values: 谱图纵轴数据。
    """

    sequence: int
    task_id: str
    wavenumber: float
    power: float
    explore_time: float
    integer: int
    power_type: int
    grating_index: int
    status: str
    success: bool
    point_count: int = 0
    y_min: float | None = None
    y_max: float | None = None
    duration_seconds: float = 0.0
    error_msg: str | None = None
    response_file: str | None = None
    x_values: list[float] = Field(default_factory=list)
    y_values: list[float] = Field(default_factory=list)


class RamanCaptureSummary(BaseModel):
    """拉曼批量采集汇总模型。

    Args:
        total: 任务总数。
        success: 成功数量。
        failed: 失败数量。
        duration_seconds: 总耗时。
    """

    total: int
    success: int
    failed: int
    duration_seconds: float


class RamanCaptureRunData(BaseModel):
    """拉曼批量采集响应模型。

    Args:
        instrument_ip: 拉曼光谱仪 IP 地址。
        callback_url: 实际回调地址。
        polling_interval_seconds: 查询轮询间隔秒数。
        polling_timeout_seconds: 单任务轮询超时秒数。
        summary: 采集汇总。
        results: 单条件结果列表。
        report: Markdown 文本报告。
    """

    instrument_ip: str
    callback_url: str
    polling_interval_seconds: int
    polling_timeout_seconds: int
    summary: RamanCaptureSummary
    results: list[RamanCaptureResultItem]
    report: str
