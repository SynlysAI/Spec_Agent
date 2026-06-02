"""任务接口模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


TaskStatus = Literal["PENDING", "QUEUED", "RUNNING", "SUCCESS", "FAILED", "CANCELED"]
TaskKind = Literal["gpc_analysis", "nmr_analysis", "ir_analysis", "raman_analysis", "lcms_analysis"]


class TaskInput(BaseModel):
    """任务输入模型。

    函数名称: TaskInput
    参数说明:
    - input_type: 输入类型，可为 file_path/file_id/folder_path。
    - input_path: 输入路径。
    - file_id: 已上传文件 ID。
    """

    input_type: Literal["file_path", "file_id", "folder_path"] = Field(description="输入类型")
    input_path: Optional[str] = Field(default=None, description="输入路径")
    file_id: Optional[str] = Field(default=None, description="上传文件ID")

    @model_validator(mode="after")
    def validate_input(self) -> "TaskInput":
        """执行输入有效性校验。

        函数名称: validate_input
        参数说明:
        - self: 当前模型实例。
        """
        if self.input_type in {"file_path", "folder_path"} and not self.input_path:
            raise ValueError("input_path 为必填")
        if self.input_type == "file_id" and not self.file_id:
            raise ValueError("file_id 为必填")
        return self


class TaskOptions(BaseModel):
    """任务可选参数模型。

    函数名称: TaskOptions
    参数说明:
    - priority: 任务优先级，数值越小优先级越高。
    - callback_url: 回调地址。
    """

    priority: int = Field(default=5, ge=1, le=10, description="任务优先级")
    callback_url: Optional[str] = Field(default=None, description="回调地址")


class GpcTaskParams(BaseModel):
    """GPC 任务参数模型。

    函数名称: GpcTaskParams
    参数说明:
    - detect_mode: 峰检测模式，auto/manual。
    - manual_interval: 手动检测区间。
    - three_color_arw_file_ids: 三色曲线文件 ID 列表（红/绿/白，传则必须传满 3 个）。
    - calibration_file_id: 校准文件 ID。
    - comparison_report_pdf_file_id: 对比报告 PDF 文件 ID。
    """

    detect_mode: Literal["auto", "manual"] = Field(default="auto", description="峰检测模式")
    manual_interval: Optional[list[float]] = Field(default=None, description="手动检测区间")
    three_color_arw_file_ids: Optional[list[str]] = Field(default=None, description="三色曲线文件ID列表（红/绿/白）")
    calibration_file_id: Optional[str] = Field(default=None, description="校准文件ID")
    comparison_report_pdf_file_id: Optional[str] = Field(default=None, description="对比报告PDF文件ID")
    source_file_name: Optional[str] = Field(default=None, description="上传原始文件名（可选，用于三色匹配）")

    @model_validator(mode="after")
    def validate_params(self) -> "GpcTaskParams":
        """执行 GPC 参数校验。

        函数名称: validate_params
        参数说明:
        - self: 当前模型实例。
        """
        if self.detect_mode == "manual":
            if not self.manual_interval or len(self.manual_interval) != 2:
                raise ValueError("manual 模式下 manual_interval 必须为 [start, end]")
        if self.three_color_arw_file_ids is not None and len(self.three_color_arw_file_ids) != 3:
            raise ValueError("三色曲线文件必须传满 3 个（红/绿/白）")
        return self


class NmrTaskParams(BaseModel):
    """NMR 任务参数模型（单阶段）。

    函数名称: NmrTaskParams
    参数说明:
    - nucleus: 核类型，1H/13C。
    - threshold/min_distance/min_prominence: 峰检测核心参数。
    - width_multiplier/baseline_degree/smooth_window: 处理参数。
    - enable_multiplet/max_coupling_hz: 多重峰聚合配置。
    - detection_range_mode/min/max: 检测范围参数。
    - ppm_offset: ppm 偏移。
    - integration_method: 积分方法。
    - internal_standard_policy: 内标策略，固定为 auto。
    - internal_standard_prefer: 默认内标优先级（溶剂峰/TMS）。
    """

    nucleus: Literal["1H", "13C"] = Field(default="1H", description="核类型")
    threshold: float = Field(default=0.01, gt=0, description="峰检测阈值")
    min_distance: float = Field(default=0.3, gt=0, description="最小峰距")
    min_prominence: float = Field(default=0.01, gt=0, description="最小显著性")
    width_multiplier: float = Field(default=1.0, gt=0, description="峰宽倍率")
    baseline_degree: int = Field(default=3, ge=1, le=10, description="基线拟合阶数")
    smooth_window: int = Field(default=5, ge=1, le=99, description="平滑窗口")
    enable_multiplet: bool = Field(default=True, description="是否启用多重峰聚合")
    max_coupling_hz: float = Field(default=20.0, gt=0, description="多重峰最大耦合常数阈值")
    detection_range_mode: Literal["full", "custom"] = Field(default="full", description="检测范围模式")
    detection_range_min: Optional[float] = Field(default=None, description="检测范围最小值")
    detection_range_max: Optional[float] = Field(default=None, description="检测范围最大值")
    ppm_offset: float = Field(default=0.0, description="ppm偏移")
    integration_method: Literal["voigt", "trapezoid"] = Field(default="voigt", description="积分方法")
    internal_standard_policy: Literal["auto"] = Field(default="auto", description="内标策略")
    internal_standard_prefer: list[Literal["solvent", "tms"]] = Field(
        default_factory=lambda: ["solvent", "tms"], description="内标优先级"
    )


class CreateGpcTaskRequest(BaseModel):
    """创建 GPC 任务请求模型。

    函数名称: CreateGpcTaskRequest
    参数说明:
    - input: 输入配置。
    - params: GPC 参数。
    - options: 可选参数。
    """

    input: TaskInput
    params: GpcTaskParams = Field(default_factory=GpcTaskParams)
    options: TaskOptions = Field(default_factory=TaskOptions)


class CreateNmrTaskRequest(BaseModel):
    """创建 NMR 任务请求模型。

    函数名称: CreateNmrTaskRequest
    参数说明:
    - input: 输入配置。
    - params: NMR 参数。
    - options: 可选参数。
    """

    input: TaskInput
    params: NmrTaskParams = Field(default_factory=NmrTaskParams)
    options: TaskOptions = Field(default_factory=TaskOptions)


class IrRamanTaskParams(BaseModel):
    """IR/Raman 任务参数模型。

    函数名称: IrRamanTaskParams
    参数说明:
    - spectype: 光谱类型，ir 或 raman。
    - mode: 分析模式，greedy_decode/beam_search/retrieval/function_groups。
    - k: 候选数量，beam_search/retrieval 有效。
    - x0/x1: 分析范围。
    - transmittance: IR 是否执行透射率转吸光度。
    - device: 推理设备，cpu/cuda/auto。
    """

    spectype: Literal["ir", "raman"] = Field(default="ir", description="光谱类型")
    mode: Literal["greedy_decode", "beam_search", "retrieval", "function_groups"] = Field(
        default="greedy_decode", description="分析模式"
    )
    k: int = Field(default=3, ge=1, le=10, description="候选数量")
    x0: float = Field(default=400.0, ge=0.0, description="分析范围起点")
    x1: float = Field(default=4000.0, ge=0.0, description="分析范围终点")
    transmittance: bool = Field(default=False, description="IR透射率转吸光度")
    device: Literal["cpu", "cuda", "auto"] = Field(default="auto", description="推理设备")

    @model_validator(mode="after")
    def validate_range(self) -> "IrRamanTaskParams":
        """校验范围参数合法性。

        函数名称: validate_range
        参数说明:
        - self: 当前模型实例。
        """
        if self.x0 >= self.x1:
            raise ValueError("x0 必须小于 x1")
        if self.spectype == "raman" and self.transmittance:
            raise ValueError("raman 模式不支持 transmittance=true")
        return self


class CreateIrRamanTaskRequest(BaseModel):
    """创建 IR/Raman 任务请求模型。

    函数名称: CreateIrRamanTaskRequest
    参数说明:
    - input: 输入配置。
    - params: IR/Raman 参数。
    - options: 可选参数。
    """

    input: TaskInput
    params: IrRamanTaskParams = Field(default_factory=IrRamanTaskParams)
    options: TaskOptions = Field(default_factory=TaskOptions)


class LcmsTaskParams(BaseModel):
    """LCMS 任务参数模型。"""

    source_file_name: Optional[str] = Field(default=None, description="上传原始文件名（可选）")


class CreateLcmsTaskRequest(BaseModel):
    """创建 LCMS 任务请求模型。

    Args:
        input: 输入配置。
        params: LCMS 参数。
        options: 可选参数。
    """

    input: TaskInput
    params: LcmsTaskParams = Field(default_factory=LcmsTaskParams)
    options: TaskOptions = Field(default_factory=TaskOptions)


class CreateTaskData(BaseModel):
    """创建任务返回数据模型。

    函数名称: CreateTaskData
    参数说明:
    - task_id: 任务ID。
    - task_type: 任务类型。
    - status: 任务状态。
    """

    task_id: str
    task_type: TaskKind
    status: TaskStatus


class TaskStatusData(BaseModel):
    """任务状态返回模型。

    函数名称: TaskStatusData
    参数说明:
    - task_id: 任务ID。
    - task_type: 任务类型。
    - status: 当前状态。
    - progress: 进度百分比。
    - message: 状态消息。
    - created_at: 创建时间。
    - updated_at: 更新时间。
    """

    task_id: str
    task_type: TaskKind
    status: TaskStatus
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime


class TaskListItem(BaseModel):
    """任务列表项模型。

    Args:
        task_id: 任务 ID。
        task_type: 任务类型。
        status: 当前状态。
        progress: 进度百分比。
        message: 状态消息。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    task_id: str
    task_type: TaskKind
    status: TaskStatus
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime


class TaskListData(BaseModel):
    """任务列表响应模型。

    Args:
        total: 满足筛选条件的任务总数。
        page: 当前页码（从 1 开始）。
        page_size: 每页条数。
        items: 当前页任务列表。
    """

    total: int
    page: int
    page_size: int
    items: list[TaskListItem]


class TaskArtifactItem(BaseModel):
    """任务产物项模型。

    Args:
        name: 产物文件名。
        relative_path: 相对 outputs 根目录路径。
        file_type: 产物类型（image/text/pdf/other）。
        url: 供前端访问的 URL。
    """

    name: str
    relative_path: str
    file_type: Literal["image", "text", "pdf", "other"]
    url: str


class TaskArtifactsData(BaseModel):
    """任务产物列表响应模型。

    Args:
        task_id: 任务 ID。
        items: 任务产物列表。
    """

    task_id: str
    items: list[TaskArtifactItem]


class TaskResultError(BaseModel):
    """任务失败信息模型。

    函数名称: TaskResultError
    参数说明:
    - error_code: 错误码。
    - error_message: 错误消息。
    - error_detail: 错误详情。
    """

    error_code: str
    error_message: str
    error_detail: str


class TaskResultData(BaseModel):
    """任务结果返回模型。

    函数名称: TaskResultData
    参数说明:
    - task_id: 任务ID。
    - status: 任务状态。
    - result: 成功结果对象。
    - error: 失败结果对象。
    """

    task_id: str
    status: TaskStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[TaskResultError] = None
