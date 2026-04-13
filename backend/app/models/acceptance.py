"""批量验收测试相关请求与响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AcceptanceTypeConfig(BaseModel):
    """单谱图类型的验收配置摘要。"""

    spectrum_type: str = Field(description="谱图类型编码。")
    label: str = Field(description="谱图类型名称。")
    sample_count: int = Field(default=0, description="可执行样本数量。")
    dirs: list[str] = Field(default_factory=list, description="配置目录列表。")


class AcceptanceConfigData(BaseModel):
    """验收配置摘要响应数据。"""

    config_path: str = Field(description="配置文件路径。")
    items: list[AcceptanceTypeConfig] = Field(default_factory=list, description="各类型配置统计。")
    total_samples: int = Field(default=0, description="总样本数。")


class AcceptanceRunRequest(BaseModel):
    """启动验收测试请求参数。"""

    spectrum_types: list[str] | None = Field(default=None, description="指定执行的谱图类型。为空表示全量。")


class AcceptanceRunItem(BaseModel):
    """单样本验收执行结果。"""

    spectrum_type: str = Field(description="谱图类型。")
    sample_name: str = Field(description="样本名称。")
    sample_path: str = Field(description="样本路径。")
    task_id: str = Field(description="执行任务 ID。")
    status: str = Field(description="执行状态。")
    duration_seconds: float = Field(default=0.0, description="耗时（秒）。")
    metrics: dict[str, Any] = Field(default_factory=dict, description="单样本指标数据。")
    error_message: str | None = Field(default=None, description="失败错误信息。")


class AcceptanceRunSummary(BaseModel):
    """验收运行汇总。"""

    total: int = Field(default=0, description="总样本数。")
    success: int = Field(default=0, description="成功样本数。")
    failed: int = Field(default=0, description="失败样本数。")
    progress: int = Field(default=0, description="运行进度（0-100）。")
    duration_seconds: float = Field(default=0.0, description="总耗时（秒）。")


class AcceptanceRunData(BaseModel):
    """验收运行状态响应数据。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")
    started_at: str = Field(description="开始时间。")
    finished_at: str | None = Field(default=None, description="结束时间。")
    selected_types: list[str] = Field(default_factory=list, description="本次执行的谱图类型。")
    summary: AcceptanceRunSummary = Field(description="汇总信息。")
    aggregate_metrics: dict[str, Any] = Field(default_factory=dict, description="验收指标汇总。")
    results: list[AcceptanceRunItem] = Field(default_factory=list, description="样本结果列表。")
    report_path: str | None = Field(default=None, description="报告文件路径。")


class AcceptanceRunCreateData(BaseModel):
    """启动验收测试响应数据。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")


class AcceptanceRunHistoryItem(BaseModel):
    """验收运行历史列表项。"""

    run_id: str = Field(description="批次运行 ID。")
    status: str = Field(description="批次状态。")
    started_at: str = Field(default="", description="开始时间。")
    finished_at: str | None = Field(default=None, description="结束时间。")
    selected_types: list[str] = Field(default_factory=list, description="执行类型列表。")
    summary: AcceptanceRunSummary = Field(description="汇总信息。")
    report_exists: bool = Field(default=False, description="报告文件是否存在。")


class AcceptanceRunHistoryData(BaseModel):
    """验收运行历史列表。"""

    total: int = Field(default=0, description="总条数。")
    items: list[AcceptanceRunHistoryItem] = Field(default_factory=list, description="历史列表数据。")
