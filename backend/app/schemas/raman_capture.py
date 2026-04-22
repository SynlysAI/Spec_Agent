"""拉曼光谱仪采集工具接口模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RamanCaptureRunRequest(BaseModel):
    """拉曼光谱仪批量采集请求模型。

    Args:
        instrument_ip: 拉曼光谱仪 IP 地址。
        callback_port: 本机回调服务监听端口。
        wavenumber_list: 需要扫描的中心波数列表。
        power_list: 需要扫描的激光功率列表。
    """

    instrument_ip: str = Field(default="10.26.15.56", min_length=1, description="拉曼光谱仪 IP 地址")
    callback_port: int = Field(default=9000, ge=1, le=65535, description="本机回调服务监听端口")
    wavenumber_list: list[float] = Field(default_factory=list, description="中心波数列表")
    power_list: list[float] = Field(default_factory=list, description="激光功率列表")


class RamanCaptureResultItem(BaseModel):
    """单个拉曼采集条件的结果模型。

    Args:
        sequence: 任务序号。
        task_id: 采集任务 ID。
        wavenumber: 中心波数。
        power: 激光功率。
        status: 任务状态。
        success: 是否采集成功。
        point_count: 数据点数量。
        y_min: 强度最小值。
        y_max: 强度最大值。
        duration_seconds: 采集耗时。
        error_msg: 错误信息。
    """

    sequence: int
    task_id: str
    wavenumber: float
    power: float
    status: str
    success: bool
    point_count: int = 0
    y_min: float | None = None
    y_max: float | None = None
    duration_seconds: float = 0.0
    error_msg: str | None = None


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
        callback_port: 本机回调服务监听端口。
        callback_url: 实际回调地址。
        summary: 采集汇总。
        results: 单条件结果列表。
        report: Markdown 文本报告。
    """

    instrument_ip: str
    callback_port: int
    callback_url: str
    summary: RamanCaptureSummary
    results: list[RamanCaptureResultItem]
    report: str
