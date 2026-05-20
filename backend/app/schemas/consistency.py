"""设备重复性评测相关请求与响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.tasks import TaskArtifactItem


class ConsistencyDeviceConfig(BaseModel):
    """单设备类型配置摘要。"""

    device_type: str = Field(description="设备类型编码。")
    label: str = Field(description="设备类型名称。")
    data_path: str = Field(default="", description="数据源目录。")
    group_count: int = Field(default=0, description="样品组数量。")
    enabled: bool = Field(default=True, description="是否启用。")
    summary_description: str = Field(default="", description="指标说明。")


class ConsistencyConfigData(BaseModel):
    """一致性评测配置摘要。"""

    config_path: str = Field(description="配置文件路径。")
    items: list[ConsistencyDeviceConfig] = Field(default_factory=list, description="设备配置项。")
    total_devices: int = Field(default=0, description="设备类型总数。")


class ConsistencyRunRequest(BaseModel):
    """启动一致性评测请求参数。"""

    device_types: list[str] | None = Field(default=None, description="指定执行的设备类型。")


class ConsistencyRunSummary(BaseModel):
    """一致性评测批次汇总。"""

    total: int = Field(default=0, description="总设备数。")
    success: int = Field(default=0, description="成功设备数。")
    failed: int = Field(default=0, description="失败设备数。")
    progress: int = Field(default=0, description="运行进度。")
    duration_seconds: float = Field(default=0.0, description="总耗时（秒）。")


class ConsistencyGroupResultItem(BaseModel):
    """单样品组一致性结果。"""

    group_name: str = Field(description="样品组名称。")
    status: str = Field(default="SUCCESS", description="组结果状态。")
    replicate_count: int = Field(default=0, description="重复测试次数。")
    metrics: dict[str, Any] = Field(default_factory=dict, description="组级指标。")
    remark: str = Field(default="", description="备注信息。")


class ConsistencyDeviceRunItem(BaseModel):
    """单设备一致性评测结果。"""

    device_type: str = Field(description="设备类型编码。")
    device_label: str = Field(description="设备类型名称。")
    status: str = Field(description="设备结果状态。")
    duration_seconds: float = Field(default=0.0, description="设备耗时（秒）。")
    summary_metrics: dict[str, Any] = Field(default_factory=dict, description="设备级汇总指标。")
    group_results: list[ConsistencyGroupResultItem] = Field(default_factory=list, description="样品组明细。")
    text_report: str = Field(default="", description="文本报告。")
    artifacts: list[TaskArtifactItem] = Field(default_factory=list, description="产物列表。")
    error_message: str | None = Field(default=None, description="错误信息。")


class ConsistencyRunData(BaseModel):
    """一致性评测批次数据。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")
    started_at: str = Field(description="开始时间。")
    finished_at: str | None = Field(default=None, description="结束时间。")
    selected_devices: list[str] = Field(default_factory=list, description="执行设备类型列表。")
    summary: ConsistencyRunSummary = Field(description="汇总信息。")
    device_results: list[ConsistencyDeviceRunItem] = Field(default_factory=list, description="设备结果列表。")
    report_path: str | None = Field(default=None, description="报告文件路径。")


class ConsistencyRunCreateData(BaseModel):
    """启动一致性评测响应数据。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")


class ConsistencyRunHistoryItem(BaseModel):
    """一致性评测历史列表项。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")
    started_at: str = Field(default="", description="开始时间。")
    finished_at: str | None = Field(default=None, description="结束时间。")
    selected_devices: list[str] = Field(default_factory=list, description="设备类型列表。")
    summary: ConsistencyRunSummary = Field(description="汇总信息。")
    report_exists: bool = Field(default=False, description="报告是否存在。")


class ConsistencyRunHistoryData(BaseModel):
    """一致性评测历史列表。"""

    total: int = Field(default=0, description="总条数。")
    items: list[ConsistencyRunHistoryItem] = Field(default_factory=list, description="历史项列表。")
