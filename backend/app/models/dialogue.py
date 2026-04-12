"""问答对话相关请求与响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DialogueAnalysisTypeItem(BaseModel):
    """问答分析类型条目。"""

    analysis_type: str = Field(description="分析类型编码。")
    label: str = Field(description="分析类型显示名称。")
    report_count: int = Field(default=0, description="可用报告数量。")


class DialogueAnalysisTypeData(BaseModel):
    """问答分析类型列表响应数据。"""

    items: list[DialogueAnalysisTypeItem] = Field(default_factory=list, description="分析类型列表。")


class DialogueReportItem(BaseModel):
    """问答可选报告条目。"""

    report_id: str = Field(description="报告唯一标识。")
    task_id: str = Field(description="报告来源任务 ID。")
    title: str = Field(description="报告标题。")
    created_at: str = Field(description="创建时间字符串。")
    snippet: str = Field(default="", description="报告摘要预览。")


class DialogueReportListData(BaseModel):
    """问答报告列表响应数据。"""

    analysis_type: str = Field(description="当前分析类型。")
    items: list[DialogueReportItem] = Field(default_factory=list, description="报告列表。")


class DialogueMessage(BaseModel):
    """问答消息对象。"""

    role: str = Field(description="消息角色（user/assistant）。")
    content: str = Field(description="消息内容。")


class DialogueChatRequest(BaseModel):
    """问答请求参数。"""

    analysis_type: str = Field(default="none", description="分析类型。")
    report_id: str | None = Field(default=None, description="关联报告 ID。")
    question: str = Field(min_length=1, description="用户问题。")
    history: list[DialogueMessage] = Field(default_factory=list, description="最近对话历史。")
    system_prompt: str | None = Field(default=None, description="用户自定义系统提示词。")


class DialogueChatData(BaseModel):
    """问答响应数据。"""

    answer: str = Field(description="模型回复内容。")
    report_id: str | None = Field(default=None, description="本轮使用的报告 ID。")
    used_excerpt: str = Field(default="", description="本轮检索到的报告片段。")
