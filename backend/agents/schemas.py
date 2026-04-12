"""谱图 Agent 共用的输入输出约定（脚本 / API 一键调用）。"""

from typing import Any, Dict, List, NotRequired

from typing_extensions import TypedDict


class SpectrumAgentResult(TypedDict, total=False):
    """单谱图分析的标准化返回结构。

    Attributes:
        structured_data: 可 JSON 序列化的解析结果（峰、积分、分子量、SMILES 等，依谱学类型而定）。
        text_report: 人类可读报告（建议 Markdown 纯文本）。
        errors: 非致命错误信息；若整次任务失败可将首条错误写入并视情况留空 structured_data。
        metadata: 谱学类型、样品名、版本等元信息。
    """

    structured_data: Dict[str, Any]
    text_report: str
    errors: List[str]
    metadata: NotRequired[Dict[str, Any]]
