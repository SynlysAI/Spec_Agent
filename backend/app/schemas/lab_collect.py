"""实验室数据采集相关模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


LabSpectrumType = Literal["nmr", "gpc", "ir", "raman", "lcms"]
LabCollectStatus = Literal["PENDING", "QUEUED", "RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
LabCollectTriggerMode = Literal["single_date", "date_range"]
LabCollectSampleMode = Literal["directory", "file"]


class LabCollectorTypeConfig(BaseModel):
    """单类型采集配置摘要。"""

    spectrum_type: LabSpectrumType = Field(description="谱图类型。")
    enabled: bool = Field(default=True, description="是否启用。")
    share_key: str = Field(default="", description="共享目录标识。")
    remote_root: str = Field(default="", description="远程共享根目录。")
    local_root: str = Field(default="", description="本地保存根目录。")
    sample_mode: LabCollectSampleMode = Field(description="样本模式。")
    patterns: list[str] = Field(default_factory=list, description="文件模式匹配列表。")


class LabCollectConfigData(BaseModel):
    """采集配置摘要响应。"""

    config_path: str = Field(description="配置文件路径。")
    items: list[LabCollectorTypeConfig] = Field(default_factory=list, description="配置项列表。")


class LabCollectRunRequest(BaseModel):
    """创建采集批次请求。"""

    collect_date: Optional[str] = Field(default=None, description="单天采集日期，格式 YYYY-MM-DD。")
    date_from: Optional[str] = Field(default=None, description="范围起始日期，格式 YYYY-MM-DD。")
    date_to: Optional[str] = Field(default=None, description="范围结束日期，格式 YYYY-MM-DD。")
    spectrum_types: list[LabSpectrumType] | None = Field(default=None, description="采集谱图类型列表。")

    @model_validator(mode="after")
    def validate_date_input(self) -> "LabCollectRunRequest":
        """校验日期输入。"""
        has_single = bool(self.collect_date)
        has_range = bool(self.date_from or self.date_to)
        if has_single and has_range:
            raise ValueError("collect_date 与 date_from/date_to 不能同时提供")
        if not has_single and not has_range:
            raise ValueError("collect_date 或 date_from/date_to 必须提供其一")
        if has_range and (not self.date_from or not self.date_to):
            raise ValueError("date_from 与 date_to 必须同时提供")
        return self


class LabCollectRunError(BaseModel):
    """采集失败项。"""

    spectrum_type: LabSpectrumType = Field(description="谱图类型。")
    source_date: str = Field(description="远程目录日期。")
    remote_path: str = Field(description="远程路径。")
    sample_name: str = Field(description="样品名。")
    error_message: str = Field(description="错误信息。")


class LabCollectRunSummary(BaseModel):
    """采集批次汇总。"""

    total_days: int = Field(default=0, description="扫描日期天数。")
    total_candidates: int = Field(default=0, description="候选样本数。")
    imported: int = Field(default=0, description="新增导入样本数。")
    updated: int = Field(default=0, description="覆盖更新样本数。")
    skipped: int = Field(default=0, description="跳过样本数。")
    failed: int = Field(default=0, description="失败样本数。")
    progress: int = Field(default=0, description="批次进度（0-100）。")
    type_stats: dict[str, dict[str, int]] = Field(default_factory=dict, description="按谱图类型汇总统计。")


class LabCollectRunRecord(BaseModel):
    """采集批次实体。"""

    run_id: str = Field(description="批次 ID。")
    status: LabCollectStatus = Field(description="批次状态。")
    spectrum_types: list[LabSpectrumType] = Field(default_factory=list, description="谱图类型列表。")
    date_from: str = Field(description="起始日期。")
    date_to: str = Field(description="结束日期。")
    trigger_mode: LabCollectTriggerMode = Field(description="触发模式。")
    config_snapshot: dict[str, Any] = Field(default_factory=dict, description="配置快照。")
    summary: LabCollectRunSummary = Field(default_factory=LabCollectRunSummary, description="汇总数据。")
    errors: list[LabCollectRunError] = Field(default_factory=list, description="失败项列表。")
    started_at: Optional[datetime] = Field(default=None, description="开始时间。")
    finished_at: Optional[datetime] = Field(default=None, description="结束时间。")
    created_at: datetime = Field(description="创建时间。")
    updated_at: datetime = Field(description="更新时间。")


class LabCollectRunCreateData(BaseModel):
    """创建采集批次响应。"""

    run_id: str = Field(description="批次 ID。")
    status: LabCollectStatus = Field(description="批次状态。")


class LabCollectRunListData(BaseModel):
    """采集批次列表响应。"""

    total: int = Field(default=0, description="总条数。")
    items: list[LabCollectRunRecord] = Field(default_factory=list, description="批次列表。")


class SpectrumSampleFileRecord(BaseModel):
    """样本文件清单实体。"""

    sample_file_id: str = Field(description="样本文件 ID。")
    sample_id: str = Field(description="样本 ID。")
    sample_key: str = Field(description="样本唯一键。")
    spectrum_type: LabSpectrumType = Field(description="谱图类型。")
    role: str = Field(description="文件角色。")
    file_name: str = Field(description="文件名。")
    file_ext: str = Field(description="文件扩展名。")
    relative_path: str = Field(description="相对样本目录路径。")
    remote_path: str = Field(description="远程文件路径。")
    local_path: str = Field(description="本地文件路径。")
    file_size: int = Field(default=0, description="文件大小。")
    sha256: Optional[str] = Field(default=None, description="文件摘要。")
    modified_at: Optional[datetime] = Field(default=None, description="远程文件修改时间。")
    copied_at: datetime = Field(description="复制时间。")
    is_primary_input: bool = Field(default=False, description="是否为分析主输入文件。")


class SpectrumSampleRecord(BaseModel):
    """实验样本主档实体。"""

    sample_id: str = Field(description="样本 ID。")
    sample_key: str = Field(description="样本唯一键。")
    spectrum_type: LabSpectrumType = Field(description="谱图类型。")
    source_date: str = Field(description="远程目录日期。")
    sample_name: str = Field(description="样品名。")
    sample_name_normalized: str = Field(description="标准化样品名。")
    source: dict[str, Any] = Field(default_factory=dict, description="远程来源信息。")
    storage: dict[str, Any] = Field(default_factory=dict, description="本地存储信息。")
    analysis_input: dict[str, Any] = Field(default_factory=dict, description="分析输入信息。")
    collect_status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"] = Field(description="采集状态。")
    collect_stats: dict[str, Any] = Field(default_factory=dict, description="采集统计。")
    sample_meta: dict[str, Any] = Field(default_factory=dict, description="样本元数据。")
    latest_run_id: str = Field(description="最近一次采集批次 ID。")
    collect_count: int = Field(default=1, description="采集次数。")
    created_at: datetime = Field(description="创建时间。")
    updated_at: datetime = Field(description="更新时间。")


class SpectrumSampleListItem(BaseModel):
    """样本列表项。"""

    sample_id: str = Field(description="样本 ID。")
    sample_key: str = Field(description="样本唯一键。")
    spectrum_type: LabSpectrumType = Field(description="谱图类型。")
    source_date: str = Field(description="远程目录日期。")
    sample_name: str = Field(description="样品名。")
    collect_status: str = Field(description="采集状态。")
    latest_run_id: str = Field(description="最近采集批次 ID。")
    updated_at: datetime = Field(description="最近更新时间。")
    analysis_input: dict[str, Any] = Field(default_factory=dict, description="分析输入信息。")


class SpectrumSampleListData(BaseModel):
    """样本分页列表响应。"""

    total: int = Field(default=0, description="总条数。")
    page: int = Field(default=1, description="页码。")
    page_size: int = Field(default=20, description="每页条数。")
    items: list[SpectrumSampleListItem] = Field(default_factory=list, description="样本列表。")


class SpectrumSampleSummaryData(BaseModel):
    """样本汇总响应。"""

    total_samples: int = Field(default=0, description="总样本数。")
    type_counts: dict[str, int] = Field(default_factory=dict, description="按谱图类型统计的样本数。")
    latest_updated_at: datetime | None = Field(default=None, description="最近样本更新时间。")


class SpectrumSampleDetailData(BaseModel):
    """样本详情响应。"""

    sample: SpectrumSampleRecord = Field(description="样本主档。")
    files: list[SpectrumSampleFileRecord] = Field(default_factory=list, description="文件清单。")
